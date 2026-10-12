# Three and four players do not launch from the online lobby

**State (2026-10-12, 15:50 CDT): a cause has been READ in the game's code and is being
reproduced with three native copies; nothing is proven by a run yet and nothing is fixed.
This file is kept current as the work goes; whoever continues has only this.**

## The defect (as reported, not yet reproduced by this work)

From [browser-build.md](browser-build.md), section "Mixed games": three players on one
Mac reach one room through the local lobby server. At *Start Game* two machines go into
the first level; the third stays behind with the game's message that some players are
un-reachable and the launch has failed. 3 of 3 tries with two application copies and a
page; 2 of 3 with three application copies and no page and no relay. The one success
was three application copies started without the patch sections.

Two players work in every combination.

## Candidates to separate

- (a) the game matches an arriving connection by address without the port
  (`docs/lobby-protocol.md` 9.3, game code at 0x32c2c0), and on one computer every
  player has the same address;
- (b) one of the 26 patch sections;
- (c) a time-out in the launch handshake that a loaded machine misses (load average on
  the test Mac is 220 - 340 as this starts);
- (d) our own network layer (`tools/play-net/src/RtaNet.cpp`, `RtaOnline.cpp`) or the
  lobby server.

## What the code says (read, not yet run) - the working theory

Two things in the game's own code, which together fail only when the other player has
the **same address as this machine** (one computer, one router, one relay):

1. **A race at Start, between the joiners.** A machine that gets START from the host
   (lobby client message 0x1a, flag 0x100 at client+0x64) goes to lobby state 7
   (0x324288, `case 7`): it fills the launch tables from its *live* peer connections
   (0x32e198 takes address and port from the first connection of a peer whose status is
   1; with none it leaves address 0 and whatever port was on the stack), then calls
   `SRSClient_shutdownUdp` 0x328770, which disconnects every peer at once when it has
   nothing unacknowledged. A joiner polls its socket every tenth frame. So the joiner
   whose poll comes first tears its connection to the other joiner down before the other
   joiner has filled its tables: the later joiner has address 0 for the earlier one.
   With two players there is only the host's connection, and the host waits for the
   acknowledgement (finding 2 of [native-online.md](native-online.md) is the same hole
   seen from the two-player side).
2. **The launch handshake heals that - unless the sender has this machine's own
   address.** `net_launchUpdate` 0x135638 finds the sender of a launch datagram by the
   player number inside it, and when the datagram's source is not the address and port
   it has for that player (0x1358e0 - 0x1359f4):
   - source address == this machine's own entry in the address table 0x402b3b (in a
     lobby game: this machine's *external* address, client+0xd10): the player is
     re-addressed to its entry in the second table 0x402b4b and port 4000 ("two consoles
     behind one router"). The developer LAN start fills that second table; **the lobby
     start does not** (state 7 writes 0x402b3b and the ports 0x402b5c only), so the player
     becomes 0.0.0.0:4000 and is never reached again;
   - any other source: the player's address and port are taken from the datagram.
   Between two houses the second branch repairs the missing address. On one computer,
   behind one router, or through one relay, every other player's datagrams come from
   this machine's own external address, the first branch is taken, and the launch fails
   for that machine ("un-reachable").

Also read, and relevant to **four** players with one address: the accept rule at
0x32c2c0 takes an arriving connection for the first sought player whose external address
equals the source address, whatever the port. A newcomer to a room of three has two
players on its seek list at once (the host is known already); with one address for all,
the second one's connection is taken for the first. With three players a newcomer seeks
one player only, so this does not explain three. Not yet run.

Seen in the earlier logs (`local/mixed-online/app*/rta.log`): a member of the room dials
the newcomer (14-byte connect request), the newcomer answers (21 bytes) and does not
dial itself; no log line shows a datagram to 0.0.0.0 - but the emulated machine's own
network stack may refuse that address before a frame exists, so this says nothing.

## Where things are

- scratch files of this work: `local/three-players/` (not in the repository)
  - `nplay.py OUT --players N`: N headless native copies (`local/recomp-out/bin/
    rta_native_online`) through the local lobby into one game; every copy gets
    `net-server=<this Mac's address>` and `net-local-only=1`; the script stops unless the
    copy's own first line says so. Per copy: `OUT/<role>.out` (the game's own debug
    lines appear there as `[game] ...`), `OUT/<role>/net.log`, `OUT/<role>.tick.tsv`.
  - `elfstr.py ADDR...`: the text at an address of the game's executable
- the earlier test scripts and logs: `local/mixed-online/`

## How to reproduce (command under test now)

```
python3 -B local/three-players/nplay.py local/three-players/n3a --players 3 --play 2400 --limit 420
```

## Established so far

Nothing by a run yet.

## In the middle of

The first three-copy native run (`n3a`). Next: read each copy's `[game]` lines around
"Got START from host" / "Terminating known peer", and `net.log` for a datagram to
0.0.0.0:4000.

## Not tried

Everything else: the fix, four players, the emulator application, a page, the relay,
bisecting the sections.
