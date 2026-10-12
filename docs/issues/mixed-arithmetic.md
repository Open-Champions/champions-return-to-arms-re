# Mixed arithmetic: a browser player and a Mac-application player in one game

Champions: Return to Arms, SLUS-20973 v2.00, on this project's playable build (Play!,
`tools/play-net`) and its browser build (the same emulator as WebAssembly,
`tools/play-web`). **Ran** = run on this Mac (rig: `tools/rig`, copies of one Play! build,
not a console; browser: Google Chrome 155). **Observed** = read in the source named.
**Inferred** = follows from those. Local scripts, logs and states are under `local/mixed/`
(not in the repository); `local/mixed/NOTES.md` is the working log.

## Summary

The game is deterministic lockstep (`docs/netcode.md`): every machine computes the whole
simulation and they compare a hash of the shared seed and the players' whole-number
positions. The application's machine rounds floating-point results toward zero, as the
console does; a WebAssembly machine can only round to nearest. With one of each in a game
the positions differ in the last bit on the first step and the game's own check ends the
session within two seconds (`docs/issues/browser-build.md`, `live-rig.md` 8.3; again here,
section 3.2).

| Question | Answer | Kind |
|---|---|---|
| How does the two builds' arithmetic differ for this game? | In the state of the host processor only: the rounding rule (toward zero against to nearest) and the treatment of tiny numbers (taken as zero against kept). The two translators are fed the same intermediate operations by the same front end and turn each into the same IEEE operation; neither fuses or reorders. Section 1 | Observed; Ran (60 operations, 2,000,000 operand sets each) |
| Can the application compute what a browser computes? | Yes: "browser arithmetic", a switch in the core, off by default (`FpUtils::SetArithmetic`). It puts the machine thread's control register in the state WebAssembly code runs in. Section 2 | Ran |
| Proof without a browser | One machine in each arithmetic: out of step on the first step (3 pairs of 3 with input). Both in browser arithmetic: in step over the boot pair and every fuzz pair; the existing pair scripts end as they do in native arithmetic (one exception, a timing race that did not happen). Section 3.2 | Ran |
| Proof against the real thing | The browser build in Chrome and the rig in browser arithmetic, the same recorded input by vertical blank from power-on: two sessions, 12,400 frames (walking, turning, fighting, 8 deaths, four level changes) and 8,810 frames (another level, both sticks), 224 bytes of game state read in every frame, **no byte differs**. The rig in native arithmetic with the same input differs from frame 2741. Section 3.3 | Ran |
| Does the game behave in that arithmetic? | Nothing broke in any run. Section 4 has what was measured | Ran |
| How is the arithmetic chosen in a real game? | Proposed and written (application and shared network code), compiled for both builds, one copy seen to change on request, **not yet tried between two copies**: every copy tells the others what it can do and does, on the path the patch-set figure already uses; the application changes to browser arithmetic in the room when a browser copy is heard, and warns when a copy cannot follow. Section 5 | Observed (code); the exchange between copies not Ran |
| Limits | An x86 browser was not available (a generated NaN has another sign there); an Intel build of the application is not covered; games in browser arithmetic are no longer bit-identical to a console. Section 6 | — |

## 1. How the two builds' arithmetic differs

