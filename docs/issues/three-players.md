# Three and four players do not launch from the online lobby

**State (2026-10-12, 16:10 CDT): the cause is found and reproduced with three native
copies (one failing run read call by call). The fix is one change in the lobby server -
no change to the game, to the patch set or to any player's copy. It is BUILT in a copy
of the server source under `local/three-players/server/` and a second server instance
with it is running; the series that proves it is under way. The change is NOT yet in
`server/upstream`. Not yet tried: four players, the emulator application, a page.
Whoever continues: read "Where the work stands" at the end first.**

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
  host, 0x40 for a joiner; handlers 0x330128 and 0x32a0d0 store it at client+0xd10): the
  player is re-addressed to its entry in the second table 0x402b4b and port 4000 ("two
  consoles behind one router"). The developer LAN start fills that second table
  (0x1e21e0); **the lobby start never does**, so the player becomes 0.0.0.0:4000 and is
  not reached again;
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
below had the 26 suggested sections while other runs of the same build worked (no
bisection was run: the mechanism does not involve a section); **(c) is the trigger** -
not a time-out but which joiner reads its socket first, so load changes the odds and
not the mechanism; **not (d)**: our network layers carry the datagrams as they should,
and the lobby server did what the original must have done.

It concerns real games: two friends behind one router (when the router loops their
traffic back), and all browser players, who share the relay's address.

### The run that shows it

`local/three-players/n3a/run-fail` (three headless native copies, the 26 sections, set
3f5b1e14, local lobby server, load average 306). Nobody reached the first level. Host
port 4000, joiner 1 port 4004, joiner 2 port 53777, all at 192.168.1.123.

- Host's log (ms): START to both joiners at 79883; joiner 1's acknowledgement and its
  disconnect (peer-library type 5) at 79971; joiner 2's acknowledgement at 80026.
  Joiner 1 took START 88 ms after it was sent, joiner 2 143 ms after.
- Joiner 2's log, one read of its socket at 77298: START from the host, then the
  disconnect from joiner 1 (8 bytes, `00 05`). Its own debug lines: "Got START from
  host", "Terminating known peer 0" - and no line for joiner 1, whose connection was
  gone already (a run that worked has that line on both joiners).
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
whichever of the two connects first is filed under the first one's number, so the
newcomer's launch tables have the two swapped. Before the fix that alone breaks a game
of four on one address (the launch datagram of "player 1" comes from player 2's port:
branch one). The launch handshake identifies players by the number in the datagram, so
with the fix it should repair this as well. **Not yet run with four.**

## The fix

**The lobby server stops telling a Return to Arms client its own observed address.**
In notifications 0x3E and 0x40 it sends `0.0.0.0` (the port unchanged) instead of the
address it saw the client at. The game uses that address for one thing only: the
"is this datagram from my own address" test above. (client+0xd10 is read by state 7; it
is also written into the peer record a machine sends about itself, from which the
receivers take no address: 0x32ca18 case 0x1b copies the name and two bytes, 0x32a1b8
skips a player it already knows, and the host is known to everyone it sends to.) With
0.0.0.0 the test is never true, a wrong address is always repaired from the datagram,
and the race stops mattering.

Why there: one redeploy of the server covers every copy players already have (the
application with set 3f5b1e14, the browser page, the native build, a console); no game
patch, so the patch-set figure does not change; no new application build, no new page.

The change (in `local/three-players/server/`, a copy of `server/upstream` of 16:00;
`diff -ru server/upstream/Source local/three-players/server/Source` and the same for
`Include/configuration.hpp` show all of it - 4 files):

- `Include/configuration.hpp`, `Source/configuration.cpp`: a setting
  `rta_tell_console_its_observed_address` (default 0; 1 gives the old behaviour, for
  comparison) and `Config::OwnAddressForRta(observed)`, which returns `"0.0.0.0"` unless
  the setting is on; the reason is written above the function.
- `Source/Network/Event/NotifyGameDiscovered.cpp` (0x3E): for a Return to Arms client the
  address is `Config::OwnAddressForRta(user->m_discoveryAddr)`. Champions of Norrath
  clients are told what they were told before (that game was not read).
- `Source/Network/Event/NotifyClientDiscovered_RTA.cpp` (0x40): the same.

**To be done by the owner once proven:** the four files into `server/upstream` (another
job changed `configuration.cpp/.hpp` there at 14:23 today: merge, do not overwrite), a
line in `server/upstream/FIXES.md` and in `bin/config.ini`'s comments, rebuild, restart
the local lobby, redeploy the public one. Nothing else has to be released.

### Tried so far (kept current; the raw lines are in `local/three-players/*.results`)

All on one Mac, every copy at 192.168.1.123, the 26 suggested sections (set 3f5b1e14).
"Stale" = a joiner's port table 0x402b5c had another joiner's entry wrong when the
launch began: the race of cause 1 went the bad way. "In step" = `tools/rig/compare.py
ticks` over every pair of tick logs: seed, level, player count, button maps, every
player's position, state, hit points, gold and experience, the out-of-sync flags and the
machine's own sync hash of the previous tick, tick by tick. "Own address zeroed" = a test
script writes 0 into client+0xd10 on every copy once it is in the room, which is what
the server change causes. "Fixed server" = the second server instance with the change;
there client+0xd10 read 00000000 on every copy by itself.

| What | Copies | Runs | Launched | Of them stale | Ticks compared, each pair | Load |
|---|---|---|---|---|---|---|
| 3 players, no fix, local lobby | native ×3 | 4 | **2** | the 2 that failed were stale; the 2 that launched were not | 2,625 and 2,718, in step | 44 - 306 |
| 3 players, own address zeroed, local lobby | native ×3 | 3 | **3** | 3 | 2,715 - 2,719, in step (see the note) | 50 - 164 |
| 3 players, fixed server | native ×3 | 3 | **3** | 3 | 2,718 - 2,719, in step (see the note) | 35 - 109 |
| 4 players, fixed server | native ×4 | 1 | **1** | yes: 3 wrong entries on 2 joiners | 2,718 on all 6 pairs, in step | 40 |

Both failed runs without the fix show a datagram answered to 0.0.0.0:4000 in the stale
joiner's log. With the fix no run that was stale failed (7 of 7).

Note: in three of the runs above the two joiners got their player numbers in the order
they joined, not the order the test started them, and the test's hash column then read
another player's ring on those two copies. In those runs that one column differs and
every other column is equal on every tick; the column was corrected for the runs after
16:12 (it now follows the byte at 0x402a39).

Not counted: one run of each local-lobby series at 16:04 in which the local lobby server
did not answer for 20 s. The second instance stood still in the same 40 seconds, so it
was the Mac, not either server.

## Where things are

- scratch files of this work: `local/three-players/` (not in the repository)
  - `nplay.py OUT --players N [--log-all] [--own-zero] [--second-server]`: N headless
    native copies (`local/recomp-out/bin/rta_native_online`) through a lobby on this Mac
    into one game; the host presses Start when every joiner has a character; drawn input
    for `--play` frames; pairwise tick comparison at the end. Every copy gets
    `net-server=<this Mac's address>` and `net-local-only=1`, and the script stops unless
    the copy's own first line says so. Per copy: `OUT/<role>.out` (the game's own debug
    lines appear there as `[game] ...`; the launch tables are printed at lobby state 12),
    `OUT/<role>/net.log` (with `--log-all` every library call), `OUT/<role>.tick.tsv`.
  - `series.sh NAME COUNT nplay-options...`: COUNT runs, one line each in
    `NAME.results`, each run's logs kept in `NAME/run<k>/`.
  - `analyze.py OUT`: the result line (who launched, stale tables, datagrams to
    0.0.0.0:4000, ticks compared).
  - `server/`: the copy of the server source with the fix, built (`sh build.sh`);
    `server/bin/config.ini`: bound to 192.168.1.123 only, every port the usual one plus
    1000 (gateway 41800-41817, lobby 41900/41910, discovery UDP 11101), own database.
  - `redirect.c`, `redirect.dylib`: loaded into a TEST copy with `DYLD_INSERT_LIBRARIES`
    (`RTA3P_ADDR=192.168.1.123 RTA3P_DISCOVERY=11101`), it turns the game's built-in
    gateway port 4081x into 4181x and sends the discovery datagram to the second
    instance. `nplay.py --second-server` sets it. (It must be set on the copy itself: a
    system program such as `nice` or `sh` in between drops `DYLD_` variables.)
  - `elfstr.py ADDR...`: the text at an address of the game's executable
