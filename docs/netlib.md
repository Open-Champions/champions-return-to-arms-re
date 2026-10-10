# netlib — lobby client, SOE UdpLibrary, AES, Sony SDK (0x323dcc–0x3b0000)

2,066 functions of third-party and platform code plus the game's own lobby front end.
Everything here was read from the executable; nothing was run when it was written. Since
then the project has a live game — the Play! emulator, which is not a PlayStation 2 and not PCSX2 —
and what was run on it is listed in `FINDINGS.md`, "Run on the live game" (rows V1–V13) and `docs/issues/live-rig.md`.
Two things in it bear on this document (4d there). The game loads its eleven network
modules from the disc at boot and they start as real code; and the ten library entries the
game's own netcode calls (`sceLibnetInitialize`, `sceInetInterfaceControl`, `sceInetCreate`,
`sceInetOpen`, `sceInetSendTo`, `sceInetRecvFrom` and the rest) were seen being called,
with the arguments their call sites show — but with the library itself replaced by the rig
at those entries, so no library code below them ran. The lobby client, UdpLibrary, AES and the
sign-in path were not run at all. No test patch has been run on a live game. Claims are marked
**Observed** (read at the address given), **Inferred** or **Unknown**. Function names in
`code font` are in `symbols/netlib.tsv` unless noted.

Library function names (`sceInetSendTo`, `CreateSema`, `UdpConnection_Send` …) are the
vendor's own names where the code gives enough evidence to be sure which function it is
(a string naming the function, a system-call number, an assertion with the member name).
SOE's UdpLibrary is publicly documented; I used that only as a guide to where to look and
checked every function I named against the code.

## The headline result

**Gameplay traffic does not use UdpLibrary.** UdpLibrary carries only the pre-game
handshake between the PS2s in a game room. When the game launches, the lobby front end
deletes the `UdpManager` and the game's own netcode opens a plain UDP socket through Sony's
libnet and speaks its own protocol on it.

Evidence (all Observed):

- `UdpConnection_Send` (0x391430) is reached from 18 `jal` sites (0x32b554–0x33082c) and
  one tail jump (0x33067c), all inside the lobby client. Every site passes channel 4. The three
  generic "send this buffer to a peer" helpers at 0x330528, 0x3305f8 and 0x330768 have no
  callers and no pointers to them.
- Every direct call or jump into 0x390b10–0x39caa0 (UdpLibrary) comes from 0x324000–0x332000
  (lobby client) or from inline class members at 0x3d0000–0x3e5c40. None comes from the game
  netcode at 0x131d88–0x13ecf8.
- Lobby state 7 (inside `lobby_task`, about 0x327530–0x327740) copies each peer's address
  and port into the netcode tables 0x402b3b (4 bytes per ident) and 0x402b5c (word per
  ident), then calls `SRSClient_shutdownUdp` (0x328770), which ends by deleting the manager
  and zeroing `SRSClient+0x40`. `SRSClient_update` skips `UdpManager_GiveTime` when that
  pointer is null (0x32d3c0).
- The netcode calls `sceInetCreate`/`sceInetOpen` (0x134c60, 0x135638), `sceInetRecvFrom`
  (0x1345c0, 0x135638, 0x13c078) and `sceInetSendTo` (0x131b00, 0x132e90, 0x1345c0,
  0x1354f8, 0x135638, 0x137d60, 0x13e2c8) itself, with its own connection ids (0x4027c8,
  0x402b80).

Consequence for `FINDINGS.md`: L1 should read "peer to peer over raw UDP through libnet;
UdpLibrary is used only for the lobby handshake". L2's numbers are right for the library
but describe the handshake, not play. L3 falls away: per-frame input never rides a
UdpLibrary reliable channel. The answer to "how long before a lost input is resent" is in
the netcode area (the send rotation in `net_main` and `net_sendInputPacket` 0x137d60, names
from `symbols/netcode.tsv`), not here.

### The resend constants, for the record

They decide how long a *lobby handshake* message (welcome, peer list, character info,
start) waits before it is resent.

| Address | Instruction word | Value | What |
|---|---|---|---|
| 0x32a6ac | 0x240E012C | 300 | resendDelayAdjust, ms added to the scaled ping (stored 0x32a75c) |
| 0x32a6b0 | 0x240F007D | 125 | resendDelayPercent, percent of average ping (stored 0x32a760) |
| 0x32a6b4 | 0x24101F40 | 8000 | resendDelayCap, upper bound in ms (stored 0x32a764) |
| 0x399ee8 | 0x24030320 | 800 | starting value of the channel's average ping |
| 0x39a970 | 0x24030064 | 100 | divisor for the percent |
| 0x39af88 | 0x24630064 | +100 | added to average ping when a timed-out packet is resent, at most once per ping interval |
| 0x39b8f8 | 0x24420190 | +400 | added to average ping when an ack-all arrives for data already acked |

Resend delay = min(cap, averagePing × percent / 100 + adjust), computed at
0x39a96c–0x39a9b0 in `UdpReliableChannel_GiveTime` (the multiply at 0x39a988 is the
three-operand R5900 form, which the disassembler prints as unknown). Average ping is
updated only by packets that were never resent: new = (3 × old + sample) / 4
(0x39ba80–0x39babc). With the starting value the first resend comes after 1300 ms, which
the stepped clock rounds up to 8 steps (1333 ms).

The one-word change that shortens it: at 0x32a6ac replace 0x240E012C with a smaller
immediate, for example 0x240E0064 (100 ms). It is safe in the sense that the receiver
discards duplicates by sequence number and the only reader of the value is the delay
computation at 0x39a980. It is of
little use, for two reasons: it does nothing for gameplay, and the library's clock only
moves in 166.67 ms steps (see "Clock" below), so any delay under one step behaves the same.

## Layout of the range

Boundaries are function starts. "Anchor" says how the block was recognised. Blocks marked
*not examined* were placed by their strings only.

