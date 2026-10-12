# The native build online

Started 2026-10-12. The native build of Champions: Return to Arms (SLUS-20973 v2.00; the
game's code translated to C++, `docs/issues/native-recomp.md`, `native-app.md`) played
lockstep games over the hidden LAN start (`native-net.md`) but could not reach the lobby
server. This file is the work that takes it there: the design, what was **Ran** (with
what was seen), what was only built, and what is left. Nothing derived from the game is
in the repository: translations, programs, logs and cards are under `local/recomp-out/`.

## Status (2026-10-12, 15:20)

All **Ran** against the lobby server on this computer, with throwaway names made by the
tests; a native copy under test is started with `net-local-only=1` and sends nothing
beyond this computer. The machine was shared with other jobs the whole time: the load
average is quoted with every run (100 to 550 on 18 cores).

| What | Result |
|---|---|
| a native instance to the lobby's game list, from power-on | 17 s of real time; gateway 18 bytes out and 35 in, as the rig's capture |
| two native instances in one lobby game (host by code, join by code) | 7,610 ticks through a level change and a fight, **no shared column differs**; the game's own checksum exchange agreed every round |
| native + emulator application, native hosting | 3,062 ticks (drawn input on both from tick 200); checksum exchange agreed on both; 40 samples of the emulator copy equal the native tick log, 0 different |
| native + emulator application, emulator hosting | 2,413 ticks; the same; 34 samples equal, 0 different |
| the window program `rta_app` in a lobby game (as host, as joiner) | 1,229 and 1,684 ticks (the second with a level change), no shared column differs |
| one-step online: name asked once, account made, login saved 0600, used again | Ran on a terminal; no saved password in any of 240 output files |
| Host / Join by code, the character used last | Ran (every pair after its first run) |
| patch-set announcement | figure 3f5b1e14 (90 words), the application's; told and understood both ways with the emulator application; two native copies with different sets are both warned |
| characters saved by the periodic save, loaded at the next log-in | gold written in one tick came back in a new session on both copies |
| the name question on the window (a sheet), the note in the window's title | **built, not run**: a test window has nobody to answer, and no other window was opened on this computer |

## Where the cut is, and why

Two ways were open:

- **(a)** run the game's own network stack natively and put a virtual adaptor under it, as
  the emulator-based application does (`tools/play-net/src/RtaNet.cpp`);
- **(b)** answer Sony's network library at its entries, as `tools/recomp/net/netshim.cpp`
  does for the ten entries of the LAN start.

**(b) was taken.** What decided it:

1. **The stack is not in the executable.** The game's side of the network is three
   layers of its own code — the lobby client (SOEGamesAPI: framing, encryption), the peer
   library (SOE UdpLibrary: handshake, reliable channel) and the lockstep netcode — and all
   three end in Sony's libnet (0x364fb8–0x366550), which does nothing but carry each call
   by RPC to the I/O processor. The TCP/IP stack itself is eleven I/O-processor modules
   (`inet`, `inetctl`, `netcnf`, `ppp`, `pppoe`, `dev9`, `smap`, `msifrpc`, `libnet`,
   `eznetcnf`, `eznetctl`): MIPS R3000 code for a second processor, a second kernel and an
   Ethernet chip, none of which the native build has (it answers the I/O processor's
   services, it does not run its programs). Running that natively means translating
   Sony's modules and writing an I/O-processor kernel and a chip model for them — none of
   it code of ours, and none of it deciding anything a server or another player sees.
2. **The ERX modules are not on the lobby path.** `LIBINSCK.ERX`, `NG_INSCK.ERX` and
   `DNAS_NET.ERX` are loaded by the network window (`FUN_0033ed70`, states 0xc, 0xd, 9,
   10, 6 of the word at +0xdb4) for one purpose: the sign-in with Sony's servers, which
   are gone. With the project's local sign-in patch the window is done before any of them
   is loaded (**Ran**: no ERX file is asked for on the way to the lobby or in a game). Translating them ahead of
   time, as `native-recomp.md` planned, would serve a step that cannot succeed.
3. **The boundary is narrow and says everything.** 15 library entries and 13
   configuration-client entries. Above them every byte the server and the other players
   get is produced by the game's own translated code; below them a stream is a host TCP
   connection and a datagram a host UDP datagram. The emulator-based application ends the
   game's TCP in its own code and carries the bytes on host sockets too, so toward the
   server and toward other players the two builds do the same (what differs is listed
   under "Behaviour that differs from the emulator build").

It was also the soonest: the first run of the first build reached the game list.

## Design

| File | Does |
|---|---|
| `tools/recomp/net/hle-online.txt` | the addresses the driver supplies (`recomp.py --hle-add`) |
| `tools/recomp/net/netdrv.cpp`, `netdrv.h` | the library entries on host sockets; the network setting; the patch-set announcement; the tick log and tick-keyed writes of a test run |
| `tools/recomp/net/online.cpp` | joins the one-step driver of the emulator build (`tools/play-net/src/RtaOnline.cpp`, linked unchanged) to the runtime; script commands; the Config button |
| `tools/recomp/net/online_mac.mm` | the name question, the note and the set warning on the window (AppKit); linked into `rta_app` only |
| `tools/recomp/net/build_online.py` | `bin/rta_native_online`: the headless program with the network |
| `tools/recomp/net/play-native.sh` | starts `rta_app` with the options of `tools/play-net/play.sh` (`--server`, `--online`, `--host [CODE]`, `--join CODE`, `--choose-character`, `--player N`) |
| `tools/recomp/net/lobbypair.py`, `lobbyapp.py` | test: two copies (headless native, the window program, or the emulator application) through the lobby into one game, and the comparison |
| `tools/recomp/recomp.py` | new options `--hle-add FILE` (one more list of supplied addresses) and `--extra-pnach FILE` (a patch file from outside the repository, applied whole; its words follow the fix set's in `patches.cpp`, and `recomp_patch_set_words()` says how many belong to the set) |
| `tools/recomp/app/build.py` | `rta_app` is translated with the network list and the local sign-in patch (when present) and links the four network files |

Nothing in `tools/recomp/rt/` was changed, and `rt.h` / `iface.h` are as they were. The
driver sets itself up from the game's `main()` (an entry of its list): it reads its
options with `rt_option`, puts itself in front of the controller source
(`g_hooks.pad`), and chains `script_app_command` and `rt_at_finish`. `rta::NetDriver` in
`iface.h` stays reserved: the driver is linked at the entries, as the sound library is.

### The entries

| Address | Entry | Answered with |
|---|---|---|
| 0x365ec0, 0x365f88 | `sceLibnetInitialize`, `sceLibnetTerminate` | 0 |
| 0x365a08, 0x365a90 | `sceInetGetInterfaceList`, `sceInetInterfaceControl` | one interface; code 9 its address (this copy's made-up one), code 8 "up, running" |
| 0x3654a8 | `sceInetCreate` | type 0 a datagram socket on the game's port, 1 a stream to the address and port of the block, 3 the raw (ICMP) socket the peer library opens beside its data socket |
| 0x365518 | `sceInetOpen` | a stream: a host `connect` that does not block; 0, or −500 while it is under way |
| 0x3651e0 | `sceInetPoll` | bit 4 (out) for a connected stream, which is what the lobby client waits for |
| 0x365780, 0x3655a8 | `sceInetSend`, `sceInetRecv` | bytes moved, −500 for "not now", an error once the server has closed (the game then connects again by itself, as on the rig) |
| 0x365830, 0x365670 | `sceInetSendTo`, `sceInetRecvFrom` | one datagram; −500 when none waits |
| 0x365560 | `sceInetClose` | a stream is closed; a datagram socket's host socket stays |
| 0x365288, 0x365348 | `sceInetName2Address`, `sceInetAddress2String` | dotted text both ways (the peer library converts every address through text); the lobby's name gets the server's address; any other name does not exist |
| 0x364fb8 | `libnet_callRpc` | every other library entry ends here: an error, and a line in the report (none was called in any run) |
| 0x367da8 … 0x368270 | `ezNetCnfInit`, `Exit`, `GetCount`, `GetCombinationList`, `GetProperties` | the settings found in the card directory's `mc0/BWNETCNF`: the 0x800-byte list as the emulator's module fills it (head 6, 1, 1; per entry state 0 or −8, kind 2, three names of 64 bytes) |
| 0x37a5d8 … 0x37ad38 | `ezNetCtlInit`, `Exit`, `SetProperties`, `SetCombination`, `UpInterface`, `DownInterface`, `GetStatus`, `WaitEventTO` | the interface is "starting" for 20 vertical blanks after `UpInterface` and then as read on the emulator with the line up: 1, "eth0", 2, state 3, link 1; `DownInterface` leaves event 0xb for the next wait |
| 0x137a10, 0x13e638 | `net_loadModules`, `net_linkCheck` | 1 and 1, as the LAN shim |
| 0x323dcc | `main` | set-up, then the original |
| 0x3226e4 | `tasks_run` | the original; the call from `net_frameLoop` is one lockstep tick (tick log, tick-keyed writes — test equipment, idle without its options) |

A libnet address is 16 bytes: a zero word, then the IPv4 address **as one 32-bit word of
the machine** (192.168.1.2 is 0xC0A80102; in memory the bytes run backwards). The peer
library converts through text both ways and would work with any layout the driver chose,
but the netcode writes the word itself. Seen: with the bytes read in network order the
launch datagrams went to the reversed address (123.1.168.192) and the game hung at launch.

### Below the entries: the emulator application's rules

`netdrv.cpp` does under the entries what `tools/play-net/src/RtaNet.cpp` does under the
game's stack, rule for rule:

- a made-up own-network address per copy (198.19.x.y, made once, kept in
  `<data>/online-address`); the game reports it to the lobby server and other players'
  games try it — those attempts are not carried, "as between two houses";
- a server on this computer is reached at the computer's outside address, so that the
  server sees an address other players can use; the lobby's host name is answered with
  that address, and an address the gateway's reply names for the lobby is taken for the
  server when the server is local or private (read from the 0x43 reply as it passes);
- one host UDP socket per UDP port of the game, with the same number when free, kept for
  the whole run: the lobby server sees the pair other players must send to, and the
  netcode that opens the port again at launch keeps the path the peer handshake opened;
- the server's address on a port that is not the server's is another copy on the server's
  computer and goes through the loop-back interface; what comes back is shown to the game
  as coming from the address it sent to;
- every other player heard from is told this copy's patch set (the mark `RTAset1` after a
  keep-alive of the game's UDP library) and its arithmetic (`RTAari1`: can do the
  console's, does the console's); theirs are taken out before the game sees them.

### The network setting

"Internet Game" wants a network setting on the memory card. The driver writes the four
files of `BWNETCNF` into `<card>/mc0` when they are missing — the same bytes the emulator
application writes, so a card directory goes back and forth between the two builds — and
answers the configuration clients from what is in that directory (a card that holds more
settings, made by Sony's program in the emulator, lists them all).

The network screen offers "Config" (triangle), which restarts the machine into Sony's
network settings program on the disc — a second executable the native build does not
contain. As in the emulator application, the button is not passed on while that screen
lists the setting (**Ran**: the screen stays; cross then accepts and the game connects).

### The sign-in step

`build_online.py` and `app/build.py` hand `local/SLUS-20973_4028A55F_signin.pnach` to the
translator when the file is there (`--extra-pnach`; `RTA_SIGNIN_PATCH` names another
place). Its words are applied to the image before translation and written to memory with
the fix set's; they are not counted in the patch-set figure, as in the application.
Nothing of the file is in the repository, printed or logged; without it the game stops
at its sign-in step. The skip is not re-implemented in any code here.

### Options

`--opt key=value` to the runtime (after `--` for `rta_app`): `net-server`,
`net-server-public`, `net-data`, `net-card`, `net-netcnf=0`, `net-addr`,
`net-loopback=on|off`, `net-ports=0`, `net-set-quiet=1`, `net-local-only=1`, `net-pace=HZ`,
`net-log=FILE`, `net-log-all=1`, `online=lobby|host[:CODE]|join:CODE[+choose]`,
`online-name=NAME[,NAME…]`, `online-person=0`, `tick-log`, `tick-watch-file`, `tick-do`.
`netdrv.h` describes each. Script commands: `app online start MODE`, `app online stop`,
`app online name NAME`, `app online`, `app net peers`, `app net drop`.

## What was run

Headless copies are `bin/rta_native_online`, held to 59.94 vertical blanks a second
(`net-pace`); the lobby's time-outs count frames, and the server and the other copy answer
in real time. "Compared" is `tools/rig/compare.py ticks` over the two tick logs with the
rig launcher's columns (tick, shared seed, level, player count, button maps, the previous
tick's sync record, and for both players position, facing, action state, object seed, hit
points, mana, gold, experience, three bags, statistics, points, equipment, abilities,
skills) plus the lobby flag and `g_checksumFailed`.

| Run (`local/recomp-out/online/`) | Load | Result |
|---|---|---|
| `n1`: one copy, `online=lobby`, new account | 24–40 | game list at 16.9 s; 2 TCP connections, 928 bytes out, 1,525 in |
| `pair1`, first run with characters: host + join | 129 | launched at frame 3,205 of the host (53 s); 2,117 ticks compared, nothing differs |
| `pair2`: new accounts, new characters by script, `--play 3000 --level drunare --play2 3600` | 196 | 7,610 ticks compared (3,900 in `hub`, 3,710 in `drunare`), **nothing differs**; 95 and 332 distinct hit-point values (both die in the arena fight); checksum tables equal in all rounds (23 values); 4 saves answered |
| `x1`: native hosts, emulator application joins | 553 | 3,062 ticks, drawn input on both from tick 200; `g_checksumFailed` 0 and expected = received on both; 40 samples equal the native tick log in every column, 0 different |
| `x2`: emulator application hosts (new character through its control socket), native joins | 448 | 2,413 ticks; the same; 34 samples equal, 0 different |
| `pair1`: `rta_app` in a test window hosts, headless joins | 366 | 1,229 ticks compared, nothing differs; the pair ran at the window copy's speed, about 32 ticks a second |
| `pair1`: headless hosts, `rta_app` joins, level change in tick 1300 | 272 | 1,684 ticks compared, nothing differs |
| `pair2`, two sessions: the save round trip (below) | 361, 374 | 5,602 and 616 ticks compared, nothing differs |
| `pair1`: host with the 26 sections, joiner with 25 | 432 | both warned (below); 553 ticks in `hub`, nothing differs |
| `idle26`, `idle25`: no input after the launch (below) | 380–430 | nothing differs; the input is not stuck |

**The emulator copy has no tick log.** What it leaves is samples: one batch of control
commands reads the tick counter, the shared seed, both positions as raw bits, hit points,
gold and experience, and is kept when the counter is the same at both ends of the batch.
Each sample is looked up in the native copy's log at the tick before the counter (a
vertical blank falls between two ticks). In 5 of the 74 equal samples the emulator copy's
own player stood at its predicted position (`net_predictLocalPlayer` runs once per drawn
frame); those three columns are counted apart. This is weaker than a row-for-row
comparison; the game's own checksum exchange, which ran every 240 ticks on both copies
and never failed, is the other half. No level change was made in the mixed pairs: the
application has no tick-keyed write.

**On the wire** a native copy looks as the rig's captures of the emulator do
(`live-rig.md` 13.4, 19): gateway request 18 bytes, reply 35; the lobby connection; one
52-byte discovery datagram to port 10101; the one-byte seek, the 14-byte connect request,
the welcome; game port in 4000–4004 (4000, 4001 and 4004 seen), the host socket with the
same number unless another program on this computer held it.

### Conveniences

- **Name asked once.** Headless on a terminal with no saved login: the driver asks, an
  answer of two characters is refused with the rule and asked again, the account is made,
  the login is saved (`online-login`, mode 0600). Second start: "a saved login for it is
  there", the log-in form, the game list; nothing asked. The 15 passwords the tests saved
  were searched for in all 240 files the tests wrote (logs, tick logs, the terminal
  transcript): 0 occurrences outside the login files.
- **Host / Join by code**, **the character used last**: every pair. A copy with a stored
  character takes it from the server's list by itself (0x5B, 0x5C); a new account gets
  the game's character screens, which the test scripts fill.
- **Patch set.** The native build shows 3f5b1e14 with 90 words — the application's figure
  for the 26 suggested sections; the two words of the sign-in patch are not in it. A
  native copy and the emulator application each log the other's set as "the same as this
  copy". A copy built without one section (88 words, a5c309fa) and a 26-section copy in
  one room: both print `WARNING: a player (…) has patch set …: they would fall out of step`.
- **In the window program** (`rta_app`): the same driver; `online_mac.mm` puts the name
  question on the window as a sheet, the driver's note (where it is, the code of a hosted
  game) and the server into the window's title, and the set warning into a sheet.
  **Not run**: a test window is left alone by design (its title stays "AGENT TEST - …",
  the name comes from `online-name`), and no other window was opened here. What ran in the
  window program is the game itself online, as host and as joiner.

