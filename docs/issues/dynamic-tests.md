# Dynamic tests: running the game's own code, one function at a time

Everything in `FINDINGS.md` and the area documents was read from the executable; none of it
had been executed, because the only full emulator available needs a console BIOS this
project does not have. This document describes a small interpreter that runs single
functions of `SLUS_209.73`, and what happened when specific claims and every test patch
were run through it.

**Evidence label used here: "executed in isolation".** It means: the game's own
instructions were executed on a state the test built, with other calls stubbed. It is
stronger than *Observed* for the question "what does this code do with these inputs" and
says nothing about "do these inputs occur in a real game". Nothing here was seen on a
console or in a console emulator. No patch below has been tested on a running game.

- `tools/ee_emu.py` — the interpreter (standard-library Python, no game data).
- `tools/test_ee_emu.py` — 65 unit tests on hand-assembled instruction words; run by CI
  without any game file.
- `tools/ee_tests.py` — the checks below; needs your own `SLUS_209.73`, otherwise prints
  `SKIP` and exits 0. `python3 tools/ee_tests.py -v` prints the tables; `-k codec` runs one
  group. At the time of writing: **208 checks, 208 PASS** (the count follows the patch
  file: one `p` check per section). The first pass ended at 128; sections 2.10–2.15 are the
  80 added since (65 in six new groups, 15 for new patch sections).

The patch file and the ledger changed several times while this was being written: the
alive-list patch at 0x1b3504 and the two pacing patches were withdrawn, rows G14–G24,
D24–D32 and L8–L12 arrived, L4–L6 were reworded, and the patch file went from five
sections to twelve. The script therefore finds patch sections by the address they patch,
runs whatever is there, reads proposal tables out of `docs/issues/prediction-copy.md` and
`docs/issues/lag.md`, and keeps the withdrawn patches as explicit words so their result
stays on record. Row wordings quoted below are those of `FINDINGS.md` as it stood at the
last run (2026-10-10).

A second pass covered what arrived after that: fifteen more patch sections (0x1375dc,
0x28da74, 0x217448, 0x1a5c0c, 0x1b9fcc + 0x1ba3ac, 0x1d2d30, 0x13b21c, 0x199df8, 0x217f58,
0x1dd1f0, 0x1b53d4, 0x1a5ba8, 0x1e6a60, 0x231a64, 0x27def8 — the last five were added
while this pass was running) and the ledger rows B1–B3, B8–B11, K1–K3, K5–K8, MV2, MV5,
MV6, F3, F4 and F7, which had been written from reading only. **All 27 sections in the
patch file at the last run are executed; none was left out**, and
each of those rows is reproduced, sharpened, or listed in section 5 with the reason it
could not be run. No ledger row and no patch description was contradicted; four statements
were sharpened (section 3, items 10–13).

**Two machines.** The interpreter has one machine. Where a row or a patch is about a
difference between machines, the check builds the same state twice, changes the one word
that is per-machine state (a selector word, a menu flag, a card-screen state, a latch),
runs the same code on both and compares every call and every store outside the stack
(call arguments too, where both runs take the same path). "The patch removes the difference" means the two patched runs no longer
differ in what the row names; "nothing else changed" means the patched run was compared
call for call and store for store with the shipped run and differs only in the one thing
the patch text names (in most cases it simply equals the shipped run with the per-machine
word clear). Large functions were entered part-way with registers and frame prepared, as
the pacing checks do; each row says where.

## 1. What the interpreter is, and is not

**It is** an instruction interpreter for the subset of the MIPS R5900 these functions use:
MIPS III integer instructions with 64-bit registers and 32-bit little-endian addresses,
delay slots, "likely" branches, HI/LO, unaligned load/store pairs, the R5900 three-operand
multiply, conditional moves, the second HI/LO pair, 128-bit load/store, 62 of the
multimedia (MMI) instructions, and the single-precision FPU. It loads the segments of the
ELF into a sparse memory, gives the code a stack, and lets a test

- call a function by address with arguments, or run from one address to another with
  registers prepared;
- replace any callee by a Python function, stub every callee wholesale, or let chosen ones
  run for real;
- overwrite instruction words first (a patch), by word or from a `.pnach` section;
- read back every call made (site, target, arguments) and every store outside the stack.

**It is not a console.** There is no timing, no interrupt, no kernel, no IOP, no vector
units, no graphics or sound hardware and no second machine. Consequences:

- A function that reaches a system call, a COP2 instruction or anything else that is not
  implemented stops with an error naming the address and the word. Nothing is guessed.
  The same goes for a load or store to memory nobody set up, an unaligned access, a
  trapping overflow, a `break`, and an integer division by zero (no trap on this CPU, but
  no defined result either). None of the runs below hit any of these.
- Callees are stubs unless a check says otherwise. A stub returns what the test tells it
  to. A check that says "calls X" saw the call; it did not see what X does.
- The state is the test's, not the game's. A fake player object has the dozen fields the
  function reads and zeroes elsewhere. A result of the form "with these inputs the code
  does this" is solid; "so this happens in play" is not shown by any check here.
- Where a check strings several real functions together (clone, then process damage, then
  rebuild the list) the glue between them — what the prediction loop does around the
  call — is the test's reading of the ledger (G3), not executed code.

**Floating point is the one place the interpreter approximates.** The console FPU is not
IEEE: no NaN, infinity or denormal, results clamped and rounded toward zero. Those rules
are implemented exactly. The last bit of a sum or product is not certain, because the
hardware keeps fewer bits than an exact computation; no console was available to compare
with, and the two descriptions of the hardware adder that I know of were written down from
memory. The interpreter therefore has four selectable adder models (two console-style, one
plain truncated sum, one round-to-nearest), a worst-case switch for the multiplier and a
switch for the rounding of divide and square root. The stick codec and `pad_apply` were
run under all of them (a10–a12, b12), and where the answer moves the table says so. The
other float code run here (the cutscene audio comparison, the truncation in the sync
hash) has margins thousands of times larger than the bit in question.

**How the interpreter itself was checked**

| Check | What it shows |
|---|---|
| 65 unit tests (`tools/test_ee_emu.py`) | each instruction class against values worked out by hand: sign extension, 64-bit compares, shifts, multiply/divide, delay slots, likely branches, unaligned pairs, 128-bit moves, FPU clamping and truncation, MMI lanes, stubs, hooks, patches, the error cases |
| x1–x5 in `ee_tests.py` | the executable's own `strlen`, `strcmp`, `memcpy`, `memset`, `memchr`, `memcmp` (433 alignment and length combinations), `rand` (64-bit multiply), `atoi`, `sprintf` (4,905 instructions for one call), `qsort` with a callback, and the engine's 16-bit `atan2` all return the independently known answer |
| a2, b10 | two independent re-implementations by other contributors (the sequences in `docs/netcode.md`, the stick table in `docs/issues/lag.md`) and the executed code agree to every printed digit |

## 2. Results

Result column: what the executed code did. Ledger column: the row or document statement it
bears on — **supports**, **sharpens** (true, but something is missing or off by one) or
**contradicts**. Ids are the check ids printed by `ee_tests.py`.

### 2.1 Input codec — `netcodec_encodeAxis` 0x13c450, `netcodec_decodeAxis` 0x13c970

Both functions were called directly, one channel each, frame by frame and as multi-frame
packets. Neither calls anything; they read only the four small tables at 0x402860–0x40289b.