| Range | Module | Anchor |
|---|---|---|
| 0x323dcc–0x324288 | one start-up function called from the program entry 0x14fa88 | not examined |
| 0x324288–0x328410 | lobby front end: `lobby_task`, character-summary helpers, the entry points the rest of the game calls | lobby state word 0x506160 |
| 0x328410–0x331340 | class `SRSClient`: lobby callbacks and the UdpLibrary peer mesh | class name in assertion strings; three vtables 0x51c8d8, 0x51c918, 0x51cc08 |
| 0x331340–0x3321e0 | `MemStream` byte stream | its error string |
| 0x3321e0–0x3325d8 | IOP module load/unload helper, relaunch of the network set-up program | strings |
| 0x3325d8–0x34e068 | `SRSUI…` window classes: character select, chat, account creation, on-screen keyboard, login, main lobby, modal/status, network set-up (loads the DNAS, netglue and libinsck ERX modules), game selection, text box, chat control, terms of service | class names in strings; sub-boundaries not established |
| 0x34e068–0x34ef28 | network configuration thread (drives eznetcnf / eznetctl) | strings |
| 0x34ef28–0x350190 | libgraph (`sceGs…`) | `sceGsSyncPath` strings |
| 0x350190–0x3509d8 | libdma | string |
| 0x3509d8–0x352190 | libpad | strings |
| 0x352190–0x3525e0 | libmtap (multitap) | strings |
| 0x3525e0–0x353d68 | libkernl: 16-byte system-call stubs 0x3525e0–0x352e60, then handler lists, thread helpers, `DelayThread` | system-call numbers |
| 0x353d68–0x355608 | TTY output and the printf family (`dbg_printf` 0x355490) | strings |
| 0x355608–0x356e20 | SIF command and SIF RPC (`sceSifBindRpc`, `sceSifCallRpc`) | semaphore names |
| 0x356e20–0x35b0a8 | fileio (`sceOpen` … `sceReadlink`) | one semaphore name per call |
| 0x35b0a8–0x35ece0 | loadfile, IOP reboot, libc glue, kernel support (alarms, TLB set-up) | partly strings; mostly not examined |
| 0x35ece0–0x35f560 | libsdr (sound remote) | strings |
| 0x35f560–0x360ea0 | libmc (memory card) | strings |
| 0x360ea0–0x364a18 | libcdvd, including the streaming and CD-DA calls | strings |
| 0x364a18–0x364fb8 | libmrpc (multi-thread SIF RPC) | semaphore names |
| 0x364fb8–0x366550 | libnet (`sceInet…`, `sceLibnet…`) | buffer-size message, argument shapes at call sites |
| 0x366550–0x367da8 | netcnfif | strings; not examined |
| 0x367da8–0x3683b0 | eznetcnf client | functions print their own names |
| 0x3683b0–0x36b078 | Logitech keyboard/mouse library 1.06.001 | banner string |
| 0x36b078–0x36d2c8 | liblgaud 1.09.004 (Logitech USB headset) | functions print their own names |
| 0x36d2c8–0x37a5d8 | MPEG / IPU decoder (libmpeg from 0x372948) | strings; not examined |
| 0x37a5d8–0x37b474 | eznetctl client and its status-message tables | functions print their own names |
| 0x37b474–0x38bcd4 | SOEGamesAPI client: containers and data classes (–0x37c7b4), request builders (–0x381de8), `APICore` request bookkeeping (–0x382380), field serialisers (–0x383578), `APICore` reply and notification parsers (0x383858–0x388c50), data-class serialisers, connection wrapper (0x38b5fc–) | `APICore::` trace strings |
| 0x38bcd4–0x38c8c8 | TCP transport over libnet | trace strings |
| 0x38c8c8–0x38d378 | string encryption context | key strings at 0x55b700, 0x55b728 |
| 0x38d378–0x390748 | LibTomCrypt AES: `rijndael_setup` 0x38d48c, encrypt 0x38da40, decrypt 0x38ef90, self test 0x390518 | file names aes.c / aes_tab.c, error strings |
| 0x390748–0x390b10 | AES block loops and a small byte-string class | callers |
| 0x390b10–0x39caa0 | SOE UdpLibrary (details below) | file names in assertions |
| 0x39caa0–0x3a51b0 | liberx, the loader for ERX modules | strings |
| 0x3a51b0–0x3b0000 | math routines and compiler support (float, double and 64-bit helpers; the pure-virtual stub 0x3ad348) | call counts only; not examined |

UdpLibrary sub-layout (Observed from assertion file names and vtables):

| Range | Part |
|---|---|
| 0x390b10–0x3957d0 | `UdpConnection` (UdpConnection.cpp), vtable 0x51d920 |
| 0x3957d0–0x396104 | PS2 socket driver, vtable 0x51d9c8 (12 virtual functions) |
| 0x396104–0x396624 | guard (empty on PS2), `UdpIpAddress`, reference counting (UdpLibrary.cpp, UdpTypes.h) |
| 0x396624–0x399e20 | `UdpManager` (UdpManagerPS2.cpp), vtable 0x51db30 |
| 0x399e20–0x39bc54 | `UdpReliableChannel` (UdpReliableChannel.cpp) |
| 0x39bc54–0x39c5f0 | logical packet classes (UdpLogicalPacket.cpp) |
| 0x39c5f0–0x39caa0 | `UdpMisc`: clock differences, random, crc, variable-length values |

## How the pieces fit

```
game menus ──> lobby_task (run task, priority 0x19)
                 │  every 10th call
                 ▼
              SRSClient_update ──> SOEGamesAPI_process ──> TCP to the lobby server
                 │                                          (requests, replies, notifications)
                 ├──> UdpManager_GiveTime(100, 1) ──> UDP port 4000..4004 ──> other PS2s
                 └──> every 10th update: discovery datagram + seek-peer ping

state 7: peer table -> netcode tables, SRSClient_shutdownUdp, state 0xc (in game)
         the game netcode then owns the UDP port
```

`lobby_task` (0x324288) is registered by `lobby_addTask` with `task_add(fn, 0x19, name, 0)`;
the last argument 0 makes it a *run* task, so it is called once per simulated frame
(Observed: argument at 0x327f80; meaning of the argument from `names.tsv`). In state 0xc
(in game) it does only the periodic part and returns. Inferred: the task stays registered
during play, because the only code that removes it is `lobby_shutdown` and because game
code issues lobby requests (character saves) that need the TCP client serviced. Not
checked: whether a level load clears and re-adds tasks.

