# netcode — lockstep loop, prediction, input codec, peers, game messages (0x131d88–0x13ecf8)

54 functions. Everything here was read from the decompile and the disassembly. The earlier
version added "nothing was seen on a running game"; that is no longer true of the whole
document. Parts of the wire format, the receiver and the drop procedure have since been
executed function by function in `tools/ee_emu.py` (`docs/spec/net-wire.md`), and a few
statements have been seen on the live game — one machine in a net game started through the
developer LAN path, in the Play! emulator, which is not a PlayStation 2 and not PCSX2
(`FINDINGS.md`, "Run on the live game", rows V1–V13; `docs/issues/live-rig.md` 4b, 4d). Those
are marked **Ran** where they stand: eleven button bits, the stick response, the 31-tick
re-clone of the prediction copy, the two object flags, the two developer-lobby packets and
how a lone machine's game ends.
Everything not so marked is still reading only; two machines have since been joined on that rig (FINDINGS V9–V13), and the only test patches run on a live game are the two for K1 and K2. Names are in `symbols/netcode.tsv` (41 functions, 40 globals) and
`names.tsv` (13 functions that were already named). Unless a line says *Inferred* or
*Unknown*, a statement is *Observed* at the address given.

## Summary

- The game's own netcode is a peer-to-peer deterministic lockstep for up to four machines.
  Each machine samples its pad once per rendered frame, stores it as an input record for a
  future frame, and the simulation only runs a frame when it holds that frame's record from
  every peer that has not been dropped.
- **Transport.** Lockstep traffic does not go through SOE's UdpLibrary. `net_sendInputPacket`
  and `net_pumpReceive` call the Sony libnet stubs `sceInetSendTo` 0x365830 and
  `sceInetRecvFrom` 0x365670 directly on a socket the game opens itself (`sceInetCreate`
  0x3654a8 with type 0 and a local port — the same call UdpLibrary's PS2 driver uses for its
  own UDP socket at 0x3958c0). So input, sync hashes and game messages are plain unreliable
  datagrams; the reliable-channel resend timer in FINDINGS L2 plays no part. Reliability is
  done by repetition: every input packet carries all frames the receiver has not yet
  acknowledged.
- **What a lost packet costs.** Nothing is resent on a timer. The next regular packet, 2, 4
  or 6 `net_main` calls later (1, 2 or 3 remote peers), carries the lost frames. Only the
  simulation tick waits; drawing and the local player's prediction go on. The tick can never
  run faster than real time afterwards, so each tick it waited becomes one more frame of
  input delay on that machine, and that delay is taken back one frame per 62 calls (or per
  31). See "When a packet is lost".
- Game messages (inventory, shop, dialog, level change, leave…) are byte strings queued by
  any code, attached to one of the sender's future input frames and executed by every
  machine, the sender included, when the simulation reaches that frame.
- There is no join in progress. The peer table is filled once, at the end of the launch
  handshake. Players leave by a game message, by a silence timeout that ends in a
  negotiated drop frame, or by a manual kick.

## How the pieces fit

Once per rendered frame `mainloop_runSession` (0x322998, call at 0x323248) calls
`net_main(0,0)` instead of `tasks_run`. One call does, in this order:

1. `net_pumpReceive` 0x13c078 — read every waiting datagram.
2. Housekeeping: kicked notices, silence timeout, kick negotiation (see "Drop").
3. Sample the local pad and camera yaw, apply the input lock, decide whether to *hold*
   (skip sampling this call), otherwise append `engine_frameStep()` (1 or 2) input records
   at `g_localInputFrame`.
4. Attach newly queued game-message bytes to an input frame.
5. Send an input packet to the peer whose turn it is in the send rotation.
6. Drop any peer whose agreed drop frame is the current frame.
7. Count how many consecutive frames from `g_netFrame` are *ready* (a record from every
   non-dropped peer); run `net_frameLoop(min(ready, engine_frameStep()))`.
8. `net_predictLocalPlayer` — run the ghost through local input frames not yet predicted.
9. Copy the raw local pad into `g_pads[local]` for menus and drawing.

`net_frameLoop` 0x139e88 runs one tick per step: apply each peer's record to its lockstep
pad, run that peer's game messages, run the run tasks, store the sync hash. After the last
step it may re-clone the ghost.

## Functions

| Address | Name | Role |
|---|---|---|
| 0x131d88 | `net_predictLocalPlayer` | runs the ghost for input frames `g_simFrame … g_localInputFrame-1`; with no ghost it only updates the camera |
| 0x132db0 | `net_flushBeforeLoad` | before a level load: no-sim, no-input `net_main` passes until all peers acked our input up to `g_netFrame` (max 121) |
| 0x132e90 | `net_main` | (noSim, holdInput) the per-rendered-frame driver described above |
| 0x1345c0 | `net_debugLanLobby` | developer LAN discovery, only when flag 0x402792 is set — which it is in the shipped data (the byte is 1); what keeps the retail game out is that `g_networkMode` is not yet set at the first level change. **Ran** with the boot argument `--net` (`docs/issues/live-rig.md` 4d; `docs/mainloop.md` section 7 step 3) |
| 0x134c60 | `net_launchTransfer` | prepares the launch: buffer, launch socket, own launch record (the handshake itself is 0x135638) |
| 0x1354f8 | `net_launchSendData` | launch DATA chunk with checksum |
| 0x135638 | `net_launchUpdate` | launch handshake state machine; fills the peer table on success |
| 0x1378e0 | `net_restoreButtonConfig` | puts the local controller mapping back into the per-slot tables |
| 0x137a10 | `net_loadModules` | IOP network modules and interface bring-up |
| 0x137d60 | `net_sendInputPacket` | builds and sends one input / raw-relay packet |
| 0x1393f8 | `net_shutdown` | close socket, clear peer table, leave network mode |
| 0x1397a0 | `net_gameInit` | resets lockstep state and codec states, initialises libnet, reads own address |
| 0x139e88 | `net_frameLoop` | (steps) the simulation ticks |
| 0x13b5d0 | `net_frameLoop2` (name in names.tsv is wrong) | (packet, length, raw) receiver of input and raw-relay packets |
| 0x13c078 | `net_pumpReceive` | datagram dispatcher |
| 0x13c450 / 0x13c970 | `netcodec_encodeAxis` / `netcodec_decodeAxis` | stick channel codec |
| 0x13ce68 | `net_launchDraw` | launch screen |
| 0x13d668 | `net_localIsFirstActive` | host test |
| 0x13d760, 0x13e6b0 | static initialiser of the codec states and its table entry | |
| 0x13da90 | `ShockProjectile_clone` | not netcode |
| 0x13da98 / 0x13dc30 | `net_registerMsgHandler` / `net_registerDirectHandler` | |
| 0x13db38 | `net_sendGameMsg` | (id, bytes, length) queue a game message; offline it calls the handler at once (0x13db78) |
| 0x13dcd0, 0x13dce0 | `net_clearGhost`, `net_startSync` | |
| 0x13dd40 … 0x13e638 | small queries and setters | see the symbol file |
| 0x13e6d0, 0x13e8f8, 0x13eac8, 0x13ebd8 | script loader pieces | not netcode |