| Id | Claim | How tested | Result | Ledger |
|---|---|---|---|---|
| a1 | From the reset state a centred stick decodes as 77, 43, 34, 44, 78, 101 … | 40 frames of 128 from reset state | 77, 43, 34, 44, 78, 101, 112, 118, 121, 122, 123, 123, 123, 125, 126, 127 …; within 4 of centre from frame 14, steady at 127 from frame 16 | supports `netcode.md` ("about 13 frames") |
| a2 | A full push reads 129, 134, 143, 162, 201, 227, 239, 245 | 40 frames of 128, then 255 | exactly that sequence, then 248, 250, 251 | supports `netcode.md`, L6 |
| a3, a4 | — | hold 255, hold 0 | 255 settles at **251** (predictor 252: the last 3 counts are below the smallest step); 0 settles at 0 | new; same as `lag.md` section 8 ("never passes 0.94") |
| a5 | decode(encode(x)) keeps both ends in step | 600 frames of mixed input (holds, sweeps, jitter, noise) | decoder step index and predictor equal the encoder's after every frame; decoder consumes exactly the bits written | supports `netcode.md` |
| a6 | Predictor rule: steps 4, 6, 8, 12, 16, 24, 32, 48, 64; index +2 after a move, −1 otherwise | a Python statement of the documented rule run beside the game code for the same 600 frames; all nine indexes visited | identical on every frame | supports `netcode.md` |
| a7, a8 | Decoder smoothing: ten spring steps, result truncated | the documented formula in both possible orders, in the interpreter's FPU arithmetic, beside the game code | matches on 600 of 600 frames only when each step **adds the velocity to the value first and then updates the velocity**; in the order printed in `netcode.md`, 187 of 600 bytes are wrong. Gain 0.049999997 (raw 0x3d4ccccc); damping 1 − √0.2 computed at run time = 0.55278641 (raw 0x3f0d8369) | **contradicts** the formula in `netcode.md` (its numbers are right); agrees with `lag.md` C6 |
| a9 | A packet repeats unacknowledged frames; the decoder skips frames already held | 27 packets of 1–90 frames, decoded with 0–39 leading frames skipped, against frame-by-frame coding; includes runs longer than 31 | same bytes, same state, same bit count | supports `netcode.md` (receiver step 3) |
| a10 | — | a1–a3 under all four adder models | identical | limit check |
| a11 | The decoded byte depends on float arithmetic (`netcode.md` per-machine row 11) | the same 600 frames with sums truncated vs rounded to nearest | 30 of 600 bytes differ, always by 1 | supports row 11, now with a number |
| a12 | — | console-style adders vs plain truncated sum; multiplier bias; square-root rounding | the two console-style adders agree on all 600 frames; both differ from the plain truncated sum on 30 frames, always by 1; multiplier bias and square-root rounding change nothing | **limit**: see 3.9 |

### 2.2 `pad_apply` 0x174410 and the slew limit (G5, L6)

Called directly on a 0x58-byte pad, a record and an 8-byte previous-state block; its one
callee (`pad_decodeStick` 0x174ce0) ran for real.

| Id | Claim | How tested | Result | Ledger |
|---|---|---|---|---|
| b1 | G5: every pad field is rewritten from the record | pad pre-filled with a marker, one call, list of stores | every byte of +0x08…+0x57 is stored **except +0x24…+0x27**; +0x00…+0x07 are not touched | sharpens G5 |
| b2 | G5: two globals could differ between machines | read and write log of one call | as shipped it stores nothing outside the pad and the previous-state block and reads exactly two globals, 0x41bfc0 and 0x41c138 (both 0 in the file) | supports G5 |
| b3 | G5: no stale pad state | two pads with different old contents, the same 60 random records | byte-identical in the stored range after every call | supports G5 |
| b4 | Record bytes +0xa/+0xb reach pad +0x38/+0x50 | one call | they do, as byte/255 | supports `netcode.md` per-machine row 1 |
| b5 | G5: "never written anywhere in the program" | 0x41bfc0 forced to 2 | `pad_apply` itself decrements it (store at 0x174464) and drops button 0x800 | sharpens G5: the function is its own writer once the value is non-zero; it never becomes non-zero by itself. The other global, 0x41c138, has a writer too, outside this function: `pad_updateRumble` subtracts one on every tick and stores the result clamped at 0 (store at 0x174790, read from the code, not run; `docs/issues/claims-audit.md` row 12). Neither is ever set to a non-zero value |
| b6 | — | 0x41c138 forced to 1 | sticks and analog fields zeroed, buttons masked with 0x41bfb8 \| 0x41bfbc | supports G5 (the global does gate the output) |
| b7 | 0.8 threshold for digital directions | sweep of one axis | movement is 0 below byte 169; digital flag at 239 and above, and at 17 and below | supports `netcode.md` |
| b8 | L6: 4 dead frames, 0.8 on the 7th | a2's sequence fed through the real `pad_apply` | no movement on frames 1–4; 0.368, 0.667 on frames 5, 6; digital direction from frame 7 (0.805) | supports L6; its "model numbers" are now executed |
| b9 | L6: at most 0.94 | settled value for a held 255 and a held 0 | **+0.943** through the codec against +0.989 for the raw byte offline; **−1.000** toward 0 | supports L6 for one direction; new: the other direction does reach full, so in a net game the stick range is not symmetric. Whether speed scales with it is Unknown |
| b10 | `lag.md` section 8 stick table (a model); L6: nothing for a flick under 4 frames | the five rows executed: full push, release, reversal, 3-frame push, 5-frame push | identical to the printed table to two decimals; a 3-frame push never moves the character (a 4-frame push gives 0.07 for one frame), a release keeps it moving 5 frames | supports `lag.md` section 8, L6 |
| b11 | `lag.md`: 20 spring passes at 0x13cd34 would bring "every row forward by exactly one frame" (not a proposed patch) | word 0x24060013 applied | first movement on frame 4, digital on frame 6 — one frame earlier each — but the values are 0.09, 0.70, 0.89, not the shipped row shifted | sharpens that remark |
| b12 | — | 86 stick positions under every FPU model and both divide roundings | identical | b7–b11 do not depend on the FPU approximation |

### 2.3 Object pool — `pool_new` 0x14fdb8, `pool_free` 0x150470 (D21)

`pool_init` 0x14fcd8, `pool_new`, `pool_free`, `pool_countFree` 0x150410 and the library
`memset` all ran for real; only the heap-print routine 0x150290 was stubbed.

| Id | Claim | Result | Ledger |
|---|---|---|---|
| c1 | 512 + 512 + 32 blocks | `pool_countFree` returns 1056 after `pool_init` | supports D21, `objects.md` |
| c2 | Blocks are zero-filled | a freed block is handed out next and is zero over its whole class size | supports "ruled out: uninitialised object memory" |
| c3, c4 | A full class spills into the next larger one | requests 1–512 of 0x148 bytes come from the 0x180 class, the 513th from the 0x500 class | supports D21 |
| c5 | `pool_free` finds the class from the address | a spilled block goes back to the 0x500 list | supports `objects.md` |
| c6, c7 | Returns nothing when all are full | after 1056 blocks `pool_new` calls the print routine once and returns 0 | supports D21 |
| c8 | — | 3001 bytes returns 0 even with a free block; 3000 is served | supports `objects.md` |
| c9 | — | outside the pool and its class table the allocator stores to one global, 0x4d8a24 | new detail |
| j3 | Reaper below 300 free blocks, sampled every 64th frame | stretch 0x14b9ac onward on the real pool: entered at 299 free, not at 300; on other frames the stored count is used however stale | supports D21, `objects.md` O1 |

### 2.4 Pacing — the hold decision of `net_main`, 0x13354c–0x133608 (L3, L4)

The block was run as a stretch from 0x13354c to its two exits, with `$v0`, `$v1`, `$s1`
and the frame prepared as the preceding code leaves them; its three counters live in the
game's own globals and carry over between calls. The stretch that folds a call's ready
count into the window minimum (0x13437c–0x1343a4) was executed too.

| Id | Claim | Result | Ledger |
|---|---|---|---|
| d1 | Constants 39, 31, 61, 3 | present at 0x133554, 0x133574, 0x1335c0, 0x1335e4 | supports `netcode.md` |
| d2 | Cap: hold when 39 or more ahead | held from a difference of 39 | supports `netcode.md`, L4 |
| d3 | Equalise: 5 or more above the smallest lead for 31 calls in a row | calls 31, 62, 93 … held; 4 above never; one call below 5 restarts the count | supports `netcode.md`, L4 |
| d4 | Trim: every 62nd call if the window minimum was above 2 | calls 62, 124, 186 held with 3 ready; never with 2; one call with 2 ready cancels that window only | supports `netcode.md`, `lag.md` C4 |
| d5 | Caller argument; "never" rule | a non-zero second argument holds every call; below input frame 3 nothing is held | supports `netcode.md` |
| d6 | L10: the pacing counters are private to `net_main` | the block stores only 0x4027dc, 0x4027e0, 0x4027e4 and the hold flag | supports L10 |
| d7 | L4: a stall is never caught up; L11: about 30 s after an outage | block executed inside a small modelled call loop (a held call samples nothing; one tick per call when a frame is ready): lead peaks at 39, then 2,236 calls (37 s at 60 calls/s) to drain to 2 when all machines are equally delayed | supports L4; same order as L11 (which models both ends and gets a peak of 35). The loop around the block is a model |
| d8 | L11: about 15 s after a one-sided event | same loop, others steady at lead 2: 872 calls (15 s) from 39 to 2 — equalise and trim both fire, two to three frames per 62 calls | supports L4, L11 |
| d9 | L3: cycle 2, 4, 6 | stretch 0x133760–0x1337ec: 6, 2, 4, 6 for 0–3 remote peers; 9, 3, 6, 9 with the modem flag; dropped and being-kicked peers not counted | supports L3 |
| d10 | L3: one packet every second call | turn test 0x133834 and phase step 0x1341e0 over 12 calls: one packet in every second call for 1, 2 or 3 peers; each of 3 peers every 6th call | supports L3 |