The object at 0x50613c is the `SRSClient`. It inherits three interfaces: the UdpLibrary
manager handler (vtable at +0x00), the UdpLibrary connection handler (+0x04) and the
SOEGamesAPI client with 92 virtual callbacks (base at +0x08, vtable 0x51c918).

### Lobby state word 0x506160

States 7, 0xc and 0xd are Observed in `lobby_task`; the descriptions of the others are
Inferred from the windows each case creates and were not checked in detail.

| State | Meaning |
|---|---|
| 1, 2 | create the window manager and windows |
| 3–6 | network set-up, login/account, character and game selection, main lobby window (6) |
| 7 | launch: fill the netcode peer tables, tear down UdpLibrary, go to 0xc |
| 8–0xb | reset own character info, open the character menu, then send character info (0x1b) and return to state 5 or 6 |
| 0xc | in game (`lobby_stateIsMenu` returns false) |
| 0xd | shut down (`lobby_shutdown`) |
| 0xe, 0xf | start-up wait |

State 6 becomes 7 when `SRSClient` flag 0x100 is set (`SRSUIMainWindow_nextLobbyState`,
0x33ca00). The flag is set by the host in `SRSClient_startGame` (0x330a40) and by the
others when the START message arrives.

## UdpLibrary as this game configures it

### UdpManager::Params (0x184 bytes, built on the stack in `srs_getUdpManager` 0x32a650)

The function first writes the library defaults (0x32a6b8–0x32a78c, an inlined constructor)
and then the game's own values (0x32a82c–0x32a85c and 0x32a890). `UdpManager_ctor` copies
the block to manager+0x14. Names marked A come from an assertion in `UdpManager_ctor` that
reads the offset; names marked U were confirmed by how the copy at manager+0x14+offset is
used (address given); names marked P are from the public library only (Inferred).

| Offset | Name | Default | Game value | Store | How known |
|---|---|---|---|---|---|
| +0x00 | handler | 0 | the SRSClient | 0x32a84c | U: called on connect request, 0x399a88 |
| +0x04 | maxConnections | 10 | 10 | 0x32a834 | A |
| +0x08 | port | 0 | 4000 | 0x32a838 | A |
| +0x0c | portRange | 0 | 5 | 0x32a82c | A; ctor tries port + (random + i) mod range |
| +0x10 | outgoingBufferSize | 65536 | — | | A |
| +0x14 | incomingBufferSize | 65536 | — | | A |
| +0x18 | packetHistoryMax | 100 | 1 | 0x32a83c | A |
| +0x1c | keepAliveDelay | 0 | 3000 | 0x32a844 | A; copied to connection+0x1e0 at 0x390e50 |
| +0x20 | portAliveDelay | 0 | — | | A |
| +0x24 | reply to packets from unknown senders | 1 | 0 | 0x32a848 | U: 0x398e34 tail |
| +0x28 | allow port remapping | 1 | — | | U: 0x398e34 |
| +0x2c | allow address remapping | 0 | — | | U: 0x398e34 |
| +0x30 | icmpErrorRetryPeriod | 5000 | — | | U: 0x3910f4 |
| +0x34 | noDataTimeout | 0 | 15000 | 0x32a840 | U: copied to connection+0x134 at 0x390e50 |
| +0x38 | oldestUnacknowledgedTimeout | 90000 | — | | U: 0x39a87c |
| +0x3c | reliableOverflowBytes | 0 | — | | U: 0x3937b4 |
| +0x40 | maxDataHoldTime | 50 | — | | U: 0x3937b4 |
| +0x44 | maxDataHoldSize | −1 (= packet size) | 0 | 0x32a854 | U: 0x39492c |
| +0x48 | maxRawPacketSize | 512 | — | | A |
| +0x4c | hashTableSize | 100 | — | | A |
| +0x50 | avoidPriorityQueue | 0 | 1 | 0x32a850 | U: ctor skips the queue, 0x396ec4 |
| +0x54 | clockSyncDelay | 0 | — | | A |
| +0x58 | (lingerDelay) | 10 | — | | P |
| +0x5c | pooledPacketMax | 1000 | 0 | 0x32a85c | U: 0x399200 |
| +0x60 | pooledPacketInitial | 0 | — | | U: ctor loop |
| +0x64 | pooledPacketSize | −1 | — | | U: ctor |
| +0x68 | cap on recycled callback events | 5000 | — | | U: 0x399474 |
| +0x6c | processIcmpErrors | 1 | — | | U: 0x3910f4 |
| +0x70 | processIcmpErrorsDuringNegotiating | 0 | — | | U: 0x3910f4 |
| +0x74 | connectAttemptDelay | 1000 | — | | U: 0x3937b4 |
| +0x78 | bindIpAddress[32] | "" | — | | U: passed to the driver's open |
| +0x98 | reliable[4], 0x34 bytes each | see below | — | | A (maxOutstandingBytes) |
| +0x168, +0x16c | user encrypt expansion bytes | 0 | — | | A |
| +0x170 | socket driver object | 0 | SRSClient+0x44 | 0x32a890 | U: ctor uses it instead of making one |
| +0x174 | queue callbacks as events | 0 | — | | U: copied to manager+0x230 |
| +0x178 | crcBytes | 0 | — | | A |
| +0x17c, +0x180 | encryptMethod[2] | 0 | — | | A |

So handshake packets carry no checksum and no encryption (Observed: both left at 0).

Reliable channel configuration, the same for all four channels (reliable[0] is written at
0x32a750–0x32a78c and copied to the other three by the loop at 0x32a790–0x32a808):

