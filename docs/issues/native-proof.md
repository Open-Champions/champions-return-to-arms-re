# Native build: closing the gaps in the proof

What this file is about: `docs/issues/native-recomp.md` shows that the game's code,
translated to C++ (`tools/recomp/`), computes what the original computes — function by
function against the interpreter `tools/ee_emu.py`, and in play against the original in
the emulator rig. It left four gaps: two differences against the rig that were found and
not explained, 301 functions the function-by-function test could not drive, no count of
which code the compared play actually ran, and no test of the arithmetic helpers on
corner cases. This file closes them as far as stated below.

Conventions as in `native-recomp.md`: **Ran** = executed and measured here; **Read** =
taken from reading code; **Inferred** = a reading that fits the measurements and was not
itself measured; **Not reached** = not done. Everything was run headless on 2026-10-12 on
an Apple-silicon Mac that other jobs kept at a load average of 300–500, which is why the
rig figures are slow.

## Status

(final for this round: 2026-10-12 21:20. Everything below was re-run after the graphics
patch and the flush-to-zero change were merged into `tools/recomp` — translation,
instrumented runtime and state driver rebuilt, all eight tours, the fight, every recorded
state and all arithmetic runs repeated — and gives the same numbers as before the merge.
Nothing of this work is still running.)

| Part | Result |
|---|---|
| 1. The two differences against the rig | both located to the byte, the writing code and the cause — the completion time of a disc read, and which sound-sequence slot was free — measured on both machines. Neither is a translation error |
| 2. The 301 functions without a comparable case | **69 now identical to their return on states recorded in the running game, 6 more identical up to a common stop, 0 different.** 24 are entered and cannot return in isolation (they wait for an interrupt or the I/O processor). 202 were entered by no session; 137 of those are library and C++ runtime code offline play does not call, 20 are named by no call, jump or data word |
| 3. Coverage of play | nine sessions compared with the rig tick for tick (79,547 ticks, 93 levels besides the first, all seven classes): **2,987 of 7,732 functions (38.6 %)** ran. Four tours (34,995 ticks) agree in every column at every tick; in the others position, both seeds, state and all character columns agree at every tick and the pool or record checksum differs for causes located to bytes and writer (3c), one of them not explained. The set was still growing when the round ended |
| 4. Arithmetic corner cases | FPU: 24 instructions × 1,980,400 operand sets, **0 differences** in both builds against their references; integer, multiply/divide and multimedia: 156 instruction words × 250,000 sets, **0**; vector unit 0: 225 forms × 21,000,000 lane results in two modes, **0**; the host model against the rig itself: 15 instructions × 16,384 pairs, **0** with flush-to-zero. One gap found in the runtime (no flush-to-zero) — since fixed by the runtime's keeper |

Across everything: **no difference found is a translation error.** Of the 7,732
functions, 7,460 now have at least one comparable case identical to the return (7,391
from the sweep, 69 from recorded states), 46 only up to an instruction both sides stop
at, 226 none; none fails.

## Round 2 (2026-10-13): the open ends

Kept current while the work goes on (a stop can come without warning). Built from a
**snapshot** of the translator and runtime taken 2026-10-13 07:26
(`local/recomp-out/proof/snap/recomp`: `rt/` as of 2026-10-12 23:48, which has the
runtime keeper's own first-tick rule in the controller replay; `build_proof.py` builds
from the snapshot into `local/recomp-out/proof/build/`). The sessions of round 1 were
run again on this build where said.

### R2.1 NP14 is explained: the comparison's controller replay lacked one row (Ran)

**What decides the tick of a level change.** A level change the game makes itself is a
door: `Player_run` 0x1a5030 → `Player_interact` 0x1b2640 (the nearest object with flag
0x100000 within 48 units; fires when the *pressed-edge* word of the player's pad,
`g_pads[slot]`+0xc, has the use button, 0x1b2b34–0x1b2b48) → `PushTrigger_interact`
0x1ecc70 → `obj_runActionScripts` 0x14dcc8 → `script_runByName` → `scr_interpret` →
`script_newWorld` 0x143dd0 → `script_setNextWorld` 0x1472c4, which copies the name into
`g_pendingLevel`. The main loop acts on a non-empty `g_pendingLevel` at the top of its
next pass (`docs/mainloop.md` section 7). So the tick is the simulation tick in which the
press edge is seen - nothing else: no disc read, no flush, no frame counter, no I/O
answer. Measured with the write-watch on `g_pendingLevel` and the new call-chain record
(`proof_rt.cpp`: the calls under way are printed with every watched change): in `s2`'s
`fay3` the one write is in the tick after 153 in the native run, with exactly that chain.

**Why the native run was a tick late.** The tour script presses the use button when the
tick reaches 152. The rig's tick log has one row per displayed frame, written at the
head of the frame (`gfx_beginFrame`); the row of tick T shows the controller bytes the
game read while it computed tick T. The frame that begins with the row of tick 152
computes tick 153 with the press, the door fires, and the next row is the new level's:
**the log has no row of tick 153, so the replay file had no bytes for it.** At that one
blank the native run's replay found nothing and fell back on its own copy of the script,
whose press reaches the game one blank later than the rig's did - the press was seen in
tick 154. The missing bytes are in the log all the same: the first row of the next
episode still shows the last bytes read (`0079ff7f…`, the use button), since nothing
reads the controller between the last tick and the first frame of the load.

**Fix, in the comparison tool only** (`cmp.py`, `last_tick_fix`, on by default in
`session.py`): the replay file gets, for the tick after each level's last row, the bytes
of the next episode's first row. With it (Ran, `s2w` and `s3w` = the rig logs of `s2`
and `s3` of round 1, native run repeated):

| | before | with the row added |
|---|---|---|
| `s2` `fay3` → `fay2` | rig leaves after tick 152, native after 153; hit points one regeneration step ahead for the remaining 16 levels | both after 152; **hit points, record and pool identical in every later level** but for one stretch of the record (R2.2) |
| `s3` `torment3` → `torment2` | 188 against 189; record and pool different from there to the end | both after 188; record identical to the end, pool identical but for one level (R2.2) |

So the two "rows 2 and 3" of 3c in `s3` (a float of the record, two pose-cache pointers)
were consequences of the extra tick too, not separate effects.

**Which side was right.** Both: each machine did what its input said. The fault was the
harness handing the two machines different input for one tick.

**Can it desync a network game?** No, not this. In a net game a press is not read from
the controller by the tick: `net_main` puts each machine's controller sample into an
input record for a numbered lockstep frame, and every machine applies the same record in
the same frame (`net_frameLoop`, `docs/mainloop.md` section 5), so every machine sees the
edge in the same tick, the door script runs in the same tick, and `net_frameLoop` skips
its ticks on every machine while `g_pendingLevel` is non-empty. Nothing in the chain
above reads a clock, the disc or the I/O processor. (What a native machine and an
emulator machine in one lockstep game do was not run here; the claim is from the chain
measured and the code read.)

### R2.2 The other differences of 3c, located and measured (Ran)

New aids: `session.py` takes `"dumps": ["level:tick", …]` (a memory image on both
machines at the same tick, several per run) and `"watch": […]` (extra columns);
`imgdiff.py` lists the differing words of an image pair with the object, its class and
the offset; `proof_rt.cpp`'s write-watch prints the calls under way. Sessions `s5d`,
`s3d`, `s2d` (images) and `s5e`, `s3e`, `s6e` (columns for the cutscene state and for
the animation state of the objects found) are the tours of round 1 run again in the rig
and natively.