Pacing patches (each: the three rules re-measured with the patch applied, compared with
what the new constant implies):

| Id | Patch | Result |
|---|---|---|
| dp1 | file: "equalise at once (LAG-1)", 0x133574 | held on **every** call while 5 or more above the smallest lead; cap and trim unchanged |
| dp2 | file: "trim leaves one spare frame (LAG-2)", 0x1335e4 | trim needs 4 ready frames in every call of the window; never with 3; cap and equalise unchanged. In the modelled loop the lead settles at 3 instead of 2 |
| ds1 | file: "4-player send cycle 6 → 4 (LAG-3)", data 0x4027f4 | cycle 4 with 3 remote peers; each served every 4th call; the 4th call of each cycle carries no packet |
| ds2 | file: "3-player send cycle 4 → 3 (LAG-4)", data 0x4027f0 | cycle 3 with 2 remote peers; each served every 3rd call; the 3rd call carries no packet |
| dq1 | `lag.md` proposal LAG-1b, 0x133574 | held every 4th call while 5 or more above |
| dq2 | `lag.md` proposal LAG-5, 0x133554 | held from a difference of 29 (more than 28) |
| dw1 | withdrawn: "input delay drains faster" | equalise every 8th call, trim window 12 calls, cap unchanged — what its text said |
| dw2 | withdrawn: "lower input delay cap" | held from a difference of 15 (more than 14); the other two rules unchanged |

Modelled loop, 120-call stall then input flowing (calls until the lead stops falling):

| Constants | Peak lead | All machines equally delayed | Others steady at lead 2 |
|---|---|---|---|
| shipped | 39 | 2,236 calls, to 2 | 872 calls, to 2 |
| LAG-1 | 39 | 2,236, to 2 | 252, to 2 |
| LAG-2 | 39 | 2,174, to 3 | 810, to 3 |
| LAG-1b | 39 | 2,236, to 2 | 314, to 2 |
| LAG-5 | 29 | 1,616, to 2 | 686, to 2 |
| withdrawn drain patch | 39 | 444, to 2 | 204, to 2 |
| withdrawn cap patch | 15 | 748, to 2 | 376, to 2 |

These numbers are from one machine with idealised peers; `docs/issues/lag.md` models both
ends and the network and should be preferred for anything beyond "the rule fires when the
document says it does".

### 2.5 Alive list, death path, clone (G3, G11–G14, G18, G21, G24)

`game_rebuildAlivePlayers` 0x1e72f8 and `net_isLocalSlot` 0x13e150 ran for real on a
constructed player table. `Player_processDamage` 0x1b2cc0 ran on a fake player with 100 hit
points and 500 pending damage; its seven calls were stubbed except where stated.
`Player_clone` 0x11e870 ran with `pool_new` handing out a zeroed block and
`handle_initEmpty` running for real.

