# Getting the game to a community server

What stands between the game and a replacement lobby server, read from the executable.
**Nothing here has been run on a console or an emulator yet**; each step says how it is
known. The server side is in [lobby-protocol.md](lobby-protocol.md).

## What the game does when you choose online play

The network menu is a state machine (the function at 0x33ed70, state word at object
+0xdb4, driven from the front-end flow at 0x324288). **Observed** in the code:

| Step | States | What happens |
|---|---|---|
| 1. Network set-up | 0–4 | Loads Sony's network configuration modules, lets the player pick a saved network configuration, and waits for the link (up to 2,100 frames) |
| 2. Sign-in check | 5, 0xc, 0xd, 9, 10, 6, 7 | Loads the DNAS authentication modules from the disc, runs the check against Sony's servers and polls its status. Success sets a flag (0x507270) so the check is not repeated in the same session |
| 3. Done | 0xb | Returns "network ready" to the front end |
| 4. Lobby | — | The lobby client connects by TCP to host `con.soegames.net`, port 40810 (host string at 0x554a08, port constant at 0x3249b0) |

## What that means for a community server

1. **A network configuration must exist.** On a console it is the usual memory-card network
   setting. In PCSX2 the emulated adapter supplies addresses itself.
2. **The sign-in check cannot succeed any more**: Sony shut the DNAS servers down in 2016.
   It has to be answered by a replacement DNAS service (the PS2 online community runs DNS
   servers for this) or skipped. The game's own code has a developer shortcut in state 5
   that returns "network ready" without running the check when a debug flag is set and a
   button is held (0x33f904–0x33f920). The eight-byte ID the check would produce
   (0x507268) is not read anywhere else by direct address, so the lobby login does not
   appear to depend on it — **Inferred**.
3. **The host name must lead to the server.** `con.soegames.net` has to resolve to the
   machine running the server. On a console: point the console's DNS at a resolver you
   control. In PCSX2: Settings → Network & HDD → enable Ethernet, use the internal DNS and
   add a host entry for `con.soegames.net` with the server's address (setting keys
   `DEV9/Eth`: `EthEnable`, `ModeDNS1 = Internal`, and `DEV9/Eth/Hosts/Host0`: `Url`,
   `Address`, `Enabled` — the key names were read from PCSX2 2.8.2; the behaviour is
   untested here).
4. **The server must expose** TCP 40810 and 40910 and UDP 10101 at one address every
   player can reach ([lobby-protocol.md](lobby-protocol.md), section 11).
5. **Players must be able to reach each other.** Game traffic is console to console over
   UDP, set up by hole punching that the lobby coordinates. It works through ordinary home
   routers; it fails behind routers that pick a new public port per destination; and a
   player on the same home network as the server is reported with a private address that
   outside players cannot reach ([lobby-protocol.md](lobby-protocol.md), section 9). For a
   group of friends the simplest arrangement is a server on a public host, or everyone on
   one LAN or VPN.

## Checked so far

- The Champions Reborn server builds and runs on macOS, and a simulated pair of Return to
  Arms clients gets from account creation to a started game against it
  (`python3 tools/lobby_e2e_test.py`, 16 steps). That exercises the server, not the game.
- Server defects that affect real sessions are listed in
  [lobby-protocol.md](lobby-protocol.md), section 10, and are fixed in the fork
  [TrustlessMike/Champions-Reborn-Server](https://github.com/TrustlessMike/Champions-Reborn-Server)
  (33 of 33 extended test steps pass there). That fork also adds an optional setting for the
  "player on the same home network as the server" case in step 5.

## Not checked

Everything on the game's side: that the emulator's DNS override is honoured, that the game
gets past the sign-in step, that two real clients find each other, and that play then
stays in sync ([VALIDATION.md](VALIDATION.md) describes how to test the last part).