### The save round trip

Session 1 (`pair2`, 5,602 ticks): the gold of both characters is written in lockstep tick
400 on both copies (500 → 12,345 for slot 0, 23,456 for slot 1), then nothing is pressed
for 5,400 frames. The periodic save (0x5E with its 0x5D piece) is answered with result 0
three times on each copy. Session 2, new processes with the same accounts: each copy
takes its character from the server's list by itself, the game is launched, and at tick 1
both copies have 12,345 and 23,456. The memory card has no part in it: no file of either
card directory changed after the copy's first boot.

## Findings

1. **The address word order** (above, "The entries").
2. **A timing dependency of the game's own launch.** On Start the host sends START to
   every peer, and `SRSClient_shutdownUdp` 0x328770 then waits for the acknowledgement
   before it disconnects: at most 100 rounds of `UdpManager_GiveTime` and
   `DelayThread(100)`. A joiner polls its socket every tenth frame, takes START, and
   fills its launch tables from the *live* connections on its next lobby-task call. On a
   console every empty receive of the peer library blocks 1 ms on the data socket and
   1 ms on the ICMP socket (the time-outs it asks for), so 100 rounds last over 200 ms —
   longer than the joiner's 167 ms between polls. With library calls that answer at once
   the 100 rounds are over in 10 ms: the joiner gets START and the disconnect in one
   poll, finds no live connection, fills its tables with address 0 (the uninitialised
   case `docs/netlib.md` describes under "Per-machine state", 2) and never launches.
   **Seen twice** before the fix: both copies in lobby state 12, the host sending 66
   datagrams, the joiner sending to 0.0.0.0:4000, no level. **Fix, in the driver**: a
   call that asked to wait and has nothing to give parks its game thread for that time
   on the virtual clock (`rt_sleep`) and looks once more. Every launch since has worked
   (13 of 13). The margin is the console's own: 200 ms against 167.