| Id | Claim | Result | Ledger |
|---|---|---|---|
| g1–g3 | The list is the slots whose object exists and is not dead | slots {alive, dead, none, alive}, slot 3 local → list [0, 3], local list [3], first local 3, previous local count saved; only the first `g_numPlayers` slots scanned; with no peers every slot is local; stores confined to 0x4f841c–0x4f844f | supports G11, `copyfix.tsv` |
| e1, e2 | A player's death rebuilds the list on the spot | death path taken (flags 0x8, 0x1, 0x100; state 4; hp 0); exactly one call to the rebuild, from 0x1b3504 | supports G11 |
| e5 | G11/G13: the copy's death rebuilds the list too, and prediction does not put it back | table pointed at a copy (flag 0x20000), copy killed, table pointer and hp restored as G3 describes: list is [1] while the real player is alive; the next rebuild makes it [0, 1] | supports G11, G13, G18 |
| e6 | — | the same death sets 0x402797 (force re-clone) for a local slot | supports G18 |
| e9 | G12/G14: the clone copies pending damage, not the attacker | clone has the source's +0xc8, +0x2dc, +0x2e0, +0x2e8; +0x2e4 is empty although the source's was not | supports G12, G14 |
| e11 | G12 chain | real player with a killing blow pending → `Player_clone` → `Player_processDamage` on the clone: the clone dies and the list loses the slot while the real player is untouched | supports G12, G13 (each step executed; the order of events is the ledger's) |

Patches on this path:

| Id | Patch | Result |
|---|---|---|
| e3 | **withdrawn** 0x1b3504 → no-operation | with callees stubbed: the same 6 other calls with the same arguments and the same 9 stores in the same order; the rebuild call is the only difference — the patch did exactly what it said |
| e4, e7 | same | real death: shipped list goes [0, 1] → [1] inside the death, patched stays [0, 1] until the end-of-frame rebuild; copy's death: list untouched. The first half is the delay for real deaths that G21 names as the reason for withdrawal |
| e8, e10 | file: "prediction copy starts without pending damage", 0x11ea8c (P1, G24) | `Player_clone` makes the same 20 calls and the same 311 stores **except one**: clone +0xc8 receives 0 instead of the amount. Flags +0x2dc are still copied, as `prediction-copy.md` 5.1 says |
| e12 | same, in the chain of e11 | the clone does not die, the rebuild is not called, the list stays [0, 1]; the blow still waits on the real player |
| e13 | all proposal tables in `prediction-copy.md` | all 28 quoted original words match the executable |
| e14, e15 | proposal P2 with its nine-word routine at 0x321700 | copy's death: the routine returns without entering the rebuild, list unchanged. Real death: the routine jumps into the rebuild, which returns directly to 0x1b350c; list updated on the spot; every store has the same address and value as in the shipped run |
| e16 | the second routine at 0x321724 (for O1–O6) | run on its own: returns 0 without calling `pool_new` when `$fp` holds a copy, otherwise passes the size through and returns `pool_new`'s result. The six call-site words decode as calls to it; they were not run in place |

### 2.6 Cutscene audio — `cut_advance` 0x199214 (D8, D18, engine P6)

Called with a constructed speaker (three animation tracks, one with flag 0x20), the audio
position and status stubbed to chosen values, `anim_findTrackByFlag` 0x171178 real.

| Id | Claim | Result | Ledger |
|---|---|---|---|
| f2 | D8: track times nudged ±0.1 toward the local audio position | audio 1 s ahead: +0.1 on **all** tracks of the speaker, not only the flagged one | supports D8 |
| f3 | D8: no network-mode check; per-machine | identical game state, three audio positions (ahead, behind, aligned): +0.1, −0.1, 0 | supports D8 |
| f4 | — | the correction is re-applied every call while the position reads the same value; dead band 0.02 s | detail for D8 |
| f7, f8 | D18: wait keys hold the cutscene until every machine's stream has ended and reported | stream playing: nothing sent, key not executed, frame counter, clock and key index put back. Stream ended: "done" message queued once; key runs when the done count reaches the number of active peers (2 of 2), not at 1 of 2 | supports D18 |
| j5 | engine P6: lip-sync or generic talk depends on a local read being finished | stretch 0x196a90 onward: line number below the count at 0x83d180 → animation started with flags 0x26; otherwise the talk loop with flags 3 | supports P6 |
| j7 | Only a 0x20 track is nudged | real `anim_start` then `cut_advance`: flags 0x26 → audio position requested, track nudged; flags 3 → neither | supports D8, P6 |

| Id | Patch | Result |
|---|---|---|
| f1, f5, f6 | file: "cutscene audio sync off", 0x199448 | the original word is the "no speaker" branch; patched, the call makes neither the track lookup nor the audio request, leaves the speaker untouched, and is call-for-call and store-for-store the shipped function with no speaker. The only stores removed are the track times, 0x83d108 and 0x44fd30 |
| j6 | file: "generic talk animation in cutscenes", 0x196aa0 | the generic path (flags 3) is taken whether or not the line is ready; with j7, that also stops the nudge |

### 2.7 Sync record — tail of the tick, 0x13af44–0x13b138 (D1)

Run as a stretch with a constructed player table and peer table; `dbg_printf` stubbed.

| Id | Claim | Result | Ledger |
|---|---|---|---|
| g4 | hash = seed + integer x, y, height of every player | record {frame + 1, saved frame counter, hash}; hash equals seed + truncated coordinates of the two existing players; the empty slot is skipped; `g_netFrame` advanced, `g_simFrame` restored | supports D1, `netcode.md` |
| g5 | — | positions moved by less than one unit: same hash | supports per-machine row 14 |
| g6 | — | one player +1 in x, another −1 in y: same hash; `g_syncAcc` is added | supports row 14 (weak check) |
| g7, g8 | A mismatch flags the peer | peer record for the same frame with another hash: out-of-sync byte +0x44d7 set, message printed; equal hash: nothing; record for another frame or a dropped peer: not compared | supports D1, L7 (first half; the receiver that then ignores the peer was not run) |

### 2.8 Network sign-in — state machine 0x33ed70, state 5 (`online-setup.md`)

One call on a blank menu object, every callee stubbed, the semaphore field set to "none".

| Id | Case | Returned | State after | Sign-in check started (0x1e3c84) |
|---|---|---|---|---|
| h1 | link-ready field clear | 2 | 5 | no |
| h2 | as shipped, link up | 2 | 0xc | yes |
| h3 | debug flag 0x4f8ee0 set and pad bit 0x400 held | **4** | 5 | no |
| h3 | either of the two alone | 2 | 0xc | yes |
| h4 | state 0xb (normal end of the sequence), link up | 4 | — | — |
| h5 | local, unpublished sign-in patch applied; no debug flag, no button | **4** | 5 | no |
| h5 | same, link down | 2 | 5 | no |

So the developer shortcut described in `online-setup.md` exists and returns the same value
as the normal end of the sequence, and with the local patch the shortcut path was executed
and returned 4 once the link is up. What the front end does with 4, and everything after
it, was not run.

### 2.9 Other ledger rows

| Id | Claim | How tested | Result | Ledger |
|---|---|---|---|---|
| i1 | D12: draw decrements the first non-zero of 16 counters unless frozen | stretch 0x10b898 onward | index 3 goes 5 → 4, index 7 untouched; nothing when `game_isFrozen` returns non-zero | supports D12 |
| i2 | D12: index 12 is never decremented | counters 12, 13, 15 non-zero | none of them changes | sharpens D12 (3.6) |
| i3 | D12: frozen = pause flag in a net game | `game_isFrozen` 0x1ebdf8 with read log | returns the word 0x41b4f4; reads only that and the network-mode byte | supports D12 |
| i4 | D20: newWorld gate | `newWorld_netGate` 0x143d04 | offline or no active player: allowed, nothing changed; net game: cooldown set to 600; cooldown running: refused, message only on the local machine | supports D20 |
| i5 | D20 | cooldown running, one player in the alive list | **allowed**, cooldown restarted | sharpens D20 (3.5) |
| i6 | Per-machine row 6 | `net_objOrGhost` 0x13e180 | the copy for this machine's own player; the object itself for another player, a non-player, or offline | supports row 6, G23's premise |
| i7 | Per-object generator | `GameObject_rand` 0x1509d0, three draws | state × 1664525 + 1013904223, result state >> 16 | supports `OVERVIEW.md` |
| i8 | G8: potion use guarded | `Player_usePotion` 0x1b9cb8 on a copy | returns with no call and no store | supports G8 |
| i9 | G9: score functions test for the copy | 0x305580, 0x305650 with the table pointing at a real player, then at a copy | real: the 16-bit score at 0x50389a changes; copy: nothing | supports G9 |
| i10 | L5: step capped at 2 | `engine_frameStep` 0x19e3a8 | 1, 1, 2, 2, 2 for a field count of 0, 1, 2, 3, 10 with 0x44fd40 = 0; with the file's initial values it returns 1 | supports L5, `lag.md` C5 |
| j1 | D22: variant 3 asks "can use" and casts | stretch 0x2726ec onward, the virtual stubbed | variant 3: asks, casts on yes; other variants never ask | supports D22 |
| j8 | D6: activity judged from the camera in a net cutscene | stretch 0x1e4da8–0x1e4de0 | byte 0x4039c1 = "camera mode is not 1" offline and in a net game during a cutscene; 0 in a net game otherwise | supports D6 |

Diagnostic patches in the file:

| Id | Patch | Result |
|---|---|---|
| j2 | "knight never summons", 0x2726f4 | variant 3 no longer asks and never takes the cast exit from here; other variants unchanged |
| j4 | "pool reaper off", 0x14b9cc | reaper body not entered at 299 free blocks nor at 0 |
| j9 | "never judge activity from the camera", 0x1e4dd4 | in a net game the byte is 0 with or without a cutscene; offline unchanged |
| j10, j11 | D28 and "CloudGiant king conjure test uses a shared flag", 0x250930 | stretch from 0x250930: shipped, the conjure exit is taken when the word at object +0x530 is 0, whatever +0x508 holds; patched, it follows +0x508 and ignores +0x530 |
| j12, j13 | D29 and "fire bombs ignore the view test", 0x261fd0 | stretch 0x261fc4 onward: shipped, `isNearView(position, 960)` is asked; on "no" the shared seed is untouched, on "yes" one value is drawn from it. Patched, the test is not called and the seed is drawn every time |
| p1–p27 | every section | the "was" word quoted in the file is the word in the executable (the cutscene section quotes none; the potion section quotes one word for its two addresses, and both hold it) |

### 2.10 Kill, loot and pick-up — group k (K1–K8; patches at 0x1a5c0c, 0x1b9fcc + 0x1ba3ac, 0x1d2d30)

Item records in these checks point at rows of the executable's own item table, found at
run time through its potion-name tables or by category; no item data is in the script.

| Id | Row or patch | How run | Result | Ledger |
|---|---|---|---|---|
| k1, k2 | K1: `Player_run` skips `Player_interact` while 0x41b818[slot] is set | `Player_run` entered part-way at 0x1a5b98, run to 0x1a5c28; `Player_interact`, `dialog_isOpen`, `net_getCamFlag` real; one fake interactable object whose prompt and interact are stubs; twice, selector word 0 and 1 | word 0: prompt asked, slot stored in `g_scriptActivePlayer` (0x4d8ae4), the object's interact called. Word 1: identical up to and including `Player_weaponSwapInput`, then nothing — the 13 later calls and 5 stores (prompt icon and fade of the slot, prompt text, active player) are missing. Same offline and in a net game | supports K1 |
| k3 | K1: the sister test has a network test | stretch 0x1a6de4–0x1a6e18 | offline a set word cancels the action; in a net game the word is not loaded at all | supports K1 |
| k4 | K1: the writer | `hud_spellSelect` from its entry to just after its store | remote slot: returns at once, word untouched. Local slot with any D-pad bit held in the raw pad: `net_maskLocalButtons(slot, 3, abilityA \| abilityB \| use)` and the word becomes 1; none held: 0 | supports K1. "Only writer" is a search result, not executed; that the mask then filters sampled input was not run |
| k5 | patch "use button works with the spell selector open" | same stretch as k1, patched, word 0 and 1 | the two machines are identical, and both equal the shipped run with the word 0 | does what it says |
| k6 | same: nothing else changed | all 64 combinations of pause word, menu lockout, dialog, camera flag, prediction copy, offline/net; patched with the word 0 and 1 against shipped with the word 0 | 128 of 128 runs identical in calls and stores. Offline this is the behaviour change the patch text states | does what it says |
| k7–k10 | K2: a potion drunk with the local inventory open | `Player_run` entered part-way at its potion-button test 0x1a5940 (which makes the call with a last argument of −1); `Player_usePotion`, `invmsg_sendDrop`, `player_countPotions`, the weight helpers real. Three machines with the same record: owner with inventory open and drawn once, owner with it closed, a machine that does not own the player. Then the queued message through `invmsg_dispatch` and `inventory_dropItem` (real) on owner and other. Health and mana potion each | all three add the same amount still to be delivered. Owner-open leaves the bag alone and queues inventory message 0, mode 2, for bag 2 index 0 — the first cell of its list, not the potion used; the other two take the potion out directly and send nothing. Apart from the message the stores that differ are the stack count, the carried load re-summed at the end (record +0x120) and a HUD potion counter. After delivery (one item off the addressed stack on both, no sound, no object) the bag reads [2, 5, 4] on the owner's machine and [2, 4, 4] on the other for a health potion ([2, 5, 3] for mana), starting from [3, 5, 4] | supports K2 |
| k11 | — | read log of `inventory_dropItem` on the owner's machine | the −1 is used as the panel index of the local list copy: 675 cells in the 0xbdd8 bytes just **below** the list buffer are compared with the item and none inside it, so the open screen keeps the old counts. What is below the buffer in a running game is Unknown (zero here) | new detail for K2 (3.12) |
| k12 | K2: three conditions | menu open but list pointer 0; list loaded but menu closed; menu and list on a machine that does not own the slot | each takes the potion out directly | supports K2 |
| k13 | patch "potions always leave the bag directly" | both words; the three machines again, both potion kinds | owner-open now makes, call for call and store for store, the shipped run of owner-closed; no message; the three bags are equal. Owner-closed and the other machine are identical to their shipped runs. The list copy on the open screen is not written | does what it says, including the stated cosmetic cost |
| k14, k15 | K3: the stats page rewrites stored damage | `Player_weaponSwapInput` whole (the per-tick recompute), then `stats_screen` entered part-way at 0x1d2c20, run to 0x1d2d80; `Player_recalcDamage`, the item helpers, `sprintf`, `strcat` real; text and draw helpers stubbed. Two different one-handed weapons | the tick ends in `Player_recalcDamage(player, primary, 1)` and leaves the primary weapon's values on both machines. The page calls it with the same arguments and then with the second weapon; the record's +0xcc/+0xd0/+0xd4 then hold the second weapon's values on that machine only. With no second weapon, or set 1 active, only the first call is made | supports K3 |
| k16 | patch "stats page does not rewrite stored weapon damage" | same, patched | one call instead of two (the 7 calls that go are the second one and its look-ups); the record keeps the tick's values, equal to the machine without the page; the printed second range repeats the first. Only the three record fields and the printed text change; the single-weapon and set-1 cases are identical to shipped | does what it says |
| k17 | K5: landing conversion with a full pool | `PhProp_run` entered part-way at 0x156c0c; `pool_new` stubbed to a block, to 0, and real after all 1056 blocks were taken | asks for 0x190 bytes; with a block: constructor, then `obj_delete` on the flying object; with none: no constructor, and the flying object is still deleted | supports K5 |
| k18 | K5: 120 below the first alive player | stretch 0x156d10 on | deleted when height + 120 is below the first listed player's height (−119 stays, −121 goes); with players at 0 and 400 and the object at 250, a list starting with slot 0 keeps it, one starting with slot 1 deletes it | supports K5, G19 |
| k19 | K6: experience | `Creature_processDamage` entered part-way at 0x111e3c; `powf`, skill look-up, the creature's generator real; `player_giveExp` recorded; life-tap fraction stubbed to 0 | six cases match section 2 of `kill-loot-xp.md`: int(int(pow(value / sum of levels, 1.4)) × 0.75); shares 0.6 / 0.4 / 0.5; half at 0 hit points; capped at the level step; class-0 killer's mana. Globals read: `g_numPlayers`, the level table, one skill pointer, record +0x50, +0x59, +0xac, +0xc0, +0xc4, the object pointer, the skill list. A machine with another local slot, alive list, selector word and options gives the same | supports K6 (its "only" list is short by class, the level-step table and the skill list — all lockstep state) |
| k20 | K6: loot rolls | `loot_generateDrops` whole on 40 seeds with a knight's arguments; software double arithmetic real, everything else stubbed | 5 to 12 draws per call, every global store is to the shared seed 0x404464; the cosmetic seed and the fourth generator are untouched; reads: the shared seed, `g_numPlayers`, the two PvP flags, the level's monster level, the quality table | supports K6 for this one function; the generators and constructors it calls were not run |
| k21 | K6: gold by touch | `Gold_onTouch` whole | real player, countdown 0: `hud_addGoldFloater(slot, position, amount)`, amount zeroed, object queued for deletion, no game message. Copy, monster, running countdown, amount 0: nothing. Same whichever slot is local | supports K6 |
| k22 | K7: level-up | `player_giveExp` whole on a record 10 points short | level byte +0x59 up by one, skill points by band (1, 2, 2, 3, 3, 4, 4, 5 for levels 5, 6, 15, 16, 25, 26, 35, 36), stat points +3, `player_recalcStats`, refill; +0x58 unchanged. Same stores on owner and other; only the sound is owner-only (the message call is made on both, with the slot) | supports K7 |
| k23 | K7: acknowledgement | `menu_openInventory(slot, 1)` whole on both machines, then `invmsg_dispatch` | owner: `g_localMenuOpen` set, inventory message 9 {slot, level} queued; other: nothing stored, nothing sent. The handler stores the level in +0x58 on both | supports K7; the `hud_run` trigger (0x1db870) was not run |
| k24 | K8: knight 3's death | `Horsemen_setState(knight, 0x14)` whole, callees stubbed | variant 3 looks the summoned skeleton up by name and calls its set-state with 0x14; every variant then calls `Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25)` once and the weapon helper for hand 1 and hand 2, then its own slot 28 | supports K8 |

### 2.11 Sync breakers — group s (B1–B3, B8–B11; patches at 0x1375dc, 0x28da74, 0x217448)

| Id | Row or patch | How run | Result | Ledger |
|---|---|---|---|---|
| s1 | B1: when the exchange is on | `net_allPlayersState2` whole, nine cases | true only in a net game, lobby-launch word set, game-complete byte clear, low five bits of +0x4c1c equal to 2 for every player | supports B1; "only two writers of kind 2" not executed |
| s2 | B1/B2: when it starts | `gameMiscSync` entered part-way at 0x1e3e4c, two machines, seven frame numbers | message 9 queued on frames with remainder 60 modulo 240, by the first active machine only; never with one player of another kind; in the front end the test is not made | supports B1, B2 |
| s3 | B2: one round | the same stretch and `hud_onMsg` whole; `net_sendChecksums`, `player_checksum`, `save_playerBlock`, `net_disconnectPlayer` real; sends recorded | message 9 sets the pending word on both; each machine then sends message 10 with the two values of its own slot; with equal records no flag, no drop | supports B2 |
| s4 | B2: a mismatch | one field (gold) changed on one machine | the machine that sees the difference sets 0x4f7144 and marks that peer dropped; the other machine notices nothing. **Sharper:** the "first active machine" test in `net_disconnectPlayer` is made after the drop, so a machine that has just dropped every slot in front of it passes it and queues game message 4 as well | supports B2; sharpens `sync-breakers.md` section 1 (3.10) |
| s5 | B2: both halves | the save-buffer copy changed; hit points changed | the save-buffer copy is compared exactly like the live record; hit points are not covered | supports B2 |
| s6 | B3 | `Player_interact` whole with the game's own Savepoint virtual table (prompt and interact real); script `saveGame` whole | all-lobby game: the prompt returns "nothing", no active player store, no interact. `saveGame` asks for the save screen only when no player is kind 2 | supports B3 |
| s7 | B8: the menu value, the lifetime bit | the option-list input handler 0x1a01d0 on both of the game's option lists, cursor on the blood entry, three buttons, start values 0, 1, 2, 7; the three `GutChunk` constructors entered part-way | the entry is type 3 in both lists and the handler stores "was it 0": only 0 or 1. The lifetime bit is set for 0 and 1, not for 2 or 3 | supports B8 |
| s8 | B8: net game ignores the options | stretches 0x1ea994 (`damage_apply`), 0x1113f8 (`Creature_processDamage`), 0x1b31dc (`Player_processDamage`), offline/net × option 0/1 | the first two skip only for option 0 offline. The third draws the shared seed in a net game with either value; only the blood effect follows the option | supports B8 |
| s9, s10 | B9 | `Player_interact` whole for player 1 at a save point on two machines that differ in the card-screen state word; prompt, interact, `memcard_isBusy` real | idle machine: prompt 1 with text, active player := 1, `Savepoint_interact` asks for the save screen, sets +0x84 and +0xc4, links the light, runs the action scripts. Busy machine: prompt 0, no text, active player unchanged, none of the rest. A non-zero card result word counts as busy too | supports B9 |
| s11 | patch "save-point prompt ignores this machine's card screen" | same, patched | both machines store the active player and reach `Savepoint_interact`; the prompt text is now set on the busy machine. **Still different:** on the busy machine `Savepoint_interact` returns at its own card test — no save request (intended), and also no +0x84, +0xc4, light or action scripts | does what its text says; the residue is 3.13 |
| s12 | same: nothing else changed | idle machine patched against shipped; the all-lobby refusal | identical calls and stores; refusal unchanged | does what it says |
| s13 | B10: the save screen | `memcard_saveScreen` whole, one call per case, callees stubbed | choosing a slot (both ways) stores 1 in 0x4f8f28; sub-state 4 stores 0 on its exit; a card error goes to sub-state 9, and neither that step nor either exit from sub-state 9 stores to the latch | supports B10 |
| s14 | B10: the three readers | level change entered part-way at 0x320f8c; `jumpgate_resetDestinations` whole; stretch 0x322dc0 | latch 0: `save_clearBuffer(0)`, `save_getAct`, `jumpgate_resetDestinations`, `quest_clearAll`, `player_removeFlag39Items` per player, `vars_clearAll`, a store of 1 at 0x4f7118; the gate list reset to the hub; `Camera_reset`. Latch 1: none of it | supports B10 |
| s15 | B10/B11 chain | net launch entered part-way at 0x1375c4, run to 0x1375e0 (`save_clearBuffer(1)` real), then the act-change block | the launch zeroes the save buffer and stores 0 at 0x4f8f2a on both; a machine that entered with the latch at 1 leaves with 1 and then makes none of the seven clean-up calls and no camera reset; the other makes them all | supports B10 and the mechanism of B11 (the desync that follows is still Inferred) |
| s16 | patch "net launch clears a stuck memory-card latch" | same, patched | the store goes to 0x4f8f28; both machines leave with 0 and make the same clean-up calls. Against shipped: same calls, one store differs, by its address | does what it says. "0x4f8f2a is never set by anything" is a search result; if it were ever set, `save_clearBuffer` would skip the clear |
| s17, s18 | section 7: the debug file | `save_init` entered part-way at 0x2173c8 (the card answers yes or no); `hud_run` entered part-way at 0x1dbb60 | the flag 0x4f8ee0 is set only when the card reports the file; with it set, slot 0's lockstep pad (pressed 0x4000, held 0x8) gives 1,500,000 gold and 20,000 experience to every player on that machine | supports section 7 |
| s19 | patch "ignore the debug file on the memory card" | same, patched | flag 0 either way; calls and stores are those of a card without the file | does what it says |

### 2.12 Player movement — group m (MV2, MV5, MV6)

| Id | Row | How run | Result | Ledger |
|---|---|---|---|---|
| m1 | MV6: S | `Player_move` whole, mode 0, full push; trigonometry, angle approach, yaw and dialog look-ups real; animation step and the move itself stubbed (the vector handed to the move is recorded) | 155.150 units/s offline, 135.000 in a net game; a net game in PvP mode B with word 0x4f7124 clear, or in the level `watmedal`, uses the offline value | supports MV6 |
| m2 | MV6: formula, no acceleration | six stick positions, 31 calls each | speed = 180 × min(S × stick length, S) on the first call already; velocity along the facing (within 2/65536 turn); the facing is what lags | supports MV6 |
| m3 | MV6: multipliers and cap | five (record multiplier, runSpeed) pairs | product, capped at 1.2 (216 units/s) | supports MV6 |
| m4 | MV6: statistics and load | a record with extreme statistics, level and load against a plain one; read log | bit-identical velocities; the only record field loaded is +0x4c20 | supports MV6 |
| m5 | MV2 | `Player_move` with the dialog word set; `Player_run` entered part-way at 0x1a5640 (pad choice) | stick fields zeroed and velocity 0; the all-zero pad is chosen — offline and in a net game alike. (The menu lockout swaps the pad only offline.) | supports MV2; the writer list is a search result |
| m6 | MV5 | the **whole** of `Player_run` on a fake player, every callee stubbed, once per action state, net and offline | states 3, 4, 10, 0xc call no move routine. The others match the table in `movement-camera.md` 4.4 (0: mode 6 net / 1 offline; 1: 3; 2: 0; 6: 5; 7: 0; 8: 1; 9: 2; 0xb: 1; 0xe: none) | supports MV5. States 5 and 0xd not run (section 5) |
| m7 | MV5: knock-back | `Creature_applyKnockback` whole | player in a net game: amount zeroed, no move; offline: `Creature_moveBy` and 2 off the amount; offline PvP mode B: zeroed; monster in a net game: moved | supports MV5 |

### 2.13 Floating-point special cases — group z (F3, F4, F7)

A divide by zero is recognised here by the sticky divide or invalid bit the interpreter
sets in the control register and by the value 0x7fffffff; both follow the published
description of the console, not a measurement.

| Id | Row | How run | Result | Ledger |
|---|---|---|---|---|
| z1 | F7 | each of the four functions run to its `sqrt.s`; the result read on the next instruction; square root truncated, then rounded to nearest; three truncating adder models | executed at run time at all four sites; 0x3ee4f92d truncated, 0x3ee4f92e nearest; the adder model does not matter | supports F7, MV1. Which value a console gives cannot be decided here |
| z2 | MV1: 34 velocities | the damping step for all 65,536 angular velocities in the interpreter's arithmetic; the game's stretch 0x10bb74–0x10bc28 executed under both roundings for the differing ones and 300 others | 34 differ, the smallest ±2889; the executed stretch stores the model's value every time | supports `float-divergence.md` |
| z3 | F3: FireStorm | both constructors whole (callees stubbed); `FireStorm_run` from its entry to the store of the light record | each constructor stores 1.0 / 0.0 = 0x7fffffff at object +0x70 and +0x78. In the first 30 frames `FireStorm_run` computes 1 / (0 × 0) and stores the same with radius 0; from frame 31 finite. The fade-out branch divides by zero only for a storm that lives under 31 frames. Stores: the four light fields and the grown radius only | supports F3; who reads the two fields was not executed |
| z4 | F3: the insects | `SpellTagarsInsects_run` entered part-way at 0x30cdc0, four cases | arrival = now: distance / 0 (and 0 / 0 on the victim) = 0x7fffffff; the arrival block then reloads the register with the constant before its first use. A negative divisor is replaced the same way; a travelling swarm uses its finite quotient | supports F3 |
| z5 | F4 | the cast stretch 0x1a81a0–0x1a8200 and the melee stretch 0x1aa178–0x1aa23c of `Player_run`, slow byte 0 to 61 | frame 20 becomes 20, 40, 1200 for slow 1, 30, 59; at 60 the divisor is 0 and the frame 2147483647 (never). Melee: all three float and five integer thresholds become the maximum at 60. 61 and above are left alone | supports F4 |
| z6 | F4: how the byte reaches 60 | `Creature_run` entered part-way at 0x113604 | chill timer alone: capped at 30 for a player. Counter 7: twice the frames since it started for 30 frames, then 60 — **for any counter of 31 or more**, and the counter itself only below that | supports F4; sharpens `movement-camera.md` 4.6 (3.11) |

### 2.14 The four arena-entry sections — group n (E6, E8, E9, E13)

One check per section, as these arrived last.

| Id | Patch | How run | Result |
|---|---|---|---|
| n1 | "no prediction copy", 0x13b21c (E6) | `net_frameLoop` entered part-way at 0x13b1c4, 16 combinations of frames since the last rebase, force flag, local object | shipped: goes on to re-make the copy when 31 or more frames have passed since this machine's rebase frame 0x4027d4, or the force flag is set, and the local player has an object — two machines whose rebase frames differ by one differ on that call. Patched: never. The one store on the way is unchanged. The rebase itself was not run here |
| n2 | "cutscenes end in the tick they start", 0x199df8 (E13) | `cut_runFrame` entered part-way at 0x199d90 | shipped: ended when any slot's lockstep pad has pressed bit 0x800 — the same on every machine, **there is no per-machine difference for this patch to remove**. Patched: ended on the first call whatever the pads say; the two end levels still wait for cutscene frame 301. A patched and an unpatched machine take different exits on the same pads |
| n3 | "no autosave on entering a level", 0x217f58 (E8) | `save_armAutosave` whole, then `save_daemonRun` whole on a machine with the gate open and one with a full-screen menu open | shipped: armed word 1; the open machine calls `save_game(0, 1)` and disarms, the other saves nothing and stays armed. Patched: same calls, the one store is 0; neither saves |
| n4 | "closing a notice box does not run the pending script", 0x1dd1f0 (E9) | `help_task` entered part-way at 0x1dd008, run twice (button up, then pressed); `script_runPostAction` real, the script a stub; the sibling stretch 0x1dcf30 | shipped: the machine with the slot's notice flag set runs the pending script and empties the pending name; a machine without the flag does neither. Patched: the name stays pending on both. Still different: the menu lockout word, 60 on the closing machine (per machine by nature, D26). The full-screen help box path calls the script offline and not in a net game |

E13 itself (the hash cannot change during that cutscene) and the level-specific halves of
E6 and E8 are inferences about a level's whole course and were not run.

### 2.15 The five sections added last — group u (D26, U1, U2)

One check per section.

| Id | Patch | How run | Result |
|---|---|---|---|
| u1 | "menu lockout never drops player damage", 0x1b53d4 (D26) | `Player_takeDamage` whole, 25 damage to a player in a net game, lockout word 0 and 60 | shipped: with the word 0 the 25 is added to the pending damage at +0xc8; with 60 the function returns before that and stores nothing. Patched: both runs equal the shipped run with the word 0 |
| u2 | "menu lockout never blocks weapon swap and use", 0x1a5ba8 (D26) | the stretch of k1, lockout word 0 and 60; then all 64 combinations of the other five tests | shipped: with 60 the stretch makes no call and no store; with 0 it makes them all. Patched: 128 of 128 runs equal the shipped run with the word 0 |
| u3 | "option commit leaves the button maps alone", 0x1e6a60 (U1) | `config_commitOptions` whole in a net game with one option changed, on two machines whose button tables are equal and whose saved controller rows differ | shipped: each machine overwrites all 36 words of the nine per-slot tables with its own saved rows, so the tables then differ between the machines. Patched: the tables are untouched on both; the function's other stores (the saved option set) and its call are unchanged. With nothing changed no copy is made even unpatched |
| u4 | "mission menu ignores the chooser's pause menu", 0x231a64 (U2) | `missionMenu_run` entered part-way at 0x231a44, four machines (owns the choosing slot or not × pause menu open or not) | shipped: only the chooser's machine with its pause menu open calls `net_lockLocalInput(slot, 4)` and returns before the pad test; the other three go on. Patched: all four go on, nobody locks input |
| u5 | "jump-gate menu ignores the chooser's pause menu", 0x27def8 (U2) | `jumpgate_menuRun` entered part-way at 0x27ded8, the same four | the same result |

The pad test and the menus' actions after it were not run; U3 (the routes by which the
lockout is set inside a tick) is a list of writers and was not run.

