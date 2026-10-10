# net-wire — the peer-to-peer wire format, written for an implementer

What a program has to send, accept and remember to take part in a lockstep session of
Champions: Return to Arms (SLUS_209.73, v2.00), or to read and write one.

- `tools/ref_netwire.py` — the reference model (Python 3, standard library only).
- `tools/difftest_netwire.py` — runs the game's own packet builder, receiver, `net_main`
  and tick in `tools/ee_emu.py` and compares them with the model (section 18).
- `tools/test_ref_netwire.py` — unit tests of the model that need no game file.

Evidence labels: **Observed** = read in the executable at the address given; **Executed** =
the original code was run in the interpreter and its output compared with the model, byte
for byte, for the inputs section 18 lists ("executed in isolation" in the sense of
`docs/issues/dynamic-tests.md`: the game's instructions on a state the test built, no
console, no timing); **Model** = a number produced by the model alone; **Inferred**;
**Unknown**. Nothing here was seen on a console or between two real machines.

All multi-byte fields are little endian. Frame numbers are 32-bit and start at 1.

## 1. Transport

One UDP socket per machine (`g_netSocket` 0x4027c8, opened at the end of the launch on the
machine's own port; `docs/netcode.md`). Every datagram starts with a 32-bit type word.
`net_pumpReceive` 0x13c078 reads datagrams into a 0x7c0-byte (1984) buffer until the
receive call returns −500 and dispatches on that word. **Observed.**

- The source address and port of a datagram are never looked at (the two output arguments
  of the receive call are not read again). Who sent an input packet is decided by a
  nibble inside it. **Observed** 0x13c110–0x13c3f4.
- A datagram longer than 1984 bytes cannot be received whole. What the network library
  does with one is **Unknown**. The sender does not limit what it builds (section 7.5).

| Type word | Name | Length | Sent by | Section |
|---|---|---|---|---|
| 0xbd3f | input packet | variable | `net_main`, one peer per send turn | 7–9 |
| 0xbd40 | (not a type: marks a sync record inside 0xbd3f / 0xbd42) | | | 7.3 |
| 0xbd41 | kick request | 12 | `net_main` while a kick is being negotiated | 12 |
| 0xbd42 | raw relay | variable | answer to a kick request | 12 |
| 0xbd43 | kicked notice | 4 | `net_main` after a manual kick | 12 |
| 0xbd44–0xbd47 | direct message, handler index = type − 0xbd44 | 4 + n | `net_sendMsgToPeers` 0x131b00 | 13 |
| 0xbd3d, 0xbd3e | developer LAN lobby announce / start | 4 | 0x1345c0, only with flag 0x402792 | 13 |

Any other type word is ignored (**Executed** for 0xbd3d, 0xbd40 and 0xbd48).

## 2. What a machine keeps

Per peer — one entry of `g_peers` 0x5bf838, 0x44e0 bytes; the local machine has an entry
too. Offsets as in `docs/netcode.md`; `Peer.pack()` in the model produces this image and
the differential test compares all of it.

| Offset | Field (model name) | Used for |
|---|---|---|
| +0x00, +0x04 | address bytes, port | destination of everything sent to this peer |
| +0x10 | `recv_state`, codec state | decoder state **after the newest frame received** from this peer |
| +0x5c | `send_frame` | frame up to which `send_state` has been advanced |
| +0x60 | `send_state`, codec state | encoder state **just before frame `acked`** |
| +0xac | `ring`, 256 input records | this peer's input, index = frame & 0xff. In the local entry: this machine's own samples |
| +0x18ac | `sync_ring`, 256 × {frame, saved counter, hash} | sync records received from this peer; in the local entry this machine's own |
| +0x24ac | `msg_ring`, 0x2000 bytes | game-message bytes of this peer (local entry: queued by this machine) |
| +0x44ac | `msg_write` | write position in `msg_ring` |
| +0x44b4 | `pad_prev` | two words `pad_apply` keeps for this slot's lockstep pad |
| +0x44bc | `newest` | newest frame held from this peer |
| +0x44c0 | `acked` | newest of our frames this peer has acknowledged; **1 at the start** |
| +0x44c4, +0x44c8 | `lead`, `sim` | what the peer's last accepted packet said about its pacing |
| +0x44cc, +0x44d0 | `silence`, `heard` | calls since an accepted packet; set by every accepted packet |
| +0x44d4…+0x44d7 | `local`, `dropped`, `kick`, `oos` | one byte each |
| +0x44d8 | `drop_frame` | −1 while a kick is negotiated, then the frame at which the peer is dropped |
| +0x44dc | `kicked_notice` | counter of the 0xbd43 notices still to send |

Globals an implementation needs an equivalent of: next input frame `g_localInputFrame`
0x4027a4 (`lif`), simulation frame `g_netFrame` 0x4027ac (`net_frame`), the frame whose
sync record was last sent 0x4027cc, the value of `lif` at the last send 0x4027a8, the
message-ring position up to which bytes have been attached 0x5d14d8, the kick negotiation
state 0x5d1450 with four answer flags 0x5d1454, and two more codec states for the local
player's own input (section 14).

**Input record**, 24 bytes: +0 u32 frame number; +4…+0xf the 12-byte **wire record**; +0x10
u32 start and +0x14 u32 count of this frame's game-message bytes in the owner's
`msg_ring`. Wire record: u16 buttons, stick bytes of record +6, +7, +8, +9, two pressure
bytes (+0xa, +0xb), u32 = sign-extended 16-bit camera yaw with bit 0 replaced by the
camera flag. Only the wire record, minus the two pressure bytes, is ever transmitted in
an input packet.

**Codec state**, 0x4c bytes: four channels of 16 bytes at +0x00 (record byte +8), +0x10
(+9), +0x20 (+6), +0x30 (+7), each {s32 step index, s32 predictor, float value, float
velocity}; +0x40 s16 previous raw yaw (encoder only); +0x42 s16 predicted yaw; +0x44 s16
yaw delta; +0x48 s32 frames coded (incremented, never read). Reset: index 0, predictor 0,
value 128.0, velocity 0, yaw fields 0.

**Start of a session** (Observed 0x1393f8, 0x13768c, 0x139804–0x139828, 0x13dce0): the
peer table is zero except both codec states of every peer in reset state and `acked` = 1;
`lif` = `net_frame` = 1; `net_startSync` copies `net_frame` into 0x4027cc (so no sync
record is sent for frame 1) and zeroes the shared seed. Frame 0 is a record of zeros that
is never sent. The first time a peer is served the sender's persistent encoder state is
advanced over that zero record (section 8); from the reset state this changes nothing but
the frame counter, which is why sender and receiver start in step.

## 3. The bit stream

An array of 16-bit little-endian words. Bit position p is in word p >> 4; fields are
written most significant bit first, so the first bit of a word is its 0x8000 bit, and that
bit is in the word's **second** byte. A write ORs into the current word and assigns the
next one (the spill or zero), so one word beyond the last one used is always written.
Every read loads two consecutive words. **Executed** (`BitWriter`, `BitReader`).

## 4. A run of n frames

Used unchanged by input packets (n = byte 10 of the header), by the sender's catch-up
passes and by the local round trip (n = 1). In this order:

1. **16 bits**: the first frame's button word.
2. **Button runs.** A 5-bit run length says how many consecutive frames (starting with
   the first) carry the current word. After a run shorter than 31, unless the frames are
   used up, a 4-bit number names one bit of the word; that bit is toggled and the next run
   follows. A run of 31 is followed directly by another run. A change of several bits is
   sent lowest bit first, with a zero-length run before each further bit. A final run of
   length 0 is not written.
3. **Four stick channels**, in the order record bytes +6, +7, +8, +9 (section 5).
4. **Yaw** (section 6).
5. **Yaw flag**: 1 bit, the first frame's flag; then 5-bit run lengths of frames with the
   current flag. After a run shorter than 31 (frames not used up) the flag toggles. A
   toggle after exactly 31 equal frames is a 31 followed by a 0.
6. **16 bits 0xa5a5.** The receiver skips them without looking.

The stream is self-delimiting given n; `read_frames()` parses one without any state.
**Executed** for 1 ≤ n ≤ 255, runs of exactly 31 and 62, and every bit of the button word.

## 5. One stick channel

### 5.1 Sender: sample → (move, direction)

State: step index 0…8 and predictor 0…255. Steps: 4, 6, 8, 12, 16, 24, 32, 48, 64 (data
0x402860). Per sample (0x13c450, first loop):

```
q = (sample - predictor) / step[index]      truncated toward zero
move = 1 if q != 0 else 0;  direction = 1 if q < 0 else 0
predictor += step[index] if q > 0, -= step[index] if q < 0;  clamped to 0..255
index = index + 2 if move else index - 1;   clamped to 0..8
```

### 5.2 Bits of one channel for n samples

**Move bits.** Two modes, starting in count mode:

- *count mode*: a 5-bit number z = how many samples from here have move = 0. z = 31 means
  "31 zeros, stay in count mode". z < 31 means "z zeros, then a 1" — unless the z zeros
  reach the end of the samples, in which case nothing is implied — and switches to
  literal mode. A pending count of 0 at the end of the samples is not written.
- *literal mode*: five move bits written as they are. If any of the five was 1, another
  five follow; if none was, back to count mode. A group cut short by the end of the
  samples is simply shorter.

**Direction bits**, only if at least one sample moved: 1 bit = direction of the first
move; then 3-bit run lengths counting moves (not samples) that have the current direction.
A run shorter than 7 is followed by a change of direction; 7 means "seven more, direction
unchanged". A pending run of 0 at the end is not written; a change right after exactly
seven is a 7 followed by a 0.

### 5.3 Receiver: (move, direction) → stick byte

Per sample (0x13c970 from 0x13ccb8): the same predictor and index update as the sender
(with both clamps), then the spring, ten times, **in this order** (0x13cdb0–0x13cdd8):

```
value    = value + velocity
velocity = (velocity + (predictor - value) * G) * D
```

G is the single 0x3d4ccccc (just under 0.05); D = 1.0 − sqrt(0x3e4ccccc), computed at run
time, 0x3f0d8369 in the interpreter. The stick byte is the last `value` converted to an
integer toward zero and clamped to 0…255. `value` and `velocity` persist from frame to
frame; they are part of the state a receiver must carry, to the bit.

A packet repeats frames the receiver already holds. The decoder is told how many leading
frames to skip: it reads their bits but applies only the rest, so its state always
corresponds to the newest frame it has stored.

### 5.4 Reproducing the float arithmetic, and the uncertain bit

The model does the spring in integer arithmetic on the 32-bit patterns (`Fpu`), with the
console's rules as `tools/ee_emu.py` states them: no NaN, infinity or denormal; products
and square roots exact and then truncated; sums truncated. **Executed**: under each of the
interpreter's six floating-point settings (four adder models, multiplier bias, square root
rounded to nearest) the model's stick bytes, `value` and `velocity` equal the original's
bit for bit (section 18).

