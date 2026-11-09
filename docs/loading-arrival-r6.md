# Arrival research round 6: the round-5 refusals that now run

2026-11-03. Original work extends round 5 `a574a65663c73c6092905412767cd0861bacfbe0`.
The round-6 commit `75d2b70` left round 5 untouched. `662d408` then changed the round-5 note and difftest.
**STATUS: PARTIAL.** These stages execute the original handlers past the
refusals named at the end of
[loading-arrival-r5.md lines 160–164](loading-arrival-r5.md#L160).
They are not a loader census and not a playable arrival.

Bodies 0–11 and seeds 7 and 20973 agree on every native trace below. The
executable digest is the existing loading pin. No callee is stubbed and no
instruction is patched. The route scripts are the same three fixtures as
round 5. Nothing here selects which one a campaign loads.

## Stage record

**Observed, Executed** by `tools/difftest_arrival_stage_r6.py`.

| Stage | Reached | Exact next stop |
|---|---|---|
| Route 0, `removePlayerItem` | 17 calls, each player `-1`. `0x1c5a70` runs 17 times and `0x1c1cb0` is not called. The three bag-count words are not stored. Then three `0x143500`, four `0x1416d4`, two `0x143500` | the entry returns. No post action. Queue stays front 0, back 2, parity 0 |
| Loader call `0x322e6c` | one `0x1eda24`. That pass promotes the two names and runs none of them | before `dbg_printf` `0x355490`. Queue is front 2, back 0, parity 1 |
| Second deferred pass | 48 calls of `0x145690`. Each original v0 is 0, and `0x1c5880` is not a callee | the pass returns. Front 0, back 0, parity 2. This pass is not the loader call |
| Route 0 prop, no model word | `0x23d680` reaches `0x179550`. A sentinel at `+0xc8` remains | fault at pc `0x179550`, load address `0x10`. Queue stays 0 |
| Route 0 prop, header at `+0x90` | a sentinel at `+0xc8` is replaced by the show mask. The allocated 0 at `+0x128` is not stored, so `0x170838` is not called. Slot 19 `0x23d7ac` returns | the entry then takes the same route-0 order and stops before `0x14598c`, with back count 2 |
| Route 1, object present | `0x144db8` calls `0x14f028` once. Three `0x144c00` call `0x14ef48` | the entry returns. The shown object stays on the grid. The three hidden objects are off it |
| Route 2 delete, object present | `0x144b44` calls `0x14cf90` | that body returns: a recorded store of vtable `0x5122a8` at `+0x48`, three `0x1a1698`, no `0x3b91d8`, no `0x150470`. The name-count word stays 1 |
| First `cut_runFrame` | `0x14a480` replaces `0x11111111` at `0x4039ac` with 0, then `0x19a6cc` | before `0x14f498`. The setup byte is not stored. Arguments 0 and 1 match when each starts from a fresh `cut_start` |

Evidence: [route 0 bag words, the loader promote, and the 48 v0 values, lines 202–275](../tools/difftest_arrival_stage_r6.py#L202),
[null-model sentinel and the planted mask, lines 282–327](../tools/difftest_arrival_stage_r6.py#L282),
[show, hide, and the planted grid bits, lines 330–386](../tools/difftest_arrival_stage_r6.py#L330),
[delete, the vtable store, and the first frame, lines 424–505](../tools/difftest_arrival_stage_r6.py#L424).

## `removePlayerItem` `0x14598c`

**Observed, Executed:** the route-0 entry continues through the round-5 stop.
The native runs 17 times. Every player argument is `-1`. With one player, each
call reaches `inventory_findItemBySubstring` `0x1c5a70` once. Every call
recorded from a site inside that function, before `0x1c5b48`, targets
`strstr` `0x3b96a8`, and no other target is recorded there. None of the 17
results select an item, so `inventory_removeItem` `0x1c1cb0` is not entered.
The three bag-count words receive no store that touches any of their bytes
during the entry, so the counts stay the values below.

**Observed:** those counts are not the same for every body. Bag 0 is 1 for
bodies 0, 1 and 4–9 and 11, 3 for bodies 2 and 3, and 2 for body 10. Bags 1
and 2 are 3. The native trace does not read that difference.

**Observed, Executed:** after the 17 calls the entry reads a quest variable
three times (`0x143500`), calls `setPlayerFlag` `0x1416d4` for players 0, 1, 2
and 3 with bit 4 and value 0, reads the quest variable twice more, and
returns. There is no post action. Front count and parity stay 0. Back count
stays 2.

**Executed:** bit 4 of record `+0x4c28` is set on all four records before the
entry, as a fixture, and is clear afterwards. The reference model performs
the same four clears. Its substring search is answered with no hit; the
original search agrees, because the bags match and `0x1c1cb0` is absent.

## The loader call at `0x322e6c`

**Observed:** `0x322e6c` is one call of `0x1eda24`, after `mainloop_startWarmup`
`0x322934` and before `dbg_printf` `0x355490`.

**Observed, Executed:** the finished route-0 entry leaves the queue at front 0,
back 2, parity 0. Starting at `0x322e6c` runs that one pass. The two names move
to the front, the back count becomes 0, and parity becomes 1. No native runs.
The next instruction not entered is `0x355490`.

**Observed, Executed:** calling `0x1eda24` again, which the loader does not do
at this site, runs the 48 `0x145690` tests from round 5. Each original v0 is
0, and `0x1c5880` is absent from that call, while `0x4dcec8` is 0. The queue
is then empty and parity is 2.

**Inferred:** the loader's single call does not run the deferred names this
entry queued. Treating the 48 tests as the body of `0x322e6c` would run a
second pass the loader has not reached.

## Hide mask `0x179550`

**Observed:** the body loads the halfword at model `+0x10` and the double at
model `+8`. The result starts as the complement of that double. A null model
faults on the halfword load. The fault address is `0x10`.

**Observed, Executed:** six synthetic headers match the complement of their
own hidden double on both seeds. The seed is stored at `0x404464` before the
calls and is still there afterwards. Those six rows use record bits that do
not change the complement, so a skipped walk and a walk of those records
return the same value. Since round 7 the records sit at offset `0x30`, clear
of the flag halfword and the base byte, and four of the rows run with flag
bit `0x2` stored.

**Observed, Executed:** the same hidden double `0x5` and variant bit 0, with
`+0x21` equal to 4, place one 16-byte record `{show 1, hide 2}` at `0x40`.
Different records sit at `0x30` and `0x50`. Flag 0 and flag 1, both with bit
`0x2` clear, leave the complement `0xfffffffffffffffa`. Flag bit `0x2` returns
`0xfffffffffffffff9`: the mask ored with that record's first double and
cleared by its second, from the byte `+0x21` shifted up by 4. It is not the
decoy value `0xfffffffffffffff6`. The direct call is
[lines 155–199](../tools/difftest_arrival_stage_r6.py#L155).

**Observed, Executed:** the route-0 autoprop with `States` 100 still has model
word `+0x90` equal to 0. A sentinel at `+0xc8` is still there after the fault,
and the two deferred names are not queued. A planted header whose hidden
double is `0x5` and whose flag halfword is 0 replaces a sentinel at `+0xc8`
with `0xfffffffffffffffa`; that 8-byte store is recorded. The clip word at
`+0x128` is the allocated 0 and is not stored, so `anim_push` `0x170838` is
not called. Slot 19, `0x23d7ac`, is called once and returns. The entry then
enqueues the same two names and stops before `0x14598c`.

**Inferred:** round 5's "do not append" applies while `0x23d680` has not
returned. A header that lets the mask body and slot 19 return does append.

## Show, hide, and delete with an object

**Observed, Executed:** route 1 with a resident normal lump and an empty name
table is the round-5 return: no `0x14f028` and no `0x14ef48`. The four names
have lengths 8, 10, 10 and 10. One grid object per name, each with the
creature flag and a grid link from `GameObject_ctor` `0x14cb10`, changes the
same native order as follows. `showMonster` `0x144db8` calls
`obj_updateGridCell` `0x14f028` once. Each `hideMonster` `0x144c00` calls
`obj_moveOffGrid` `0x14ef48`. Those two grid bodies make no further calls.
Before the entry the first object's flag `0x8000` and hidden bit 3 are set,
and the other three have both clear. Afterwards the first object stays on the
grid, with that flag and that bit clear. The other three are off the grid,
with both set. The entry returns. Both queue counts stay 0.

**Observed, Executed:** route 2's replacement still calls `deleteMonster`
`0x144b44` once. On an empty table it returns, as in round 5. With one object
of that name, creature flag set and property pointer `+0x2c` equal to 0, the
native calls slot 1, `GameObject_dtor` `0x14cf90`. That body stores the
GameObject vtable `0x5122a8` at `+0x48`, skips the property walk because the
pointer is 0, calls `handle_clear` `0x1a1698` three times, and returns. The
run records a store of the GameObject vtable `0x5122a8` at `+0x48`. It does
not call `0x3b91d8` or `pool_free` `0x150470`. `objNames_add` `0x14bce0`
stores 1 at the name-count word `0x5f86f8` from `0x14bd68` while the object
is planted. The delete leaves that word at 1 and records no store that
touches any of its four bytes (round 7 tests the byte range).

**Inferred:** a property list would take the walk that this fixture skips.
The name would then be removed and the block freed. This run does not show
that.

## First cutscene frame

**Observed, Executed:** after the round-5 `cut_start` return, `cut_runFrame`
`0x199944` is entered with argument 1 and, on a second fresh start, with
argument 0. Both call `light_setScale` `0x14a480`, which replaces a planted
`0x11111111` at `0x4039ac` with a recorded 0, then enter `cut_setup`
`0x19a6cc`. The setup byte `0x44fcd2` is not stored and remains 0. The next
call not entered is `0x14f498`.

**Inferred:** argument 1 is the warm-up call and argument 0 is the task call.
They have not diverged at this stop. Continuing `cut_setup` without returning
from the first call is a different entry, and it is not this result.

## What the native client can implement

Under these fixtures, for every body 0–11:

- Route 0: run the round-5 prefix, then the 17 `0x14598c` calls. Each searches
  all current players and removes nothing. The bag-count words are not stored
  and stay the values above. Apply the four `setPlayerFlag` clears of bit 4, including the three
  records past the one live player. Leave the queue at back 2. The following
  loader call only promotes that queue and must refuse at `0x355490` before
  drawing or warming the world. The 48 `0x145690` calls belong to a later
  pass, each returning 0 without calling `0x1c5880`, and only while `0x4dcec8` is 0.
- Route 0 with a matching autoprop and no model pointer: refuse on the fault
  at `0x179550` / address `0x10`, and do not enqueue. With a header at `+0x90`
  and a zero clip word that this call does not store: store the show mask from the rule above, run slot 19
  to a return, then enqueue and refuse at `0x14598c`.
- Route 1 with a resident normal lump: the round-5 empty-table return. With
  one constructed object per name: `0x144db8` relinks the grid and clears a
  planted hidden flag and bit; each `0x144c00` moves that object off the grid
  and sets them from a clear sentinel.
- Route 2: the round-5 `cut_start` finals. The replacement `0x144b44` returns
  when the name is absent. When one object is present and its property list is
  0, run `0x14cf90` through the three handle clears, record the vtable store,
  and do not free it or store the name count. The first `cut_runFrame`,
  argument 0 or 1, replaces the planted light word with 0, leaves the setup
  byte unstored, and refuses at `0x14f498`.

**Unknown, and still a refusal:** which of the three scripts a live arrival
selects; `dbg_printf` and the warm-up loop after `0x322e6c`; `0x170838` when
the clip word is not 0; `0x23d7ac` when its value argument is not 0; a delete
whose property list is present; `cut_setup` at and after `0x14f498`; and the
level-name bytes the loader stores.

Run: `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arrival_stage_r6.py local/SLUS_209.73 local/arrival-route-r4.json`.
Result: bodies 0–11, seeds 7 and 20973, all stages PASS.
Existing reference APIs, vectors, and the round-4 difftest are unchanged. The round-6 commit left the round-5 note and difftest untouched. `662d408` then changed both.
