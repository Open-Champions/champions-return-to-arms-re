# Route marks: can what an earlier route search leaves behind change a later one?

`FINDINGS.md` row V43 (`docs/issues/live-rig.md` 16.5) showed on two linked machines that a
player's prediction copy queues real route requests on its own machine only, and that the
shared route grid then carries different search marks on the two machines (433 marked nodes
against 54) and the request queue different indexes, for thousands of ticks. Left open: can
those leftovers change the result of a later search by the real simulation?

**Answer: no — with one exception, found here, that needs a requester standing on the
corner node of the grid.** Each search begins by wiping the marks of the search before it
and by rewriting every global it reads; the queue indexes only choose a slot. Executed with
the game's own code on ten real levels: a later search B was run alone and after
1,940 histories of earlier searches (answered, suspended part-way, waiting, repeated up to
200 times, on one of two machines only); what B produced — result, path, work counters and
the grid afterwards — was identical every time.

The code has three conditions under which an earlier search does change a later one:

| Condition | Reproduced | Can a prediction copy cause it? |
|---|---|---|
| the earlier search started at node index 0, the corner of the grid: its start mark is not cleared (4.2) | **yes**: a later search to a goal by that corner fails, or takes another way | only by standing on that corner (less than 12 units inside it). In 111 of the 117 levels with a grid there is no floor there and in one it is flagged blocked; in five the terrain reaches the corner. Whether a player can get there: **Unknown** |
| 127 requests waiting when the next one is made (4.1) | yes: refused without a search | only by adding one request to 126 real ones made in the same tick |
| a clearing wave of 497 nodes or more (4.3) | no: largest wave found 229 | — |

One patch is proposed for the first (section 6): one word, tested in the interpreter only.
Neither of the two fixes first thought of — keeping the copy out of the queue, or clearing
marks at the start of a search — is needed: the second is what the game already does.

Evidence words as in `CONTRIBUTING.md`: **Observed** = read in the executable at the address
given; **Inferred**; **Unknown**. **Executed** = the game's own machine code run in
`tools/ee_emu.py`, an instruction interpreter, on a real level file — not a console, not an
emulator of one, not a running game. Nothing in this document was run on a live game.

## 1. What the code does

Names and the search itself are in `docs/spec/world-queries.md` section 10; this section adds
what matters for leftovers.

**Where the marks are.** Bits 8–15 of the node's word in the level's node grid (world +0x38,
one u32 per node; bits 0–7 links, bits 16–31 block counter). 0 = not reached, k + 1 = entered
through link k, 15 = start node [Observed: 0x184bec; the two passes of `path_search`
0x183e40]. There is no other per-node search state, no per-search stamp and no pass over the
whole grid.

**What a search does with marks it finds.** `path_search` never clears a mark and cannot
tell an old one from its own: a neighbour with any mark, or with a block counter, is not
entered [Observed, Executed]. The clearing is done by `path_service` 0x184798, once, when it
takes a request off the queue and before it seeds the search (0x184a04–0x184b88) [Observed,
Executed]:

```
if g_pathPrevStart (0x44f098) != 0:                           the branch at 0x184a08
    ring 0 = [g_pathPrevStart];  clear that node's mark
    repeat, two of the four ring buffers taking turns as "this wave" and "next wave":
        for each node of this wave, for each link bit set in it:
            if the neighbour has a mark: clear it, append it to the next wave
        after each node: if the next wave holds 497 or more, drop the rest of this wave
    until a wave is empty
ring counts[0..3] = 0;  rounds (0x44f094) = 0;  round (0x7d89c0) = 0
g_pathPrevStart = start node;  ring 0 = [start node];  start node's mark = 15
g_pathBusy (0x44f0a4) = 1;  goal test pointer and goal globals set for the request's type
```

