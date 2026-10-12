# Getting the game to a community server

What stands between the game and a replacement lobby server, read from the executable.
The server side is in [lobby-protocol.md](lobby-protocol.md). This page was written for
PCSX2 and consoles, and **nothing on it has been run in PCSX2 or on a console**; each
step says how it is known.

If you want to play today, this is not the page: the playable build is the Mac
application of [play-online.md](play-online.md), which does the steps below by itself.
[STATE-OF-PLAY.md](STATE-OF-PLAY.md) compares the routes — PCSX2 with the patch file, the
Mac application, the [browser build](issues/browser-build.md) and the
[native build](issues/native-recomp.md) — with what each has been shown to do.

What has been run, all of it in the Play! emulator — not a PlayStation 2 and not PCSX2
(`FINDINGS.md`, "Run on the live game"; `docs/issues/live-rig.md`):

- **The steps of the table below, with the real game.** On the project's rig the game's
  own network stack found a network configuration, resolved the host name, did the
  gateway step and reached the lobby (FINDINGS V32–V34, live-rig section 13), and then
  went the whole way: account, characters, a game hosted and joined, the launch and a
  lockstep game (V49, live-rig section 19). The sign-in step was passed with a local
  sign-in patch that is not part of this repository; as shipped the game stops there with
  a network error (V33). The Mac application does the same path
  ([tools/play-net/README.md](../tools/play-net/README.md)).
- **Player-to-player traffic between two instances on one Mac**, through the loop-back
  address. Hole punching through a router has not been run.
- **The patch set below**, on two linked instances: see "Suggested patch set".
- **A developer LAN start that needs none of the steps**: the boot argument `--net` opens
  a small discovery lobby with no network menu, no sign-in check and no lobby server
  (V6). Most of the rig's pair runs start that way. Whether a console or PCSX2 can pass
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
it "OUT OF SYNC". From reading the code. Some items of this list have been
seen on a running game: two linked emulator instances went out of step in the two ways
of the K1 and K2 item (`docs/issues/live-rig.md` section 7.3), in the way of the options
item (section 14.1), in the way of the inventory item (section 16.1) and, with the float
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

The set is the 26 sections of the table (`tools/play-net/sections-suggested.txt` lists
them by title; the Mac application applies exactly these). Each only makes one machine do
what the others already do, so a mix of patched and unpatched machines is safe, but a fix
only holds for the machines that have it — enable them on every machine. These are the
sections written as fixes rather than diagnostics.

**What the set rests on.** All of it is the two-machine rig: two copies of one Play!
build on one host (`docs/issues/live-rig.md`). Nothing below has run in PCSX2 or on a
console, and the patch file says so section by section.

- Without any section, 7 of 12 real-character arena fights diverged (FINDINGS V17, V21).
- "**Confirmed live**" in the table means: the fault was reproduced on the rig and the
  section removed it there. A row without the mark says what was run and what was not.
- A soak with 24 fix sections on — 120 long pairs, 5,121,702 ticks — ended with no
  difference in any shared value compared and no out-of-sync message; eight pairs
  launched through the real lobby path, 195,331 ticks, the same (FINDINGS V62, live-rig
  section 22). Two bytes of local effect state in the player record did differ between
  the machines, in 68 of the 120 pairs; the soak follows them without counting them as a
  divergence, and no reader in the simulation is known (V63). **Those 24 are not this
  set.** Eighteen of the 19 were among them. "No
  touch handler runs for a prediction copy that walks into something" was not; its runs
  are in `docs/issues/touch-handlers.md` section 6 (FINDINGS V61) and it has not been in
  a soak. The soak also had six sections that are not suggested here.
- The Mac application applies this set ([play-online.md](play-online.md) section 6); its
  online runs with two copies on one Mac are in section 8 there.