- the earlier test scripts and logs: `local/mixed-online/`

## How to reproduce

```
# the failure (about one run in two or three):
python3 -B local/three-players/nplay.py local/three-players/n3a --players 3 --play 600 --limit 300 --log-all
# a failing run ends "LAUNCHED: host=NO j1=NO j2=NO"; a joiner's net.log has "UDP to 0.0.0.0:4000 not carried"

# the second server instance (the fix), if it is not running:
cd local/three-players/server/bin && (nohup ./champions-server > server.out 2>&1 & echo $! > server.pid)
# its first answers came 80 s late on the loaded Mac (it accepted nothing until then); wait for that

# a series against it:
cd local/three-players && ./series.sh srv3 6 --players 3 --play 2400 --limit 420 --second-server --log-all
```

## Where the work stands (for whoever continues)

Running now, all started by this work, to be stopped by pid when done:
- the second server instance: pid in `local/three-players/server/bin/server.pid`;
- three series (`base3`: no fix, local lobby; `zero3`: own address zeroed, local lobby;
  `srv3`: the fixed server instance), 6 runs each: pids of the shell loops in
  `local/three-players/<name>.series.pid` (removed when a series ends), pids of the
  copies of the current run in `local/three-players/<name>/pids`.

Next, in this order:
1. read the three `.results` files; `srv3` is the proof for three players (wanted: 6 of
   6 launched, a few thousand ticks each, some of them "stale");
