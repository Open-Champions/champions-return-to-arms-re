# What a mission change does to the bags

2026-11-03. Continues [the campaign note](quests.md). That note's section 7
listed what still blocked a start-to-finish campaign. Later branches closed
some of those rows. This note is the inventory that travels with the
character: a same-act mission change, an act change, and the quest-item copy
`save_load` can make. Nothing here was seen on a running game.

**Evidence convention:** Observed below includes **Executed** original EE
instructions on constructed state. Addresses are US v2.00. No game text,
disassembly, or disc bytes are stored here. `player_recalcStats` `0x1b6458`,
`player_resetIdleAnim` `0x1b2470`, and `net_isLocalSlot` `0x13e150` (returning
0) are stubbed, so the closed inventory screen's grid refresh is not compared.
The shared seed at `0x404464` is unchanged on seeds 20973 and 7.

## Which section 7 rows later research closed

| Row in `docs/quests.md` §7 | Status | Where |
|---|---|---|
| Dialog | Partial. The ordinary hub's predicates, first offer, and second-offer matrix are executed. One session grants mission 2, opens the menu, writes pending `innovat1`, and stops at loader `0x1e55c0` before any loader instruction | `t3/research-mission-unlocks` `e5c6176`, `docs/spec/mission-unlocks.md`; `t3/research-mission2-route` `b8e2d11`, `docs/mission2-compose.md` |
| Granting a quest item | Open. Starting equipment's `inventory_giveItem` `0x1c1868` is executed. `givePlayerItem`'s descriptor parse is not | `t3/research-loading-readiness` `366b65a`, `docs/starting-equipment-r4.md` |
| Removing a turned-in item | The equipped-pointer fixups inside `inventory_removeItem` `0x1c1cb0` are executed on the act-change path below. The substring search in front of a script turn-in was already specified | this note; `docs/spec/game-messages.md` §5.2; `docs/spec/script-builtins.md` §3.6 |
| Cutscenes and the shop | Open. None of the four neighbouring branches execute them | — |
| Menu draw `0x232300` | Open. The run task's lifetime is executed, including counter 0 staying registered. State 4's helper `0x18ebb8` faults on a 4-byte write at `0x00000004` when it is not stubbed | `e5c6176`; `b8e2d11` |
| Save and load of the record | Partial. A direct `save_build` / `save_load` does not snapshot the menu task registry. A party-wipe `save_reload` `0x22266c` restores the checkpoint record, so gold, experience, bags, and equipment roll back with it; no separate death fee was established. The quest-item copy below is the callee `save_load` uses when `0x4f85b4` is set | `e5c6176`; `t3/research-death-reload` `9a34671`, `docs/death-reload.md`; this note |
| Which script entry runs | Open outside the one hub offer above | `b8e2d11` |

State 4's countdown, which `docs/quests.md` had not followed to 0, is executed
on `e5c6176`: counter 0 stays registered, and the next negative
`counter - 16` result removes the run task when `0x8e2f00` is 0.
`b8e2d11` uses that rule for the second offer and does not re-derive it.
hub2's dialog choices, the loader body, arrival, and physical use remain
unknown there.

Mission bytes, medals, gold, experience, and level are not cleared by the
stretch below. That is the campaign advance state that survives a mission
change. The quest list and the quest-variable values survive only when the
clear does not run.

## Same-act travel keeps the bags

**Observed / Executed:** `mainloop_loadRequestedWorld` is entered at
`0x320f8c` and stopped at `0x321024`, with `r19` already `0x420000`. The
instruction at `0x320ef0` is what writes that base; the level-store call at
`0x320f44` is outside this entry. `save_actChanged` `0x217f70` is called with
the pending name at `0x41b6d0`.

When the pending name is in the current act, the call returns 0 and the clear
does not run. Executed pairs: `blood1` to `strife` in act 0, and `hub` to
`hub2` in act 0. Bags, equipment pointers, the quest-list count, the variable
values, gold, experience, the mission byte, and the medal byte stay. The act
at `0x88d3d4` stays. The word at `0x4f7118` stays 0. `game_clearLevel`
`0x1e4e88` is a later step of a real load. With every callee stubbed, its own
body stores nothing in the first two player records, and those bytes are
unchanged. **Unknown:** whether a followed object destructor, which this run
does not enter, writes bag bytes. The earlier arena-entry note still says
that destructor zeroes the object pointer and five record words.

A frontend byte at `0x41b510` that is not 0 takes the branch at `0x320f94`.
Its delay slot clears the gate, so `save_actChanged` is not called and the
clear does not run. The act stays the one already stored.

## An act change strips unkept flag-39 items