## 3. Where a run contradicts or sharpens a document

1. **`netcode.md`, "The codec, bit by bit" — order of the spring step.** Printed: velocity
   is updated first, then added to the value. Executed: in each of the ten passes the old
   velocity is added to the value first, and the new velocity is then computed from the new
   value. With the printed order 187 of 600 decoded bytes come out wrong (a8). The sequences
   printed in the same section are right. `lag.md` C6 says the same from reading.
2. **FINDINGS G5 — two wordings.** (a) "rebuilds every pad field": the word at pad +0x24 and
   the first eight bytes are not stored by `pad_apply` (b1). Nothing was found that makes
   this matter; it limits the claim to +0x08…+0x57 less one word. (b) "never written
   anywhere in the program": `pad_apply` itself stores to 0x41bfc0 (decrement, at 0x174464)
   whenever it is non-zero (b5). Since it starts at 0 and the function only ever lowers it,
   the conclusion of G5 stands; the sentence should say "never set to a non-zero value".
   The same holds for 0x41c138, which `pad_updateRumble` counts down and clamps at 0 on
   every tick (0x174790; `docs/issues/claims-audit.md` row 12).
3. **FINDINGS L4 — now agrees.** When this work started L4 read "capped at 38 frames" and
   "one frame per 62 calls, or per 31 calls when 5 or more above". Executed: a call is held
   from a difference of 39, so the lead peaks at 39 (d2, d7), and the two rules have
   separate counters and both fire (d8). L4 was reworded in the meantime to "39 or more"
   and to three independent rules, which is what the block does. The withdrawn cap patch
   likewise held from 15, not 14 (dw2).
