# Mission 2 route list and the hub-return stop

2026-11-03. Continues [the offer and planted-list hub return](mission2-offer-hub.md).
That older test still registers the destination list itself. This note runs
the original list writers, then the same final portal and the same pre-load
stop. It does not open the second-offer dialog, and it does not re-test the
mission-menu lifetime in `t3/research-mission-unlocks` `e5c6176`.

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
qualified current level through `0x1ec0f0`. A name that is already listed is
left as it is, and `0x1ec300` is not called, even when that name is the other
hub. A new name that is not `hub` or `hub2`, added while the list also has
neither, is appended and `0x1ec300` is not called. If the new name or an
existing entry is one of those two hub names, `0x1ec300` runs first: every
hub entry other than its result is removed, the other hub name is not
inserted, and a new ordinary name is then appended.
Evidence: [insertion samples](../tools/difftest_mission2_compose.py#L94-L130).

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
`save_actChanged` is nonzero. The second offer, the mission menu, and dialog
admission are not composed in this file. In particular, the audited rule that
the menu run task stays registered when the cancellation counter reaches 0
and is removed on the next negative step is not re-run here; a client still
has to apply that rule from `e5c6176` rather than treating counter 0 as
termination. Helper `0x18ebb8`, hub2's dialog resource, carried quest
variables, and a same-session offer remain open.

## Reproduction

From this worktree, with private inputs in ignored `local/` and unittest
preloaded so `tools/dis.py` does not shadow the standard library:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_compose.py",run_name="__main__")' local/SLUS_209.73 local --seed 20973
python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission2_compose.py",run_name="__main__")' local/SLUS_209.73 local --seed 7
python3 -m unittest tools.test_mission2_compose
```

Both seeds pass 84 route-list cases, 6 portal returns, and 543 counter
comparisons. The pure model test passes without the executable. Existing
offer, travel, and quest vectors are not edited.
