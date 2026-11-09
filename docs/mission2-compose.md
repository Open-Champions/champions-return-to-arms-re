# Mission 2 route list, same-session offer, and the hub-return stop

2026-11-03. Continues [the offer and planted-list hub return](mission2-offer-hub.md).
That older test still registers the destination list itself and copies player
bytes into a second emulator for the menu. This note runs the original list
writers, then one emulator from the second offer through the mission menu and
the pre-load stop. Menu-task admission uses the audited rule from
`t3/research-mission-unlocks` `e5c6176` and does not re-derive its countdown.

**Evidence convention:** Observed below includes **Executed** original EE
instructions on constructed state. It does not mean a running game. No game
text, disassembly, or disc bytes are stored here.

## Reset stores the resolver hub

**Observed / Executed:** `jumpgate_resetDestinations` `0x27db00` calls
`game_getHubName` `0x1ec300` when `g_cardXferLatch` `0x4f8f28` is 0, and the
list becomes that single name. Latch 1 returns without the resolver call and
leaves the entries that were already there. `hub2` is the result only when
the current difficulty row has its evil bit, its decision bit, and mission
1's completion bit. That includes difficulty 4 and a completion bit with the
available bit clear. Mission 2's completion bit does not change the name.
All four player records and the shared seed are unchanged.
Evidence: [reset controls](../tools/difftest_mission2_compose.py#L63-L93),
[model](../tools/ref_mission2_compose.py#L10-L21).

## Arrival insertion keeps that hub

**Observed / Executed:** `jumpgate_addCurrentLevel` `0x27db60` reads the
qualified current level through `0x1ec0f0`. A name that is already listed
returns unchanged, and `0x1ec300` is not called, even when that name is the
other hub. A name that is not already listed is appended. The later walk
calls `0x1ec300` for an entry that is `hub` or `hub2`. The first such entry
that is not the resolver result is removed, and the function returns. A
second copy of that other hub name stays. An ordinary new name remains the
appended entry when that one removal does not delete it. The 14 committed
samples contain at most one non-matching hub name, so their final lists are
the same under this order.
Evidence: [insertion samples](../tools/difftest_mission2_compose.py#L94-L130),
[model](../tools/ref_mission2_compose.py#L24-L42).

**Observed / Executed:** with the latch clear, reset while the current level
is the resolver hub, followed by insertion at `innovat1`, `inmine1`,
`inmine2`, and `innovat2`, leaves exactly that hub and then those four names.
Evidence: [route order](../tools/difftest_mission2_compose.py#L131-L143),
[model](../tools/ref_mission2_compose.py#L24-L49).

**Inferred, bounded:** a client can build the return list by calling these
two functions in that order. The test calls them directly. Which object or
level-load path calls them during play, and whether `0x27dcf4` / `0x27dd30`
restore this list, are not re-established here.

## The final portal reads that list

**Observed / Executed:** `innovat2` Portal record 57, gate 0, refuses the
prompt. The built list and the empty pending name stay, and no travel task is
registered. Gate 1 runs the original prompt `0x27d7a0`, interaction
`0x27d754`, and menu `0x27dd74`. Discovery does not grow the list, because
`innovat2` is already on it. The menu's found row is that current level, the
last entry. An explicit selection of row 0, not a pad walk, writes the hub
name and orientation 255. The list, the four player records, and the seed
stay. Difficulty 0 covers both hubs; difficulty 4 covers the evil row.
Evidence: [portal return](../tools/difftest_mission2_compose.py#L147-L220).

**Observed / Executed:** on that same state, `0x320edc` reaches loader
`0x1e55c0` and is stopped before any loader instruction. The retained
act-change stubs return without the clear. The pending name is cleared, the
current level becomes the hub, the saved previous level is `innovat2`,
orientation becomes 254, and the portal's 255 is stored at `0x41b7c1`.
Evidence: [boundary](../tools/difftest_mission2_compose.py#L223-L242).

**Unknown:** physical approach and pad movement to row 0, the loader body,
arrival, saving or restoring the list, and this boundary when
`save_actChanged` is nonzero.

## One session from the second offer to the load stop

**Observed / Executed:** on the ordinary hub, with mission 1 complete and
mission 2 unavailable, original dialog open selects node 7 and either choice
is not required here: choice 0 runs `mission_setAvailable` for mission 2.
Original message 3 then closes the dialog. `dialog_isOpen` `0x22fbc0` returns
0 and no tasks remain. The PushTrigger key returns 1. Its action dispatcher
`0x14dcc8` registers menu run `0x2316fc` and draw `0x232300` at priority 20,
with the run-task name pointer `0x5410e8`. The same memory's 26 menu calls
match the existing menu model and leave pending `innovat1` and orientation
255. Player mission bytes do not change again. The action also changes a
15-byte prefix of the packed quest table; the menu and the following load
stop leave that prefix in place. The dialog model does not perform that
write, so the comparison copies the table after the action.
Evidence: [offer session](../tools/difftest_mission2_compose.py#L299-L360).

**Observed / Executed:** `0x320edc` on that pending name stops at loader
`0x1e55c0` before any loader instruction. With the retained act-change stubs,
the current level becomes `innovat1`, the previous level is the hub, and
orientation 255 is saved at `0x41b7c1`. Player bytes and the quest table are
unchanged across that stop.

**Inferred, bounded:** the client can keep one player record and one quest
table from the offer write through this stop. The 15-byte prefix is an
original action effect, not a decoded variable name.

## Admission uses the registered task, including counter 0

**Observed / Executed:** the same trigger-opened menu is placed at state 4
with counter 16. Counter 16 is the constructed start that lands on a
still-registered 0. One original `missionMenu_run` stores counter 0 and
leaves both tasks registered. Counter 15 is the last positive countdown
value from `e5c6176` and is not remeasured here.
`task_isRunning` on the registered name returns 1. A new dialog open calls
`task_isRunning` with pointer `0x540c70`. That pointer and `0x5410e8` name
the same task. No offer script is entered and the availability writer does
not run. The next `missionMenu_run` removes both tasks, leaves counter 0 and
state 4, and `task_isRunning` returns 0. The following open selects node 8.
Choice 1 there does not call the availability writer.
Evidence: [admission](../tools/difftest_mission2_compose.py#L364-L399),
[model](../tools/ref_mission2_compose.py#L44-L50).

**Inferred, bounded:** dialog admission for this offer is the live run-task
registration. Counter 0 is not termination. A client that latches "menu has
opened" until some other flag clears will refuse the offer after this
cancellation. This does not execute the eight-step countdown, draw the menu,
or follow a real cancel button into state 4.

## hub2 dialog choices

**Observed:** `hub2` still has one NPC and one PushTrigger, with the trigger
key and action at `0x98` and `0x54`, and no ordinary-hub offer entries at
`0x734` or `0x7b0`. The NPC dialog entry is `0x0`. That entry calls
`startDialog` at cell `0x3c` with controls `(1, 0)` and a 7-character resource
name. The resource has 26 nodes.
Evidence: [hub2 boundary](../tools/difftest_mission2_compose.py#L419-L440),
[dialog binding](../tools/difftest_mission2_compose.py#L598-L621).

**Observed / Executed:** with mission 0's byte left at 3 and quest variables
absent, the original selector follows mission 2's byte and not mission 1's.
Byte 0 or 2 selects node 1 with one visible choice. Byte 1 selects node 4
with two. Byte 3 selects node 5 with two. Mission 1's byte was 0 and 3.
Evidence: [cold opens](../tools/difftest_mission2_compose.py#L647-L681),
[model](../tools/ref_mission2_compose.py#L61-L73).

**Observed / Executed:** the one visible choice on node 1 runs script
`0x29bc` and does not call `mission_setAvailable`. When mission 1 is not
complete it lands on node 2. When mission 1 is complete (byte 3) it lands on
node 3. Node 4's first choice enters `0x41b4` (`changeSwoop`, then
`activateStore` 0) and stays on node 4; its second choice adds no further
script entry. Neither changes mission bytes. Node 5's choices enter `0x2dd8`
and `0x42c8`. Both call `mission_setAvailable` for mission 3, so byte 3
becomes 1. Mission 2's byte stays 3.
Evidence: [cold choices](../tools/difftest_mission2_compose.py#L656-L681).

**Observed / Executed:** opening again after that mission-1-complete choice,
without clearing the variable it stored, selects node 3 with two visible
choices. Both call `mission_setAvailable` for mission 2 (`0x2b6c`, then
`0x4224`) and byte 2 becomes 1.
Evidence: [continuation](../tools/difftest_mission2_compose.py#L708-L727).

## hub2 trigger key and action

**Observed / Executed:** key `0x98` returns 1 when any mission 1..11 is
available and not complete, or when mission 12 is available whether or not
it is complete. Otherwise it returns 0, including mission 2 byte 0, 2, or 3
with the other missions clear. `demoRunning` is called and is not what opens
the key.
Evidence: [key and action](../tools/difftest_mission2_compose.py#L682-L707),
[model](../tools/ref_mission2_compose.py#L76-L87).

**Observed:** action `0x54` `callScript`s `0x2210`, and that entry calls
`0x1a84` first. `0x1a84` tests missions 1..12. A mission opens the gate when
it is available, not complete, and its own quest variable is nonzero.
Missions 1..9 use a 15-character variable. Missions 10..12 use a 16-character
variable. The other branch of `0x2210`, when the gate returns 0, is
`setEntrance` then `activateMissionMenu`. When the gate returns 1, `0x2210`
`callScript`s the 7-character entry at `0x22d0` instead.

**Observed / Executed:** the planted row is mission byte 0 at 3, mission 1
at 0, mission 2 at 1, missions 3..12 at 0, with quest variables clear.
`0x1a84` returns 0 on that row. The action then calls `setEntrance` with
`evilstart` and `activateMissionMenu`, and returns 0. `activateMissionMenu`
calls `dialog_isOpen` at `0x143fb0`. That call is the seeded responder
stub, not the original function. Seed 20973 returns 0, and `missionMenu_open`
`0x231520` then runs as the dialog-harness logger and returns 0. Seed 7
returns 1, and `missionMenu_open` is not called. The registration body
stays unentered on both seeds. The same row with mission 2's
variable set to 1 makes `0x1a84` return 1. The action then enters `0x22d0`
(`addHelpMessage`, then `addDeferedCall`) and does not call `setEntrance` or
`activateMissionMenu`. Mission 2 byte 3, available and complete, with that
variable set, still returns 0 from `0x1a84` and still takes the entrance
calls.
Evidence: [key and action](../tools/difftest_mission2_compose.py#L682-L707),
[model](../tools/ref_mission2_compose.py#L76-L100).

## The menu helper

**Observed:** state 0 of `missionMenu_run` `0x2316fc` calls `particle_resetAll`
`0x18ebb8` at `0x2319a4`. On the menu image, whose slot words are still 0,
the call faults on a 4-byte write at unmapped address `0x00000004`
(pc `0x0018ec10`). The compared menu path still stubs the call.
Evidence: [helper fault](../tools/difftest_mission2_compose.py#L446-L474).

**Observed / Executed:** after `particle_staticInit` `0x195d30` and
`particle_init` `0x18e648`, the same helper returns 1. Slot 0 stays occupied.
Slots 1..31 are free (`-1`). A planted group handle and trail handle become
0, and the generation words `0x44fc9c` and `0x44fca4` become 1. The call then
enters `trail_resetAll` `0x1929c8` and `particleGroup_resetAll` `0x18e840`.
When `g_trailsFrozen` `0x44fc98` is nonzero, it first calls the empty
function `0x18ebb0`. `particleDef_setDefaults` `0x18f360` stores the
definition's own address at its `+0x28`. Claiming that definition takes slot
1 and copies the address to `0x82c4e8`. The reset then writes `-1` at
definition `+4`, 0 at `+8`, and `-1` into the slot word.
Evidence: [helper effects](../tools/difftest_mission2_compose.py#L498-L535).

Fixture stubs for that boot (added 2026-11-09): `boot_particles` replaces
`task_add` `0x19e4a0` and `0x173768` with "return 0" before
`particle_staticInit` and `particle_init` run
([boot](../tools/difftest_mission2_compose.py#L486-L494)). Neither body is
entered, so no task is registered and that resource call has no effect. The
reset results above hold under those two stubs. The menu-image fault above
does not use this boot.

## Loader body through the archive lookup

**Observed / Executed:** `game_loadLevel` `0x1e55c0` for `innovat1` sets the
loading flag `0x4f7198` to 1. Real string compares walk the level table at
`0x1e57ec`. The front-end call at `0x1e5738` is not taken. The follow set is
only `0x1e55c0` and `0x3b0000-0x3c0000`, so every other call returns 0. The
run records 163 call sites. `lump_load` `0x173558` is stubbed, including the
call at `0x1e5988`. The following call at `0x1e599c`, to `0x171fd8`, is
stubbed and returns 0. The faulting 4-byte read at `0x00000004` (pc
`0x001e59ac`) uses that return plus 4. Both addresses are outside the follow
set. The shared seed is unchanged and the cosmetic seed stays 0. The body
after a successful archive open is **Unknown**.
Evidence: [loader prefix](../tools/difftest_mission2_compose.py#L543-L564).

## Physical use

**Observed / Executed:** `Player_interact` `0x1b2640` makes no calls when the
argument's word at `+0x540` is 0. The slot word at `+0x3c8` selects the
record (`slot * 0x4c30 + 0x4d8af0`). The float at that record `+0xac` is 0,
and the compare branches to the epilogue at `0x1b2c90` before the
object-pointer load at `0x1b26ac`. The box query is not reached. The
epilogue returns the record address. Slot 0 returns `0x4d8af0`. Slot 1
returns `0x4d8af0 + 0x4c30`. Both returns replace a sentinel in the return
register. The argument is `0x580` bytes, so those two words are inside it.

**Observed / Executed:** with the free-list head `0x864ea8` still 0,
`pool_init` `0x14fcd8` and `pool_new` record no store to that word, and it
reads 0 after `pool_new`. In a separate run, sentinel `0xa5a5a5a5` planted
before `pool_init` and `0x5a5a5a5a` planted before `pool_new` both survive
([sentinels](../tools/difftest_mission2_compose.py#L796-L816), added
2026-11-09). `GameObject_ctor`
`0x14cb10` then faults on a 4-byte write at address 0 (pc `0x001a1780`).
That is the null link-head store. Round 4 writes `0x847268` there from
`handle_initPool` and the constructor returns
([mission2-round4.md](mission2-round4.md)).
Evidence: [no linked player](../tools/difftest_mission2_compose.py#L567-L589).

## Still unknown

Round 4 continues the archive open and the in-range prompt in
[mission2-round4.md](mission2-round4.md). Round 5 runs NPC, trigger, and
portal use and the loader past the SIF DMA in
[mission2-round5.md](mission2-round5.md). Round 6 runs the portal menu to
travel, the destination-list save and load, and the loader to the gate
arrival in [mission2-round6.md](mission2-round6.md). This round left the following
open. In-range NPC, trigger, and portal use. The loader body after a successful
archive open, arrival, and save/load of the destination list. Real
cancel-button reachability of the constructed counter 16. Mission 1's own
completion writer is not run here; the session starts from the completed
byte. Retail `missionMenu_open` stays unentered: the harness logger runs
only when the responder's `dialog_isOpen` returns 0.

## Reproduction

From this worktree, with private inputs in ignored `local/` and unittest
preloaded so `tools/dis.py` does not shadow the standard library:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_compose.py",run_name="__main__")' local/SLUS_209.73 local local/disc.iso --seed 20973
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_compose.py",run_name="__main__")' local/SLUS_209.73 local local/disc.iso --seed 7
python3 -m unittest tools.test_mission2_compose
```

Both seeds pass the route list, the portal return, the same-session offer,
the counter-0 admission, the hub2 dialog and trigger key, the particle reset,
and the loader prefix. Each seed also records the menu-image helper fault in
`local/mission2-compose-helper-<seed>.log`. The pure model test passes
without the executable. Existing offer, travel, and quest vectors are not
edited.