| 3c row | What it is now known to be |
|---|---|
| 2 — record +0x4a74, one unit apart (`s5` from its first tour level, `s2` in `nitmedal`; in `s3` it was the extra tick of NP14 and is gone) | **Ran:** written once per *displayed frame* by the draw pass (0x323284 → `tasks_call` → 0x1dbc48 → 0x1d9cd4 → return of 0x1dd380, `hud_spellSelect`), 1.0 per frame, also while the tick stands. In `nitmedal` the tick stands at 1 for 2,596 displayed frames on the rig and 2,595 natively (a notice; the script's wait runs out): one frame, one unit. A count of pictures shown, per machine; no reader outside the HUD (Read, round 1) |
| 3 — pointers in an object's animation state (+0x120, +0x1a0 of the player in `bossgood` and the last `hub` of `s5`; a `Critter`'s +0x120) | **Ran:** the decoder-slot pointer of an animation track (state +0x0c, +0x20 per track), stored by `animtrack_decode` 0x16e468 from `animcache_alloc` 0x16e388 - "the least recently used slot" - in the run pass (`Player_run` → 0x1a3f70 → 0x1754a0 → 0x16f720 → `anim_buildPose`) and in the draw pass (`world_drawObjects` → `Creature_draw` → `model_drawShadow` → `anim_emitPose` → `anim_buildPose`). Which slot is least recently used follows every earlier use, the draw pass's included, so two machines that showed different numbers of frames, or held different numbers of tracks (row 6), hold different slot addresses with the same contents. An address, not a value |
| 4 — `s6` boss level, two track times 0.9 apart | **Ran:** FINDINGS D8, live between these two machines. `cut_advance` 0x199214 compares the speaker's talk track with `audio_streamPosition(1)` and adds `g_cutAudioCorrection` 0x44fd30 = ±0.1 to **every track time of the speaker** per tick (0x199444–0x1995c8). Logged per tick: the rig's stream position (0x83d108) counts up from tick 346, the native build's is 0 throughout (`rt/sound_null.cpp` answers 0); the rig's correction is +0.1 in ticks 453–461, nine ticks = 0.9; the native build's is 0. The anim_advance argument round 1 took for a sound position is the object's position for sound events (0x116334); the inference there was wrong, the mechanism is this one |
| 6 — `s5`, pool in the last two levels (was: not located) | **`islgoth`, from tick 14:** one object, the `GnomeNavigator` (0x6517c0): its track times advance 1.1 per tick on the rig and 1.0 natively from tick 14 on (logged per tick), so its long idle ends sooner there and it holds three chained tracks where the native build still holds one (image at tick 300: 10 words of that object, +0x120 to +0x178). The cutscene correction is 0 on both machines; the 0.1 is the same code a second time: `dialog_syncMouth` 0x22fdd8 does for `g_dialogFocusObj` 0x4fdcc0 what `cut_advance` does for the cutscene speaker (correction at 0x4fdcdc, loop 0x22ff04–0x22ff28) (**Read**; the two columns of that site were not logged). **`bossgood` and the return to `hub`:** two words, the player object's decoder-slot pointers +0x120 and +0x1a0 (row 3), different because the slot cache's history differs since `islgoth` |
| `s3`, `dis2`, ticks 93–458 (new: it was hidden under the extra tick) | D8 again: three track times of one `NPC` (0x63fac0; +0x134, +0x154, +0x174) 6.5 apart; the rig's correction is +0.1 in 65 ticks (93–246), the native build's 0; stream position 2,048 and up on the rig, 0 natively |

So every difference of the tours is now one of four things, each measured: the tick of a
disc read (NP1), which sound slot was free (NP2), **what the sound driver reports as the
voice stream's position (D8 and its twin in the dialogue code)**, and counts of displayed
frames (the HUD value, the decoder-slot order). None is the translation.

**What this says about a network game (Read, with the measurements above).** D8 is
already in the ledger as a way for one machine's sound timing to reach object state; here
it is seen doing so between a machine with the emulator's sound processor and one with a
silent driver: the speaker's track times differ for the rest of the level, and with them
when its animation ends and what it chains next (`islgoth`). Whether that reaches the
sync hash is D10/D19's question and is not answered here; in these sessions position,
both seeds, state and every character column of the player stayed identical through
it. What the native build adds to the question: **a native machine with `sound_null`
reports position 0, so it never corrects, while an emulator machine does** - a mixed
pair is the worst case for D8, and the native application's real sound driver
(`sound/sound_rta.cpp`) is the one whose reported position decides it. Not run here.

### R2.3 The runtime keeper's first-tick rule replaces the workaround (Ran)

`rt/iop.cpp` (in the snapshot) hands over the next tick's first row while a loading
screen is up. The three sessions that had needed `cmp.py`'s `first_tick_fix` (`s2`, `s3`,
`h6`, as `s2w`, `s3w`, `h6w`) were run on the snapshot build without it: `h6w` identical
at every tick (49 load blanks got the first-tick row), `s2w` and `s3w` identical in
position and seeds at every tick. `first_tick_fix` is removed from `cmp.py`;
`last_tick_fix` (R2.1) stays, since it supplies a row the rig's log does not have.

### R2.4 Play that no session had reached (Ran; one question open - read to the end)

**Why round 1's tours covered so little of the game.** They walk and cast at random
where a level starts, which is seldom where its monsters are: the seven tours gained
experience once (one kill, in `inmine1`).

**The new sessions** (`tools/recomp/proof/play.py`; scripts under
`local/recomp-out/proof/play/`). The generator looks before it writes, as `pilot.py`
does: it runs the native build with the script so far, takes a memory image, reads
where the living creatures are (`objs.py`), and writes the next piece.