3. **The start ramp, and a check that was asked for.** In a lobby-launched game with
   nothing pressed, the stick value of the lockstep pad record (`g_pads[slot]+0x14`) is
   non-zero in ticks 1 to 5 (−0.25, −0.64, −0.75, −0.63, −0.24) for both slots on both
   copies, and both players move about 7 units; from tick 6 it is 0 and they stand. The
   same five values with the 26 sections and with "Net test: flush before a level load
   waits for the peers' tick" left out (25 sections), and the held word (+8) is 0 on every
   tick in both. The fault reported for the developer LAN start with that section (held
   word 0x500000 and stick bf91a47b for the whole game) **does not appear on the lobby
   path**: 1,797 and 1,815 idle ticks, and 1,845 more through a level load. With drawn
   input the record follows it (73 and 77 values of the held word, 126 and 105 of the
   stick, 508 and 476 positions) and ramps to 0 over five ticks when the stick is let go.
   One run each; native pair; `hub` and `drunare`.
4. **Bytes 0x38–0x3b and 0x50–0x53 of a pad record differ between the two copies** (two
   floats in the record of the other player's slot). Per machine; nothing in the
   comparison's shared columns depends on them.
5. **Other programs on the computer.** Game ports 4000–4004 are per computer: in most
   runs one native copy got another host port because a program on the computer held the
   game's number (other jobs ran emulator copies against the same lobby), which the rules
   above are made for. Once, after a native copy had quit, the emulator copy it
   had played with heard an arithmetic announcement from the port the native copy had
   used: another job's emulator had taken the freed port. Tests that share a computer
   share these ports.
6. **Two lines of the runtime's report that are not faults**: `eznetcnF.IRX` and
   `eznetctL.IRX` "not on the disc". They are the two configuration modules the game asks
   the loader for before it calls the clients this driver answers; the load is answered
   "loaded" and nothing reads them. No library entry went unanswered in any run, and no
   ERX file was asked for.

## Behaviour that differs from the emulator build

- No frame ever exists: there is no DHCP, ARP or DNS traffic, no TCP ended in a relay.
  The server and the other players see the same requests, replies and datagrams.
- TCP segments are cut by the host's stack (`TCP_NODELAY` is set, so the length word and
  the body the game sends separately leave as it sends them).
