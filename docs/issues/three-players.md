# Three and four players do not launch from the online lobby

**State (2026-10-12, 21:50 CDT), final. Two causes, both found, both fixed, both needed:**

1. **The game's launch handshake and the address the lobby server tells a console as its
   own.** With players who share an address (one computer, one router, one relay) a
   joiner that takes the host's START later than another joiner can never be reached by
   it again; nobody gets into the level. **Fixed in the lobby server** (4 source files
   in the working tree of `server/upstream`, FIXES.md 32). No game patch.
2. **The emulator's Ethernet adaptor loses the second of two datagrams sent back to
   back.** Only a game of three or four sends two in one frame during its launch; the
   player whose keep-alive was the second one is left behind while the others go into
   the level counting it. This is the picture the earlier report describes. **Fixed in
   the emulated chip** (`Source/iop/Iop_Speed.cpp` / `.h` of Play!, in
   `tools/play-net/play-net.patch`). It needs a new application build and a new page
   build. No game patch, the patch set stays 3f5b1e14.

Proven on one Mac, every copy at one address, against a second server instance with the
change (the running local lobby was not rebuilt, restarted or reconfigured; nothing
touched the public server): three and four native copies, three and four copies of the
application built with the adaptor fix, two applications and a page through the current
relay, one application and two pages through it - the table is under "Proof". Not
tried: two computers, a real router, a person playing.

Related: [browser-build.md](browser-build.md) section "Mixed games" (the report this
started from), [native-online.md](native-online.md) finding 2 (the same hole in the
launch seen with two players), `docs/lobby-protocol.md` 9, `docs/netcode.md` "Launch".

## The defect as reported

Three players on one Mac reach one room through the local lobby server. At *Start Game*
two machines go into the first level, with three players counted; the third stays behind
with the game's message that some players are un-reachable and the launch has failed.
3 of 3 tries with two application copies and a page, 2 of 3 with three application
copies. Two players work in every combination.

## Cause 1: the launch handshake and "my own address" (the game; healed by the server)

It needs two things at once.