4. **`netcode.md`, "Input delay is not a constant".** Its hold table is right in every row
   (d2–d5). Nothing to correct there beyond what `lag.md` C1–C4 already list.
5. **FINDINGS D20 — a missing condition.** The gate refuses only when the cooldown is
   running **and** `g_alivePlayerCount` is 2 or more. With one player listed it allows the
   level change and restarts the cooldown (i5). This makes the gate another reader of the
   alive list for G13/G19.
6. **FINDINGS D12 — index 12.** True that it is never decremented; in addition the loop
   stops at the first non-zero counter, so while counter 12 is non-zero and 0–11 are zero,
   counters 13–15 are not decremented either (i2).
7. **`lag.md` section 8, last paragraph — "exactly one frame".** With 20 spring passes the
   first movement and the digital direction each come one frame earlier, but the values
   are not the shipped row shifted by one (b11).
8. **Not contradicted, now executed:** the sequences and the 7th-frame threshold of
   `netcode.md` / `lag.md` C7 / L6 (a1, a2, b8, b10); D1, D6, D8, D18, D21, D22, D28, D29
   (the read or the gate, not the divergence); the G3-based chain G11–G14; L3, L4, L5;
   engine P6; the sign-in shortcut. From the second pass: B1–B3, B8, B9, B10 and the
   mechanism of B11; K1–K3, K5–K8; MV2, MV5, MV6; F3, F4, F7; the timing rule of E6, the
   gate of E8, E9; both readers of D26; the copy of U1; the two early returns of U2. In
   every case it is the mechanism that was executed, not the desync a row infers from it.
