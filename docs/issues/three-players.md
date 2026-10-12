# Three and four players do not launch from the online lobby

**State (2026-10-12, 16:25 CDT): the cause is found and reproduced with three native
copies (one failing run read call by call). A fix is designed - one change in the lobby
server, no change to the game or to any player's copy - and is NOT yet built or tried.
This file is kept current as the work goes; whoever continues has only this.**

## The defect

From [browser-build.md](browser-build.md), section "Mixed games": three players on one
Mac reach one room through the local lobby server. At *Start Game* the launch fails for
one machine with the game's message that some players are un-reachable. 3 of 3 tries with
two application copies and a page; 2 of 3 with three application copies and no page and
no relay. Two players work in every combination.

## The cause (read in the code, then seen in a run)

It is the game's own code, and it needs two things at once.

**1. A race between the joiners at Start.** A machine that takes the host's START
(lobby client message 0x1a, flag 0x100 at client+0x64) goes to lobby state 7 (0x324288,
`case 7`). There it fills the launch tables from its *live* connections to the other
players: 0x32e198 takes address and port from a player's first connection whose status
is 1. Then it calls `SRSClient_shutdownUdp` 0x328770, which - with nothing left to be
acknowledged - disconnects every player at once. A joiner reads its socket every tenth
frame, so the two joiners take START up to 167 ms apart. The one that is first has
closed its connection to the other before the other has filled its tables. For a player
without a live connection 0x32e198 writes nothing, and state 7 then stores what its two
stack variables still hold: the address and port **of the player before it in the
table** (the host's), or 0 and a leftover for the first. The host is not affected: it
fills its tables when it sends START.

**2. The launch handshake repairs a wrong address - unless the sender has this
machine's own address.** `net_launchUpdate` 0x135638 finds the sender of a launch
datagram by the player number inside it. When the datagram's source is not the address
and port it has for that player (0x1358e0 - 0x1359f4):
- source address == this machine's own entry in the address table 0x402b3b - in a lobby
  game that is this machine's *external* address as the lobby server told it (0x3E for a
  host, 0x40 for a joiner; stored at client+0xd10): the player is re-addressed to its
  entry in the second table 0x402b4b and port 4000 ("two consoles behind one router").
  The developer LAN start fills that second table (0x1e21e0); **the lobby start never
  does**, so the player becomes 0.0.0.0:4000 and is not reached again;
- any other source: the player's address and port are taken from the datagram, and at
  the end of the launch written back to the tables the game's peer table is made from
  (0x136ff0 onward).

Between two houses the second branch repairs what the race broke, which is why the
original game worked. **On one computer, behind one router, or through one relay, every
other player's datagrams come from this machine's own external address**, the first
branch is taken, and the launch never completes between the two joiners: the later
joiner answers the earlier one at 0.0.0.0:4000. The same code also sends each contact
attempt a second time to the second table's pair whenever a player's external address
equals this machine's (0x1362d0 - 0x136368): in a lobby game that is 0.0.0.0:0, sent
by every copy on one computer, harmless.

So of the candidates: **(a) in a different place than suspected** - not the accept rule
of the peer library but the launch handshake's test against this machine's own address;
**not (b)**: the tables and the test are untouched by any section, and the failing run
below had the 26 suggested sections while the first run with the same build worked;
**(c) is the trigger** - not a time-out but which joiner reads its socket first, so load
changes the odds and not the mechanism; **not (d)**: our network layers carry the
datagrams as they should, and the lobby server does what the original must have done.

It concerns real games: two friends behind one router (when the router loops their
traffic back), and all browser players, who share the relay's address.

### The run that shows it

`local/three-players/n3a` (second run; three headless native copies, the 26 sections,
set 3f5b1e14, local lobby server, load average 306). Nobody reached the first level.
Host port 4000, joiner 1 port 4004, joiner 2 port 53777, all at 192.168.1.123.

- Host's log (ms): START to both joiners at 79883; joiner 1's acknowledgement and its
  disconnect (peer-library type 5) at 79971; joiner 2's acknowledgement at 80026.
  Joiner 1 took START 88 ms after it was sent, joiner 2 143 ms after.
- Joiner 2's log, one read of its socket at 77298: START from the host, then the
  disconnect from joiner 1 (8 bytes, `00 05`). Its own debug lines: "Got START from
  host", "Terminating known peer 0" - and no line for joiner 1, whose connection was
  gone already (the run that worked has that line on both joiners).