| Offset | Name | Value | How known |
|---|---|---|---|
| +0x00 | maxOutstandingBytes | 204800 | A |
| +0x04 | maxOutstandingPackets | 400 | U: array size, capped at 30000, 0x399e20 |
| +0x08 | maxInstandingPackets | 400 | U: incoming array size |
| +0x0c | fragmentSize | 0 | U: 0x399e20 |
| +0x10 | trickleSize | 0 | U: 0x399e20, 0x39a87c |
| +0x14 | trickleRate | 0 | U: 0x39a87c |
| +0x18 | resendDelayAdjust | 300 | U: 0x39a980 |
| +0x1c | resendDelayPercent | 125 | U: 0x39a96c |
| +0x20 | resendDelayCap | 8000 | U: 0x39a98c |
| +0x24 | congestionWindowMinimum | 0 | U: 0x399e20 |
| +0x28 | deliver out of order | 0 | U: 0x39b328 |
| +0x2c | coalesce | 1 | U: 0x399e20, 0x39a2a4 |
| +0x30 | ackDeduping | 1 | U: 0x39b328 tail |

### Send entry points

`UdpConnection_Send(conn, channel, data, len)` at 0x391430 is the only public entry in
use. It calls `UdpConnection_InternalSend` (0x391698), which switches through the jump
table at 0x55faa0:

| Channel | Meaning | Path |
|---|---|---|
| 0 | unreliable | `UdpConnection_BufferedSend` 0x39492c |
| 1 | unreliable, unbuffered | copy, then `UdpConnection_PhysicalSend` 0x394534 |
| 2 | ordered | 4-byte header (0, 0x1b, 16-bit counter from connection+0x1a4), then buffered send |
| 3 | ordered, unbuffered | same header, then physical send |
| 4–7 | reliable 1–4 | creates the channel object on first use (0xf8 bytes), then `UdpReliableChannel_Send` 0x39a2a4 |

An unreliable or ordered send that does not fit one datagram is silently moved to channel 4
(0x391774–0x3917ac). The game uses channel 4 only. `UdpConnection_SendLogicalPacket`
(0x39154c) has no callers.

### Holding and batching

Two separate mechanisms exist (Observed):

1. Connection multi-buffer. `UdpConnection_BufferedSend` groups small packets (type 3
   wrapper) until `maxDataHoldTime` passes. The game sets `maxDataHoldSize` to 0, and the
   test "length + 3 ≤ min(maxDataHoldSize, maxRawPacketSize)" at 0x39492c then always
   fails, so every packet handed to this function is sent at once. This mechanism is off.
2. Reliable-channel coalescing. `coalesce` is left at 1, so a reliable send shorter than
   (payload size − 5) is appended to a group packet (type 0x19) by
   `UdpReliableChannel_SendCoalesce` (0x39a4bc) and nothing reaches the socket until the
   next `UdpReliableChannel_GiveTime` pulls it into the send window. This mechanism is on.

`UdpManager_GiveTime` is called from `SRSClient_update` (once per 10 lobby-task calls),
from `SRSClient_sendStart` and from the shutdown flush. A handshake message therefore
waits up to 10 frames before its first transmission, except START, which is pushed out
immediately.

### Clock

All UdpLibrary timing uses the driver's clock, `UdpDriverPS2_Clock` (0x395e3c): the 64-bit
counter at 0x564208 times the double 16.66666 at 0x55fe30, plus an offset that keeps it
monotonic. The only writer of the counter is `SRSClient_update`, which adds 10 per call
(0x32d394). So the clock is "lobby-task calls × 16.67 ms", advances in 166.67 ms steps, and
stands still whenever `SRSClient_update` is not being called (Observed). It is not a
hardware timer.

### Resend, keep-alive, timeouts

`UdpReliableChannel_GiveTime` (0x39a87c), in my words:

```
if clock < nextNeedTime: return the difference
delay = min(cap, avgPing * percent / 100 + adjust)
oldest = max(clock - delay, firstSendTimeOfLastAckedPacket)
for each outstanding packet, oldest id first, while window space remains:
    pull new data into the window when the id reaches the end
    if packet.lastSend < oldest: mark it for sending
send marked packets (header type 9+n, or 13+n for a fragment):
    first time: stamp firstSend
    resend:
        if clock - firstSend > oldestUnacknowledgedTimeout (90 s): disconnect, reason 8
        if lastSend is older than the last acked packet's first send   ("overtaken")
            once per ping interval: window = window * 3/4
        else                                                           ("timed out")
            once per ping interval: threshold = max(2*payload, window/2),
                                    window = starting window, avgPing += 100 (capped)
    stamp lastSend
```

Other behaviour, all in `UdpConnection_InternalGiveTime` (0x3937b4) unless noted:

- While connecting (status 0) a 14-byte connect packet (type 1, protocol version 2, connect
  code, packet size) is sent every `connectAttemptDelay` = 1000 ms; the attempt is abandoned
  with reason 5 after the timeout given to `UdpManager_EstablishConnection` (15000 ms at
  0x329d58).
- Keep-alive: if nothing has been sent for 3000 ms a 2-byte packet (0, 6) goes out.
- No-data timeout: if nothing has been received for 15000 ms the connection is dropped with
  reason 2.
- Every received datagram stamps connection+0x188 (`UdpConnection_ProcessRawPacket`).
- Acks are sent immediately on receipt (`UdpReliableChannel_ReliablePacket`, 0x39b658
  onward) because the multi-buffer is off.
- Above the library, `SRSClient_pingSeekPeers` (0x32a4b8) runs every 10th update: each
  peer still being sought gets a 1-byte datagram straight through the driver (opens the
  NAT mapping) and is dropped after 15001 ms.

Disconnect reason numbers (Observed from the name table at 0x395454 and the constants
passed to `UdpConnection_InternalDisconnect`): 0 None, 1 IcmpError, 2 Timeout,
3 OtherSideTerminated, 4 ManagerDeleted, 5 ConnectFail, 6 Application,
7 UnreachableConnection, 8 UnacknowledgedTimeout, 9 NewConnectionAttempt,
10 ConnectionRefused, 11 ConnectError, 12 ConnectingToSelf, 13 ReliableOverflow,
14 ApplicationReleased.

