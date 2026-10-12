# Three and four players do not launch from the online lobby

**State (2026-10-12, 15:45 CDT): work just started. Nothing established yet beyond what
the earlier account says. This file is kept current as the work goes; whoever continues
has only this.**

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
  the test Mac is 275 - 340 as this starts);
- (d) our own network layer (`tools/play-net/src/RtaNet.cpp`, `RtaOnline.cpp`) or the
  lobby server.

## Where things are

- scratch files of this work: `local/three-players/` (not in the repository)
- the earlier test scripts and logs: `local/mixed-online/`

## Established so far

Nothing yet.

## In the middle of

Reading the game's code for what decides "un-reachable" (the message text, the function
that shows it, the accept rule at 0x32c2c0).

## Not tried

Everything.