Two netcode functions sit just below the range, in the creatures area: `net_sendMsgToPeers`
0x131b00 (direct, unsynchronised packet to a peer mask) and `net_kickPeer` 0x131cb8.

## Data structures

### Peer — `g_peers` 0x5bf838, 4 entries of 0x44e0 bytes

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | u8[4] | IPv4 address in the byte order of the libnet address block (the developer lobby prints bytes 3, 2, 1, 0 as a.b.c.d) | copied into bytes 4–7 of the address block of every send, 0x139384 |
| +0x04 | u32 | UDP port | last argument of `sceInetSendTo` |
| +0x08 | 8 bytes | not referenced in the code read | Unknown |
| +0x10 | codec state, 0x4c | receive side: state after the newest frame received from this peer | 0x13b910–0x13bac8 |
| +0x5c | s32 | frame up to which the send-side codec state has been advanced | read 0x133888, written 0x134160 |
| +0x60 | codec state, 0x4c | send side: state just before the frame this peer last acknowledged | encode calls 0x133b98–0x133c88 |
| +0xac | 256 × 24 | input ring, index = frame & 0xff | 0x134324 (ready scan), 0x13be2c (store) |
| +0x18ac | 256 × 12 | sync ring {frame, sim-frame counter before the tick, hash}; the local peer's ring holds this machine's own hashes | 0x13af44–0x13b048, 0x13bec0 |
| +0x24ac | 0x2000 | game-message byte ring | written 0x13dbd0–0x13dc00 and 0x13c01c, read 0x13acb4–0x13ad24 |
| +0x44ac | u32 | message ring write position | 0x13dc14, 0x13c02c |
| +0x44b0 | u32 | message ring read position; written for remote peers only; no read found (displacement and absolute-address search) | 0x13ad54 |
| +0x44b4 | 2 × u32 | previous buttons and repeat counter for `pad_apply` on the lockstep pad | 0x13ac84 |
| +0x44bc | s32 | newest frame received from this peer | 0x13b7f4, 0x13be6c |
| +0x44c0 | s32 | newest of *our* frames this peer has acknowledged; set to 1 for all four at launch | 0x13b7c4, 0x13768c |
| +0x44c4 | s32 | peer's lead: its newest input frame minus its simulation frame | 0x13b7ac |
| +0x44c8 | s32 | peer's simulation frame as last reported | 0x13b790 |
| +0x44cc | s32 | `net_main` calls since the last accepted packet from this peer | 0x13b750, 0x133060 |
| +0x44d0 | s32 | heard flag, set on every accepted packet, cleared by `net_clearHeardFlags` | 0x13b75c |
| +0x44d4 | u8 | this entry is the local machine | 0x137638 |
| +0x44d5 | u8 | dropped: its input is no longer required or applied | 0x134278, 0x13dec0 |
| +0x44d6 | u8 | kick state: 0 none, 1 being negotiated, 2 negotiated | set to 1 in 0x133060–0x1330a8, at 0x131d40 and in 0x13c194–0x13c2a0; set to 2 at 0x133320 |
| +0x44d7 | u8 | out of sync | 0x13b0ac, 0x13bf30 |
| +0x44d8 | s32 | drop frame: −1 while negotiating, then newest received frame + 1 | 0x1332a4 |
| +0x44dc | s32 | kicked-notice counter (non-zero after a manual kick); such a peer does not count as active in `net_fewerThanTwoActive` | 0x131d54, 0x132f24 |

`g_localSyncRing` 0x5c10e4 in names.tsv is simply peer 0's sync ring (0x5bf838 + 0x18ac);
the code always adds the local slot's offset to it.

### Input record — 24 bytes

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | u32 | frame number; the ready scan compares it with the frame wanted, so a stale ring entry is never used | 0x134340 |
| +0x04 | u16 | buttons: inverted pad bytes 2 and 3, byte 2 in the high half. 0x1 L2, 0x2 R2, 0x4 L1, 0x8 R1, 0x10 triangle, 0x20 circle, 0x40 cross, 0x80 square, 0x100 select, 0x200 L3, 0x400 R3, 0x800 start, 0x1000 up, 0x2000 right, 0x4000 down, 0x8000 left. The earlier version gave the whole layout as *Inferred* from the usual libpad layout. **Ran** for eleven of the sixteen bits (L2, R2, L1, R1, select, L3, R3 and the four directions: each held alone on the live game and read back from `g_pads` +8, `docs/issues/live-rig.md` 4b); the four face buttons and start were not pressed in isolation and stay *Inferred* | sampler 0x17421c |
| +0x06, +0x07 | u8, u8 | stick pair that `pad_apply` turns into pad +0x14/+0x18 (movement); pad buffer bytes 6 and 7, the left stick in the usual layout | 0x174410 |
| +0x08, +0x09 | u8, u8 | stick pair for pad +0x1c/+0x20; pad buffer bytes 4 and 5 (right stick) | same |
| +0x0a, +0x0b | u8, u8 | pad buffer bytes 0x10 and 0x11 (L1 and R1 pressure). **Not transmitted** — see "Per-machine state" | 0x174410 writes pad +0x38 and +0x50 from them |
| +0x0c | u32 | sign-extended 16-bit camera yaw with bit 0 replaced by a flag (camera mode field +0x34 ≠ 1) | 0x133464–0x1334a8 |
| +0x10 | u32 | start of this frame's game-message bytes in the owner's message ring | 0x133740 |
| +0x14 | u32 | number of game-message bytes for this frame, 0 for none | 0x133754, read 0x13ac90 |

### Codec state — 0x4c bytes

Six copies exist: send and receive per peer (above), and four globals — `g_simEncState`
0x5bf798 / `g_simDecState` 0x5bf7e8 used by the tick for the local player, and
`g_predictEncState` 0x5bf6f8 / `g_predictDecState` 0x5bf748 used by prediction (copied from
the first pair at each ghost rebase, 0x13b340–0x13b4f8).

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | channel | record byte +0x08 |
| +0x10 | channel | record byte +0x09 |
| +0x20 | channel | record byte +0x06 |
| +0x30 | channel | record byte +0x07 |
| +0x40 | s16 | previous raw yaw (encoder only) |
| +0x42 | s16 | predicted yaw |
| +0x44 | s16 | current yaw delta per frame |
| +0x48 | s32 | count of frames coded; only ever incremented |

A channel is {s32 step index 0–8, s32 predictor 0–255, float smoothed value, float
velocity}. Reset state is index 0, predictor 0, smoothed 128.0, velocity 0.

### Packet types (first 32-bit word of a datagram)