Internal packet types (Observed in `UdpConnection_ProcessCookedPacket`, jump table
0x55fad0; a packet is internal when its first byte is 0): 1 connect, 2 confirm, 3 multi,
5 terminate, 6 keep-alive, 7 clock sync, 8 clock reflect, 9–12 reliable 1–4, 13–16
fragment 1–4, 17–20 ack 1–4, 21–24 ack-all 1–4, 0x19 group, 0x1a/0x1b ordered, 0x1c port
alive, 0x1d unreachable connection, 0x1e remap request. 4 is ignored.

### Object layouts (offsets Observed in the functions named)

`UdpManager` (0x390 bytes, allocated at 0x32a88c):

| Offset | Meaning | Seen in |
|---|---|---|
| +0x0c | vtable 0x51db30 | ctor |
| +0x14 | parameter block (0x184 bytes) | ctor copy loop |
| +0x1b8, +0x1bc | packet history ring and position | 0x39896c |
| +0x1c0 | random seed (clock at construction) | ctor |
| +0x1cc | connection list | 0x3976a8 |
| +0x1e0 | disconnect-pending list | 0x398348 |
| +0x1f4, +0x1f8 | address and connect-code hash tables | 0x3976a8 |
| +0x1fc | priority queue (null: disabled) | ctor 0x396ec4 |
| +0x208 | socket driver | ctor |
| +0x22c | error condition (2 = could not bind) | 0x397454 |
| +0x230 | queue callbacks as events | ctor |
| +0x250 | statistics, 0xa8 bytes | 0x3984f4 |

`UdpConnection` (0x358 bytes):

| Offset | Meaning | Seen in |
|---|---|---|
| +0x0c | vtable 0x51d920 | ctors |
| +0x48, +0x4c | remote address, port | 0x390e50 |
| +0x64 | status: 0 negotiating, 1 connected, 2 disconnected, 3 disconnect pending | 0x3937b4, 0x3911dc |
| +0x6c | manager (null once disconnected) | 0x3911dc |
| +0x70 | connect code | 0x390b30 |
| +0x78–0x127 | statistics | 0x391a30 |
| +0x130 | connect attempt timeout | 0x390b30 |
| +0x134 | no-data timeout | 0x390e50 |
| +0x138 | disconnect reason | 0x3911dc |
| +0x148 | four reliable channel pointers | 0x391918 |
| +0x15c, +0x168 | crc bytes, raw packet size | 0x390c88 |
| +0x178 | time the multi-buffer was started | 0x39492c |
| +0x180 | last send time | 0x394258 |
| +0x188 | last receive time | 0x391bf0 |
| +0x198, +0x19c | multi-buffer start and write pointer | 0x39492c |
| +0x1a4 | outgoing ordered counter | 0x39182c |
| +0x1dc | handler object | 0x32e0f8 |
| +0x1e0 | keep-alive delay | 0x390e50 |

`UdpReliableChannel` (0xf8 bytes):

| Offset | Meaning | Seen in |
|---|---|---|
| +0x04 | copy of the 0x34-byte configuration | 0x399e20 |
| +0x38 | connection | 0x399e20 |
| +0x40 | first-send time of the last acked packet | 0x39b950 |
| +0x50 | next time the channel needs service | 0x39a87c |
| +0x58 | last time the window was cut | 0x39a87c |
| +0x60 | channel number 0–3 | 0x399e20 |
| +0x68, +0x70 | next outgoing id, oldest unacked id (64-bit) | 0x39a68c, 0x39b950 |
| +0x78, +0x7c | bytes outstanding, bytes queued | 0x39a68c |
| +0x80–0x88 | fragment reassembly buffer, received, total | 0x39b718 |
| +0x8c | average ping | 0x399ef8, 0x39babc |
| +0x90 | payload bytes per packet | 0x399e20 |
| +0x98 | outstanding array, 0x28 bytes per id: +0x08 first send, +0x10 last send, +0x18 packet, +0x1c data, +0x20 length | 0x39a68c, 0x39a87c |
| +0x9c | queue of logical packets | 0x39a618 |
| +0xb0, +0xb4, +0xb8, +0xbc | window start size, window, slow-start threshold, minimum | 0x399e20 |
| +0xc8 | next expected incoming id | 0x39b328 |
| +0xd0 | incoming array, 8 bytes per id | 0x39b328 |
| +0xd4–0xe4 | coalesce packet, start, end, count, size limit | 0x39a4bc |
| +0xec, +0xf0, +0xf4 | counters: duplicates, overtaken resends, timed-out resends | 0x39b328, 0x39a87c |

PS2 driver (vtable 0x51d9c8; slot numbers as in `tools/vtab.py`): 2 open, 3 close,
4 receive, 5 send, 6 port-alive send, 7 local address, 9 name lookup, 12 clock. Its state
block holds the data connection id (+0), a second connection id used for ICMP (+4), and the
libnet client data and buffer (+0x28, +0x2c), which it shares with the lobby TCP client.

## The peer handshake (SRSClient over UdpLibrary)

`SRSClient` (object at 0x50613c), offsets Observed in the functions named:

| Offset | Meaning | Seen in |
|---|---|---|
| +0x00 | vtable 0x51c8d8, UdpLibrary manager handler | 0x3285c0 |
| +0x04 | vtable 0x51cc08, UdpLibrary connection handler | 0x3285c4 |
| +0x08 | SOEGamesAPI client base; its vtable 0x51c918 sits at +0x38 | 0x32e9b8 |
| +0x40 | UdpManager, null when not in a room | 0x32a650, 0x328770 |
| +0x44 | embedded PS2 socket driver | 0x32a830 |
| +0x54, +0x58 | discovery server address and port | 0x32d438 |
| +0x5c | update counter | 0x32d3d4 |
| +0x64 | flags, see below | many |
| +0x6c | maximum players (u16) | 0x330f18 |
| +0x84 | connect handler object (notified with negative codes) | 0x32e8b8 |
| +0x9c | game record, 0xb8 bytes | 0x32e588 |
| +0x4a0 | seek table: 4 peer records | 0x32c2c0 |
| +0x740 | known table: 4 peer records | 0x32b660 |
| +0x9e0 | reject table: 4 peer records | 0x32c2c0 |
| +0xc80 | local peer record | 0x32b660 |
| +0xd28 | session id, wide string | 0x32eba8 |
| +0xd68 | fatal error flag; stops `SRSClient_update` | 0x32e9b8 |

