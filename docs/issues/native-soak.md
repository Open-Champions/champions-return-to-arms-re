# A soak farm on the native build

Started 2026-10-12. The native build with its network (`docs/issues/native-net.md`) runs a
two-machine lockstep game many times faster than the emulator rig and has been shown to
compute what the emulator computes. This file is the farm built on it to hunt for the
desyncs that are left: the method, what was covered, what was found, and at what rates.
Every result says what was **Ran**; **Read** marks what comes from reading code alone.

**Status: in progress.** The tables below are filled as the farm runs; the section
"Working notes" at the end says where things stand for whoever resumes this.

## In short

- One fault found so far, and it is in the fix set, not in the game: the section
  "flush before a level load waits for the peers' tick" leaves both players' lockstep
  input stuck from the launch on (section "Finding 1"). Reproduced on the emulator rig.
  The machines stay in step, so no comparison of two machines could see it.
- The cause is one delay slot; a three-word form of the section is proposed and was run
  natively and on the rig. The farm's main arm is the suggested set with that form
  (`fix26c`); the game as shipped (`nofix`) is the check on the method.
- Totals: see "Totals" (filled as the farm runs).

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
doing: live-rig.md 8.2). The columns are the rig launcher's, those of live-rig.md sections
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

## Totals

**State at 2026-10-12 15:45 (the farm is still running; these are an hour's work on a
machine at load 250–450, not the result).** `farm.py report <arm directory>` prints the
current figures.

| Arm | Jobs | Ticks compared | Jobs with a deciding difference | Jobs in which a machine dropped a peer |
|---|---|---|---|---|
| `fix26c` (26 sections, the flush section as proposed) | 4 | 191,793 | **0** | 1 (tick 38,407 of seed 3002, the arena; 38,406 ticks compared before it, none differing) |
| `fix25` (the 26 less the flush section) | 4 (one of three machines) | 120,340 | **0** | 0 |
| `nofix` | 6 | 126,950 | **6 of 6** | 5 |

Together 312,133 ticks with fixes and no deciding difference — a twentieth of what one
rig soak covered (5.1 million, live-rig.md 22), so it says nothing yet about what is
left. The speed is the limit: a pair makes 60–200 ticks a second of wall time here
against about 1,000 on a quiet machine (the instances get a fraction of a core each; the
processor time per tick, about 2.2 ms, is itself twice the quiet figure of
`native-net.md`). The pool checksum and the 110 columns do not show in that figure
(the same game with `poolraw` every tick, every eighth tick or never: 12.1, 13.4 and
14.5 s of processor for 4,779 ticks — noise).

### The check on the method: the unpatched arm

All six unpatched jobs differ, each repeating at the same tick in a second run:

| Seed | Level | First tick | Columns at the first difference | Reading |
|---|---|---|---|---|
| 5000 | `hub2` | 10,380 | `pool` alone | an object of the pool (not yet looked at: the second run of this job was made before the farm dumped pools) |
| 5001 | `drundar` | 2,101 | bag 2, load | K2's columns (the potion bag) |
| 5002 | `stomedal` | 1,200 | bag 0 | not classified yet |
| 5003 | `nit1` | 2,733 | bag 0, load, `pool`, object count | an object live on one machine only at that tick |
| 5004 | `pvpnit` (three machines) | 1,123 | load | the carried-weight class (FINDINGS V57) by its column |
| 5005 | `strife` | 5,897 | bag 2, load, `pool`, object count | an object live on one machine only |

The classes are named here by their columns only; which section removes each has not
been tried. Five of the six jobs went on to a dropped peer.

## Coverage

**State at 15:45, the two arms with fixes together (8 jobs, 312,133 ticks).** Counts are
entries of the function on every machine, the prediction copy's included (the `CALL` /
`CALLR` counters; calls inside a merged unit and tail jumps are not counted).

