# A soak farm on the native build

Started 2026-10-12. The native build with its network (`docs/issues/native-net.md`) runs a
two-machine lockstep game many times faster than the emulator rig and has been shown to
compute what the emulator computes. This file is the farm built on it to hunt for the
desyncs that are left: the method, what was covered, what was found, and at what rates.
Every result says what was **Ran**; **Read** marks what comes from reading code alone.

**Status: ended 2026-10-12 22:45.** The farm is stopped; nothing of it is running.

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
# which function writes a word: build with --instrument trace, then
python3 $S/farm.py one --arm fix26ct --out local/recomp-out/soak/t --seed 3103 --frames 5100 \
        --env SOAK_WATCH=86db94:10 --env SOAK_WATCH_TICKS=4650:4670 --env SOAK_WATCH_LOG=/tmp/w-%M.txt
```

## Files

`tools/recomp/soak/`: `build_soak.py`, `soakhooks.cpp`, `farm.py`, `hub.py`, `poolcmp.py`,
`poolmask.txt`, `flush_test.py`, `proposed-flush.pnach`. Everything generated, dumped or
logged is under `local/recomp-out/` (`gen-soak-*`, `soak/`): the farm's rows in
`soak/farm/<arm>/jobs.tsv`, call tables in `calls.tsv`, in-step field samples in
`rawdiff.tsv`, the kept games beside them; the runs of the findings in `soak/t/` (native)
and `soak/rig/` (emulator).

Left undone: the two findings' wider consequences; a section for finding 3; the
classification of the in-step fields; scripted games for spent points and the workshop; a
native machine against a rig machine inside the farm. A machine whose partner has ended
is sometimes still running 60 seconds later and is killed by the farm (its last tick-log
row is cut off and skipped, its call table missing from the sums); not looked into.
