# Online quality: what ends a session, and what a player feels

Champions: Return to Arms, SLUS-20973 v2.00. Everything marked **Ran** was run on the rig
(`tools/rig/`, `docs/issues/live-rig.md`) with two, three or four machines: copies of one
Play! build, **not a PlayStation 2 and not PCSX2**, so timing statements are in frames and
calls of the game, not in a console's milliseconds. **Observed** = read in the executable at the address given.
**Inferred** = follows from those. **Unknown** = not established.

Local wrappers, scripts and logs are under `local/rig-out/oq/` (not in the repository):
`oq.py run NAME …` runs one pair and `oq.py multi NAME --n N …` two to four machines on the
private runner, with a per-frame log of the net state of every machine; `oq.py show NAME`
prints the changes, `oq.py sync NAME` compares the tick logs, `oq.py lag NAME…` and
`oq.py lagsum` give the figures of section 2. The runner used here is a private build
(`local/rig-build-oq/`, section 0). Four sections were added to
`patches/SLUS-20973_4028A55F.pnach` (1.7, 3.1, 3.2, 4.2; `tools/ee_tests.py` passes with
them, 222 checks). The ledger was not edited — proposed rows are near the end.

Status: all five parts have results. Not reached: a skill point spent, the workshop, a
pick-up of one player's dropped item by another, anything in PCSX2 or on a console
(the last section lists them). Every run can be repeated from `local/rig-out/oq/`
(`lines/*.rig` are the scripts, `oq.pnach` the test sections, `*.batch` the queues;
`oq.py batch FILE --budget 4` starts a queue's jobs while this work's live runners stay
within the budget).

## 0. Rig additions used here

Made in a private copy of the runner (`local/rig-build-oq/rig.cpp`, built from the
runner source as it stood before the `--arith` work that is going on in `tools/rig/rig.cpp`
at the same time; `local/rig-build-oq/apply.py` holds the edits as exact text replacements
so they can be merged). Not yet in `tools/rig/`.

| Addition | What it does |
|---|---|
| script command `freeze N` (use as `A: freeze N`) | this machine stands still for N frames of the others: nothing of it runs, the link stays in step, and what the others send waits in its socket queue — a stopped emulator, or a host that hung. The other machines see `wait N` |
| `--link` repeatable, `--machine A…D`, tags `C:` `D:` | three and four runners in one game, each pair joined by its own socket; all advance frame by frame together. **Ran**: `oq.py multi NAME --n 3\|4 --start` takes three and four machines from power-on through the developer LAN start into one game in `strife` (`g_numPeers` 3 and 4; addresses .134, .132, .130, .128 are slots 0–3) and leaves states at tick 660 (`local/rig-out/oq/states3`, `states4`) |
| `--link-keep-going` | a runner that ends is forgotten by the others instead of ending them (built; not used: a machine that leaves is left running, alone) |
| `--bus …,burstevery=F,burst=N` | nothing crosses for N frames out of every F (same phase on every machine: both directions fail together). **Ran** (path E of section 2) |

## 1. The "pause-menu kick"

### 1.1 In short

- The three pairs of the confirmation soak that ended with a drop while a pause menu was
  open (`docs/issues/live-rig.md` 22.3) were **the host's own "kick players" entry, chosen
  by random input** — not a time-out. **Ran** again with break points (1.2).
- **A game menu does not stop the network or the simulation.** With one machine's pause
  menu open for 22 s and then its inventory panel for 13 s, both machines ran one tick in
  every frame (1.3). On a console a menu cannot get a player dropped.
- **The one automatic drop is a silence time-out**: a machine that has accepted no packet
  from a peer in 901 calls of `net_main` in a row starts dropping it on the 902nd — 15 s at
  60 calls a second. It is decided by each machine alone, about each peer (1.4).
- What triggers it here is therefore **anything that stops the emulated machine for 15 s**:
  an emulator's own pause, a host that sleeps or hangs. Up to 14.7 s the session survives
  and stays in sync; from 15.1 s both players lose the game (1.5). A machine that is merely
  slow, or that stops and starts, is not dropped: every accepted packet resets the counter.
- **Softening, proven**: one word, the limit 900 → 1440 calls (24 s) (1.7).
- Looking for it turned up three things that do hurt a session, each with a section and a
  proof: the host's kick hangs everybody else in a three- or four-player game (4.2); a
  drop leaves the others with 38 frames of input delay (3.1); a level change can cost two
  seconds that are nobody's loading time (3.2).

### 1.2 The soak's kicks are the kick entry

Pair 072 of the soak (builds c0+c6, arena, seed 1772) run again with break points on
`net_kickPeer` 0x131cb8, on the first instruction of the silence path (0x13306c) and on the
opening and closing of the pause menu. **Ran**: machine B's pause menu opens at tick 13296
and stays open; at tick 13708 `net_kickPeer(1)` is entered from `pauseMenu_task`
(return address 0x18de18) and the menu closes; the silence path is never reached in the
pair (0 hits on either machine). The run ends as in the soak (13,050 ticks compared, drop
at 13713).