| Patch section | Removes |
|---|---|
| use button works with the spell selector open | K1 — **confirmed live**: without it, one machine changes level and the other does not |
| potions always leave the bag directly | K2 — **confirmed live**: without it, potion counts differ silently |
| stats page does not rewrite stored weapon damage | K3 — the differing record and its removal ran live (V42); a hit that reads the differing values was not run |
| menu lockout never drops player damage / never blocks swap and use | D26, U3 — **confirmed live**: dying with the inventory open made one machine drop a hit or skip a weapon swap for the other player; each section removes its half (V39) |
| closing a notice box does not run the pending script | E9 — **confirmed live** (V40) |
| mission menu / jump-gate menu ignore the chooser's pause menu | U2 — the jump-gate case **confirmed live**; the mission-menu case could only be produced by forcing the pause flag (V41) |
| save-point prompt ignores this machine's card screen | B9 — the fault was not reproduced live; the section was on in the soak without harm (V62) |
| net launch clears a stuck memory-card latch | B10, B11 — the fault was not reproduced live; the section was on in the soak without harm (V62) |
| predicted spin cast leaves the shared animation alone | two players of the same class using the spin skill — **confirmed live**: 6 of 6 pairs diverged without it, 0 of 6 with it |
| creatures ignore being touched by the prediction copy | a pet or monster reacting early on its owner's machine — **confirmed live**: the pet pair that diverged stays in step with it |
| no touch handler runs for a prediction copy that walks into something | the same fault in every other kind of object (a small spider dying, a container or prop being shoved, on one machine only) while a player is under scripted control, for instance frozen by a cutscene — **confirmed live**: a spider killed on one machine only stays alive on both with it |
| item records start from zero, not from stack leftovers | dropped items carrying different unused bytes on different machines — **confirmed live**: with it, all twelve arena fights agree completely |
| menu screens do not recompute player statistics; stats page does not recompute the main weapon's damage either | a heal that overshoots being trimmed early on the machine with a menu open, which ends in a death on one machine only — **confirmed live**: the one cause left after a five-million-tick soak, gone with these two |
| carried weight is recomputed only inside the simulation | one machine allowing a pick-up that another refuses, because only the owner's machine had updated the character's carried weight — **confirmed live** |
| peer silence time-out 900 -> 1440 calls | a player whose machine stands completely still (asleep, frozen, a long hitch) being dropped after 15 seconds, which ends the game for both sides; with this the others wait 24 seconds — **confirmed live**: a machine frozen for 21.7 seconds is kept and the pair is in step afterwards; without it the same machine is dropped. Each machine decides alone, so players need not match on it |
| kick request is answered for a peer already dropped | in a three- or four-player game the host kicks one player and every other machine stands still for good — **confirmed live** on three and four machines: the others drop the player 30 frames after the host and play on in step. Every machine should have it |
| a peer being dropped still bounds the input lead | half a second of extra input delay for everyone for half a minute after any time-out or kick in a three- or four-player game — **confirmed live**: lead 15 and 13 frames at the drop instead of 38 |
| flush before a level load waits for the peers' tick | everybody standing still for about two seconds after some level changes — **confirmed live**: 0 of 6 long waits instead of 2-3 of 6, on two and four machines; costs 16 frames at each level change |
| trim leaves one spare frame (LAG-2) | one-frame freezes on a steady two-player link — **confirmed live**: a tenth as many, for one frame more input delay |
| 4-player send cycle 6 -> 4 (LAG-3) | input delay with four players — **confirmed live**: 1.8 to 3.0 frames less; on a slow link the game runs at 97.9 % speed instead of 92.6 % |
| 3-player send cycle 4 -> 3 (LAG-4) | input delay with three players — **confirmed live**: 1.3 to 2.1 frames less |
| prediction copy starts without pending damage | G11–G13, G24 — the fault was not reproduced live; the section was on in the soak without harm (V62) |
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
  (40 of 40 extended test steps pass there; [lobby-protocol.md](lobby-protocol.md) section
  1a). That fork also adds an optional setting for the "player on the same home network as
  the server" case in step 5.
- In the Play! emulator, with the real game: every step of the first table, and the patch
  set, as the head of this page says.

## Not checked

- **Anything in PCSX2 or on a console**: that the emulator's DNS override is honoured,
  that the game gets past the sign-in step there, that two clients find each other, that
  the patch file applies and does what it does in Play!, and that play then stays in sync
  ([VALIDATION.md](VALIDATION.md) describes how to test the last part).
- **Two different machines** — two PCs, a PC and a console, two Macs. Every pair so far
  was two copies of one emulator build on one host, which shows differences in the game's
  logic and nothing else. The one mixed pair that has been looked at does not agree: the
  browser build rounds floating-point results differently from the Mac application
  ([issues/browser-build.md](issues/browser-build.md)).
- **Two networks.** Step 5 (hole punching) and the port and address advice are from
  reading and from runs on one host.
- **More than two players.**

What the rig did check about staying in sync, in the order it happened (sections 7–22 of
`docs/issues/live-rig.md`): placeholder characters with the K1 and K2 patches stay in
sync through hundreds of thousands of ticks of random play in 24 levels. Real characters
that cast skills do not: the Drundar arena diverged in 7 of 12 fights unpatched and 3 of
12 with the K1, K2 and LAG-1 patches. Each cause found after that has a section in the
table above — a summoned pet, the spin skill for two players of one class, stale bytes in
an item record, a heal trimmed by a menu, the carried weight — and with 24 sections on
the last soak found none left in 5.1 million ticks. What that soak cannot see is listed
in section 22.8 there.
