# A soak farm on the native build

Started 2026-10-12. The native build with its network (`docs/issues/native-net.md`) runs a
two-machine lockstep game many times faster than the emulator rig and has been shown to
compute what the emulator computes. This file is the farm built on it to hunt for the
desyncs that are left: the method, what was covered, what was found, and at what rates.
Every result says what was **Ran**; **Read** marks what comes from reading code alone.

**Status: first part ended 2026-10-12 22:45. A second part (2026-10-13, below: "Second part") takes findings 2 and 3 to the bottom, corrects finding 3's reading of seed 5000 and proposes three sections; its status is at its head.**

## In short

- **7.91 million lockstep ticks with fixes on, no desync.** The suggested set as it will
  ship — the 25 other sections plus the flush section in the three-word form proposed
  here — played 122 games of two, three and four machines, 7,792,955 ticks, and no
  column that decides differs for a reason that is the set's; a further 120,340 ticks
  with the 25 alone. That is one and a half times the rig's largest soak (5.1 million),
  on new input, with a check of every pool object that the rig's soaks did not have.
- **One fault found, and it is in the fix set, not in the game**: the section "flush
  before a level load waits for the peers' tick", as first written, leaves both players'
  lockstep input stuck from the launch on in the developer LAN start (finding 1). Cause:
  one delay slot. A three-word form is proposed, executed in `tools/ee_emu.py` and run
  on a native pair and on an emulator-rig pair.
- **Two known mechanisms seen live for the first time**, both silent and neither a new
  cause: a draw-time jump-gate prompt that appends a quest variable on the owner's
  machine four ticks early (finding 2, `docs/script.md` P1), and the half of ledger row
  B9 that the save-point section does not cover — `Savepoint_interact` runs on one
  machine only (finding 3). Neither reached a player, a monster or the shared seed.
- **The method sees what it should**: without fixes 19 of 22 games differ, most of them
  ending in the game's own out-of-sync message, in the columns of the known classes.
- Three differences the farm reported were the comparison's own doing and are explained
  below ("Differences reported").
- The aim of tens of millions of ticks was not met: the machine was at load 100–450 from
  other work for most of the day and a pair made 60–500 ticks a second instead of 1,000.

## Method

### Programs

`tools/recomp/soak/build_soak.py` builds `local/recomp-out/soak/bin/rta_soak-<name>`: the
translated game, the runtime and `tools/recomp/net/netshim.cpp` exactly as
`build_net.py --wrap-memory` links them, plus `tools/recomp/soak/soakhooks.cpp`. Nothing
under `tools/recomp/net` or `tools/recomp/rt` is changed:

- the shim is compiled with the name of the function its tick hook calls changed
  (`-Dorig_003226e4=soak_tasks_run`), so the hooks run between the game's task pass and
  the shim's tick-log row;
- the generated code is compiled against a copy of `rt/recomp.h` (written to
  `local/recomp-out/soak/inc-count/`, first on the include path) whose `CALL` and `CALLR`
  macros also count the call by target address: every run leaves a table of how often
  each function was entered, which is where the coverage figures come from. A second
  copy (`--instrument trace`) keeps a shadow call stack and compares watched memory at
  every call and return, which names the function that writes a word;
- the runtime is linked from objects frozen at the first build (`--rt frozen`), because
  its sources were being changed by other work during the soak. Frozen: `runtime.cpp`
  sha1 a23ce0e2…, all runtime sources and headers 1217933f….

| Program | Sections |
|---|---|
| `rta_soak-fix26c` | the 26 of `tools/play-net/sections-suggested.txt`, with "flush before a level load waits for the peers' tick" in the three-word form proposed in finding 1 (`build_soak.py --less … --extra-pnach tools/recomp/soak/proposed-flush.pnach`): the main arm |
| `rta_soak-fix25` | the 26 less that section: the main arm's first hour, before the replacement was written |
| `rta_soak-fix26` | the 26 as the file has them: only the runs of finding 1 |
| `rta_soak-nofix` | none: the check on the method |

### A job

`tools/recomp/soak/farm.py` derives a job from its seed alone (`make_job`), so a seed
repeats its game: `farm.py plan --arm fix25 --seeds 2000:20` prints the jobs,
`farm.py one --arm fix25 --seed N` runs one again, `--frames F` cuts it short with the
same input.

- **Machines**: two (80 % of seeds), three (10 %) or four (10 %). Two are joined by the
  shim's own link; three and four by `tools/recomp/soak/hub.py`, which stands in the
  middle and speaks the link's format to each, so all machines advance frame by frame
  together and a run repeats exactly.
- **Start**: every machine from power-on through the developer LAN start (`--net`).
- **Characters**: each slot's class is drawn from the seven; the lobby's model table
  (0x530338) is written before the confirm. In lockstep tick 680, on every machine:
  level 8, 25 or 45 with statistics to match, five of the class's active skills at rank
  10 (the first two on the ability buttons; in a quarter of the jobs a healing skill is
  put first where the class has one), and by the seed: every passive at 5, 50,000 gold,
  mana set to 500 every 300 ticks, a level-up left pending (acknowledged level one below,
  12 skill points, 15 stat points).
- **Level**: entered by a pending-level write in tick 700, before any input (the rule of
  live-rig.md 17.5): the arena `drunare` (30 %), one of the 23 levels of the rig's soaks
  (30 %), or any of the 90 names of the level table (40 %). In the arena the confirming
  machine's player walks into the trigger of the opening.
- **Input**: the rig's `fuzz` on every controller, in segments of 6,000 to 15,000 frames,
  each with one of six mixes (movement, right stick, attack, block, abilities, both
  potions, use, D-pad, inventory button, pause button, stick buttons); 30,000, 60,000,
  120,000 or 300,000 frames in all.
- **Bus**: none; delay 2, jitter 2, loss 1 %; 4, 3, 5 %; 6, 8, 3 %; 10, 6, 10 %; and in
  8 % of the jobs one outage of 60, 90 or 120 frames.

### What is compared

Every pair of machines of a job, at every lockstep tick, in every shared column of the
tick log, until one of the two holds a peer dropped (a kick or a leave is the game's own
doing: live-rig.md 8.2). Columns read through a player's object pointer are not compared
in a tick in which that pointer is null on both machines (the tick of a level reload):
they then show low memory, which is the runtime's own and per machine. A job with a
deciding difference is played a second time, cut off 400 frames after the difference,
with the pools of every machine dumped in the tick before and in the tick of it; every
job also dumps its pools at seven sampled ticks for the list of fields that differ in
step. The columns are the rig launcher's, those of live-rig.md sections
17, 18 and 22, and four new ones from the object pool (next section). A two-machine job
ends 60 ticks after a drop.

Columns that decide ("a difference"): shared seed, level, player count, button maps, the
game's own sync record and out-of-sync flags, cutscene flag, pending level, 2,048 bytes of
quest variables, pending post action, mission and jump-gate menu state; per player
position, facing, action state, object seed, hit points and maximum, mana and maximum,
gold, experience, three bags, statistics, equipment, ability records, skill ranks,
passives, weapon set, potion words, load, armour, resistances, and the ranges of the
player record listed in live-rig.md 22.1; and `pool`.

Columns followed on their own (first tick, count): the stored damage (+0xcc), the two
weapon-trail bytes (FINDINGS V63), the points block (its level-up bytes are V48),
`poolraw`, `poolfree`.

### The object-pool checksum

After every tick the hooks walk the object pool (`g_poolClasses` 0x403a10; a free block
is one on a free list) and leave out the prediction copy (`g_ghost`) and blocks whose word
at +0x48 is not a virtual table.

- `pool`: the sum over live objects of a hash of the virtual table, position, facing and
  the object's own random state (+0x44). A monster, pet, projectile or prop that stands
  somewhere else, faces elsewhere or has drawn a different number of random values on
  one machine changes it in that tick.
- `poolraw`: the sum over live objects of a hash of every word of the block. A word that
  is an address is taken as what it points at (a heap address as "a heap address", a
  pool address as the class it points into), because two machines in step place pose
  buffers and handle nodes differently.
- `poolfree`: the three free lists in order. `nobj`: the number of live objects.

Both sums are independent of the order and addresses of the objects: **Ran**, the free
lists of two machines in step do differ (calibration below), so the next object can land
at different addresses on the two.

`tools/recomp/soak/poolmask.txt` lists the words left out. Built in: the three handle
heads of every object, flag 0x200000 (this machine's own player) and flag 0x100 (hit
flash, cleared by drawing). The rest was learned in a calibration: six games of the
25-section build (seeds 1001, 1003, 1005, 1006, 1010, 1011, 9,000 frames, pools dumped
every 200 ticks) in which no player column differed; every (class, offset) that differed
at a sampled tick went into the file. That list says "differs between machines in
step", not "local by design" — see "Fields that differ between machines in step".

`tools/recomp/soak/poolcmp.py` compares two machines' pool dumps object by object
(`farm.py one --dump TICK`), which gives the first differing class and offset of a
difference in either checksum.

## Finding 1: the flush section leaves the players' input stuck from the launch on

Not a desync: a fault of one section of the suggested set, in the developer LAN start.

**Ran**, native pair, 26 sections, power-on to `strife`, no input: from lockstep tick 3
the held word of both lockstep pads (`g_pads` + slot × 0x58 + 8) is 0x500000 and the
left-stick value −1.138, on both machines, for the rest of the game — still so at tick
1,300 under random input, where button bits from the real controller come through on
top and the stick does not. The players walk by themselves and leave `strife` for
`blood1` at tick 228. Unpatched: −0.253, −0.644, −0.747, then 0 from about tick 10 (the
reset-state transient of `docs/netcode.md`), and the players stay.

| Program | Held word / stick at ticks 1, 3, 6, 31, 91 | Frame of tick 1 | Level at tick 300 |
|---|---|---|---|
| no sections | 0 / −0.253; 0 / −0.747; 0 / 0; 0 / 0; 0 / 0 | 651 | `strife` |
| 26 sections | 0 / −0.276; 0x500000 / −0.931; 0x500000 / −1.115; 0x500000 / −1.138; the same | 668 | `blood1` (from 228) |
| 26 less LAG-2; less the kick answer; less "a peer being dropped…" | as with 26 | 668 | `blood1` |
| 26 less the flush section | as with none | 651 | `strife` |
| none + word 0x132DFC alone (`slti a2,s0,16`) | as with 26 | 668 | `blood1` |
| none + word 0x132E28 alone (`lw v0,-8(a0)`) | as with none | 651 | `strife` |
| none + the proposed three words; 25 + the proposed three words | as with none | 651 | `strife` |

**Ran**, emulator rig, pair from power-on, the section applied by `pnach` at frame 300
(before the confirm), and a control without it: the same values to the digit on both
machines (−0.276, −0.931, −1.115, −1.138; 0x500000; `blood1` at tick 228); the control
stays in `strife` with the stick at 0. So it is the game with that patch, not the native
build.

**The cause.** `net_flushBeforeLoad` 0x132db0 begins its loop with

```
132df0  lw   v0, g_numPeers
132df8  blez v0, 0x132e40        ; no peers: skip the scan of the peers
132dfc  move a2, zero            ; delay slot.  The section: slti a2, s0, 16
...
132e40  beqz a2, 0x132e70        ; nothing to wait for: leave
```