- `pt6` **the first level**: both potions drunk (hit points and mana written low
  first); the shop - talk to the keeper, through her lines, "Enter Shop", **buy** twice,
  the sell list, **equip** and **unequip** there, **sell**; the inventory screen
  (unequip, equip, every page); the **save point** (card check, new save, "Save
  Successful"); the pause menu's **Load Game** and the save loaded again.
- `pf0`–`pf6` **one per class, three levels each** (21 levels, 2 of them the boss
  levels): the tour's character with its experience one point below the next level;
  per level four "legs" - the character is put beside the nearest awake creature of a
  kind not fought yet (position and facing written), then strikes, casts and blocks for
  216 frames, the ability buttons moving through the class's skills; after the first
  kill the **level-up** screen (three ability points and skill points spent); both
  potions; a **chest** opened and its contents picked up; at the end hit points
  written to next to nothing among monsters until one of them **kills** the
  character, and the **restart**. Kinds fought: Minotaur, WarBoar, Warrior, Skeleton,
  Marr, Demon, SeaMonster, Kobold, WarWraith, FireBeetle, Goblin, Cazic, Badger,
  LavaMonster, Orc, WoodElfSoldier, Creep, Gremlin, Bubo, Mosquito, GnawSpawn, Hag,
  Tormentor, FatCyclops, Clockwork, Froglock, Ant, BlackWidow, Scorpion, Droid.
- `pp0`–`pp6` **the characters as created** (their first skills), one level each; each
  is killed by a creature within three legs, and restarts.
- Not reached: **the workshop**. The item-list code has a fourth mode that leads to
  `workshop_input` 0x1d0b90 (0x1ceb30), but neither shop met (the first level's
  keeper, the gnome island's trigger) offers more than Buy and Sell to a character
  without gems; how the mode is entered was not found.

How the menus are driven was found in a rig session with its screen text (`rig.py
session … --screen-text`): the use button held 12 frames at an object; in the shop
cross chooses, the use button buys or sells, circle goes back; select opens the
inventory, and the level-up screen while a gained level is not acknowledged.

**Two things the comparison needed.**

1. *Memory writes inside the tick hook.* A scripted write runs at a vertical blank and
   the blank falls anywhere in a frame (3b.1), so the first simulation step that sees
   it can differ by one between the machines; for a position in a fight that is another
   fight. A session marked `"ticked"` has every group of writes moved into the rig's
   tick hook (`ontick M poke …`, armed by the script writing the marker M into
   `g_netFrame`): the hook logs the row and then writes - the order in which the native
   run logs and writes - so both machines apply a group at the same row. With it the
   written columns agree in every row (no "write rows" left in `pt6`).
2. *Pointers through the player object* in a write (`[g_players+0x43d8]+off`):
   resolved by `proof_rt.cpp` when the write is applied.

**Results so far** (position, both seeds, state, hit points, mana, gold, experience,
statistics, bag, equipment, abilities, skills at every tick; the record and the pool
differ in every session for the causes of R2.2 - the HUD's frame count, cache pointers,
the dialogue speaker's track times - confirmed by image pairs in `pt6`):

| Session | Levels | Result |
|---|---|---|
| `pt6` | first level, 1,585 ticks; after the load 189 | **identical at every tick** - potions, shop, equipment, save, load |
| `pf1` | blood1, fire1, bossgood: 5,157 ticks | **identical at every tick** |
| `pf3` | swamp1, dis2, torment2, restart: 5,631 ticks | **identical at every tick** |
| `pf5` | fire3 (death), restart, storm3, arachna1, restart: 5,090 ticks | **identical at every tick** |
| `pf6` | honor, wate2a, inmine1, restart: 5,699 ticks | **identical at every tick** |
| `pf2` (first run) | storm1, fay1, nit1: 4,243 ticks identical; the restart after the death differed from its second tick | the script's doing, below; run again |
| `pf4` (first run) | islsm1 identical; innovat1 differed from tick 43, islc1 after it | the script's doing, below; run again |
| `pf0` | valor identical to tick 372; the shared seed differs from tick 373, everything after | **explained, and identical once the cause is removed** - below |

**`pf2`, `pf4`: writes in frames the other machine does not have (the harness).** In
`pf4` the script's "skip the arrival cutscene" pressed start in a level without one
(it tested the camera's mode), which opened the pause menu; in `pf2` the character died
while the script was still writing its hit points and position. In both the script then
writes while the tick stands - in a menu, in the restart's load - and the tick stands
for more frames on the rig than natively (the load: 120 against 38). A write the rig
applied in a frame the native run does not have is applied a tick late there (`proof:
poke … applied late`, 19 times in `pf2`). `play.py` now tests the cutscene flag itself
and looks after every six tries whether the character is dead; both sessions were made
and run again (table at the end of this section).

**`pf0`: the first place where the two machines' simulations part for a cause that is
in the game (Ran, every step).**

1. After the level-up screen is closed the game "warms up": `g_warmupFrames` 0x506048
   is set to 10, counts down one per displayed frame and is **put back to 10 while
   terrain streaming is busy**; while it is not 0 the game is frozen and the tick
   stands. Logged per frame: the screen was up for 1,159 frames on both machines; the
   warm-up after it took **25 frames on the rig and 11 natively**.
2. `script_runDeferred` 0x1ed5a0 (run task `Script`, priority 125) has no test for
   "frozen": it runs once per displayed frame, paused or not, and each run carries out
   the scripts queued by the frame before - which is how a level script counts time.
   Its counter `g_scriptDeferFlip` 0x4f8690 is 14 further on the rig in an image pair
   at tick 349 (0x62f against 0x621) - the 14 frames.
3. The level's monster generator fires 14 ticks earlier on the rig: `script_runDeferred`
   → `script_runByName` → `scr_interpret` → `script_generateMonster` 0x1473d4 →
   `ScriptGenerator_spawn` 0x265fc4 → `world_createObject` → `Skeleton_ctor` 0x2a5af4 →
   `Creature_ctor`, in tick 373 on the rig (break point on `GameObject_ctor`) and in
   tick 387 natively (write-watch with the calls under way).
4. `GameObject_ctor` 0x14cb10 draws the new object's seed from the shared generator:
   from tick 373 the two machines' `g_randSeed` differ, and with it every fight after.

**The proof of it:** the native run was repeated with nothing changed but
`g_warmupFrames` held at 10 for 15 more frames at that one place (written from a file,
`PROOF_EXTRA_POKES`), so that its warm-up is the rig's 25 frames. The session then
agrees with the rig **at every tick of all three levels** - valor 1,497, wat1 1,305,
bossevil 1,171 ticks, the boss fight and the death in it - in position, both seeds,
state, hit points, mana, gold, experience, statistics, bag, equipment and skills. With
14 frames instead of 15 the generator fires one tick late and the run parts again.

**What it means.**
- It is not the translation: the native build does exactly what the original does once
  its streaming takes as long.
- **Offline, two machines with different disc or streaming speed play different games
  after the first menu, save screen or cutscene** (the nine callers of
  `mainloop_startWarmup`): level scripts run on displayed frames, the simulation on
  ticks, and the warm-up puts a machine-dependent number of frames between them. So a
  tick-for-tick comparison of a native machine with an emulator (or a console) through
  a menu holds only while no level script is counting - which is why `pf1`, `pf3`,
  `pf5` and `pf6` agree through their level-up screens and `pf0` does not. This is the
  limit of what "identical in play" can be made to mean offline; before, it had only
  been seen in cosmetic state (NP1).
- **In a network game (Read, `docs/mainloop.md` sections 5 and 6):** the run pass is
  not called once per displayed frame there but once per lockstep tick
  (`net_frameLoop` → `tasks_run(1, 2)`), and `game_isFrozen` is `g_paused` alone, so
  `script_runDeferred` runs once per tick on every machine whatever each one's warm-up
  does. The mechanism above does not exist there. Not run on a pair here.

### R2.5 The 24 functions that wait: compared at a bound (Ran)

**Method.** The translation counts: its budget goes down at every call and at every
taken branch or jump to a target at or before it inside the same unit (`BUDGET()`), and
when it is gone the test driver stops with the whole state. The interpreter was made to
count the same events (`realproof.py`, `BoundedEE`): the counted branch sites are taken
from the snapshot translator's own units (`build_proof.py sites`: 6,775 sites, the same
number as `BUDGET(); goto` occurs in the generated code), a call counts where the
translation counts it - after the delay slot, before the callee's first instruction. Both
sides are given the same count N and stop at the same point of the same instruction
stream; there everything is compared that the function-by-function test compares at a
return (registers at 128 bits, HI/LO, FPU, the calls so far with their arguments, every
byte of memory).

**Result.** `realproof.py bounded` on the states of the nine sessions of round 1, each
state with callees running and with calls replaced, at N = 16, 256, 4,096 and 32,768:

| | |
|---|---|
| functions | 24 (the list of part 2) |
| runs | 2,568 |
| identical at the bound | **2,568** |
| different | **0** |

Not one of those runs reached a return: the functions do wait. **Control:** with the
interpreter stopped one event later than the translation (`PROOF_BOUND_SKEW=1`) 139 of
144 runs are reported different (the other five are idle loops whose extra turn changes
nothing), so the comparison sees a shift of one loop turn.

What this adds over round 1: there, only the calls made up to the limit were compared;
now the registers and all of memory are, 32,768 loop turns and calls into each wait.
What it does not do: it does not show what the functions do once the interrupt or the
answer they wait for arrives - that is play (part 3), where they all run.

### R2.6 The 46 "partly compared" functions, and vector unit 0 in the interpreter (Ran)

**What the 46 are (Read, counted from the executable).** Not mostly vector-unit code:

| Functions | Where both sides stop | Status |
|---|---|---|
| 36 | at their first instruction: each **is** a `BREAK` (C-library entries that are nothing else, 0x3a44d8–0x3a5190) | complete: the trap is all there is to compare |
| 1 (0x3a2e10) | in such a `BREAK` entry it calls and then jumps to | complete in the same sense |
| 5 (0x35c858 and the four SDK entries 0x35c8c8–0x35c8f8 that jump into it) | at the `ERET` that ends them (interrupt enable/disable in kernel mode) | complete: `ERET` is their return |
| 1 (0x3e3a58) | at the divide check `BREAK 7` on made-up input (a zero divisor) | **open**: no session entered it, so there is no real state |
| **3** (`gfx_uploadMicrocode` 0x19be08, 0x34f890, `sceGsSyncPath` 0x34fe78) | at a `CTC2` / `CFC2`, the first vector-unit instruction | **finished below** |

The executable holds 15 vector-unit instructions in four functions: those three, and
`anim_buildPose` 0x16ed40 (two `VCALLMS`, two `LQC2`, `QMTC2`, `CTC2`, three `QMFC2`),
which the sweep had passed on inputs that do not reach them.

**The interpreter's vector unit** is `tools/recomp/proof/vu0ref.py`: the six register
moves, `VCALLMS`, and the microprogram instructions `rt/vu0.h` implements, written a
second time with all arithmetic in exact integer arithmetic (`softf.py`: IEEE single
precision rounded toward zero, denormals flushed). `realproof.py` gives it to the
interpreter (`VuEE`); `proof_driver.cpp` runs the translation's side on `rt/vu0.h`;
`proof_rt.cpp` records the unit's registers, microprogram and data memory with every
state (it needs `g_vu0` of `rt/runtime.cpp` visible: item 1 of
`tools/recomp/proof/rt-proposed.patch`; the proof's build has it in its snapshot). The
unit's registers, accumulator, I, control registers and both memories are compared
besides everything else.

**Result** (states recorded with the unit, session `h6w`; functions that use the unit or
call one that does):

| Function | Runs | Result |
|---|---|---|
| `anim_buildPose` 0x16ed40 | 8 states (its 1st, 2nd, 5th, 20th … 12,500th call), callees running; 926 to 3,605 microprogram instructions each | **identical to the return** |
| 0x1795f8 (calls it) | 7 | identical to the return |
| `sceGsSyncPath` 0x34fe78 | 8 | identical to the return |
| 0x34f890 | 1 | identical to the return |
| `gfx_uploadMicrocode` 0x19be08 | 1 state: with calls replaced identical to the return; with callees running (one waits) identical at 256, 4,096, 32,768 and 262,144 counted events | identical |

**Control:** a reference whose multiply is one unit of the last place off fails all eight
`anim_buildPose` states (first difference in pose memory and `vf1`).

So of the 46: 42 are complete as they stood (their stop is their end), 3 are now identical
to the return, 1 has no real input. More states of `anim_buildPose` come with the play
sessions (R2.4).

### R2.7 The vector unit in the rig with infinities and NaNs, and what `vu0.h` should do (Ran)

**Measured** (`tools/recomp/proof/rigvu.py`, the emulator at commit 83700b2c on this
ARM64 machine): 14 upper instructions (ADD, SUB, MUL, MAX, MINI and their x-broadcast
forms, FTOI0/4, ITOF0/12, ABS) on 128 × 128 operand patterns - 11,449 pairs finite and
normal, 2,240 with a denormal, 472 with an infinity, 2,223 with a NaN - each as its own
microprogram written into the unit's program memory, run with `VCALLMS` in the game's
thread. Results that differ from the emulator's, of 229,376:

| Against | finite | denormal | infinity | NaN |
|---|---|---|---|---|
| `rt/vu0.h` as it is | 0 | 260 | 1,888 | 13,331 |
| `rt/vu0.h` as proposed | 0 | 0 | 476 | 4,644 |
| `vu0ref.py`, model 'host' | 0 | 260 | 1,240 | 8,128 |
| `vu0ref.py`, model 'console' | 0 | 0 | 476 | 4,644 |

- **On finite normal operands the header is the emulator**, bit for bit (the first
  measurement of the vector unit against the rig itself; round 1 had only the written
  reference).
- **The emulator does not compute with the host's infinities and NaNs.** It brings
  operands of exponent 255 to the largest number before it multiplies or subtracts
  (0 × ∞ = 0 there, NaN on the host), compares MAX and MINI as sign-and-magnitude
  integers, and does so per instruction: ADD clamps its first operand only, ADDA, SUBA,
  MSUB and MSUBA none (Read: `Source/ee/VUShared.cpp`, the `…_base` functions; the
  comments there name the games each clamp was added for). FTOI is the host's
  conversion (NaN gives 0).
- **`vu0.h` today** hands the host's results on, and a NaN's sign is the host's choice
  (ARM64 0x7fc00000, x86-64 0xffc00000): the difference the Windows build found.

**The console** has neither infinity nor NaN nor denormal in the unit: exponent 255 is an
ordinary exponent, exponent 0 is zero (the same statement `docs/issues/native-app.md`
10.1 rests on; there is no console here to measure). **Proposal** (item 2 of
`rt-proposed.patch`): the rule `render/vu1_step.h` already follows for VU1 - an operand
of exponent 255 is read as the largest number of its sign, one of exponent 0 as zero, a
result too small to be a number is zero, MAX and MINI compare bit patterns. Then the
operands are finite, the host rounds toward zero, no infinity or NaN can arise, and the
result does not depend on the host. It equals `vu0ref.py`'s 'console' model on all
229,376 results (the last two rows of the table are the same numbers). Against the
emulator 5,120 results remain different: 2,816 in ADD with an infinite or NaN second
operand, 2,304 in FTOI of a NaN - places where the emulator itself falls back on the
host. A header that followed the emulator there exactly would be host-dependent again.

**Does it matter in play? (Ran)** A measurement build (`rta_proof_vu`: the proposed
header with counters) was run on four recorded sessions:

| Session | Microprogram instructions | Operands read by arithmetic | with exponent 255 | denormal | Tick log against the present header |
|---|---|---|---|---|---|
| `h6w` | 61,818,048 | 525,388,452 | 2,844,104 | 5,447,392 | byte for byte the same |
| `s2w` | 97,116,899 | 825,632,858 | 4,856,003 | 8,553,820 | the same |
| `s3w` | 85,328,940 | 725,145,972 | 4,053,269 | 7,522,968 | the same |
| `s5w` | 84,047,957 | 714,236,390 | 3,961,874 | 7,378,943 | the same |

So such operands are not rare - one in 180 has exponent 255 in the game's own pose
program (stale words and integers in fields the program carries along) - but nothing
the game reads back depends on them: besides the tick logs, an image of all 32 MB taken
at the same tick of `h6w` with either header is identical. The game's program executes
no MAX or MINI. The change is therefore free in these sessions, and it removes the one
place where an ARM64 and an x86-64 build of the runtime compute different bits.

## Tools added (all in `tools/recomp/proof/`, outputs under `local/recomp-out/proof/`)

Nothing under `tools/recomp/rt`, `render`, `sound`, `app`, `net` and nothing in
`recomp.py`, `build.py`, `difftest.py` or `rigcompare.py` was changed.

| File | What it does |
|---|---|
| `cmp.py` | `rigcompare.py` with an output directory per run, a choice of native binary, extra watch columns and extra arguments for the native run; removes a level's loading rows from the controller replay file (3b.3) |
| `instrument.py`, `proof.h.in` | a copy of the generated translation with one line added at every entry point: `PROOF_ENTER(n)` |
| `proof_rt.cpp` | what that line calls, linked into a build of the unchanged runtime (`bin/rta_proof`): a counter per entry point; the machine state at a function's entry (registers and all memory, pages stored once); a write-watch that reports the two points of execution between which watched bytes changed; memory dumps and memory writes keyed on level episode and tick |
| `build_proof.py` | translate, instrument, build `rta_proof` and `proof_driver` in directories of their own |
| `proof_driver.cpp` | `rt/test_driver.cpp` with recorded states as input |
| `realproof.py` | the function-by-function comparison on recorded states (part 2) |
| `tour.py`, `session.py` | scripted sessions: class, character, a list of levels, seeded play; rig run, native run on the rig's controller bytes and memory writes, comparison (part 3) |
| `coverage.py` | adds the counters of several runs up against the function table (part 3) |
| `summary.py` | a session's comparison, one line per level, with the rows of scripted memory writes counted apart |
| `arith.py`, `arith_main.cpp`, `softf.py`, `rigarith.py` | the arithmetic tests (part 4) |

The instrumented build was checked to be the same program: on the fight session it gives
the same 27 columns at every tick as the plain build, including the two differences below
at the same ticks (**Ran**).

## 1. The two differences against the rig

### 1a. One tick of the player record in the first level (hub tick 7)

**The bytes (Ran).** Both machines were run again with the 256 record bytes logged as a
column. Six bytes differ, in one row: the upper halves of three floats at record +0x4a88,
+0x4a98 and +0x4aa8, which are 0.0 on the rig and 1.0 in the native build at tick 7 and
1.0 on both from tick 8 on. They are the diagonal of a 3×4 matrix at the head of the main
weapon's trail state (`docs/player.md`, +0x4a88).

**The writer (Ran, native write-watch).** The three words change between the return of
the call at 0x1f6e00 (`mat34_setIdentity`) and the return to 0x1bc964: the store is in
`fx_modelStatusEffects` 0x1f6ac8, called from `Player_weaponTrails` 0x1bc768 with the
trail state as its third argument.

**The cause (Ran).** `fx_modelStatusEffects` returns at once while its model argument is
null (0x1f6b70). `Player_weaponTrails` gets that argument from `eqcache_lookupModel`
0x1a2d48, which answers null until the weapon's model has arrived from the disc. Logged
on both machines in one more run:

| Tick (hub) | Equipment-cache record of slot 0 (0x866388) holds the model | Trail matrix written |
|---|---|---|
| 6 | native: yes — rig: no | neither |
| 7 | both | native: yes — rig: no |
| 8 | both | both |

So the matrix is written one tick after the model is there, on both machines, and the
model is there one tick earlier in the native build. Moving the native build's disc
timing moves the write with it: default timing — written in tick 6; `--emulator-timing`
(the delays Play! applies) — in tick 8; the rig — in tick 7. It is the completion time of
an asynchronous disc read, counted in ticks.

**Can it reach the sync hash? (Read)** The sync hash covers the shared seed and the
player positions (`docs/netcode.md`, row 14). The 0x30 matrix bytes are read and written
only by `fx_modelStatusEffects` (`tools/fieldxref.py` over record +0x4a88–+0x4b07: the
other hits are `Player_meleeHit` storing the hit material and timer at +0x4ac5/+0x4ac6
and `player_importCharacter` copying the block), which emits particles and draws from the
cosmetic generator. The cosmetic seed was identical on both machines at every hub tick of
that run, so the first call drew nothing. Not sync-hash material; on two consoles the
same one-tick spread would exist whenever their drives differ.

### 1b. Twenty-seven ticks of the object pool in the fight (valor, ticks 3886–3912)

**The bytes (Ran).** The rig run was repeated twice: once with the pool logged as 232
checksums of 4 KB (one chunk differs, 0x6c88c0–0x6c98bf, at exactly the 27 ticks), once
with that chunk logged in full. One 32-bit word differs: **the player object's +0x00**,
the head of its "who refers to me" handle list (`docs/objects.md`). The two machines hold
different handle nodes there (0x84a404 and 0x84a4cc, nodes of `g_handleNodes`):

| Ticks | rig | native |
|---|---|---|
| 3830–3885 | 0x84a4cc | 0x84a4cc |
| 3886–3888 | 0x84a404 | 0x84a4cc |
| 3889–3912 | 0x84a4cc | 0x84a404 |
| 3913–3934 | 0x84a404 | 0x84a404 |

Position, facing, state, both seeds' simulation side, hit points and every other byte of
the 947,968-byte pool are identical through the window.

**The writer (Ran, native write-watch on the four bytes, ticks 3820–3940).** Every change
of the word lies between the entry of `handle_clear` 0x1a1698 and the return to 0x214324,
or between the entry of `handle_link` 0x1a1738 and the return to 0x214334: both calls are
in `sound_playOnObject` 0x214230, which picks one of the 32 sound-sequence slots
(`g_soundSeqs`), clears the slot's handle and links it to the object the sound is to
follow. Nothing else wrote the word in those 120 ticks.

**The cause (Ran).** The fight was run once more on both machines with the 32 slots
(2,432 bytes at `g_soundSeqs`) logged in full:

- The slots differ between the machines at 854 of the 3,978 ticks compared, first at tick
  1,522 — while every simulation column is identical. The bytes that differ are the
  slots' time counters (+8 to +10) and track flags (+32, +34): where each sound is in its
  life. That follows the sound driver, which is `sound_null.cpp` here and the emulator's
  sound processor on the rig.
- In the window: slot 30 holds a handle to the player on both machines throughout. Slot
  31 holds one from tick 3886 on the rig and from tick 3889 in the native build; and the
  native build re-links slot 30 at tick 3885, the rig at tick 3888. The same two sounds
  are started on the player on both machines, in the two slots the other way round,
  because the slots were in different states when the first was asked for. From tick 3889
  both machines hold the same two handles in opposite list order, and at tick 3912/3913
  the next re-link puts the same node at the head on both.

So the difference is the order of two back links, set by which sound-sequence slot was
free on each machine. With `--emulator-timing` (which changes when the I/O processor's
answers arrive, not what the sound driver answers) the window is the same 27 ticks.

**Can it reach the sync hash? (Read)** Not through this word: the handle list is a list
of back links, walked when the object is deleted and when a handle is cleared; no code
found orders anything by it. Two things were **not** audited: every caller's use of
`sound_playOnObject`'s return value (a handle, or −1 when no slot is free), and whether
a different order of handle-node allocation can change simulation state anywhere (node
addresses differ, the nodes' contents do not). On two consoles the sound hardware is the
same, so the question only arises between unlike machines.

## 2. The 301 functions without a comparable case

### Why the interpreter stops on them (Ran: read off the sweep's report)

`realproof.py want` reads `local/recomp-out/sweep-stub.txt` (the stub-mode sweep, twelve
synthetic inputs per function) and lists the functions with no run that reached the
return: 301, plus 40 whose only comparable runs end at an instruction both sides stop at.
By what stopped the interpreter in most of a function's twelve runs:

| Reason on synthetic inputs | Functions |
|---|---|
| step limit of 100,000: a loop that waits for something an interrupt or the I/O processor would do, or a long loop over made-up data (a string copy without an end, a list that points into itself) | 143 |
| wild pointer: an access outside the 32 MB through a made-up pointer | 109 |
| unaligned access through a made-up pointer (the interpreter refuses it, as the CPU would) | 40 |
| an instruction the interpreter does not implement (vector unit, some COP0) | 6 |
| a jump to address 0 or out of the code through a made-up function pointer | 3 |

No function of the 301 stops on a system call or `BREAK` alone; the 40 "partial" ones are
those (their runs end at a `BREAK`, a vector-unit instruction or a trap on both sides).

### Method: real inputs (Ran)

The instrumented runtime records, at a function's entry in the running game, the whole
register context and all of memory (`--opt proof-capture`; its 1st, 2nd and 5th call per
session; memory as 4 KB pages stored once, about 20,000 pages for 168 states).
`realproof.py replay` runs each recorded state to the function's return in the
interpreter and in the translation (`proof_driver`, the test build of the plain
translation) and compares what `difftest.py` compares — all general registers at 128
bits, HI/LO and the second pair, the shift amount, the FPU registers, accumulator and
compare bit, every call with its eight integer and eight float argument registers — and
**every byte of memory**: all 32 MB, the scratchpad and any other page touched (not only
the pages a write log names). Each state is tried with callees running (the whole call
tree is compared); when the interpreter does not reach the return within three million
instructions, again with every call replaced by "return 0" on both sides. On both sides a
system call returns 0, the mirrors of main memory fold as `rt/runtime.cpp` folds them,
and hardware registers are plain memory that starts at zero.

### Result (Ran: nine sessions — the fight and eight tours of part 3; 1,679 states, 2,310 runs)

| Of the 301 | Functions |
|---|---|
| identical to the return, callees running | 62 |
| identical to the return, calls replaced | 7 |
| identical up to an instruction both sides stop at (an `ERET` in four SDK functions around 0x35c8c8; the first vector-unit control-register move in `sceGsSyncPath` and 0x34f890) | 6 |
| entered, not comparable: neither side returns in isolation | 24 |
| entered by no session | 202 |
| **different** | **0** |

Of the 40 partial ones: 2 entered (`gfx_uploadMicrocode` and 0x35c858, again identical
up to the stop), 38 not entered (37 of them library code).

**The 24 that cannot return** wait for something only the running machine supplies —
a vertical blank, an answer of the I/O processor, the end of the session:
`gfx_waitVsync`, `iop_loadModules`, `engine_init`, `sound_init`, `scePadInit`,
`sceMtapInit`, `sceSdRemoteInit`, `sceMcInit`, `lgAudInit`, `loadscreen_renderLoop`,
`loadscreen_stop`, `mainloop_runSession`, `mainloop_runModalCallback`,
`shop_openOrStock`, and 0x14fa88, 0x17ca58, 0x31ed80, 0x323dcc, 0x3536e0, 0x353f00,
0x35c190, 0x36a878, 0x36a988, 0x36af80. On both sides they run until the limit (three
million interpreter instructions; 400 million loop iterations and calls in the
translation), and the calls they made up to there — site, target and arguments — are the
same on both sides in every one of their 642 runs. That is evidence, not a comparison of
an end state. A method that would compare them is not built: stop both sides after the
same number of backward branches and calls (the translation counts exactly those) and
compare the state there.

**The 202 never entered**, by where they lie: 84 in the libraries above 0x34e000 (SDK,
keyboard, network configuration, UDP, lobby API), 53 in the C and C++ runtime, 11 in the
lobby and network-session client, 3 in the netcode — 151 that offline play has no reason
to call — and 51 in game code (11 monsters, 10 skills and spells, 10 engine, 7 menus, 6
effects, 4 player, 3 others) that the tours did not reach. Twenty are named by no `jal`,
no `j` and no data word of the executable, so nothing visible can call them (dead code,
unless reached through a computed address): 0x164a48, 0x19d0c4, 0x19dea4, 0x1c2120,
0x1d3f2c, `minimap_blipColor` 0x1e40a8, `dbg_scanIopMemory` 0x323d70, 0x3284c0, 0x3570f8,
0x357a40, 0x35f3f8, 0x360ea0, 0x3676d0, 0x3697f0, 0x38235c, 0x3a0f50, 0x3a4eb8, 0x3ad1c0,
0x3c7f60, 0x3c8030. The full list with reference counts:
`realproof.py report local/recomp-out/proof/real/* --hits … --list`.

A first run reported 6 differences; all six were the test driver folding the 0x30000000
mirror with the wrong mask (`proof_driver.cpp`, fixed), none was the translation.

### Beyond the 301: every function a tour enters, from its first real call (Ran)

One tour (class 1, 13 levels) was run with a state recorded at the first entry of every
entry point it reached, and all were replayed (budget 200,000 instructions with callees
running, then 100,000 with calls replaced).

| Of the 2,015 functions entered | Functions |
|---|---|
| identical to the return, callees running (the whole call tree compared) | 1,845 |
| identical to the return, calls replaced | 123 |
| identical up to an instruction both sides stop at | 9 |
| not comparable within the budget | 38 |
| **different** | **0** |

So for 1,968 functions the sweep's result on made-up inputs is now also a result on the
registers and the 32 MB of memory the game really called them with.

## 3. Coverage of the comparison in play

### The counter (Ran)

`instrument.py` adds one line at each of the 12,147 entry points of the generated code;
7,732 of them are the first instructions of the functions of `ghidra_funcs.tsv` (nine of
those are labels inside another function's body and are counted at the label). A run of
`bin/rta_proof` with `--opt proof-hits=FILE` writes how often each was reached;
`coverage.py` adds runs up.

### 3a. Sessions compared with the rig (Ran)

Each session: `session.py NAME rig`, `native`, then `summary.py NAME`. Rows are matched
on level episode and tick as in `rigcompare.py`; 29 columns (rigcompare's 27 and
checksums of the 32 sound slots and of the equipment cache).

| Session | Levels | Ticks compared | Result | Functions reached | New | Total |
|---|---|---|---|---|---|---|
| fight (class 6 as created) | start-up, front end, first level, valor | 4,810 in valor | identical but for 1a and 1b | 1,839 | 1,839 | 1,839 |
| `s6` class 6 | 13 | 9,916 | identical except 122 ticks of the pool in the boss level (3c, row 4) | 2,048 | 259 | 2,098 |
| `s5` class 5 | 13 | 9,916 | position, seeds, state, hit points, mana, statistics, bag, equipment, abilities, skills identical at every tick; one word of the record differs from the first tour level on, and the pool in the last two levels (3c, rows 2 and 6) | 2,175 | 243 | 2,341 |
| `s0` class 0 | 13 | 10,016 | **identical at every tick** | 1,906 | 36 | 2,377 |
| `s1` class 1 | 13 | 8,856 | **identical at every tick** | 2,054 | 77 | 2,454 |
| `s3` class 3 | 13 and one the game entered | 8,861 | position, seeds, state and character columns identical at every tick; one word of the record and two of the pool differ from the fourth level on (3c, rows 2 and 3) | 2,255 | 206 | 2,660 |
| `s4` class 4 | 13 | 9,056 | **identical at every tick** | 2,093 | 93 | 2,753 |
| `s2` class 2 | 15, four level changes made by the game | 11,049 | position, seeds, state identical at every tick; hit points one regeneration step apart from one of those level changes on, record and pool with it (3c, row 5) | 2,298 | 139 | 2,892 |
| `h6` class 6 | the first level and its twin, 1,599 ticks of walking each, three times | 7,067 | **identical at every tick** | 1,909 | 95 | 2,987 |

"Identical" leaves out the tick of 1a (in every session), the columns that are not
expected to agree — the displayed-frame counter, the cosmetic seed, the controller
checksum, the sound-slot and equipment-cache checksums (part 1) — and the "write rows"
of 3b.

**2,987 of 7,732 functions (38.6 %)**, 3,009 of 12,147 entry points. The last three
sessions added 93, 139 and 95: the set has **not** stopped growing.

By area (reached / all): start-up, items, creatures 154 / 380; netcode 28 / 69; engine
653 / 938; player 96 / 140; menus 90 / 207; effects and vehicles 168 / 311; sound, card,
save, dialogs 170 / 272; monsters 481 / 891; skills and spells 490 / 983; lobby and
network-session client 19 / 437; libraries 221 / 1,551; C and C++ runtime 417 / 1,553.
`coverage.py … --areas --list FILE` prints the table and the 4,745 functions never
reached.

The tours (`tour.py`): the class is chosen on the character-creation screen (the number
of presses per class was measured: the screen turns through twelve models); in the first
level the character is given level 25, large statistics and every active skill of its
class at rank 10 by memory writes; then, per level, the game's own level-change request,
seeded random walking, striking, blocking and casting, the two ability buttons moving on
to the next two skills every 96 ticks, and in one level per tour hit points written to
almost nothing (no character died of it: nothing hit it in time). The levels are in
`local/recomp-out/proof/sessions.json`: 93 between the seven tours, among them the two
boss levels, the medal and bonus levels, the arenas and the three cutscene levels.

**Not reached:** shops, the workshop, saving at a save point, a level-up by experience, a
death. Each needs the character walked to an object or a creature, as `pilot.py` does.

### 3b. What it took to compare a session with memory writes and many levels (Ran)

1. **A scripted memory write lands at a vertical blank, and the blank falls anywhere in a
   frame.** The script announces each group of writes (`echo @P n`), the rig prints the
   frame it ran them in, and the native run applies the same bytes at that row of the tick
   log (`--opt proof-pokes`) instead of running them from the script. A write that ends a
   level is applied after the level's last row, so both machines leave after the same
   tick (all 102 scripted level changes did). Any other write is applied one
   row later than the rig's log first shows it: the columns it touches then differ for
   that one row ("write rows": 1 for the character, 3 to 5 per level for the ability
   buttons and mana, up to 3 for hit points) and nothing after it. Applied a row earlier
   they agree in that row, but the simulation step of that tick sees the write here and
   not on the rig, and a hit-point write then leaves a constant offset for the rest of the
   session (seen, and the reason for the choice).
2. **The noise table.** `engine_init` 0x19d19c seeds the cosmetic generator from the CPU
   cycle counter (0x19d1e0) and `math_buildNoiseTable` 0x1646c8 fills `g_noiseTable` from
   it; `Torch_run` 0x2b2088 takes a torch's light radius and position from the table
   (`math_noise` 0x166b48) and stores them in the torch object (+0x68 to +0x84), which is
   in the pool. With different counter values the pool differs at every tick of every
   level that has a torch (three of the first tour's levels: 14 words in two objects in a
   memory image taken on both machines at the same tick; writer found with the
   write-watch). The rig's log shows the seed only after start-up has drawn from it, but
   each draw is a step of a linear generator, so the logged seed is a·counter + b
   mod 2³²: two short native runs with the counter forced to 0 and 1 give a and b, the
   rig's seed gives its counter (0x002a3038 in every run of these scripts), and the native
   run is given it (`--count-at 19d1e0=…`; `session.py` does all of it). After that those
   levels are identical in every pool byte at every tick.
3. **The first tick of a level gets stale controller bytes.** `rt/iop.cpp`'s replay
   hands the game, at a blank where the tick stands at T, the rig's next row of tick T
   if there is one and else the row of tick T+1. A level stands at tick 0 while it loads,
   for more frames on the rig than here, so the last blank before tick 1 gets one of the
   rig's loading rows and the game's first tick reads the wrong bytes (native tick 1 =
   the rig's tick 0; equal from tick 2). When a level starts with the stick at rest — all
   level changes the script makes — it cannot matter. When the game changes level itself
   in mid-play (seven times in `s3` and `s2`) or the script plays through a load (`h6`),
   the character moves differently in tick 1 and the runs part: position from tick 1,
   seeds some hundred ticks later. `cmp.py` (`first_tick_fix`) removes a level's loading
   rows after the first from the replay file, so every blank of the load gets the tick-1
   row; with that, all three sessions agree in position and seeds at every tick. The
   replay itself is not changed by this work.
4. **A write the rig made while a level was loading** (the script ran on through a level
   change the game made) is applied at the start of the load here: the load is shorter
   and the rig's frame of it never comes.
5. **Memory images at the same tick on both machines.** The rig dumps memory inside its
   tick hook when a script write arms it (`ontick 77 dump …`, `poke 0x4027ac:s32 77`);
   `session.py` makes the native run dump at the row of the same episode and tick
   (`--opt proof-dump`); `rigcompare.py memdiff --a … --b …` compares. This located every
   row of 3c.

### 3c. Every difference in the tours

| # | Where | What differs (Ran) | Writer (Ran) | Cause |
|---|---|---|---|---|
| 1 | every session, first level, tick 7 (two sessions: 7–8) | player record: the weapon-trail matrix | `fx_modelStatusEffects` | 1a: disc-read completion (**Ran**) |
| 2 | `s5` from its first tour level, `s3` from its fourth | one float of the record, +0x4a74, one unit apart (−3161 / −3160 in an image pair at tick 89; −2085 / −2086 in another) | read from the code: stored only by `hud_spellSelect` 0x1dd270 and the HUD function 0x1de8c4 (and copied by `player_importCharacter`) | **Inferred:** an animation value of the spell-selection display that moves per displayed frame, and the machines display different numbers of frames. No reader outside the HUD |
| 3 | `s3` from its fourth level | two pool words: the player object's +0x114 and another object's same field, pointers to different 0x620-byte entries of the table near 0x795000 | not traced here | the pose cache of `docs/issues/rescan.md` R1 and `native-recomp.md` finding 4: entries are handed out by drawing (**Read**, not re-measured) |
| 4 | `s6`, boss level, ticks 453–578 | two floats in one creature object, 0.9 apart (162.9 / 162.0, −238.1 / −239.0), each moving by 1 per tick on both machines | `anim_advance` 0x16d748 called from `Creature_stepAnim` at 0x1163a4 | animation track times that start 0.9 apart at tick 453. **Inferred:** `anim_advance` takes a sound position as its third argument (an animation that follows a voice), and the two sound drivers are at different positions. Not measured; whether such a track can move an event that matters to the simulation is not established |
| 5 | two of the seven level changes the game made itself (`s2` third level, `s3` third level) | the native run stays **one tick longer** in the old level (last tick 153 against 152, 189 against 188); in `s2`, where hit points were regenerating, they are one step (0.653) ahead from then on, record and pool with them; in `s3` rows 2 and 3 begin there | not traced | **not explained.** Positions, seeds and state agree at every tick both machines have. Not the load-time write (left out as an experiment: no change). **Inferred:** the change waits for something counted in fields or answered by the I/O processor, as in 1a; at the other five the two machines leave after the same tick |
| 6 | `s5`, last two levels and the return | pool checksum | not traced | **not located** (no image pair made); every other column agrees |

## 4. Arithmetic corner cases

The translated code does its arithmetic through `rt/fpu.h` (two models: `-DFPU_PS2`, the
interpreter's, used by the function-by-function proof; and the default 'host' model, used
by the runtime because it is what the emulator computes), `rt/mmi.h`, the multiply/divide
helpers of `rt/recomp.h`, and `rt/vu0.h`. `tools/recomp/proof/arith.py` tests them one
instruction at a time. Every instruction is compiled from the C++ text `recomp.py` itself
emits for that instruction word (`arith_gen.cpp`, generated), so the translator's choice
of helper and operand order is tested with the helper.

### 4a. FPU instructions (Ran)

All 24 FPU instruction forms the executable contains, 1,980,400 operand sets each
(47.5 million in all): the product of 480 edge patterns with itself (zeroes; denormals;
exponents 1, 2, 23–25, 126–129, 150–159, 253, 254; exponent 255 with ten mantissas, i.e.
every infinity and NaN shape; mantissas 0, 1, 2, all ones, alternating), then seven seeded
sets of 250,000: uniform bit patterns; exponents within 30 of each other; pairs that
cancel to within three units of the last place; products and quotients within three
exponents of overflow and of underflow; denormal operands; infinity and NaN patterns;
whole numbers and integers read as floats.

| Comparison | Operand sets | Different |
|---|---|---|
| **A.** `-DFPU_PS2` build against the interpreter (`ee_emu.py`, model `ps2`): result register, accumulator, compare bit | 24 × 1,980,400 | **0** |
| **B.** runtime build ('host' model) against `softf.py`, denormals kept (how the runtime's threads run today) | 24 × 1,980,400 | **0** |
| **B′.** runtime build with the CPU's flush-to-zero mode set, against `softf.py` with flush-to-zero (how the emulator runs the game) | 24 × 1,980,400 | **0** |

`softf.py` is a description of the host model written for this test in integer
arithmetic only: operands clamped to ±FLT_MAX, the IEEE operation rounded toward zero
(overflow gives ±FLT_MAX, never infinity), divide and reciprocal square root by a zero
exponent give ±FLT_MAX, multiply-add as two rounded operations, conversion saturating with
NaN → 0. That B and B′ are zero means the compiler flags hold (no fused multiply-add, the
rounding mode honoured, nothing folded at compile time) and the special cases in `fpu.h`
are what the header says.

Where the two models differ from each other is not an error, it is the difference
between the emulator's arithmetic and the interpreter's console model; counted over the
same sets (host model without flush-to-zero against the interpreter):

| Cause | Results that differ |
|---|---|
| an operand with exponent 255 — the host model clamps it to FLT_MAX first, the console model computes with it | 4,704,020 |
| a denormal operand — zero in the console model, a number for a host that keeps denormals | 2,744,765 |
| last bit — the console model's adder keeps six guard bits, IEEE truncation the exact sum | 2,649,202 |
| overflow — 0x7fffffff in the console model, FLT_MAX on the host | 1,644,001 |
| underflow — zero below the smallest normal number, a denormal on the host | 258,522 |
| other (compositions of the above in `rsqrt` and multiply-add) | 84,650 |

No instruction differs in any other way: `abs`, `neg`, `mov`, `c.f` and `cvt.s.w` agree
on every set; `cvt.w.s` differs only on NaN patterns (exponent 255 with a non-zero
mantissa: the console model saturates, the host gives 0).

### 4b. The host model against the emulator itself (Ran) — and one gap in the runtime

`rigarith.py` writes a small routine and 128 edge patterns into unused memory of a saved
rig state and makes `gfx_beginFrame` jump to it once: the emulator's own translation of
each instruction then computes all 128 × 128 pairs in the game's thread. The dump is
compared with `fpu.h`'s host model built as the runtime builds it.

| Instruction | pairs | differ, flush-to-zero set | differ, denormals kept |
|---|---|---|---|
| add.s | 16,384 | 0 | 1,510 |
| sub.s | 16,384 | 0 | 1,510 |
| mul.s | 16,384 | 0 | 1,892 |
| div.s | 16,384 | 0 | 1,508 |
| sqrt.s | 16,384 | 0 | 1,280 |
| rsqrt.s | 16,384 | 0 | 596 |
| max.s | 16,384 | 0 | 1,240 |
| min.s | 16,384 | 0 | 1,320 |
| abs.s, neg.s, cvt.w.s, cvt.s.w | 4 × 16,384 | 0 | 0 |
| c.eq.s | 16,384 | 0 | 130 |
| c.lt.s | 16,384 | 0 | 65 |
| c.le.s | 16,384 | 0 | 65 |

So on these inputs `fpu.h`'s host model **is** the emulator's arithmetic, bit for bit,
including the clamping of exponent-255 operands, overflow and division by zero — provided
the thread runs with flush-to-zero. It does not today:

**Finding (runtime, not translation).** The Play! emulator starts its machine thread
with `fesetround(FE_TOWARDZERO)` and `FpUtils::SetDenormalHandlingMode()` (`PS2VM.cpp`,
`CPS2VM::EmuThread`; on ARM64 that sets FPCR.FZ, on x86 the DAZ and FTZ bits) (**Read**).
`rt/runtime.cpp` (`thread_main`) calls only `fesetround`. With denormals kept, a denormal
operand is a number instead of zero and a result below the smallest normal number is a
denormal instead of zero: `add.s` 0 + 0x00000001 gives 0 on the rig and 0x00000001 here;
`c.eq.s` 0, 0x00000001 is true on the rig and false here; and because rounding is toward
zero, adding a negative denormal to a positive number lowers its last bit
(0xb40531e5 + 0x004e3b21 gives 0xb40531e4 here and 0xb40531e5 with flush-to-zero)
(**Ran**). In the 47.5 million directed sets flush-to-zero changes 118,000–282,000
results per arithmetic instruction and 33,000–67,000 per compare (column "fz changes" of
`local/recomp-out/proof/arith/fpu.txt`).

No compared session showed it — no compared value met a denormal — but a value that
decays toward zero does reach the denormal range, and from there the two machines would
compute different numbers, positions included. The fix was sent to the runtime's keeper
and **is in the merged runtime**: `thread_main` now sets the processor's mode on every
thread that runs the game's code (the run prints "arithmetic: toward zero, denormals are
zero"; `--opt arith=nearest` switches both off). All sessions and tables of this file
were repeated on the merged runtime; none changed.

### 4c. Integer, multiply/divide and multimedia instructions (Ran)

156 instruction words against the interpreter, 250,000 operand sets each (39 million):
the 33 multimedia operations of `rt/mmi.h` (the parallel shifts at six shift amounts),
`MULT`/`MULTU`/`DIV`/`DIVU` and their second-pair forms, `MADD`/`MADDU`, `PLZCW`, the
HI/LO moves, the 32- and 64-bit shifts at four amounts and by register, the conditional
moves, set-on-less-than and the logical and wrapping arithmetic instructions. Operands:
128-bit values whose lanes (8, 16, 32 or 64 bits) are edge values (0, 1, −1, the largest
and smallest signed, the saturation boundaries) or random; for multiply and divide also
zero divisors, the most negative number by −1, and register contents that are not
sign-extended 32-bit values. Compared: the 128-bit destination, HI, LO, HI1, LO1.

**0 different in 39,000,000.**

### 4d. Vector unit 0 (Ran)

The interpreter has no vector unit, so `rt/vu0.h` is tested against `softf.py`: every
upper-instruction form the header implements — add, subtract, multiply, multiply-add and
multiply-subtract with a register, a broadcast field or the I register, to a register or
to the accumulator; maximum and minimum; the four fixed-point conversions each way;
absolute value — 225 forms with three destination masks, one instruction per run of the
header's own microprogram loop, on finite operands (a sixth of them denormal or zero, a
tenth at the largest exponents, a fifth cancelling to within two units of the last
place).

| Mode | Lane results | Different |
|---|---|---|
| denormals kept | 21,000,000 | **0** |
| flush-to-zero set | 21,000,000 | **0** |

Not covered: infinity and NaN operands (they cannot arise from finite operands under
rounding toward zero; they would have to come in as data), the lower instructions (moves,
loads, stores, one branch), and the vector unit against the rig itself. The game's one
vector-unit program runs in every session of part 3 (`anim_buildPose`), where its results
feed the compared state.

## How to repeat

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/proof/build_proof.py translate     # recomp.py into gen-proof-src, hook into gen-proof
python3 tools/recomp/proof/build_proof.py runtime       # bin/rta_proof
python3 tools/recomp/proof/build_proof.py driver        # bin/proof_driver
python3 tools/recomp/proof/realproof.py want            # the 301 (+40) from sweep-stub.txt
python3 tools/recomp/proof/session.py s6 rig            # one tour in the rig ...
python3 tools/recomp/proof/session.py s6 native --capture
python3 tools/recomp/proof/summary.py s6                 # the comparison, one line per level
python3 tools/recomp/proof/realproof.py replay local/recomp-out/proof/real/s6
python3 tools/recomp/proof/realproof.py report local/recomp-out/proof/real/* --hits local/recomp-out/proof/cmp/s6/hits.tsv --list
python3 tools/recomp/proof/coverage.py --sessions s6,s5,s0 --areas
python3 tools/recomp/proof/arith.py build && python3 tools/recomp/proof/arith.py fpu && python3 tools/recomp/proof/arith.py int && python3 tools/recomp/proof/arith.py vu
python3 tools/recomp/proof/rigarith.py                  # needs local/rig-out/states/04-hub.zip
```

## What remains unproven

- **226 functions have no comparable case**: 24 cannot return in isolation (the bounded
  comparison described in part 2 would cover them and is not built); 202 ran in no
  session — 151 of them network, library and runtime code offline play does not call, 20
  of the 202 apparently dead, the rest reachable game code not reached.
- **46 functions are compared only up to an instruction both sides stop at**, most of
  them at their first vector-unit instruction: the interpreter has no vector unit. What
  stands for the vector unit is 4d (the header against a written reference) and the play
  comparison, in which `anim_buildPose` runs every frame.
- **4,745 functions ran in no compared session.** About 2,880 of them lie in the
  libraries, the C++ runtime and the lobby client; the others are monsters, skills,
  menus and the save path not visited: no shop, workshop, save point, level-up or death
  was reached, and the executed set was still growing.
- **Two differences in the tours are not explained** (3c rows 5 and 6: one tick more of
  the old level at two level changes the game made; a pool checksum) and two are
  explained by reading, not by measurement (rows 3 and 4). In all four every simulation
  column other than the one named agrees at every tick.
- **Tool limits found:** the controller replay's first tick of a level (3b.3: worked
  around in `cmp.py`, the replay in `rt/iop.cpp` is unchanged); a scripted memory write
  costs one row of difference in what it writes (3b.1).
- 1b: that the sound slots' time counters differ *because* the two sound drivers report
  voices ended at different times was not traced into the drivers; the slots and the
  handle order were measured.
- The arithmetic of the vector unit was not run inside the rig (only the FPU was), and
  infinity and NaN operands of the vector unit were not tested.

## Proposed ledger rows

| Id | Statement | Status | Where |
|---|---|---|---|
| NP1 | The one-tick difference of the player record at hub tick 7 is the identity matrix of the weapon-trail state, written by `fx_modelStatusEffects` one tick after `eqcache_lookupModel` first returns the weapon's model; the tick depends on when the disc read completes. Cosmetic state | Ran (bytes, writer, both machines' cache record, three timings) | 0x1f6ac8, 0x1bc964, 0x1a2d48, record +0x4a88 |
| NP2 | The 27-tick difference of the object pool in the fight is one word, the player object's handle-list head (+0x00), written by `sound_playOnObject` linking a sound-sequence slot's handle to the object: the same two sounds take the two slots the other way round on the two machines. The 32 slots differ between the machines at 854 of 3,978 ticks with the simulation identical | Ran (bytes, writer, slots on both machines) | 0x214230, 0x1a1698, 0x1a1738, `g_soundSeqs` |
| NP3 | `rt/fpu.h`'s host model equals the emulator's FPU arithmetic on 15 instructions × 16,384 edge pairs when the thread runs with flush-to-zero, and differs on 65–1,892 pairs per instruction without. The runtime did not set it; it does since the merge of 2026-10-12 | Ran | `rt/runtime.cpp` `thread_main`; `tools/recomp/proof/rigarith.py` |
| NP4 | `-DFPU_PS2` arithmetic equals the interpreter's on 24 FPU instructions × 1,980,400 directed operand sets; the host model equals its written reference with and without flush-to-zero on the same sets | Ran | `tools/recomp/proof/arith.py fpu` |
| NP5 | The translation of 156 integer, multiply/divide and multimedia instruction words equals the interpreter on 250,000 operand sets each | Ran | `tools/recomp/proof/arith.py int` |
| NP6 | `rt/vu0.h` equals IEEE single precision rounded toward zero on 225 upper-instruction forms, 21,000,000 lane results, with and without flush-to-zero | Ran | `tools/recomp/proof/arith.py vu` |
| NP7 | Of the 301 functions without a comparable synthetic case, 69 are identical to their return on states recorded in the running game (registers, calls, all of memory), 6 more up to a common stop; 24 wait and cannot return in isolation; 202 ran in no session; none differs. 7,460 of 7,732 functions now have a comparable case identical to the return | Ran (nine sessions, 2,310 runs) | `tools/recomp/proof/realproof.py` |
| NP8 | 1,968 of the 2,015 functions one tour enters are identical to their return when replayed from the state of their first real call; none differs | Ran | `realproof.py replay … --all` |
| NP9 | Nine sessions compared with the rig at every tick (79,547 ticks, 93 levels, seven classes) run 2,987 of the 7,732 functions. Position, both seeds, state and every character column agree at every tick of all nine; four tours (34,995 ticks) agree in every column | Ran | `tools/recomp/proof/session.py`, `summary.py`, `coverage.py` |
| NP10 | The object pool of a level with a torch differs between two machines at every tick unless they read the same cycle-counter value in `engine_init`: `Torch_run` stores light radius and position taken from the per-boot noise table in the torch object (+0x68–+0x84). With the counter made equal the pools are identical | Ran | 0x19d1e0, 0x1646c8, 0x166b48, 0x2b2088 |
| NP11 | The controller replay of `rt/iop.cpp` hands the game, at the first tick of a level, a row of the rig's loading frames; a level that starts with input held then diverges from the rig at tick 1. Removing the loading rows from the replay file removes the divergence in all three sessions that had it | Ran | `--opt pad-replay`; `tools/recomp/proof/cmp.py` `first_tick_fix` |
| NP12 | Record +0x4a74 is written only by `hud_spellSelect` and the HUD function 0x1de8c4 and differs between machines by one unit in two tours | Ran (bytes), Read (writers), cause Inferred | 0x1dd270, 0x1de8c4 |
| NP13 | In a boss level two animation track times of one creature start 0.9 apart on the two machines and stay so; written by `anim_advance` from `Creature_stepAnim` | Ran (bytes, writer), cause Inferred | 0x16d748, 0x1163a4 |
| NP14 | At two of seven level changes the game made itself the native run stays one tick longer in the old level than the rig (hit points regenerate one step more); unexplained | Ran | — |

## Working notes

- `RTA_DISC` must be set. Rig runs: `nice -n 19`, at most three at a time here. Under
  the afternoon's load a tour took 30 minutes in the rig and 3 natively; at a load of 17,
  7 minutes and 2.
- A rig state saved in mid-script (`save`) cannot continue the same run: the script's
  held buttons are not in the state. `cmp/pool/valor3800.state` was made that way and its
  resumed run is a different fight; the full run was repeated instead.
- `local/recomp-out/unproven.txt` (442 lines) is from an earlier sweep and is stale; the
  301 are derived from `sweep-stub.txt` by `realproof.py want`.