- The interface is "up" 20 vertical blanks after the game asks, where the emulator's
  stack takes its address by DHCP first.
- The arithmetic announcement says "can do the console's only". The emulator application
  can switch to a browser copy's arithmetic; the native build cannot, and warns when a
  player says it computes that way. A game with a browser copy was not tried.
- Library calls cost what they asked to wait and nothing else; on the emulator each is an
  RPC through the emulated I/O processor. Finding 2 is where that mattered.
- Nothing is relayed for `--arg --net` (the developer LAN start) by this driver:
  broadcast and made-up addresses are not carried. That start stays with
  `tools/recomp/net/netshim.cpp`.

## What remains for a native release online

**Timing.**

- The margin of finding 2 is the game's (200 ms against 167). A copy that is slow — the
  window program ran at about half speed under load here — stretches both sides alike,
  since both count frames; a joiner that stalls for a whole poll interval at the wrong
  moment would still lose the launch, as on a console. Not seen in 13 launches.
- A program without a window must be held to real time (`net-pace`, default 59.94): the
  lobby's time-outs count frames, the server answers in real time. Unpaced online runs
  were not tried.
- The game's thread must not stand still for long: the server drops a client it has not
  heard from for 120 s. Level loads take under a second here; the name sheet is a sheet
  for this reason (it does not stop the window's loop). A window being dragged, or the
  computer asleep, was not tried.
- The server's address is looked up before the game starts (a blocking `getaddrinfo`);
  inside the game nothing is looked up.
- Datagrams are read when the game asks, not at a frame boundary. Two native copies and a
  native with an emulator copy stayed in step with that; loss, delay and reordering on a
  real path were not tried (the loop-back interface loses nothing).

**Not exercised.** Private games (0x56, 0x57); chat typed by a player, friends, ignore,
messages; cancelling a join or a game (0x05, 0x60); deleting a character; importing a
memory-card character into the lobby; the "save the login on the memory card?" choice; a
third and fourth player; a player leaving a running game, the pause-menu exit back to the
lobby, a second game in one run; the line to the server cut during the lobby or a game
(`app net drop` exists; the loop of `live-rig.md` 19.9 was not provoked); the game without
the sign-in patch (it should stop at its sign-in error; not run); a server that is not on
this computer, two players on different networks, a router; a browser copy in the game;
the window program's sheet and title note (built, not run); a real person at the
controls.

**Windows.** The driver is POSIX: `socket`/`connect`/`poll`/`fcntl`, `getifaddrs`,
`getaddrinfo`, `SIGPIPE`, `_NSGetExecutablePath` for the default data directory. A
Windows build needs Winsock set-up and its names for the same calls (`WSAPoll`,
`ioctlsocket`, `closesocket`, `WSAEWOULDBLOCK`), `GetAdaptersAddresses` for "is this
address this computer's", and a place for the login file whose access is the user's alone
(`RtaOnline.cpp` relies on mode 0600). `online_mac.mm` needs a counterpart for the name
question (or the terminal's, which is in `online.cpp`). Until then a build that does not
link the driver gets the translated originals of the listed entries (`hle_weak.cpp`) and
plays offline as before.

**Other.** The network settings program (Config) is kept away rather than run. The
`rta::NetDriver` shape in `iface.h` is still unused; if the runtime ever owns the library
entries, `netdrv.cpp` is one implementation of it.

## How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/net/build_online.py          # bin/rta_native_online (the sign-in patch from local/, when there)
python3 tools/recomp/app/build.py                 # bin/rta_app, with the network
O=local/recomp-out/online

# one copy to the game list
mkdir -p $O/n1
printf 'until 0x506160:u32 == 5 timeout 12000\nwait 600\napp online\nquit\n' > $O/lobby.rig
RTA_NATIVE=$PWD/local/recomp-out/bin/rta_native_online python3 tools/recomp/native.py boot \
    --card $O/n1/card --opt net-data=$O/n1 --opt net-local-only=1 --opt online=lobby \
    --opt online-name=SomeName --opt online-person=0 --opt net-log=$O/n1/net.log --script $O/lobby.rig

# two copies through the lobby into one game; --host / --join: native, window, app
python3 tools/recomp/net/lobbypair.py run $O/pair2 --play 3000 --level drunare --play2 3600
python3 tools/recomp/net/lobbypair.py run $O/x1 --host native --join app --play 3000
python3 tools/recomp/net/lobbypair.py run $O/x2 --host app --join native --play 3000
python3 tools/recomp/net/lobbypair.py run $O/pair1 --host window --join native --play 1800

# the save round trip: session 1 writes, session 2 reads the tick log's first row
python3 tools/recomp/net/lobbypair.py run $O/pair2 --idle --play 5400 \
    --tick-do "400 poke32 g_players+0xe4 12345" --tick-do "400 poke32 g_players+0x4c30+0xe4 23456"
python3 tools/recomp/net/lobbypair.py run $O/pair2 --idle --play 300

# a person: the window program, as the emulator build is started
tools/recomp/net/play-native.sh --disc "$RTA_DISC" --host
tools/recomp/net/play-native.sh --disc "$RTA_DISC" --player 2 --join CODE
```

A copy started by `lobbypair.py` keeps its name in `OUT/<role>/name` and its login in
`OUT/<role>/online-login`; a run directory can be used again (the character used last is
then taken by itself).

## Files

`tools/recomp/net/`: `hle-online.txt`, `netdrv.h`, `netdrv.cpp`, `online.cpp`,
`online_mac.mm`, `build_online.py`, `play-native.sh`, `lobbypair.py`, `lobbyapp.py`.
Changed: `tools/recomp/recomp.py` (`--hle-add`, `--extra-pnach`), `tools/recomp/app/build.py`
(the network in `rta_app`). Linked unchanged: `tools/play-net/src/RtaOnline.cpp`.
Everything generated or logged: `local/recomp-out/gen-online*`, `obj-rta_native_online*`,
`bin/rta_native_online*`, `online/`.