So the wipe is a flood from the previous start along link bits, in the direction the search
itself spread. Every marked node was entered through a link bit of a node marked before it,
so the flood reaches all of them unless it drops nodes, and it drops nodes only when a wave
reaches 497 (0x184b54). It also wipes any other marked node it happens to reach. It is
skipped altogether when the previous start node had index 0 (0x184a08) — which is how the
code tells "no previous search", and is also the index of a real node. The Ghidra listing
of `path_service` omits the store at 0x184a28 that puts the previous start into ring 0;
without it the flood would seem to start from a stale node.

**What a search reads besides the grid** [Observed: every global referenced by 0x183e40 and
by the four goal tests 0x1844a4, 0x1844f0, 0x1845bc, 0x1846a4]: `g_pathEnabled` 0x44f090,
the count of rounds, the round index, the four ring counts, the ring entries below those
counts, the goal test pointer 0x7d35e0 and the goal globals of its type (0x7d5ba8, 0x7d89c4
for type 0; 0x7d5bb0, 0x7d89c8–0x7d89d4 for types 1–3), and hardware timer T0 when not
blocking. All but `g_pathEnabled` and the timer are written by the seeding above. Ring
entries above the counts are stale and never read.

**A suspended search.** `path_search` returns −1 after a round that found nothing when the
call is not blocking and T0 ≥ 7513. `g_pathBusy` stays 1, and the next call of
`path_service`, blocking or not, calls `path_search` again for the entry at the read index
before it looks at anything else; no other request starts and no mark is cleared until that
search has delivered. Requests made meanwhile only append to the queue. In a net game the
only non-blocking caller is the run task `task_plotroute` 0x322970, last in the run pass,
and `net_frameLoop` calls `path_service(1)` at 0x13af3c straight after `tasks_run`
(0x13aee0) with no call in between [Observed], so a search is never left suspended beyond
that gap.

**The queue indexes.** Write index 0x44f09c: the slot the next request is stored in, and the
full test `((write + 1) & 127) == read`, which answers the request 0 at once without queueing
it. Read index 0x44f0a0: the entry being started or searched; `write == read` means empty.
Nothing else reads them [Observed: the only code that touches either is the four request
functions, `path_service` and `world_resetRuntime` 0x18b1b8]. A request's content does not
depend on its slot.

**What an answered request of the prediction copy leaves behind** on its machine
(`Player_run` 0x1a5604 → `Creature_moveToDest` 0x119f38 → `Creature_advanceWaypoint` 0x11a108
→ `Creature_requestPath` 0x1164c0 → `path_requestToPoint` 0x184e38, type 0, capacity 16;
the chain is as run on the live rig, `live-rig.md` 12.3 d):

| What | Where | Until |
|---|---|---|
| its search's marks | node grid, bits 8–15 | the next search starts on that machine |
| its start node | `g_pathPrevStart` 0x44f098 | the same |
| both indexes one further (mod 128) | 0x44f09c, 0x44f0a0 | the level ends (`world_resetRuntime`) |
| the request's twelve words | queue slot | the slot is reused, 128 requests later |
| rounds, round index, ring counts, ring contents, goal globals | 0x44f094, 0x7d89c0, 0x7d89b0, 0x7d69b0, 0x7d35e0, 0x7d5ba8, 0x7d89c4 | the next search is seeded |
| two handle nodes taken and returned | free list 0x864ea8 | — (order of the free list not looked at) |
| the path, waypoint index, failure count | the copy itself (+0x23c, +0x2bc, +0x2c4), by `Creature_onPathResult` 0x11a260 | the copy |

At level change `game_clearLevel` 0x1e4e88 calls 0x18b270 (every node reduced to its link
byte) and then `world_resetRuntime` (indexes and `g_pathPrevStart` to 0) [Observed:
0x1e5070, 0x1e5078], and none of the 117 level files with a path grid carries anything
above the link byte, so no mark crosses a level change.

## 2. The test

`tools/routemarks_test.py` (run as `python3 -I -B tools/routemarks_test.py`; its docstring has
the options). It imports the level set-up and the path rig of `tools/difftest_world.py`
unchanged: the level file is copied into the interpreter, the game's `world_fixup` 0x181d30
is run on it, `g_world` is pointed at it, and stand-in requesters receive the results
through virtual slot 7. Everything below is the original code: the four request functions,
`path_service`, `path_search`, the goal tests, and 0x18b6c0 for the block counters.

