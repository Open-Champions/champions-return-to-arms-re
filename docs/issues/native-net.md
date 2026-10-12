# Network for the native build

Started 2026-10-12. The native build (`docs/issues/native-recomp.md`: the game's code
translated to C++, a headless runtime under it) had no network. This file is the design
of the network shim that was added beside it, what was run with it, and what the lobby
path would still need. Every result says what was **Ran**; nothing here is inferred from
reading alone unless it says **Read**.

## Status

- **The network works for the game's own lockstep netcode**: the developer LAN start
  (boot argument `--net`: discovery by broadcast on port 4000, launch handshake, level
  load, lockstep game) runs natively from power-on, between two native instances and
  between a native instance and an emulator runner of the rig.
- **Native against native**: no shared column of the tick log differs in any run — up to
  **296,778 ticks in one game** (83 minutes of play, run in four), with delay, jitter and
  loss on the wire, through a level change, a cutscene and a fight on seeded random input.
- **Native against the emulator in one game**: no shared column differs in any run — up
  to **21,141 ticks** in the arena fight with delay 4, jitter 4, loss 8 %.
- **The known desyncs reproduce natively at the documented ticks** without fixes (K2, K3,
  E9, D26, U1) and are gone with the suggested fix set built in (K2, K3, E9, D26; U1's
  section is not in the set). The same holds in a mixed pair (D26, K2).
- **Speed**: two native instances in a lockstep game, unthrottled, run 1,387 ticks per
  second of wall time idle (23 × real time) and 930 to 1,300 in the arena fight (15 to
  22 ×) on a quiet machine; the emulator rig manages about 0.85 ×.
- Not done: the lobby path (TCP, DNS, network configuration, the two ERX modules) — see
  "What the lobby path needs".

## Where things are

| What | Where | In the repository? |
|---|---|---|
| the shim | `tools/recomp/net/netshim.cpp` | yes |
| functions it replaces | `tools/recomp/net/hle-net.txt` | yes |
| build (own translation, patches, object cache) | `tools/recomp/net/build_net.py` | yes |
| launcher: images, pairs, cross-play, comparison | `tools/recomp/net/netpair.py` | yes |
| long input scripts | `tools/recomp/net/soakscript.py`, `tools/recomp/net/examples/` | yes |
| translation, objects, programs | `local/recomp-out/gen-net*`, `obj-net*`, `bin/rta_native_net*` | no — derived from the game |
| memory images, rig states, logs of every run | `local/recomp-out/net/` | no |

Nothing of the runtime (`tools/recomp/rt/`), of the translator or of the rig is changed.
The shared list `tools/recomp/hle.txt` is not changed either: the build makes its own list.

## Design

### Where it connects

The translator emits a function on its HLE list as `orig_<address>` and leaves
`fn_<address>` to whoever links it. `build_net.py` translates into a directory of its own
(`local/recomp-out/gen-net`) with the list `tools/recomp/hle.txt` + `hle-net.txt`, and
`netshim.cpp` supplies:

| Address | Function | What the shim does |
|---|---|---|
| 0x365ec0 | `sceLibnetInitialize` | answers 0 |
| 0x365a08 | `sceInetGetInterfaceList` | one interface, id 1 |
| 0x365a90 | `sceInetInterfaceControl` | code 9: this machine's address (`RTA_NET_ADDR`) |
| 0x3654a8 | `sceInetCreate` | a socket for the parameter block's type and local port; returns its id |
| 0x365518 | `sceInetOpen` | 0 |
| 0x365560 | `sceInetClose` | forgets the socket |
| 0x365830 | `sceInetSendTo` | a datagram to an address and port; returns its length |
| 0x365670 | `sceInetRecvFrom` | the next datagram that may be received in this frame, or **−500** |
| 0x137a10 | `net_loadModules` | not run; answers interface 1 |
| 0x13e638 | `net_linkCheck` | 1 |
| 0x19b6e4 | `gfx_vblankHandler` | frame counter, exchange with the other machine, input script; then the original |
| 0x17421c | `pad_readPort` | the original, then the 8-byte record is overwritten from the script |
| 0x3226e4 | `tasks_run` | the original; the call that returns to 0x13aee8 is one lockstep tick: tick log, in-tick commands |
| 0x323dcc | `main` | with `RTA_NET_ARG` the argument block 0x5f8740 is filled (`--net`); then the original |
| 0x3646c8 | `sceSifMInitRpc` | sets the word it waits for (0x8ef2c4); then the original |
| 0x36c1a0 | `lgAudEnumerate` | the original; an answer without the error bit becomes 0x8000000A |

