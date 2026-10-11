# Getting the game to a community server

What stands between the game and a replacement lobby server, read from the executable.
**Nothing on this page has been run on a console or an emulator yet**; each step says how
it is known. The server side is in [lobby-protocol.md](lobby-protocol.md).

What has changed since that sentence was first written: the game itself now runs in this
project, in the Play! emulator — not on a PlayStation 2 and not in PCSX2 — and what was run
there is listed in `FINDINGS.md`, "Run on the live game" (rows V1–V23) and
`docs/issues/live-rig.md`. Two results bear on this page. The executable has a developer
LAN start that needs no network menu, no sign-in check and no lobby (boot argument `--net`,
row V6). And two instances of the emulator have been joined that way into one lockstep
game (rows V9–V23, `live-rig.md` sections 7–10): with placeholder characters they stay in
sync under ordinary play once the two per-machine branches K1 and K2, which were
reproduced, are patched; with real characters that cast skills they do not always — the
Drundar arena went out of sync in 3 of 12 fights even with those patches, from a summoned
pet, from stale bytes in a picked-up item and, for two players of one class, from the
spin skill (rows V17–V20). The pet and the spin have patches too, and with the whole set
on no fight of twelve reached the out-of-sync message; two still differed, silently, in
two bytes of an item that nothing was seen to read (rows V21–V23).
That path bypasses every step below, so none of them — network set-up, sign-in, the host
name, the lobby, hole punching — has been exercised, and the two instances exchange their
packets through the test rig, not through a network; whether a console or PCSX2 can pass
that argument was not tried.

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

## Settings every player must match

Play is deterministic lockstep: each machine runs the whole simulation itself and they only
exchange controller input. Anything that makes one machine compute a different number puts
it "OUT OF SYNC". From reading the code. Of this list two items have been
seen on a running game: two linked emulator instances went out of step in the two ways
of the K1 and K2 item (`docs/issues/live-rig.md` section 7.3), and, with the float
rounding mode of one of them changed by the test rig, in the way of the arithmetic item
(section 8.3 there). Those instances are two copies of one build on one host, so apart
from that forced rounding mode they cannot show any of the version, arithmetic or
hardware differences the other items are about:

- **Same disc version.** Everything in this project is for SLUS-20973, version 2.00.
- **Same emulator version, and the same arithmetic settings**: EE/FPU rounding, EE/FPU
  division rounding and EE/FPU clamping, VU0 and VU1 rounding and clamping, the FPU and VU
  game fixes, and both recompilers on. Leave them at the defaults. Even controller input is
  decoded with float arithmetic, so a different rounding setting diverges within a second
  of stick use (FINDINGS F5, F9; `docs/issues/float-divergence.md`).
  Confirmed on two linked emulator instances: with one machine's float rounding mode changed,
  sync breaks within about two seconds of anyone moving, in every level (FINDINGS V15).
- **Same test patches.** Patches marked "every player must use the same setting" change
  the simulation; a mix is itself a desync. Patches marked "a mix is safe" only make one
  machine do what the others already do.
- **A real console against an emulator** has not been shown to stay in sync and should be
  expected to drift. The same goes for an ARM-native emulator build against an x86 one.
  PCSX2 2.8.2 on an Apple-silicon Mac is the x86-64 build running under Apple's
  translator; that is expected to match an x86 PC but has not been compared.
- **No `debug.sht` on anyone's memory card**, and in a game with memory-card characters,
  take turns at save points and never leave a save that ended in a card error unrepeated
  (FINDINGS B9–B11).
- **Habits that avoid two known per-machine branches** on any machine that does not have
  the patches for them: do not press "use" and then the D-pad spell selector in quick
  succession, and do not open the inventory right after pressing a potion button (FINDINGS
  K1, K2). Both branches are confirmed on the running game, and so is the first one's
  worst case — at a level exit one machine leaves and the other stays. The two patches
  removed them on two linked Play! emulator instances; they have not been run in PCSX2 or
  on a console (see the next section).
- **Do not change anything in the pause menu's options during an online game** if any
  player has remapped buttons in the game's own controls screen; simplest is for everyone to
  keep the game's default controls and remap in the emulator instead (FINDINGS U1).
  Confirmed on two linked emulator instances: changing the music volume on one machine made
  it misread the other player's remapped button and the game stopped with the out-of-sync
  message (FINDINGS V35).