- Joiner 2's port table 0x402b5c right after: 4000, **4000**, 4004 (host, joiner 1, own)
  - joiner 1's entry is a copy of the host's. Host and joiner 1 have 4000, 4004, 53777.
- Joiner 2 at 78044: a 512-byte launch datagram arrives from 192.168.1.123:4004 with
  player number 1; its answer goes to **0.0.0.0:4000**, and so does every later one (422
  datagrams not carried). Its launch record for player 1: address 00000000, port 4000,
  state 2. Joiner 1's record for player 2 stays in state 0 (never heard). Host: both
  records in state 8 (done).

### Also read: the accept rule, which matters for four

`SRSClient_onPeerConnected` 0x32c2c0 takes an arriving connection for the first sought
player whose external address equals the source address, whatever the port. A newcomer
to a room of three has two players on its seek list at once; with one address for all,
whichever of the two connects first is filed under the first one's number. The launch
handshake identifies players by the number in the datagram and repairs addresses (branch
two above), so with the fix below this should heal as well. **Not yet run with four.**

## The fix (designed, not built yet)

**The lobby server stops telling a Return to Arms client its own observed address.**
In notifications 0x3E and 0x40 it sends `0.0.0.0` (the port unchanged) instead of the
address it saw the client at. The game uses that address for one thing only: the
"is this datagram from my own address" test above (client+0xd10 is read by state 7 and
written into peer records that the receivers do not take addresses from: 0x32ca18 case
0x1b copies the name and two bytes; 0x32a1b8 skips players it knows). With 0.0.0.0 the
test is never true, a wrong address is always repaired from the datagram, and the race
stops mattering.

Why there: one redeploy of the server covers every copy players already have (the
application with set 3f5b1e14, the browser page, the native build, a console); no game
patch, so the patch-set figure does not change; no new application build.

Where: `server/upstream/Source/Network/Event/NotifyGameDiscovered.cpp` (0x3E) and
`NotifyClientDiscovered_RTA.cpp` (0x40); a switch in `config.ini` to get the old
behaviour back for comparison.

How it will be tried without touching the running lobby: a second server instance built
from a copy of the source under `local/three-players/server/`, own database, bound to
this Mac's address on other ports; test copies are pointed at it.

Quick check of the idea before that: writing 0 into client+0xd10 on each copy once it is
in the room (a test script's `poke`), which is what the server change would cause.

## Where things are

- scratch files of this work: `local/three-players/` (not in the repository)
  - `nplay.py OUT --players N [--log-all]`: N headless native copies (`local/recomp-out/
    bin/rta_native_online`) through the local lobby into one game; every copy gets
    `net-server=<this Mac's address>` and `net-local-only=1`, and the script stops unless
    the copy's own first line says so. Per copy: `OUT/<role>.out` (the game's own debug
    lines appear there as `[game] ...`; the launch tables are printed at lobby state 12),
    `OUT/<role>/net.log` (with `--log-all` every library call), `OUT/<role>.tick.tsv`.
  - `elfstr.py ADDR...`: the text at an address of the game's executable
- the earlier test scripts and logs: `local/mixed-online/`

## How to reproduce

```
python3 -B local/three-players/nplay.py local/three-players/n3a --players 3 --play 600 --limit 300 --log-all
```

One run of two failed so far (first run: all three in the level, 2,625 lockstep ticks
compared pairwise, no shared column differs; load 280). A failing run ends with
`LAUNCHED: host=NO j1=NO j2=NO` after the scripts' time-out; look for
`UDP to 0.0.0.0:4000 not carried` in a joiner's `net.log`.

## Numbers so far

| What | Copies | Load | Result |
|---|---|---|---|
| 3 players, no fix | native ×3 | 280 | launched; 2,625 ticks, in step |
| 3 players, no fix | native ×3 | 306 | launch failed (the run above) |

## Not tried yet

The fix itself; four players; the emulator application (released build in
`local/play-stable-build`); a page through the relay; more runs for a failure rate;
holding back the peer library's disconnect datagrams in our network layers as a second
line of defence (it would also cover a START that is lost and sent again, where the
disconnect arrives first and the game renumbers its players, 0x32d098 - a hole of the
original game on a lossy line, not seen here).