**A race between the joiners at Start.** A machine that takes the host's START (lobby
client message 0x1a, flag 0x100 at client+0x64) goes to lobby state 7 (0x324288,
`case 7`). There it fills the launch tables from its *live* connections to the other
players: 0x32e198 takes address and port from a player's first connection whose status
is 1. Then it calls `SRSClient_shutdownUdp` 0x328770, which - with nothing left to be
acknowledged - disconnects every player at once. A joiner reads its socket every tenth
frame, so two joiners take START up to 167 ms apart. The one that is first has closed
its connection to the other before the other has filled its tables. For a player without
a live connection 0x32e198 writes nothing, and state 7 then stores what its two stack
variables still hold: the address and port **of the player before it in the table** (the
host's), or 0 and a leftover for the first. The host is not affected: it fills its
tables when it sends START.

**The launch handshake repairs a wrong address - unless the sender has this machine's
own address.** `net_launchUpdate` 0x135638 finds the sender of a launch datagram by the
player number inside it. When the datagram's source is not the address and port it has
for that player (0x1358e0 - 0x1359f4):
- source address == this machine's own entry in the address table 0x402b3b - in a lobby
  game that is this machine's *external* address as the lobby server told it (0x3E for a
  host, 0x40 for a joiner; handlers 0x330128 and 0x32a0d0 store it at client+0xd10): the
  player is re-addressed to its entry in the second table 0x402b4b and port 4000 ("two
  consoles behind one router"). The developer LAN start fills that second table
  (0x1e21e0); **the lobby start never does**, so the player becomes 0.0.0.0:4000 and is
  not reached again;
- any other source: the player's address and port are taken from the datagram, and at
  the end of the launch written back to the tables the game's peer table is made from
  (0x136ff0 onward).

Between two houses the second branch repairs what the race broke, which is why the
original game worked. **On one computer, behind one router that loops traffic back, or
through one relay, every other player's datagrams come from this machine's own external
address**, the first branch is taken, and the launch never completes between the two
joiners. Nobody gets into the level; 45 seconds later the launch fails.

The same repair also covers the accept rule of the peer library
(`SRSClient_onPeerConnected` 0x32c2c0 takes an arriving connection for the first sought
player with that *address*, whatever the port): a fourth player whose two fellow joiners
share an address files them the wrong way round. Seen in four launches of four
application copies (ports of players 1 and 2 swapped in the fourth copy's tables); with
the fix all four launched and stayed in step, because the handshake goes by the player
number in the datagram.

### The run that shows it

`local/three-players/n3a/run-fail` (three headless native copies, the 26 sections, set
3f5b1e14, the unchanged local lobby, load average 306). Nobody reached the first level.
Host port 4000, joiner 1 port 4004, joiner 2 port 53777, all at 192.168.1.123.

- Host's log (ms): START to both joiners at 79883; joiner 1's acknowledgement and its
  disconnect (peer-library type 5) at 79971; joiner 2's acknowledgement at 80026.
- Joiner 2's log, one read of its socket at 77298: START from the host, then the
  disconnect from joiner 1 (8 bytes, `00 05`). Its own debug lines: "Got START from
  host", "Terminating known peer 0" - and no line for joiner 1, whose connection was
  gone already (a run that worked has that line on both joiners).
- Joiner 2's port table 0x402b5c right after: 4000, **4000**, 4004 (host, joiner 1, own)
  - joiner 1's entry is a copy of the host's. Host and joiner 1 have 4000, 4004, 53777.
- Joiner 2 at 78044: a 512-byte launch datagram arrives from 192.168.1.123:4004 with
  player number 1; its answer goes to **0.0.0.0:4000**, and so does every later one (422
  datagrams not carried). Its launch record for player 1: address 00000000, port 4000,
  state 2. Joiner 1's record for player 2 stays in state 0. Host: both records done.

The same in the released application: with the last joiner's machine held still for two
seconds at Start Game its launch record for the other joiner reads `00000000:4000`,
state 2, and nobody is in the level 150 s later (2 of 2).

### The fix

**The lobby server stops telling a Return to Arms client its own observed address.** In
notifications 0x3E and 0x40 it sends `0.0.0.0` (the port unchanged). The game uses that
address for one thing only: the test above. (client+0xd10 is read by state 7; it is also
written into the peer record a machine sends about itself, from which the receivers take
no address: 0x32ca18 case 0x1b copies the name and two bytes, 0x32a1b8 skips a player it
already knows, and the host is known to everyone it sends to.) With 0.0.0.0 the test is
never true and a wrong address is always repaired from the datagram.

In the working tree of `server/upstream` (the files as they were:
`local/three-players/server-before/`):
- `Include/configuration.hpp`, `Source/configuration.cpp`: a setting
  `rta_tell_console_its_observed_address` (default 0; 1 gives the old behaviour) and
  `Config::OwnAddressForRta(observed)`; the reason is written above the function.
- `Source/Network/Event/NotifyGameDiscovered.cpp` (0x3E, Return to Arms clients only;
  Champions of Norrath clients are told what they were told before - that game was not
  read) and `NotifyClientDiscovered_RTA.cpp` (0x40).
- `FIXES.md` section 32.
- `tools/lobby_e2e_test.py` of this repository: `observed_pair` - told 0.0.0.0, the test
  takes the address its own datagrams leave from as what the server observed (the file
  as it was: `local/three-players/lobby_e2e_test.py.before`). 40 of 40 with `--extended`
  against the instance with the change.
- `docs/lobby-protocol.md`: the rows for 0x3E and 0x40 and the table in 9.2.

What other players are told about a console (0x55, 0x57, 0x65) is unchanged, and so is
the server's check that a discovery datagram comes from the address of the session's
connection.

## Cause 2: the emulated Ethernet adaptor (the emulator; candidate (d), one layer below ours)

**Seen:** on the server with fix 1, three copies of the released application with the
last joiner held 2 s at Start Game: 0 of 3 launches - but now two copies were in the
level counting three and one was left behind. The same happened once in three launches
of four without any hold. The copy left behind had right addresses and had been done
with everybody (launch state 8); what it lacked was the other joiner's word that it
"sees everybody ready" (flag bit 8 at launch record +0x5d), which a machine asks for
with a keep-alive every 45 frames. A machine counts down 120 frames and goes when it has
that word from everyone; nothing tells the others.

**Read from packet captures of the copies** (`--rta-pcap`; the two joiners' captures are
kept in `local/three-players/captures-stable/`; `launchcap.py` lists the launch
datagrams with time, player number, type and argument):
- A copy that has two players in state 8 sends two keep-alives in one frame, one to
  each. In the joiners' captures the first of the two leaves the machine **twice, with
  the same IP identification, and the second never leaves**: the next datagram carries
  the identification after the missing one. The left-behind copy sent 58 such pairs in
  that run and lost 58 datagrams; its keep-alive to the other joiner never went out
  once. Its answers to the others' keep-alives (single datagrams) did go out - so they
  counted down and left.
- It is the same for any two datagrams written back to back; the launch survives the
  others by its retries, and which datagram of a group is lost shifts when an answer is
  sent in the same frame. That is why most launches of three got through and why it
  looked like load.
- A game of two never sends two datagrams back to back in the launch: two players
  always worked. The native build has no emulated adaptor: three and four native copies
  need only fix 1.

**Where:** `CSpeed::HandleTx` in `Source/iop/Iop_Speed.cpp` of Play! (the emulated SMAP
chip; the file is patched by `tools/play-net/play-net.patch` and the browser build
compiles the same file). It sent each ready descriptor's frame from
`m_txBuffer.data() + descriptor.pointer - 0x1000` and then emptied the buffer. Seen with
a log line in a test build: the game's driver **reads the chip's transmit write pointer
(register 0x10001004) before it writes a frame** and puts that into the descriptor. The
emulated chip had no such register (it read 0), so every descriptor said 0x1000 - right
for one frame at a time; of two frames written before the first "send", the first went
out twice and the second never. (For the same reason the first frame after the driver
starts went out as the driver's own 1516-byte test pattern.) Not a fault of the game.

**Fix:** the transmit buffer is the chip's ring of 4096 bytes with its write pointer;
register 0x10001004 reads (and sets) that pointer, bit 0 of the control register
0x10001000 empties the ring; `HandleTx` takes each ready descriptor's frame from where
the descriptor says, oldest descriptor first, and nothing is emptied.

- `tools/play-net/play-net.patch`: **only its two sections for `Source/iop/Iop_Speed.cpp`
  and `Iop_Speed.h` were replaced** (the patch as it was:
  `local/three-players/play-net.patch.before`; before replacing, the old sections were
  checked to be byte for byte what the released source has). In those sections the new
  parts are: `HandleTx` rewritten, a new `TxFifoWrite`, `REG_SMAP_TXFIFO_CTRL` and
  `REG_SMAP_TXFIFO_WR_PTR` in the register enum and in `ReadRegister` / `WriteRegister`,
  the two data paths (register and DMA) writing through `TxFifoWrite`, `Reset`, and the
  members `TX_FIFO_SIZE`, `m_txFifoWr`. Everything the patch did to these files before
  is still in them.
- The two files as changed: `local/three-players/Iop_Speed.final.cpp`, `.final.h`.
- A tree that has the old patch applied needs `tools/play-net/build.sh --reset`; the
  page's tree has to be made anew (`tools/play-web/build.sh` says so itself).

With that build: in the captures of one launch of three, 0 frames sent twice and 0
datagrams missing among 2,255.

## The candidates, answered

- (a) matching by address without the port: **yes, but in another place than suspected**
  - the launch handshake's test against this machine's own address (cause 1); the accept
  rule's address-only match exists too and is repaired by the same handshake.
- (b) one of the 26 sections: **no.** Neither cause involves a section; failures and
  successes came with the same 26 sections. No bisection was run.
- (c) a time-out a loaded machine misses: **no time-out, but timing decides** - which
  joiner reads its socket first (cause 1), and whether an answer happens to be sent in
  the frame of the keep-alives (cause 2). Load changes the odds, not the mechanisms.
- (d) our own network layer or the lobby server: **cause 2 is in the emulator's adaptor
  under our layer; `RtaNet.cpp`, `RtaOnline.cpp` and the relay carry what they are
  given.** The server did what the original must have done; changing what it tells a
  console about itself is the cure for cause 1, not its origin.

A control from the soak work (its runs, not repeated here): with the developer LAN
start three and four native machines launch and stay in step for 30,000 to 60,000
frames. That fits: the LAN start writes every player's address into both tables from
the developer's list and needs no live connection, and native copies have no adaptor.

## Proof

All on one Mac, every copy at 192.168.1.123, the 26 suggested sections (set 3f5b1e14),
throw-away accounts on lobby servers on this Mac only. Load average 35 to 340 from other
jobs throughout (what the load decides is said above). "Fixed server" is the second
instance; on it client+0xd10 read 00000000 on every copy. "Stale" = a joiner's port
table 0x402b5c had another player's entry wrong when the launch began (cause 1's race
went the bad way). "Held" = the last joiner's machine stands still for 2 s from just
before Start Game (the application's `hang` test command), which makes it stale every
time. In step: for native copies `tools/rig/compare.py ticks` over every pair of tick
logs (seed, level, player count, button maps, every player's position, state, hit
points, gold, experience, out-of-sync flags, own sync hash of the previous tick), drawn
input on every copy; for application copies and pages every machine's ring of its own
per-frame sync hashes compared by frame, and the rings of hashes received from the
others, players walking and swinging.

| Players and copies | Server | Launches | All in the level | Lockstep frames in step, each launch | Notes |
|---|---|---|---|---|---|
| 3 native | no fix | 7 | **3** | 2,617 - 2,719 | the 4 failures are exactly the 4 stale ones, each with an answer to 0.0.0.0:4000 |
| 3 native | fixed | 6 in a row | **6** | 2,529 - 2,719 | all 6 stale |
| 4 native | fixed | 4 in a row | **4** | 2,537 - 2,719, all 6 pairs | all 4 stale, two or three wrong entries each |
| 3 native, client+0xd10 set to 0 by the test script | no fix | 3 | **3** | 2,715 - 2,719 | all 3 stale; shows it is that one value |
| 3 application, released build | no fix | 5 | **5** | 1,120 - 2,185 | never stale by itself |
| 3 application, released build, held | no fix | 2 | **0** | - | nobody in the level; record `00000000:4000` |
| 3 application, released build | fixed | 2 | **2** | 2,103 and 2,279 | not stale |
| 3 application, released build, held | fixed | 3 | **0** | - | cause 2: two in, one left behind (twice); once the host alone |
| 4 application, released build | fixed | 3 | **2** | 1,621 and 3,117 | the failure: three in, one left behind |
| 3 application, **build with the adaptor fix**, held | no fix | 2 | **0** | - | nobody in the level: fix 2 alone is not enough |
| 3 application, **build with the adaptor fix**, held | fixed | 3 in a row | **3** | 1,741, 1,686, 1,529 | all 3 stale |
| 4 application, **build with the adaptor fix** | fixed | 4 in a row | **4** | 1,479, 2,298, 1,444, 2,918 | players 1 and 2 swapped in the fourth copy's tables in two of them |
| 2 application + 1 page, **both with the adaptor fix**, through the relay | fixed | 3 | **3** | 2,089, 2,755, 2,074 | one stale; the application hosts; "Everyone computes the same way: 2 other players heard ... browser arithmetic" |
| 1 application + 2 pages, **both with the adaptor fix**, through the relay | fixed | 3 in a row | **3** | 2,942, 2,906, 1,886 | none stale; two browser players in one game, both at the relay's address |

Not counted as launches (nobody was in a room): runs in which a lobby server did not
answer a copy within 20 s (five native runs and two application runs, at moments when
several copies logged in at once on the loaded Mac - both server instances at the same
moments; not looked into further), two in which a copy's one-step driver stopped on a
screen before the room, and one in which a new character's made-up name was taken.

Also run: `tools/lobby_e2e_test.py 192.168.1.123 --gateway-port 41810 --extended`
against the fixed instance, 40 of 40.

In four native runs made before 16:12 the joiners had their player numbers in the order
they joined, not the order the test started them, and the test's hash column read
another player's ring on those copies; in those runs that one column differs and every
other column is equal on every tick. The column was corrected (it follows the byte at
0x402a39); later runs with the numbers out of order compare clean.

## What it covers, and what it does not

- **Players who share an address behind one router:** fix 1 removes the game's test that
  broke them, for every copy (application, page, native, a console), whenever the two
  reach each other at the router's outside address - the same path as on one computer,
  which is what was run. Not run with a real router. A router that does not loop
  traffic back keeps two of its players from connecting in the room at all
  (`docs/lobby-protocol.md` 9.3); that is as it was and is not touched.
- **Browser players behind the relay:** they all have the relay's address, so fix 1 is
  what lets two of them (or one and a player on the relay's computer) be in a game of
  three; run with one page (three launches) and with two pages (the last row above).
  The server's discovery check (the datagram's source address must be the address of
  the session's connection) is not changed and is not in the way: a page's connection
  and its datagram both come from the relay.
- **A copy without the adaptor fix** in a game of three or four can still be left
  behind, and it is that copy which is at risk: every player needs the new application
  or page. Native copies need nothing new.
- Fix 1 does not close the hole it works around: a START that is lost and sent again,
  so that another joiner's disconnect arrives *before* it, makes the game renumber its
  players (0x32d098). Not seen here (nothing is lost on one computer).

## To release (the owner's steps)

1. **Lobby server:** `sh build.sh` in `server/upstream`, restart the local lobby,
   redeploy the public one. Covers every copy players already have for cause 1.
2. **Application:** a new build from `tools/play-net/play-net.patch` as it is now
   (`build.sh --reset` on a tree that has the old patch).
3. **Page:** a new build with the same patch (a fresh `local/play-web-src`), and the
   page redeployed. The relay needs nothing from this work.
4. Nothing changes in `patches/SLUS-20973_4028A55F.pnach` or `sections-suggested.txt`;
   the set stays 3f5b1e14. `tools/play-net/proposed-three-players.pnach` was not needed
   and does not exist. (The release of the same evening changed one section for another
   reason - the flush section's third word, `docs/issues/native-soak.md` finding 1 - and
   with it the figure: 27f61e1d, 91 words.)

## Where things are

Scratch files of this work, `local/three-players/` (not in the repository):

- `nplay.py OUT --players N [--second-server] [--log-all] [--own-zero]`, `series.sh`,
  `analyze.py`: N headless native copies through a lobby on this Mac into one game, the
  pairwise tick comparison, one result line per run (`*.results`, logs in
  `<series>/run<k>/`).
- `aplay.py NAME --players N [--second-server] [--launches K] [--hitch S] [--pcap]
  [--app BINARY]`: copies of the emulator application, each with `--rta-test`, a data
  directory of its own and `--rta-server <this Mac>`; reads each copy's log for its
  server line first; tables at the start of the launch; sync hashes.
- `apppage.py up | run NAME apps=A pages=P [launches=K] [app=BINARY] | down`: the same
  with pages in Chrome windows of the test's own, a relay on 127.0.0.1:8991 pointed at
  the second instance and a page server on 127.0.0.1:8990 serving `site/`.
- `launchcap.py FILE.pcap`: the launch datagrams in a copy's capture (numbers only).
- `server/`: the copy of the server source the second instance was built from (equal to
  `server/upstream` now), `server/bin/config.ini`: bound to 192.168.1.123, every port
  the usual one plus 1000, own database.
- `redirect.c`, `redirect.dylib`: loaded into a TEST copy with `DYLD_INSERT_LIBRARIES`
  it turns the game's built-in gateway port 4081x into 4181x and sends the discovery
  datagram to the second instance; it refuses any address but this Mac's.
- `play-src`, `play-build`: the released application's source with the adaptor change,
  and its build. `web-src`, `web-build`, `site`: the same for the page.
- `captures-stable/`: the two joiners' captures from a failing launch of the released
  build. `down.sh all`: ends everything this work started, by pid.

## How to reproduce

```
# cause 1, native copies on the unchanged local lobby (fails in about half the runs):
python3 -B local/three-players/nplay.py local/three-players/n3a --players 3 --play 600 --limit 300 --log-all
#   a failing run ends "LAUNCHED: host=NO j1=NO j2=NO"; a joiner's net.log has "UDP to 0.0.0.0:4000 not carried"

# cause 1 in the released application (fails every time): the unchanged local lobby, the last joiner held
python3 -B local/three-players/aplay.py app3b --players 3 --hitch 2

# cause 2 in the released application (fails every time): a server with fix 1, the last joiner held, captures
python3 -B local/three-players/aplay.py app3s --players 3 --second-server --hitch 2 --pcap
python3 -B local/three-players/launchcap.py local/three-players/app3s/app2.pcap
```

## Not tried

Two computers; a real router; a relay on a public address; a person playing; Safari or
Firefox; a page hosting a game of three; a level change or a long session in a game of
three or four with the application or a page (the native runs and the earlier soak work
cover the lockstep game itself); `lobby_fix_checks.py`, `lobby_fuzz.py` and the
sanitizer build of the server with the change, and the setting at 1; the server change
compiled on Linux (where the public server runs), with GCC or MSVC; Champions of Norrath
clients (untouched by the change); holding back the peer library's disconnect datagrams
in our network layers as a second line of defence against the race itself; why the lobby
servers sometimes answer a log-in late on the loaded Mac.