9. **A limit that is also a finding.** A stick value that comes to rest from above lands
   exactly on an integer and then has a tiny negative velocity added to it. Whether the
   result is that integer or the float just below it depends on the last bit of the
   adder. Both console-style models give the integer; a plain truncated sum gives one
   count less, for as long as the stick is held (30 of 600 frames in the test input; a
   stick held at 56 reads 56 or 55). So (a) this interpreter pins the decoded byte only to
   within 1 on such frames, and (b) machines whose single-precision addition differs in
   that bit would feed different input to the simulation whenever a stick is held —
   `netcode.md` per-machine row 11 is a practical hazard for mixed setups (console with
   emulator, or emulators with different floating-point settings), not only a theoretical
   one. Identical machines are unaffected.

### Second pass: no contradiction, four sharpenings

Nothing run in sections 2.10–2.15 contradicts a ledger row or the stated effect of a patch.
Four statements came out sharper than written:

10. **`sync-breakers.md` section 1 (and B2) — who sends "player left".** The document says
    `net_disconnectPlayer` marks the peer dropped on this machine only and that the first
    active machine also sends game message 4. Executed (s4): the function asks "am I the
    first active machine" *after* it has marked the peer dropped. A machine that has just
    dropped every slot in front of its own therefore answers yes. In a two-machine game the
    machine in slot 1 that sees a checksum difference for slot 0 drops slot 0 **and** queues
    message 4 for slot 0. The drop itself is still local, as B2 says. What the other
    machines do with a packet from that machine afterwards was not run.
11. **`movement-camera.md` 4.6 (and the reachability note under F4) — the slow byte after
    the ramp.** Written: twice the frames since counter 7 started for 30 frames, "then the
    counter value up to 60". Executed (z6): after the ramp the byte is 60 for any counter
    of 31 or more, and equals the counter only when the counter is 30 or less. So a player
    under counter 7 sits at exactly 60 — the divide-by-zero value of F4 — for as long as the
    counter is above 30, not only when the counter happens to be 60.
12. **K2 — a detail the row does not have.** The drop message carries the −1 that
    `Player_run` passes as the last argument of `Player_usePotion`, and
    `inventory_dropItem` uses it as the panel index of the machine's local item-list copy
    (k11). On the owner's machine it compares the item with 675 cells in the 0xbdd8 bytes
    immediately below the list buffer and with no cell inside it. In the test that memory
    was zero and nothing matched; in a running game its contents are Unknown, and a match
    would decrement a 16-bit count there. This is local memory, not shared state, and it
    explains why the open screen keeps showing the old counts.
13. **Patch at 0x28da74 — what it leaves.** The patch does what its text says: both
    machines set the active player (s11). It does not make the two machines equal. On the
    machine whose card screen is open `Savepoint_interact` still returns at its own card
    test, so the save point's +0x84 and +0xc4, its light and its `action` scripts still
    differ from the other machines. `sync-breakers.md` 4b already lists those fields as
    read only by the point's own effect code and the level save record, and B7 says no
    save point on the disc has `action`; a custom level that gave one an `action` would
    still run it on some machines only.

Smaller notes, none of them a contradiction: K6's list of what experience reads is short by
the record's class, the level-step table and the killer's skill list (k19; all lockstep
state). The level-up message call in `player_giveExp` is made on every machine with the
slot as argument; only the sound is behind the local-slot test (k22;
`kill-loot-xp.md` section 2 words both as owner-only). The patch at 0x199df8 has no
per-machine difference to remove: it is a switch every machine must share (n2).

## 4. Proposed ledger rows

Not edited into `FINDINGS.md`; for the maintainers to place. Kind for all:
*Executed in isolation* (interpreter, callees stubbed, constructed state).

