# Lag: the pacing rules as a runnable model, and which constants to change

Scope: FINDINGS L3–L7 and the section "Pacing and lag" of `docs/netcode.md`. The pacing code
was re-read (`net_main` 0x132e90, receiver 0x13b5d0, sender 0x137d60, stick codec 0x13c450 /
0x13c970) and turned into a simulation, `tools/pacing_sim.py`.

**Nothing here was run on a game. Every patch below is untested.** Statements are marked

- **Observed** — read in the executable (SLUS_209.73 v2.00) at the address given;
- **Inferred** — follows from observations;
- **Model** — a number printed by `tools/pacing_sim.py`. The model is built from the
  Observed rules plus the assumptions listed in section 4. It has not been compared with a
  running game, so a Model statement is a prediction, never a measurement;
- **Unknown** — not established.

New names are in `symbols/lag.tsv`. `FINDINGS.md`, `patches/` and the other documents were
not edited; proposed ledger rows and corrections are in sections 3 and 10.

## 1. Result in short

- **How much delay there is (Model).** Two players on a 30 ms link with 1–2 % loss run
  with about 5 frames of input delay each (85–90 ms) and one stalled frame every 3–4 s.
  Four players on the same links run with about 13 frames (220 ms), because each peer is
  sent a packet only every sixth call. A hiccup of half a second or more — a network
  outage, a frozen machine, a second at 30 frames per second — takes the delay to 35 frames
  (0.58 s). It then lasts about 15 s if one machine was behind and about 30 s if the link
  failed for both. A peer that runs 10 % slow keeps the other machine at 36 frames for as
  long as it is slow.
- **Best single constant (Model).** The equalise rule's duration at 0x133574, 31 → **1**.
  The rule then stops a machine from getting more than 4 frames ahead of the smallest lead
  it has been told about, at once instead of after half a second. Because that figure
  stops updating when packets stop, it also limits the delay in an outage. Peak after a
  one-second hiccup 35 → 12 frames, recovery 30 s → about 10 s, a 10 % slow peer costs 6
  frames instead of 36. Stalls: unchanged for two players on a steady link, +10 % for
  four, +29 % on a link that loses packets in bursts. Unlike a lower cap it does not slow
  the game on long links.
- **The two untested patches (Model).** "Input delay drains faster" recovers quickly but
  its second word (trim window 62 → 12 calls) multiplies steady-state stalls by 3 to 6
  (two players, 1 % loss: 16 → 51 per minute; four players: 44 → 220 and the game runs at
  94 % speed). "Lower input delay cap" (14) is fine for two players below about 60 ms one
  way and throttles everything else (four players at 30 ms: 80 % speed; two players at
  110 ms: 80 %). Better values are in section 9.
- **Two more useful constants (Model).** Trim threshold 0x1335e4, 3 → 4: two-player stalls
  16 → 3 per minute for about two thirds of a frame (10 ms) more delay. Send cycle for four
  players (data 0x4027f4) 6 → 4 and for three (0x4027f0) 4 → 3: delay 13 → 10 and 9.4 → 7.7
  frames, and fewer stalls.
- **A trap (Observed rule, Inferred consequence).** The send cycle cannot be shortened to
  "a packet every call". Queued game messages are attached to an input frame only in a
  call that follows a call without a send (0x1336c4–0x1336d4); with a packet every call
  inventory, shop, dialog and level-change messages would never be sent. The model has no
  game messages and would happily recommend it; the tool prints a warning instead.
- **One machine only (Observed).** The pacing counters are read and written only inside
  `net_main`; the peer fields they use are written only by the packet receiver. Nothing
  in the simulation reads them. Each of these constants can differ between players.
- **Stick codec, L6 (Observed code, Model numbers).** Real. A full push gives no movement
  at all for four simulated frames, 0.37 on the fifth, 0.8 on the seventh, and never more
  than 0.94. A flick shorter than four frames is swallowed. Three of the four dead frames
  come from the coder's step rule and cannot be removed with one word.

## 2. The rules, exactly

All Observed. Pseudo-code is mine; `/` is integer division.

### 2.1 State

| Name here | Global | Meaning |
|---|---|---|
| `lif` | `g_localInputFrame` 0x4027a4 | next input frame to be sampled; 1 at start (0x139804) |
| `nf` | `g_netFrame` 0x4027ac | next simulation frame to run; 1 at start (0x139828) |
| `eq` | `g_netExcessLeadCalls` 0x4027dc | calls in a row with excess lead |
| `win` | `g_netTrimWindow` 0x4027e4 | position in the trim window |
| `minReady` | `g_netMinReady` 0x4027e0 | smallest ready count seen in the window; data value 100 |
| `phase`, `cycle` | 0x4027b4, 0x4027b0 | send rotation |
| `lastSent` | `g_netLastSentInputFrame` 0x4027a8 | `lif` at the last send |
| `stall` | `g_netStallCalls` 0x4027d0 | calls in a row without a simulation frame |
| `p.newest` | peer +0x44bc | newest frame held from peer p |
| `p.acked` | peer +0x44c0 | newest of our frames p has acknowledged; 1 at launch (0x13768c) |
| `p.lead` | peer +0x44c4 | p's lead as last reported |
| `p.sim` | peer +0x44c8 | p's simulation frame as last reported |
| `p.silence` | peer +0x44cc | calls since the last accepted packet from p |

`eq`, `win`, `minReady` and `phase` are touched by `net_main` and by nothing else — not by
`net_gameInit` or `net_startSync` (`tools/gxref.py` on the four addresses). They carry over
from one game to the next, so their starting values are arbitrary.

### 2.2 One call of `net_main(noSim, holdArg)` — once per rendered frame