- **Do not die with the inventory open**, and do not open the pause menu while a mission
  or jump-gate menu is up (FINDINGS D26, U2).

## Suggested patch set for a first online test

**Result on the two-machine rig with this whole set on:** none of twelve real-character arena
fights reached the out-of-sync message, against 7 of 12 with no patches, and with the item-record
section included the twelve agree in every shared value (FINDINGS V21, V30). That
was the Play! emulator with two character builds; PCSX2, consoles, lobby characters and the
other classes are untested.

Two of these are now confirmed on the running game: on two emulator instances joined
together (the Play!-based rig, `docs/issues/live-rig.md`), random input reproduced the K1 and
K2 desyncs and the K1 and K2 patches removed them; the LAG-1 patch was measured there too. With K1 and K2 fixed, 60 further pairs over 24 levels found no other desync. That was the Play! emulator, not PCSX2 or
a console. The other patches in `patches/SLUS-20973_4028A55F.pnach` have been executed
function by function but not on a running game. These are the ones written as fixes rather
than diagnostics. Each only makes one machine do what the
others already do, so a mix of patched and unpatched machines is safe, but the fix only
holds for the machines that have it — enable them on every machine:

| Patch section | Removes |
|---|---|
| use button works with the spell selector open | K1 — **confirmed live**: without it, one machine changes level and the other does not |
| potions always leave the bag directly | K2 — **confirmed live**: without it, potion counts differ silently |
| stats page does not rewrite stored weapon damage | K3 |
| menu lockout never drops player damage / never blocks swap and use | D26, U3 |
| closing a notice box does not run the pending script | E9 |
| mission menu / jump-gate menu ignore the chooser's pause menu | U2 |
| save-point prompt ignores this machine's card screen | B9 |
| net launch clears a stuck memory-card latch | B10, B11 |
| predicted spin cast leaves the shared animation alone | two players of the same class using the spin skill — **confirmed live**: 6 of 6 pairs diverged without it, 0 of 6 with it |
| creatures ignore being touched by the prediction copy | a pet or monster reacting early on its owner's machine — **confirmed live**: the pet pair that diverged stays in step with it |
| item records start from zero, not from stack leftovers | dropped items carrying different unused bytes on different machines — **confirmed live**: with it, all twelve arena fights agree completely |
| menu screens do not recompute player statistics; stats page does not recompute the main weapon's damage either | a heal that overshoots being trimmed early on the machine with a menu open, which ends in a death on one machine only — **confirmed live**: the one cause left after a five-million-tick soak, gone with these two |
| carried weight is recomputed only inside the simulation | one machine allowing a pick-up that another refuses, because only the owner's machine had updated the character's carried weight — **confirmed live** |
| prediction copy starts without pending damage | G11–G13, G24 |
| equalise at once (LAG-1) | input delay staying high after a stall, which is also what widens K1 and K2 — **confirmed live**: peak 11 frames instead of 34, cleared in 10 s instead of 35 |

Leave the "Arena diagnostic" and "Diagnostic" sections off unless you are bisecting; several
of them change the simulation and must then be identical on every machine. "Option commit
leaves the button maps alone" (U1) is for test sessions only: with it, a change made in the
game's controls screen does not take effect.

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
stays in sync ([VALIDATION.md](VALIDATION.md) describes how to test the last part). The
live rig (`docs/issues/live-rig.md`) checks none of the first three: its machines start
through the developer LAN path and exchange packets inside the rig. On the fourth it has
a partial answer (sections 7–10 there): two copies of one emulator build, with placeholder
characters and the K1 and K2 patches, stay in sync through hundreds of thousands of ticks
of random play in 24 levels. With real characters that cast skills they do not: the
Drundar arena diverged in 7 of 12 fights unpatched and 3 of 12 with the K1, K2 and LAG-1
patches, the remaining causes being a summoned pet, stale bytes in a picked-up item and
— for two players of the same class — the spin skill, of which the first and the last
have patches in the table above; with those on as well, none of twelve fights reached the
out-of-sync message and two kept a silent two-byte difference in an item record. Whether two *different* machines — two PCs, a PC and
a console — stay in sync is still unchecked.