| What | Entries |
|---|---|
| levels entered at the start | `wate2a`, `wate2b`, `torment0`, `bastion1`, `swamp1`, `drunare` × 3 |
| machines | two in 7 jobs, three in 1; four: not yet |
| `Player_castSkill`; `Player_usePotion`; `Player_meleeHit` | 4,576; 18,504; 1,859 |
| `damage_apply`; `Player_takeDamage`; `player_giveExp` | 3,962; 3,057; 156 |
| inventory opened; inventory messages; equip; drop; `itemprop_tryPickup` | 1,406; 4,965; 154; 165; 115 |
| `stats_screen`; `skills_screen`; pause menu opened; `config_commitOptions` | 14,762; 6,683; 672; 173 |
| `shop_openOrStock`; `shop_buySellMenu`; `shop_buy` | 52; 318; **0** |
| `recall_execute`; `save_game`; `game_loadLevel`; `missionMenu_run`; `cut_advance` | 193; 163; 153; 53; 41,443 |
| a stat point or a skill point spent; the workshop; a respawn; the jump-gate menu | **never** (the level-up is left pending in a third of the jobs, but no point was spent) |
| skill and spell objects run (of 54 named `Spell…_run` / `Cast…_run`) | 18 in the first four jobs alone; the full list comes from `farm.py report` |

## Fields that differ between machines in step

From the calibration (six games of the 25-section build in which no player column
differed; pools compared at 42 sampled ticks each). **Ran**: the values; the reading is
from the documents named, and where none is named the field is not classified.

| Class | Offsets | What was seen | Reading |
|---|---|---|---|
| every object | +0x00, +0x04, +0x08 | handle-node addresses | the handle pool is used by the prediction copy too (live-rig.md 11.3) |
| every object | flag 0x100 (+0x0c) | set on one machine | hit flash, cleared by drawing (`docs/objects.md`) |
| `Player` | flag 0x200000 | set on the owner's machine | this machine's own player (`docs/netcode.md`) |
| creatures, `Player`, props | a heap address against 0 at +0x120, +0xa4, +0x98, +0x1a0 … | a buffer on one machine, none on the other | pose and animation buffers (the pose cache is rewritten by the copy: live-rig.md 11.3). Not read per field |
| `Player` | +0x198, +0x1b8 | bit 0x10000 | not classified (animation track state by its place) |
| `Player` | +0x220 | 0xfdff51b7 against 0xffffffff | not classified |
| `Player` | +0x98, +0x9c | 0xffc6ffc6, 0x0000ffc6 against 0 | not classified |
| `Horsemen` +0x414, `Skelight` +0x40c | two low bytes, one or a few apart | not classified; `Creature_draw` decrements a status counter from draw code (`docs/creatures.md` C1) |
| `Nightmare` | +0xa8 bit 0x80000000 | set on one machine | "boss health bar is showing", written from the local alive list (`docs/creatures.md` C3) |
| `Gold`, `Torch`, `JumpGate`, `AddParticle` | +0x44 and blocks of floats | **the object's own random state differs** | not classified: presentation classes by their names; no reader in the simulation looked for |
| `ItemProp` | +0x13c (float 0 / 1 / 2 / 6 / 7), +0x104 | a counter that runs differently | not classified |
| `PhProp` | +0x104, +0x110–0x13c | twelve words | not classified |
| `playerProjectile`, `MissileWeapon`, `DarknessProjectile`, `FireStorm`, `GlowingCylinder`, `Weather`, `AutoProp`, `HackDoor`, `Savepoint`, `Kobold`, `NPC` | see `tools/recomp/soak/poolmask.txt` | | not classified |
| the three free lists | order | differ from about tick 700 to 2,000 on | the next object can land at different addresses on the two machines; the checksums do not depend on addresses |