```
 1  receive every waiting datagram (2.3)                              0x132ee4 -> 0x13c078
 2  each remote peer not dropped or kicked: p.silence += 1;
    past 900 the kick negotiation starts                              0x133060
 3  minLead = lif - nf;  minSim = nf                                  0x13334c-0x133368
    for each peer with local = dropped = kick = 0:                    0x133398-0x1333f0
        minLead = min(minLead, p.lead);  minSim = min(minSim, p.sim)
    excess = (lif - nf) - minLead                                     0x133424
 4  read the pad and the camera yaw, apply the input lock             0x133420-0x13353c
 5  hold = (lif - minSim >= 39)                              CAP      0x133548-0x133560
    if excess < 5:  eq = 0                                   EQUALISE 0x13354c, 0x133590
    else:           eq += 1;  if eq >= 31:  eq = 0; hold = true       0x133564-0x13358c
    if holdArg:     hold = true                                       0x1335a4-0x1335b0
    w = win;  win += 1                                       TRIM     0x1335b4-0x1335c8
    if w >= 61:                                                       0x1335c0
        win = 0;  m = minReady;  minReady = 100                       0x1335cc-0x1335e0
        if m >= 3:  hold = true                                       0x1335e4-0x1335ec
    if lif < 3:     hold = false                                      0x1335f8-0x133608
 6  if not hold: engine_frameStep() times:                            0x133610-0x1336b8
        store the sample as record number lif, message count 0;  lif += 1
 7  if lastSent < lif - 1 and game-message bytes are queued:          0x1336c4-0x13375c
        attach them to frame max(lastSent + 1, nf)
 8  n = number of peers with local = dropped = kick = 0               0x133764-0x1337b4
    cycle = table[n]          (6, 2, 4, 6 for n = 0..3)               0x1337cc, data 0x4027e8
    if modem: cycle += cycle >> 1                                     0x1337d8-0x1337e8
    k = 0
    for each such peer p, in slot order:                              0x133800-0x1341dc
        if phase == (k * cycle) / n:                                  0x13383c-0x133858
            send frames p.acked .. lif - 1 to p;  lastSent = lif      0x13387c, 0x1341a8, 0x1341c0
        k += 1
    phase += 1;  if phase >= cycle: phase = 0                         0x1341e0-0x134204
 9  mark as dropped the peers whose drop frame equals nf              0x13420c-0x1342a4
10  ready = 0                                                         0x1342a8-0x134378
    while ready < lif - nf - 1 and every peer that is not dropped
          (this machine included) holds a record numbered nf + ready:
        ready += 1
    minReady = min(minReady, ready)                                   0x134380-0x1343a4
    steps = 0 if noSim else min(ready, engine_frameStep())            0x1343a0-0x1343d4
    if steps >= 1:  stall = 0;  run `steps` simulation frames (nf += steps)   0x1343d8-0x1343e0
    else:           stall += 1                                        0x1343f0-0x134400
11  g_netLongStallCalls (0x40279c): +1 while stall > 300 and the
    session has not ended, otherwise 0                                0x134408-0x134448
12  net_predictLocalPlayer: run the prediction copy for every frame
    from g_simFrame to lif - 1                                        0x13444c; 0x131e30-0x132cf0
```

Notes on that listing.

- The three hold rules use values taken **before** sampling in this call. A peer's
  `p.lead` and `p.sim` are what its last packet said, however old.
- CAP compares with reported simulation frames, which lag by the transit time and the send
  interval. EQUALISE counts peers that are out of sync; only dropped or kicked peers are
  left out (the tests at 0x133398–0x1333b4 read bytes +0x44d4…+0x44d6 only).
- TRIM: `win` runs 0…61, so the window is 62 calls. It fires only when **every** call of
  the window had at least 3 frames ready, and `ready` already contains the limit
  `lif − nf − 1`.
- Step 10 cannot run the frame sampled in the same call. At the end of a call
  `lif − nf ≥ 1`; with one simulation frame per call, input sampled now is simulated
  `lif − nf` calls later (that value measured just before the sample). This document calls
  it the **lead**. Its floor is 1; the trim rule stops at 2.
- The argument passed at 0x13444c is the hold flag, but the prediction function does not
  appear to read it (no use in the decompile, no read of the argument register in its
  first instructions).

### 2.3 The receiver — what a packet changes (0x13b5d0)

```
input packet from slot s, last frame `last`, header bytes b9, b10, b11:
    ignore it if the sender's active mask differs from ours, or s is local,
        dropped or out of sync, or s is being kicked and this is not a raw relay   0x13b6ec-0x13b744
    p.silence = 0;  p.heard = 1                                       0x13b750, 0x13b75c
    p.sim  = last - b9                                                0x13b780-0x13b790
    p.lead = last - p.sim                                             0x13b798-0x13b7ac
    if p.newest >= last:  stop  -- nothing else in the packet is read 0x13b7a4-0x13b7a8
    p.acked = max(p.acked, last + signed(b11))                        0x13b7c0-0x13b7f0
    first = last - b10 + 1
    if first > p.newest + 1:  stop                                    0x13b7f4-0x13b804
    store frames p.newest + 1 .. last;  p.newest = last               .. 0x13be6c
    then the sync record, then the game-message blocks
```