The first ten are the ten the rig replaces (`tools/rig/rig.cpp`, `CNetShim`;
`docs/issues/live-rig.md` 4d) and have the rig's semantics, word for word: sockets are
kept by connection id; a datagram for this machine's own address or for a broadcast
address is queued for this machine's sockets on that port; a datagram for another address,
and a broadcast, leaves the machine; nothing blocks; a connection id the shim never handed
out (a memory image taken inside a net game) is taken to be the game socket on port 4000.

The last three exist because of the runtime, not the network; they go when the runtime
does these things itself (the runtime's owner has the list):

- The runtime started `main()` with no arguments, and the LAN start is chosen by `--net`.
  (Since `runtime.cpp` 1c56b1e3 the runtime has `--arg <text>` for this; the hook and
  `RTA_NET_ARG` stay until its status section announces the option.)
- `sceSifMInitRpc` (libmrpc, called by `net_gameInit` at 0x139dcc) sends SIF command
  0x80000001 and polls `sceSifGetSreg(1)` until the I/O processor's multi-thread RPC
  manager has answered. That manager only carries the network library's calls, all of
  which are replaced, and nothing answers natively: the main thread spins for ever.
- A net game lists USB headsets after its first ticks (0x31f634): `lgAudEnumerate(i)` for
  i = 0, 1, 2 … until an answer has bit 31. The runtime's headset server answered that
  function with no data, so the list never ended — 181,038 calls in 3,000 fields, the
  session loop dead after lockstep tick 20.

### Two transports

**The rig's link** (`RTA_NET_LINK=listen:<path>|connect:<path>`). The shim speaks the
wire format of the rig's `CLink`: a Unix stream socket; at every vertical blank each side
sends one message — its frame number and the datagrams its game sent since the last one,
each with the first frame of the receiver on which it may be received — and waits for the
other's message with the same frame number. Neither machine can get ahead, what a machine
receives depends on frame numbers only, and a run repeats exactly (**Ran**: the long
native + rig fight was run twice, two builds of the runtime apart, and reached the same
event in the same frame). Because the format is the rig's, the other machine can be an
`rta_rig` runner started with `--link`: this is how cross-play is done, with no bridge.

**Host UDP** (`RTA_NET_UDP=<base port>`). One non-blocking host socket per game socket,
bound to 127.0.0.1. The game's address a.b.c.d and port p (4000–4015) is host port
base + d·16 + (p − 4000); the first three octets are taken to be this machine's. A
broadcast goes to every address in `RTA_NET_PEERS`. Datagrams on the wire are the game's
own bytes with no header. Arrivals are collected at the vertical blank, so a datagram
becomes receivable at a frame boundary as on the link. The instances are not held in
step: `RTA_NET_PACE` (default 59.94) paces each to the wall clock.

**The bus model** on both is the rig's (`RTA_NET_BUS=delay=N,jitter=N,loss=N,seed=N,
stallat=F,stall=N`): the same generator, the same seeding, the same order of draws, and a
different stream for machine B. A native machine and a rig machine given the same `--bus`
therefore treat the wire alike.

A "frame" is one call of the game's vertical-blank handler. That is every vertical blank
once the game has installed its handler, which is all a sequence number for the exchange
needs.

### Input, tick log, script

`RTA_NET_SCRIPT` is a file in the rig's script language; the shim implements `wait`, `at`,
`until`, `tapuntil`, `press`, `release`, `tap`, `stick`, `pad`, input-table lines, `poke`,
`dump`, `show`, `echo`, `fuzz`, `quit`, `ontick N <command>` and the `A:` / `B:` tags.
`fuzz` is the rig's generator and table, so one file gives a native machine and a rig
machine the same input. `netshim`, `sync`, `log` are accepted and do nothing; `pnach` is
refused with a note (below).

`RTA_NET_TICKLOG` is the rig's tick log: one row per lockstep tick, written where the rig
writes it (after the tick's task pass, `g_netFrame` still the tick's number), with the
rig's expression grammar, types and checksum, so `tools/rig/compare.py ticks` reads a
native log and a rig log alike. `netpair.py` gives both kinds of machine the rig
launcher's columns.

### Patched builds

Translated code is fixed at build time, so a patch has to be in the executable the
translator reads. `build_net.py --pnach FILE --sections LIST --name NAME` writes the patch
words into a copy of the executable, translates that copy into `gen-net-NAME`, and leaves
`patch-words.txt` there, which the shim writes into memory at start (`RTA_NET_PATCH`) so
that data words are patched too and memory reads as on a patched console.

That alone does not give a usable program. A fix that jumps to a routine written into the
body of an unused function, and from there back into the middle of the patched function,
makes the translator treat the two as entangled, and `merge_entangled` joins every unit
that lies **between** them: for the suggested set "1a5030-2d1a94: 1921 units", one C++
function of 13.6 MB, which the compiler had not finished after an hour. `build_net.py`
therefore hands the translator a function table with a row started at each target of a
patch jump (four for the suggested set: 0x1a9580, 0x257ae4, 0x257b0c, 0x2d1980). Those
targets are then unit starts, the jumps are ordinary tail calls, 17 of 46 files recompile
(31 s) and the fixes behave as on the rig (results below). The lasting answer belongs in
`recomp.py`: merge the members of a cluster, not the span.

Objects are cached by the text of their source, so a variant compiles only what its
patches changed.

### The launcher

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/net/build_net.py                         # bin/rta_native_net
python3 tools/recomp/net/build_net.py --name fix --pnach patches/SLUS-20973_4028A55F.pnach \
        --sections tools/play-net/sections-suggested.txt      # bin/rta_native_net-fix

# two machines from power-on through the developer LAN start; each is `native` or `rig`
python3 tools/recomp/net/netpair.py run local/recomp-out/net/boot1 --boot --a native --b native \
        --script tools/rig/examples/pair-start.rig
python3 tools/recomp/net/netpair.py run local/recomp-out/net/x1 --boot --a native --b rig \
        --script my.rig --bus delay=3,jitter=3,loss=50,seed=1
python3 tools/recomp/net/netpair.py run local/recomp-out/net/u1 --boot --udp 42000 --pace 240 --script my.rig

# or from memory images of a running pair game (one per machine) taken on the rig
python3 tools/recomp/net/netpair.py snapshot local/recomp-out/net/img1 \
        --a-state local/rig-out/run1/a.zip --b-state local/rig-out/run1/b.zip
python3 tools/recomp/net/netpair.py run local/recomp-out/net/nn --img local/recomp-out/net/img1 --script my.rig
```

`run` prints each machine's summary and then the verdict of `compare.py ticks` on the two
tick logs. Machine A is 192.168.1.132 and plays slot 1, machine B is 192.168.1.134 and
plays slot 0, as in the rig's launcher. With `--boot` the memory cards are copies of the
rig pair's (`local/rig-out/pair-a`, `pair-b`).

`snapshot` exists because the first runs were made before the runtime could read the disc.
It runs a rig pair twice — a rig pair repeats exactly — first to find a frame in which both
machines pass the head of the session loop (0x322b48) with a new tick number, then to
write, in that frame, each machine's memory, scratchpad and registers at the loop head and
a rig state of each machine at that frame's vertical blank. Images and states of one
instant are mutually consistent (neither machine has seen anything the other sent in that
frame), so any mix of native and rig machines can continue from them; what was on the wire
is lost, which the netcode's repetition covers. With the runtime's `--adopt` a resumed
instance can load levels too.

## Results (Ran)

Machine: Apple silicon, 18 cores, shared with other jobs — the load average is quoted
with every speed. "Nothing differs" means `compare.py ticks` reported no shared column
differing on any tick; the shared columns are the tick, the shared seed, the level, the
player count, the button maps, the sync record of the previous tick, and for both players
position, facing, action state, object seed, hit points, mana, gold, experience, three
bags, statistics, points, equipment, abilities, skills and the out-of-sync flags.

Runtime linked: (a) the object of the binary that passed the 2,005-frame test of
`native-recomp.md` (sha1 f477f6c8…), while the runtime's sources were between two states;
(b) the live sources with `runtime.cpp` sha1 fb955116… (no disc service yet); (c) the live
sources with `runtime.cpp` 9403e8dd… and (d) 1c56b1e3… (boot, disc, cards).

### From memory images (runtime a, b)

Images of frame 90 of a rig pair started from the states of `pair-start.rig`: lockstep tick
748, level strife.

| Pair | Input | Bus | Ticks compared | Result |
|---|---|---|---|---|
| native + native | none, 600 frames | none | 599 | nothing differs |
| native A + rig B; rig A + native B | none | none | 599 each | nothing differs |
| the three above against the rig pair of the same states | | | 599 | **the tick logs are byte-identical**, per-machine columns included |
| native + native | fuzz move, fight, potion, use | delay 3, jitter 3, loss 5 % | 3,121 | nothing differs |
| native A + rig B | the same | the same | 3,121 | nothing differs |
| native + native | walking in loops + fuzz (`soakscript.py`) | the same | 5,855 | nothing differs; both then ask for a level change in the same tick |
| native + native | fuzz without walking | delay 4, jitter 5, loss 8 % | 29,924 | nothing differs |
| native + native over host UDP | fuzz | delay 3, jitter 3, loss 5 % | 868; 598 | nothing differs (ended at a level change: no disc in runtime b) |

Strife has nothing to fight (hit points, experience and gold never change there), which is
why the later runs go to the arena.

### From power-on (runtime c)

`netpair.py run --boot`, script `tools/rig/examples/pair-start.rig` unchanged, then the
steps of `pair-arena.rig`: level change to drunare written in one tick on both machines,
machine A's player walks into the trigger, the opening cutscene, the fight on fuzz.

| Pair | Scenario | Bus | Ticks compared | Result |
|---|---|---|---|---|
| native + native | lobby, launch, strife | none | 659 | nothing differs |
| that run against a rig pair booted the same day | | | 659 | every shared column equal, both machines (only `l_drawframe` differs: loading is faster natively) |
| native A + rig B | lobby, launch, strife | none | 659 | nothing differs |
| native + native | … arena, cutscene, 4,500 frames of fight | none | 6,973 | nothing differs; 161 and 466 hit-point changes |
| native A + rig B | the same | delay 3, jitter 3, loss 5 % | 6,679 | nothing differs |
| rig A + native B | the same | the same | 6,752 | nothing differs |
| rig A + native B | 20,000 frames of fight | delay 4, jitter 4, loss 8 % | 21,141 | nothing differs |
| native A + rig B | the same | the same | 21,010 | nothing differs — with `--wrap-memory` (runtime d), see finding 1; without it the native machine stops at tick 5,126 |
| native + native over host UDP, 240 Hz | lobby … 4,500 frames of fight | delay 3, jitter 3, loss 5 % | 6,851 | nothing differs |
| native + native | 60,000 frames of fight, fix set | delay 3, jitter 3, loss 5 % | 61,313 | nothing differs |
| native + native | the same, no fixes | the same | 61,385 | nothing differs |

The lobby on the wire is what the rig's log shows for the emulator: one socket on port
4000, a 4-byte announcement (first word 0xbd3d) to 192.168.1.255, launch packets (0xbd3e),
then the game's input packets on the same socket.

### The known desyncs, with and without the suggested fix set (runtime c)

Scripts of `tools/rig/examples/`, appended to `pair-start.rig` (or `pair-chars-start.rig`)
so that the native pair boots into the state the examples start from. "Fix set": the
sections of `tools/play-net/sections-suggested.txt` as the file stood at 09:50 that day —
its first 20 sections, 82 words — built in (`rta_native_net-fix`); a rig machine in a
mixed pair gets the same sections by `pnach` lines at the top of the script.

(At 11:04 the file grew to 26 sections, 90 words. With those a pair entering the arena by
`pair-arena.rig` arrives at other positions, runs its ticks on different frames with no
bus set, and machine A's scripted walk does not move its player, so the cutscene never
starts — **on a rig pair and on a native pair alike**, with the same entry positions. That
is a property of the new sections or of the script, not of the native build; it is why
the later runs name the 20-section list.)

| Finding | Pair | Without fixes | With the fix set |
|---|---|---|---|
| K2 potion and inventory, bus delay 10 | native + native | potion count and bag 2 of player 1 differ **from tick 744** (the rig's documented tick) | nothing differs, 1,044 ticks |
| K2 | rig A + native B | the same columns from tick 755 | nothing differs, 1,038 ticks |
| K3 stats page rewrites weapon damage | native + native | stored damage of slot 0 differs from tick 831, 189 ticks | nothing differs, 1,137 ticks |
| E9 notice box runs the pending script | native + native | pending name and quest variable differ from tick 806 (rig: 805) | nothing differs, 1,017 ticks |
| D26 death with the inventory open | native + native | seed, hit points differ at **tick 2400**, the game flags out-of-sync at **2402** (as documented) | nothing differs, 3,110 ticks |
| D26 | rig A + native B | seed, hit points, equipment, weapon set at 2400, flag at 2402 | nothing differs, 3,035 ticks |
| U1 option commit rewrites button maps | native + native | button maps from tick 1090, out-of-sync at 1270 | the same: its section is not in the suggested set |
| K1 use press with the selector open | native + native | not seen in 6,723 ticks | — |

K1 was found on the rig by random input; a native machine does not reproduce a rig
machine's input timing frame for frame (finding 3), so the run takes another course.

### Speed and soak

Two native instances, joined by the link, unthrottled; per instance one core is busy.

| Scenario | Load average | Ticks per second of wall time | × real time | Ticks per processor-second, per instance |
|---|---|---|---|---|
| idle in strife, 20,000 frames | 13 | 1,387 | 23 | 1,429 |
| the same, `--hle-renderer` | 13 | 1,844 | 31 | 1,910 |
| arena fight on fuzz, 22,000 ticks | 16 | 927 | 15 | 1,062 |
| arena fight, 61,000 ticks, bus on | 33–47 | 437–527 | 7.3–8.8 | 655–677 |
| idle in strife, 20,000 frames | 55 | 408 | 6.8 | 620 |
| rig pair from power-on, for comparison | 50 | 51 frames/s | 0.85 | — |

At load 350–450 a pair that sleeps or free-runs (host UDP) fell to 3 frames per second of
wall time while using 1.3 s of processor in 200 s: on a machine that busy the wall figures
say nothing about the program. The link runs were not affected in that way.

**Soak.** From power-on into the arena, then 300,000 frames of fuzz (move, fight,
potion, use) in the fight; bus delay 3, jitter 4, loss 6 %; runtime d; built with
`--wrap-memory` (finding 1); tick log with the columns the game itself hashes plus level,
hit points, action state, experience and the out-of-sync flags (`--columns small`).

| Build | Ticks compared | Wall time, load | Ticks per second | Result |
|---|---|---|---|---|
| no fixes | 296,778 | 242.6 s, load 9 | 1,223 (20 × real time) | nothing differs; 17,168 and 15,556 hit-point changes, 6,270 changes of action state |
| fix set | 296,691 | 227.9 s, load 7 | 1,302 (22 ×) | nothing differs |

Each is 83 minutes of play. Without fixes the game read memory where nothing is three
times, with fixes once (finding 1) — on both machines in the same tick each time.

## Findings

1. **The game reads memory where nothing is, in play, and the emulator lets it.**
   `Player_run` 0x1ab7c0 reads a float from player + 0x124 + t × 0x20 with
   t = −1,000,000,000, the "no such track" answer of `anim_findTrackByFlag(…, 0x8000)`
   (call at 0x1ab6ec) used untested — the out-of-bounds read `docs/spec/player-tick.md`
   describes, where it says it was not established whether it happens. It happens: tick
   5,126, frame 6,410 of the long native A + rig B fight, address 0x8d13559c. The
   runtime's `rt_load` stops the native machine there; the emulator machine plays on,
   because Play! answers such a read with 0xCC in every byte and drops such a store
   (**Read** in its `MemoryMap.cpp`). `build_net.py --wrap-memory` compiles `runtime.cpp`
   with its four load/store functions renamed — the source is untouched — and puts the
   emulator's answer in front. With it the same run (the event recurred in the same frame)
   passes the read and the pair stays in step for the remaining 15,900 ticks. In the
   300,000-frame soaks the read came up three times and once, each time on both machines
   in the same tick (46,526 for two objects, 255,941; 69,371): it is part of the
   simulation, and whatever a platform answers there is shared state. The option goes when
   the runtime answers such accesses itself. A console would more likely take
   an exception there; that is a question for `docs/issues/float-divergence.md`'s kind of
   comparison, not for this one.
2. **A patched executable needs the function table split** at the targets of the patches'
   jumps before it is translated ("Patched builds" above).
3. **Input timing differs between a rig machine and a native one, and that is all that
   differs.** On the rig a controller state set by the script at a vertical blank reaches
   the game one frame later than a direct overwrite of `pad_readPort`'s record does, and
   now and then in the same frame: the emulator runs the game's own pad driver on the
   emulated I/O processor, and its answer races the game's read. Measured with single
   presses of every button and both sticks: with one frame of latency in the shim
   (`RTA_NET_PADLAT`, default 1) all events land on the rig's ticks except the occasional
   early one (one press in 193 fuzzed ticks; a stretch of three events in 200 frames of
   another run). The emulator's driver also reports full pressure (0xff) for a held L1 or
   R1; the shim does the same. Which bits `pad_readPort` gives each button was checked
   against the rig for all sixteen buttons — it is the table in `docs/netcode.md`, input
   record +4. Consequence: with no input a native pair and a rig pair give byte-identical
   tick logs; with input they are the same game played with presses that can be one tick
   apart, so a divergence found by random input on the rig (K1) is not replayed natively
   by the same seed, while one produced by a scripted sequence is (K2, K3, E9, D26, U1).
4. **No divergence between the native build and the emulator was found.** The tick logs
   compared above include the shared random seed in every tick and the positions of both
   players as raw float bits; nothing in them differs between a native machine and an
   emulator machine playing the same game, in 21,141 + 21,010 + 6,752 + 6,679 ticks of
   fighting and the shorter runs. Separately, a native pair and a rig pair booted from
   power-on by the same script give the same 659 ticks in every shared column, and a
   patched native pair and a patched rig pair arrive in the arena at the same positions.
5. For the runtime's owner, besides finding 1 and the three hooks listed under "Where it
   connects": `sceSifSearchModuleByName("INET_SPEED_UART_driver")` at 0x139e58 (module
   loader function 9) is left unanswered once per boot; the caller tests the sign of the
   result.

## What the lobby path needs

The online path (sign-in is out of scope and stays a local patch outside the repository)
goes through the same library. Beyond the entries the shim has:

| Entry | Used by | What it needs natively |
|---|---|---|
| `sceInetName2Address` 0x365288 | `apitcp_connect` 0x38bf2c, `UdpDriverPS2_GetHostByName` 0x395d48 (5,000 ms) | a host name look-up that does not hold the runtime's lock: on a helper thread, the calling game thread parked with `rt_sleep` until the answer or the time-out |
| `sceInetCreate` with a TCP parameter block, `sceInetOpen` | `apitcp_connect` | a non-blocking host `connect`; `sceInetOpen`'s `ms` is the time-out |
| `sceInetPoll` 0x3651e0 | the API's connect check | readiness of host sockets, with the time-out |
| `sceInetSend` 0x365780, `sceInetRecv` 0x3655a8 | the SOEGamesAPI TCP sender and reader | stream sockets; the −500 "nothing waiting" convention has to be checked for the TCP reader as well |
| `sceInetAddress2String` 0x365348 | logging | text |
| a second socket per UDP socket | `UdpDriverPS2_SocketOpen` 0x3958c0 opens an ICMP one and `SocketReceive` reads it when the data socket answers −500 | answer −500 on it, or map host errors (`ECONNREFUSED`) to what the driver expects |
| the UdpLibrary data socket, ports 4000–4004 | SRSClient peer handshake, then handed to the game netcode | the datagram sockets the shim already has, without the loopback port mapping: the game's addresses are then real ones |
| network configuration: `netcfg_thread` 0x34e068 loads eznetcnf.irx / eznetctl.irx and calls `ezNetCnf…` / `ezNetCtl…` over RPC | the network set-up screens and the interface bring-up | answers from the runtime's I/O-processor services (one configuration "from the host", status "up"), or `netcfg_pollStatus` / `netcfg_startInterface` replaced at the game's side as `net_loadModules` is |
| `LIBINSCK.ERX`, `NG_INSCK.ERX` | the network set-up window only | translation ahead of time for a fixed load address (the translator's job), or that window skipped |

`net_loadModules` and `net_linkCheck` are already answered the way the lobby path wants
(interface 1, link up). libmrpc carries nothing once every library entry is replaced.

How it would sit in the code: `rt/iface.h` already declares `rta::NetDriver` with exactly
these entries (`initialize`, `interface_list`, `interface_control`, `create`, `open`,
`close`, `send`, `recv`, `send_to`, `recv_from`, `poll`, `name_to_address`,
`address_to_string`), "not wired yet". When the runtime owns the library's `fn_` and calls
a driver, the socket half of `netshim.cpp` becomes one implementation of that interface
(host sockets) and the link becomes another (test); the vertical-blank, controller and
tick hooks are test equipment and stay in a test build. For testing without contacting
anyone, the project's own lobby server on 127.0.0.1 is the peer
(`docs/lobby-protocol.md`, `docs/online-setup.md`).

## Limits

- Loopback only was allowed here: host UDP was run on 127.0.0.1 with the port mapping.
  The unmapped form (the game's addresses are the hosts' addresses, a real broadcast) is
  a few lines and has not been run.
- Two machines. The shim has no limit of its own on UDP; the link is a pair by design.
- Agreement is with the Play! emulator and its floating-point model, as in
  `native-recomp.md`; nothing here compares with a console.
- The comparison is the tick log. Two machines in step differ in about half a megabyte of
  memory by design (`tools/rig/README.md`), so whole-memory equality between a native and
  an emulator machine in a net game was not attempted.
- `pad_readPort` is overwritten only for port 0 and only when a script is given; without
  a script the runtime's own controller service is what the game reads.

## How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
N=local/recomp-out/net; E=tools/rig/examples; S=tools/play-net/sections-suggested.txt
python3 tools/recomp/net/build_net.py
python3 tools/recomp/net/build_net.py --name fix --pnach patches/SLUS-20973_4028A55F.pnach --sections $S
python3 tools/recomp/net/build_net.py --name wrap --wrap-memory

# power-on, lobby, launch, strife: native pair; native + emulator
python3 tools/recomp/net/netpair.py run $N/boot --boot --script $E/pair-start.rig
python3 tools/recomp/net/netpair.py run $N/bootx --boot --a native --b rig --script $E/pair-start.rig

# into the arena and its fight, with delay and loss; the same over host UDP
cat $E/pair-start.rig $E/pair-arena.rig > $N/boot-arena.rig
python3 tools/recomp/net/netpair.py run $N/arena --boot --script $N/boot-arena.rig --bus delay=3,jitter=3,loss=50,seed=1
python3 tools/recomp/net/netpair.py run $N/arenax --boot --a rig --b native --script $N/boot-arena.rig --bus delay=3,jitter=3,loss=50,seed=1
python3 tools/recomp/net/netpair.py run $N/arenau --boot --udp 42000 --pace 240 --script $N/boot-arena.rig

# a known desync without and with the fix set (K2; K3, E9, D26 start from pair-chars-start.rig)
cat $E/pair-start.rig $E/pair-k2.rig > $N/boot-k2.rig
W="--tick-watch p1q1=g_players+0x4c30+0x258c:s16"
python3 tools/recomp/net/netpair.py run $N/k2 --boot --script $N/boot-k2.rig --bus delay=10 $W
python3 tools/recomp/net/netpair.py run $N/k2f --boot --program rta_native_net-fix --script $N/boot-k2.rig --bus delay=10 $W

# a long soak (the fuzz line of pair-arena.rig lengthened to 300000 frames)
python3 tools/recomp/net/netpair.py run $N/soak --boot --program rta_native_net-wrap --script $N/boot-arena-300k.rig \
        --bus delay=3,jitter=4,loss=60,seed=11 --columns small
```

A rig machine is an `rta_rig` runner under `nice -n 19`; a mixed pair has one, a rig pair
two. Exit codes of a native machine: 0 done, 3 a script condition timed out or the runtime
stopped, 4 `RTA_NET_FRAMES` ended before the script, 6 the other machine ended first, 7 a
level change became pending and `RTA_NET_ALLOW_LEVEL` was not set (resumed images without
`--adopt`).

## Files

`tools/recomp/net/netshim.cpp`, `hle-net.txt`, `build_net.py`, `netpair.py`,
`soakscript.py`, `examples/strife-fuzz.rig`, `examples/arena-prelude.rig`. Everything
generated, dumped or logged is under `local/recomp-out/`.