| Word | Meaning | Sent from | Handled at |
|---|---|---|---|
| 0xbd3d, 0xbd3e | developer LAN lobby announce / start (**Ran** on one machine: 0xbd3d to 192.168.1.255 port 4000 every 64 displayed frames, 0xbd3e eight times on the confirm button; `docs/issues/live-rig.md` 4d, FINDINGS V6) | 0x1345c0 | same |
| 0xbd3f | input packet | `net_main` 0x1341a8 | `net_frameLoop2`, called at 0x13c3d4 |
| 0xbd40 | marker of the sync record *inside* an input packet | 0x1391e4 | 0x13be68 |
| 0xbd41 | kick request {requester slot, mask of peers being kicked} | `net_main` 0x133234, every 30 rendered frames | 0x13c194–0x13c3a8 |
| 0xbd42 | raw relay of a kicked peer's last frames | 0x13c3a8 | `net_frameLoop2` with raw = 1 |
| 0xbd43 | "you were kicked" notice, 4 bytes | `net_main` 0x132fdc | sets flag 0x4027a0, shown by the HUD |
| 0xbd44–0xbd47 | direct messages, handler table 0x5d14e0 (only index 0 is registered: 0x31f308, 0x86-byte voice frames — *Inferred* from the Logitech audio library strings) | `net_sendMsgToPeers` 0x131b00 | 0x13c1b4 |

### Input packet (0xbd3f) and raw relay (0xbd42)

| Offset | Type | Meaning |
|---|---|---|
| 0 | u32 | type |
| 4 | u32 | last frame in the packet |
| 8 | u8 | low nibble: slot the frames belong to; high nibble: sender's *active mask* (bit per peer that is not dropped, not being kicked and not out of sync) |
| 9 | u8 | input packet: last frame − sender's simulation frame; raw relay: slot of the relaying machine |
| 10 | u8 | number of frames |
| 11 | s8 | acknowledgement: newest frame the sender has received from the addressee, minus the last frame of this packet |
| 12 | … | frames: bit stream (input packet) or 12-byte copies of record +4…+0xf (raw relay) |
| aligned to 4 | u32 | 0xbd40 followed by a 12-byte sync record, or 0xffffffff when this simulation frame's record was already sent (`g_netLastHashFrame` 0x4027cc). The receiver does not test for 0xffffffff: it compares the word with 0xbd40 only (0x13be68) and takes any other value as "no record". Up to two of the padding bytes in front of the word are uninitialised stack of the sender (**Executed**: 590 of 1,200 packets, `docs/spec/net-wire.md` 7.3) |
| then | repeated | message blocks {u8 last frame − frame, u8 byte count, bytes} for every frame in the packet that has message bytes, to the end of the datagram |

The first frame of an input packet is the frame the addressee last acknowledged (+0x44c0),
the last is `g_localInputFrame − 1`. That is the acknowledged frame itself, not the one
after it: the newest acknowledged frame is sent once more in every packet and the receiver
skips it (**Executed**, `docs/spec/net-wire.md` section 8). The receiver (0x13b5d0):

1. Ignores the whole packet if the sender's active mask differs from its own (0x13b6ec), if
   the slot is local or dropped, if it is flagged out of sync, or if it is being kicked and
   the packet is not a raw relay.
2. Clears the silence counter, sets the heard flag, records the peer's simulation frame,
   lead and acknowledgement.
3. If the packet ends after the newest frame already held and starts no later than that
   frame + 1, decodes it, skipping frames already held (the skip count is passed to the
   decoder so that state is only advanced for new frames), and stores the new records with
   message count 0. A packet that starts later is discarded — its frames, sync record and
   messages, that is; its acknowledgement has already been taken (the store to +0x44c0 at
   0x13b7f0 comes before the test at 0x13b7f4; **Executed**, `docs/spec/net-wire.md`
   section 9, row 6).
4. Stores the sync record in the peer's sync ring and compares it with this machine's own
   record for that frame if it has one (see "Sync check").
5. Copies each message block into the peer's message ring, once per frame (only while that
   record's count is still 0).

Steps 3 to 5 stand or fall together, which the list above did not say: when the packet
brings no new frame (it does not end after the newest frame held, 0x13b7a4–0x13b7a8) the
receiver leaves at once and reads neither the acknowledgement, nor the sync record, nor the
message blocks; from such a packet only the peer's simulation frame, its lead and the
silence counter are taken. When it starts later than newest + 1 (0x13b7f4–0x13b804) the
receiver leaves too, without the sync record and the message blocks, but in that case the
acknowledgement has been taken first (0x13b7c4–0x13b7f0; the second pass of corrections
said "neither the acknowledgement" for both cases, which is right only for the first). A machine that
is not sampling (held by the cap, or called with the hold argument during a load) still
sends packets, but its acknowledgements do not register and a sync record in one of them is
lost, since a record is sent once (`docs/issues/lag.md` section 3, C2; the consequence is
Inferred there).

## The codec, bit by bit

The stream is an array of 16-bit words in the machine's byte order; fields are written most
significant bit first, bit position p lives in word p >> 4. A packet with n frames contains,
in this order:

1. **Buttons.** 16 bits: the first frame's button word. Then a list of 5-bit run lengths:
   a run says how many consecutive frames have the current word. After a run shorter than
   31, unless the frame count is exhausted, a 4-bit number names one bit to toggle; changing
   several bits at once costs a zero-length run per extra bit. A run of exactly 31 is
   followed directly by another run.
2. **Four stick channels**, in the order record +6, +7, +8, +9. Each sample is reduced to
   two bits by the adaptive delta coder: *move* (0 or 1) and *direction*. With step =
   table[index] (4, 6, 8, 12, 16, 24, 32, 48, 64 at 0x402860), move = 1 when the sample is
   at least one step away from the predictor; the predictor then moves by one step toward it
   (clamped 0–255); index += 2 after a move, −1 otherwise (clamped 0–8).
   Bits for a channel: the *move* bits first — alternating between a 5-bit count of zeros
   (31 means "31 zeros, another count follows"; anything less implies a following 1) and
   groups of five literal bits that repeat while a group contains a 1; then, only if any
   move bit was 1, one bit for the direction of the first move followed by 3-bit run
   lengths of moves with the same direction (7 means "seven, same direction continues").
3. **Yaw.** 5-bit run lengths of frames that keep the current delta (predicted = predicted +
   delta), each followed (unless 31 or the end) by one bit and either a new 9-bit signed
   delta (bit 1) or a 16-bit absolute value (bit 0). The encoder (inlined five times:
   0x13a378 in the tick, 0x132220 in prediction, 0x133ce0, 0x138448 and 0x138d28 for the
   wire) picks: absolute when the raw value jumped by more than 1000 or the prediction is
   off by more than 3000; otherwise delta = raw change, plus error/15 when the
   prediction is off by more than 200; the current delta is kept when the new one differs by
   less than 31 and has not changed sign; new deltas are clamped to ±255.
4. **Yaw flag** (bit 0 of record +0xc): one bit, then 5-bit run lengths, the bit toggling
   after every run shorter than 31.
5. 16 bits 0xa5a5. Nothing checks it.