The sender (0x137d60) fills the header with: b9 = `last − nf` with `nf` as it is before
this call's simulation frames (0x137e40), b10 = `last − p.acked + 1`, b11 = `p.newest −
last` (0x137ec0–0x137f00), where `last = lif − 1`. So the lead a machine reports is its own
lead before sampling when it takes one step per call, and one more than that at two steps.

### 2.4 How many steps a call stands for

`engine_frameStep` 0x19e3a8 (Observed): 1 while `g_displayRateModeInv` 0x44fd40 is non-zero;
otherwise `g_lastFrameFields` 0x83d2c8 clamped to 1…2. `gfx_endFrame` 0x19da78 (Observed):
`g_lateFrameRun` 0x44fdb0 counts frames in a row that did not wait for the vertical blank,
and the 32nd calls `gfx_setDisplayRateMode(1)` 0x19dd48; in mode 1, frames that used less
than one field (0x2627 timer counts) bank the remainder in `g_spareFrameTime` 0x44fdac and
more than 0x7272 counts (three fields) calls `gfx_setDisplayRateMode(0)`. That mode 1 is
"each picture shown for two fields" is the reading of `docs/mainloop.md` section 6
(Inferred there); I did not re-derive which frames count as late.

### 2.5 What the lead delays, and what it does not

Step 12 runs the prediction copy through every sampled frame in the same call, so the
player's own character answers at once (Observed; `docs/netcode.md`, "Prediction"). The lead
delays everything else: when a hit lands, when damage is taken, when other players see the
move. Two side effects are Inferred:

- A **held** call samples nothing, so the prediction loop has nothing to run and the camera
  update inside it is skipped: the player's own character stands still for that picture.
- A rebase (every 31 simulated frames, 0x13b1e8, or when forced) sets `g_simFrame` back to
  `nf` (0x13b28c), and step 12 then re-runs all `lead` frames in one call. The cost of a
  rebase grows with the lead. How much time that is on the console is Unknown.

## 3. What the earlier documents got wrong or left vague

| # | Where | Correction | Kind |
|---|---|---|---|
| C1 | netcode.md "Input delay is not a constant": "the lead … is at least 2" | True only at the ready scan, after sampling. At the end of a call the floor is 1 (section 2.2) | Observed |
| C2 | netcode.md, receiver steps 4 and 5 read as if always done | The acknowledgement, the sync record and the message blocks are read only from a packet that brings at least one new frame and starts no later than newest + 1 (0x13b7a4–0x13b7a8, 0x13b7f4–0x13b804). A machine that is not sampling (held by the cap, or called with the hold argument during a load) still sends packets, but nothing except `p.sim`, `p.lead` and the silence counter is taken from them: its acknowledgements do not register, and a sync record in such a packet is lost, since a record is sent once | Observed rule, Inferred consequence |
| C3 | netcode.md hold table, "cap" and FINDINGS L4 "capped at 38 frames" | The cap is against *reported* simulation frames. The lead it allows is 38 minus how far the slowest report lags (Model: 31–36 on a 30 ms link) | Observed, Model |
| C4 | FINDINGS L4 "drains at one frame per 62 calls" | The trim rule fires only if all 62 calls of a window had 3 or more frames ready. With packet loss many windows do not qualify. It never fires on a machine whose ready count is limited by another machine's input, so two leads can stay up to 4 frames apart indefinitely (equalise needs 5) | Observed rule, Model |
| C5 | FINDINGS L5 "below 30 frames per second" | The threshold is 60, not 30, for the first 32 pictures: at full display rate a call stands for one step however long the picture took (section 2.4). Every missed field costs the other machines one frame of lead until the display drops to half rate. From then on 30 per second is neutral, and only below 30 does the shortfall continue. A machine that misses fields now and then, without 32 in a row, costs the others one frame each time, indefinitely | Observed (0x19e3a8, 0x19da78), consequence Inferred |
| C6 | netcode.md codec text: "velocity = …, value += velocity" | The order in the code is value first, then velocity from the new value (0x13cdb0–0x13cdd8). The sample numbers printed there are right (my separate model reproduces them); only the sentence is loose. The damping factor is 1 − √0.2, computed at run time (0x13cc6c, 0x13cd24, 0x13cd64) | Observed |
| C7 | netcode.md: "the 0.8 threshold … after 6" frames | By the model it is the 7th simulated frame, because 0.8 is tested after the dead zone of `pad_decodeStick` 0x174ce0 (radial, 0.32). The first movement of any size is on the 5th frame | Observed code, Model numbers |
| C8 | netcode.md, send cycle and game messages described separately | They are tied: see section 6.5. The attach test needs a call without a send between sends | Observed rule, Inferred consequence |

Not wrong, but worth knowing (Observed): the trim window, its minimum, the equalise counter
and the send phase are not reset between games (2.1).

## 4. The model

`tools/pacing_sim.py` (Python 3, standard library only) simulates 2 to 4 machines doing
sections 2.2–2.4 on their own clocks, joined by links with latency, jitter, loss, loss
bursts and outages. Every constant in section 2.2 is a parameter, for all machines or for
one (`cap=20@A`).

| In the model | Source |
|---|---|
| hold rules, sampling, send rotation, packet header, receiver, ready scan, steps per call | Observed, section 2 |
| 8-bit wrap of the three header bytes | Observed (0x137ec0–0x137f00) |
| half-rate display switching | `docs/mainloop.md` section 6 and section 2.4 |
| a frame that needs more than one field takes a whole number of fields | assumption |
| a call happens at the start of each picture and takes no time | assumption |
| jitter = extra delay, exponential with the given mean, cut at 8× | assumption |
| losses independent, or bursts covering the given share of time | assumption |
| packets that arrive while a machine is frozen are all kept | assumption (the socket buffer size was not read) |
| peer fields start at 0 except `acked` = 1 | Inferred (table cleared by `net_shutdown`; 0x13768c) |
| machines start with random clock offsets, trim-window and send phases | follows from 2.1 |

Not in the model: dropping a peer (it only warns when silence passes 900 calls), level
changes, **game messages**, the sync check, packet sizes, CPU time, the simulation itself.

Three quantities are reported per machine: **lead** (frames, end of call), **stalled** calls
(no simulation frame: the world stands still for a picture) and **held** calls (no input
sampled: the own character stands still for a picture). `run` prints them over time, in
rows of 5 s, and as a summary; `compare`, `sweep` and `cases` print summaries only. In a
steady state the two counts are equal, because every stall adds a frame of lead and every
hold removes one.

```
python3 tools/pacing_sim.py run --latency 30 --loss 1 --outage 20:1
python3 tools/pacing_sim.py compare --emu B:20:60:90 --variant "A only:eq_calls=1@A"
python3 tools/pacing_sim.py sweep cap 14,20,28,38 --players 4 --latency 60
python3 tools/pacing_sim.py cases --brief      # every table of section 5.1 and 6.1, about 80 s
python3 tools/pacing_sim.py stick              # section 8
python3 tools/pacing_sim.py words eq_calls=1   # address, original word, new word
```

One thing can be checked by hand (Inferred): machine A cannot simulate a frame before B's
input for it arrives and the reverse, so the two leads together are at least the round trip
in frames, plus the wait for the next packet in each direction, plus 2. The model's sums
agree: 3.3 frames on a LAN, 10 at 30 ms.

## 5. How much delay builds up, and how long it lasts

All Model. "30 ms" is one way; jitter 3 ms; a frame is 16.7 ms; 12 seeds per row.

### 5.1 A steady link, original constants

Mean lead of the machine with the larger one, the time from a pad sample to the simulation
frame that uses it on that machine, and stalled calls per minute and machine
(`cases --brief`, rows "original").

| Case | Players | Link | Lead (frames) | Delay | Stalls / min |
|---|---|---|---|---|---|
| lan | 2 | 1 ms, no loss | 1.8 | 29 ms | 0 |
| bb1 | 2 | 30 ms, 1 % loss | 5.2 | 86 ms | 16 |
| bb2 | 2 | 30 ms, 2 % loss | 5.3 | 89 ms | 17 |
| bb2x3 | 3 | 30 ms, 2 % loss | 9.4 | 159 ms | 34 |
| bb2x4 | 4 | 30 ms, 2 % loss | 13.3 | 224 ms | 44 |
| wifi | 2 | 30 ms, 2 % loss in 150 ms bursts | 10.4 (95 % of the time ≤ 20, peak 35) | 178 ms | 68 |
| far | 2 | 110 ms, jitter 8 ms, 1 % loss | 10.7 | 179 ms | 12 |
| far4 | 4 | 110 ms, jitter 8 ms, 1 % loss | 17.3 | 292 ms | 43 |

- Loss of 1–2 % adds little delay by itself (5.2 against 4.9 frames with no loss) but
  produces the stalls: about one per lost packet at 1 %, because the trim rule has removed
  the spare frame again before the next loss.
- The player count matters more than the link. A peer is sent a packet every 2, 4 or 6
  calls for 2, 3 or 4 players, so input is up to 6 frames old before it leaves.
- In a three-player game with two consoles in one house and the third 110 ms away, all
  three run at about 13.5 frames: everyone carries the worst link.

### 5.2 A hiccup, original constants

Two players, 30 ms, 1 % loss; machine A's lead, 5 frames before the event
(`run --loss 1 --outage 20:SECONDS --duration 140 --runs 12`, and `--freeze B:20:SECONDS`).

| Event | Length | Peak lead | Peak delay | Back to normal after |
|---|---|---|---|---|
| link drops everything | 0.1 s | 12 | 0.20 s | 4 s |
| | 0.25 s | 20 | 0.33 s | 14 s |
| | 0.5 s | 35 | 0.58 s | 28 s |
| | 1 s, 2 s, 5 s | 35 | 0.58 s | 28–30 s |
| the other machine freezes | 0.1 s | 13 | 0.22 s | 9 s |
| | 0.25 s | 22 | 0.37 s | 12 s |
| | 0.5 s and longer | 35 | 0.58 s | 15–16 s |

The two kinds recover at different speeds for a reason visible in section 2.2. After a
freeze only the machine that waited has a high lead, the equalise rule sees an excess and
gives back one frame per 31 calls. After an outage both leads are high, there is no excess,
and only the trim rule works: one frame per 62 calls. Machine A during and after a
one-second outage (`run --loss 1 --outage 20:1 --duration 70 --series --bucket 5`):

| Seconds | 15–20 | 20–25 | 25–30 | 30–35 | 35–40 | 40–45 | 45–50 | 50–55 |
|---|---|---|---|---|---|---|---|---|
| mean lead, original | 6.0 | 28.3 | 25.3 | 20.5 | 15.7 | 10.8 | 6.2 | 7.3 |
| mean lead, equalise duration 1 | 5.8 | 11.1 | 7.8 | 7.0 | 6.7 | 6.0 | 6.4 | 6.0 |

### 5.3 One slow machine, original constants

Machine B is the slow one; the table is about the other machine, A.

| What B does | A's lead | A back to normal | Game speed |
|---|---|---|---|
| draws at 30 per second for 10 s (in-game load) | peaks at 36 after one second | about 16 s after that peak, although B's display went to half rate and stopped causing stalls after the first second | full, apart from that first second |
| draws at 20 per second for 10 s | 37 for the whole spell | 13 s after it ends | two thirds while it lasts (two steps per three fields) |
| runs at 90 % speed for 40 s (an emulator that cannot keep up) | 36 for the whole spell, 0.6 s of delay | 16 s after it ends | 90 % |
| runs at 80 % speed | the same | 15 s | 80 % |

B's own lead does not move in any of these. The 30-per-second case is correction C5: for the
first 32 pictures B produces one input frame per two fields, A stalls every other call, and
each stall is a frame of lead. The slow-emulator case is the worst for a person: the game
only slows by 10 %, but the faster machine's player has 0.6 s of delay for as long as it
lasts, because the equalise rule returns two frames a second and the shortfall is six.

## 6. Which constants help

All Model unless marked. Names of constants as in `tools/pacing_sim.py`.

### 6.1 One constant at a time

`cases --brief`. Lead and delay are for the machine with the larger mean lead; stalls are
the mean per machine and minute and include the 58 or so that a one-second event forces.
"4 players" is case bb2x4, "bursts" is case wifi, "slow peer" is case emu90 (mean lead of A
over 110 s, 40 of them with B slow), "freeze" and "outage" are the one-second events.

| Constants | 2 players: lead, stalls | 4 players: lead, stalls, speed | Bursts: lead, stalls | Slow peer: lead | Freeze: peak, recovery | Outage: peak, recovery | 4 players at 110 ms: speed |
|---|---|---|---|---|---|---|---|
| original | 5.2, 16 | 13.3, 44, 98.8 % | 10.4, 68 | 17.4 | 35, 16 s | 36, 30 s | 98.8 % |
| patch "drains faster" (`eq_calls=8,trim_calls=12`) | 4.4, **51** | 10.6, **220**, **93.9 %** | 6.2, **116** | 5.3 | 36, 6 s | 36, 6 s | **94.5 %** |
| patch "cap 14" (`cap=14`) | 5.2, 16 | 7.1, **722**, **79.9 %** | 6.0, 103 | 7.5 | 11, 8 s | 12, 6 s | **54.9 %** |
| `eq_calls=8` | 5.1, 17 | 13.0, 47, 98.7 % | 9.6, 73 | 5.8 | 35, 8 s | 36, 29 s | 98.7 % |
| `eq_calls=4` | 5.1, 17 | 13.0, 48, 98.6 % | 9.3, 75 | 5.6 | 35, 7 s | 36, 30 s | 98.7 % |
| **`eq_calls=1`** | 5.1, 17 | 12.9, 48, 98.6 % | 7.9, 88 | 5.5 | **12**, 7 s | **12**, 12 s | 98.7 % |
| `trim_calls=12` | 4.5, **46** | 13.7, **161**, 95.5 % | 8.5, 100 | 16.2 | 36, 10 s | 36, 6 s | 95.7 % |
| `trim_min=4` | 5.9, **3** | 13.5, 40, 98.9 % | 10.7, 65 | 18.0 | 32, 15 s | 35, 28 s | 98.9 % |
| `cap=28` | 5.2, 16 | 12.9, 47, 98.7 % | 9.3, 74 | 13.1 | 25, 13 s | 26, 18 s | **94.2 %** |
| `cap=20` | 5.2, 16 | 10.1, **212**, **94.1 %** | 7.5, 84 | 9.8 | 17, 9 s | 18, 10 s | **74.4 %** |
| `send3=4` (and `send2=3`) | no effect | **10.0**, 33, 99.1 % | no effect | no effect | no effect | no effect | 99.1 % |
| `eq_calls=1,trim_min=4` | 5.9, 3 | 13.1, 45, 98.7 % | 8.3, 81 | 6.8 | 12, 4 s | 12, 6 s | 98.8 % |
| `eq_calls=1,trim_min=4,send2=3,send3=4` | 5.9, 3 | 10.1, 28, 99.2 % | 8.3, 81 | 6.8 | 12, 4 s | 12, 6 s | 99.3 % |

Bold = clearly better or clearly worse than the original.

### 6.2 The equalise duration (0x133574) — why 1 is different from 8 or 4

With any duration above 1 the lead still grows during a stall (by 7 frames in 8 calls at
duration 8), reaches the cap in a long one, and is only returned faster afterwards. That
fixes one-sided events and a slow peer — up to a shortfall of one frame per `eq_calls`
calls: 8 copes with a peer at 90 % speed and not at 80 %, 4 copes with both. It does
nothing for an outage, where both leads rise together.

At 1 the rule is no longer "give back slowly" but a limit: no sample while this machine is
5 or more ahead of the smallest lead it knows. `p.lead` is written only when a packet
arrives (0x13b7ac, Observed). In an outage, or while a peer is frozen, it keeps its last
value, so the limit holds in exactly the cases where the cap is reached today — and unlike
the cap it is relative to the other machines' leads, so it needs no adjusting for latency
or player count. Starting a four-player game at 150 ms with it reaches full speed as fast
as the original (first two seconds 83 against 101 simulated frames, practically the same
from then on).

What it costs: on a link that loses packets in bursts the lead no longer stays inflated
from one burst to the next, so each burst stalls in full (68 → 88 stalled calls per minute
for 2.5 frames, 42 ms, less delay). In a steady four-player game stalls rise by a tenth.

### 6.3 The trim rule (0x1335c0, 0x1335e4)

The window length is the wrong knob. The rule does not know how much of this machine's
input the *others* have in hand; a hold here is a stall there. At 62 calls it already
removes the spare frame within a second of every loss. At 12 it does so five times as
often, and stalls go up three- to sixfold in every steady case. This is what is wrong with
the "drains faster" patch.

The threshold is the useful knob. With `trim_min=4` the rule stops one frame earlier; a
single lost packet (two frames late with one remote peer) is then absorbed. Two-player
stalls fall from 16 to 3 per minute at 1 % loss and from 17 to 5 at 2 %, for 0.5–0.8 frame
(8–13 ms) more delay. With three or four players the gain is small (44 → 40), because a
lost packet there is four or six frames late.

A short window can be combined with the higher threshold for two players
(`trim_calls=12,trim_min=4`: outage recovery 30 s → 5 s, stalls 16 → 4), but not for four
(stalls 44 → 200). With `eq_calls=1` in place it is not needed.

### 6.4 The cap (0x133554)

The cap is the only original rule that limits delay after an outage, which is why lowering
it looks attractive. It has to stay above roughly twice the one-way latency in frames,
plus twice the send cycle, plus 8 (a rule of thumb read off the table below; it errs on the
high side for two players). Below that the machine stops sampling during normal play and
the whole game slows down. Game speed and stalls per minute by cap
(`sweep cap … --players N --latency L --jitter J --loss 1 --duration 90 --runs 4`, jitter
8 % of the latency):

| Players, one-way latency | cap 14 | cap 20 | cap 24 | cap 28 | cap 32 | cap 38 (original) |
|---|---|---|---|---|---|---|
| 2, 30 ms | 99.5 %, 18 | 99.5 %, 18 | = | = | = | 99.5 %, 18 |
| 2, 60 ms | 99.6 %, 13 | = | = | = | = | 99.6 %, 13 |
| 2, 110 ms | **79 %**, 741 | 98.9 %, 39 | 99.7 %, 10 | = | = | 99.7 %, 10 |
| 2, 150 ms | **63 %** | **85 %**, 545 | 96.0 %, 145 | 99.6 %, 14 | = | 99.7 %, 12 |
| 3, 30 ms | 97.6 %, 84 | 99.1 %, 33 | = | = | = | 99.0 %, 35 |
| 3, 60 ms | **88 %**, 416 | 98.7 %, 46 | 99.1 %, 32 | = | = | 99.1 %, 32 |
| 3, 110 ms | **65 %** | **87 %**, 459 | 96.8 %, 113 | 99.0 %, 34 | 99.2 %, 28 | 99.2 %, 28 |
| 4, 30 ms | **85 %**, 539 | 96.5 %, 124 | 98.4 %, 57 | 98.7 %, 44 | = | 98.7 %, 44 |
| 4, 60 ms | **71 %** | 92 %, 286 | 96.6 %, 121 | 98.4 %, 54 | 98.7 %, 44 | 98.8 %, 43 |
| 4, 110 ms | **55 %** | **74 %** | **86 %**, 523 | 93.8 %, 221 | 97.6 %, 84 | 98.8 %, 40 |
| 4, 150 ms | **46 %** | **63 %** | **73 %** | **83 %** | 91.5 %, 306 | 97.9 %, 75 |

So 14 is a two-player, short-link value; 28 is safe for everything except four players
beyond about 60 ms and three at 150 ms (94 %, not in the table); and for four players at
150 ms the original 38 is already slightly too low. A lower cap on one machine slows the
game for everybody, because the others then wait for that machine's input. With
`eq_calls=1` the cap is hardly ever reached and can stay where it is.

### 6.5 The send cycle (data 0x4027e8) — and why it cannot be "every call"

The model's largest single gain for more than two players is sending more often. With a
packet to one peer in every call it predicts 8.4 frames instead of 13.3 for four players,
and 4 frames with 1–3 stalls a minute instead of 5.2 and 16 for two. **It would break the
game.** Step 7 of section 2.2 attaches queued game-message bytes only if `lastSent < lif −
1`, and step 8 sets `lastSent = lif` on every send (0x1341c0). At one step per call that
test is true only when the previous call sent nothing. The original cycles (2, 4, 6) always
leave every second call free. A cycle with a packet in every call leaves none: messages
would be queued and never attached, on that machine's own simulation as well (Inferred from
the two Observed rules; with two steps per call, half-rate display, they would still go).

Cycles that keep one free call:

| Remote peers | Original | Shortest safe | Sends at phases | Model, 30 ms 2 % loss |
|---|---|---|---|---|
| 1 | 2 | 2 | 0 | — |
| 2 | 4 | 3 | 0, 1 (2 free) | lead 9.4 → 7.7, stalls 34 → 28 |
| 3 | 6 | 4 | 0, 1, 2 (3 free) | lead 13.3 → 10.0, stalls 44 → 33; at 110 ms 17.3 → 14.5 |

With these, messages get a slot once per cycle (every 3 or 4 calls instead of every 2), and
each peer still gets one sync record per cycle, since a record goes into the first packet
after `nf` changes (0x1391c0–0x1391e4 in the sender's tail). Values that put two peers in
the same call (for example 2 or 1 for three remote peers) would also leave the second of
them without any sync record.

For two players nothing can be gained from the table. Making that cycle 1 would need the
attach rule changed as well (the comparison at 0x1336cc and the target frame at 0x13370c,
by my reading). That is a change to the message path, where a mistake means a desync or
lost messages, and it is not proposed here.

### 6.6 What I would test first

1. `eq_calls=1` alone (LAG-1).
2. Add `trim_min=4` (LAG-2) if stalls on a clean link are the complaint.
3. In three- and four-player games add the shorter send cycle (LAG-3, LAG-4).

Together (last row of 6.1): four players 13.3 → 10.1 frames with a third fewer stalls; two
players 0.7 frame more delay than now with a fifth of the stalls; no modelled event leaves
more than 12 frames of delay for two players (16 for four), and it is gone in 4–6 s.

## 7. Changing them on one machine only

**Safe as far as the simulation is concerned (Observed).**

- `eq`, `win`, `minReady`, `phase`, `cycle`, `lastSent`, `stall`: every reference found by
  `tools/gxref.py` is in `net_main`, `net_gameInit` or `net_startSync`.
  `g_netLongStallCalls` is also read by the HUD's draw function 0x1dbc48 and by the wait
  after a level load (0x323054) — both per machine already.
- Peer fields +0x44c4 and +0x44c8 are written only at 0x13b7ac and 0x13b790 and read only
  in step 3. A sweep of every address formed inside the peer table (0x5bf838–0x5d0bb8)
  finds only netcode functions (0x131b00–0x13e628); the accessors that simulation code
  calls return the dropped byte, the local byte, the out-of-sync byte, the camera yaw or
  the prediction copy, never a pacing field. (The sweep also lists lighting and script
  functions; I checked three of them and they are stale-register artefacts of the search.)
- `lif` is read by prediction, `nf` is the lockstep frame itself.
- A packet says what it contains (first frame by count, last frame, acknowledgement); the
  receiver assumes nothing about how often packets come or how large the lead is.

What a different lead does change is *when* things happen in real time: which frame a
button press or a game message lands on. That already differs per machine.

**Limits (Observed fields, Inferred consequences).**

- Do not raise the cap. The raw relay used when a peer is dropped covers the last 41 frames
  (0x13c370), and the count, lead and acknowledgement bytes in the header are 8 bits.
  Everything proposed here lowers leads.
- Who benefits (Model, `compare` with `@A`): `eq_calls=1` on A alone gives A the full
  benefit (outage: A peaks at 12, B at 34 and needs 15 s) and hardly changes B's stalls
  (+1 % on a steady link, +8 % in the outage case). A lower cap on A alone slows everyone
  if it is too low. A shorter send cycle helps in proportion to how many machines have it:
  on one of four machines every lead falls by 0.6 frame and the others see that machine's
  input 20 ms sooner; on all four every lead falls by 3.3.
- When a silent peer is dropped after 900 calls, the survivors have by then stalled for 15
  s. With the original constants their leads are at the cap, so many packets already
  carried the frames around the drop. With `eq_calls=1` (or a low cap) their leads are
  only 4 above normal. `docs/netcode.md` (per-machine state, row 2) describes a possible
  deadlock at the drop frame that more buffered input makes less likely. Whether that
  matters is Unknown; it concerns three- and four-player games only.

## 8. The stick codec (L6)

**The mechanism is Observed; the numbers are Model** (`pacing_sim.py stick`, a
re-implementation of the two functions from the description below, single precision).

- Encoder 0x13c450, per axis and frame: step = table[index] (4, 6, 8, 12, 16, 24, 32, 48,
  64; data 0x402860). If the sample is at least one step from the predictor, the predictor
  moves one step toward it (kept in 0…255) and the index goes up 2; otherwise the index
  goes down 1 (0…8; data 0x402878). One "moved" bit and one direction bit go on the wire.
- Decoder 0x13c970: the same predictor from the two bits (tables 0x402880, 0x402898), then
  ten times: value += velocity; velocity = (velocity + (predictor − value) × 0.05) ×
  (1 − √0.2). The stick byte is the value, truncated (0x13cdb0–0x13ce28).
- `pad_decodeStick` 0x174ce0 then removes a radial dead zone of 0.32 of full deflection and
  rescales; `pad_apply` 0x174410 sets a digital direction above 0.8.
- The tick passes the local player's own input through the same pair (FINDINGS G4), and so
  does prediction. So this applies to every machine and to the player's own character, in
  every net game, whatever the connection. Offline the byte is used as read.

From rest the predictor can only go 4, 8, 16, 32, 64 in successive frames, so it passes
the dead-zone edge (41 counts) on the fourth frame whatever the spring does. That is a
bound from the code alone: **at least three frames of nothing.** With the spring:

| Frame after the stick moves | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| full push, decoded byte | 129 | 134 | 143 | 162 | 201 | 227 | 239 | 245 | 248 | 250 |
| full push, value the game reads | 0 | 0 | 0 | 0 | 0.37 | 0.67 | 0.80 | 0.87 | 0.91 | 0.93 |
| release after a long push | 0.93 | 0.87 | 0.77 | 0.55 | 0.10 | 0 | 0 | 0 | 0 | 0 |
| reversal, full right to full left | 0.93 | 0.87 | 0.77 | 0.55 | 0.10 | 0 | −0.21 | −0.61 | −0.82 | −0.91 |
| push held for 3 frames only | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| push held for 5 frames only | 0 | 0 | 0 | 0 | 0.37 | 0.36 | 0.29 | 0.02 | 0 | 0 |

- A full push: nothing for 4 frames (67 ms), half on the 6th, a digital direction on the
  7th. L6's "4–6 frames" is right; it is the dead zone that turns a slow ramp into a pure
  delay.
- The value never passes 0.94: the predictor stops within 3 counts of the target and the
  byte is truncated. Whether movement speed scales with that value was Unknown here; it
  does, linearly (`docs/spec/movement-camera.md` 4.1 c and g: the speed is the stick
  magnitude times the top speed, capped at the top speed), so a full push through the
  codec moves at about 94 % of top speed. The limit is one-sided: executed in isolation, a
  stick held toward 255 settles at +0.943 and one held toward 0 at −1.000
  (`docs/issues/dynamic-tests.md`, checks a3, a4, b9).
- Letting go, the character keeps moving for 5 frames. A flick of 50 ms does nothing.
- For the player's own character this is the whole added delay (prediction hides the
  lead). For everything else it comes on top of the lead.

No stick patch is proposed. The cheapest change, the spring's iteration count at 0x13cd34
(original word 24060009; 24060013 would make it 20), brings every row above forward by
exactly one frame in the model, and it changes the decoded input, so **every** player
would need it or the game is out of sync on the first stick movement. Removing the other
three frames means changing the step rule in both tables on every machine.

## 9. Patch proposals

**All untested.** Words are 32-bit, as PCSX2 `word` patches take them; each original was
read from the executable. One change per row. "Model" gives before → after from sections
5–6. None of LAG-1…LAG-5 has to match between players (section 7).

| ID | Address | Original | New | What it changes | Model, before → after | What could go wrong | Every player? |
|---|---|---|---|---|---|---|---|
| LAG-1 | 0x00133574 | 2862001F | 28620001 | Equalise duration 31 calls → 1: no input is sampled while this machine's lead is 5 or more above the smallest lead it has been told about | One-second outage: peak 35 → 12 frames, back to normal 30 s → about 10 s. One-second freeze of the peer: 35 → 12, 16 s → 7 s. Peer at 90 % speed: 36 → 6–7 frames while it lasts. Steady stalls per minute: 2 players 16 → 17, 4 players 44 → 48, bursty loss 68 → 88 | During any stall the player's own character also stops after about 5 frames, instead of running on and paying for it later. More stalled frames on a link that loses packets in bursts. Acts on reports that are a few frames old; the model includes that, the game has not been watched. Fewer frames in hand when a silent peer is dropped in a 3–4 player game (section 7) | No. The machine that applies it gets the benefit |
| LAG-1b | 0x00133574 | 2862001F | 28620004 | The cautious alternative to LAG-1, not in addition: duration 31 → 4 | Freeze: peak unchanged at 35, back to normal 16 s → 7 s. Peer at 90 % or 80 % speed: 36 → 6 frames. Outage: no change. Steady stalls: 2 players 16 → 17, 4 players 44 → 48 | Does nothing for an outage or any event that hits both machines | No |
| LAG-2 | 0x001335E4 | 28420003 | 28420004 | Trim threshold: the window must have had 4 frames ready, not 3, before a sample is skipped | 2 players, 1 % loss: stalls 16 → 3 per minute, lead 5.2 → 5.9 frames. 2 % loss: 17 → 5. 4 players: 44 → 40 | About 10 ms more delay all the time. Recovery after an event is not faster. With few stalls left, two machines' leads can stay up to 4 frames apart | No |
| LAG-3 | 0x004027F4 | 00000006 | 00000004 | Send cycle with three remote peers (four players): each peer gets a packet every 4th call, not every 6th | 4 players, 30 ms, all four patched: lead 13.3 → 10.0 frames (224 → 168 ms), stalls 44 → 33. At 110 ms: 17.3 → 14.5. One machine of four patched: 13.3 → 12.6 | 45 packets a second instead of 30; the cost of a send on the console was not measured. Game messages get a slot every 4th call instead of every 2nd (menu actions up to 33 ms later). **Must not be lower than 4** (section 6.5) | No. The gain grows with the number of machines that have it |
| LAG-4 | 0x004027F0 | 00000004 | 00000003 | Send cycle with two remote peers (three players): every 3rd call, not every 4th | 3 players, 30 ms: lead 9.4 → 7.7 frames, stalls 34 → 28 | As LAG-3 (40 packets a second; message slot every 3rd call). **Must not be lower than 3** | No |
| LAG-5 | 0x00133554 | 28420027 | 2842001D | Cap 38 → 28 frames. Only as a replacement value for the existing cap patch; little to add once LAG-1 is in | Outage: peak 36 → 26, back to normal 30 s → 18 s. Peer at 90 %: 36 → 26 | Four players beyond about 60 ms one way: the game slows (94 % at 110 ms, 83 % at 150 ms); three players at 150 ms: 94 %. One machine with a cap that is too low slows all | No, but see the cell to the left |

The two data words 0x4027F0 and 0x4027F4 are read on every call (0x1337cc), so a patch
applied at any time takes effect.

### The two patches already in `patches/`

- **"Net test: input delay drains faster"** (0x133574 → 28620008, 0x1335C0 → 2863000B).
  Split it. The first word is good, and 28620001 (LAG-1) is better. The second should be
  dropped: in the model it is the cause of 3–6 times more stalls in steady play and of a
  94 % game speed with four players. Its description says a held call "can make the
  others wait"; the model says that this happens after nearly every lost packet.
- **"Net test: lower input delay cap"** (0x133554 → 2842000F, cap 14). Its description
  should say: two players, up to about 60 ms one way. With three players it costs 2–12 %
  of game speed at 30–60 ms, with four 15–30 %. If a cap patch is wanted for general use,
  28 (LAG-5) is the lowest value the model supports for up to four players at 60 ms.

### Proposed patch text

```
[Net test: equalise at once (LAG-1)]
author=reverse engineering test patch, untested on a running game
description=net_main, 0x133574: skip sampling input whenever this machine's input is 5 or more frames further ahead of its simulation than the smallest such lead reported by the others, instead of only after 31 calls in a row. Keeps the extra input delay after an outage, a frozen peer or a slow peer to about 4 frames above the others. During a stall your own character stops too. Per machine. docs/issues/lag.md.
// was: 2862001F (slti v0,v1,31)
patch=1,EE,00133574,word,28620001