Flags at +0x64 (Observed tests and sets; meanings Inferred): 0x2 logged in (set 0x32eba8),
0x4 send discovery datagrams (tested 0x32d410), 0x10 joining (set 0x32aeb0), 0x20 welcomed
by the host (set in `SRSClient_OnRoutePacket`), 0x40 this machine is the host (gates
`SRSClient_welcomePeer` and the peer-list rebroadcast), 0x100 START sent or received.

Peer record (0xa8 bytes):

| Offset | Size | Meaning |
|---|---|---|
| +0x00 | s8 | ident: 0 is the host, −1 means empty |
| +0x01 | 32 | name |
| +0x21 | 32 | second string |
| +0x41, +0x42, +0x43 | u8 each | character bytes (0x42 doubles as the refusal message type in the reject table) |
| +0x44 | 0x40 | wide string |
| +0x88 | s64 | clock value when last heard (seek table) |
| +0x90, +0x94 | u32 | external and internal address |
| +0x98, +0x9a | u16 | external and internal port |
| +0x9c, +0xa0 | ptr | UdpConnection to the external / internal address |

Messages, all on channel 4. Header: u8 sender ident, u16 type (low byte first). Parsed in
`SRSClient_OnRoutePacket` (0x32ca18).

| Type | Body | Sent by | Effect on receipt |
|---|---|---|---|
| 0x19 | u8 count, then that many peer records | host, after any change | `SRSClient_readKnownPeers`: unknown peers go to the seek table and both their addresses are dialled |
| 0x1a | none | host, `SRSClient_sendStart` | sets flag 0x100 |
| 0x1b | sender's peer record | everyone, `SRSClient_sendCharInfo` | copies name and character bytes into the known entry; the host then re-sends 0x19 to all |
| 0x1c | none | host, to a connection found in the reject table | drop all peers, connect handler(−1) |
| 0x1d | u8 your ident, game record, wide string, u8 count, peer records | host, `SRSClient_welcomePeer` | stores ident and game record, sends API request 0x5f with the host's string, sets flag 0x20, then handles the peer list |
| 0x1f | none | host, `SRSClient_sendEject` | drop all peers |

Peer record on the wire (`SRSPeer_write` 0x32e328): u8 ident; name as u32 length + bytes;
second string likewise; three u8; wide string as u32 count + 16-bit characters; u32
external address; u32 internal address; u16 external port; u16 internal port.

Game record on the wire (`SRSGameInfo_write` 0x32e588): u32; u32 address, u16 port; u32
address, u16 port; two wide strings (capacities 0x1e and 0x80 characters); three u16; two
u8. The three u16 and the first u8 are what state 7 copies, on the host only, into the
netcode globals 0x402a32, 0x402a33, 0x402a35 and (plus one) 0x402a34.

Connection set-up: the lobby server tells a client to dial another with notification 0x65
(two address/port pairs). `SRSClient_onClientRequestsConnect2` adds the peer to the seek
table and `srs_notifyClientRequestsConnect2` calls `UdpManager_EstablishConnection` for the
external pair and, if different, the internal pair, 15 s each. Whichever connects first is
handled in `SRSClient_onPeerConnected` (0x32c2c0), which moves the peer from the seek table
to the known table; on the host it also assigns the lowest free ident
(`SRSClient_nextFreeIdent`) and welcomes the newcomer.

## The lobby protocol (SOEGamesAPI over TCP)

Transport (Observed, `apitcp_sendFramed` 0x38c1e4, `apitcp_readLength` 0x38c65c): each
message is a 4-byte big-endian length that counts itself, followed by the payload. Inside
the payload every integer is little-endian.

Field encodings (Observed in the serialisers 0x382380–0x383098 and 0x389e94–0x38a208):

| Name used below | Encoding |
|---|---|
| u8, u16, u32 | 1, 2, 4 bytes, low byte first |
| str | u32 byte count, bytes |
| wstr | u32 character count, 16-bit characters |
| enc | a wstr whose characters are an AES blob: u32 plain byte length, then the text zero-padded to (length rounded down to 16) + 16 bytes and encrypted block by block (`apicrypt_encrypt` 0x38cf34) |
| blob | u32 byte count, bytes |

Request header (`soeapi_writeHeader` 0x37cc64): u16 type, u32 tracking number (a counter
that skips 0), u32 taken from word 0 of the API object. Requests marked S then carry the
session id as an enc field (`soeapi_writeHeaderWithSession` 0x37cd14).

Reply header (`APICore_readResponseHeader` 0x3837bc): u16 type, u32 tracking number, u32
result. Replies are matched to requests by tracking number in `APICore_onMessage`
(0x381f80); a frame with no pending request goes to `APICore_notificationCallback`.

Connect sequence (Observed, `APICore_onConnect` 0x388a34 and `APICore_connectSequence`
0x387124): on the first connection (host con.soegames.net, set in
`lobby_createSOEGamesAPI`) the client sends 0x43; the reply is a host string and a port and
the client reconnects there. On that connection it sends 0x27 with its own key string; the
reply is a str that is decrypted with the fixed 32-character key at 0x55b728 and becomes the
session key. Both ciphers are AES with a 256-bit key in ECB mode (`rijndael_setup` is called
with key length 0x20).

Requests the client can build. Fields are in wire order after the header; the label in the
last column is what the public Champions Reborn server source calls the message, given
only as a cross-reference. Some builders have no direct caller in this executable (they
were looked for as `jal` targets only); Inferred: they are left over from the library's use
in the earlier game.