The decoder (0x13c970) rebuilds the predictor and then runs ten steps of a spring toward it
in single-precision floats. Each step is: value += velocity, then velocity = (velocity +
(target − value) × 0.05) × 0.5528 with the *new* value (0x13cdb0–0x13cdd8; the earlier
version wrote the two updates in the other order, though the sample numbers below were
produced with the right one). The factor 0.5528 is 1 − √0.2, computed at run time (0x13cc6c,
0x13cd24, 0x13cd64; `docs/issues/lag.md` C6). The truncated value is the stick byte. The
local player's own input goes through the same encode and decode before the tick uses it
(G4), so all machines agree — on the condition that the decoder's float spring gives the
same bits on every machine; rounding to nearest instead of chopping changes about 12 % of
the decoded bytes in a model (FINDINGS F5, `docs/issues/float-divergence.md`; item 11
below).

Consequences, from a re-implementation of the two functions (scratch model, not game code):

- A stick pushed from centre to full reads 129, 134, 143, 162, 201, 227, 239, 245 on the
  following frames: about half deflection after 4 frames and the 0.8 threshold `pad_apply`
  uses for digital directions after 6. This is in every net game regardless of connection,
  and the ghost is fed through the same codec. *Inferred* (model), not measured.
  (`docs/issues/lag.md` C7 puts the threshold on the 7th simulated frame, because 0.8 is
  tested after the radial dead zone of `pad_decodeStick` 0x174ce0, and the first movement
  of any size on the 5th.) Measured since, so no longer *Inferred* — **Ran**, one machine in
  a net game (`docs/issues/live-rig.md` 4d; FINDINGS V4): after a full push the prediction
  copy does not move for four samples, moves at 0.38 of full speed on the 5th, 0.68 on the
  6th and 0.82 on the 7th, and the real player follows one frame behind — the C7 figures.
  The two codec functions are entered eight times a frame with no remote peer. After
  release the movement takes five frames to die away, which no earlier document said.
  Offline the same push moves the player at once: the codec is not in the offline input
  path.
- The range is not symmetric: a stick held toward 255 settles at byte 251, which is 0.943
  after decoding (0.989 for the raw byte offline), while one held toward 0 reaches 0, which
  is −1.000 (`docs/issues/dynamic-tests.md`, executed in isolation). Movement speed scales
  linearly with the stick value (`docs/spec/movement-camera.md` 4.1). **Ran** on the live
  game: in a net game the settled speed toward 255 was 0.9426 of the speed toward 0, and
  offline the pad read 0.98851 toward 255 and −0.99999994 toward 0 (`docs/issues/live-rig.md`
  4c, 4d).
- With the reset state a centred stick decodes as 77, 43, 34, 44, 78, 101 … and only settles
  near 127 after about 13 frames. It is the same on every machine.

## The tick — `net_frameLoop(steps)` 0x139e88

For each step, unless a level name is pending in 0x41b6d0 (then the step does nothing and
`g_netFrame` does not advance, 0x139fb4):

1. Save `g_simFrame`, set it to `g_netFrame`.
2. For each peer in slot order that is not dropped: take its record for `g_netFrame`; for
   the local slot pass it through encode and decode (0x13a29c–0x13a99c); `pad_apply` it to
   `g_pads[slot]` (0x13ac84); store the low 16 bits of record +0xc in `g_netCamYaw[slot]`
   (0x13ac9c); then walk this frame's message bytes {id, length, payload} and call
   `g_netMsgHandlers[id](payload, length)` (0x13ad24).
3. For each peer that is being kicked and whose drop frame is this frame: clear object flag
   0x400000 on its player, call its take-damage slot with 1,000,000 and
   `Player_processDamage` (0x13ae48–0x13aeb8).
4. `tasks_run(1, 2)` with `g_inSimTick` set (0x13aee0).
5. Move the hit-flash flag 0x100 from the real local player to the ghost.
6. `path_service(1)`; `g_netFrame++`; restore `g_simFrame`.
7. Store the sync record for the new `g_netFrame`: hash = `g_randSeed` + `g_syncAcc` (never
   non-zero: its only writer stores 0, 0x139870) + integer x, y, height of every player
   object; compare with each remote peer's record for the same frame (0x13b048).

After the loop: the exclude mask goes back to 0x200000, and if more than 30 frames have
passed since the last rebase (or the force flag is set), a player object exists, the game
is not paused and the pause menu is not open, the ghost is deleted and cloned again from the
real player, `g_simFrame` is set to `g_netFrame` and the prediction codec states are
refreshed (0x13b1c8–0x13b5b0). `g_netAckFrame` 0x4027d4 is the frame of that last rebase;
despite its name nothing waits on it.

## Prediction — `net_predictLocalPlayer` 0x131d88

Outside the tick `g_simFrame` is the *prediction frame*. While it is below
`g_localInputFrame` the function takes the local record for that frame, runs it through the
prediction codec states, applies it to `g_pads[local]` and `g_netCamYaw[local]`, points the
player table at the ghost, runs the ghost's run slot, restores seed, hit points, mana and
the table pointer (G3), and increments `g_simFrame`. So each input frame is predicted once;
the ghost is only corrected at a rebase. The flag 0x4000000 on the ghost and
`g_predictCatchingUp` are set while more than one call's worth of frames remains, and the
camera is only updated when they are clear.

## Pacing and lag

### Input delay is not a constant

Input sampled in a call is stored at frame `g_localInputFrame` (0x4027a4), which then
advances by `engine_frameStep()`. The simulation may run at most up to
`g_localInputFrame − 2` in that call (0x1342bc), and at most `engine_frameStep()` frames per
call (0x1343a0–0x1343cc). The *lead* (`g_localInputFrame − g_netFrame`) is therefore at
least 2 at the ready scan, just after sampling — measured at the end of a call its floor is
1 (`docs/issues/lag.md` section 2.2 and C1; the earlier version gave 2 without saying
where) — and otherwise whatever it has grown to: it grows by one for every tick the
simulation could not run while input was still being sampled, and it shrinks only when a
call is *held* (no sample taken). A call is held when any of these is true (0x13354c–
0x133608):