| Proposed | Claim | Evidence |
|---|---|---|
| G5 (reword) | `pad_apply` stores every byte of pad +0x08…+0x57 except the word at +0x24, from the record and its 8-byte previous-state block; it reads two globals, 0x41bfc0 and 0x41c138, both 0 in the file. It decrements 0x41bfc0 itself while that is non-zero, and `pad_updateRumble` counts 0x41c138 down to 0 on every tick; nothing sets either to a non-zero value | b1–b6; stores at 0x174464 and 0x174790 (the second read, not run) |
| L6 (kind) | Its model numbers — 4 dead frames, movement from the 5th, 0.8 on the 7th, at most 0.94, nothing for a push of 3 frames or fewer — are reproduced by executing the encoder, the decoder and `pad_apply`. *Executed in isolation* instead of *Inferred (model numbers)* | a2, b8–b10 |
| L6 (add) | The limit is one-sided: a stick held toward 255 settles at byte 251 (0.943; 0.989 offline) while one held toward 0 reaches 0 (−1.000). Whether movement speed scales with the value is Unknown | a3, a4, b9 |
| D12 (add) | While counter 12 is the first non-zero counter, counters 13–15 are not decremented either | i2 |
| D20 (add) | The gate refuses only with two or more players in the alive list | i5; 0x143d4c–0x143d58 |
| netcode per-machine 11 (add) | Two models of single-precision addition that differ only in the last bit give different decoded stick bytes on 5 % of frames of mixed input, and persistently for a held stick. Settle on hardware or by comparing two emulator settings | a11, a12 |
| D1 (add) | The hash is a plain sum of truncated coordinates: divergence below one unit, and opposite one-unit moves of two players, do not change it | g5, g6 |
| B2 (add) | `net_disconnectPlayer` tests "first active machine" after marking the peer dropped, so a machine that drops every slot in front of its own also queues game message 4 for the dropped slot | s4; 0x13dec0, 0x13decc |
| F4 (add) | After its 30-frame ramp the slow byte is 60 for any value of status counter 7 above 30, and the counter itself only at 30 or below; from the chill timer alone a player's byte never passes 30 | z6; 0x113774–0x1137d8 |
| K2 (add) | The drop message's last byte is the −1 `Player_run` passes; `inventory_dropItem` uses it as a panel index and, on the owner's machine with the list loaded, compares 675 cells in the 0xbdd8 bytes below the list buffer (local memory; contents Unknown) | k11; 0x1a599c, 0x1c46ec |
| B9 (add) | With the prompt's card test removed the active player is set on every machine, but the save point's +0x84, +0xc4, light and `action` scripts still follow each machine's own card state through the second test in `Savepoint_interact` | s11; 0x28dc44 |

### Proposed replacements for rows X1–X4

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| X1 | The interpreter runs the executable's own C library correctly (string and memory functions, sprintf, qsort, the multiply-based generator), which is the basis for trusting it on game functions; 65 unit tests on hand-assembled words cover each instruction class | Executed | `python3 tools/ee_tests.py SLUS_209.73`, checks x1–x5; `tools/test_ee_emu.py` |
| X2 | These ledger rows reproduce when the functions are executed: D1 (sync hash), D6, D8, D12, D18, D21 (pool spill and failure), D22, D28, D29, G8, G9, G11–G14 (clone carries pending damage; the copy's death rebuilds the alive list), L3–L5 (pacing rules), L6 (stick: 4 dead frames after a full push); B1–B3 (when the checksum exchange runs; a mismatch flags and drops on the machine that sees it), B8, B9, B10 and the skipped clean-up B11 starts from; K1, K2, K3 (each as a difference between two machines that differ in one word), K5–K8; MV2, MV5, MV6 (run speed 180 × min(S·stick, S), S 0.861945 / 0.75, cap 1.2); F3, F4 (the divides by zero and where their results go), F7 (both root values; which one a console gives is not decided); the rebase rule of E6, the autosave gate of E8, E9; both readers of the lockout word in D26, the button-map copy of U1, the two early returns of U2. It is the mechanism that is executed, never the desync a row infers from it | Executed in isolation | 208 checks, all passing; docs/issues/dynamic-tests.md sections 2.1–2.15 |
| X3 | Every one of the 27 sections in `patches/SLUS-20973_4028A55F.pnach` changes what its description says when the patched function is executed. Where a description names a difference between machines (0x1375dc, 0x28da74, 0x217448, 0x1a5c0c, 0x1b9fcc + 0x1ba3ac, 0x1d2d30, 0x13b21c, 0x217f58, 0x1dd1f0, 0x1b53d4, 0x1a5ba8, 0x1e6a60, 0x231a64, 0x27def8), two unpatched runs that differ in the one per-machine word differ as described, the two patched runs do not, and nothing else in the patched function's calls and stores changes. Two limits: 0x28da74 removes the active-player difference but not the save point's own effect state; 0x199df8 has no per-machine difference, it is a switch all machines must share. So do the withdrawn patches and several proposals not in the file | Executed in isolation | docs/issues/dynamic-tests.md sections 2.4–2.6, 2.9–2.15 |
| X4 | The network sign-in step returns "wait" as shipped and "network ready" through the developer shortcut (debug flag plus held button) | Executed in isolation | state 5 of 0x33ed70; docs/online-setup.md (unchanged) |
| X5 (new) | Execution sharpened four statements without contradicting any row: the "player left" message is also sent by a machine that has just dropped the slots in front of it (B2); the slow byte is 60 for any counter 7 above 30 (F4); the potion drop message indexes below the local list buffer (K2); the save-point patch leaves the point's own state per machine (B9) | Executed in isolation | s4, z6, k11, s11; docs/issues/dynamic-tests.md section 3, items 10–13 |

No patch is proposed by this document.

## 5. Not done, not known

- The packet-level codec (buttons, yaw, flag bits) is inlined in `net_main`,
  `net_frameLoop` and the receiver; only the per-axis functions were run.
- `net_frameLoop`, `net_predictLocalPlayer` and the receiver 0x13b5d0 were not run as
  wholes. What prediction does around the copy's run (swap the table pointer, restore hp)
  is done by the test script from G3's description. `Player_run` was run whole only with
  every callee stubbed (m6); its real paths were run as stretches.
- **Not runnable, with the reason** (second pass):
  - Every "only writer", "never set", "no other reader" statement (K1's writer of
    0x41b818, MV2's writers of 0x8e2d60, B1's writers of kind 2, the byte 0x4f8f2a of the
    0x1375dc patch, the reader list of the FireStorm light fields in F3). These are search
    results over the whole program; an interpreter that runs one function can show what a
    named writer does, not that there is no other.
  - K6 as a whole ("nothing else in the chain depends on the machine"): a universal
    statement. Run: the experience block, the roll logic of `loot_generateDrops`, the gold
    touch. Not run: the item generators and object constructors under the loot roll,
    `itemprop_tryPickup`, the dropped objects' physics.
  - The consequences B11, K1 (chest loot built on some machines only), E6, E8 and E13
    infer: each needs a level, objects and many ticks. Only the first differing step was
    run.
  - `Player_run` in action states 5 and 0xd on a blank player: both load through a pointer
    the test did not build (the cast's skill object at 0x1ab604, an object at 0x1a5ee8).
    They are not part of MV5.
  - What the input sampler does with the mask `net_maskLocalButtons` records (K1 patch
    text, "new use presses are still filtered"); what `hud_run` does to open the level-up
    screen (K7); the transport between `net_sendGameMsg` and the handlers (messages were
    carried by the test); `save_game`, the cutscene skip path after the test, and the
    rebase after 0x13b224 (stubs or stops in n1–n3); the pad test and the menu actions
    behind the early returns of u4 and u5.
  - Which of the two square roots of F7 a console produces, and whether its divide by zero
    really gives the signed maximum: the interpreter implements the published description.
  - K4 was not in scope and was not run.
- Proposals P3a/P3b (`SpellCyclone_run`) and the O1–O6 call sites in place were not run.
- The last bit of floating-point sums and products on the real console (3.9). A handful
  of known results from hardware, or from an emulator's software-float mode, would let one
  of the adder models be chosen and the others dropped.
- 62 MMI instructions are implemented, the ones a census of the executable found plus
  their near relatives; each has a unit test, none was compared with hardware. COP2 (the
  vector unit) is not implemented at all, so no function that uses it can be run.
- No symbols were added: every address used here already has a name or is an instruction
  inside a named function.
- None of this replaces the two-machine protocol in `docs/VALIDATION.md`. It removes one
  class of doubt — "does that code really do what we read" — for the functions listed.