2. four players against the fixed instance: `series.sh srv4 4 --players 4 --play 2400
   --limit 480 --second-server`; and four without the fix for the base rate;
3. the emulator application, three copies: the released build in
   `local/play-stable-build` as it is. Every copy needs `--rta-test "TEXT"`, a data
   directory of its own under `local/three-players/`, and `--rta-server 192.168.1.123`;
   never start the bundle without arguments. Start the `Play` binary directly with the
   arguments `tools/play-net/play.sh` would build (so that `DYLD_INSERT_LIBRARIES`
   reaches it), read its log for the server line first, drive it over `--rta-control`
   (see `local/mixed-online/mx.py`, class `App`, and `sync.py` for the sync hashes).
   On a failure read the tables with `peek`: 0x402b5c (4 ports), 0x402b3b (4 addresses),
   launch records 0x402ba4 / 0x402bc8 / 0x402bec + 0x144 × player;
4. two applications and a page, one application and two pages, through a relay of the
   test's own (`local/mixed-online/up.sh` shows how; the relay must be pointed at the
   second instance - not looked at yet how);
5. put the change into `server/upstream` (see "The fix") - the owner's step.

## Not tried

Everything in the list above from 2 on; a failure rate from more than a handful of runs;
two computers; a router; holding back the peer library's disconnect datagrams in our
network layers as a second line of defence (it would also cover a START that is lost and
sent again, where the disconnect arrives first and the game renumbers its players,
0x32d098 - a hole of the original game on a lossy line, not seen here); Champions of
Norrath clients (untouched by the change).