The section's first word sits in the delay slot of the "no peers" branch, so it runs in
that case too: with no peers at all the function now goes round sixteen times, calling
`net_main(1,1)` each time (**Executed**, `tools/recomp/soak/flush_test.py`: 0 passes
unpatched, 16 with the section). In the developer LAN start the main loop
(`mainloop_runSession` 0x322998) reaches its first pending level with `g_networkMode` set
by the boot argument and calls `net_flushBeforeLoad` *before* the block that runs
`net_gameInit(0)`, `net_launchTransfer()` and the developer lobby (guarded by the byte at
0x402792 and `g_netLaunchLatch`), with `g_numPeers` = 0. Sixteen passes of `net_main`
then run on a netcode that has not been set up; `net_main` samples input whenever
`g_localInputFrame` < 3 whatever its "no input" argument says (**Read**, the test before
the sampling loop). Which state survives `net_gameInit` and holds the pads was not traced.

A lobby-launched game calls `net_gameInit` in the front end, so at its first flush
`g_numPeers` is positive and the netcode is initialised: by this reading the fault is the
developer start's alone. Not run here; the coordinator reports that a lobby-launched
native pair was checked by other work with the 26 sections as they are and with 25, idle
and across a level change, and that input is not stuck there.

Why nothing saw it before: the machines stay in step (every shared column equal), and the
rig runs of online-quality.md 3.2 and of the soaks applied the section to states saved
after the launch. It is also what `docs/issues/native-net.md` met when, with the 26
sections, "machine A's scripted walk does not move its player".

**Proposed section** (replaces the one of the same title; one word more;
`tools/recomp/soak/proposed-flush.pnach`):

```
[Net test: flush before a level load waits for the peers' tick]
// was: 18400011 (blez v0,0x132e40), 0000302D (move a2,zero), 8C82FFF0 (lw v0,-0x10(a0))  now: blez v0,0x132e70; slti a2,s0,16; lw v0,-8(a0)
patch=1,EE,00132DF8,word,1840001D
patch=1,EE,00132DFC,word,2A060010
patch=1,EE,00132E28,word,8C82FFF8
```

With no peers the branch goes straight to the function's exit (0x132e70), which is what
the original does in that case; nothing else changes.

| Check | Result |
|---|---|
| `tools/ee_emu.py`, `tools/recomp/soak/flush_test.py` (13 checks) | no peers: 0 passes unpatched, 16 with the section as it is, 0 proposed; with peers: the 16-pass minimum, the wait for the peers' reported tick, the 121-pass limit, with two and four peers — all pass |
| native pair, unpatched + proposed, and 25 sections + proposed | pads as unpatched (table above); in step; the level change at tick 700 takes 66 frames against 52 unpatched (the section as it is: 66), so the sixteen passes are there where they are wanted |
| emulator rig pair from power-on, proposed section by `pnach` at frame 300 | stick −0.253, −0.747, 0 from tick 6, held word 0, on both machines; `strife` until a scripted level change at tick 330, `blood1` at 331 on both |

The soak's main arm (`fix26c`) is the suggested set with this form of the section.

## Finding 2: a jump-gate prompt at draw time appends a quest variable on one machine

Known from reading (`docs/script.md` P1 and the `getv` row; `docs/issues/draw-sim-leaks.md`),
now **Ran**. Seed 3103 (two machines, level `nit2`, bus delay 6, jitter 8, loss 3 %, 26
sections): the 2,048-byte checksum of the quest variables differs in ticks 4662–4665 and
in nothing else; repeated exactly. The table has 16 entries on machine 0 and 17 on
machine 1 in those ticks: the entry `nit_gotshard`, value 0.