(The first such run's logs were deleted by mistake when a later run of this work was given
the same directory name; the run was repeated with the same command and gave the same
figures. The files in `local/rig-out/oq/kick/072-c0c6-drunare-bp/` are the second run's.)

**Observed**, how a player gets there:

- The pause menu's table (0x44f3b8) has a "kick players" record (0x44f418). It is hidden
  unless this is a net game, the local machine is the first active one
  (`net_localIsFirstActive` 0x13d668, test at 0x18ce18) and the level is not a medal
  mission (0x4f713c). So **only the host has it** — which is why every kick in the soaks
  was machine B's: B plays slot 0.
- Choosing it builds a list of the other active players (0x18dad8–0x18db40; row → slot in
  the byte table 0x7d8a18) and opens it with the cursor on the first of them
  (`menuList_setSelection(…, 1)`). Choosing a row calls `net_kickPeer` at once and closes
  the menu (0x18de04–0x18de18). **There is no confirmation**: from the kick entry, two
  presses of the confirm button kick the first other player.

So in real play this is a deliberate act of the host, four or five presses from the game;
random input finds it about once in forty long pairs.

### 1.3 Menus do not stall anything

**Observed**: the session loop calls `net_main(0,0)` once per displayed frame whatever is
on the screen (0x323248; `docs/mainloop.md` section 5); the pause menu, the inventory
panel and the shop are draw tasks, and none of them sets the pause flag in a net game
(their symbol notes: "`g_paused` only offline").

**Ran** (pair `menus`; the soak's section set; no bus delay): machine A's pause menu open
for 1,335 frames, closed, then its inventory panel open for 780 frames, machine B on
random input throughout.

| | machine A | machine B |
|---|---|---|
| ticks run while A's pause menu was open | 1,335 in 1,335 frames | the same |
| largest count of calls without a tick (`g_netStallCalls`) | 2 | 2 |
| largest silence counter held for the other machine | 4 | 4 |
| ticks compared, shared columns that differ | 3,579, none | |

The soak agrees in bulk: 5,511 inventory openings, 1,016 shop openings and the pause
menus of 120 pairs, and no drop that was not a kick.

Pair 072 with a per-frame log of the silence counters, through its level loads, saves and
menus: see 1.6.

### 1.4 The silence time-out, exactly

**Observed** (`net_main`, housekeeping, 0x133004–0x1330a8; it runs in every call, also in
the no-simulation calls around a level load):

- For every peer that is not the local one, not dropped and not already being kicked:
  read the counter at peer +0x44cc, store it back plus one, and if the value read was 901
  or more (0x133060, `slti v1,v1,901`) set the peer's kick state to 1, its drop frame to
  −1, and the negotiation state `g_netKickState` to 1.
- The receiver sets the counter to 0 for every packet it accepts from that peer
  (0x13b750). So the drop starts in the 902nd call after the last accepted packet.
- The counter counts **this machine's calls**, one per displayed frame: 15.0 s at 60
  frames a second, twice that on a machine whose display has gone to half rate.
- From there it is the kick negotiation of `docs/netcode.md` ("Drop"): every 30th
  displayed frame a request to every other active peer; with nobody else to ask the drop
  frame is set at the first such frame (newest frame received + 1), and the tick with that
  number marks the peer dropped and kills its character.
- Nothing is sent to the dropped machine: a peer being kicked is taken out of the send
  rotation, and the 4-byte notice 0xbd43 is sent only after a manual kick (the notice
  counter +0x44dc is set by `net_kickPeer` alone).
- **Who ends the game of a machine left alone** (this settles the open point in
  `docs/netcode.md`, "Drop", last item): `hud_run`, a run task, at 0x1db904: in a net game
  with `net_fewerThanTwoActive()` true, the game not completed and no countdown running,
  it sets `g_netExitCountdown` 0x4f6948 to 240. The HUD's draw task counts it down once
  per displayed frame, showing a box, and at 1 leaves network mode and sets
  `g_sessionExitCode` to 0xc9. A peer with a running kicked-notice counter does not count
  as active, so **a host that kicks the only other player starts its own countdown in the
  same frame**.

What else watches a stall (**Observed**, `net_main` 0x1343f0–0x134448 and
`hud_netStatusDraw` 0x1dbc48): `g_netStallCalls` counts calls in a row without a tick;
above 300 `g_netLongStallCalls` counts and the HUD blinks its no-connection picture; with
`g_netLongStallCalls` above 1200 (a stall of 1500 calls, 25 s) a lost-connection line or
box is shown; above 1800 (2100 calls, 35 s), or above 600 with the kicked flag 0x4027a0
set, **and more than two players**, the machine closes its menus and leaves the game.

### 1.5 A machine that stands still: 5, 14.7, 15.1 seconds, and stop-and-go

**Ran** with `freeze N` on machine A (slot 1) in `strife`, the soak's section set (LAG-1
on), no bus delay; frame numbers are the pair's.

| Pair | A stands still | Result | B: longest stall / silence counter / lead | Ticks compared afterwards |
|---|---|---|---|---|
| `fz300` | 300 frames (5 s) | session lives | 299 / 302 / 8 | 1,889, no difference |
| `fz880` | 880 frames (14.7 s) | session lives; B's no-connection picture was up for 579 frames | 879 / 882 / 8 | 1,889, no difference |
| `slow` | 8 × (200 frames still, 20 running) | session lives | 200 / 202 / 8 | 1,449, no difference |
| `fz905` | 905 frames (15.1 s) | **both lose the game** | below | — |

While A stands still B's world stands still too (lockstep), B's own character runs on in
prediction for 5 frames and then B stops taking input (LAG-1 holds it 5 above A's last
reported lead; without LAG-1 it would run to the 38-frame cap). When A runs again the
ticks resume in the same frame, and B's lead stays at 6–8 until the trim rule takes it
back.

`fz905`, machine B (kept running), frames after A stopped:

| Frame | What |
|---|---|
| +901 | silence counter 902: kick state 1, drop frame −1 |
| +917 | the drop is executed (next 30th displayed frame): A's character dies, B plays on; a box says the player has been disconnected and the game is returning to the main menu, and a line says A has left |
| +1156 | 239 frames later: network mode off, session exit code 0xc9 |

Machine A, once running again: it reads what B had sent up to the start of the kick, runs
8 ticks on it, and then hears nothing. Its world stands still for 902 calls (the
no-connection picture from call 301), then it drops B the same way (drop executed 15
frames later, the same box, out 239 frames after that) — 19 s after it came back.

**A manual kick, two players** (`mkick`: the four writes of `net_kickPeer` made on the host
in one frame). Host: drop executed 17 frames later; its own exit countdown starts in the
frame of the kick, so **the host is back at the front end 240 frames after kicking its
only partner**. Kicked machine: twelve notices, one every 10 frames; its world stands
still at once; from stalled call 301 on a line says it was kicked; at call 902 it drops
the host, and it is out 19.3 s after the kick. (With more than two players the kicked
machine leaves earlier, by the HUD rule above: 900 stalled calls.)

### 1.6 A whole soak pair: how close ordinary play comes to the limit

**Ran**: the same pair 072 with the silence and stall counters logged in every frame, both
machines: 14,036 frames, three level changes (`strife` → arena → `hub` → arena), three
saves, 50 pause-menu openings, the inventory and a shop, no bus delay.

| | machine A | machine B |
|---|---|---|
| largest silence counter held for the other machine | 132 (frame 8710, just after the load of the arena) | 122 (frame 8507, just after the load of `hub`) |
| largest count of calls without a tick | 133 | 123 |

So nothing in ordinary play comes near 901: menus and saves leave the counters at 1–4,
and the largest values, 122–133, belong to level changes. They are not loading time: they
are the wait of section 3.2, a machine that sat out all 121 passes of the flush before
its load while the other had already loaded.

### 1.7 Softening: the limit 900 → 1440 calls

Why a longer limit and nothing cleverer: a stopped emulator and a dead console look the
same from outside, so the only dial is how long the others wait. Why 1440 and not more:
the HUD's own rules stay untouched and unseen — the lost-connection line needs 1500
stalled calls, and with more than two players a machine leaves the game after 2100, so a
limit above about 2000 would make three- and four-player games end for everybody when one
console dies, instead of dropping it and going on. The price: when a peer really is gone
the others wait 24 s instead of 15 (the host can use the kick entry sooner), and a
machine that comes back too late sits for 24 s before it is put out.

```
[Net test: peer silence time-out 900 -> 1440 calls]
// was: 28630385 (slti v1,v1,901)
patch=1,EE,00133060,word,286305A1
```

It is per machine (each machine decides alone when to start a drop; the drop frame is
still agreed), so players need not match on it; a machine without it simply starts the
drop earlier.

**Ran**, the soak's section set plus this one, machine A standing still:

| Pair | A stands still | Without the section | With it |
|---|---|---|---|
| `fz880` / — | 880 frames | lives | — |
| `fz905` / — | 905 frames | dropped at call 902 | — |
| — / `p1300` | 1300 frames (21.7 s) | (dropped, as 905) | **lives**: B's stall 1299, silence counter 1302, `g_netLongStallCalls` 999 (no lost-connection line); 1,589 ticks compared afterwards, no difference |
| — / `p1500` | 1500 frames (25 s) | (dropped) | dropped at call 1442 on B, executed 16 frames later, out 239 frames after; A the same after its own 1442 calls; `g_netLongStallCalls` peaked at 1154, below the line's 1200 |

**Three machines** (`drop3`, `drop3p`; section 4.1): with a third machine standing still
the other two start the drop in calls 902 and 1442, agree on the drop frame 51–53 frames
later, and play on in sync. With the longer limit the stall reached 1458 and 1484 calls on
the two machines, 16 short of the 1500 at which the lost-connection line appears: the
negotiation takes one to two rounds of 30 frames, so **in a three- or four-player game the
line can show for a moment** before the drop when a round is lost or falls badly. It is a
line of text; 1380 instead of 1440 would keep a full second of margin if that matters.

Not done for this section: PCSX2.

**A variant for two-player games only, not built**: with two players nothing is gained by
dropping a silent partner (the game ends either way), so the limit could be much longer
there. A version that picks the limit from `g_numPeers` needs seven words in the loop's
set-up (0x133010–0x13302c, 0x133058, 0x133060, 0x133084); sketched, not written or run.

## 2. The lag sections live (LAG-2, LAG-3, LAG-4)

**About time.** The runners are frame-locked: every machine of a game advances one
emulated frame, exchanges its datagrams, and waits for the others, and the path model
(delay, jitter, loss, bursts) counts frames. Nothing here depends on how fast the host
ran — it ran between one and thirty frames a second per runner while this was measured —
so **every figure is a count of frames or of `net_main` calls, never measured seconds**;
where seconds are written they are frames ÷ 60, what a machine running at full speed
would see. What this cannot show is exactly what real time adds: two hosts that do not
keep the same pace (`docs/issues/lag.md` 5.3).

### 2.1 What was run

59 games of two, three and four machines from the states of section 0, the soak's
sections with LAG-1 taken out as the base, 1,500 frames of random movement and fighting
each (2,400 for the two-machine games without delay and on path B). Figures are from the
frames after the first 300 and before the first level change (a level change's waits are
3.2's subject), 900–2,200 frames per machine: **the leads are firm, the stall rates are
from one short run each and are rough**.

*Lead* = newest input frame minus simulation frame at the end of a call: the game's own
input delay, in frames. *Stalls* = calls in which no tick ran (`g_netStallCalls` went up),
per 3,600 calls — each is one frame in which the world stands still. Means over the
machines of a game.

| Path | One way, frames | Loss |
|---|---|---|
| A | 1 | none |
| B | 2–3 | 1 % |
| C | 6–8 | 2 % |
| D | 9–12 | 5 % |
| E | as B, and nothing crosses for 30 frames out of every 900 | 1 % |

### 2.2 Two machines: LAG-2

| Path | base: lead / stalls | LAG-1 | LAG-1 + LAG-2 |
|---|---|---|---|
| A | 3.0 / 0 | 3.0 / 0 | 4.0 / 0 |
| B | 5.1 / 29 | 5.0 / 30 | 5.8 / 3 |
| C | 10.2 / 21 | 10.1 / 22 | 10.9 / 1 |
| D | 15.0 / 18 | 14.5 / 21 | 15.4 / 11 |
| E | 21.1 (most 32) / 38 | 6.2 (most 12) / 93 | 7.0 (most 13) / 84 |

- **LAG-2** does what its description says, a little dearer than the model had it: on a
  steady link nine tenths of the one-frame freezes go (30 → 3, 22 → 1 a minute; half of
  them on the worst path) for **0.8 to 1.0 frame** more delay (the model: 0.7).
- **LAG-1** changes nothing on a steady link and everything after an outage (2.4).

### 2.3 Three and four machines: LAG-4 and LAG-3

| Machines, path | base | LAG-1 | LAG-1 + LAG-4 (three) / LAG-3 (four) | … + LAG-2 |
|---|---|---|---|---|
| 3, A | 4.8 / 4 | 4.8 / 4 | 4.6 / 5 | 5.0 / 3 |
| 3, B | 9.0 / 36 | 8.7 / 50 | 7.4 / 27 | 7.6 / 21 |
| 3, C | 14.0 / 36 | 14.1 / 44 | 12.7 / 33 | 13.1 / 21 |
| 3, D | 18.6 / 30 | 18.8 / 31 | 16.7 / 30 | 17.4 / 16 |
| 3, E | 19.8 (most 26) / 85 | 9.6 (13) / 108 | 8.2 (11) / 95 | — |
| 4, A | 7.4 / 8 | 7.1 / 4 | 5.3 / 10 | 6.2 / 8 |
| 4, B | 12.0 / 45 | 11.8 / 39 | 8.9 / 36 | 9.4 / 25 |
| 4, C | 17.6 / 41 | 17.5 / 45 | 14.5 / 39 | 14.7 / 35 |
| 4, D | 19.0 / 266, the game at 92.6 % speed | 19.0 / 266, 92.6 % | 18.7 / 76, 97.9 % | 18.8 / 75, 97.9 % |
| 4, E | 20.0 (most 27) / 73 | 12.6 (19) / 110 | 10.9 (15) / 106 | — |

- **LAG-4** takes 1.3–2.1 frames off the delay of a three-player game, **LAG-3** 1.8–3.0
  off a four-player game (the model: 9.4 → 7.7 and 13.3 → 10.0 on a 30 ms link; here 8.7
  → 7.4 and 11.8 → 8.9 on path B), with the same or fewer stalls.
- **Four players on the worst path run into the cap**: the lead cannot pass about 20 (38
  minus the age of the slowest machine's report), one call in fourteen runs no tick and
  the game runs 7 % slow. LAG-3 makes the reports fresher and takes that back to 2 %.
- With the shorter cycles **game messages still go through**: `fuzz4r` and `fuzz3r` (4.1)
  ran the full input mix with them — 78 and 76 inventory messages, item drops and
  pick-ups, level changes, on every machine alike.

### 2.4 After an outage (path E)

Lead at its highest after each 30-frame outage, and frames until it is back within one
frame of the same arm's steady value:

| Machines | base | LAG-1 | LAG-1 + LAG-4 / LAG-3 (LAG-2 for two) |
|---|---|---|---|
| 2 | 33; not back in the 1,423 frames left | 8–12; back in 130–382 | 9–13; 131–382 |
| 3 | 28–32; not back in 1,508 | 11–13; 89–373 | 10–13; 150–465 |
| 4 | 25–27; 609–857, or not within the run | 14–17; 79–363 | 13–15; 206–552 |

### 2.5 Sync

Every game of the matrix, and every other run of this work, was compared tick by tick,
machine against machine: 107 runs, 200 pairs of machines, 351,603 ticks. No shared column
differs anywhere except where a difference is the point (a machine against one it has
dropped or that has left) and in the two level-up bookkeeping bytes of 4.3.

### 2.6 Recommendation for the suggested set

- **LAG-3 and LAG-4: yes.** Two to three frames (30–50 ms) less delay with four players,
  one to two with three, nothing lost in any run.
- **LAG-2: yes, by a small margin**, and mostly for two players: a tenth of the one-frame
  freezes for one frame of delay that the player's own character, being predicted, does
  not show.
- **The three sections of 3.1, 3.2 and 4.2: yes** (4.2's on every machine).
- The time-out section of 1.7 is in already.

## 3. What a player feels

### 3.1 After a drop in a three- or four-player game: 38 frames of input delay

**Observed** (`net_main` 0x133398–0x1333fc): the loop that finds the smallest lead and the
slowest simulation frame among the other machines — the two figures the equalise rule
and the cap work from — skips a peer that is local, dropped, **or being kicked** (kick
state +0x44d6 not 0). So from the call in which a drop starts to the tick that carries it
out, one to two rounds of 30 calls, the remaining machines are bounded only by each
other, the simulation stands still, and each samples a frame per call up to the cap of 38.
Afterwards they all have the same lead, the equalise rule (LAG-1 or not) has nothing to
do, and only the trim rule takes it back: one frame per 62 calls.

**Ran** (three machines, machine C standing still; four machines, the host kicking one;
the soak's sections; lead of the machines that go on):

| Run | Lead at the drop | 120 / 300 / 600 frames later |
|---|---|---|
| `drop3` (C silent) | 38, 38 | 35 / 32 / 29 on both; 26 after 879 frames |
| `drop3k`, the same with the section below | 15, 13 | 14 / 11 / 9 and 12 / 9 / 7; 6 and 4 after 879 |
| `kick3a` (host kicks C; without the section below) | 37, 33 | 19 / 19 / 14 and 19 / 20 / 15 |
| `kick3ak` (with it) | 13, 16 | 12 / 9 / 4 and 16 / 13 / 8 |
| `kick4ak` (four machines, with it) | 17, 18, 15 | 16 / 13 / 14, 18 / 16 / 15, 14 / 11 / 11 |

**The section** leaves the peer in the two comparisons until its drop frame is set
(+0x44d8 above 0: the field is 0 for a peer in good standing, −1 while the drop is being
negotiated, the frame afterwards), so the stale lead it last reported keeps bounding the
others exactly as it did during the silence before:

```
[Net test: a peer being dropped still bounds the input lead]
// was: 80E20006 (lb v0,6(a3)), 1440000F (bnez v0,0x1333f4)  now: lw v0,8(a3); bgtz v0,0x1333f4
patch=1,EE,001333B0,word,8CE20008
patch=1,EE,001333B4,word,1C40000F
```

Why it cannot hold a machine back from the drop: nothing has to be sampled while the
negotiation runs, and once the drop frame is set the peer is skipped as before; the tick
with that number is the one the machine is already waiting at. Without LAG-1 the lead is
at the cap before the drop starts and the section changes little (`drop3k-noL1`: 28 and
30 at the drop). In sync afterwards in every run (993, 1,154, 840 and 842 ticks compared).

### 3.2 A level change: two seconds of standstill that are nobody's loading time

**Observed** (`net_flushBeforeLoad` 0x132db0): before it loads, a machine calls
`net_main(1,1)` — no simulation, no new input — until every other machine has
acknowledged its input up to `g_netFrame` (peer +0x44c0), at most 121 times. And
(FINDINGS L8) an acknowledgement is only read from a packet that brings a new input
frame, which a machine in this loop no longer sends.

**Ran** (pair `hop2-c0-base`, the fourth of six level changes, no bus delay): machine A,
lead 5, has its input acknowledged, makes no pass at all and starts loading in frame
2102. Machine B, lead 2, has sampled frames 2201 and 2202 in the last two calls; A never
acknowledged them and is now silent. B makes all 121 passes, loads 121 frames after A,
and A — loaded — waits for B. Both stand still for about 125 frames more than the load
takes. It is the machine with the smaller lead that waits, and the smaller the leads the
likelier: it is a good-link problem.

Six level changes written into one tick on every machine, random input between them:

| Run | Path | Level changes with a standstill of 60 frames or more | Longest | With the section: such changes / longest |
|---|---|---|---|---|
| `hop2-c0` | 2 machines, no delay | 3 of 6 (123–144 frames) | 144 | 0 of 6 / 40 |
| `hop2-c1` | 2 machines, 2–3 frames, 1 % loss | 2 of 6 (117–125) | 125 | 0 of 6 / 47 |
| `hop2-c2` | 2 machines, 6–8 frames, 2 % | 0 of 6 | 38 | — |
| `hop2-c3` | 2 machines, 9–12 frames, 5 % | 0 of 6 | 39 | 0 of 6 / 50 |
| `hop4-c1` | 4 machines, 2–3 frames, 1 % | 3 of 6 (123–137), on all four | 137 | 0 of 6 / 47 |

The same wait is in the other runs of this work wherever random input walked through a
level exit (`lag2-none-c1` 123 frames, `lag4-L1-c1` 125–135, `leave4` 119–125) and in the
soak pair of 1.6.

**The section**: every machine makes at least 16 passes, and then waits until each other
machine has *reported the simulation frame of the level change* (peer +0x44c8, read from
every accepted packet, new frame or not) instead of waiting for an acknowledgement:

```
[Net test: flush before a level load waits for the peers' tick]
// was: 0000302D (move a2,zero), 8C82FFF0 (lw v0,-0x10(a0))  now: slti a2,s0,16; lw v0,-8(a0)
patch=1,EE,00132DFC,word,2A060010
patch=1,EE,00132E28,word,8C82FFF8
```

A machine that reports that frame has run the tick that set the level, so it holds
everything it needs from us; the 16 passes are there so that the last machine to arrive —
which finds everybody else already there — still sends its own report to each of them
(a peer is served every 2nd, 4th or 6th call) before it goes silent. The 121-pass limit
stays. Cost: 16 frames at every level change. All runs in sync (3,189, 3,148, 3,087 and
3,098–3,103 ticks compared).

Tried first and **not** kept: letting the passes sample input (0x132e5c, `net_main(1,0)`),
so that the flush packets carry new frames and their acknowledgements are read. It does
nothing for the machine whose partner made no pass at all (`hop2-c0-flush`: 3 of 6, as
without), is worse with four (`hop4-c1-flush`: 4 of 6) and raises the lead.

### 3.3 The delay itself, and what was tried to shorten it

With the set recommended in 2.6, lead in frames (÷ 60 for seconds at full speed): the
time between a press and its effect on anything but the presser's own predicted
character.

| Path (one way) | 2 players | 3 players | 4 players | unpatched, 2 / 3 / 4 |
|---|---|---|---|---|
| A (1 frame) | 4.0 (67 ms) | 5.0 (83 ms) | 6.2 (103 ms) | 3.0 / 4.8 / 7.4 |
| B (2–3 frames, 1 %) | 5.8 (97 ms) | 7.6 (127 ms) | 9.4 (157 ms) | 5.1 / 9.0 / 12.0 |
| C (6–8 frames, 2 %) | 10.9 (182 ms) | 13.1 (218 ms) | 14.7 (245 ms) | 10.2 / 14.0 / 17.6 |
| D (9–12 frames, 5 %) | 15.4 (257 ms) | 17.4 (290 ms) | 18.8 (313 ms) | 15.0 / 18.6 / 19.0 |

It is the path's delay with its jitter, plus the send cycle, plus about two frames; the
sections cannot take the first part away. (The stick codec's own dead frames, FINDINGS
L6, come on top for movement and were not measured again.)

Two further constants, pacing only like the others, **tried and not recommended**:

| Change | Two machines, path B and D: lead / stalls | Four machines, path B (with LAG-3) |
|---|---|---|
| trim window 62 → 31 calls (0x1335C0, 2863003D → 2863001E) | 4.7 / 32 and 14.1 / 22 against 5.0 / 30 and 14.5 / 21 | 8.2 / 64 against 8.9 / 36 |
| equalise threshold 5 → 3 (0x13354C, 2A240005 → 2A240003) | 4.9 / 23 and 14.4 / 32 | 8.6 / 46 |

A third to two thirds of a frame, paid for with more stalls where there are four.

## 4. Coverage the soak did not have

### 4.1 Three and four machines; a player leaving; a player going silent

All on the developer LAN start, default characters, `strife`, the soak's sections;
comparisons are of the tick logs, pair by pair (position, facing, action state, hit
points, mana, gold, experience, the three bags, statistics, points, equipment and skills
of every player, the shared seed, the quest variables).

| Run | What | Result |
|---|---|---|
| `leave3` | 3 machines; C leaves (its exit countdown started as the pause menu's exit entry starts it) | A and B mark it dropped 11 frames later and play on; 1,023 ticks compared, no difference |
| `leave3h` | 3 machines; the host (slot 0) leaves | the two others mark it dropped 7 frames later; 1,037 ticks, no difference |
| `leave4` | 4 machines; D leaves, 500 frames later the host leaves | each time the others play on; A–C 1,115 ticks, no difference (A–B to the host's leaving, 498) |
| `drop3` | 3 machines; C stands still | A and B start the drop in calls 902 (frames 1200, 1202), carry it out in the same tick 51–53 frames later, play on; 993 ticks, no difference |
| `drop3p` | the same with the 1440 limit | drop started in call 1442; 953 ticks, no difference |
| `fuzz4n` | 4 machines, 2–3 frames of delay, 1 % loss, 6,000 frames of the soak's full input mix without the pause button, all sections of this work on | 5,180 ticks compared A–B, A–C, A–D: no difference. Three level changes, 5 drops and 5 pick-ups, 53 inventory messages |
| `fuzz3n` | 3 machines, 6–8 frames, 2 % loss, the same | 5,766 ticks, no difference; 4 drops, 4 pick-ups, 76 inventory messages |
| `fuzz4r`, `fuzz3r`, `fuzz2r` | 4, 3 and 2 machines, 2–3 frames, 1 %, the same input, the set recommended in 2.6 (LAG-1, LAG-2, LAG-3 or LAG-4, the four sections of this work) | 5,205, 5,794 and 5,642 ticks, no difference; 78, 76 and 44 inventory messages, 6, 4 and 5 drops, 5, 3 and 2 pick-ups, 3, 1 and 2 level changes with no standstill above 41 frames |

**Joining late** does not exist: the peer table is filled once, at the end of the launch
(`docs/netcode.md`, "Launch"; `g_numPeers` is written only there, by the developer lobby
and at shutdown), and nothing in the lockstep can add a machine. Not run because there is
nothing to run.

### 4.2 The host kicks a player in a three- or four-player game: everybody else hangs

This is FINDINGS L7, the second half, on the running game.

**Ran** (`kick3`, `kick4`: the writes of `net_kickPeer` made on the host in one frame):

| | 3 machines | 4 machines |
|---|---|---|
| host | carries the drop out 52 (32) frames later, plays on for 38 (33) ticks, then stands still | |
| every other machine that stays | is told by the host's request, answers it, sends its own request 30 frames later — and **gets no answer**: the host has dropped the player by then, and answers only for a peer it has not yet dropped (0x13c2f0). It never gets a drop frame; its ticks stop at 966 | both of them |
| the kicked machine | told (the notice), stands still, leaves by the HUD rule after 900 stalled calls | the same |

At the end of the runs, 900 frames on, nobody has moved; they keep exchanging packets,
so no silence time-out ends it. (By the HUD rule of 1.4 they would leave the game after
2,100 stalled calls; not run that far.) On the rig the machines' displayed-frame counters
are in step, which is the worst case — the second request leaves exactly as the host
finishes; on real machines the order depends on the phase of the two counters
(`docs/spec/net-wire.md` 12.3 puts it at a few per cent of kicks). A silent player's drop
does not go this way when all the others time out within the same 30 calls (`drop3`).

**The section** makes the answer unconditional:

```
[Net test: kick request is answered for a peer already dropped]
// was: 1440002F (bnez v0,0x13c3b4)  now: nop
patch=1,EE,0013C2F4,word,00000000
```

The relay it then sends is the dropped player's last 41 frames, which the answering
machine still holds; the asking machine ends up with the same newest frame, sets the same
drop frame and carries the drop out in the same tick as the host did.

| Run | Result |
|---|---|
| `kick3a` | the second machine drops the player 30 frames after the host; both play on; 966 ticks compared, no difference |
| `kick3ak` (with the section of 3.1 as well) | the same; 1,154 ticks, no difference |
| `kick4ak` | both other machines drop the player 30 frames after the host; A–B 840 ticks, A–D 842, no difference |

### 4.3 Points, items

| Run | What | Result |
|---|---|---|
| `spend2`, `spend3` | 2 machines, real characters, a level-up left pending on both players (acknowledged level below the level, stat and skill points written in one tick on both machines); the level-up page opens and stat points are spent by scripted presses | `inventory_onStatPoint` entered 30 and 6 times on each machine; statistics, skills and everything else agree throughout (3,261 and 2,845 ticks). The points column differs from the tick in which the page opens — the two level-up bookkeeping bytes +0xed/+0xee of FINDINGS V48, written on the owner's machine, local as recorded there; slot 0's are equal again once its last point is spent |
| the same | the skill page that follows (`skills_screen` ran 701–2,041 times per machine) | **no skill point was spent**: none of the scripted presses took one, and the page shows no text to steer by. Not reached |
| `trade`, `points` | 2 machines, real characters standing together, 4,000 and 3,600 frames of inventory-heavy random input | 4,179 and 3,817 ticks, no difference; 4 drops, 30–43 inventory messages; no pick-up by the other player happened |
| the workshop | — | **not reached**. What was found: it is entered from the item list, by choosing an item whose descriptor has flag bit 35 set (`itemList_input` 0x1cd988 state 3 → `workshop_input` 0x1d0b90); the rig's characters own no such item |
| buying, selling | — | not run again here: 88 purchases and the sales among 2,932 drops are in the confirmation soak |

## 5. The two weapon-trail bytes (FINDINGS V63)

Record +0x4ac5 / +0x4ac6 (and +0x4b05 / +0x4b06 for the second weapon) are bytes +0x3d
and +0x3e of the two 0x40-byte trail blocks at record +0x4a88 and +0x4ac8.

**Everything in the executable that touches the two blocks** (**Observed**: every
instruction that forms the address of a block or of a byte in it — the absolute form
0x4dd578 / 0x4dd5b8 plus slot × 0x4c30, the record-relative form +0x4a88 / +0x4ac8, and
the displacements 0x4ac5, 0x4ac6, 0x4b05, 0x4b06 — searched in the disassembly, and
`tools/fieldxref.py 4a88-4b07 --static 0x4d8af0,0x4c30,4`):

| Code | What it does with them |
|---|---|
| `Player_ctor` 0x1a2460–0x1a2488 | clears both blocks (two `memset` of 0x40) when the player object is built |
| `Player_meleeHit` 0x1b70d8, 0x1b70f8, 0x1b7118 | **stores only**: +0x3d = what was hit (0–3, from the target's flags), +0x3e = 5 |
| `Player_weaponTrails` 0x1bc914, 0x1bca4c, 0x1bcb7c | hands the block to `fx_modelStatusEffects` 0x1f6ac8 — the only place the bytes are read one by one |
| `player_importCharacter` 0x1bd9b8–0x1bda90 | **stores only**: copies both blocks from the character data being imported |
| whole-record copies (0x4c30 bytes: the launch transfer, the card save's pack and unpack, the saved copy and its restore) | carry them along with everything else |

**What the one reader does with them** (**Observed**, `fx_modelStatusEffects`, the part
for a weapon, decompile lines 570–890): +0x3c counts up to 100 while the weapon swings
and gives the trail its length; while +0x3e is not zero and the local decal-detail option
0x44fdc0 is above 0 it spawns spark particles (`particle_spawn` 0x18f3f8, one of three
particle definitions chosen by +0x3d) and counts +0x3e down; otherwise it clears both.
Nothing else is computed from them. Particles are the per-machine effect pool with the
cosmetic seed.

**They are in neither check** (**Observed**): the sync hash is the shared seed plus the
players' positions; `player_checksum` 0x1bdc98 mixes record +0x20–0x23, +0x58, +0x59,
+0x5c–0x5f, +0x90–0xa7, +0xc0–0xcb, +0xe4–0xeb, +0x3748–0x41cf and +0x43f0–0x4433, and
the trail blocks lie outside all of them. So the lobby's checksum exchange cannot trip
over them either.

**Why they differ** is `docs/issues/live-rig.md` 22.4: the trail code runs for the real
player on other machines and for the prediction copy on the owner's, at different ticks.

So: local by construction, no reader in the simulation, nothing to fix. The stored
character carries them (a save holds whatever the saving machine had), and the next game
clears them when the player object is built.

**Ran** (pair `trailforce`): real characters in the arena, 3,500 frames of random play
with melee, the four bytes written to fixed values on machine A in every tick (on A the
sparks therefore never stop; on B the game set the bytes itself 26 times). 5,071 ticks
compared: the bytes differ on 3,375 (slot 0) and 3,727 (slot 1) of them and **no shared
column differs on any**. A reader in the simulation would have had every chance.

## Proposed ledger rows

| Row | Text |
|---|---|
| L (new) | The session-ending drops of the confirmation soak were the host's pause-menu kick entry chosen by random input, not a time-out: **Ran** twice with break points (pair 072: `net_kickPeer` entered from `pauseMenu_task`, return address 0x18de18; the silence path 0x13306c never reached). The entry exists on the first active machine only (0x18ce18) and has no confirmation. `docs/issues/online-quality.md` 1.2 |
| L (new) | A game menu does not stop the network: **Ran**, one machine's pause menu open 1,335 frames and its inventory 780, one tick per frame on both machines throughout, silence counter never above 4; over a whole soak pair the largest silence counter is 132, at a level change. `docs/issues/online-quality.md` 1.3, 1.6 |
| L (new) | The silence time-out, measured: a machine standing still for 300 and 880 frames is kept and the pair stays in sync; for 905 frames it is dropped in the other's 902nd call (0x133060), executed 16 frames later, the lone machine's game ends 239 frames after (`hud_run` 0x1db904 starts `g_netExitCountdown` at 240), and the returning machine goes the same way after its own 902 calls. Stop-and-go (8 × 200 frames still) is not dropped. With three machines the two others drop the silent one in the same tick and stay in sync. `docs/issues/online-quality.md` 1.4–1.5, 4.1 |
| L (new) | Section "peer silence time-out 900 -> 1440 calls" (0x133060): **Ran**, a machine standing still 1300 frames is kept (in sync afterwards), one standing still 1500 is dropped at call 1442. With three machines the stall reaches 1458–1484 calls before the drop is carried out, 16 short of the HUD's lost-connection line. Per machine. `docs/issues/online-quality.md` 1.7 |
| L7 (add) | **Ran** on three and four machines: after the host's kick every other machine's request goes unanswered (0x13c2f0) and all of them stand still for good; on the rig, whose frame counters are in step, in every kick. Section "kick request is answered for a peer already dropped" (0x13C2F4 → nop): the others drop the player 30 frames after the host and play on in sync (966, 1,154, 840 ticks compared). `docs/issues/online-quality.md` 4.2 |
| L (new) | While a drop is negotiated the peer being dropped no longer bounds the others (0x1333b0–0x1333b4), who run to the 38-frame cap and then drain at one frame per 62 calls: **Ran**, lead 38 at the drop and 29 ten seconds later on both remaining machines. Section "a peer being dropped still bounds the input lead": 15 and 13 at the drop, 9 and 7 ten seconds later. `docs/issues/online-quality.md` 3.1 |
| L (new) | `net_flushBeforeLoad` waits for acknowledgements that a machine already loading never sends: the machine with the smaller lead sits out 121 passes and the others wait for it after their load. **Ran**: 2–3 of 6 level changes on good links (two and four machines), 117–144 frames each. Section "flush before a level load waits for the peers' tick" (0x132DFC, 0x132E28): 0 of 6, longest 47. `docs/issues/online-quality.md` 3.2 |
| L11, L12 (add) | Live figures for the lag sections, frame-locked runners, 59 games: LAG-2 on a steady two-player link 30 → 3 and 22 → 1 stalls a minute for 0.8–1.0 frame of lead; LAG-4 −1.3 to −2.1 frames with three players, LAG-3 −1.8 to −3.0 with four; four players at 9–12 frames one way run into the cap (92.6 % speed) and LAG-3 brings that to 97.9 %; after a 30-frame outage the lead peaks at 25–33 unpatched and 8–17 with LAG-1. All in sync. `docs/issues/online-quality.md` 2 |
| V63 (replace the last sentence) | The only code that reads the two bytes is `fx_modelStatusEffects`, to time and choose spark particles; `Player_meleeHit` and `player_importCharacter` only store, `Player_ctor` clears. Not in the sync hash, not in `player_checksum`. **Ran**: forced to other values on one machine in every tick of a 5,071-tick melee pair, no shared column differs. Local. `docs/issues/online-quality.md` 5 |
| V (new) | Coverage added: stat points spent (36 calls of `inventory_onStatPoint` per machine in two pairs, in sync but for the V48 bytes); a player leaving in three- and four-machine games, the host leaving, two leaving in turn (in sync, 1,023–1,115 ticks); four- and three-machine games on the full input mix with the recommended set (5,205 and 5,794 ticks, no difference). Not reached: a skill point, the workshop, a pick-up of another player's drop. `docs/issues/online-quality.md` 4 |
| V (new) | `docs/netcode.md` "Drop", last item: the caller of `net_fewerThanTwoActive` that ends a lone machine's game is 0x1db904 in `hud_run` (countdown 240 displayed frames, then exit code 0xc9); a host that kicks its only partner ends its own game that way |

## Not done

- A skill point spent: the skill page opens after the stat points (`skills_screen` ran
  thousands of times, in sync) but no scripted press took a point, and the page shows no
  text to steer by. Needs the page's input code read, or a picture (`--video`).
- The workshop: needs a character with an item whose descriptor has flag bit 35, and gems.
- One player picking up what another dropped: drops and pick-ups happened (up to 6 and 5
  per game, on every machine alike), but whose item was picked up was not followed.
- The memory-card screens and a system dialog with the other machine playing (1.3 has the
  pause menu and the inventory; the soak has the shop).
- The two-player-only longer time-out of 1.7; a confirmation for the kick entry.
- Stall rates over long runs: each figure of section 2 is one run of 900–2,200 frames.
- Two hosts that do not keep the same pace, and everything on PCSX2 or a console: the
  runners here are frame-locked copies of one Play! build.