| Rule | Condition | Constant at |
|---|---|---|
| cap | `g_localInputFrame` − (lowest simulation frame of this machine and all active peers) > 38. The peers' frames are the ones last *reported* in their packets, so the lead the cap really allows is 38 minus how far the slowest report lags (31–36 on a 30 ms link in the model of `docs/issues/lag.md`, C3) | 0x133554 |
| equalise | own lead ≥ 5 above the smallest lead (own and peers') for 31 calls in a row | 0x13354c, 0x133574 |
| trim | every 62nd call, if the smallest ready count seen in the window was > 2 — that is, only if all 62 calls of the window had 3 or more frames ready. With packet loss many windows do not qualify, and it never fires on a machine whose ready count is limited by another machine's input, so two leads can stay up to 4 frames apart indefinitely (equalise needs 5) (`docs/issues/lag.md` C4) | 0x1335c0, 0x1335e4, reset value 100 at 0x1335d8 |
| caller | second argument of `net_main` non-zero | 0x1335ac |
| (never) | `g_localInputFrame` < 3 | 0x133600 |

### What makes the loop wait

The ready scan (0x1342a8–0x134378) counts frames f = `g_netFrame`, `g_netFrame`+1 … below
`g_localInputFrame − 1` for which every non-dropped peer's ring entry carries frame number
f. The first missing record ends the count. If the count is 0 the call runs no tick and
`g_netStallCalls` 0x4027d0 goes up.

### How often packets go out

One input packet per peer per *send cycle*. `g_netSendCycle` = `g_netSendCycleTable`[number
of remote peers that are not dropped and not being kicked] = 2, 4 or 6 calls (table at
0x4027e8, read at 0x1337cc), times 1.5 when the UART modem driver is loaded (0x1337e0).
Peer k of n is served when the phase counter equals k × cycle / n (0x133850), so one packet
leaves every second call (third on the modem) whatever the player count. A packet is sent
even when it carries nothing new. It goes out through
`sceInetSendTo(0x5d1458, 0x5d0c40, socket 0x4027c8, buffer, length, 0, address block, port,
1000 ms)` at 0x1393b8. The receive side polls `sceInetRecvFrom(…, buffer, 0x7c0, &flags,
&address, &port, 0 ms)` at 0x13c14c until it returns −500.

Sync records ride inside input packets: at most one per simulation frame for the whole
machine (not per peer), never repeated. A lost one just means that frame is not compared.
With more than one remote peer each record therefore reaches only one of them. A raw relay
(packet 0xbd42) falls under the same once-per-frame rule and so uses up the relaying
machine's record for that frame; what it carries in that place is not the relayer's own
record but the entry at index `g_netFrame` & 0xff of the *relayed* peer's sync ring,
whatever frame that entry holds (0x1391f8–0x139240, the ring is chosen by the peer index;
**Executed**, `docs/spec/net-wire.md` 12.1).

### When a packet is lost

*Observed* mechanism, *Inferred* numbers (at 60 rendered frames per second):

- The frames it carried arrive with the next packet from that peer: 2 calls later with one
  remote peer (33 ms), 4 with two (67 ms), 6 with three (100 ms); 3, 6, 9 on the modem.
  Acknowledgements ride in the same packets, so a lost packet also delays the sender's
  knowledge of what was received, which only makes later packets a little longer.
- The receiving machine's tick stalls only if it uses up that peer's buffered frames before
  the next packet arrives, and then for at most one send interval per lost packet. How many
  frames are buffered depends on the relative timing of the machines: the pacing rules let
  the smaller of (own lead − 1) and (frames buffered from the slowest-arriving peer) settle
  at 2 or less, so at least one machine of a pair normally runs close to the edge.
- During the stall the machine keeps drawing, keeps sampling input and keeps predicting its
  own player, until its input is 38 frames ahead of the slowest simulation frame; then
  sampling stops too.
- The stall is not caught up: the tick runs at most `engine_frameStep()` frames per call,
  the same rate at which input is sampled. Every stalled tick therefore adds one frame to
  that machine's lead. The trim rule gives back one call's worth per 62 calls, the equalise
  rule one per 31 calls, and a held call on one machine can in turn stall a machine that was
  waiting for its input. After a long stall (anything over about 0.6 s reaches the cap) the
  lead is 38 frames and takes tens of seconds to drain.
- The same applies when one machine simply runs slowly: `engine_frameStep()` is capped at 2,
  so a machine rendering below 30 frames per second produces fewer than 60 input frames per
  second and every other machine stalls behind it. The threshold is 60, not 30, until the
  display has gone to half rate: at full display rate a call stands for one step however
  long the picture took, so every missed field costs the other machines one frame of lead;
  after 32 late pictures in a row the display drops to half rate, a call stands for two
  steps, and only then is 30 per second neutral (0x19e3a8, 0x19da78; FINDINGS L5,
  `docs/issues/lag.md` C5, `docs/mainloop.md` section 6). A machine that misses a field now
  and then, without 32 in a row, costs the others one frame each time.
- Long silences: after 300 stalled calls the HUD counter 0x40279c starts and the
  no-connection icon blinks; after 900 calls without an accepted packet from a peer the
  kick negotiation starts (below); the HUD shows the lost-connection text 1200 calls after
  the counter started and leaves the game at 1800 when more than two players were in it
  (thresholds in the HUD draw task 0x1dbc48, outside this range).

### Constants that control delay, pacing and timeouts

| What | Value | Address |
|---|---|---|
| send cycle table | 6, 2, 4, 6 | data 0x4027e8 |
| modem multiplier | cycle + cycle/2 | 0x1337e0 |
| ticks per call | min(ready, `engine_frameStep()`), 1 or 2 | 0x1343a0–0x1343cc |
| input cap | 38 frames | 0x133554 (compares with 39) |
| equalise threshold / duration | 5 frames / 31 calls | 0x13354c / 0x133574 |
| trim window / threshold | 62 calls / minimum ready > 2 | 0x1335c0 / 0x1335e4 |
| ghost rebase interval | more than 30 frames (**Ran**: `g_ghostRebaseFrame` stepped by 31 eight times in a row on the live game, `docs/issues/live-rig.md` 4d) | 0x13b1e8 |
| rebase frame at start | input frame − 10 | `net_startSync` 0x13dce0, `net_gameInit` 0x139d68 |
| silence before kick | more than 900 calls | 0x133060 |
| kick request repeat | rendered-frame counter multiple of 30 | 0x1330c4, 0x1332d4 |
| raw relay depth | newest frame − 40 … newest frame | 0x13c370 |
| kicked notice | every 10th call for 120 calls | 0x132f38, 0x132f24 |
| send timeout / receive timeout | 1000 ms / 0 | 0x139388 / 0x13c150 |
| receive buffer | 0x7c0 bytes | 0x13c140 |
| stall counter threshold | more than 300 calls | 0x134418 |
| flush before a level load | at most 121 passes | 0x132e48 |
| wait after a level load | until counter 0x40279c reaches 601 | 0x323054 (main loop) |
| launch | retries 0.75 s and 1.0 s, failure after 2700 frames, 120-frame countdown, chunk 1300 bytes (512 on the modem) | inside 0x135638 and 0x134c60 |

## Sync check

A record is {frame, value of `g_simFrame` before the tick (not compared), hash}. The
comparison is made twice, whichever side arrives second: when a record is received
(0x13bec0–0x13bf30) and when the local record is stored (0x13b048). A mismatch sets the
peer's out-of-sync byte and prints the "out of SYNC" line. From then on that peer's bit leaves this
machine's active mask and its packets are ignored, so the simulation stops as soon as that
peer's buffered input runs out; 900 calls later the silence timeout kicks it. In a
two-player game both sides flag each other and each ends alone. *Inferred* from the flag's
uses; not seen running. That sentence describes one possible outcome, not the rule
(**Executed** with three interpreter instances, three runs with three different outcomes,
`docs/spec/net-wire.md` section 11): the machine that flags first changes its active mask,
the other side then ignores its packets — sync records included — and may never set a flag
of its own. One flag on one machine is enough to stop the session; the machines without a
flag see a silent peer and drop it after the 900-call timeout. Still not seen on the live
game.

## Game messages

`net_sendGameMsg(id, bytes, n)` appends {id, n, bytes} to the local peer's message ring.
`net_main` (0x1336c4–0x13375c) attaches everything queued since the last attach to one input
frame: the frame after the first one not yet sent to anybody, or `g_netFrame` if that is
later — and only when such a frame already exists, so messages wait for the next send turn.
The block travels with that frame in every packet until acknowledged and is executed in
step 2 of the tick on every machine. Offline the handler is called immediately.

Ids are handed out by `net_registerMsgHandler` in the order of seven calls at
0x323e50–0x323e80:

| Id | Id stored at | Handler | Registered by | Family |
|---|---|---|---|---|
| 0 | 0x83d1c8 | 0x198f64 | `cut_registerNetMsg` 0x19b4b4 | cutscene |
| 1 | 0x505b14 | 0x31f354 | 0x31fd38 (also registers direct handler 0x31f308) | voice |
| 2 | 0x8e2e94 | `dialog_onMsg` 0x22ee2c | 0x22f974 | NPC dialog |
| 3 | 0x86ac40 | `hud_onMsg` 0x1d8ca0 | `hud_registerMsgHandler` 0x1dc194 | game |
| 4 | 0x86aa60 | 0x1e01b0 (empty) | same | none |
| 5 | 0x866d18 | `invmsg_dispatch` 0x1bfdb0 | 0x1c59a8 | inventory |
| 6 | 0x8e8ed8 | 0x31d82c | 0x31da4c | text line |
| 7 | 0x86a6a0 | `shop_onMsg` 0x1c5d28 | 0x1d13a0 | shop |

The handlers are outside this range and were only skimmed; their owners' documents have the
detail. Payload byte 0 is a sub-type except where noted.

| Id / sub | Payload after the sub-type | Sender and occasion | Effect |
|---|---|---|---|
| 0 | none (length 0) | `cut_advance` 0x199214 when this machine's dialog audio has ended | counts "voice done" for the cutscene wait key (D18) |
| 1 | one byte: slot in the low nibble, bit 7 = on | 0x31f1a4 (on), 0x31f1e4 (off) | sets or clears the slot's bit in 0x503968; talk indicator, *Inferred* |
| 2 / 0 | name length, NPC name, padding, player slot, two bytes, camera position (3 words), two camera angles | `dialog_start` 0x22fa50 from script `startDialog` | closes menus, moves every machine's camera to the sender's, starts the dialog |
| 2 / 1, 2, 3, 4 | 2 has one signed byte | dialog task 0x22ff48 from the raw local pad and local audio state | confirm, move choice, end, leave request |
| 3 / 0 | slot, a, b | 0x1de06c, quick-cast selector | swaps record bytes +0x4a84/+0x4a85 |
| 3 / 1 | slot, b, 32-bit, 64-bit | 0x1de3ec | assigns a spell to an ability record |
| 3 / 2 | slot, state, flag | `hudmsg_sendMenuState` 0x1de0dc, 14 call sites, net games only | state 0: clears object flag 0x800000, masks buttons 0xf0 for 60 calls on the owner; else sets 0x400000 (and 0x800000 when state > 1) |
| 3 / 3 | slot | 0x1de138 | recall potion |
| 3 / 4 | slot | 0x1de16c, only from the machine for which `net_localIsFirstActive` is true, when a peer is dropped | shows the player-left text and kills that player's character |
| 3 / 5 | three filler bytes, then a 32-bit **object address** | 0x1de1a0 from `Savepoint_run` | stores 1 at address + 0xcc |
| 3 / 6 | slot | 0x1de1e0 from the HUD draw task while the local player is leaving | on the other machines: `net_disconnectPlayer(slot, 1)` |
| 3 / 7 | level name string | 0x1d9250 | writes the pending level name 0x41b6d0; the tick then stops |
| 3 / 8 | none | 0x1de25c | starts the mission-exit countdown |
| 3 / 9 | none | 0x1de430, host only | resets the checksum count |
| 3 / 10 | slot, two filler bytes, two 32-bit checksums | `net_sendChecksums` 0x1de46c | when all have arrived, a mismatch sets `g_checksumFailed` and drops that slot |
| 3 / 11 | three filler bytes, level name | 0x1de598 | like 7, also clears the pause-menu flag |
| 3 / 12 | none | 0x1de5ec from the medal scripts | sets 0x4f7140 |
| 3 / 13 | slot, a | 0x1de0a4 | quick-cast warning |
| 4 / 0, 1 | none; slot | 0x1e0108 (unreferenced), 0x1e0134 | nothing — the handler is empty |
| 5 / 0–10 | see `symbols/ui.tsv` (`invmsg_send*`) | inventory screens | drop, equip, unequip, join panel, weapon class, stat point, skill point, combine, level byte, use potion |
| 6 | no sub-type: the text-entry buffer at 0x8e8a40, which starts with its own length byte (length + 5 bytes are sent) | 0x31da74 | appends a line to an 8-line log at 0x8e8ac8; text chat, *Inferred* |
| 7 / 0 | slot, 2 filler bytes, 32-bit **address** of a stock record in the static table 0x866e78 | `shopmsg_sendBuy` 0x1c5f78 | `shop_buy` |
| 7 / 1 | slot, 16-bit, 32-bit index, 16-bit, bag, two bytes | 0x1d1330 | sell |

Limits: a message is at most 255 bytes (length byte); the bytes attached to one frame are
counted in one byte on the wire (0x1392c4–0x1392c8) although the ring field is 32 bits; the id is not
range-checked before the table call (0x13ad24). **Executed** since (`docs/spec/net-wire.md`
7.5): with 304 bytes on one frame the builder wrote the count 0x30 and all 304 bytes, and
the receiver took 48, read the rest as further blocks, missed the end of the datagram and
walked on through memory. Two buffer sizes belong here as well: the builder assembles the
datagram in 5008 bytes of its own stack frame with no length check (0x137d9c, 0x137ed8;
overrun reproduced with a synthetic 255-frame packet, not reachable from a frame backlog
under the pacing cap), and a received datagram has 1984 bytes (0x7c0, 0x13c140).

## Launch, drop and disconnect

### Launch

`frontend_startNetGame` 0x1e21e0 calls `net_gameInit` and `net_launchTransfer`; the
front-end task then calls `net_launchUpdate` every frame while flag 0x402793 is set
(call at 0x1e0af4). The handshake runs on its own socket (`g_launchSocket`) with packets
{sender's player id, type, argument, payload}, mostly 0x200 bytes long. A launch datagram
shorter than 16 bytes is ignored, so a DATA chunk under 4 bytes could not be delivered (with
the sizes below the last chunk is never that short, *Inferred*). The DATA checksum is 16
bits; the sending loop masks with 0x8f37 and the receiving loop with 0x148f37, which agree
in the low 16 bits (`docs/spec/net-wire.md` section 15: the sender **Executed**, the
receiver read only):

| Type | Name in the executable's status strings | Argument / payload |
|---|---|---|
| 0, 1 | SHAKE, SHAKE ACK | the sender's 0xd0-byte info block (name, appearance, level, data size, game options, button configuration, chunk size) |
| 2, 3 | SIZE, SIZE ACK | byte count of the character data to follow |
| 4, 5 | DATA, DATA ACK | (16-bit checksum << 16) \| sequence; payload = chunk |
| 6, 7 | KEEP ALIVE, KEEP ALIVE ACK | 7 carries the number of other players the sender sees as ready |
| 8 | HOST FORCE LAUNCH | bit mask of players to keep |

Per remote player there is a 0x144-byte record in `g_launchRecs` with a state byte at +0x5c:
0 contacting, 1 or 5 contacted (who sends first depends on index order), 2 size sent, 3
sending a chunk, 4 waiting for its acknowledgement, 6 receiving, 7 then 8 done. Known
fields: +0x10 address block, +0x38 port, +0x3c bytes left, +0x40 player id, +0x48 last DATA
word, +0x4c last chunk size, +0x50 unanswered count, +0x58 time of last change, +0x5d flag
bits, +0x60 transfer cursor, +0x64 contacted, +0x68 info block, +0x138 sequence, +0x13c /
+0x140 bytes done / total. The rest of the record was not mapped.

If a packet arrives from this machine's own external address the peer is re-addressed to its
internal address and port 4000 (two consoles behind one router, 0x135974–0x1359f4). What is
transferred is each player's character: the full 0x4c30-byte player structure or a 0x2c-byte
summary, depending on mode bits in 0x402a30.

When every other player is in state 8 and has confirmed, a 120-frame countdown runs and the
function finishes (0x136ffc onward): closes the launch socket, compacts the player list to
the kept mask, installs every player's button configuration into the per-slot tables
0x41b980…0x41ba30, sets difficulty and versus flags, clears the save buffer, writes address,
port and local flag of each peer, sets `g_numPeers`, sets +0x44c0 = 1 for all peers, and
opens the game socket on this machine's port. The front end then sets `g_networkMode`,
calls `game_resetState` and `net_startSync`, which zeroes the shared seed. The host can
force a launch with only the ready players (button 0x40 and a confirmation), any player can
cancel (button 0x20). A launch with somebody uncontacted for 2700 frames fails.

There is no code that adds a peer after this point (*Observed*: `g_numPeers` is written
only by the launch, the developer lobby and shutdown).

### Level change

Message 3/7 or 3/11 sets the pending level name on every machine in the same tick; ticks
then do nothing. The main loop calls `net_flushBeforeLoad`, loads, calls `net_main(1,0)`,
`net_clearHeardFlags`, and then `net_main(1,1)` once per rendered frame until
`net_allPeersHeard` or the stall counter limit. The silence counters keep running during
that wait, so a machine that loads more than about 900 rendered frames slower than another
is kicked by it. *Inferred* from the counters; not seen.

### Drop

- **Leaving on purpose.** The leaving machine sends 3/6 every frame of its exit countdown
  and then turns network mode off. The others mark it dropped in the tick that carries the
  first of those messages.
- **Silence.** A remote peer's counter +0x44cc passes 900: kick state 1, drop frame −1,
  negotiation state 0x5d1450 = 1 (0x133060–0x1330a8).
- **Manual kick.** `net_kickPeer` 0x131cb8 does the same and also starts the kicked notice.
- **Negotiation.** While state 1, every 30 rendered frames a kick request goes to every
  active peer that has not answered. A machine receiving a request marks the named peers as
  being kicked too and answers with a raw relay of each named peer's last 41 frames. A raw
  relay both fills in frames the requester was missing and counts as the answer. When all
  have answered, the drop frame of every kicked peer becomes newest received frame + 1 and
  the state goes to 2, then 0 (0x133278–0x133340). A machine answers only for a named peer
  that is not local and that it has not already dropped (byte tests at 0x13c2e4 and
  0x13c2f0). So a request that arrives after the answering machine has executed the drop is
  never answered: the requester stays in the negotiation, never gets a drop frame and never
  drops the peer; its simulation stops at the drop frame and the first machine stalls
  behind it once it has used up the requester's input. Both keep exchanging packets, so
  neither times the other out (**Executed** with three interpreter instances; in model runs
  with random counter phases 7 of 160 kicks ended this way, `docs/spec/net-wire.md` 12.3;
  FINDINGS L7).
- **Execution.** When `g_netFrame` equals the drop frame the peer is marked dropped
  (0x13420c–0x134298) and, in that tick, its character is killed. The first active machine
  also sends 3/4.
- `net_fewerThanTwoActive`, `net_endIfAlone`, `net_dropAllRemotes` handle being the last
  one left. **Ran** (one machine alone in a net game, `docs/issues/live-rig.md` 4d): the
  game ended itself about 100 frames after the level started, and not through
  `net_endIfAlone` — that function was never entered and patching it changed nothing, which
  agrees with its symbol note ("no callers"). The game stayed up only once
  `net_fewerThanTwoActive` 0x13dd88 was made to answer "no"; which of its four callers
  (0x1db904, 0x1dbe9c, 0x1e3e10, 0x1e74c4) ends the game was not determined.

## Per-machine state

Places in this range where shared state is, or could be, influenced by something that
differs between machines.

| # | What | Kind | Where |
|---|---|---|---|
| 1 | **L1/R1 pressure bytes are not on the wire.** A received record's bytes +0xa/+0xb are whatever was on the receiver's stack (the decoder writes only buttons, four sticks and yaw into the 12-byte scratch records, which are then copied whole into the ring); the owner's own record keeps the real pad bytes. `pad_apply` turns them into lockstep pad +0x38 and +0x50, which therefore differ between machines. | Observed | store 0x13be2c–0x13be34; local path 0x13a29c–0x13ac84; `pad_apply` 0x174410 |
| 1a | The only reader of those two pad fields found, 0x174d80 (`pad_buttonValue`), returns 0 or 1 from the button bits in a net game, so today this does not reach the simulation. No exhaustive search for other readers was made. A search has been made since (FINDINGS L16): no other reader among the functions that touch the pad array or read the stick fields through the same pointer. That the two fields differ on every machine in every frame is **Executed** (`docs/spec/net-wire.md` section 14) | Inferred harmless ("no other reader" rests on a search, not on a proof) | 0x174d80 |
| 2 | **The active mask gates all input.** A packet is discarded unless the sender's set of "not dropped, not kicked, not out of sync" peers equals the receiver's. Dropped and out-of-sync bytes change at a simulation frame or on receipt of a hash, i.e. at different real times on different machines. If machine A passes the frame that drops a third player before machine B has received A's input for that frame, B can never accept it afterwards and both wait until the 900-call timeout kicks the other. Needs own lead ≥ send cycle to be safe; three- and four-player games only. | Observed rule, Inferred consequence | 0x13b6ec; `net_disconnectPlayer` 0x13de68; flags 0x13b0ac, 0x13bf30 |
| 3 | **Raw local pad edges inside the tick.** `net_frameLoop` leaves the pressed-edge words of all four raw pads (`g_rawPads` +0xc, +0x10) live for the first tick of a call, zeroes them for later ticks and restores them at the end. Run tasks that read the raw pads therefore act on a frame that depends on this machine's timing; what they do must go through a game message. | Observed | save 0x139f3c, clear 0x13b140, restore 0x13b184 |
| 4 | **Message handlers run between pad updates.** Peer i's messages are executed before the pads and yaw of peers above i are set for the frame. At that moment the local slot's lockstep pad still holds the raw local pad (copied at the end of `net_main`) and `g_netCamYaw[local]` the predicted yaw; other machines see last frame's lockstep values there. A handler that reads another slot's pad or yaw would diverge. None was identified here; handlers were not audited for it. One handler that reads a pad has been identified since (`docs/issues/draw-sim-leaks.md`): `inventory_unequipItem` (inventory message 2) passes the message slot's lockstep pad to `Player_weaponSwapInput` (pointer formed at 0x1c2ffc). It is the sender's own slot, whose pad has already been applied for the frame, so the read is consistent; no handler reading *another* slot's pad is known | Observed order; impact: none found (one consistent pad read) | 0x13ac84 → 0x13ad24; 0x134454; 0x132b5c, 0x132b80; 0x1c2ffc |
| 5 | `g_simFrame` (0x44fdcc) outside the tick is the prediction frame, which runs ahead of `g_netFrame` by this machine's lead. Draw-phase code that uses it to change shared state is per machine (compare D12). | Observed | 0x13af98, 0x13b28c, 0x132c94 |
| 6 | `net_objOrGhost` 0x13e180 returns the ghost on its owner's machine and the real player elsewhere. 17 call sites, 16 of them in simulation code (two in `Creature_run`, fourteen in skill code) and one, 0x1e4c1c, in `minimap_draw` 0x1e42e0, which is draw code — the earlier version counted it as simulation code. Read: the two in `Creature_run` (0x113284, 0x113550) gate particle emitters that only write the cosmetic seed; 0x2c88e4 and 0x2c8fe0 mirror a field write (+0x58c) onto the ghost; 0x2dee18, 0x2e1144 and 0x2e1214 take a position from the result while the same function draws from the spell's own generator. Not classified here: 0x1e4c1c (fills the list of objects the minimap draws as blips), 0x2d1b04, 0x2e7cf8, 0x2e95cc, 0x2fb4c8, 0x2feed8, 0x2ffbd0, 0x302650, 0x303454, 0x3036e4. All 17 are classified in `docs/issues/prediction-copy.md` section 3.3: apart from 0x2d1b04 (`SpellCyclone_run`, FINDINGS G22) and a contained BloodLust case none can change shared state (G23). | Observed accessor, call sites partly checked | 0x13e180 |
| 7 | Ghost rebase between ticks: deletes and clones an object, restoring only the shared seed; sets flag 0x200000 on the real local player and moves flag 0x100 to the ghost, so the real player's flag word differs per machine (G1, D13). The two flags are **Ran** on the live game: the real player's flag word read 0x00204060 and the copy's 0x00024060 (`docs/issues/live-rig.md` 4d) | Observed; the two flags Ran | 0x13b1c8–0x13b5b0, 0x13af18–0x13af34 |
| 8 | The drop frame of a silent peer comes from per-machine counters and is made equal by the raw-relay exchange. It works if no machine is more than 40 frames behind another in what it holds from the kicked peer; the 38-frame input cap is what keeps that true. | Inferred consistent | 0x133060, 0x13c370, 0x133554 |
| 9 | Message bytes per frame are counted in one byte on the wire. More than 255 bytes queued by one machine between two send turns would be executed in full locally and mis-parsed remotely. The mis-parse is **Executed** now (the receiver walks out of the datagram, `docs/spec/net-wire.md` 7.5). The window is per input frame, not per send turn: the count grows with every attach to the same frame, and at two input frames per call (half display rate) the call without a send and the next call both attach to one frame, so their bytes add up (`docs/spec/net-wire.md` section 10). The game also adds its own 4-byte "player left" message inside `net_main` on top of whatever is queued. | Observed encoding, Executed mis-parse, Inferred risk in play (needs e.g. two long text lines at once) | count byte 0x1392c4–0x1392c8, copy loop 0x139300–0x139304 |
| 10 | Message 3/5 carries a heap object address; it is only right on other machines if their heaps match. The ghost is a per-machine allocation. (Message 7/0 carries an address inside a static table, which is the same everywhere.) | Observed, impact Unknown | senders 0x1de1a0, 0x1c5f78 (outside the range) |
| 11 | The decoded stick byte depends on single-precision arithmetic and truncation. Identical on identical hardware; emulator instances with different floating-point settings could disagree in the input itself. | Inferred | 0x13cdb0–0x13cddc |
| 12 | Game messages are sent from draw tasks and from local conditions (pad, menus, audio position). That is the intended funnel, but the frame they land on is per machine, and `net_sendGameMsg` acts at once offline and `lead` frames later online. | Observed | 0x13db78 |
| 13 | `g_inSimTick` is set only around step 3 and 4 of the tick, not while message handlers run. | Observed | 0x13ae30, 0x13af40 |
| 14 | The sync hash covers the shared seed and player positions only, and a lost sync record is not resent, so other divergence is reported late or never. | Observed | 0x13af44–0x13b048 |

The input lock (`net_lockLocalInput`, `net_maskLocalButtons`) is applied only on the machine
that owns the slot and before the sample becomes a record, so it is not a hazard even though
it is timed in calls.

## Corrections to earlier notes

- names.tsv `net_frameLoop2` 0x13b5d0 is the packet receiver, not a loop.
- names.tsv `g_netGameConn` 0x86ac40 is the game-message id 3, and the first argument of
  `net_sendGameMsg` is a message id, not a connection.
- names.tsv `g_netAckFrame` 0x4027d4 is the frame of the last ghost rebase; the tick does
  not stall on it.
- names.tsv `g_syncAcc` 0x4027c0 is always 0.
- names.tsv `net_launchTransfer` 0x134c60 only prepares; the SHAKE/SIZE/DATA exchange is in
  0x135638.
- FINDINGS L1 and L3: gameplay traffic is the game's own datagrams, see Summary. The answer
  to L3 is no.

## Open questions

- Whether the mask deadlock (row 2) happens in practice. Test: three machines, one leaves
  from the menu while the others are in a busy scene; watch for both remaining machines
  freezing and dropping each other about 15 s later.
- The lag figures: measure lead (`g_localInputFrame − g_netFrame`) over time on two
  machines after dropping packets for 0.1 s, 0.5 s and 2 s.
- Whether any simulation code besides 0x174d80 reads lockstep pad +0x38 or +0x50. Answered
  as far as a search can: 0x174d80 (`pad_buttonValue`) uses the button bits in a net game,
  and no other reader was found (FINDINGS L16, `docs/spec/net-wire.md` section 14).
- The ten call sites of `net_objOrGhost` listed as not classified, and whether the number
  of generator draws in 0x2dedec and 0x2e0d10 can depend on the ghost's position.
- Whether heap addresses agree between machines when message 3/5 is sent.
- Peer bytes +0x08…+0x0f; the unmapped parts of the launch record; the exact meaning of the
  mode bits in 0x402a30 (set by lobby code).
- `scr_findInTable38`: what the table at script header +0x38 holds.

Not done: `net_launchUpdate` and `net_launchDraw` were read for structure, not line by
line; the message handlers outside the range were skimmed only; `net_loadModules` was read
only far enough to name it.