`poolraw` still differs in most games after this mask (in thousands of ticks), so it is
followed, not counted. Each farm job now dumps its pools at seven sampled ticks and
records the unmasked (class, offset) pairs that differ while the machines are in step
(`rawdiff.tsv` in the arm's directory): the list above will grow from that.

## Proposed ledger rows

For whoever edits `FINDINGS.md` (this document does not). Draft of 15:45; the soak rows
are to be filled in when the farm has run.

| Row | What to record |
|---|---|
| L (new) | Section "flush before a level load waits for the peers' tick" as first written: its word at 0x132DFC is the delay slot of the no-peers branch of `net_flushBeforeLoad`, so with `g_numPeers` = 0 the function makes 16 passes of `net_main(1,1)` (**Executed**: 0 unpatched, 16 patched). In the developer LAN start the main loop calls it before `net_gameInit`, and both players' lockstep pads then stay stuck for the whole game (held word 0x500000, left stick −1.138; the players walk out of `strife` by themselves at tick 228). **Ran** on a native pair and, with a control, on an emulator-rig pair from power-on: the same values. In step throughout. A lobby-launched game initialises in the front end and is not affected (reported by other work). Replacement, three words (0x132DF8 → 1840001D, 0x132DFC → 2A060010, 0x132E28 → 8C82FFF8): **Executed** (13 checks), **Ran** native and rig. `docs/issues/native-soak.md` finding 1 |
| V (new) | Every rig or native run that applied the 26 suggested sections before a developer-LAN launch (2026-10-12 11:04 onward) had both sticks stuck; `docs/issues/native-net.md`'s remark that with the 26 sections "machine A's scripted walk does not move its player" is this |
| V (new) | Object pools of two machines in step, compared word by word (native pair, 25 sections, six games): the block addresses of live objects agree at every sampled tick while the free lists' order does not; the fields that differ are listed in `docs/issues/native-soak.md` ("Fields that differ between machines in step") — among them the private random state (+0x44) of `Gold`, `Torch`, `JumpGate` and `AddParticle` objects. No reader in the simulation was looked for |
| V (new) | Native soak farm, first hour: 312,133 ticks with fixes (26 sections with the flush section as proposed: 191,793; 25 sections: 120,340; one three-machine game), no deciding difference in any column of the rig's soaks or in a checksum of position, facing and random state of every pool object; unpatched, 6 of 6 games differ. To be replaced by the final totals |

## Working notes

State at 2026-10-12 15:45, for whoever resumes this.

- **Running**: `local/recomp-out/soak/farm/supervise.sh` keeps two arms going —
  `fix26c` seeds 3000–4199 (4 native instances, `farm/fix26c/limit.txt`) and `nofix`
  seeds 5000–5599 capped at 30,000 frames (2 instances). **It ends by itself**: it tells
  the arms to start no more jobs when `farm/heartbeat` has not been touched for 45
  minutes (touch it at every poll), or when `farm/stop-all` appears; running jobs then
  finish. To resume: `rm -f farm/stop-all farm/*/stop; nohup farm/supervise.sh &`
  (`farm.py run` skips the seeds already in `jobs.tsv`).
- **Per arm**: `jobs.tsv` (one row per job: first differing tick, columns, values,
  `where` = the classes and offsets of the pool that differ in a second, cut-off run),
  `calls.tsv` (call counts summed), `rawdiff.tsv` (unmasked pool fields differing in
  step at sampled ticks), and the directory of every job that differed, with
  `<job>-again` holding the pool dumps of the tick before and of the tick of the
  difference (`poolcmp.py <dir> <tick> --words --masked`).
- **Half-done**:
  1. The soak itself: 0.3 million ticks with fixes against an aim of tens of millions.
  2. The unpatched arm's classes are named by columns only; seed 5000 (`pool` alone at
     tick 10,380 in `hub2`) has not been looked at:
     `farm.py one --arm nofix --seed 5000 --frames 10800 --dump 10379,10380 --tag=-d`.
  3. `poolraw` is not usable as a deciding column yet: the mask needs the fields in
     `rawdiff.tsv` classified.
  4. Coverage holes to close by scripted jobs rather than random input: a stat point and
     a skill point spent, a purchase, the workshop, a respawn, four machines.
  5. Not started: a pair of the rig against a native machine inside the farm; a
     three-machine developer-start control for `docs/issues/three-players.md` (seed 2001,
     three machines, 30,421 ticks in step with 25 sections, is one such run).
- Experiments on finding 1: `local/recomp-out/soak/t/` (native: `*-1003-pad`) and
  `local/recomp-out/soak/rig/flush-with`, `flush-without`, `flush-proposed` (emulator).
  Calibration dumps: `local/recomp-out/soak/cal/`.
- `RTA_DISC` must be set; machines run at `nice -n 10`; at most 6 native instances.
- Tried and not used: the runtime's `--hle-renderer` (one game, 10,380 ticks: every
  column of the tick log equal to the run without it, timing columns apart; no faster
  under this load).
- A machine whose partner has ended is sometimes still running 60 seconds later and is
  killed by the farm; its last tick-log row is then cut off (the comparison skips it) and
  its call table is missing from the coverage sum. Not looked into.
