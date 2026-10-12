# The native build online

Started 2026-10-12. The native build of Champions: Return to Arms (SLUS-20973 v2.00; the
game's code translated to C++, `docs/issues/native-recomp.md`, `native-app.md`) played
lockstep games over the hidden LAN start (`native-net.md`) but could not reach the lobby
server. This file is the work that takes it there: the design, what was **Ran** (with
what was seen), and what is left. Nothing derived from the game is in the repository:
translations, programs, logs and cards are under `local/recomp-out/`.

## Status (kept current)

- **Ran**: a native instance, headless, from power-on to the lobby's game list against the
  lobby server on this computer: Internet Game, the network setting from the memory card,
  the gateway, the lobby, the server's terms, an account made by the one-step driver, log
  in, "Game Selection and Chat". 17 s of real time.
- Next: host and join between two native instances; then with the emulator application.

(Sections below are filled in as the work goes on.)

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
2. **The two ERX modules are not on the lobby path.** `LIBINSCK.ERX`, `NG_INSCK.ERX` (and
   `DNAS_NET.ERX`) are loaded by the network window (`FUN_0033ed70`, its states 0xc, 0xd,
   9, 10, 6) for one purpose: the sign-in with Sony's servers, which are gone. The
   project's local sign-in patch makes that window leave at its state 5, before any of
   them is loaded (**Ran**: no ERX load is asked for on the way to the lobby). Translating
   them would serve a step that cannot succeed.
3. **The boundary is narrow and says everything.** 14 library entries and 13
   configuration-client entries. Above them every byte the server and the other players
   get is produced by the game's own translated code; below them a stream is a host TCP
   connection and a datagram a host UDP datagram. The emulator-based application ends the
   game's TCP in its own code and carries the bytes on host sockets too, so toward the
   server and toward other players the two builds do the same (the differences are listed
   under "Behaviour that differs from the emulator build").

## Design

| File | Does |
|---|---|
| `tools/recomp/net/hle-online.txt` | the addresses the driver supplies (`recomp.py --hle-add`) |
| `tools/recomp/net/netdrv.cpp`, `netdrv.h` | the library entries on host sockets; the network setting; the patch-set announcement; the tick log of a test run |
| `tools/recomp/net/online.cpp` | joins the one-step driver of the emulator build (`tools/play-net/src/RtaOnline.cpp`, linked unchanged) to the runtime |
| `tools/recomp/net/build_online.py` | `bin/rta_native_online`: the headless program with the network |
| `tools/recomp/recomp.py` | new options `--hle-add FILE` (one more list of supplied addresses) and `--extra-pnach FILE` (a patch file from outside the repository, applied whole; its words are not counted in the patch-set figure) |

The rules below the entries are the emulator application's, one for one (head of
`netdrv.cpp`): a made-up own-network address per copy (198.19.x.y, kept in
`<data>/online-address`); one host name answered, the lobby's; TCP to the server's address
or to an address the gateway names for it goes to the server; one host UDP socket per UDP
port of the game, with the same number when free, kept for the whole run (the lobby
server sees the pair other players must send to, and the netcode that takes the port over
at launch keeps the path the peer handshake opened); the server's address on a port that
is not the server's is another copy on the server's computer and goes through the
loop-back interface; made-up, broadcast and loop-back destinations are not carried.

The sign-in step: `build_online.py` hands `local/SLUS-20973_4028A55F_signin.pnach` to the
translator when the file is there (`--extra-pnach`). Nothing of it is in the repository,
printed or logged; without it the game stops at its sign-in step.

## How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/net/build_online.py
O=local/recomp-out/online; mkdir -p $O/n1
printf 'until 0x506160:u32 == 5 timeout 12000\nwait 600\napp online\nquit\n' > $O/lobby.rig
RTA_NATIVE=$PWD/local/recomp-out/bin/rta_native_online python3 tools/recomp/native.py boot \
    --card $O/n1/card --opt net-data=$O/n1 --opt net-local-only=1 --opt online=lobby \
    --opt online-name=SomeName --opt online-person=0 --opt net-log=$O/n1/net.log --script $O/lobby.rig
```