One case is a later search **B** and a history. B is first requested and answered alone:
the grid as the fix-up left it, the queue empty at slot 0, every path global and scratch
array zero. Then the same B is requested after the history, and everything B produced is
compared word for word:

- the result delivered to B's requester (and that it was delivered once),
- the whole path buffer (48 pairs, pre-filled with a marker, so length and end mark count),
- the work counters: rounds 0x44f094, round index 0x7d89c0, the four ring counts, and
  `g_pathBusy`, `g_pathPrevStart`,
- the twelve words of B's queue entry,
- **the whole node grid afterwards** — which also shows whether any mark of the history
  survived, because B's own search clears nothing.

Histories (A = an earlier request; each A starts 0–25 nodes from B's start so that its
marks lie where B searches; about a third of the A's are searches no node can satisfy,
which run to the 80-round limit and leave the most marks a search can; A's are of all four
types, B's too):

| History | What happens before B is answered |
|---|---|
| complete | A requested and answered (blocking) |
| suspended | A started by a non-blocking call and stopped by the timer after 0, 1, 2, 3, 5, 8, 13, 20 or 40 rounds — and, as a second history, stopped again one round later; B is then queued behind it and a blocking call finishes both |
| queued | A (or two A's) and B all waiting when the blocking call runs |
| several | 2–6 A's, each answered or left waiting |
| copy | one type-0 request made 1, 2, 5, 17, 49, 64, 127, 128, 129 or 200 times, each answered: what a copy standing in the walk-to-destination state does; the write index ends that many further, modulo 128 |
| index | no A, but the queue starts at slot 1–127; and the same with an A answered first |
| non-blocking | A (or two) started by a non-blocking call on rising timer readings; B then answered by non-blocking calls only, each a new "frame" with its own readings; also B alone answered that way |
| deleted | A's requester deleted while A waits; or while A is suspended |
| torch | 1–3 block rectangles (0x18b6c0) raised before A, or between A and B; B alone is run with the same blocks |
| two machines | a search both machines made; then, on one machine only, a type-0 request made 1, 2, 3, 6 or 12 times; then B on both. Both are compared with B alone, so with each other |

The grids are compared after B; the states going into B are counted: how many histories
really handed B's search a grid with marks in it, how many nodes, and for the two-machine
cases how many nodes differed between the two machines at the moment B was requested.

Limits of this test. It uses the interpreter's default floating-point model only; floating
point enters a route search only through the goal tests and the start node, which are the
same on both sides of every comparison. Goal tests of types 1 and 3 cast rays against
objects; the object query is replaced by an empty list, as in `difftest_world.py`. The
handle list is a stub that stores a pointer. Levels: the four unpacked under `extracted/`
with the default 220 B each, and six more from the same disc (`hub`, `blood1`, `fire3`,
`storm2`, `nitmar1`, `firmedal`; the grid with the fewest linked nodes and the one with
the most are among them) with `--quick`, 44 B each. Seed 20973; a level takes 2 to 24
minutes.

## 3. Results

| Level | B | Histories compared | of them handing B a grid with marks | most marked nodes going in | Two-machine cases with differing grids | most nodes differing | Largest clearing wave reached | Worst three starts (model = original) | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `drunare` | 220 | 374 | 308 | 1,193 | 21 of 22 | 1,276 | 101 | 105 / 104 / 104 | all equal |
| `pvparena` | 220 | 374 | 308 | 1,193 | 21 of 22 | 1,193 | 102 | 105 / 104 / 104 | all equal |
| `drunarm` | 220 | 374 | 308 | 4,429 | 22 of 22 | 4,058 | 216 | 216 / 216 / 216 | all equal |
| `drundar` | 220 | 374 | 308 | 4,417 | 22 of 22 | 4,417 | 216 | 216 / 216 / 216 | all equal |
| `hub` | 44 | 74 | 62 | 1,193 | 4 of 4 | 1,192 | 92 | 93 / 92 / 92 | all equal |
| `blood1` | 44 | 74 | 62 | 4,429 | 4 of 4 | 4,428 | 216 | 216 / 216 / 216 | all equal |
| `fire3` | 44 | 74 | 62 | 4,426 | 4 of 4 | 4,423 | 216 | 216 / 216 / 216 | all equal |
| `storm2` | 44 | 74 | 62 | 4,429 | 4 of 4 | 4,415 | 216 | 216 / 216 / 216 | all equal |
| `nitmar1` | 44 | 74 | 62 | 538 | 4 of 4 | 524 | 48 | 58 / 58 / 56 | all equal |
| `firmedal` | 44 | 74 | 62 | 4,429 | 4 of 4 | 610 | 216 | 216 / 216 / 216 | all equal |
| **total** | **1,144** | **1,940** | **1,604** | | **110 of 112** | | | | **no difference** |

Histories by kind, all levels: complete 118, copy 112, deleted 224, index 224, non-blocking 224, queued 236, several 118, suspended 236, torch 224, two machines 224.

**In every one of the 1,940 histories, over 1,144 different B, what B produced was identical to
B alone**, bit for bit, the grid afterwards included. 1,604 of the histories handed B's
search a grid that carried marks (up to 4,429 marked nodes — a whole failed search around
B's start); 1,801 had another write index; in 260 a search was in progress when B was
asked. In 110 of the 112 two-machine cases the two machines' grids differed when B was
asked, by up to 4,428 nodes and in the mark bits only — the state of `live-rig.md` 16.5 —
and B came out the same on both.

What did differ after B: in 1,245 histories the contents of the four ring buffers (the
counts were equal, so only in entries above them, which nothing reads), and in 1,801 the
two indexes, and with them the slot B's request lay in. None of it is read by a search
(section 1).

## 4. The three ways an earlier search can change a later one

### 4.1 A full queue (reproduced)

A request made while `((write + 1) & 127) == read` is not queued: the request function
calls the requester's slot 7 with 0 itself (0x184ea8–0x184ec0 in `path_requestToPoint`,
the same test in the other three). Executed on every level of section 3: with 126 requests
waiting, B is queued and later answered exactly as alone; with 127 waiting, the same B —
which alone finds a path — is refused on the spot with result 0, no search run.

So the queue's *fill* can change a result, and a machine whose copy has added a request is
one nearer to it. For that to bite, 126 requests of the real simulation must be waiting at
once. The queue is emptied at the end of every tick (section 1), so they would have to be
made inside one tick; the live arena run made 31 in 15,295 ticks. **Inferred**: not
reachable in play. What would follow if it were: `Creature_onPathResult` 0x11a260 with 0
sets the waypoint index +0x2bc to 0, the first waypoint to (−1, −1) and adds 1 to the
failure count +0x2c4; `Creature_moveToDest` 0x119f38, once that count is 4 and flag
0x8000000 of +0xa8 is clear, drops the path and takes a new destination from
`Creature_randomPointNearHome` 0x110b58, which draws from the creature's own generator
[Observed]. A creature refused on one machine only would walk differently there.

### 4.2 A search started at node 0 (reproduced)

`path_service` does not clear when `g_pathPrevStart` is 0, and 0 is also the index of the
grid's corner node. A search started on node 0 therefore leaves its start mark (15) on node
0, and the search after it starts without any clearing. Node 0 has no links of its own in
any of the 117 levels, so that search marks nothing else; but a neighbour links *into* node
0 in 114 of them, so other searches enter node 0, and it can be the last node of a path.
While it carries the stale mark it cannot be entered. Executed (`start at node 0` in the
test, every level of section 3; the coordinates below are level `pvparena`, where node 0
stands at (−768, −648) and the earlier request is a type-0 request made from that point):

| Later search B (type 0, radius 24, from node 132 at (−720, −600) unless stated) | Alone | After the search from node 0 |
|---|---|---|
| any goal, started 45 or more nodes from the corner (6 per level) | — | identical; the grid keeps mark 15 on node 0 and nothing else |
| other goals, started within 3 nodes of node 132 (up to 12 per level) | — | same result and path; the counters can differ (3 of 12 here), because the wave no longer enters node 0 |
| goal (−768, −648), the corner itself | result 1, path (−720, −600) (−744, −624) (−768, −648) | **result 0, no path** |
| goal (−758, −646), 10 units along the edge | result 1, path (−720, −600) (−720, −624) (−744, −648) | **result 1, path (−720, −600) (−744, −624) (−744, −648)** |
| the corner goal again, with one more search from node 132 in between | as above | as alone: clearing that search's marks follows the link into node 0 and wipes it |

So a later search is changed when node 0 would pass its goal test: it fails where it would
have ended on node 0, or reaches a neighbouring node by another way, because the node that
found node 0 first stops trying its other links (`world-queries.md` 10.5). The same held on
all ten levels (in `nitmar1` no neighbour links into node 0, so only the first row applies there).

This is a leftover mark changing a later result, in the original code. On the two machines
it becomes a difference when only one of them made the search from node 0 — which is what
a prediction copy's request is. It needs a requester whose position rounds to node 0 (less
than 12 units inside the corner in both axes; `world-queries.md` 10.3), and afterwards a
real request whose goal is within its radius of that corner, before a clearing has passed
by. Whether anything can stand there (model `terrain_height` and `terrain_testFlag1` with a
12-unit disc at node 0's position, all 117 levels with a grid):

| Under node 0 | Levels |
|---|---|
| no floor | 111 — among them `drunare`, `drunarm`, `drundar`, `pvparena` |
| floor, flagged blocked | 1: `dismedal` |
| floor, not flagged blocked | 5: `fearboss`, `islcave1`, `obsfor1`, `water1` (all four 50 × 40 nodes with 977 linked), `islsm3a` |

In the five, the terrain's corner is the grid's corner. That is all the terrain data says:
the blocked flag is the only thing the terrain sweep stops a mover on, and the nodes next to
the corner are linked in the arena too, where there is no floor. Whether the geometry of
those five levels lets a player walk into the corner, and whether a player is ever in the
walk-to-destination state there, was not determined: **Unknown**. The arena, where the
out-of-sync reports come from, is not among them. What a monster does with the changed
result: it walks the other waypoints, or, on result 0, counts a failure as in 4.1.

### 4.3 A clearing wave of 497 nodes (looked for, not found)

The flood drops the unprocessed rest of a wave when the next wave has reached 497 nodes;
marks beyond the dropped nodes would stay and block later searches at those nodes, as
`docs/spec/world-queries.md` 10.3 says. Whether any search produces such a wave was measured:

- In the histories of section 3 the largest wave the original reached was 216 (address
  0x184b54 watched on every clearing); the limit was never reached.
- Model sweep (`--sweep-all`; `tools/ref_world.py`, whose search and clearing
  `tools/difftest_world.py` compares bit for bit with the original): from **every linked
  node of every level** — 4,050,653 starts in 117 levels — the search that marks the
  most (no node passes the goal test, so it runs to its limits; up to 4,429 nodes marked),
  then its clearing. Largest wave: **229** (`fire4`), limit 497; no clearing
  dropped a node or left a mark. The same search cut short after every 4th round, from 60
  starts per level (133,019 states): largest wave 218, none incomplete.
- On each level of section 3 the three starts the model ranks worst were run through the
  original: the number of nodes marked and the largest wave equal the model's, and the
  grid is clean after the next search.

Why about 216: a wave of the flood is the set of marked nodes at the same number of link
steps from the start, in open ground a square ring of 8 × d nodes at distance d. A search
lasts 80 rounds, a straight step costs 2 and any other 3, so the marked area is an octagon
reaching 40 nodes along the axes and 26 along the diagonals; the largest complete ring in
it is at d = 27, 216 nodes. Obstacles bend the rings and can add a few nodes (the largest
found is 229), not hundreds. **Executed** as above for the shipped levels;
**Inferred** that no level reaches 497.

## 5. The live observation, explained

`live-rig.md` 16.5, one-sided pair: machine A's copy asked 49 times, machine B's never.
After each of A's copy searches, A's grid holds the marks of that search (433 nodes) and
`g_pathPrevStart` its start; B's grid still holds the marks of the last search both
machines made (54 nodes). That is the 418-node difference, and it lasts until the next
search — there was none in that pair after tick 9797. In the ordinary pair a real request
came at tick 9994 from differing grids and left them equal: on each machine the clearing
removed whatever search had been last there (the copy's on one, an older common one on
the other), and both then held exactly the new search's marks. That is the two-machine
history of section 2, and what section 3 shows for 110 constructed cases.

The differing write index means the same request lies in different slots on the two
machines. Nothing reads a slot number; only the distance between the indexes matters, and
that is 0 on both machines at the end of every tick.

## 6. Verdict and patch proposal

**Leftover marks: no**, apart from 4.2. A real search cannot see the marks of a copy's
search or of any earlier search: `path_service` wipes them before seeding, the wipe is
complete for every search the shipped levels allow (4.3), and every global the search
reads is rewritten at the seeding. Shown by execution in 1,940 histories with no difference,
among them 110 two-machine cases whose grids differed going in.

**Queue state: no**, short of 126 real requests waiting in one tick (4.1).

**The exception (4.2)** is a search started on the corner node: its mark is not cleared.
In 112 of the 117 levels, the arena among them, there is nothing to stand on at that corner
or it is flagged blocked; in five levels it may be possible.

So this is not the cause of an arena desync, and of the two fixes first thought of,

- *clear the marks at the start of a search* is what the game already does, and
- *stop the prediction copy from queueing route requests* would remove only state that
  nothing reads (and the copy would then never receive a path in the walk-to-destination
  state, which is the picture the owner sees between ticks). Not proposed.

What is proposed closes 4.2 at its root. PCSX2 form: `patch=1,EE,00184A08,word,00000000`.
The original word was read from the executable.

| # | Address | Original | New | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| RM1 | 0x00184a08 | 10400060 | 00000000 | In `path_service`, the branch that skips the clearing when `g_pathPrevStart` is 0 becomes a no-op (its delay slot, the load of the grid pointer, runs either way). The clearing then also runs after a search started on node 0, and wipes its mark. When there was no previous search it floods from node 0 on a clean grid, finds no mark and stops at once, since node 0 has no links in any level | If some level's node 0 had links, the flood would follow them — still only clearing marks. A machine with the patch and one without differ exactly in the case of 4.2 (a real request made from the corner node is cleared on one and not on the other) | Yes |

**Tested in the interpreter only** (`patch 0x184a08` in the test, the word changed in the
interpreter's memory): on the ten levels, 450 ordinary runs (B alone and after each
history) were identical to B alone without the patch, and after a search started at node 0
89 later searches — next to the corner and elsewhere, the search to the corner
itself among them — were identical to themselves alone, grid included. **Untested on a
running game, in PCSX2 and on a console.** Given that 4.2 is not known to be reachable,
it is a tidy-up, not a fix for a reported fault.

## 7. For the ledger and for earlier documents

Proposed rows (this document edits neither `FINDINGS.md` nor any other file):

| Row | What to record | Kind |
|---|---|---|
| V43 (answer) | A later search is not changed by the marks or the queue indexes a copy's searches leave: `path_service` clears the previous search's marks by a flood from `g_pathPrevStart` before seeding and rewrites every global the search reads. 1,940 histories on ten levels (A complete, suspended, waiting, repeated up to 200 times, requester deleted, block counters raised, non-blocking service, two machines with differing grids) gave B bit for bit as alone | Executed in isolation; `tools/routemarks_test.py`, `docs/issues/route-marks.md` |
| V29 (close) | Effect of the copy's route requests on a real search: none, apart from the row below | the same |
| new | A search started on node index 0 is not cleared after (0x184a08: index 0 doubles as "no previous search"). Its start mark stays on node 0 until a later clearing reaches it, and a later search whose goal test node 0 would pass fails or takes another way; reproduced. Reachable only by a requester standing on the grid corner: no floor there in 111 of 117 levels, flagged blocked in one, unflagged floor in `fearboss`, `islcave1`, `obsfor1`, `water1`, `islsm3a`. Patch RM1 | Executed in isolation; reachability Unknown |
| new | The clearing flood is incomplete only if a wave reaches 497 nodes (0x184b54). From every linked node of all 117 levels (4,050,653 starts) the largest wave of the search that marks the most is 229 | Executed (model sweep; worst cases of ten levels in the original) |
| new | With 127 requests waiting the next request is refused with result 0 (0x184ea8); reproduced. A copy's request counts toward the 127 | Executed in isolation; Inferred (unreachable in play) |

Corrections and additions:

| Where | Statement | What was found |
|---|---|---|
| `names.tsv`, `path_service` | "1 request per call" | it loops: a blocking call answers every waiting request; a non-blocking call goes on until T0 ≥ 9000 [Observed 0x184de4–0x184df8; Executed: 126 waiting requests and B answered by one call] |
| `docs/spec/world-queries.md` 10.3 | "nothing if the previous start node had index 0" | add the consequence: after a search started on node 0 the next search clears nothing, and the mark on node 0 stays (4.2) |
| `docs/spec/world-queries.md` 10.3 | "Marks the flood does not reach stay in the grid and block later searches at those nodes" | true of the code; add that no search in the shipped levels produces such a wave (4.3), and that the flood also wipes any other marked node it reaches along links |
| `docs/spec/world-queries.md` 11, not generated: "path start nodes at grid index 0" | | now executed in the original (4.2); the model was not compared for it |
| `docs/spec/world-queries.md` 10.1 | 0x18b6c0: "There is no bounds check" | confirmed by accident: a block rectangle that left the grid of `pvparena` made the original read below the grid (0x18b7ac) and the interpreter stop. The test now keeps its rectangles six nodes inside |
| `docs/issues/live-rig.md` 16.5, last paragraph | "Whether a copy's marks can survive a real search's clearing and change its result … is still Unknown" | answered here: not through an incomplete clearing; only through a search started on node 0 |
| Ghidra listing of `path_service` (`decomp/all/00184798.c`) | the clearing loop reads ring 0 without a visible store | the store of `g_pathPrevStart` into ring 0 is at 0x184a28 |

No symbol is proposed: every address used here is named in `names.tsv` or `symbols/`, or
has a name proposed in `docs/spec/world-queries.md` section 13.

## 8. Not done, not known

- Nothing here ran on a console, in PCSX2 or on the live rig. A live confirmation of the
  main result would be a real monster request made while the grids differ; the ordinary
  pair of `live-rig.md` 16.5 contains one (tick 9994, equal results).
- Whether a player can stand within 12 units of the grid corner in the five levels of 4.2,
  and be in the walk-to-destination state there. Walking a character into that corner on
  the live rig, with the copy on one machine only, would settle it.
- The original was run on ten levels; the other 107 are covered only by the model sweep of
  4.3, which measures the clearing waves and node 0, not pairs of searches.
- The sweep measures the search that marks the most from every start, and that search cut
  short from 60 starts per level; it does not enumerate every goal.
- Block counters (torches, fires) were raised in the pair test, not in the sweep. A block
  counter stops a search from entering a node; it does not stop the clearing.
- When a ring buffer is full (512), a node is marked but not queued; whether any search in
  the shipped levels fills one was not measured. It would not change the clearing.
- A copy's request that is still waiting when the level is torn down (`game_clearLevel`
  resets the indexes without answering) was not run. Nor was `g_pathBusy` surviving a
  level change (`world_resetRuntime` does not clear it); in a net game no search is left
  suspended past the end of a tick (section 1).
- The order of the handle free list 0x864ea8 after a copy's request, and
  `g_terrainStamp` 0x44f08c, which the ray-casting goal tests of types 1–3 advance, were
  not looked at; the copy asks with type 0, whose goal test casts no ray.
- The two levels without a path grid have nothing to test.
