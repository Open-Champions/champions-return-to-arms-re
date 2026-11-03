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
with counter 16. That counter is the audited last positive value from
`e5c6176`, constructed again here rather than remeasured. One original
`missionMenu_run` stores counter 0 and leaves both tasks registered.
`task_isRunning` on the registered name returns 1. A new dialog open calls
`task_isRunning` with pointer `0x540c70`. That pointer and `0x5410e8` name
the same task. No offer script is entered and the availability writer does
not run. The next `missionMenu_run` removes both tasks, leaves counter 0 and
state 4, and `task_isRunning` returns 0. The following open selects node 8.
Choice 1 there does not call the availability writer.
Evidence: [admission](../tools/difftest_mission2_compose.py#L363-L394),
[model](../tools/ref_mission2_compose.py#L44-L50).

**Inferred, bounded:** dialog admission for this offer is the live run-task
registration. Counter 0 is not termination. A client that latches "menu has
opened" until some other flag clears will refuse the offer after this
cancellation. This does not execute the eight-step countdown, draw the menu,
or follow a real cancel button into state 4.

## hub2 is not the ordinary-hub offer script

**Observed:** `hub2` has one NPC and one PushTrigger. The trigger's key and
action entries are at the same public offsets `0x98` and `0x54` as the
ordinary hub. Its script image is not the ordinary hub script, and it has no
entry at `0x734` or `0x7b0`. The NPC has a dialog property. That dialog was
not opened, so its choices are **Unknown**.
Evidence: [hub2 boundary](../tools/difftest_mission2_compose.py#L414-L434).

## Still unknown

Physical NPC, trigger, and portal use. The body of helper `0x18ebb8`: the
menu's first tick calls it at `0x2319a4`, and following it writes through an
unmapped address, so the compared menu path stubs it and makes no claim about
it. Real cancel-button reachability of counter 16, hub2 dialog choices, the
loader body, arrival, and save/load of the destination list. Mission 1's own
completion writer is not run here; the session starts from the completed byte.

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
and the counter-0 admission. The pure model test passes without the
executable. Existing offer, travel, and quest vectors are not edited.