**Observed / Executed:** when `save_actChanged` returns nonzero, `0x4f8f28` is
0, and `task_isRunning` `0x19e5e8` returns 0, the stretch calls
`save_clearBuffer(0)` `0x21f144`, `save_getAct` `0x217edc`,
`jumpgate_resetDestinations` `0x27db00` (which calls `game_getHubName`
`0x1ec300`), `quest_clearAll` `0x1d3adc`, `player_removeFlag39Items`
`0x1be1d8` once per slot below `g_numPlayers`, and `vars_clearAll` `0x1ed728`.
The instruction at `0x321020` then stores 1 at `0x4f7118`.

`player_removeFlag39Items` calls the real `inventory_removeItem`. A flag-39
cell whose name is not on the keep list in `docs/quests.md` §3 is removed.
The equipment slot its definition byte names is cleared, the active weapon
word is cleared when it names that cell and the weapon class becomes 5, and a
later cell's equipment and weapon pointers follow the slide. Stamps of the
tail drop by one. Ordinary items, kept names (`bloodstone`, `shardof`, and the
exact keep list), gold, experience, level, the mission byte, and the medal
byte stay. The quest-list count becomes 0 and the used titles get the
placeholder. Variable names stay and their value bytes become 0. A record at
or above `g_numPlayers` is not walked. Executed for `blood1` to `innovat1`
(act 0 to act 1) and for the first level from act −1 into act 0.

**Observed / Executed:** a latch byte of 1 at `0x4f8f28` still lets
`save_actChanged` store the new act, then the branch at `0x320fb4` skips the
clear. Bags, quests, and variable values stay, and `0x4f7118` stays 0. A
forced nonzero return from `task_isRunning` does the same skip after the act
has been stored. The empty task list's real call returns 0 and is the case
that clears. The death-task object itself is not constructed here; the
checkpoint rollback of the bags is the death-reload result cited above, not
this skip.

## Quest items copied on a load are bag 2 only

**Observed / Executed:** `inventory_shareQuestItems` `0x1c4fa8` has one caller,
`save_load` at `0x2221ac`. It reads the source slot's bag 2. Every cell there
with flag bit 39 set is copied, stack count included, to each other slot below
`g_numPlayers`, through `inventory_giveItem`. Those other slots first lose
their own bag-2 cells with that bit, through `inventory_removeItem`, including
when the source bag has nothing to copy. A plain cell in bag 2 stays and is
not a copy source. Bags 0 and 1 are not walked, so a flag-39 cell there is
neither dropped nor copied. Bit 38 is not bit 39. The source record is
unchanged. A copy is a new cell and is not equipped. Calling it with slot 1
copies that slot's bag 2 to the other slots in range; `save_load` passes 0.
Gold, the mission byte, and the seed are unchanged.
**Unknown:** flag bit 8 (stackable) on a cell this function copies. The give
rule for a matching stack is the one already executed in
`docs/spec/game-messages.md` §5.1 and was not re-run from this caller.

## The arena call is not a mission reset

**Observed / Executed:** `player_removeAllItems` `0x1bf600` removes the first
cell of each non-empty bag and leaves a later cell in place. Equipment and
weapon pointers follow the same fixups. Gold and the mission byte stay. Its
only `jal` site is `0x304e9c`. The walk entered at `0x304e88` and stopped at
`0x304eb4` calls it once per slot below `g_numPlayers`, not until a bag is
empty. That site is the arena init path. It is not the act-change stretch.

`player_removeFlag39Items` is reached from `0x220684` and from the stretch at
`0x320ffc`. The second of those is the campaign clear above.

## What is still in the way of playing the campaign through

Dialog outside the executed hub offer, `givePlayerItem`, the menu draw, the
unstubbed helper fault, the loader body and arrival, hub2's choices, cutscenes,
and the shop. A same-act mission change does not by itself take the bags. An
act change takes the unkept flag-39 cells and the quest list, and zeroes
quest-variable values, and it leaves the mission bits and the ordinary items.
The client refusal for a start-to-finish campaign stays until the open rows
above are executed.

## Reproduction

From this worktree, with the private executable in ignored `local/` and the
standard-library `dis` module loaded first so `tools/dis.py` does not shadow it:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 tools/difftest_inventory_reset.py local/SLUS_209.73 --seed 20973
python3 tools/difftest_inventory_reset.py local/SLUS_209.73 --seed 7
python3 -c 'import dis,unittest,sys; sys.path.insert(0,"tools"); r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName("test_ref_inventory_reset")); sys.exit(0 if r.wasSuccessful() else 1)'
python3 tools/difftest_quests.py local/SLUS_209.73
```

Both seeds pass the caller sites, the flag-39 fixups, the bag-2 copy, the
one-cell arena removal, the slot walk, the seven act gates, and the stubbed
`game_clearLevel` body. The pure model test passes without the executable.
Existing quest vectors are not edited.