| Type | Builder | S | Fields | Cross-reference |
|---|---|---|---|---|
| 0x43 | 0x37cec4 | | u32 = 12 | GetServerAddress (client trace string agrees) |
| 0x27 | 0x37cf98 | | str key, u32 = 12 | GetEncryptionKey (client trace string agrees) |
| 0x06 | 0x37d090 | | enc × 5 | CreateAccount |
| 0x16 | 0x37d354 | | enc, enc | Login |
| 0x64 | 0x37d4b4 | | enc, enc | — |
| 0x42 | 0x37d9a4 | | str, str | GetRules |
| 0x0f | 0x37f33c | | none | GetRealmStats |
| 0x05, 0x0e, 0x17, 0x61, 0x62, 0x63 | 0x38014c, 0x37dd6c, 0x37d614, 0x37dcac, 0x37dd0c, 0x37dcdc | S | none | CancelGame, GetPublicRooms, Logout, GetSocialListInitial, GetSocialListUpdate, — |
| 0x07, 0x0b, 0x24, 0x46, 0x52 | 0x37dc7c, 0x37dd3c, 0x37d644, 0x37f56c, 0x37dab4 | S | none; no direct caller | —, —, TouchSession, —, — |
| 0x01, 0x02, 0x1c, 0x1d | 0x37e3cc, 0x37e5c4, 0x37e4c8, 0x37e6c0 | S | wstr | AddFriend, AddIgnore, RemoveFriend, RemoveIgnore |
| 0x09, 0x0c, 0x11, 0x15 | 0x37de98, 0x37df94, 0x37dd9c, 0x37e090 | S | wstr | CreatePrivateRoom, EnterRoom, GetRoom, LeaveRoom |
| 0x21, 0x22, 0x19 | 0x37e2ac, 0x37e18c, 0x37ef9c | S | wstr, wstr | SendInstantMessage, SendRoomMessage, — |
| 0x23 | 0x380374 | S | u8, u16, list | StartGame |
| 0x54 | 0x37f708 | S | u16, u32, u32, u32, wstr, option list, blob, wstr, u32, wstr, u32 | CreatePublicGame (RTA) |
| 0x55 | 0x37fac8 | S | u16, u32, u32, i32, option list, u8, u32, u32 | MatchGame (RTA) |
| 0x56 | 0x37f950 | S | wstr, wstr, u32, wstr, u32 | CreatePrivateGame (RTA) |
| 0x57 | 0x380278 | S | wstr | GetGame (RTA) |
| 0x58 | 0x380888 | S | u32, wstr, list, list, blob, u32 = 0 | CreateNewCharacter |
| 0x5a | 0x3812c4 | S | u32, u32 | DeleteCharacter |
| 0x5b | 0x381420 | S | u32 | GetNetCharacterList |
| 0x5c | 0x3817b0 | S | u32 | GetCharacterData |
| 0x5e | 0x380f08 | S | enc, u32, u32, wstr, list, list, blob, u32 = 0 | SaveCharacter |
| 0x5f | 0x381554 | S | enc | UserJoinSuccess |
| 0x60 | 0x3816c0 | S | none | CancelGame (RTA) |
| 0x66 | 0x3804f8 | S | u32, wstr, i32 | DoClientDiscovery (RTA) |
| 0x00, 0x03, 0x04, 0x08, 0x14, 0x1b, 0x1e, 0x1f | 0x37e9fc, 0x37ec3c, 0x37e7bc, 0x37fc88, 0x37ee7c, 0x37eb1c, 0x37ed5c, 0x37e8dc | S | wstr, wstr; no direct caller | 0x08 CreatePrivateGame |
| 0x0d, 0x25, 0x44 | 0x38017c, 0x38063c, 0x38075c | S | wstr / u32, wstr / blob; no direct caller | GetGame, DoClientDiscovery, UpdateGameData |
| 0x28, 0x29 | 0x37d674, 0x37d80c | S | enc, enc; no direct caller | — |
| 0x53 | 0x37dae4 | S | wstr × 4, i32; no direct caller | — |
| 0x12, 0x13, 0x10 | 0x37f0bc, 0x37f1a8, 0x37f294 | | wstr / wstr / none; no direct caller | — |
| 0x0a, 0x18, 0x1a, 0x45 | 0x37fda8, 0x37ff8c, 0x37f59c, 0x37f3e4 | S | the pre-RTA forms of 0x54 and 0x55, a list request, an option request; no direct caller | CreatePublicGame, MatchGame, —, — |

Replies and notifications, as far as read. The reply parser `APICore_responseCallback`
(0x3841dc) reads the fields and calls the `SRSClient` callback in the slot shown (slot n is
vtable 0x51c918 offset n × 8).

| Type | Fields after the header | Callback |
|---|---|---|
| 0x06 | enc | slot 5, `SRSClient_onCreateAccountResult` |
| 0x16 | enc (≤ 0x40 characters), enc (≤ 0x80) | slot 6, `SRSClient_onLoginResult` |
| 0x43 | str host, i32 port | handled inside `APICore_connectSequence` |
| 0x27 | str key blob | handled inside `APICore_connectSequence` |
| 0x0e | list of rooms | slot 19, `SRSClient_onPublicRooms` |
| 0x11 | wstr, wstr, list | slot 20, `SRSClient_onRoomInfo` |
| 0x55 | several parallel lists | slot 48, `SRSClient_onMatchGame` |
| 0x57 | wstr (≤ 15), u32, wstr (≤ 0x200), u32, wstr (≤ 0x200), u32 | slot 51, `SRSClient_onGetGame` |
| 0x5c | blob, u32 | slot 60 (0x32fbd8) |
| 0x62, 0x63 | lists | slots 16, 17: friend and ignore lists |
| 0x54, 0x56, 0x25, 0x66 | str, i32 | not followed |
| 0x2a–0x3d (notifications) | two or three wstr each | slots 65–84: room, chat and friend events |
| 0x3e, 0x3f, 0x40 | str address, i32 port | slots 85, 86, 88 |
| 0x41 | u16 | slot 89, `SRSClient_onForcedLogout` |
| 0x65 | str, i32, str, i32 | slot 87, `SRSClient_onClientRequestsConnect2` |

The client also sends one datagram outside TCP: every 10th `SRSClient_update` while flag 4
is set, `SRSClient_sendDiscoveryDatagram` (0x32a8d0) sends the encrypted session id (at most
64 bytes) from the game's UDP socket to the discovery address, so the server learns the
port mapping (Inferred purpose).

## Per-machine state

Nothing in this area runs the simulation, so there is no place here where simulation code
reads camera, audio or pad state. What the area does contribute:

