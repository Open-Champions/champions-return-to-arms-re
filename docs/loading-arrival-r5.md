# Arrival research round 5: the next stop after each round-4 boundary

2026-11-03. Original work extends audited tip `366b65a24bc898ef96766eb15a88583b418113b4`.
**STATUS: PARTIAL.** These stages execute the original handlers past the three
round-4 stops and the deferred names that one of them queues. They are not a
loader census and not a playable arrival.

Round 4 left the normal deferred census, route selection, object load,
resource bootstrap and cutscene runtime unknown
([loading-arrival-r4.md lines 184–207](loading-arrival-r4.md#L184)).
Each row below says how far the original function went and the exact next
instruction that was not entered. Bodies 0 and 11 and seeds 7 and 20973 agree.
The executable digest is the existing loading pin. No callee is stubbed and no
instruction is patched.

## Stage record

**Observed, Executed** by `tools/difftest_arrival_stage_r5.py`. The name table
starts empty. Player count is 1, difficulty is 1, network byte `0x402791` is 0,
and the player-object word `0x4dcec8` is 0. Those are fixture inputs. The three
destination scripts stay separate; nothing here selects which one a campaign
loads.

| Stage | Reached | Exact next stop |
|---|---|---|
| Route 0, empty name table | `0x142320` finds nothing, then two `0x144160`, `0x143534`, `0x143500`, `0x143540`. Back count is 2 | before `0x14598c` |
| Route 0 deferred pass 1 | `0x1eda24` | returns with front 2, back 0, parity 1, and no native |
| Route 0 deferred pass 2 | 48 calls of `0x145690`. Each original v0 is 0, and `0x1c5880` is not a callee | the pass returns; front 0, back 0, parity 2 |
| Route 0 prop, `States` 0, argument 0 | `0x23d680` returns. A sentinel at `+0x178`, `+0x17c` and `+0x180` remains | the same `0x14598c` stop; `0x179550` is not called |
| Route 0 prop, `States` 100, argument 0 | `0x23d680` replaces that sentinel with `+0x178 = 0`, `+0x17c = 0`, `+0x180 = 0` | before `0x179550` |
| Direct `0x23d680` | argument 50 with `States` 10, and argument 0 with `States` −1, return with the sentinel. Argument −1 with `States` 100 stores −1 and stops at `0x179550` | signed `argument < States` |
| Route 1, lump absent | `0x14222c` → `0x173558` → `0x17306c` returns 0 | before `0x1724fc` |
| Route 1, resident record, flag bit 0 set | the same lookup misses | before `0x1724fc` |
| Route 1, flag bit 0 clear, name table empty | the initial entry returns: quest reads, one `0x144db8`, three `0x144c00` | no further native. `0x1724fc` and `0x14f028` are not called |
| Route 2, resident cut, header word 0 | `0x143f1c` → `cut_start` `0x19b4dc` returns, then `0x143540` and `0x143ee4` | the published replacement |
| Route 2 replacement, name table empty | one `0x144b44` | that post action returns and clears its name. Queue stays 0 |

Evidence: [route 0 order, the 48 v0 values, the limit and slot 18, lines 33–36 and 439–474](../tools/difftest_arrival_stage_r5.py#L439),
[signed compare and the sentinel stores, lines 384–417 and 485–508](../tools/difftest_arrival_stage_r5.py#L384),
[resource miss, bit 0, and the clear-bit return, lines 35–37 and 530–555](../tools/difftest_arrival_stage_r5.py#L530),
[cutscene order, formats, camera word and replacement, lines 38–49 and 584–610](../tools/difftest_arrival_stage_r5.py#L584).

## Object load

**Observed, Executed:** `0x142320` converts its name and calls
`world_findObjectsByName` `0x14bf58` once. The argument register and the
halfword at `0x142354` are both `0x64`. Virtual slot 18 runs only when object
flag `0x10000000` is set. The route-0 argument is 0. At table `0x5133c0`, slot
18's halfword is 0 and the next word is `0x23d680`.

**Observed, Executed:** an empty table makes `0x14bf58` return no object, so
slot 18 is not called. The entry continues. `0x144160` / `0x1ed52c` appends one
name, `0x143534` returns the player count, `0x144160` appends a second name,
then a quest read and a quest write run. The next native is `removePlayerItem`
`0x14598c`. Its body is not entered. Back count is 2, front count and parity
are 0.

**Observed, Executed:** one registered object with the flag and `States` 0
returns from `0x23d680` before `0x179550`. The three words, filled with
`0xa5a5a5a5` before the entry, are unchanged, and that function records no
store to them. The entry then reaches the same `0x14598c` stop. With `States`
100 the same argument replaces the sentinel: `+0x178`, `+0x17c` and the
8-byte word at `+0x180` are the recorded stores 0, and the next instruction
not entered is `0x179550`. The queue is still empty at that stop, because the
enqueues are later in the entry.

**Observed, Executed:** five direct calls of `0x23d680` separate the operator.
Argument 0 with `States` 0 returns and leaves the sentinel. Argument 0 with
`States` 100 stops at `0x179550` after storing 0. Argument 50 with `States` 10
returns with the sentinel, which an inequality test would not do. Argument −1
with `States` 100 stops at `0x179550` and stores `0xffffffff` at `+0x178`,
which an unsigned compare would not do. Argument 0 with `States` −1 returns
with the sentinel, which an unsigned compare would not do. The test is signed
`argument < States`.

**Inferred:** a loaded prop whose `States` is not greater than the argument, as
a signed compare, does not take the enqueue path. Treating the empty-table
continuation as the arrival would skip the `States` 100 stop.

## Deferred names from this prefix

**Observed, Executed:** `0x1eda24` is only the call to `0x1ed5a0`. The first
pass copies the two back names to the front, clears the back count and
increments parity. It calls no native. The second pass runs both names. Their
only native is `0x145690`. It is called 48 times. Each original v0 is 0, and
`inventory_countItemByName` `0x1c5880` is absent from that call's callees. The
player-object word `0x4dcec8` is the fixture 0. The pass ends at front 0, back
0, parity 2. The original arguments match the existing native model.

**Inferred:** these two names and the 48 tests are the queue produced by this
route-0 entry up to `0x14598c`. They are not the queue at `0x322e6c`. Routes 1
and 2 enqueue nothing in the stages above. An empty queue there is not evidence
that the loader's pass is empty.

## Resource bootstrap

**Observed:** `0x14222c` calls `lump_load` `0x173558` and then returns 0. The
lookup `0x17306c` returns the data pointer when the 16-byte record name matches
and flag bit 0 is clear. A miss calls `cd_findFile` `0x1724fc`.

**Observed, Executed:** with the lump count at 0, the route-1 entry reaches
`0x1724fc` and stops before its first instruction. No disc transfer is performed.
One resident record of the entry's name with flag bit 0 set takes that same
stop: `0x17306c` runs and `0x1724fc` is the next instruction not entered. With
that bit clear, `0x17306c` hits, `0x1724fc` is not called, and the initial
entry runs to a return. The
quest reads, `showMonster` `0x144db8` and three `hideMonster` `0x144c00` calls
find no object. `0x14f028` is not called. Both queue counts and parity stay 0.

**Unknown:** the same natives when the name table holds an object. That would
enter the grid update or the off-grid move, which this fixture does not run.

## Cutscene runtime

**Observed, Executed:** `0x143f1c` formats the current level name `0x41b721`
with `%s.lmp` at `0x531270` and the argument with `%s.cut` at `0x531288`. The
two `0x3b7ef0` calls pass those addresses, and the immediates at `0x143f54`
and `0x143f74` are `0x1270` and `0x1288`. It calls
`res_find` `0x17365c`, then `cut_start` `0x19b4dc`, and returns 0.
`cut_start` reads the header word at `0x19b504` with no null test. Bit value
`0x2` clear calls `mainloop_startWarmup` `0x322934`. Offline,
`net_closeLocalMenus` `0x1eb000` returns at `0x1eb024` without further calls.
A null player object makes `0x19a62c` skip the spell removal.

**Observed, Executed:** the level-name bytes are the fixture `authored` and a
terminator, not a value read from the loader. The lump is one resident normal
record. Its single entry is the formatted cut name and its header word is 0.
A camera object is installed at `0x4f8450` with `0xa5a5a5a5` at `+0x34`,
`+0x38`, `+0x3c` and `+0x98`. `cut_start` calls `0x2072e8` with argument 0.
That call stores 0 at `+0x34` and leaves the other three words. `cut_start`
returns. The ordered
calls are `0x3b7ef0`, `0x3b7ef0`, `0x17365c`, `0x19b4dc`, `0x322934`,
`0x1eb000`, `0x19a62c`, `0x18617c`, `0x2072e8`, `0x18619c`, `0x3a59a8` three
times, and `0x19e4a0` twice. The finals, on both seeds, are:

| Address | Value |
|---|---|
| `0x506048` | 10 |
| `0x506080` | the draw-frame word `0x44fdd0`, which is `0x400` in this executable image |
| `0x44fd2c`, `0x44fd28`, `0x44fcfc`, `0x44fd00`, `0x44fce8` | 0 |
| `0x44fcd2`, `0x44fcec` | byte 0 |
| `0x44fce0` | 1 |
| `0x44fcd0`, `0x44fcd1` | byte 1 |
| `0x7d8a04` | `0x44e10000` |
| `0x41b4fc` | `0x3c` |
| `0x4f66a8` | byte 1 |
| `0x83d198`, `0x83d18c` | 0 |
| camera `+0x34` | 0, stored over a sentinel by `0x2072e8` |
| camera `+0x38`, `+0x3c`, `+0x98` | the sentinel `0xa5a5a5a5` remains |
| `0x44fdb8` | 2 |
| `0x44fce4` | the entry data pointer; that word's first cell is 0 |

The post action then writes one quest variable and publishes a replacement.
Quest count is 1. Front, back and parity stay 0. The replacement's only native
is `deleteMonster` `0x144b44`. On the empty name table it returns, and the post
name is cleared. The two registered tasks are not run.

**Inferred:** this is the cutscene start for a zero header word, an offline
machine and no player object. It is not a cutscene frame and not proof that a
missing resource can be ignored. Passing a null pointer into `0x19b504` is a
read at address 0.

## What the native client can implement

Under the fixtures above, and only those:

- Route 0 with no matching autoprop, or with signed `States` not greater than
  the argument 0: run through the two deferred appends, the player-count read and
  the quest read/write, then refuse at `0x14598c`. The following deferred pass
  promotes and runs nothing; the pass after that may run the 48 `0x145690`
  calls. Each returns 0, and does not call `0x1c5880`, while `0x4dcec8` is 0.
- Route 0 with a matching autoprop whose signed `States` is greater than 0:
  store the three zero fields over whatever was there and refuse at `0x179550`.
  Do not append the deferred names.
- Route 1 with no resident lump, or with flag bit 0 set: refuse at `0x1724fc`
  before the disc lookup. With flag bit 0 clear and no named object: the
  initial entry's quest reads, `0x144db8` and `0x144c00` return without a grid
  call.
- Route 2 with the authored level name, a resident zero-header cut, offline
  mode and no player object: apply the `cut_start` finals in the table, leave
  the two tasks unrun, apply the quest write, and run the replacement
  `0x144b44` only while the name table has no object.

**Unknown, and still a refusal:** the loader's queue at `0x322e6c`; which of
the three scripts a live arrival selects; `0x14598c` itself; `0x179550` and
later prop work; any show, hide or delete while an object is present; a header
whose bit `0x2` is set; the level-name bytes the loader stores; and every
`cut_runFrame` after the two tasks are registered.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arrival_stage_r5.py local/SLUS_209.73 local/arrival-route-r4.json`.
Result: bodies 0 and 11, seeds 7 and 20973, all four route-0/1/2 stages PASS.
Existing reference APIs, vectors and the round-4 difftests are unchanged.