What is **not** established is which adder a console has. The four choices give different
stick bytes (**Model**, 20,000 frames of one channel with mixed input): the default `ps2`
(smaller operand aligned with six extra bits, the rest floored), `ps2g1` and IEEE
round-to-nearest agree on all but 1 frame; plain truncation of the exact sum (`chop`)
differs from them on 11.4 % of frames, always by one count. The cases are values that
come to rest on an integer and then have a tiny negative velocity added
(`docs/issues/dynamic-tests.md` 3.9). An implementation that must agree with real consoles
therefore needs one fact this repository does not have: the last bit of a single-precision
sum on hardware. An implementation that only talks to other copies of itself can use any
of them, as long as every participant uses the same one. `pad_apply` (section 14) was
compared under the same six settings and the model equals the original under each;
whether its output differs *between* settings was measured by `tools/ee_tests.py` (b12: it
did not, on 86 stick positions), not here.

## 6. Yaw

Sender state: previous raw value, predicted value, delta (all s16). Per frame, with `raw`
= the record's yaw word with bit 0 cleared (inlined, e.g. after 0x138cd0):

```
change = raw - previous;   previous = raw;   error = raw - predicted
if |change| > 1000 or |error| > 3000:
    ABSOLUTE:  predicted = raw                       (delta is left as it is)
else:
    want = change;  if |error| > 200:  want += error / 15      (truncated)
    if |want - delta| < 31 and delta * change >= 0:
        KEEP:  predicted += delta
    else:
        NEW:   delta = clamp(want, -255, 255);  predicted += delta
```

Bits: 5-bit run lengths of KEEP frames. After a run shorter than 31 (frames not used up)
one bit and a value: 1 + 9-bit two's-complement delta (NEW), or 0 + 16 bits of `raw`
(ABSOLUTE). 31 means "31 kept, another run follows". A pending run of 0 at the end is not
written.