1. **Launch tables are built from each machine's own view of the room.** Observed: lobby
   state 7 (in `lobby_task`, 0x327530–0x327740) sets the player count 0x402a37 to 1 plus the
   number of occupied entries in *this machine's* known table, raised to own ident + 1 if
   smaller, and fills the address/port tables from each peer's live UdpConnection. Inferred:
   if one machine has not finished connecting to another when START arrives (the peer is
   still in its seek table), its count and tables differ from the host's. What the netcode
   launch handshake does with that belongs to the netcode area.
2. **A peer with no live connection inherits the previous peer's address.** Observed:
   `SRSPeer_getConnectedAddress` (0x32e198) writes its outputs only when a connection is in
   status 1; state 7 initialises the address once before the loop and the port not at all,
   so the first such peer gets address 0 and an uninitialised port, later ones the previous
   peer's values.
3. **START is sent once and cannot be resent.** Observed: the host sets flag 0x100, sends
   0x1a and calls `UdpManager_GiveTime` once (0x32b7f8); the next lobby-task call moves to
   state 7 and runs `SRSClient_shutdownUdp`, whose flush loop (at most 100 rounds) never
   calls `SRSClient_update`, the only thing that advances the UdpLibrary clock. With the
   clock frozen the resend test in `UdpReliableChannel_GiveTime` cannot fire. Inferred: if
   that one datagram is lost, the peer never launches while the others count it as a
   player. The loop is short: `DelayThread` takes microseconds (Observed at 0x35dac8: the
   argument is scaled by 147,456,000 / 1,000,000), so 100 rounds sleep about 10 ms in total
   plus the time of the receive calls.
4. **The lobby clock counts simulated frames.** Observed: `lobby_task` is a run task and
   the UdpLibrary/SRS clock is derived from its call count. Every timeout in this area
   (keep-alive 3000, no-data 15000, seek 15001, connect 15000, resend) is therefore
   measured in frames/60, not seconds, and stretches when the game runs slowly. During play
   only the lobby TCP client is still affected.
5. **Lobby callbacks run inside the simulated frame during play.** Inferred (see the note
   on `lobby_task` above): `SRSClient_update` keeps servicing the TCP connection every 10th
   simulated frame in state 0xc, and its callbacks fire at whatever frame the data arrives
   on that machine. Observed: the
   callbacks I read write only lobby globals (0x506154, 0x506178, 0x50615d, 0x4f85d0[slot])
   whose readers are menu, HUD-status and save-screen code (0x1d9cd4, 0x1dbc48, 0x21fcd0,
   0x220468, 0x2259d0) and `net_launchTransfer`. Unknown: whether the connect-handler chain
   (`SRSClient+0x84`, reached on TCP loss and forced logout) changes anything the
   simulation reads; its targets are small adaptor functions at 0x3d2350–0x3d25d8 that I
   did not follow.
6. **The C library random generator is seeded per machine.** Observed: its seed function
   0x3b70d8 has one caller, `apicrypt_ctor` (0x38c934), which passes the lobby seconds
   counter 0x564330; the generator 0x3b70f0 has two callers, the key generator 0x38ca40 and
   the engine function 0x192a40. Inferred: 0x192a40 looks like an effect builder (it sits
   next to the trail code), which would make this cosmetic; it should be confirmed by the
   engine area.
7. **Blocking calls.** Observed: every `sceInet…` call is a multi-thread SIF RPC that waits
   for the IOP (`libnet_callRpc` 0x364fb8), so each send or receive made by the game netcode
   blocks the calling thread for a machine-dependent time. This changes timing only.
8. Raw pad data, CD streaming status, memory-card status and sound-driver status all enter
   the program through libraries in this range (libpad 0x3509d8–, libcdvd 0x360ea0–, libmc
   0x35f560–, libsdr 0x35ece0–). They are per machine by nature; whether simulation code
   reads them is a question for the areas that call them (engine, audio-save).

## Open questions

- The reply layouts for 0x0e, 0x11, 0x55, 0x58–0x5e and the notifications 0x2a–0x3d, 0x4c,
  0x4f, 0x51 were only outlined. The parsers are `APICore_responseCallback` (0x3841dc) and
  `APICore_notificationCallback` (0x387388); the list element readers are the inline
  functions at 0x3ded30–0x3e1ddc.
- The option-list and character-data encodings (helpers 0x389600, 0x38a2a8, 0x38a348,
  0x38a3e8, 0x38a208) were not read.
- Notifications 0x3e, 0x3f and 0x40 each carry an address and a port; which is "client
  discovered", "game discovered" and "client requests connect" was not settled from the
  client side. 0x32a0d0 (slot 88, type 0x40) looks a host up in the seek table.
- Where flags 0x4 and 0x40 of `SRSClient+0x64` are set (probably the create-game reply
  callbacks) was not found.
- Whether a lost TCP connection during play ends the game for that machine, and how (item 5
  above).
- Whether START loss is seen in practice (item 3). Two running copies with packet loss
  injected just before launch would settle it.
- The `SRSUI…` windows (0x3325d8–0x34e068, about 430 functions) were not read beyond the
  functions named. The DNAS / ERX loading sequence lives in the network window
  (0x33ed70).
- 0x323dcc, the kernel-support block 0x35c2a0–0x35ece0, netcnfif, the Logitech libraries,
  the MPEG decoder, liberx and everything from 0x3a51b0 up were located but not read.
- Parameter +0x58 of the UdpManager block (value 10) has no reader that I found.

## What was done and what was not

Read closely: `srs_getUdpManager`, `UdpManager_ctor`, the whole send path, the reliable
channel, connection housekeeping, the PS2 driver, the `SRSClient` peer functions, the
request builders (by script over the decompiled text, then spot-checked), the TCP framing
and the string encryption. Outlined: reply and notification parsers. Located only:
everything listed under "not examined" in the layout table. 380 symbols were written, 42 of
them system-call stubs named from their system-call number (two stubs each exist for
system calls 0x10 and 0x12; those four were left unnamed because the pairs cannot be told
apart from the stub alone).
