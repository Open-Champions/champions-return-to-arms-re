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
  group. At the time of writing: **198 checks, 198 PASS** (the count follows the patch
  file: one `p` check per section). The first pass ended at 128; sections 2.10–2.14 are the
  70 added since (60 in five new groups, 10 for new patch sections).

The patch file and the ledger changed several times while this was being written: the
alive-list patch at 0x1b3504 and the two pacing patches were withdrawn, rows G14–G24,
D24–D32 and L8–L12 arrived, L4–L6 were reworded, and the patch file went from five
sections to twelve. The script therefore finds patch sections by the address they patch,
runs whatever is there, reads proposal tables out of `docs/issues/prediction-copy.md` and
`docs/issues/lag.md`, and keeps the withdrawn patches as explicit words so their result
stays on record. Row wordings quoted below are those of `FINDINGS.md` as it stood at the
last run (2026-10-10).

A second pass covered what arrived after that: ten more patch sections (0x1375dc, 0x28da74,
0x217448, 0x1a5c0c, 0x1b9fcc + 0x1ba3ac, 0x1d2d30, 0x13b21c, 0x199df8, 0x217f58, 0x1dd1f0)
and the ledger rows B1–B3, B8–B11, K1–K3, K5–K8, MV2, MV5, MV6, F3, F4 and F7, which had
been written from reading only. **All 22 sections now in the patch file are executed**, and
each of those rows is reproduced, sharpened, or listed in section 5 with the reason it
could not be run. No ledger row and no patch description was contradicted; four statements
were sharpened (section 3, items 10–13).

**Two machines.** The interpreter has one machine. Where a row or a patch is about a
difference between machines, the check builds the same state twice, changes the one word
that is per-machine state (a selector word, a menu flag, a card-screen state, a latch),
runs the same code on both and compares every call (target and arguments) and every store
outside the stack. "The patch removes the difference" means the two patched runs are
identical; "nothing else changed" means the patched run equals, call for call and store
for store, the shipped run with the per-machine word clear. Large functions were entered
part-way with registers and frame prepared, as the pacing checks do; each row says where.

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
| b5 | G5: "never written anywhere in the program" | 0x41bfc0 forced to 2 | `pad_apply` itself decrements it (store at 0x174464) and drops button 0x800 | sharpens G5: the function is its own writer once the value is non-zero; it never becomes non-zero by itself |
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
| p1–p12 | every section | the "was" word quoted in the file is the word in the executable (the cutscene section quotes none) |

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
   engine P6; the sign-in shortcut.
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

## 4. Proposed ledger rows

Not edited into `FINDINGS.md`; for the maintainers to place. Kind for all:
*Executed in isolation* (interpreter, callees stubbed, constructed state).

| Proposed | Claim | Evidence |
|---|---|---|
| G5 (reword) | `pad_apply` stores every byte of pad +0x08…+0x57 except the word at +0x24, from the record and its 8-byte previous-state block; it reads two globals, 0x41bfc0 and 0x41c138, both 0 in the file. It decrements 0x41bfc0 itself while that is non-zero; nothing sets it | b1–b6; store at 0x174464 |
| L6 (kind) | Its model numbers — 4 dead frames, movement from the 5th, 0.8 on the 7th, at most 0.94, nothing for a push of 3 frames or fewer — are reproduced by executing the encoder, the decoder and `pad_apply`. *Executed in isolation* instead of *Inferred (model numbers)* | a2, b8–b10 |
| L6 (add) | The limit is one-sided: a stick held toward 255 settles at byte 251 (0.943; 0.989 offline) while one held toward 0 reaches 0 (−1.000). Whether movement speed scales with the value is Unknown | a3, a4, b9 |
| D12 (add) | While counter 12 is the first non-zero counter, counters 13–15 are not decremented either | i2 |
| D20 (add) | The gate refuses only with two or more players in the alive list | i5; 0x143d4c–0x143d58 |
| netcode per-machine 11 (add) | Two models of single-precision addition that differ only in the last bit give different decoded stick bytes on 5 % of frames of mixed input, and persistently for a held stick. Settle on hardware or by comparing two emulator settings | a11, a12 |
| D1 (add) | The hash is a plain sum of truncated coordinates: divergence below one unit, and opposite one-unit moves of two players, do not change it | g5, g6 |

No patch is proposed by this document.

## 5. Not done, not known

- The packet-level codec (buttons, yaw, flag bits) is inlined in `net_main`,
  `net_frameLoop` and the receiver; only the per-axis functions were run.
- `Player_run`, `net_frameLoop`, `net_predictLocalPlayer` and the receiver 0x13b5d0 were
  not run as wholes. What prediction does around the copy's run (swap the table pointer,
  restore hp) is done by the test script from G3's description.
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