[Net test: trim leaves one spare frame (LAG-2)]
author=reverse engineering test patch, untested on a running game
description=net_main, 0x1335E4: the periodic input skip needs 4 ready frames instead of 3. Fewer one-frame world freezes after a lost packet, about 10 ms more input delay. Per machine. docs/issues/lag.md.
// was: 28420003 (slti v0,v0,3)
patch=1,EE,001335E4,word,28420004

[Net test: 4-player send cycle 6 -> 4 (LAG-3)]
author=reverse engineering test patch, untested on a running game
description=Send-cycle table, 0x4027F4: with three remote peers each one is sent a packet every 4th call instead of every 6th. Do not use a value below 4: game messages need one call without a send. Per machine. docs/issues/lag.md.
// was: 00000006
patch=1,EE,004027F4,word,00000004

[Net test: 3-player send cycle 4 -> 3 (LAG-4)]
author=reverse engineering test patch, untested on a running game
description=Send-cycle table, 0x4027F0: with two remote peers each one is sent a packet every 3rd call instead of every 4th. Do not use a value below 3. Per machine. docs/issues/lag.md.
// was: 00000004
patch=1,EE,004027F0,word,00000003
```

## 10. Proposed ledger rows

For `FINDINGS.md`, section "Lag". Not applied.

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| L4 (replace) | A stall is never caught up: each call runs at most as many simulation frames as it samples. Three rules skip a sample: the cap (own input 39 or more ahead of the slowest *reported* simulation frame), equalise (own lead 5 or more above the smallest reported lead for 31 calls in a row), trim (every 62nd call, if all 62 had 3 or more frames ready). Reported values are as old as the last packet | Observed | 0x133548–0x133608, 0x13b790, 0x13b7ac; docs/issues/lag.md section 2 |
| L5 (replace) | At full display rate a call stands for one step however long the picture took, so every field a machine misses costs every other machine one frame of lead. After 32 late pictures in a row the display goes to half rate and a call stands for two steps; only below 30 pictures per second does the shortfall continue | Observed (rules), Inferred (consequence) | 0x19e3a8, 0x19da78, 0x19dd48; docs/mainloop.md section 6 |
| L6 (replace) | The stick codec is used for the local player too. From rest its predictor moves 4, 8, 16, 32, 64 counts in successive frames and a radial dead zone of 0.32 follows, so a full push gives no movement for at least 3 frames; with the decoder's spring the model gives 4 dead frames, 0.8 on the 7th, at most 0.94, and nothing at all for a flick under 4 frames | Observed (code), Inferred (model numbers) | 0x13c450, 0x13c970, 0x174ce0; `tools/pacing_sim.py stick` |
| L8 | A packet that brings no new frame is used only for the sender's reported lead and simulation frame and to reset the silence counter. Its acknowledgement, sync record and message blocks are not read | Observed | 0x13b7a4–0x13b7a8, 0x13b7f4–0x13b804 |
| L9 | Game messages are attached to an input frame only in a call where two sampled frames are still unsent. At one step per call that needs a call without a send before it, which the cycles 2, 4, 6 provide. A send cycle with a packet in every call would stop all game messages | Observed (rules), Inferred (consequence) | 0x1336c4–0x1336d4, 0x1341c0, table 0x4027e8 |
| L10 | The pacing counters and the peer fields they read are private to `net_main` and the packet receiver. The pacing constants can differ between machines without affecting the simulation. The cap must not be raised (raw relay depth 41, 8-bit header fields) | Observed | gxref on 0x4027a8–0x4027e8; writes 0x13b790, 0x13b7ac; 0x13c370 |
| L11 | Predicted input delay with the original constants: about 5 frames each for two players at 30 ms one way, 9 for three, 13 for four (send cycle 2, 4, 6 calls); 35 frames after any stall of half a second, lasting about 15 s after a one-sided event and 30 s after an outage; 36 frames for as long as a peer runs 10 % slow | Inferred (unvalidated model) | `tools/pacing_sim.py cases --brief`; docs/issues/lag.md section 5 |
| L12 | Predicted effect of the test patches: trim window 12 multiplies steady stalls by 3–6; cap 14 slows three- and four-player games and two-player games beyond about 60 ms; equalise duration 1 bounds the delay after every kind of stall at about 12 frames without slowing any modelled case | Inferred (unvalidated model) | docs/issues/lag.md section 6 |

## 11. How to check the model on two running copies

Follow `docs/VALIDATION.md` for the setup. The lead is `g_localInputFrame` (0x4027a4) minus
`g_netFrame` (0x4027ac), readable with the emulator's memory view on each machine;
`g_netStallCalls` (0x4027d0) is non-zero in a stalled call; 0x4027dc, 0x4027e0 and 0x4027e4
are the equalise and trim counters. Sample them once per picture if the tool allows, once a
second otherwise.

| Test | Model says |
|---|---|
| Two machines on one LAN, a minute of play | lead 1–2 on both, no stalls |
| Add 30 ms each way and 1 % loss with a traffic shaper | lead about 5 on both, drifting between 3 and 8; a stall every 3–4 s |
| Block all traffic for one second | both leads at 31–36 at once, then one frame less roughly every second for half a minute |
| Pause one emulator for one second | the other machine's lead at 31–36, then one frame less every half second |
| Run one emulator at 90 % speed for 30 s | the other machine's lead climbs to about 36 in under 10 s and stays |
| The last three with LAG-1 on the machine being watched | lead never above 10–13; back to normal within about 10 s |
| Four machines, any link | lead about 8 above the two-machine figure; LAG-3 on all four takes 3 off |
| Stick: film the screen at 60 pictures per second, push fully, count pictures to first movement, online and offline | 4 more online |

If the first two rows are off by more than a frame or two, the model is wrong in its
basics and nothing in section 6 should be trusted.

## 12. Not done, not known

- Nothing was run. The model's link (jitter and loss shapes) and its timing of a call are
  assumptions; real consoles and emulators may differ, for example in how many packets
  survive a freeze.
- Which frames `gfx_endFrame` counts as late was taken from `docs/mainloop.md`, not
  re-derived; the terrain-streaming path to half rate (22 frames) is not modelled.
- The CPU cost of sending more packets and of re-predicting a long lead after a rebase.
- Dropping a peer, the kick negotiation and FINDINGS L7 were not re-read or modelled; the
  remark in section 7 about leads at a drop rests on `docs/netcode.md`.
- Level loads (`net_flushBeforeLoad`, the wait for all peers) were not modelled. Correction
  C2 suggests that the flush cannot see acknowledgements from a peer that has itself
  stopped sampling and may then run to its limit of 121 passes; Inferred, not traced.
- The change that would let two players send every call (section 6.5) was reasoned about,
  not worked out as a patch.
- Whether movement speed or animation depends on the stick value above 0.94.
- Clock drift between machines is a parameter of the tool (`--drift`) but no case uses it.