**Observed** in `local/play-playable` (the application's tree) and `local/play-web-src`
(the browser's). The code generators (`deps/CodeGen/src`, `include`) and the EE and
vector-unit front ends (`Source/ee`, `Source/COP_FPU.cpp`) are the same files in both
trees; the only differing files in the two cores are counters for the browser's speed
figures, the browser's disc reader and video code, and now the switch itself (`FpUtils`
and two places in `PS2VM.cpp`). So both translators are handed the same sequence of intermediate
operations for the same game code, and the question is what each makes of one operation.

| What | Application (ARM64 translator) | Browser (WebAssembly translator) | After the switch |
|---|---|---|---|
| Add, subtract, multiply, divide, square root (EE FPU and both vector units) | `fadd fsub fmul fdiv fsqrt` (scalar and four-wide), rounded by the thread's control register: **toward zero** (`fesetround(FE_TOWARDZERO)` in `CPS2VM::EmuThread`) | `f32.add` … `f32.sqrt`, `f32x4.add` …: **to nearest**, always | same |
| Integer to float (`cvt.s.w`, the vector units' `itof`) | `scvtf`: rounded by the same register (matters above 2^24) | `f32.convert_i32_s`: to nearest | same |
| Tiny (denormal) numbers | flush-to-zero is set (`FpUtils::SetDenormalHandlingMode`): a tiny result becomes zero and a tiny operand is read as zero - in arithmetic and also in compares, minimum / maximum, the vector units' zero flag and clip test | kept, and computed with | same |
| Float to integer (`cvt.w.s`, `trunc.w.s`, `ftoi`) | `fcvtzs`: truncates, saturates, NaN gives 0 | `i32.trunc_sat_f32_s`, `i32x4.trunc_sat_f32x4_s`: the same | same in either state |
| Multiply-add (`madd.s`, the vector units' `MADD`, `MSUB`, `OPMSUB`) | a multiply, then an add: the intermediate language has no fused operation and the ARM64 assembler has no `fmadd` / `fmla` at all | `f32.mul`, then `f32.add`; an engine may not fuse them | same |
| Reciprocal, reciprocal root | 1.0 divided by the value, by its root: `fdiv`, `fsqrt`; no estimate instructions | `f32.div`, `f32.sqrt` | same |
| Reordering, constant folding | none: the optimiser of the intermediate language folds no floating-point constants | none | — |
| Compares (`c.eq.s`, `c.lt.s`, `c.le.s`) | `fcmp` and the conditions EQ, CC, LS: false with a NaN | `f32.eq`, `f32.lt`, `f32.le`: false with a NaN | same |
| "Greater than" with a NaN | true (`fcmp`, HI) | false (`f32.gt`) | **differs** - but no front end emits it: the FPU has the three compares above, the vector units compare bit patterns as integers |
| `max.s` / `min.s` | `fmax` / `fmin` | `f32.max` / `f32.min`: the same for numbers and for ±0 | same |
| The vector units' `MAX` / `MINI` | integer compare of the bit patterns, no float instruction | the same integer operations | same in either state |
| The console's clamping, as Play! does it: an infinite or NaN **operand** becomes the largest finite value of its sign | integer minimum, signed then unsigned (`smin`, `umin`) | `i32x4.min_s`, `i32x4.min_u` | same in either state |
| Divide by zero (`div.s`, `rsqrt.s`, the vector units' `DIV`, `RSQRT`) | integer test of the divisor's exponent (so a tiny divisor counts as zero), result the largest value with the right sign | the same integer code | same in either state |
| Square root of a negative number | absolute value first, then the root | the same | same |
| Results are not clamped | a result too large is the largest finite value (toward zero never reaches infinity) | infinity, clamped when next used as an operand | same |
| Rounding-mode instruction of the intermediate language | writes the control register (used for blocks listed in `GameConfig.xml`, and back to "toward zero" at their end) | nothing | **no block of this game is listed** (no entry for `SLUS_209.73`); with one, the switch would be undone until the next vertical blank |
| Other per-game arithmetic: exact add / subtract through an integer routine, vector-unit blocks without clamping, the `ADDi` variant for certain games | by block list | the same, except the `ADDi` variant, compiled out | none applies to this game |
| C++ of the emulator doing float arithmetic for game code | none (helper calls from translated code are memory access and one integer routine) | none | — |
| Bits of a NaN that an operation creates | sign clear (`7FC00000`) on ARM | whatever the host processor gives: sign clear on ARM, **sign set on x86** | same on an ARM host; see section 6 |

Which simulation code goes through which path (`docs/issues/float-divergence.md`): game
code uses single precision on the FPU only (about 26,000 add / subtract / multiply
instructions, 368 divides, 172 square roots, 128 reciprocal roots, 1,462 conversions to
integer, three kinds of compare, `max.s` / `min.s`); `double` is integer library code and
cannot differ; and one function, `anim_buildPose`, runs a VU0 microprogram (vector add,
subtract, multiply, multiply-accumulate, conversion to fixed point) whose result places
the spells a player casts. VU1 draws. All of these are in the table.

**Ran: the two translators against each other** (`tools/arith/jitdiff.cpp`, built once
for this Mac and once with Emscripten for node 26, each linked against the code generator
library of the build it stands for). Every floating-point operation of the intermediate
language, alone ("raw"), as the FPU front end emits it (operands clamped) and as the
vector-unit front end emits it, 65 in all, each over 2,000,000 operand sets (all pairs of
65 special values - zeroes, tiny numbers, the largest, infinities, NaNs with different
payloads - then random bits, ordinary magnitudes, values one place apart, small whole
numbers); four values per set for the vector operations.

| | Operations with the same checksum as WebAssembly |
|---|---|
| ARM64 translator, control register in the browser state | **60 of the 60** the front ends emit (among the results 21.9 million NaNs, bit for bit the same); of the 5 they do not emit, 4, the fifth being "greater than" |
| ARM64 translator, Play!'s own state | 12 of the 60: absolute value, negate, clamp, the conversions to integer, the vector units' maximum / minimum. The other 48 differ, the compares and the zero flag among them (tiny operands) |

So the intermediate operations are one-to-one, and what differs is the processor's state.

## 2. The switch: "browser arithmetic"

`local/play-playable/Source/FpUtils.h`, `FpUtils.cpp`, `PS2VM.cpp` (in
`tools/play-net/play-net.patch` once that is regenerated).

- `FpUtils::SetArithmetic(ARITHMETIC_NATIVE | ARITHMETIC_BROWSER)`, any thread, any time;
  the default is native and nothing changes for a copy that never calls it.
- The machine's thread puts its processor in line when it starts and at every vertical
  blank (`FpUtils::ApplyThreadArithmetic`): for browser arithmetic the control register
  with rounding to nearest, flush-to-zero off and the default-NaN and alternate-handling
  bits clear - the state a new thread has and the state WebAssembly code is run in; for
  native what Play! set before (toward zero, flush-to-zero on). On an Intel host the
  corresponding bits of MXCSR are written (not verified against a browser: section 6).
- `FpUtils::GetThreadArithmetic` reads back what the thread really has. A WebAssembly
  build answers "browser" and changes nothing.

That is the whole of it: section 1 found nothing else to change for this game. The rig
has the switch as `--arith browser|native` and the script command `arith`, and prints the
machine thread's control register (`00000000` in browser arithmetic, `01c00000` in
native).

## 3. Proof

### 3.1 The translators

Section 1: 60 of 60 operations, 2,000,000 operand sets each.

### 3.2 The rig, no browser

States: two pairs booted from power-on through the game's developer LAN start
(`examples/pair-start.rig`), one pair per arithmetic (`local/mixed/st-native`,
`st-browser`); each pair's two machines agree on all 659 ticks, and the two pairs differ
from tick 1 (the place the game puts the characters).

**One machine native, one in browser arithmetic** (4 pairs from the native states, 2,500
frames, random input):

| Level, input | First difference | The game's own out-of-sync flag |
|---|---|---|
| strife, movement | position, tick 698 (the first step) | tick 762 |
| drunare, movement and fighting | hit points (raw bits) tick 701, position tick 789 | tick 862 |
| drunare, movement, fighting, potions, use | hit points tick 701, position tick 788 | tick 808 |
| strife, no input | none in 2,649 ticks | never |

As in `live-rig.md` 8.3: out of step on the first step, the session over within two
seconds.

**Both machines in browser arithmetic.** Fuzz (`tools/rig/fuzz.py`, every fix section of
the patch file on both machines, 6,000 frames a pair, levels strife / drunare / hub in
turn, three input mixes, every second pair with a bus that delays, jitters and loses
datagrams): see "Rig totals" at the end of the document for the count reached. No shared
column of the tick logs (seed, level, both players' position, angle, state, hit points,
mana, gold, experience, bags, statistics, equipment, abilities, the game's own sync record
and out-of-sync flags) differs on any tick of any pair. Several pairs changed level by
themselves on the way (random input found the exits to `blood1` and `hub`).

**The existing pair scripts** (`tools/rig/examples/pair-*.rig`), each run once per
arithmetic with both machines the same, from the states and with the options its header
names. Several of them exist to show a known cause of desync of the game itself when run
without its fix (ledger rows K2, K3, U1, U2); for those the point is that browser
arithmetic gives the same verdict in the same tick.

| Script | Both native | Both in browser arithmetic |
|---|---|---|
| `pair-start` (power-on to a net game) | in step, 659 ticks | in step, 659 ticks |
| `pair-k1` | in step, 1,557 ticks | in step, 1,557 ticks |
| `pair-k2` | the known difference, bag and quick slot, tick 744 | the same, tick 744 |
| `pair-k3` | the known difference, stored damage, tick 863 | the same, tick 863 |
| `pair-u1` | the known difference, button maps, tick 1089 | the same, tick 1089 |
| `pair-u2` (mission menu) | the known difference, menu state, tick 934 | the same, tick 934 |
| `pair-u2-gate` (jump-gate menu) | the known difference, menu state, tick 1153 | in step, 1,121 ticks: the script times two presses by a walk, the walk ends three frames later in this arithmetic (frame 522 against 519), and the race it sets up did not happen (the menu opened on both machines and neither travelled) |
| `pair-arena` (into the arena and through its opening; bus with delay, jitter and loss) | in step, 6,105 ticks | in step, 5,903 ticks |

Not run: `pair-chars*`, `pair-d26`, `pair-e9` (they need helper scripts or break points
that were not set up here).

### 3.3 The real browser build

Two machines, the same input in the same vertical blanks, compared frame by frame.

- **Browser side**: the browser build in Google Chrome 155 (headless, a profile of its
  own), the page `tools/arith/web/arith.html`. The page gives the machine the whole
  session **before it starts**: one step per vertical blank from the first one on. (The
  earlier attempt of `browser-build.md` pressed buttons from JavaScript timers; the menus
  then took a different number of frames in every run, and the place and facing the game
  gives the character on arrival depend on that.) No patches, an empty memory card that
  is not kept, no sound, frame limiter off.
- **Native side**: the rig built against the application's core, `--arith browser`, a
  fresh data directory, `--replay-input` of the same stream, `--log` of the same places.
- **The session** was recorded once on the rig (`--record-input`): the script
  `tools/rig/examples/boot-to-hub.rig` from power-on through the card screens, the menus
  and character creation into the first level, then the rig's random input (`fuzz`), a
  level change written into memory in a given frame, more random input.

First with the browser build exactly as it was served (built 2026-10-12 00:13), through
the test entry points it already had (`rtaTap`, `rtaStick`, `rtaTrace`), one place per run:

| Read in every frame | Frames | Browser against rig, browser arithmetic | Browser against rig, native arithmetic |
|---|---|---|---|
| the shared seed and the cosmetic seed | 2,829 | identical | the shared seed differs from frame 2741 (the first level's first ticks) |
| the player's position and angle | 157 (from the frame the player exists) | identical | identical (standing still) |

The cosmetic seed is seeded by the game from the processor's cycle counter at start-up, so
its agreement in every frame says that the two machines are the same machine cycle for
cycle, not only that the simulation agrees.

Then the long session, with a private build of the browser front end that has three more
test entry points (`tools/arith/web-hooks.patch`: a step with buttons and both sticks, a
memory write in a given vertical blank, several places per frame), linked against copies
of the browser build's own libraries (the core's libraries are the very files the served
build was linked from):

| | |
|---|---|
| Length | 12,400 vertical blanks from power-on (about 3 minutes 27 seconds of the console's time) |
| Input | 1,682 changes of controller 1: the boot script's presses, then random left stick with the attack, skill, shoulder, potion and use buttons (the rig's `fuzz` groups move, fight, potion, use), the right stick left alone |
| Memory writes | the pending level set to `strife` in frame 3600; to `drunare` in frame 9400 (without visible effect in browser arithmetic: the character was dead at that moment and the level was reloaded as after its other deaths) |
| What happened | `intro` from frame 917, `hub` from 2457, walking and turning there; `strife` from 3601; the game's own level changes to `blood1` at 4083, back to `strife` at 6777, `blood1` again at 7297; monsters fought (67 experience), the character killed 8 times and the level reloaded each time |
| Read in every frame (224 bytes) | the three seeds; the simulation and draw frame counters; the level name; the player object's pointer; 44 bytes of the object from its position to its angle; its state; 144 bytes of the player record (experience, hit points, mana, gold) |
| **Browser against rig in browser arithmetic** | **no byte differs in any of the 12,400 frames** (object bytes and state compared in the 8,269 frames in which the player exists). The same against the rig's recording run and against a fresh replay |
| Browser against rig in native arithmetic, same input | the shared seed differs from frame 2741, the position from 2923, the state from 2934; the session then goes another way (`blood1` at 4391, no experience, 2 deaths, and `drunare` reached at 9435) |
| Time taken | browser 198 s (load average 53), rig 234 to 250 s per run |

The row before the last is the check that the comparison can tell the two arithmetics
apart. A second run of the same session in the browser gave the same 2,777,600 bytes as
the first.

A second session, another level and other input (`local/mixed/session2.rig`): 8,810
vertical blanks; random left **and right** stick, the attack, skill and shoulder buttons,
potions, use, the direction pad and the select button; the pending level set to `drunare`
in frame 3300 (entered in frame 3301, the player there from 3420; nothing was fought in
it). Browser against the rig in browser arithmetic: no byte differs in any of the 8,810
frames (the object's bytes compared in 6,019). Against the rig in native arithmetic: the
shared seed differs from frame 2741, the state from 2868, the position from 2869.

Together: 21,210 frames of game time in which a Chrome machine and a native machine in
browser arithmetic held the same seeds, counters, level, position, angle, state and
record bytes in every frame.

## 4. The game in browser arithmetic

The game was tuned on a machine that rounds toward zero. What was looked for and what was
found (all **Ran**):

- **Nothing stopped.** Every pair and every session in browser arithmetic ran to its end:
  no machine without progress, no time-out of a level load, no machine-level error. Level
  loads took the same number of frames in both arithmetics up to the point where the
  simulations part (the first level is entered in frame 2457 and the player exists in
  frame 2673 in both).
- **Standing still is still.** The character stands at the same bits in both arithmetics
  for the 157 frames after arrival (no drift, no jitter of the height): the place the
  game computes for it comes out the same.
- **Menus, creation, loading: the same course** in both arithmetics: the seeds, the frame
  counters, the level and the player's place are identical for the first 2,740 frames.
  What differs before that is last-bit only: the character's hit points and their maximum
  are `42033333` (32.8 to nearest) in browser arithmetic and `42033332` in native from the
  frame the record is filled in (2673).
- **Then the two arithmetics are two different games from the same input**, as two
  different seeds would be: the shared seed differs within the first ticks of the level
  (a random draw gated by a float compare comes out the other way), positions follow.
  Section 3.3's last rows are one such pair of sessions. This is last-bit drift amplified
  by the game's own randomness, not a malfunction: within one arithmetic everything is
  repeatable.
- Figures from the fuzz pairs and a control in native arithmetic with the same seeds are
  under "Behaviour figures" at the end of the document.

Not looked at: a long session by a person, cutscenes, the bosses' scripted fights (the
arena), anything in the picture. Timers in this game count frames; the float clocks that
exist (cast and swing times scaled by a slow effect, `float-divergence.md`) are compared
with frame counts after conversion to integer and were not singled out.

## 5. How the arithmetic is chosen in a real game

Every machine of a game must use the same arithmetic from its first lockstep tick. A
browser copy has no choice; the application has. Written and compiled for both builds.
**Ran**: one copy of the application built from these sources, started with `--rta-arith
browser`, changes at frame 30 and says so (`rta.log`: "arithmetic: the machine now
computes as a browser copy's does"; `peers`: `arith=browser`). **Not yet tried between two
copies** (that needs two copies in a room on the local lobby server), so the message and
the choice below are as read in the code, not as seen working.

**The message** (`tools/play-net/src/RtaNet.cpp`, shared by the application and the
browser build, which compiles the same file). The copies already tell each other their
patch-set figure, player to player, as a keep-alive of the game's own UDP library with a
mark and the figure after it (`tools/play-net/README.md`, "Which patch set the other
players have"). The arithmetic goes the same way, as a second datagram at the same times
(four times in nine seconds from the first datagram heard, and from the start again
whenever it changes): bytes 0, 6, the mark `RTAari1`, one byte "can do" (bit 0 Play!'s
own, bit 1 the browser's) and one byte "does now" (0 Play!'s own, 1 the browser's), 11
bytes. A copy that does not know the mark hands a keep-alive to its game, which does
nothing with it; the patch-set datagram is unchanged, so old and new copies still compare
patch sets. A browser copy declares "browser only, does browser" by being compiled for a
browser - its front end needs no change to say it.

**The choice** (`CheckArithmetic` in `tools/play-net/src/Rta.cpp`, on the machine's thread
with the patch-set check):

- While the game is in its front end (the lobby and the room are there): if a player
  heard in the last 15 s cannot do Play!'s own arithmetic, or already does the browser's,
  the application changes to browser arithmetic; when nobody heard needs it, back. The
  second condition carries the choice to copies that do not hear the browser player
  themselves.
- Once a level runs nothing is changed: all machines would have to change in the same
  lockstep tick, which is not built. A browser player who appears in a running native game
  gets the warning instead.
- `--rta-arith browser|native|auto` fixes it (a copy fixed to one says that it cannot do
  the other); `auto` is the default.

**The warning.** The status bar and `rta.log` say "browser arithmetic" while it is on;
"another player's copy is on different arithmetic … wait for this to go away before
starting" while a copy has not followed yet (it should within a second); and "WARNING:
another player's copy cannot compute with browser arithmetic as this game does (an older
copy, with a browser player in the game) … do not start it" when a copy that says nothing
about arithmetic - any application copy from before this change - is in a room with a
browser player. `peers` on the control socket shows each player's arithmetic.

**What the browser build still needs** (not done here; its sources are another piece of
work): show the same warning on its page from the fields `arithKnown`, `arithCan`,
`arithNow` that `CNet::Peers()` now returns - a browser copy must tell its player when the
other copy is an application too old to follow; and lift "browser players play with
browser players" from its texts once a mixed game has been played. The lobby could keep
old application copies out of games hosted in a browser, which nothing does today.

**Known gaps in the proposal**: a browser player who enters the room in the second before
the host starts the game may not have been heard yet (the first datagram goes out 0.3 s
after the first one heard): the warning then appears in the game instead of before it.
Two application copies stay in browser arithmetic after the browser player has left their
room until they stop hearing each other (each sees the other doing it); that is
consistent, and harmless.

## 6. Limits

- **An x86 browser was not tested, and one case can differ there.** WebAssembly fixes
  every result except the bits of a NaN. Where Play! lets one arise (the reciprocal root
  of a negative number on the FPU, which unlike the console is not taken of the
  magnitude; infinity times zero or infinity minus infinity in a vector-unit instruction
  whose second operand is not clamped), an ARM processor creates it with the sign clear
  and an x86 processor with the sign set, and the clamp that follows turns the first into
  the largest positive value and the second into the largest negative one. On this Mac
  the application and Chrome agree on 21.9 million NaN results (section 1). The game's
  128 reciprocal roots take a sum of squares in 117 cases (`float-divergence.md`), so the
  case may never occur in play - that is **Inferred**, and the same exposure already
  exists between two browser players on different processors.
- **Only the ARM64 application.** The switch writes the equivalent bits on an Intel host,
  but Play!'s x86 translator was not compared with the WebAssembly one (its conversions to
  integer and its minimum / maximum are different instructions). The application is built
  for ARM64 only.
- **Not a console's arithmetic.** A game in browser arithmetic rounds differently from a
  PlayStation 2 and from PCSX2. That matters only if such machines were ever to join.
- **Mid-game switching** is not built (section 5).
- **The choice in the room was not exercised** between two copies (section 5).
- **Per-game rounding lists.** If `GameConfig.xml` ever gets an entry for this game that
  sets a rounding mode for a block, the ARM64 translator would write the control register
  inside that block and leave "toward zero" behind until the next vertical blank; the
  WebAssembly translator ignores such entries. There is none today.
- **Coverage of the browser comparison**: one player, offline, two sessions (12,400 and
  8,810 frames) plus the 2,829-frame one with the served build; one browser (Chrome 155
  on this Mac); two machines linked through the browser's relay were
  not compared (the network path does not touch arithmetic, but it was not run).

## 7. Files

| File | What |
|---|---|
| `local/play-playable/Source/FpUtils.h`, `FpUtils.cpp`, `PS2VM.cpp` | the switch (to go into `tools/play-net/play-net.patch`) |
| `tools/play-net/src/RtaNet.h`, `RtaNet.cpp`, `Rta.cpp` | the arithmetic message, the choice, the warning |
| `tools/rig/rig.cpp`, `README.md` | `--arith`, script command `arith`, `--record-input`, `--replay-input` |
| `tools/arith/` | `jitdiff.cpp` and `build.sh` (the translators against each other), `session.py`, `browser-run.py`, `web/arith.html`, `web/arith.js` (a session on both machines), `web-hooks.patch` (test entry points for the browser front end), `README.md` |
| `local/mixed/` | `NOTES.md`; `jit/` (the two programs and their result lists); `st-native`, `st-browser` (pair states); `p2-mixed` (one machine each); `fz-bb`, `fz-bb2` (fuzz, both in browser arithmetic); `fz-nn` (control, native); `ps/` (pair scripts); `off1*`, `web/`, `web-out/` (the 2,829-frame comparison with the served browser build); `s1*`, `session1.rig`, `session-watch.txt`, `webhook/` (the long session and the private front-end build) |

## Rig totals

Both machines in browser arithmetic, tick logs compared column by column:

| Run | Pairs | Lockstep ticks compared | Pairs with a difference in a shared column |
|---|---|---|---|
| Boot pair (`pair-start.rig`) | 1 | 659 | 0 |
| Fuzz, first batch (seeds 1000–1008, 1010) | 10 | 57,454 | 0 |

The fuzz was asked to reach hundreds of thousands of ticks and did not: the Mac was shared
and at a load average of 150 to 420 while it ran (a pair of 6,000 frames took 11 minutes
or more), and from the middle of the work this job was held to four runners.

## Behaviour figures

To be read with section 4. Seven fuzz pairs with the same seed, level, input mix and bus
in each arithmetic (6,000 frames of random input on both controllers after the warp to
the level; the developer start's two level-1 characters; every fix section on). "State 4"
is the state the offline session's character was in whenever its hit points were 0.

| Seed, level | Arithmetic | Lockstep ticks | Levels passed | Experience, players 1 and 2 | Times each player entered state 4 |
|---|---|---|---|---|---|
| 1000 strife | browser | 5,140 | strife, blood1, strife | 37, 55 | 2 |
| | native | 4,873 | strife, blood1, strife, blood1 | 37, 55 | 2 |
| 1001 drunare | browser | 5,790 | drunare | 0, 0 | 2 |
| | native | 5,878 | drunare | 0, 0 | 1 |
| 1002 hub | browser | 6,201 | hub | 0, 0 | 0 |
| | native | 6,198 | hub | 0, 0 | 0 |
| 1006 strife | browser | 5,177 | strife, blood1, hub, blood1 | 55, 37 | 2 |
| | native | 4,992 | strife, blood1, strife, blood1, hub | 0, 0 | 1 |
| 1007 drunare | browser | 5,982 | drunare | 0, 0 | 1 |
| | native | 5,990 | drunare | 0, 0 | 1 |
| 1008 hub | browser | 6,217 | hub | 0, 0 | 0 |
| | native | 5,900 | hub, blood1 | 0, 0 | 0 |
| 1010 drunare | browser | 6,043 | drunare | 0, 0 | 1 |
| | native | 6,046 | drunare | 0, 0 | 1 |
| **Sum** | browser | 40,550 | 5 level changes by the game itself | 184 | 8 |
| | native | 39,877 | 8 | 92 | 6 |

Every pair, in either arithmetic, stayed in step to its end. The same kinds of things
happen at about the same rate in both; the differences are those between two different
sessions (four awards of experience against two, five exits found against eight), and seven pairs are
too few to say that one arithmetic makes the game harder or easier. The `pair-arena`
script (section 3.2) reached the arena in both and ran 6,105 ticks in native and 5,903 in
browser arithmetic.

Speed: the same 2,829-frame replay in each arithmetic, started together, took 42.65 s
(native) and 42.74 s (browser arithmetic) of the machine thread's processor time, 66.3
and 66.2 frames per processor-second (load average about 200 at the time). Keeping tiny
numbers instead of flushing them costs nothing measurable on this processor.