The receiver keeps predicted and delta and does the same three updates. **The yaw it
stores for a frame is `predicted`, not the sender's raw value**: the coding is lossy by
design (a camera turning at a steady rate is sent as nothing at all), and the owner of
the input uses the same lossy value (section 14). The stored word is `predicted`
sign-extended to 32 bits with the frame's flag in bit 0. **Executed.**

## 7. Input packet (0xbd3f)

### 7.1 Header, 12 bytes (0x137e1c–0x137f0c)

| Offset | Type | Field |
|---|---|---|
| 0 | u32 | 0xbd3f |
| 4 | u32 | `last`: number of the last frame in the packet |
| 8 | u8 | low nibble: slot whose frames these are (the sender's); high nibble: the sender's **active mask** — bit i set when peer i is not dropped, not being kicked and not out of sync on the sender, the sender's own bit included |
| 9 | u8 | `last` − sender's `net_frame`, low 8 bits |
| 10 | u8 | n, number of frames; the first frame is `last` − n + 1 |
| 11 | s8 | acknowledgement: newest frame the sender holds **from the addressee**, minus `last` |

### 7.2 Frames

From offset 12: the bit stream of section 4. Its length in bytes is (bits + 7) >> 3.

### 7.3 Sync word

At the next offset that is a multiple of 4 (counted from the start of the datagram):
either u32 0xbd40 followed by a 12-byte sync record {u32 frame, u32, u32 hash}, or one
other u32 (the game writes 0xffffffff) meaning "no record". The receiver compares only
with 0xbd40 and skips 4 bytes otherwise.

The bytes between the end of the stream and the sync word are padding. The sender stores
16-bit words up to one word beyond the last bit of the stream and nothing after that, so
in about half of all packets the two bytes just before the sync word are whatever its
stack held. **Executed**: 590 of the 1,200 packets built in the function-level test have
two such bytes; wherever they could be checked they still held the marker the test had
filled the stack with. A receiver must ignore them, a sender may write anything.

### 7.4 Message blocks

From there to the end of the datagram, zero or more blocks {u8 `last` − frame, u8 byte
count, bytes}: the game-message bytes attached to that frame (section 10). Ascending
frame order. The receiver walks blocks until its pointer **equals** the end of the
datagram; it has no other stop condition.

### 7.5 Sizes

- n ≤ 255 by the header byte. In play n is the sender's unacknowledged backlog, bounded by
  the pacing cap (39 frames ahead of the slowest reported simulation frame,
  `docs/issues/lag.md`); the sessions run here saw up to 39.
- One frame's message bytes are counted in **one byte**. The sender writes the low byte of
  its 32-bit count and then copies the full count of bytes (0x1392c4–0x139310), so more
  than 255 bytes on one frame produce a packet the receiver mis-parses. **Executed**
  (property "messages over 255 bytes"): with 304 bytes on a frame the original builder
  wrote the count 0x30 and all 304 bytes; the original receiver took 48 of them, read the
  rest as further blocks, missed the end of the datagram and walked on through memory,
  copying what it found into the peer's message ring, until the interpreter stopped it at
  unmapped memory. On a console there is more memory to walk through; where that ends
  was not determined. The model refuses to parse such a packet.
- The builder assembles the datagram in its stack frame without any length check. There
  are 5008 bytes between the start of the datagram ($fp+0x10) and the builder's own copy
  of the codec state ($fp+0x13a0). **Observed** 0x137d9c, 0x137ed8; **Executed** up to
  3,572 bytes; found because a 255-frame, message-heavy random packet (8 kB) overran it
  in the interpreter. With the pacing cap in force a frame backlog cannot get there by itself;
  about twenty frames each carrying 250 message bytes could. **Inferred**: not reachable
  in ordinary play, where messages are a few bytes.
- The receive buffer is 1984 bytes. A sender that wants to be understood keeps its
  datagrams within that.

## 8. Sending — acknowledgement and repeat rules

Once per rendered frame `net_main` 0x132e90 serves the peers whose turn it is (the send
rotation, `docs/issues/lag.md` 2.2 step 8; one peer every second call with one to three
remote peers). Peers with `local`, `dropped` or `kick` set are not served; a peer that is
only out of sync still is. For the peer served (0x13385c–0x1341c0, **Executed**):

1. If `acked` > `send_frame`: run the frame encoder of section 4 over the local records
   `send_frame` … `acked` − 1 with the **persistent** `send_state`, throw the bits away,
   set `send_frame` = `acked`. The persistent state is now the encoder state just before
   frame `acked`.
2. Build a packet with first frame = `acked`, `last` = `lif` − 1, encoding from a **copy**
   of `send_state`.
3. Set 0x4027a8 = `lif`.

So:

- **Everything is repeated until acknowledged.** A packet always starts at the frame the
  addressee last acknowledged — note: *at* it, not after it, so the newest acknowledged
  frame is sent once more every time — and ends at the newest sampled frame. There is no
  timer and no retransmission as such; a lost packet is covered by the next one.
- **The acknowledgement** rides in byte 11 of every input packet: `newest` (of the
  addressee's frames) − `last`. It wraps at ±128; with a backlog over 127 frames it would
  be wrong (not reachable under the pacing cap).
- A packet is sent every turn whether or not there is anything new.
- **Sync record**: the first packet built after `net_frame` changed carries the local sync
  record for the current `net_frame`; every other packet carries "no record". One record
  per simulation frame for the whole machine, whichever peer's turn it is — with more
  than one remote peer each record reaches only one of them — and never repeated.
  (0x1391bc–0x139258.)
- **Message blocks**: for every frame in the packet whose record has a non-zero message
  count, in every packet that contains the frame, until it is acknowledged.

Byte 9 is computed from `net_frame` as it is when the packet is built, which is before
this call's ticks.

## 9. Receiving — exactly when a packet, or part of it, is ignored

The receiver 0x13b5d0 (**Executed**; conditions in the order the code tests them,
0x13b6ec–0x13b804):

| # | Condition | Effect |
|---|---|---|
| 1 | high nibble of byte 8 ≠ this machine's own active mask | whole packet ignored |
| 2 | slot (low nibble) is this machine's own, or that peer is `dropped` | whole packet ignored |
| 3 | that peer is being kicked (`kick` ≠ 0) and the packet is not a raw relay | whole packet ignored |
| 4 | that peer is `oos` | whole packet ignored |
| — | otherwise | `silence` = 0, `heard` = 1; `sim` = `last` − byte 9; `lead` = `last` − `sim` |
| 5 | `last` ≤ `newest` | nothing else is read: no acknowledgement, no frames, no sync record, no messages |
| — | otherwise | `acked` = max(`acked`, `last` + byte 11) |
| 6 | first frame > `newest` + 1 (a gap) | nothing else is read; the acknowledgement of this packet has been taken |
| — | otherwise | decode with skip = `newest` − first + 1; store frames `newest` + 1 … `last` with message count 0; `newest` = `last` |
| 7 | sync word = 0xbd40 | the record is stored at index (its frame & 0xff) of the peer's sync ring and compared (section 11) |
| 8 | each message block | copied to the peer's `msg_ring` and attached to ring slot (`last` − offset) & 0xff **only if that slot's count is still 0**; otherwise skipped |

Consequences worth spelling out:

- Row 1 makes the active mask a precondition for all input. Two machines that disagree
  about who is dropped, kicked or out of sync cannot exchange anything, in either
  direction, until they agree again.
- Row 5: a machine that is not sampling (held by the pacing rules) still sends, but its
  packets bring no new frame, so its acknowledgements and sync records are not taken
  (`docs/issues/lag.md` C2). **Executed.**
- Row 6 cannot happen between two correct implementations — a sender starts at a frame
  the receiver once reported — but the acknowledgement is taken before the test.
- Row 8: a frame's messages are accepted from the first packet that carries the frame and
  a block for it; a block arriving for a frame already stored is accepted only if the
  frame had none. A sender must therefore attach bytes only to a frame it has never sent
  (section 10).
- The two pressure bytes of a received frame are not written by the decoder; the receiver
  stores whatever its stack held (`docs/netcode.md`, per-machine row 1). **Executed**:
  after every packet that stored frames, those bytes held the stack marker.
- Duplicated and overtaken packets need no special handling: rows 5 and 6 and the skip
  count make reception idempotent. **Executed** in the sessions (section 18).

## 10. Game messages

- **Queue.** `net_sendGameMsg(id, bytes, n)` 0x13db38 appends {u8 id, u8 n, bytes} to the
  local `msg_ring` (wrapping at 0x2000). **Executed.**
- **Attach** (`net_main` 0x1336c4–0x13375c, **Executed**): if 0x4027a8 < `lif` − 1 and
  bytes have been queued since the last attach, all of them are added to one frame:
  max(0x4027a8 + 1, `net_frame`). If that record's count was 0 its start is set to the
  old attach position; the count grows by the number of new bytes. That frame has not
  been sent to anybody and has not been simulated. The condition is true only in a call
  where two sampled frames are unsent, i.e. normally the call after one without a send.
- **On the wire**: section 7.4. The block is the frame's whole byte string — several
  {id, n, bytes} messages back to back; the receiver does not look inside.
- **Execution** (tick, 0x13ac90–0x13ad54, **Executed** with stub handlers): when the
  simulation reaches the frame, for each peer in slot order, after that peer's pad has
  been applied: walk the frame's bytes as {id, n, payload} and call handler[id](payload,
  n) until the count is used up. The sender's own machine does the same from its own
  ring. The id is not range-checked against the 16-entry table, and a count that does not
  add up never terminates.
- **Limits**: 255 bytes per message (length byte); 255 bytes per frame on the wire
  (section 7.5), headers included. The budget is per **frame**, not per attach: with two
  input frames per call (half display rate) the call without a send and the next call
  both attach to the same frame, 0x4027a8 + 1, and their bytes add up. This is how the
  test first ran into the limit: a session with one machine at two steps per call and
  random messages of up to 255 bytes brought the original receiver down. The game itself
  has no guard (`net_sendGameMsg` and the attach code do not look at the count);
  whether its own message traffic can reach 256 bytes inside one such window — a long
  text line is the largest message known (`docs/netcode.md`) — is **Unknown**.

## 11. Sync record and hash

At the end of each tick, after `net_frame` has been incremented (0x13af44–0x13b01c,
**Executed** with ordinary values, edge patterns and random bit patterns):

```
record = { net_frame (the NEW value), g_simFrame as it was before the tick, hash }
hash   = g_syncAcc + g_randSeed
         + for every player slot that has an object: (int)x + (int)y + (int)z
```

modulo 2³², the conversions toward zero and saturating at ±2³¹. `g_syncAcc` 0x4027c0 is 0
in the shipped game. The record is stored in the local sync ring at index frame & 0xff
and travels as in section 8. The middle word is not compared by anybody.

Comparison happens twice, whichever side comes second (**Executed** both ways):

- when the tick stores its record: against the record of every peer that is not local and
  not dropped (0x13b048);
- when a record is received: against this machine's own record (0x13be68–0x13bf30).

In both cases only if the two ring entries carry the same non-zero frame number. Unequal
hashes set that peer's `oos` byte. From then on the peer is out of this machine's active
mask, so its packets are ignored (row 4) and — because the mask is in every packet this
machine sends — this machine's packets are ignored by everybody whose mask still
contains the peer.

**A single flag splits the session.** **Executed** (session "one machine diverges"): three
consoles, machine 1 corrupts its seed in one frame. Whichever machine compares first sets
a flag; that changes its active mask; from then on the machines on the other side of the
difference ignore its packets by rule 1 of section 9 — including the packets that carry the
sync records which would have made them set a flag of their own. In the run reported in
section 18 only machine 1 ever set a flag (for one of the two others). Two earlier runs
of the scenario, made while the test was being written and with other random message
traffic, ended differently: in one (three consoles) the two healthy machines flagged
machine 1 and it flagged one of them; in the other (the model alone) machine 1 flagged
both and they flagged nobody. In every run machines 0 and 2 kept accepting each other, never flagged each
other, and all three stalled within a few frames, the two healthy ones because they still
required input from a peer whose packets they no longer took. To them that peer is simply
silent: 900 calls later they started a kick (section 12), agreed on a drop frame and
continued as a two-player game. `docs/netcode.md` ("both sides flag each other and each
ends alone") describes one possible outcome, not the rule.

## 12. Dropping a peer: kick request, raw relay, kicked notice

### 12.1 Packets

**Kick request** 0xbd41, 12 bytes: {u32 type, u32 requester's slot, u32 mask of the peers
whose `kick` byte is 1 on the requester}. (0x133148–0x133234.)

**Raw relay** 0xbd42: the same layout as an input packet with three differences — byte 9
is the **relaying** machine's slot; the low nibble of byte 8 is the slot of the peer whose
frames are relayed; the frames are n 12-byte wire records verbatim (pressure bytes
included, whatever they are on the relayer) instead of a bit stream. n × 12 is a multiple
of 4, so there is no padding. Then the sync word — the relayer takes the 12-byte entry at
index `net_frame` & 0xff of the **relayed peer's** sync ring, under the same once-per-frame
rule as section 8, so sending a relay uses up the relayer's own sync record for that
frame — and the relayed peer's message blocks. **Executed** (builder with raw = 1).

**Kicked notice** 0xbd43: 4 bytes. On receipt sets flag 0x4027a0, which the HUD shows.

### 12.2 Procedure (**Executed** in four sessions)

1. A machine starts a kick of peer k when k's `silence` passes 900 calls, or on
   `net_kickPeer(k)` 0x131cb8: `kick` = 1, `drop_frame` = −1, negotiation state 1, the
   four answer flags cleared. A manual kick also starts twelve kicked notices to k, one
   every tenth call. From now on k's input packets are ignored (row 3).
2. While the state is 1, every time the rendered-frame counter 0x44fdd0 is a multiple of
   30: a kick request goes to every peer that is not local, not dropped, not being kicked
   and has not answered. If there was nobody left to ask, the drop frame of every peer
   being kicked becomes its `newest` + 1, their `kick` becomes 2 and the state returns
   to 0.
3. A machine that receives a request marks every peer in the mask that it was not already
   kicking (`kick` = 1, `drop_frame` = −1, state 1, answer flags cleared — so it now runs
   step 2 itself), and answers, for every peer in the mask that is **not local and not
   dropped** on it, with a raw relay of that peer's frames `newest` − 40 … `newest`
   (from 0 if that is negative) to the requester.
4. A raw relay is received like an input packet (it is accepted for a peer being kicked),
   so it fills in frames the requester lacked; and it sets the answer flag of the slot in
   byte 9.
5. When `net_frame` equals a kicked peer's drop frame, `net_main` marks it dropped; the
   tick of that frame kills its character; the first active machine announces it with
   game message 3/4.

The relays are what make the drop frame equal everywhere: after them every machine holds
the same newest frame of the kicked peer.

### 12.3 A request that comes too late is never answered

Step 3 answers only for a peer the answering machine has **not yet dropped** (the test at
0x13c2f0). If machine A finishes its negotiation and reaches the drop frame before
machine B's own request arrives, A sends nothing; B stays in state 1 for good, never
gets a drop frame, never drops the peer, and its simulation stops at the frame A dropped
it at; A runs on until it has used up B's input and stops too. Both keep exchanging
packets, so neither times the other out.

**Executed** (session "kick request too late"): three consoles whose rendered-frame
counters are in step and whose datagrams take one round; machine 0 kicks slot 2. Machine 0
asks machine 1, gets its relay, and 30 calls later sets the drop frame and — being
already stalled at that frame — drops the slot in the same call. Machine 1's own request
leaves in that same round, arrives one round later and is not answered. Machine 0 runs
on from frame 60 to frame 98, where it has used up machine 1's input, and stops; 250
calls later machine 1 is still at frame 60, still negotiating, and has sent eight
requests.
With the counters 15 apart (session "manual kick") machine 1's request arrives while
machine 0 is still negotiating, both drop the slot at the same frame and continue. When
a peer falls silent and the others time out within the same 30-call window, all of them
are negotiating before any request is sent, and it works (session "silent peer is
dropped", four consoles; also the two healthy machines of the divergence session).

How often the bad order occurs depends on the phase of the two rendered-frame counters,
on latency and on whether the first machine has to simulate a few more frames before it
reaches the drop frame. **Model** (the model alone, random counter phases, 40 runs each;
a run counts when a survivor had still not dropped the peer 150 rounds after a manual
kick or 200 after the silence counters were set near 900): 2 runs of a manual kick among
three players with datagrams under one round in flight, 3 with one to two rounds, 1 of a
manual kick among four, and 1 of a silent fourth player. Seven of 160 is a small sample;
"a few percent of kicks" is all it supports. What the stuck machines then do — the HUD's stall counters end the game after
about 1,800 calls according to `docs/netcode.md` — was not run.

An implementation that wants to interoperate should answer a kick request with a relay
even for a peer it has already dropped. That is a change of behaviour on the answering
side only and was not tried against the original.

## 13. Direct messages and the developer lobby

**Direct message** 0xbd44 + i (i = 0…3): {u32 type, payload}. `net_sendMsgToPeers(i, mask,
bytes, n)` 0x131b00 sends one datagram to every peer in the mask that is neither local
nor dropped, and calls its own handler i for the local slot. On receipt handler i gets
(payload, length − 4); an empty table entry drops the packet. Not synchronised, not
acknowledged, not repeated. The sender copies the payload into a 508-byte stack buffer
with no check. **Executed** up to 500 bytes. Only handler 0 is registered by the game
(voice, `docs/netcode.md`).

**0xbd3d / 0xbd3e**: 4-byte announce and start of the developer LAN lobby, sent to
192.168.1.255 port 4000 by 0x1345c0 when flag 0x402792 is set. **Observed** only.

## 14. From record to simulation input

Per tick, for every peer that is not dropped, in slot order (`net_frameLoop` 0x139e88,
**Executed** as a whole):

1. Take the peer's record for `net_frame`. **For the local slot, first pass it through the
   codec**: encode this one frame with `g_simEncState` 0x5bf798, decode it with
   `g_simDecState` 0x5bf7e8, and use the decoded buttons, sticks and yaw word (the two
   pressure bytes stay as sampled). This is what makes the owner of an input see the same
   smoothed sticks and predicted yaw as everybody else. An implementation needs this pair
   of states too, advanced once per simulated frame; a second pair serves prediction.
2. `pad_apply(lockstep pad of the slot, wire record, the peer's two previous-state
   words)`.
3. Store the low 16 bits of the yaw word in `g_netCamYaw[slot]` 0x5d0bc0.
4. Run the frame's game messages of this peer (section 10).

`pad_apply` 0x174410 (**Executed**, all 0x58 bytes):

| Pad offset | Value |
|---|---|
| +0x08 u32 | buttons; plus 0x800000 / 0x400000 when the first stick's x is above 0.8 / below −0.8, 0x200000 / 0x100000 for its y. While global 0x41bfc0 is non-zero, bit 0x800 is removed and the global counted down |
| +0x0c u32 | buttons & ~previous buttons |
| +0x10 u32 | the same; replaced by all held buttons on every 4th call once the same non-zero word has been held for more than 20 calls |
| +0x14, +0x18 | stick of record bytes +6, +7; +0x1c, +0x20: bytes +8, +9. Each pair: ((b − 128) / 128), radial dead zone 0.32, then × (1 − 0.32 / length) × 1.4705882 |
| +0x28, +0x2c, +0x30, +0x34 | 1.0 or 0.0 for buttons 0x2000, 0x8000, 0x1000, 0x4000 |
| +0x40, +0x44, +0x48, +0x4c | the same for 0x20, 0x80, 0x10, 0x40; +0x54 for 0x2; +0x3c = (float)(buttons & 1) |
| +0x38, +0x50 | pressure bytes +0xa, +0xb × (1/255) — **different on every machine** for a remote slot |
| +0x00…+0x07, +0x24 | not written |

When global 0x41c138 is non-zero the analog fields are zeroed and the three button words
masked with (0x41bfb8 | 0x41bfbc).

**Executed**: in every session all machines applied bit-identical lockstep pads to every
frame except for +0x38 and +0x50, which differed in every frame.

**Input delay.** In the call that stores a sample as frame F, the ready scan stops at
F − 1 (its limit is `lif` − `net_frame` − 1, taken after the sample is stored, 0x1342a8).
With L = `lif` − `net_frame` measured at that point — after the sample is stored, before
the tick — F is the L-th frame still to be simulated, so with one tick per call it is
simulated in call c + L − 1, and each call without a tick in between adds one. The rule in
`docs/issues/draw-sim-leaks.md` ("simulated in call c + L − 1", L ≥ 2) is **confirmed**
with that definition of L. `docs/issues/lag.md` measures its lead at the end of a call,
one lower when a tick ran, and says "L calls later"; the two statements agree.
**Executed** (property "input delay rule"): every frame of a two-console session obeyed
c + L − 1 + (calls without a tick). L was 1 only in each machine's very first call (frame
1, when no tick is possible) and at least 2 afterwards.

## 15. Launch handshake packets

The launch runs before the peer table exists, on its own socket (`docs/netcode.md`,
"Launch"). Packets: {u32 sender's player id, u32 type, u32 argument, payload}. All except
DATA are sent with a length of 0x200 bytes from a stack buffer that is not cleared, so
everything after the payload is undefined (**Executed** for the generic sender
0x13e2c8). A datagram shorter than 16 bytes is ignored; one whose id is not that of a
known remote player is ignored. **Observed** in `net_launchUpdate` 0x135638, which was
read, not run.

| Type | Name | Argument | Payload |
|---|---|---|---|
| 0 / 1 | SHAKE / SHAKE ACK | 1 echoes the argument of the 0 it answers | sender's 0xd0-byte info block |
| 2 / 3 | SIZE / SIZE ACK | byte count of the data to follow; 3 echoes it | — |
| 4 | DATA | checksum << 16 \| sequence number (16 bits) | the chunk; datagram length = 12 + chunk |
| 5 | DATA ACK | the DATA argument word, echoed | — |
| 6 / 7 | KEEP ALIVE / ACK | 7: number of other players the sender sees as finished | 7: info block |
| 8 | HOST FORCE LAUNCH | bit mask of the players kept | — |

DATA checksum (**Executed**, `net_launchSendData` 0x1354f8, chunks of 1–1300 bytes):
starting from 0x217, for byte i taken as signed: if i is even subtract
(byte & 0x8f37) × (i & 7), if odd add (byte × 3) xor 0x30e15f; in both cases add the
chunk's first byte; keep the low 16 bits. The receiver's loop uses the mask 0x148f37; the
extra bits cannot reach the low 16 bits, so the two agree. A DATA chunk shorter than 4
bytes makes a datagram shorter than 16 and would never be accepted; with the sizes in
`docs/netcode.md` (0x4c30 or 0x2c bytes in chunks of 1300 or 512) the last chunk is 4, 48
or 44 bytes. **Inferred** from those sizes.

The state machine around these packets is in `docs/netcode.md`; the model has the packet
builders, the parser and the checksum, not the state machine.

## 16. Checklist for an independent participant

1. Keep, per remote peer: decoder state, encoder state at the acknowledged frame, the
   peer's last 256 records, its sync records, its message bytes, `newest`, `acked`.
2. Sample one record per input frame; store it; never change a record after it has been
   sent, except to attach message bytes to a frame nobody has been sent.
3. Each send turn: advance the encoder state to `acked`, send `acked` … newest sample with
   the header of 7.1, the sync record if this simulation frame's has not gone out, and
   the message blocks. Keep datagrams under 1984 bytes and a frame's messages under 256.
4. On receipt apply section 9 literally, including the mask test.
5. Simulate frame f only when a record numbered f is held from every peer that is not
   dropped, yourself included; pass your own record through the local encode/decode
   first; apply `pad_apply` per slot in slot order; run messages; then your simulation.
6. Compute the hash of section 11 after each frame, store it, send it once, compare.
7. Implement section 12, or never start a kick and answer every request.
8. Use the same float rules as the other participants for the spring of 5.3.

## 17. Fields the original does not check

All **Observed**; none was provoked on the original (the model raises `MalformedPacket`
instead). They matter to anyone writing the other end, and to anyone exposing a console
or emulator to packets from strangers.

| Where | What is trusted |
|---|---|
| any datagram | the source address; anybody who can reach the port can send as any slot |
| byte 8, low nibble | used as an index into the four-entry peer table without a range test (0x13b6f8); slots 4–15 address memory after the table |
| byte 9 of a raw relay | index into the four answer flags, 0–255 (0x13b764–0x13b770) |
| requester slot of a kick request | index of the peer the relay is sent to |
| mask of a kick request | a bit for the receiving machine's own slot is taken like any other: it marks itself as being kicked (the loop at 0x13c250 has no test for the local entry) |
| run lengths in the stream | a run that overshoots n is not detected: the button and flag loops never terminate, the stick and yaw loops write past their scratch arrays |
| message blocks | the walk ends only when the pointer equals the end of the datagram |
| message id, message lengths | handler table index; the per-frame count must add up exactly |
| datagram length | never compared with what the header implies |

## 18. What the differential test covers

`python3 tools/difftest_netwire.py` — numbers from the default run (seed 20973); `--quick`
runs about a tenth. Every line is a comparison of the original, executed in the
interpreter, with the model.

| Property | Cases | Original code run | What must be equal |
|---|---|---|---|
| axis encode, six float settings | 2,750 calls, 138,968 samples | `netcodec_encodeAxis` 0x13c450 | stream words, bit position, step index, predictor; any start position in the stream, runs of 31 and of 7 |
| axis decode, six float settings | 2,750 calls | `netcodec_decodeAxis` 0x13c970 | stick bytes, bits consumed, index, predictor, `value` and `velocity` patterns; 0 to n − 1 samples skipped |
| fpu choices disagree | 20,000 frames | none (model only) | the four adder choices never differ by more than one count; how often they differ is reported |
| pad_apply, six float settings | 7,000 calls | `pad_apply` 0x174410 with `pad_decodeStick` 0x174ce0 | all 0x58 pad bytes, the previous-state block, the start-block counter; mute and start-block globals varied |
| build input packet | 1,200 packets, 59,384 frames | `net_sendInputPacket` 0x137d60 | every datagram byte the builder stores; 2–4 peers, any flags, 1–255 frames, frame numbers up to 2³¹, 615 with a sync record, 567 with message blocks, 598 through the builder's own catch-up pass, up to 3,572 bytes |
| build: call arguments | 1,200 | same | address block, port, 1000 ms timeout, 0x4027cc afterwards, peer table untouched |
| build: padding not stored | 305 | same | the bytes the model calls undefined still hold the stack marker (the 305 packets with such bytes and no catch-up pass) |
| build raw relay | 300 | same, raw = 1 | every byte of the 0xbd42 datagram |
| receive input packet | 3,262 packets | receiver 0x13b5d0 | the whole peer table (4 × 0x44e0 bytes) and the netcode globals after each packet. 2,197 brought new frames (28,527 stored), 559 nothing new, 97 started after a gap, 409 were ignored (other mask, own slot, dropped / kicked / out-of-sync sender); delivered in order, late and twice; sync records matching, differing and for other frames |
| receive: pressure bytes | 1,561 packets | same | bytes +0xa, +0xb of every newly stored frame hold the stack marker |
| session: 2 consoles | 1,400 calls, 700 datagrams, 691 frames | `net_main` 0x132e90 with everything it calls except the stubs listed below | every datagram; netcode state after every call; lockstep pads, kills and executed messages of every tick; no out-of-sync flag |
| input delay rule | 1,383 frames | same session | section 14 |
| session: 3 consoles, bad link | 1,398 calls, 699 datagrams | same | same; 10 % loss, 5 % duplicates, delay 1–9 calls |
| session: 4 consoles | 1,400 calls, 700 datagrams | same | same; 561 game messages of 0–238 bytes, up to 240 bytes on one frame |
| session: uneven machines | 1,243 calls, 622 datagrams | same | same; one machine at two input frames per call that misses every third call, held calls, no-simulation calls, input lock, a 35-round outage; packets of up to 37 frames |
| session: modem send cycle | 466 calls, 156 datagrams | same | same; send cycle 3 |
| session: model as a peer | 700 calls, 350 datagrams | same, on two consoles | same; the third participant is the model alone. The consoles simulated 341 frames with its input and their hashes kept matching its hashes |
| session: one machine diverges | 1,560 calls, 784 datagrams | same | same; plus the outcome described in section 11 |
| session: silent peer is dropped | 920 calls, 472 datagrams | same | same; plus: 6 kick requests, 6 raw relays, one drop frame on all three survivors, the dropped player killed in that tick, simulation continues |
| session: manual kick | 720 calls, 376 datagrams | same, and `net_kickPeer` 0x131cb8 | same; plus: 12 kicked notices, flag set on the kicked machine, both others drop at the same frame |
| session: kick request too late | 900 calls, 472 datagrams | same | same; plus the outcome described in section 12.3 |
| tick: sync hash and compare | 600 ticks | `net_frameLoop` 0x139e88 whole | sync record, out-of-sync bytes (set 171 times) and all other netcode state; positions from edge patterns, random bit patterns, ordinary values, empty slots |
| messages over 255 bytes | 1 | builder and receiver | section 7.5 |
| small packet types | 400 | `net_sendMsgToPeers` 0x131b00, `net_pumpReceive` 0x13c078 | direct-message datagrams and handler calls; 0xbd43; ignored types |
| launch DATA packet | 600 | `net_launchSendData` 0x1354f8 | datagram, length, returned argument word; chunks of 1–1300 bytes |
| launch generic packet | 600 | `net_launchSendPacket` 0x13e2c8 | header and payload; the rest of the 0x200 bytes is the stack marker |
| engine_frameStep | 50 | `engine_frameStep` 0x19e3a8 | return value for both display-rate modes |

In the sessions the consoles ran `net_main`, `net_pumpReceive`, the receiver, the builder,
`net_frameLoop`, the two codec functions, `pad_apply`, `net_sendGameMsg`, the "player left"
sender 0x1de16c, `net_getLocalPlayerSlot`, `net_localIsFirstActive`, `engine_frameStep` and
the C library's `memset` / `memcpy` as they are. Replaced by stubs: the two socket calls,
the pad sampler 0x17421c and `Camera_getYaw` 0x207450 (test input), `tasks_run` (a toy
simulation that turns the lockstep pads, camera words and executed messages into player
positions and a seed, so that the sync hash depends on all of them), `path_service`,
`game_isFrozen` (returns 1, which keeps the prediction copy out of the tick),
`net_predictLocalPlayer`, `dbg_printf`, the two calls that kill a dropped player's
character, and the message handlers. In all: 5,331 datagrams and the state after 10,707
calls of `net_main`, no difference.

The interpreter lacked nothing these tests needed; no work-around for `tools/ee_emu.py`
was necessary.

Not covered: see section 20.

## 19. Corrections to earlier documents, and proposed ledger rows

Not edited into the other files.

| # | Where | Correction | Kind |
|---|---|---|---|
| W1 | `docs/netcode.md`, input packet: "The first frame of an input packet is the frame the addressee last acknowledged" | Correct, and worth stressing: the acknowledged frame itself is sent again in every packet (first = `acked`, not `acked` + 1); the receiver skips it | Executed |
| W2 | `docs/netcode.md`, table: "aligned to 4 … 0xffffffff when this simulation frame's record was already sent" | The receiver does not test for 0xffffffff; any word other than 0xbd40 means no record. Up to two of the padding bytes before the word are uninitialised stack | Executed |
| W3 | `docs/netcode.md`, "Sync records ride inside input packets: at most one per simulation frame for the whole machine" | Also: a raw relay consumes the relayer's record for that frame and carries an entry of the *relayed* peer's sync ring instead (the entry at index `net_frame` & 0xff, whatever frame it holds) | Observed 0x1391f8–0x139240, Executed |
| W4 | `docs/netcode.md`, Sync check: "In a two-player game both sides flag each other" | Not guaranteed. The machine that flags first changes its active mask; the other side then ignores its packets (rule 1), sync records included, and may never set a flag. One flag on one machine is enough to stop the session; the machines without a flag see a silent peer and drop it after the 900-call timeout | Executed (three consoles, three runs with different outcomes) |
| W5 | `docs/netcode.md`, Drop: "When all have answered, the drop frame … becomes newest received frame + 1" | Add: a machine answers a kick request only for a peer it has not already dropped (0x13c2f0). A request that arrives after the answering machine executed the drop is never answered and the requester never drops the peer (section 12.3) | Executed |
| W6 | `docs/netcode.md`, receiver step 3 "A packet that starts later is discarded" | Its acknowledgement has been taken before that test (0x13b7c4 precedes 0x13b7f4) | Executed |
| W7 | `docs/netcode.md`, "Limits … bytes attached to one frame are counted in one byte" and per-machine row 9 ("more than 255 bytes queued … between two send turns") | Now executed: the receiver walks out of the datagram (section 7.5). The window is per frame, not per send turn: at two input frames per call two attaches land on one frame. The game adds its own 4-byte "player left" message inside `net_main` on top of whatever is queued. Also add the two buffer sizes: 5008 bytes of stack for the datagram being built, no check; 1984 bytes for a received one | Executed (over-255 frame; overrun of the 5008 bytes reproduced by a synthetic 255-frame packet) |
| W8 | `docs/netcode.md`, Launch | A launch datagram under 16 bytes is ignored, so a DATA chunk under 4 bytes could not be delivered; the receive-side checksum mask is 0x148f37, the send-side 0x8f37 (same low 16 bits) | Observed; sender Executed |
| W9 | `docs/issues/lag.md` 2.4: `engine_frameStep` is "1 while `g_displayRateModeInv` 0x44fd40 is non-zero" | Not wrong, only abbreviated: the code returns clamp(signed byte 0x44fd50 + 1, 1, 2) in that case, and `docs/mainloop.md` section 6 records that the byte has no writer, so the result is 1 | Executed (0x19e3a8, 50 input combinations) |
| W10 | `docs/issues/lag.md` 2.2, step 6: "store the sample as record number lif, message count 0" | Also: the record's message-start word is an uninitialised stack word until bytes are attached (it is only read when the count is non-zero) | Executed |
| W11 | `docs/issues/draw-sim-leaks.md`: "simulated in call c + L − 1" | Confirmed for L = `lif` − `net_frame` taken after the sample is stored and before the tick, one tick per call; add one per call without a tick | Executed |
| W12 | `docs/issues/dynamic-tests.md` a11/a12 and FINDINGS L13, F5 | Consistent with them, with one refinement: over 20,000 frames the two console-style adders and IEEE round-to-nearest give the same stick bytes but for 1 frame; only plain truncation of the exact sum stands apart (11.4 %) | Model |

Proposed rows for `FINDINGS.md` (section "Lag" or "Desync"):

| Proposed | Claim | Kind | Evidence |
|---|---|---|---|
| L7 (add) | A kick request is answered only for a peer the answering machine has not yet dropped. If one machine completes the negotiation and executes the drop before another machine's request reaches it, that other machine never drops the peer: its simulation stops at the drop frame and the first machine stalls behind it. In model runs with random counter phases 7 of 160 kicks ended this way | Executed (three interpreter instances); frequency Model | 0x13c2f0; `difftest_netwire.py` "session: kick request too late"; docs/spec/net-wire.md 12.3 |
| D-new | An out-of-sync flag is not always mutual, and one is enough: the machine that sets it changes its active mask and is from then on ignored by every machine whose mask differs, which may never set a flag itself. Those machines stall, time the peer out after 900 calls and continue without it | Executed | 0x13b6ec, 0x13bf30; "session: one machine diverges" |
| L-new | The input packet builder has no length check: 5008 bytes of stack for the datagram, then its own locals. The receive buffer is 1984 bytes | Observed; overrun Executed with a synthetic 255-frame packet | 0x137d9c, 0x137ed8, 0x13c140 |
| L-new | Two padding bytes of about four in ten input packets, the tail of every 0x200-byte launch packet and the two pressure bytes of every received input frame are uninitialised stack | Executed | docs/spec/net-wire.md 7.3, 9, 15 |

No patch is proposed.

## 20. Not done, not known

- **Nothing was run on a console or against a real second machine.** "Executed" means the
  interpreter. In particular the last bit of float sums (section 5.4) is open.
- `net_launchUpdate` 0x135638 (the launch state machine, including the receive side of the
  DATA checksum) and the developer lobby 0x1345c0 were read only. The launch model stops
  at packet layouts.
- `net_predictLocalPlayer` 0x131d88 was replaced by a stub in every session: the second
  inlined copy of the single-frame encoder and decoder (prediction states 0x5bf6f8 /
  0x5bf748) was not executed. The ghost rebase at the end of the tick was kept out by
  making `game_isFrozen` return 1.
- `net_flushBeforeLoad` 0x132db0 and the level-change sequence were not run; ticks with a
  pending level name (0x41b6d0) were not exercised.
- The malformed inputs of section 17 were not fed to the original.
- What the network library does with a datagram over 1984 bytes, and whether its send
  call can fail or block in ways that matter here (timeout argument 1000 ms).
- The handlers behind game messages and direct messages are stubs here; payload formats
  are in `docs/netcode.md`.
- Sessions used at most 4 machines, at most 1,560 calls of `net_main` in all, frame numbers
  below 700; the function-level tests used frame numbers up to 2³¹. Wrap-around of the 32-bit
  frame number was not examined.
- The pacing rules are in the model's `net_main` because the test needed them to stay in
  step with the original; they are the subject of `docs/issues/lag.md` and
  `tools/pacing_sim.py`, which were not changed.
- No symbols were added: every address used already has a name or lies inside a named
  function.