Trace (`--instrument trace`, a watch on the new entry's bytes, both machines):

| Machine | Tick | Chain, innermost first |
|---|---|---|
| 1 (owner of the player at the gate) | 4662 | `vars_get` ← `script_getv` ← `scr_callNative` ← `scr_interpret` ← `script_runByName` ← `JumpGate_interactPrompt` ← `Player_interact` ← `Player_draw` ← `world_drawObjects` ← the draw phase of `mainloop_runSession` |
| 0 | 4666 | `vars_get` ← `script_getv` ← … ← `script_runByName` ← `script_callScript` ← … ← `script_runByName` ← `Trigger_run` ← `runObjects` ← the tick's task pass |

So the gate's predicate script, run from drawing on the machine whose own player stands at
the gate, reads a variable that does not exist yet, and `vars_get` appends it; four ticks
later a trigger's script does the same inside the tick on both machines, and the tables are
equal again. Nothing but the table differed. What it can do beyond this case — two
variables appended in different orders leave the tables in different orders for good
(lookups are by name); a predicate script with another side effect — was not run. No fix
is proposed here; it is recorded because it had never been seen on a running game.

## Finding 3: the half of B9 that the section leaves — a save point used on one machine only

*Corrected 2026-10-13 ("Second part", "Save point"): the game of this finding, seed 5000,
is not the card test — its menu mutex differs from tick 6,102, a consequence of K1 that the
set removes. The card test is real and is seed 3115's; both are worked out below.*

Known from executing in isolation (FINDINGS B9: "the save point's own effect state …
still follows each machine's card state"), now **Ran**, without fixes: seed 5000 (two
machines, `hub2`), the first job of the unpatched arm, differs in `pool` alone at tick
10,380 and in no player column to its end (30,837 ticks, no out-of-sync flag).

- Pools at tick 10,379: one object differs, the `Savepoint`, in +0x84 (0 against 1) and
  +0x8c; at 10,380 its private random state (+0x44) and its effect fields too — that is
  what `pool` saw.
- Trace of +0x84 over the whole game: written once, at tick 10,178, on machine 1 only, by
  `Savepoint_interact` 0x28dc30 ← `Player_interact` ← `Player_run` ← `runObjects` ← the
  tick. Machine 0 runs the same tick without the store. `Savepoint_interact` begins with
  `memcard_isBusy()` and `menuMutex_isHeld()` — this machine's own card screen and menu
  mutex — and does nothing when either holds (**Read**; `docs/issues/sync-breakers.md`).
  At tick 10,380 `Savepoint_run` takes its effect branch on machine 1 alone (33,051 draws
  from the object's random state against 984 in the same ticks on machine 0).
- With only "save-point prompt ignores this machine's card screen", with that and "net
  launch clears a stuck memory-card latch", and with the two menu-lockout sections: the
  same difference at the same tick with the same checksum. With the 18 sections that do
  not change timing, and with the whole set, the same seed never uses the save point, so
  those runs say nothing.
- With the whole set on: in one of 121 games (seed 3115) a `Savepoint`'s +0x84 differed
  between the machines at a sampled tick, with no deciding column differing. So the
  mechanism is reachable with the set as it ships.

What it is worth: the save point's state, its light, its random state and — by the
ledger — its `action` scripts run on the machines that are not busy and not on the one
that is. No shared column followed from it in either game. It is not covered by any
section; a section for it would have to make the two tests of `Savepoint_interact`
(0x28dc44 on) guard only the save request, and was not written.

## Totals

| Arm | Jobs | Ticks compared | Machines 2 / 3 / 4 (jobs, ticks) | Longest game | Deciding differences | Jobs ended by a dropped peer |
|---|---|---|---|---|---|---|
| `fix26c`: 26 sections, the flush section as proposed | 122 | **7,792,955** | 100, 5,905,560 / 9, 718,508 / 13, 1,168,887 | 300,887 ticks (84 minutes of play) | 3 reported, **none the set's** (below) | 10: kicks and leaves by random input in the pause menu (`net_kickPeer` entered 7 times); none preceded by a difference or an out-of-sync flag |
| `fix25`: the 26 less the flush section | 4 | 120,340 | 3, 89,919 / 1, 30,421 / — | 30,564 | 0 | 0 |
| with fixes, together | 126 | **7,913,295** | | | | |
| `nofix` | 22 | 411,941 | 19 / 1 / 2 | 56,102 | 20 reported: 19 real, 1 the comparison's | 15, of which 14 after the game's own out-of-sync flag |

Machine-ticks of the main arm (ticks × machines): 18,642,192. No job timed out, none was
left without a log. One game (seed 3194, a 300,000-frame pair) was in flight when the farm
was ended for the release builds; it was stopped and is not counted.

Main arm by split (jobs, ticks):

| Split | |
|---|---|
| length in frames | 30,000: 44, 1,332,088; 60,000: 56, 3,292,770; 120,000: 16, 1,610,224; 300,000: 6, 1,557,873 |
| bus | none: 39, 1,838,766; delay 2 jitter 2 loss 1 %: 22, 1,659,470; 4, 3, 5 %: 19, 1,170,615; 6, 8, 3 %: 19, 1,803,915; 10, 6, 10 %: 15, 753,717; with an outage of 60–120 frames: 8, 566,472 |
| character level | 25: 77, 5,119,922; 8: 27, 1,304,865; 45: 18, 1,368,168 |
| class of a player (a job counts once per class in it) | 0: 42; 1: 34; 2: 34; 3: 40; 4: 44; 5: 39; 6: 46 |

Speed: 60–200 ticks a second per pair at load 250–450 (afternoon), about 500 at load
20–110 (evening); the processor time per tick was about twice the figure of
`native-net.md`'s quiet machine, and the pool checksum and the 110 columns do not show
in it (the same game with `poolraw` every tick, every eighth tick or never: 12.1, 13.4,
14.5 s of processor for 4,779 ticks — noise).

## Differences reported

Every job of the arms with fixes in which a deciding column differed.

| Seed | Where | Column | What it is |
|---|---|---|---|
| 3009 (two machines, `wat1`) | tick 22,151, that tick only | `armour` of both players | **The comparison's doing.** Both players had died; in the tick of the level reload the player object pointer is null, and the column — a field read through that pointer — shows address 0xe4, where the native runtime keeps tables of its own (machine 1 had two more entries from tick 14,742 on: 86 words of the low megabyte differ between the machines). Fixed in `farm.py` (such columns are not compared while the pointer is null) |
| 3017 (four machines, `inmine1`, 300,000 frames) | tick 252,104 | `armour` of player 2 | the same; the second run, made with the fixed comparison, has no difference |
| 3103 (two machines, `nit2`) | ticks 4662–4665 | quest variables | finding 2: real, known from reading, silent, not the set's |

Followed columns (they do not decide): the weapon-trail bytes (FINDINGS V63) differed in
most games, as on the rig; hit points stood above the stored maximum in 45,543 ticks of
machine 0's logs (the heals of live-rig.md 17.3) without a difference between machines.

### The check on the method: the unpatched arm

22 games of at most 30,000 frames (the first ones longer). One reported difference is the
comparison's (`armour`, as above) and that game and two others have no real difference;
**19 of 22 differ**, each at the same tick in a second run, and 14 go on to the game's
own out-of-sync flag and a dropped peer.

| Columns at the first difference | Games | First tick (least – most) | Reading |
|---|---|---|---|
| load | 5 | 887 – 3,855 | the carried weight (FINDINGS V57's column) |
| object count, a bag, load, `pool` | 5 | 2,438 – 12,049 | an item object live on one machine only at that tick: a pick-up or a drop made on one machine (the K1 and carried-weight family by its columns) |
| bag 2 and load | 2 | 1,338; 2,101 | the potion bag (K2's columns) |
| bag 0 | 2 | 1,200; 6,562 | not classified |
| mana | 3 | 4,572 – 7,239 | the K4 clamp, reached by the farm's own write: mana is set to 500 every 300 ticks and level-8 and some other builds have less than that (live-rig.md 17.5 has the same on the rig) |
| pending level and the record's tail | 1 | 22,617 | one machine changes level and the other does not (K1's worst case by its columns) |
| `pool` alone | 1 | 10,380 | finding 3 |

Which section removes each was not tried (finding 3's game apart); the classes are named
by their columns. Not seen in 412,000 ticks: D26, E9, U1, K3 — each needs a sequence that
random input makes rarely.

## Coverage

The main arm's first 121 games (7,734,856 ticks; the last game to finish, of four
machines, is not in these counts). Counts are entries of the function on every
machine, the prediction copy's included (the `CALL` / `CALLR` counters; calls inside a
merged unit, tail jumps and calls made by the runtime are not counted). 3,745 functions
of the executable were entered, 3,268 of them named.

| What | |
|---|---|
| levels | 48 different start levels of the 90 in the level table; 61 levels seen in all; 1,125 level changes after the first entry, each in the same tick on every machine. Most ticks: `drunare` 1,344,579; `hub` 1,151,813; `torment0` 398,640; `firbonus` 361,856; `swamp1` 312,827; `inmine1` 286,686; `torment2` 237,309; `strife` 225,893; `hub2` 221,013; `fire1` 208,008; then 51 more, among them `bossevil` 57,246 and the four `pvp…` levels 164,113 |
| the arena | 31 games started in `drunare`; ticks with the cutscene flag up, all levels: 256,456 |
| deaths (hit points to zero, per player) | 1,303; `player_respawn` entered 106 times; reloads after the whole party died: seen (seed 3009 is one) |
| `Player_castSkill`; `Player_usePotion`; `Player_meleeHit`; `Player_takeDamage`; `damage_apply`; `player_giveExp` | 142,776; 748,106; 30,986; 82,822; 136,170; 4,062 |
| skill and spell objects run | 48 of the 54 named `Spell…_run` / `Cast…_run` functions. Never: `SpellArena`, `SpellBash`, `SpellConeOfShock`, `SpellHornOmenEffect`, `SpellPlanarSteelEffect`, `SpellShieldBash` |
| object classes run | 171 of 267 named `…_run` functions. Never, among others: `CloudGiant`, `Innoruuk`, `RedDragon`, `MummyKing`, `SpiderQueen`, `Natasla`, `Nightmare`, `UndeadKnight`, `SmallSpider`, `Vehicle`-like props (`Wheel`, `RollDoor`, `FallPlatform`), the `Hate…` objects |
| inventory opened; inventory messages; equip; drop; give; remove; `itemprop_tryPickup` | 40,213; 159,444; 9,159; 5,944; 14,809; 8,593; 5,459 |
| `stats_screen`; `skills_screen`; `player_recalcStats` | 426,713; 197,610; 62,436 |
| pause menu opened; `config_commitOptions`; `net_kickPeer` | 23,760; 3,914; 7 |
| `shop_openOrStock`; `shop_buySellMenu`; `shop_buy` | 1,488; 13,916; 115 |
| `recall_execute`; `save_game`; `game_loadLevel`; `net_closeLocalMenus` | 9,161; 6,174; 6,643; 9,681 |
| `missionMenu_run`; `JumpGate_openMenu`; `cut_advance` | 1,153; 64; 987,517 |
| `workshop_input` | 2 |
| a stat point or a skill point spent (`inventory_onStatPoint`, `inventory_onSkillPoint`); `inventory_unequipItem` | **never** — a level-up was pending with points to spend in a third of the games, and random input did not spend one |

Not covered:

- A stat or skill point spent; the workshop beyond two entries; unequipping.
- The lobby path: every game is the developer LAN start. Characters are written, not
  imported; their items are the starting ones and what they found or bought.
- 42 of the 90 levels were never a start level, and 29 were never seen.
- Bosses and classes in the "never" list above (the CloudGiant king among them).
- Games longer than 300,000 frames; two networks; anything that is not two copies of one
  build on one machine: like the rig, this shows logic differences only. Agreement of the
  native build with the emulator is `native-net.md`'s; no farm job paired a native
  machine with a rig machine.
- The instance cap of six was exceeded for about a quarter of an hour at 20:10 (eight
  instances: two farm processes, one of them with a four-machine game).

## Fields that differ between machines in step

Pools of the main arm compared word by word at 7 sampled ticks of every game (the
calibration's six games before that), while no deciding column differed. A heap address
counts as "a heap address". **Ran**: that they differ; the reading is from the documents
named, and where none is named the field is not classified.

| Class | Offsets | What was seen | Reading |
|---|---|---|---|
| every object | +0x00, +0x04, +0x08 | handle-node addresses | the handle pool is used by the prediction copy too (live-rig.md 11.3) |
| every object | flag 0x100 (+0x0c) | set on one machine | hit flash, cleared by drawing (`docs/objects.md`) |
| `Player` | flag 0x200000 | on the owner's machine | this machine's own player (`docs/netcode.md`) |
| creatures (27 classes), `Player`, props | +0x114, +0x120, +0x140, +0xa4, +0x98 | a heap address against 0 | pose and animation buffers present on one machine only; not read per field |
| creatures | +0xa8 bit 0x80000000 (`Nightmare`, `Cazic`, `Warrior`) | set on one machine | "boss health bar is showing", written from the list of alive local players (`docs/creatures.md` C3) |
| creatures | +0x408 … +0x42c, +0x49c (`Horsemen` +0x414, `Skelight` +0x40c, `Orc` +0x41c, `Goblin` +0x42c …) | two low bytes one or a few apart | not classified; `Creature_draw` decrements a status counter from draw code (`docs/creatures.md` C1) |
| `Player` (25 of 56 games sampled) | +0x1c0 – +0x1f8 (animation tracks 5 and 6 by their place), +0x198, +0x1b8 bit 0x10000 | on the owner's machine other values than on the others, for tens of thousands of ticks (seed 3005: +0x1e8 0.1667 against 1.0 from tick 9,230 to 55,384) | not classified. The owner's machine shows the copy and hides the real player; nothing followed from it |
| `Player` | +0x328 – +0x33c, +0x38c, +0x478, +0x4c8, +0x220, +0x98, +0x9c | pairs of small numbers, counters | not classified |
| `Savepoint` (16 games) | +0x58, +0xc0; once +0x84 | | +0x84: finding 3. The others not classified |
| `Gold`, `Torch`, `JumpGate`, `AddParticle` | +0x44 and blocks of floats | **the object's own random state differs** | not classified: presentation classes by their names; no reader in the simulation was looked for. Their +0x44 is left out of `pool` |
| `ItemProp` | +0x13c (a float counter), +0x104 | | +0x104 is a frame stamp only drawing reads (`docs/issues/draw-sim-leaks.md`); +0x13c not classified |
| `PhProp`, `playerProjectile`, `MissileWeapon`, `HolyStrike`, `HolyBolt`, `ShockProjectile`, `DarknessProjectile`, `FireStorm`, `GlowingCylinder`, `Weather`, `AutoProp`, `AutoPropLP`, `HackDoor`, `TormentBridge`, `RingPortal`, `AutoChest` | see `tools/recomp/soak/poolmask.txt` and `rawdiff.tsv` | | not classified |
| the three free lists | order | differ from the first thousand ticks on in most games | the next object can land at different addresses on the two machines; live objects were at the same addresses at every sampled tick but for a few blocks, and the checksums do not depend on addresses |

`poolraw` therefore still differs in most games and is followed, not counted: turning it
into a deciding column needs the fields above classified one by one.

## What this says about the fix set

For the set as it will ship (the 25 other sections and the three-word flush section):

- Nothing in 7.79 million ticks speaks against it: no difference in any deciding column
  that is the set's doing, no out-of-sync flag, in two-, three- and four-machine games
  with delay, jitter, loss and outages, 1,125 level changes, 1,303 deaths, reloads after
  a wiped party, 143,000 casts of 48 skill classes, 115 purchases.
- The flush section in its two-word form must not ship: it breaks input in every
  developer-LAN-start game (finding 1). A lobby-launched game is not affected by it
  (reported by other work), so released builds that only launch through the lobby have
  not been hurt by it.
- Two silent per-machine mechanisms are reachable with the set on (findings 2 and 3).
  Neither is new, neither produced a difference in a player, a monster or the shared
  seed here, and neither is a reason to hold the set; finding 3 is the better candidate
  for a next section.
- What the soak cannot say is in "Not covered" above; the largest items are the lobby
  path and spent points.

## Proposed ledger rows

For whoever edits `FINDINGS.md` (this document does not).

| Row | What to record |
|---|---|
| L (new) | Section "flush before a level load waits for the peers' tick" as first written: its word at 0x132DFC is the delay slot of the no-peers branch of `net_flushBeforeLoad`, so with `g_numPeers` = 0 the function makes 16 passes of `net_main(1,1)` (**Executed**: 0 unpatched, 16 patched). In the developer LAN start the main loop calls it before `net_gameInit`, and both players' lockstep pads then stay stuck for the whole game (held word 0x500000, left stick −1.138; the players walk out of `strife` by themselves at tick 228). **Ran** on a native pair and, with a control, on an emulator-rig pair from power-on: the same values. In step throughout. A lobby-launched game initialises in the front end and is not affected. Replacement, three words (0x132DF8 → 1840001D, 0x132DFC → 2A060010, 0x132E28 → 8C82FFF8): **Executed** (`tools/recomp/soak/flush_test.py`, 13 checks), **Ran** native and rig. `docs/issues/native-soak.md` finding 1 |
| V (new) | Every rig or native run that applied the 26 suggested sections before a developer-LAN launch (2026-10-12 11:04 onward) had both sticks stuck; `docs/issues/native-net.md`'s "machine A's scripted walk does not move its player" is this |
| V (new) | Native soak, the suggested set with the three-word flush section: 122 games from power-on through the developer LAN start (100 of two machines, 9 of three, 13 of four), 7,792,955 ticks, up to 300,887 in one game, 61 levels, 1,125 level changes, 1,303 deaths, 142,776 `Player_castSkill` entries, 48 of 54 named skill classes run, 115 `shop_buy`: no difference in any deciding column that is the set's doing — the rig soaks' columns and a checksum of the virtual table, position, facing and private random state of every pool object — and no out-of-sync flag; 10 games ended by a kick or leave. With 25 sections: 120,340 more. Without fixes 19 of 22 games differ and 14 reach the out-of-sync flag. Two copies of one native build: logic only |
| script P1 / E (add) | **Ran**: `JumpGate_interactPrompt`, called from `Player_draw` in display mode on the owner's machine, runs the gate's script, and its `getv` of a variable that does not exist appends it to `g_questVars` four ticks before a trigger's script appends it in the tick on every machine (seed 3103, `nit2`, ticks 4662–4665; trace of both chains). The tables are equal again afterwards; nothing else differed |
| B9 (add) | **Ran**, unpatched: `Savepoint_interact` 0x28dc30 stores +0x84 inside the tick on one machine and not on the other (seed 5000, tick 10,178; the function tests this machine's `memcard_isBusy` and `menuMutex_isHeld` first), and from tick 10,380 the save point's effect branch and private random state run on that machine alone; no player column follows in 30,837 ticks. The sections "save-point prompt ignores this machine's card screen", "net launch clears a stuck memory-card latch" and the two menu-lockout sections do not change it. With the whole set a `Savepoint` +0x84 differed in one of 121 games. No section covers it |
| V (new) | Object pools of two native machines in step, compared word by word: live objects sit at the same addresses while the free lists' order differs; the fields that differ are listed in `docs/issues/native-soak.md`, among them the private random state (+0x44) of `Gold`, `Torch`, `JumpGate` and `AddParticle` objects and animation tracks 5 and 6 of the real player on its owner's machine. No reader in the simulation was looked for |
| native runtime (note) | Columns read through a null player-object pointer show the runtime's own low-memory tables, which differ per machine (86 words of the first megabyte in one pair); two false "armour" differences came from that |

---

# Second part, 2026-10-13: the two findings to the bottom, three proposed sections

**Status: ended 2026-10-13 09:16.** The farm is stopped; nothing of it is running. Base: the shipping set as it is in
`patches/SLUS-20973_4028A55F.pnach` since the release (26 sections, 91 words). Neither that
file nor `tools/play-net/sections-suggested.txt` is changed by any of this: the proposed
sections are in `tools/recomp/soak/proposed-sections.pnach`.

## In short (second part)

- **Finding 3 was read wrongly in one point, and is two things.** Seed 5000 (unpatched) is
  not the save point's card test: there the *menu mutex* (0x4fe53c) differs between the
  machines from tick 6,102 on, and a held mutex is what makes `Savepoint_interact` do
  nothing on one machine at tick 10,178. The section "use button works with the spell
  selector open" (K1) alone removes it (**Ran**: no difference in 11,745 ticks). The card
  test is real too, with the whole set on: seed 3115, tick 26,847 (**Ran**, traced on both
  machines), and a directed game reproduces it at will.
- **Save point, verdict: it cannot reach play with the shipped levels.** Every reader of
  the differing fields is the save point's own effect, draw and stored-state code; none of
  the 111 save points on the disc has an `action` script. A five-word section removes the
  difference all the same.
- **Script variable race, verdict: the appended name cannot reach play; the same draw-time
  prompt can.** Over the whole disc a script started from drawing can write nothing shared
  but the name a `getv` appends, and the table is read by name only. But the jump gate's
  prompt *itself* marks the gate found and adds the level to the list of jump-gate
  destinations from drawing, on the owner's machine, as many ticks early as that machine's
  input runs ahead (**Ran**: 19 ticks in a directed game; the gate list is shared state the
  gate's own prompt and the jump menu decide on). One word removes the append, two words
  the early marking.
- Three sections proposed, 8 words, each executed in the interpreter (36 checks) and each
  shown on a native pair without and with it.
- **Soak, shipping set plus the three sections: 26 games, 1,779,709 ticks, no difference in
  any deciding column** — 18 games of two machines, 4 of three, 4 of four; neither of the
  two old differences; the menu mutex and the jump-gate list, new columns, equal in every
  tick. With A and B alone, before C: 365,308 more, none.
- The per-machine fields of the first part's table are classified; all but one family are
  presentation by reading or a known cache. The one that is not: the real player's
  animation tracks differ on its owner's machine, because the spin spell animates the
  prediction copy there (**Ran**); no position followed from it in 9 million ticks.

## Programs of the second part

All built by `tools/recomp/soak/build_soak.py --src local/recomp-out/soak/src-1013 --rt frozen`
into `local/recomp-out/soak/bin/` (a directory of the soak's own). `src-1013` is a copy made
2026-10-13 07:30 of `tools/recomp/*.py`, `tools/recomp/rt/`, `tools/recomp/net/netshim.cpp`
and `hle-net.txt`, of the patch file (`shipping-26.pnach`, sha1 7fa829af…) and of the
suggested list, so that nothing built later depends on what other work does to those:
`recomp.py` sha1 0d8d694e…, `netshim.cpp` 19dd8d18…, `soakhooks.cpp` 94c4ad72…; the runtime's
objects are the frozen ones of the first part (`runtime.cpp` a23ce0e2…), and the translated
code and the shim are compiled against the runtime's headers as they were at the copy. Each program's
`local/recomp-out/gen-soak-<name>/build-info.txt` has the list.

| Program | Sections |
|---|---|
| `rta_soak-s26` | the 26 of the shipping set |
| `rta_soak-s26a`, `-s26b` | the 26 and section A / section B alone |
| `rta_soak-s26ab` | the 26, A and B (built before C was written) |
| `rta_soak-s26abc` | the 26 and all three: **the soak arm** |
| `rta_soak-s26t`, `-s26abt` | the same as `s26` / `s26ab`, `--instrument trace` |
| `rta_soak-nofixa`, `-nofixp`, `-nofixpa`, `-nofixk` | no section but: A; the save-point prompt section; both; the K1 section |

`s26` repeats the first part's seed 3103 exactly (quest variables differ in ticks
4662–4665), so the new programs compute what the old ones did.

`farm.py` changes of this part: machines run under `nice -n 19`; `run` ends by itself — no
new job, the running machines stopped — once `<out>/alive` has not been touched for 45
minutes; `one` takes `--level`, `--machines`, `--bus` and `--directed FILE` (script lines
in place of the random input, `A:` / `B:` for the confirming machine / the others); four
more columns: `mutex` (0x4fe53c), `jgcount` (0x8e3c30), `jgdests` (0x8e3a50, 480 bytes) —
deciding — and `actplayer` (0x4d8ae4), followed.

## Save point

### The chain (Read, and Ran on both machines)

`Player_run` 0x1a5030 calls `Player_interact` 0x1b2640 for every real player in every
tick. That calls the nearest usable object's prompt (slot 13; for a save point 0x28da58)
and, when the prompt answers 1 and the use button is in the player's lockstep pad, sets
`g_scriptActivePlayer` and calls slot 14, `Savepoint_interact` 0x28dc30:

```
if memcard_isBusy()   (this machine: a card screen is up, or a card result is pending)  -> nothing
if menuMutex_isHeld() (0x4fe53c)                                                        -> nothing
save point +0x84 = 1;  memcard_requestSave(player)   (opens the dialog only on the machine
that owns the player, and sends game message 2);  light on (+0x88);  +0xc4 = 1;
obj_runActionScripts(this)
```

| Who | What it does with the state |
|---|---|
| `Savepoint_run` 0x28cdd0, in the tick | while +0x84 is set: when this machine's "card screen done" flag 0x4f8f29 is up it sends game message 5 with the save point's address and clears the flag; when +0xcc is set (by message 5, on every machine in the same tick: `hud_onMsg` → `Savepoint_startSavedEffect` 0x28cdc4) it plays the "saved" burst — a sound, an animation, +0x80 = 1, three passes of particles that draw about 33,000 values from the save point's own generator (+0x44) — and ends with +0xcc = 0, +0x84 = 0. +0x80, once set, counts every tick (the pulsing light, the "used" animation) |
| `Savepoint_draw` 0x28d854 | reads +0x80 and +0x78 |
| `Savepoint_saveState` 0x28dc9c | the first word of the 6 bytes the save point writes into the level's stored state is +0x84 if that is set, else +0x80 |
| `Savepoint_loadState` 0x28dcd0 | a non-zero stored word: +0x80, light, +0xc4, the "used" animation, +0xc5 = 1 |
| `Savepoint_clone` 0x12f768 | copies them (no caller clones a save point) |

That is every load of +0x80, +0x84, +0xc4, +0xcc and +0x78 in the program
(`tools/fieldxref.py`, class `Savepoint`; the only access from outside the class is the
store through the address carried by message 5). The parts of `Savepoint_run` that are
simulation — bringing a dead player back with one draw from the shared generator, the
auto-save — read +0xc6, +0xc7, +0xc8, the players and the frame counter, none of the fields
above. +0xc5 is read by the idle sparkle and written into the stored state only.
`memcard_getState() == 0`, the other thing that clears +0x84, is the state of the options
load at boot; nothing sets it during a game (**Read**: the callers of `memcard_setState`).

**Ran**, seed 3115, shipping set (`s26`, and `s26t` with a watch on +0x84 and +0xcc of the
save point of `hub`, 0x5f8bc0), columns for the save point and for each machine's card
state:

| Tick | Machine 0 | Machine 1 |
|---|---|---|
| 26,622 | player 0 uses the point: +0x84 = 1 (`Savepoint_interact` ← `Player_interact` ← `Player_run` ← the tick), its save dialog opens (card state 3) | +0x84 = 1, the same chain |
| 26,726 | | player 1 uses it: its own save dialog opens (state 3) |
| 26,796–26,798 | message 5 (`Savepoint_startSavedEffect` ← `hud_onMsg` ← `net_frameLoop`), burst, +0x84 = 0 | the same |
| **26,847** | player 0 uses it again: **+0x84 = 1** | its card screen is still up: **nothing** (+0x84 stays 0) |
| 26,934 | | its save is done: flag 0x4f8f29 = 1, but +0x84 is 0 here, so no message 5; the flag stays up |
| 28,066 | | player 0 uses the point once more: +0x84 = 1, and the flag that has waited 1,132 ticks sends message 5 at once |
| 28,081–28,083 | the burst — fifteen ticks after its own dialog opened, for a save made on the other machine | the burst |

+0x84 differs for 1,219 ticks; in this game the burst then ran on both machines in the same
ticks and the private generators stayed equal. In the directed game below it runs on one
machine only and the difference stays.

### Seed 5000 is something else

Finding 3 took seed 5000 (unpatched) for this mechanism. **Ran** with columns for the
mutex, each machine's card state, the spell-selector words 0x41b818, the menu lockout and
the pause flag: at tick 10,178 no card screen is up on machine 0; its **menu mutex is 1
and machine 1's is 0, and has been since tick 6,102**. `nofix` plus section A, plus the
prompt section, plus both: the same difference at tick 10,380 with the same checksums.
`nofix` plus "use button works with the spell selector open" alone: no difference in
11,745 ticks. So in the game as shipped a use press the owner's machine skips (K1) can
leave the menu mutex taken on one side for the rest of the game — and with it every save
point and, in a net game, every jump gate (`JumpGate_interact` tests the same word) dead on
that machine. With the set on, the mutex is a deciding column of the soak arm below.

In a net game the mutex is shared state: `menu_openInventory` and `inventory_close` touch
it only offline (0x1c1600, 0x1c52a8); the other writers are `Creature_interact` and
`Creature_trigger` (the tick), the dialog's message handler and a script built-in.

### Every reader: can it reach play?

| Path | Verdict |
|---|---|
| the save point's light, animation, sound, particles, private generator | presentation: the generator is drawn from by the burst and the idle sparkle only (`GameObject_rand` in `Savepoint_run`; nothing else of the class calls it) |
| `obj_runActionScripts(this, 1)` — the `action` scripts | would be a script run on some machines and not others. **None of the 111 save points on the disc has an `action`** (`tools/recomp/soak/enum_drawscripts.py`, every level archive; the ledger's B7 by a second reading) |
| the 6 bytes in the level's stored state → a reload after a party wipe, coming back to the level | `Savepoint_loadState` sets the same presentation fields; the block is 6 bytes whatever it holds |
| message 5 | sent when the saving machine's own +0x84 is set, to every machine in the same tick; with the difference it is sent late (above) or its burst plays on some machines only |
| `g_scriptActivePlayer` | set by `Player_interact` before the call, on every machine since the prompt section is in the set |
| the shared seed, the sync record, a player, a monster, an item | no path: none of the functions above writes or reads them on the +0x84 / +0xcc / +0x80 side |

`pool` does see it: the save point's private generator is part of that checksum, which is
how seed 5000 was noticed.

### The same test elsewhere: every prompt and every interact (enumeration)

`tools/recomp/soak/enum_interact.py`: the prompt (slot 13) has 22 implementations over the
232 classes of the object family, the interact (slot 14) has 23. Direct calls followed two
levels; the lines were then read.

| Implementation | Per-machine state it tests or uses | Reading |
|---|---|---|
| `Savepoint_interactPrompt` 0x28da58 | `memcard_isBusy` | removed by the set's "save-point prompt ignores this machine's card screen" |
| | this machine's ticks since its last save (0x4f8f30) | chooses between two texts; both answers are 1 |
| `Savepoint_interact` 0x28dc30 | `memcard_isBusy` | **section A** |
| `JumpGate_interactPrompt` 0x27d7a0 | `task_isRunning("jumpgate")` | the menu task is started in the tick on every machine (`JumpGate_openMenu`; column `jgstate`) |
| `Creature_interact` 0x116bd8 (76 classes), `PushTrigger_interact` 0x1ecc70 | through `shop_openOrStock`: the local slot | the shop opens on its owner's machine only, by design (`docs/script.md`, open question 7) |
| `JumpGate_interact`, `Savepoint_interact` | `menuMutex_isHeld` | shared state (above) |
| door, chest, switch, anchor interacts | `game_isFrozen` (in a net game `g_paused`, which is set offline only), `hud_showMessage`, `player_voice`, the gold floater | display and sound |
| the other 12 prompts (the creatures' among them, 76 classes) and 8 interacts | nothing of the kind within two calls | |

So one implementation of 45 has a per-machine test that decides what the tick does and is
not covered by the set: `Savepoint_interact`. Stores made by a prompt — which also runs at
draw time — are in "Script variables" below.

### Section A

```
[Net test: save point is used on every machine whatever this machine's card screen does]
// was: 0C085D46 (jal memcard_isBusy)        now: jal menuMutex_isHeld
patch=1,EE,0028DC44,word,0C08BF0B
// was: 0C08BF0B (jal menuMutex_isHeld)      now: jal memcard_isBusy
patch=1,EE,0028DC54,word,0C085D46
// was: 1440000A (bnez v0,0x28dc88)          now: bnez v0,0x28dc68
patch=1,EE,0028DC5C,word,14400002
// was: 24100001 (addiu s0,zero,1)           now: jal memcard_requestSave
patch=1,EE,0028DC64,word,0C085D6D
// was: 0C085D6D (jal memcard_requestSave)   now: addiu s0,zero,1
patch=1,EE,0028DC68,word,24100001
```

The two tests change places and the card one is narrowed: a held mutex still skips
everything, as before and on every machine alike; a busy card skips only the request for
this machine's save dialog (the branch lands on the `addiu`, which is also the delay slot
of the call). A machine that is not busy does exactly what it did. What changes for the
player: used while the owner's own card screen is up, the point lights up and no dialog
opens (before: nothing on that machine, everything on the others); and a "card screen done"
flag left from a save made through the pause menu can now be answered by the burst when
the point is next used during a card screen — on every machine alike. It needs the set's
prompt section to be of use (without it the busy machine never gets as far as the call).

| Check | Without the section | With it |
|---|---|---|
| `tools/recomp/soak/sections_test.py` A1–A12 (15 checks; `memcard_isBusy` and `menuMutex_isHeld` run for real on their globals) | a card screen (states 3, 5, 10, or a pending result): nothing at all | +0x84, light, +0xc4 and the action call as on a free machine, no save request; mutex held: nothing, as before; free machine: unchanged, for players 0–3 |
| seed 3115 (two machines, `valmedal` → `hub`, delay 6, jitter 8, loss 3 %), 28,200 frames, the save point's +0x84, +0xcc, +0x80, +0xc4, private generator and the mutex as deciding columns | `s26`: +0x84 1 against 0 from tick 26,847 (table above) | `s26a`: no difference in 29,012 ticks; the burst at 26,953 on both |
| directed game `local/recomp-out/soak/dir-savepoint.txt` (two machines, `drundar`, no bus delay): in lockstep tick 1,000 player 0 is put beside the save point at the entry and player 1 beside the north-west one; machine 0 presses use and leaves its dialog open; machine 1 presses use, then confirms its way through its own dialog | `s26`: tick 1,170 +0x84 of the second point 0 against 1; tick 1,418 the burst on machine 1 alone (+0xcc 1 against 2, +0x80 0 against 2, private generator 0x62aa against 0x2499f167), `pool` differs from there to the end, +0xcc left at 1 on machine 0 | `s26a`: equal in every tick of 3,589, with the values machine 1 had |
| the same directed game on three machines (`--machines 3`; the third machine idle) | `s26`: the busy machine against the two others — +0x84 0, 1, 1 at tick 1,171, the burst and `pool` on machines 1 and 2 only | `s26a`: equal on all three in every tick of 3,589 |
| seed 5000 unpatched | not this mechanism (above) | |

## Script variables and the prompts that run at draw time

### The chain (Read, Ran)

`Player_draw` 0x1a46c0 calls `Player_interact(player, 0, display only)` for this machine's
own players at display rate (0x1a4800). The tests in front of the call are the tick's
(0x1a5b98–0x1a5c1c) — pause, menu lockout, dialog, the player's camera flag — but outside
the tick they read **this machine's current** state: the local slot's pad and flags hold
what was sampled now, which the tick will see as many frames later as this machine's input
runs ahead (`docs/netcode.md`, hazards 4 and 5; the camera flag, for one, is bit 0 of
`g_netCamYaw[slot]`, 0x13e138). The position is the real player's. Which of the tests it
was in the runs below was not isolated; the lead measured is the input lead in both.

Seed 3103 again, with the players' distance to the gate of `nit2` and each machine's menu
flag: machine 1 has its inventory open until tick 4,660; its input runs 18 frames ahead; in
the frame after it closes the inventory its drawing runs the gate's prompt, whose script
reads `nit_gotshard` (`vars_get` appends it, value 0). The tick would have run the same
prompt on both machines about 18 ticks later; a trigger's script read the name first, at
tick 4,666. So "four ticks" was an accident of that game: the lead is the input lead.

### What a script started from drawing can do: the whole disc

`tools/recomp/soak/enum_drawscripts.py` reads every level archive of the disc (120 level
lumps, 18,675 objects) and follows each named entry through `callScript` and calls inside
the script.

| Started by | Objects | Entries | Built-ins reached |
|---|---|---|---|
| prompt, property `key` (`PushTrigger` 49, door and switch props 90: `decdoor`, `brazier`, `uwswitch`, `schest`, `cpdoor`, `hcrypt`, `faydoor`, `ptswitch`, `excal`, `wingedv`, one `TestLocation`) | 139 | 51 (3 are the value `1`, which names no entry) | `getv`, `playerHasItem`, `getMissionAvailable`, `getMissionComplete`, `countQuestItems`, `getEvil`, `demoRunning`, `getNumPlayers`, `getPlayerFlag`, `callScript`; stores to script globals in three (`HONOR`, `NITBONUS`, `VALOR`) |
| prompt, property `script` of a jump gate (`Portal`: 38 on the disc, 10 with a script) | 10 | 6 | `getv` only (7 names) |
| head marker, property `exclamation` (`NPC` 16, `Orc2Leader` 1) | 17 | 17 | `getv`, `playerHasItem`, `getEvil`, `callScript` |
| map icon, `iconScript` / `iconValue` (`PushTrigger_ctor` 0x1eca64 → the map-drawing function's `script_runByName` 0x1696c4 and `vars_get` 0x1696a4) | 0 | 0 | no level uses them |

- The only built-in among these that writes shared state is `getv`, and only by appending
  a missing name. No `setv`, no `getRand`, no dialog, no level change: the six `if…` entries
  with side effects that `docs/script.md` P1 left open are named by `action` properties and
  by monster triggers, not by a predicate.
- The four script globals the three entries store (`VALOR` 0x274 and 0x278, `HONOR` 0xc4,
  `NITBONUS` 0x30) are loop counters: every entry that reads one stores it first.
- The table (`g_questVars` 0x86da80, 8,192 bytes, no bounds test) is touched by four
  functions: `vars_get` and `vars_set` look names up, `vars_clearAll` keeps names,
  `vars_getByIndex` serves `save_build` alone. The 120 scripts use 239 different names,
  3,176 bytes if every one were present: it cannot overflow. It is not in the sync record
  (`g_randSeed` + `g_syncAcc`).

**Verdict for the appended name: it cannot reach play.** Present with value 0 or absent, a
name reads 0; what differs is the order and the length of the table, which only the save
file shows. Besides the scripts, `shop_openOrStock` reads two variables on the owner's
machine only (0x1c7b40, 0x1c7bc0): the same append, **Read**, not run.

### What a prompt itself does at draw time (enumeration)

Stores through `this` and state-changing calls in the 22 prompt implementations
(`enum_interact.py`):

| Prompt | At draw time on the owner's machine | Reading |
|---|---|---|
| `PhProp` (4 classes) +0x104, `ItemProp` +0x104, `UserParamProp` +0x168, `Vehicle` +0x190 | stores `g_simFrame` — outside the tick the prediction frame — as a stamp | the only loads are the classes' draw functions (the highlight) and clone: presentation. This is the `ItemProp` +0x104 of the first part's table |
| `AutoProp` (13 classes), `AutoChest` (2), `PushTrigger`, `SpiritAnchor` | run the `key` script | the enumeration above |
| `Savepoint` | HUD messages in a no-save zone | display |
| **`JumpGate`** 0x27d7a0 | **gate +0x4d = 1, `jumpgate_addCurrentLevel` (0x8e3a50, count 0x8e3c30), the "activated" message**, and the script | **shared state**, below |
| the other 11 | nothing | |

### The jump gate found on one machine first — it can reach play

`g_jumpGateDestCount` decides in the same prompt whether a gate can be used at all (one
destination: the "not yet" text and answer 0) and the list is what the jump menu offers.
**Ran**, directed game `local/recomp-out/soak/dir-gate.txt` (two machines, `drundar`, its
gate 0x5f9640 has no script, bus delay 10, jitter 6, loss 10 %; `s26ab`): machine 1 opens
its inventory; in lockstep tick 1,150 its player is put 31 units from the gate on both
machines; machine 1 closes the inventory.

| Tick | Machine 0 | Machine 1 (the owner) |
|---|---|---|
| 1,203 | gate not found, 1 destination | the same |
| **1,204** | not found, 1 destination | **found (+0x4d), 2 destinations, list checksum 7279ff34 against ddd05d44** — from drawing |
| 1,223 | found, 2 destinations (the tick's own prompt, on both) | |

Nineteen ticks, this machine's input lead. What ends it is the tick reaching the same
prompt. If it does not — the player dies, or the level changes, inside those ticks
(`Player_interact` returns at once for a dead player) — the difference stays. **Ran**,
the same game with the player's hit points written to zero in lockstep tick 1,212
(`dir-gate-death.txt`): from tick 1,204 to the end of the game, 1,600 ticks later, machine
1 has the gate found and two destinations, machine 0 neither. What follows from there is
**Read**, not run: the list lives until the act changes; at a gate where the others have
one destination and the owner's machine two, the prompt answers "not yet" on them and 1 on
it, and the use button opens the jump menu in the tick on that machine alone. In ordinary
play the same lead exists for one frame whenever a player walks up to an unfound gate (the
first part's P1 note), with the same condition.

The gate's private generator (+0x44) and light floats differ afterwards with or without
the early marking: `JumpGate_run` draws from it for the light and the sparks only while the
gate's animation state says so, and that state is advanced by drawing — the machine whose
camera is at the gate. Presentation (classification below).

### Sections B and C

```
[Net test: reading a quest variable never adds it to the table]
// was: 0C0EE1A3 (jal libc_strcpy)   now: b 0x1ed844 (v0 is 0 on both ways in)
patch=1,EE,001ED828,word,10000006

[Net test: a jump gate is found only inside the tick]
// was: 14400010 (bnez v0,0x27d864)  now: or v0,v0,s7
patch=1,EE,0027D820,word,00571025
// was: 3C02008E (lui v0,0x8e)       now: bnez v0,0x27d860
patch=1,EE,0027D824,word,1440000E
```

B: a read of a missing name returns 0 and writes nothing; names enter the table by `setv`
(and the loader), which run in the tick. One word covers every reader at once — gate and
`key` predicates, head markers, the shop — and leaves every value read as it was. The table
and the save file then hold only variables that were ever set.

C: `Player_interact` keeps its display-only argument in register s7 across the call of the
prompt (0x1b2650; the prompt is called from there and from the reflector's forwarding
prompt 0x28e2c8, which does not touch s7; nothing calls 0x27d7a0 directly). The test
"already found" becomes "already found, or called for display", so the marking, the list
entry and the message happen in the tick, on every machine in the same tick. It leans on a
register of the caller: right for this executable, to be read again for any other build.

| Check | Without | With |
|---|---|---|
| `sections_test.py` B1–B9 (11 checks; the game's own `vars_get`, `vars_set` and C library) | a missing name is appended; a draw-time read on one machine leaves `a,gate,b` against `a,b,gate` for good | not one byte written by a read; the two tables equal byte for byte; every value read the same, also between a machine with the section and one without |
| `sections_test.py` C1–C9 (10 checks; the prompt called with s7 as `Player_interact` leaves it) | from drawing: found flag, list entry and message on that machine | from drawing: none of the three, the answer and text of a found gate; from the tick: as before; a gate whose script says no: nothing either way |
| seed 3103 (two machines, `nit2`, delay 6, jitter 8, loss 3 %), 5,100 frames | `s26`: quest variables differ in ticks 4662–4665 | `s26ab`: no difference in 5,930 ticks |
| directed gate game above | `s26ab`: gate flag, destination count and list differ in ticks 1,204–1,222 | `s26abc`: found in tick 1,223 on both, no difference in the three in 2,149 ticks (the gate's private generator differs from 1,224, as it does without: presentation) |
| the same with the player dead in tick 1,212 | `s26ab`: the three differ from tick 1,204 to the end (2,803 ticks played) | `s26abc`: no difference in any deciding column in 2,803 ticks; the gate is found on neither |

## The fields that differ between machines in step, classified

The first part's table said "not classified" for most of what the word-by-word comparison
found. Each family below was looked up in the project's documents and, where they had
nothing, read (`tools/fieldxref.py` by class, the callers of `GameObject_rand`, the
functions named) or run. "Presentation" means: every load of the field found is in drawing,
effect, sound or menu code, or in a copy (clone, stored state) that leads back to those.

**Presentation — can be left out of the checksum for good**

| Field | Why it differs | Who reads it | Source |
|---|---|---|---|
| handle heads +0x00/+0x04/+0x08, every object | the run and active lists hold per-machine members (the prediction copy; lights and spouts linked by their draw functions, two nodes per drawn light) | the list code | D31; first part |
| flag 0x100 (+0x0c), every object | set by damage, cleared by drawing | drawing | `docs/creatures.md` C1 |
| flag 0x200000, `Player` | this machine's own player | the draw pass's exclude mask | `docs/netcode.md` |
| creature +0xa8 bit 31 | "boss bar showing", from the list of alive *local* players | the same block of `Creature_run`, a script helper that resets the bar; not saved | C3 (harmlessness Inferred there) |
| colour quads +0x70, +0x80, +0x90…+0x9c, creatures and `Player` | glow and tint helpers called from `Creature_draw` | drawing | `draw-sim-leaks.md`, table of draw-written fields |
| status counters 8, 10, 11 (+0x38c, +0x394, +0x398), creatures and `Player` | `Creature_draw` decrements the first non-zero counter | the glow choice in `Creature_draw` only | D12, D15. **Counters 2, 4, 7, 12, 13 are simulation inputs (D14) and must stay in** |
| model-particle state: creature +0x328…+0x33c, and the words at +0x408, +0x40c, +0x414, +0x41c, +0x42c, +0x49c, +0x4a4 of single classes | two halfwords (+8, +0xa of an emitter record) stepped by `fx_modelParticlesNearCamera` 0x1f61c0, which tests the camera | that function (called from `Creature_run` with object + 0x320) | **Read** for +0x320; the per-class records by the same shape (Inferred) |
| embedded lights: `Savepoint` +0x88…+0xc0, `JumpGate` +0x100…+0x128, `Torch` +0x4c…+0x84, `StaticFire` +0x80…, `AddParticle` +0x100, `Player` +0x4c8, `Lantern` | link words and computed radius of a light that is linked where it is drawn or lit | `light_link`, `light_unlink`, the light pass | D31; **Read** (the `&+K>light_link` call sites) |
| "was drawn" / "is linked" bytes: `Torch` +0x88/+0x89, `Lantern` +0x94/+0x95 (and `Lamp`, `Candle`, `Candle2`, `WaterSpout`) | set by the draw function, which also puts the object on the run list | their run functions, which use only the object's own generator, particles and a ripple | D31, `docs/gameplay.md` 8 |
| private generator +0x44 of `Gold` | `Gold_draw` draws from it (three sites); the only other user is the constructor | — | `draw-sim-leaks.md`; **Read** again |
| private generator +0x44 of `Torch` | `Torch_run` (14 sites) runs only where the torch was drawn | flame and sparks | D31 |
| private generator +0x44 of `JumpGate`, its light floats +0xd4, +0x11c…+0x128 and +0xf8, +0x130…+0x138 | `JumpGate_run` (11 sites) draws for the light's flicker and the sparks only while the gate's animation state says so, and that state is advanced where the gate is drawn | the gate's own light and particles | **Read**; **Ran**: in the directed gate game it differs from the tick after the gate is found, on the machine whose player stands at it, with section C on |
| private generator +0x44 of `Savepoint`, +0x80, +0xcc, +0xc4, +0x58 | the burst and the sparkle; equal unless the mechanism of "Save point" | above | this part |
| private generator +0x44 of `AddParticle`, +0x5c (emitter on), +0xfc (light on), +0xb0/+0xb4 (particle definition), +0x11c…+0x140 (light radius, halo counters) | an effect helper started and stopped from the `…LP` classes' draw and run | `AddParticle_emit`, `_updateLightAndHalo`, `_lightOn`, `_lightOff` | `docs/monsters-2.md` 6; **Read** |
| `Gold` +0x84…+0xbc | five sparkle positions | `Gold_draw` writes and reads them | **Read** |
| frame stamps: `PhProp` and `ItemProp` +0x104, `UserParamProp` +0x168, `Vehicle` +0x190 | the prompt stores `g_simFrame`, at draw time the prediction frame | the class's draw function (the highlight) | **Read** |
| draw matrix of a prop: `ItemProp` and `PhProp` +0x110…+0x13c (seen: +0x13c) | written by the draw function (`mat34_setPosRotZ`); `Prop_run` lowers +0x13c together with the height while a prop sinks | drawing. `Prop_saveState` 0x158d8c writes its rotation and translation into the level's stored state and `Prop_loadState` 0x158f04 gives them back to the matrix, not to the position; `ItemProp_loadState` and `PhProp_loadState` then rebuild the matrix from the position | **Read** |
| trail handles: `HolyBolt` +0xb4, and by the same use `LostSoul` +0xac, `FireStorm` +0xac, `HolyStrike` +0x7c | the value `trail_create` 0x190ff8 returns: a slot of the trail table, which drawing and the prediction copy use too | the trail update and release calls | **Read** (`HolyBolt` to the call; the others at the load only) |
| `Weather` +0xac…, +0x134…, +0x1ec… | a copy of the level light and two particle definitions for rain and snow around the camera | `Weather_run` | **Read** |
| `Player` +0x47a | a cursor byte of the item list | `itemList_input` (and `inventory_dropItem`, which clears it) | **Read**: all nine instructions with that displacement |
| `Player` +0x464, +0x220 | `Player_draw`: gates weapon trails; the equipment draw cache | drawing | `docs/player.md`, `draw-sim-leaks.md` |
| `JumpGate` +0xd0 | "was drawn", written by `JumpGate_draw` | `JumpGate_run`: the light, and the effects of an armed gate — which no shipped level arms | `sync-breakers.md` 5 |
| `Savepoint` +0xc8 (byte +0xc9) | a local player is near | chooses who sees a HUD line | `docs/monsters.md` 7.6 |
| the free lists' order | per-machine allocations (the prediction copy) | the next allocation's address; the checksums do not depend on addresses | first part |

**A cache with a known route into the simulation — leave out of the checksum, watch the positions**

| Field | What it is | Source |
|---|---|---|
| the pose pointer of every animation state (creature and `Player` +0x114; +0x4c, +0x58, +0x98, +0xd8 in simple classes) and the cache word of each track (+0x120, +0x140, +0x160 …; `Savepoint` +0x58, the `AutoProp` family +0xa4, `Gold` +0x64) | a pose is attached where the object was drawn or queried; a simulation query takes whatever is attached | D34, D40, `docs/issues/pose-cache.md`: a route exists in one pattern only; the consequence would be a position, which `pool` compares |

**Not presentation, or not settled**

| Field | What was found | Standing |
|---|---|---|
| animation tracks 5 and 6 of the real player on its owner's machine (`Player` +0x1c0…+0x1f8; also +0x198, +0x1b8) | **Ran**, seed 3005 (three machines), a watch on +0x1e8 of player 0: on the two machines that do not own the player, `SpellCyclone_run` ← `Creature_updateSpells` ← `Player_updateCast` ← `Player_run` — inside the tick — calls `anim_startBlendInOut` (ticks 3,459, 4,874, 8,740); on the owner's machine it does not, because the spell animates `net_objOrGhost`, there the prediction copy (`docs/netcode.md`, hazard 6). The real player's track 6 then holds weight 1.0 against 0.1667 until the next cast | **a risk in principle**: tracks make the pose, and casts are placed from the pose (F6). No position ever differed in 9 million ticks. Of the 17 call sites of `net_objOrGhost`, 12 are followed by particle calls only; `SpellCyclone_run` 0x2d1b04 (**Ran**) and `SpellCharge_run` 0x2c8fe0 (**Read**: `anim_startBlendInOut` and a trail point follow the call) animate what it returns; `SkillCharge_cast`, `SpellBloodLust_ctor` and `_run` were not read. In `SpellCyclone_run` the store is made for the real caster on every machine and for the copy as well where there is one (two calls of 0x16ceb0); the watch saw the real player's word change on the non-owners only, so on the owner's machine the real player's track stack already differed at that moment — not followed further. Open: that, and whether track 6 moves a joint that a cast or a hit reads while it differs |
| `Player` +0x520…+0x52c, `RingPortal` +0x478, `GlowingCylinder` +0x68/+0x6c, `DarknessProjectile` +0x60/+0x64, `ShockProjectile` +0x14c, `PoisonBolt` +0x54, projectile caches +0xf8, +0x130…+0x170 | the last four are a heap address against 0 (a pose or trail buffer by their values); the draw-written projectile caches are named in `draw-sim-leaks.md` | not read here |

So the whole-pool checksum is not yet a deciding column, and what stands between is short:
the first table has to go into the mask by structure (the light, the animation state and
the emitter record sit at a different offset in every class, so a list learned from
samples keeps meeting new pairs); the second stays out as a cache; and the open rows
have to be decided — above all the real player's animation tracks. With those, a difference in `poolraw` would mean a field nobody has
looked at.

## The soak arm: shipping set + A + B + C

`farm.py run --arm s26abc`, seeds 6100–6121 in order, then the four-machine seeds 6130,
6156 and 6164; at most six native instances, `nice -n 19`, on a machine at load 60–130 from
other work. The deciding columns are the first part's plus the menu mutex, the jump-gate
destination count and list; the script's active player is followed.

| Arm | Jobs | Ticks compared | Machines 2 / 3 / 4 (jobs, ticks) | Longest game | Deciding differences | Out-of-sync flags | Ended by a dropped peer |
|---|---|---|---|---|---|---|---|
| `s26abc`: the 26 sections and A, B, C (29 sections, 99 words) | 26 | **1,779,709** | 18, 1,404,844 / 4, 189,755 / 4, 185,110 | 301,002 ticks | **0** | 0 | 2 (seeds 6104 at tick 16,380 and 6156 at 21,020: a kick or a leave from the pause menu under random input; no difference before either) |
| `s26ab`: the 26 and A, B — the hour before C was written, the last four jobs with the new columns | 8 | 365,308 | 5, 210,475 / — / 3, 154,833 | 61,636 | 0 | 0 | 0 |

Machine-ticks of the main arm: 4,119,393. No job timed out, none was left without a log.
The farm was started 08:01 and its last job ended 09:16; nothing of it is running.

- **Neither old difference came back.** The quest-variable column is equal in every tick
  of every pair. No save point differs in +0x84, +0xcc, +0x80 or its private generator at
  any of the 182 sampled ticks (the save points' words that do differ there are the pose
  word +0x58 and words of the light, +0x88, +0x8c, +0xc0), and `pool`, which holds every
  save point's generator, is equal throughout.
- **The new columns never differ**: mutex, destination count, destination list — and the
  active player, which is only followed, in no tick either.
- The sections' code ran: `Savepoint_interact` was entered 363 times and
  `memcard_requestSave` 339 times, so in 24 of them the request was not made (a card screen
  up, or the mutex held: the first is section A's new path); `Savepoint_startSavedEffect`
  101; `JumpGate_interactPrompt` 56,377 and `jumpgate_addCurrentLevel` 22; `vars_get`
  713,044 against `vars_set` 4,900.
- By bus: none 10 jobs, 691,237 ticks; delay 2 jitter 2 loss 1 %: 5, 275,883; 4, 3, 5 %: 3,
  211,626; 6, 8, 3 %: 3, 301,184; 10, 6, 10 %: 5, 299,779. 23 levels seen from 13 start
  levels, 153 level changes after the first entry, 347 deaths, 60,594 ticks with the
  cutscene flag up; `Player_castSkill` 36,922, `Player_usePotion` 152,801,
  `damage_apply` 31,476, 42 of the 54 named skill classes and 144 of the 267 named object
  classes run, `config_commitOptions` 614, `shop_buy` 33, `save_game` 904.
- Followed columns: the weapon-trail bytes (V63) differ in 30 games' player columns,
  `poolfree` in 22 games, `poolraw` in all 26.

What `poolraw` still trips over, with the classification above applied to the words that
differed outside the present mask at the 182 sampled ticks:

| Family | Rows | Games |
|---|---|---|
| model-particle record | 281 | 11 |
| pose cache (animation state pointer, track cache word) | 117 | 21 |
| light, emitter or generator of an effect class | 34 | 9 |
| colour quads | 23 | 3 |
| the real player's animation tracks (open) | 14 | 4 |
| `Player` menu byte, light, draw cache | 8 | 2 |
| trail handle | 5 | 3 |
| status counters 8 and 10 | 4 | 1 |
| `LightEffect` +0x4c, +0x50: the same two lights in the other order in the light list (with a save point's +0x88, +0x8c, one game) | 4 | 1 |
| `FatCyclops` +0xa8: two different objects at one address | 4 | 1 |

Nothing outside the families of the classification. Not covered: as in the first part
(the lobby path, spent points, bosses never met, two networks); every game is two to four
copies of one native build on one machine, so this shows logic differences only; none of
the three sections was run on the emulator rig, on PCSX2 or on a console.

## What is left

- The real player's animation tracks on its owner's machine (classification, last table):
  the one per-machine field found that is not presentation by reading.
- The consequence of a jump gate found on one machine for good was read, not run, beyond
  the list itself differing to the end of a game.
- The three sections on the emulator rig (the first part ran its flush section there) and
  through a lobby-launched game.
- The mask by structure, and `poolraw` as a deciding column.
- `Savepoint_interact`'s second effect of section A — a stale "card screen done" flag
  answered by the burst — was reasoned, not produced.

## Proposed ledger rows (second part)

For whoever edits `FINDINGS.md` (this document does not).

| Row | What to record |
|---|---|
| B9 (replace the first part's "B9 (add)") | **Ran**, shipping set: `Savepoint_interact` 0x28dc30 runs in the tick on the machine whose card screen is not up and does nothing on the one whose is (`memcard_isBusy` at 0x28dc44) — seed 3115, tick 26,847, traced on both machines; a directed game (two save points, the first player's save dialog left open) repeats it: +0x84 differs, the "saved" burst then plays on one machine only, the point's private generator, +0x80 and +0xcc differ for good and `pool` with them. Every reader of those fields is the save point's own effect, draw and stored-state code; none of the 111 save points on the disc has an `action`; no path to a player, a monster, an item, a script, the shared seed or the sync record. Section "save point is used on every machine whatever this machine's card screen does" (5 words, 0x28DC44–0x28DC68): **Executed** (15 checks), **Ran** (seed 3115 and the directed game: no difference with it) |
| K1 (add) | **Ran**, unpatched, seed 5000: the menu mutex 0x4fe53c is 1 on one machine and 0 on the other from tick 6,102 to the end of the game; a save point used at tick 10,178 does nothing on the machine that holds it (this is what the first part's finding 3 saw). With the K1 section alone: no difference in 11,745 ticks. In a net game the mutex is written only in the tick (`Creature_interact`, `Creature_trigger`), by the dialog's message handler and by a script built-in; it gates `Savepoint_interact` and `JumpGate_interact` |
| script P1 / E (replace the first part's row) | **Ran**: the tests in front of `Player_draw`'s display-only `Player_interact` read this machine's current menu state, so a prompt runs at draw time as many ticks before the tick's as the machine's input runs ahead (18 and 19 ticks seen). Enumerated over the disc (120 level lumps, 18,675 objects): scripts started from drawing — 139 `key` objects (51 entries), 10 of 38 jump gates (6 entries), 17 `exclamation` markers, no map icon — reach only reading built-ins, `getv` (which appends a missing name) and four scratch globals that every reader stores first; the table is read by name only, holds at most 3,176 of 8,192 bytes, is not in the sync record: the appended name cannot reach play. Section "reading a quest variable never adds it to the table" (1 word, 0x1ED828): **Executed** (11 checks), **Ran** (seed 3103: no difference with it) |
| new (jump gate) | `JumpGate_interactPrompt` 0x27d7a0 marks an unfound gate found (+0x4d), adds the level to the jump-gate destinations (0x8e3a50, count 0x8e3c30) and shows the message — also when called from drawing. **Ran**, directed game, the suggested set plus the two sections above: the owner's machine has the gate found and two destinations 19 ticks before the other; with the player's hit points written to zero inside those ticks, for the rest of the game. The count decides in the same prompt whether a gate can be used: **Read** from there on. Section "a jump gate is found only inside the tick" (2 words, 0x27D820, 0x27D824; it reads `Player_interact`'s display-only argument in register s7): **Executed** (10 checks), **Ran** (both directed games: no difference with it) |
| new (prompts and interacts) | Enumeration: 22 prompt and 23 interact implementations over 232 classes. Per-machine tests that decide what the tick does: `Savepoint_interactPrompt` (card; removed by the set), `Savepoint_interact` (card; the section above); the shop opening on its owner's machine through `Creature_interact` and `PushTrigger_interact` is by design. Stores a prompt makes at draw time: the jump gate's (above); frame stamps in `PhProp`, `ItemProp` +0x104, `UserParamProp` +0x168, `Vehicle` +0x190, read only by the classes' draw functions |
| V (replace the first part's "Object pools … No reader in the simulation was looked for") | The fields that differ between two native machines in step are classified in `docs/issues/native-soak.md` ("The fields that differ…"): presentation by reading for the lights, the drawn flags, the private generators of `Gold`, `Torch`, `JumpGate`, `Savepoint` and `AddParticle`, the model-particle records, status counters 8 and 10, the frame stamps, trail handles, prop draw matrices and a menu byte; the pose pointers are D34's cache. Not presentation: the real player's animation tracks 5 and 6 differ on its owner's machine because `SpellCyclone_run` (**Ran**) starts its animation on `net_objOrGhost` inside the tick; no position followed in 9 million ticks; open |
| V (new) | Native soak, the shipping set (26 sections, 91 words) plus the three proposed sections (8 words): 26 games from power-on through the developer LAN start (18 of two machines, 4 of three, 4 of four), 1,779,709 ticks, up to 301,002 in one game, 23 levels, 153 level changes, 347 deaths, 36,922 `Player_castSkill` entries, 363 `Savepoint_interact`, 56,377 `JumpGate_interactPrompt`: no difference in any deciding column — the first part's, and the menu mutex and the jump-gate destination count and list — and no out-of-sync flag; 2 games ended by a kick or leave. With the first two sections only: 365,308 more, none. Two to four copies of one native build: logic only |

---

# Third part, 2026-10-13 afternoon: the strafe section, soaked before it goes into the set

**Status: in progress** (started 14:36; this part is rewritten as the arms report).

The section under test is `[Net test: strafe mode - a player can run one way and face
another]` of `tools/recomp/app/fp-proposed.pnach` (84 words; the sha256 of its `patch=`
lines begins 3259b951fc619c0e), proposed and interpreter-tested by the controls work
(`docs/issues/native-first-person-controls.md`, `tools/recomp/app/fp_section_test.py`). It
is a rule change, not a fix: a mode byte per player object (+0x47e) that, while set, makes
`Player_move` turn the character to its player's look and run it along the stick; set by
game message 4 sub-type 2 from a sender at 0x215c98; cleared by `Player_ctor`.

## Programs and method (third part)

| Program | Sections |
|---|---|
| `rta_soak-s29` | the released set 073064bb: the 29 of `tools/play-net/sections-suggested.txt`, 99 words (`patches/SLUS-20973_4028A55F.pnach` as of 12:19, sha1 3b97954e…). The same words as the morning's `s26abc` (the two `patches.cpp` differ in the set's word count alone) |
| `rta_soak-s29f` | the same and the strafe section through `build_soak.py --extra-pnach` |

Built into `local/recomp-out/soak/bin/` from the morning's copy of the tools, runtime
headers and shim (`src-1013`; `recomp.py` and `netshim.cpp` have not changed since) and the
patch files as copied at 14:40 into `local/recomp-out/soak/src-1013b/`
(`local/recomp-out/soak/build-1013b.sh`). The translator merges `Player_move` with the
section's move code into one unit (0x1b4020–0x21297c), as the section's notes say it must.

New in the soak's own code for this part:

- **A driver for the mode** in `soakhooks.cpp` (`SOAK_STRAFE=<seed>[,rate=N][,at=blank]`):
  on every entry to `net_main` — once per displayed frame, on the main thread, outside the
  tick; `net_main` is hooked for it through `tools/recomp/soak/hle-soak.txt` — a machine's
  driver looks at its own player and calls the section's sender with 1 and 0 in turn (15 %
  of the calls repeat the value already asked for): about one frame in 120 at random, one
  frame in 40 while its player is dead, and with a set chance when something happens — a
  new player object, that is a level entry or a respawn (70 %: "on", 0 to 7 frames later),
  a level change becoming pending (80 %), its player dying (80 %), a change of its action
  state — a swing, a block, a cast, a hit taken — (20 %), its menu or a shop opening or
  closing (30 %). Seeded by the job and the machine, so a game repeats. `at=blank` makes
  the same calls from the vertical-blank handler instead, where the runtime's script
  command `call` runs.
- A script can ask the hooks for one call of any game function (control block 0xE0040):
  the directed games use it for the sender (`strafe on`), and for `net_kickPeer`.
- `farm.py`: `--strafe all|mixed|0,2` (whose driver runs); every player's mode byte
  (`p<n>mode`) and the yaw word that travels with the input (`yaw<n>`, 0x5d0bc0) are
  deciding columns beside the facing, which always was; per game the ticks with a player in
  the mode, the sender calls, and of the ticks in which a player in the mode moved more
  than a unit how many went more than 45 and more than 135 degrees off its facing (the same
  share for players not in the mode is the check on the measure: 4 % in the first game —
  knock-backs and pushes); `twin`: two programs play the same seeds and each machine's tick
  log of the one is compared with the other's row for row; `one` takes `--survive`,
  `--pairs` and per-machine lines (`@2: …`) for games in which a machine leaves.


## Directed games for the corners (third part)

`rta_soak-s29f`, level `drundar`, no bus delay; scripts in `local/recomp-out/soak/dir3/`,
runs in `local/recomp-out/soak/t3/`. Deciding columns as in the soak, the mode bytes and
facings included. In the three games in which a machine goes, the two that stay are compared
on through the drop.

| Corner | What was played | Result |
|---|---|---|
| a player dropping while in the mode (`drop.txt`, three machines) | machine 2's player is in the mode from tick 907 and runs about; from frame 2,600 machine 2's bus loses everything | the two others mark it dropped in tick 1,830, the same tick on both, and play on to tick 6,449 with three switches of their own (ticks 4,506, 5,433, 5,436 — each in one tick on both). The dropped player's object stays, its byte 1 on both. **No difference** in 6,449 ticks |
| the host leaving (`hostleave.txt`, three machines) | the host (machine 0) and machine 2 are in the mode (ticks 911, 909); the host starts its exit countdown, as the pause menu's exit entry does | the two others mark it dropped in tick 1,601 and play on to tick 4,382; they switch in ticks 2,437 and 3,367 (one off and the other on, in one tick, on both machines). **No difference** in 4,382 ticks |
| two players switching in the same tick (`sametick.txt`, two machines) | both machines ask in the same frame: both on, both off, both on, one off and one on, the reverse | the two bytes change in one tick each time — 942, 1,262, 1,582, 1,602, 1,922 — on both machines. **No difference** in 2,978 ticks. (A sixth step asked each machine for two calls in one frame; the hooks' control block holds one, so the second was made.) |
| the mode asked for by a dead player (`dead.txt`, three machines) | player 1, in the mode, is given a million points of pending damage in lockstep tick 1,000 and dies in tick 1,001; its machine asks off, on, off, on while it lies dead; the save point at the entry brings it back | the byte follows every request in the same tick on all three machines (1,065, 1,104, 1,146, 1,185); the player comes back in tick 1,248 as a new object with the byte 0 on all three, although the mode was on when it came back. **No difference** in 3,179 ticks (three pairs) |
| a kick while in the mode (`kick.txt`, three machines) | players 1 and 2 are in the mode and running; the host calls `net_kickPeer(2)` 0x131cb8 inside a tick, as the pause menu's kick entry does (the game prints its kick line) | player 2 is dropped in tick 1,610 on both machines that stay; they play on to tick 3,774 and switch in ticks 2,428 and 2,433. **No difference** in 3,774 ticks |


## How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
S=tools/recomp/soak
python3 $S/build_soak.py --name fix26c --sections tools/play-net/sections-suggested.txt \
        --less "Net test: flush before a level load waits for the peers' tick" \
        --extra-pnach $S/proposed-flush.pnach
python3 $S/build_soak.py --name nofix
python3 $S/farm.py plan --arm fix26c --seeds 3000:20                 # what each seed plays
python3 $S/farm.py run  --arm fix26c --out local/recomp-out/soak/farm/x --seeds 3000:200 --instances 6
python3 $S/farm.py report local/recomp-out/soak/farm/x
python3 $S/farm.py one  --arm fix26c --out local/recomp-out/soak/t --seed 3103 --frames 5100 --dump 4661,4662
python3 $S/poolcmp.py local/recomp-out/soak/t/fix26c-3103 4662 --words --masked
python3 $S/flush_test.py                                              # finding 1 in the interpreter
# second part
python3 $S/sections_test.py                                           # the three proposed sections, 36 checks
python3 -I -B $S/enum_interact.py                                     # every prompt and interact: per-machine tests, draw-time stores
python3 $S/enum_drawscripts.py "$RTA_DISC"                            # every script drawing can start, over the disc
cp -R tools/recomp local/recomp-out/soak/src && cp patches/SLUS-20973_4028A55F.pnach local/recomp-out/soak/src/shipping-26.pnach
B="python3 $S/build_soak.py --src local/recomp-out/soak/src --pnach local/recomp-out/soak/src/shipping-26.pnach --rt frozen"
$B --name s26    --sections tools/play-net/sections-suggested.txt
$B --name s26abc --sections tools/play-net/sections-suggested.txt --extra-pnach $S/proposed-sections.pnach
$B --name s26a   --sections tools/play-net/sections-suggested.txt --extra-pnach $S/proposed-sections.pnach --extra-section "save point is used"
T=local/recomp-out/soak/t13                 # columns and directed scripts are in local/recomp-out/soak/ (cols-*.txt, dir-*.txt)
python3 $S/farm.py one --arm s26  --out $T --seed 3115 --frames 28200 --columns local/recomp-out/soak/cols-sp-hub.txt
python3 $S/farm.py one --arm s26a --out $T --seed 3115 --frames 28200 --columns local/recomp-out/soak/cols-sp-hub.txt
python3 $S/farm.py one --arm s26  --out $T --seed 7001 --level drundar --bus none --frames 1500 \
        --directed local/recomp-out/soak/dir-savepoint.txt --columns local/recomp-out/soak/cols-drundar.txt
python3 $S/farm.py one --arm s26abc --out $T --seed 7001 --level drundar --bus delay=10,jitter=6,loss=100 --frames 600 \
        --directed local/recomp-out/soak/dir-gate.txt --columns local/recomp-out/soak/cols-gate.txt
python3 $S/farm.py run --arm s26abc --out local/recomp-out/soak/farm/s26abc --seeds 6100:900 --instances 6   # touch .../alive while it runs
# which function writes a word: build with --instrument trace, then
python3 $S/farm.py one --arm fix26ct --out local/recomp-out/soak/t --seed 3103 --frames 5100 \
        --env SOAK_WATCH=86db94:10 --env SOAK_WATCH_TICKS=4650:4670 --env SOAK_WATCH_LOG=/tmp/w-%M.txt
```

## Files

`tools/recomp/soak/`: `build_soak.py`, `soakhooks.cpp`, `farm.py`, `hub.py`, `poolcmp.py`,
`poolmask.txt`, `flush_test.py`, `proposed-flush.pnach`; second part:
`proposed-sections.pnach`, `sections_test.py`, `enum_interact.py`, `enum_drawscripts.py`
(the second part's runs are in `local/recomp-out/soak/t13/`, its soak in
`soak/farm/s26abc/`, the enumerations' output in `soak/enum/`, the directed scripts and
column files beside them). Everything generated, dumped or
logged is under `local/recomp-out/` (`gen-soak-*`, `soak/`): the farm's rows in
`soak/farm/<arm>/jobs.tsv`, call tables in `calls.tsv`, in-step field samples in
`rawdiff.tsv`, the kept games beside them; the runs of the findings in `soak/t/` (native)
and `soak/rig/` (emulator).

Left undone by the first part (the first three items are done in the second part, which
has its own "What is left"): the two findings' wider consequences; a section for finding 3; the
classification of the in-step fields; scripted games for spent points and the workshop; a
native machine against a rig machine inside the farm. A machine whose partner has ended
is sometimes still running 60 seconds later and is killed by the farm (its last tick-log
row is cut off and skipped, its call table missing from the sums); not looked into.
