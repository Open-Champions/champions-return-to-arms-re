# Our own way into an online game: rendezvous, friends, direct launch

Started 2026-10-13. The owner looked at the "SOEGAMES.NET Login" screen and asked: "do we
actually need this connector or can we make our own internal engine" - and then: "Build a
new sick as portal thats easy and plug and play with friends list, etc their character
name". This file is the work behind such a portal for the NATIVE build: a small service of
our own (identity without accounts, friends, presence, invitations, rooms by code, UDP
hole punching and relay) and a direct start of the game's own lockstep session with no
lobby screen. The old lobby path stays for compatibility and is not touched. Every result
says whether it was **Ran** or only **Read**.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-13, first step: the client interface and its mock are on disk.**

- `tools/recomp/net2/session.h` - the whole client interface in plain C (me, friends,
  requests, presence with character, invitations, rooms, start). `session.cpp` (checks,
  snapshots), `session_mock.cpp` (a mock that plays friends, requests, an invitation and a
  room that fills and starts; no socket), `net2cli.cpp` (the interface from a terminal).
  **Ran**: `local/recomp-net2/bin/net2cli-mock --mock --speed 4` through every call.
- Not yet: the service (`tools/rendezvous/`), the client's real body (`session_net.cpp`),
  the direct launch (`launch.cpp`, hooks as `net2.patch`), the proof.
- Decided, to be built: the direct launch enters the game's own launch handshake
  (`net_launchTransfer` 0x134c60 / `net_launchUpdate` 0x135638 - the one a lobby game uses
  after Start, which carries each player's character) from the title screen at run time,
  with the launch tables filled from the room instead of from a lobby connection; the
  developer's own menu path to it (`frontend_run` states 6 and 7, `frontend_startNetGame`
  0x1e21e0 with lobby state 0) shows the order of calls. Not the boot argument `--net`
  (placeholder characters, level `strife`, only at boot).
- Nothing of this work is running.

## What a lockstep game needs at its start, and what the lobby adds

(being established - filled in as each fact is read and run)
