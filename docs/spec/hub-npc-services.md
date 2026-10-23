# Hub interaction and non-vendor service census — SLUS-20973 v2.00

Research date: 2026-10-23. `tools/ref_hub_npcs.py` is the bounded direct-use
reference, and `tools/difftest_hub_npcs.py` pins the executable
SHA-256 and the two hub archives from the read-only disc. It checks object
records and script call sites, then executes `Savepoint_interact` in
`tools/ee_emu.py` with seeds 20973 and 7. **Observed** below means addressed
executable code or a pinned disc record; **Executed** means the named original
function ran on constructed state; **Inferred** is a link between separate
observations; **Unknown** has no accepted parity claim. There is no new
running-game or native-client capture in this work.

This reuses `t3/research-vendors` (`e2ff7e3`, shop),
`t3/research-story-route` (`76d4447`, hub conversation and mission map),
`t3/research-quest-log` (`03c2304`, mission and journal records), and
`t3/research-dialog` (`334578d`, dialog machine). For generic proximity,
savepoint and gate mechanics it also cites `t3/research-exits-walkin` and
`t3/research-death-flow`. These are research inputs, not merged commits.

## 1. Every interactive hub record

**Observed** `HUB.GOB` has 24 object records and `HUB2.GOB` has 21. The
interactive records are exactly the following five in each archive. The
other records are lights, player placement, scenery/effects and custom
variables; those are not interaction services. `HUB.GOB` SHA-256 is
`1d5f240025afb86800040664a168c27c236a8431fc4c02caf388bdcee37b385f`;
`HUB2.GOB` is
`a061b0f35549674050765eb8f3243491f947888c2cdcef85e5110e2388d71dc4`.

| Role / class | `hub` index | `hub2` index | Engagement and destination |
|---|---:|---:|---|
| One `NPC` | 10 | 5 | Has `dialogScript` and `shop=1` in both hubs. The same NPC owns conversation choices that can advance quests and open the vendor. There is no second NPC record in either hub. |
| `Savepoint` | 8 | 6 | Use opens the memory-card save flow; proximity and a dead teammate can trigger auto-save or resurrection. No `action` property in either record. |
| `Portal` / `JumpGate` | 6 | 0 | Use offers gate travel after discovery and party-distance gates. It is a distinct route from the mission trigger. |
| `PushTrigger` | 11 | 7 | Has `key` and `action`; use runs the mission-map script and opens the mission menu when eligible. |
| Rectangular `Trigger` | 12 | 9 | Walk-in script signal changes the portal visual state; it is not the use prompt or a separate service menu. |

**Observed** the two scripts export 82 and 73 entries. The NPC's
`dialogScript` resolves to an entry in each. Each script calls `startDialog`
once; the associated dialogs hold 31 nodes/54 choices (`hub`) and 26
nodes/48 choices (`hub2`). Static calls respectively include
`activateStore` 23/19, `activateMissionMenu` 2/2, `addQuest` 11/5 and
`setMissionAvailable` 35/30 and `removePlayerItem` 19/19. The latter is
concentrated in each script's `start` entry; the bounded NPC choice-action
reach scan did not find it behind a dialog choice. Those are call sites across
mutually exclusive branches, not counts of services delivered in one
playthrough. Neither hub
script calls `healPlayer`, `giveFullHealth`, `givePlayerExp`, `saveGame`,
`saveCheckPoint`, or `removeQuest`. The exact disc object and script counts,
and these absences, are asserted by the new difftest.
`removePlayerItem` 0x14598c can change bags/equipped pointers when its
condition runs (`docs/script.md`); the current probe does not execute those
hub-entry conditions or declare them a service charge.

**Conclusion limited to these two hub archives:** there is no separate
healer NPC, paid resurrection NPC, stash/storage object, trainer NPC or
additional quest-giver NPC. The existing vendor NPC also gives quest and
mission choices. The savepoint supplies conditional co-op resurrection;
the inventory skill page and save UI are not NPC services. This census does
not establish the absence of those roles in other levels or game modes.
`game_getHubName` 0x1ec300 selects `hub2` only after the documented evil and
decision bits and mission-1 completion (`t3/research-quest-log` §4); it is an
alternate hub, not a second quest-giver standing beside the first.

## 2. Engagement, screen, cost and player-record effect

| Service | Original path and screen | Cost and effect |
|---|---|---|
| Quest conversation, both NPCs | **Observed** `Player_interact` 0x1b2640 picks the nearest flagged object in its bounded box; `Creature_interactPrompt` 0x116d50 applies display-name, facing, hostile-nearby and shop-busy gates. Use enters `Creature_interact` 0x116bd8, acquires menu mutex, runs the record's `dialogScript`; `script_startDialog` 0x143824 and `dialog_onMsg` 0x22ee2c load the associated `.dbin`. `dialog_showNode` 0x230c74 submits the dialog box, localized line, voice and eligible choices. `docs/dialog.md` records the message-driven close and deferred store open. | **Observed/Executed in `t3/research-story-route`:** the fresh `hub` ending actions set mission 1 available and add one quest; mission byte at `g_players` 0x4d8af0 +0x4bbf becomes 1, count at +0x43d0 becomes 1, and one title/body pair starts at +0x41d0. The later hub and alternate-hub action calls also reach `setMissionAvailable`, `setv` and `addQuest`, but their full state-to-choice mapping is **Unknown** without an integrated dialog traversal. No quest-dialog gold, XP or item fee is established. The optional store choice uses the separate vendor pricing contract. |
| Savepoint use | **Executed here** `Savepoint_interactPrompt` 0x28da58 submits a localized prompt through `text_lookup` 0x173c84 and 0x19e854. `Savepoint_interact` 0x28dc30 requires `memcard_isBusy` 0x217518 and `menuMutex_isHeld` 0x22fc2c to return zero. Accepted use writes object +0x84=1 and +0xc4=1, calls `memcard_requestSave` 0x2175b4 for the player and dispatches object actions at 0x14dcc8. Busy/mutex controls call neither. **Observed** the shipped points have no action script. The requested screen is the memory-card save flow, not an NPC dialog; its successful card UI, disk write and pixels were not run here. | **Executed:** prompt and accepted/busy/mutex use cases wrote no byte of the constructed player record, including gold +0xe4; no fee is in this path. **Observed** `Savepoint_run` 0x28cdd0 can auto-save near living players when armed and allowed. A completed save changes save/card and point state, not a purchase or skill record. Actual card persistence is **Unknown** in this probe. |
| Savepoint resurrection | **Observed** `Savepoint_scanPlayers` 0x28d6dc checks nearby living players every eighth frame. With at least two players, a live teammate near the point, an active dead slot whose countdown is zero, and a suitable free spot, `Savepoint_run` 0x28d528–0x28d618 calls `player_respawn` 0x1bd040. This is automatic; no healer conversation, charge screen or resurrection menu appears in this path. | **Observed** `player_respawn` replaces the dead object, sets player-record HP +0xac to half of maximum +0xb0 in the normal campaign path, starts spawn protection and rebuilds the alive list. No gold, XP or item debit occurs in this branch (`t3/research-death-flow/docs/spec/player-death-flow.md` §2). The current probe does not execute the full point-to-respawn branch, so its live timing and placement remain **Unknown** here. |
| Mission map PushTrigger | **Observed/Executed separately** the record's ordered `key` is evaluated by `PushTrigger_prompt` 0x1eca94; eligible use reaches `PushTrigger_interact` 0x1ecc70 and the authored `action`. The fresh `hub` wrapper sets the entrance and calls `activateMissionMenu` 0x143fa8. `missionMenu_open` 0x231520 presents `MSEL.LMP`'s map, locked nodes, detail and selection; `t3/research-story-route` checks 26 state snapshots per seed and the row-zero story request for `blood1`. The alternate hub has the same object role and script import, but its full choice route was not replayed here. | **Observed** opening the map writes menu/task state, not HP, gold, XP or quest records. Confirming a selected destination writes `g_pendingLevel` 0x41b6d0 and orientation 0x41b720; later level loading carries the player record subject to act rules (`t3/research-quest-log` §4). No travel fee was found in this trigger path. Proximity/use through this specific disc object and full level transition are **Inferred** from separate checks. |
| Portal / JumpGate | **Observed/Executed in `t3/research-exits-walkin`:** `JumpGate_interactPrompt` 0x27d7a0 discovers the current level, requires more than one destination and nearby living party members, then `JumpGate_interact` 0x27d754 opens `JumpGate_openMenu` 0x27da24. The gate menu selects a known destination; its state-5 task at 0x27e1a8–0x27e218 writes the pending level. Both hub records are `Portal` objects, but this work does not run either as a constructed gate. | **Observed** discovery writes gate/list state; travel writes pending level/orientation and arrival placement, with no direct player-record price. No gold/XP/item debit is present in the documented gate path. Available destinations depend on persistent discovery and party state, so a menu appearing for a fresh character is **Unknown** without an integrated test. |
| Walk-in Trigger | **Observed** its rectangle calls an authored script that signals the portal object. `Trigger_run` 0x1ecf3c is a movement/occupancy path, while the `PushTrigger` above is use-button driven. It has no separate screen. | No player-record fee or change is established by this visual trigger. The full movement-through-rectangle path was not executed here. |

The common record is `g_players` 0x4d8af0, stride 0x4c30. Mission state is
five 13-byte difficulty rows beginning at +0x4bbf; quest pairs are eight
0x40-byte entries at +0x41d0 with count +0x43d0. Gold is +0xe4, current HP
+0xac and max HP +0xb0. The quest-variable table at 0x86da80 is separate
from the player record. These are **Observed** addresses from
`t3/research-quest-log` and `t3/research-death-flow`, not newly inferred
offsets. Vendor purchases and sales change gold and bags according to
`t3/research-vendors`; this report does not duplicate those price rules.

## 3. Ordered native port list

1. Load the selected `hub`/`hub2` archive and instantiate its exact five
   interactive records in object order. Keep the single NPC's shop flag and
   dialog script, and distinguish the portal, use trigger and walk-in visual
   trigger. Refuse a fabricated healer, stash or trainer service.
2. Wire `Player_interact`, prompts, facing/mutex gates and the message-driven
   dialog machine. Run the authored hub scripts and `.dbin` conditions/actions;
   persist quest variables, mission rows and journal entries in their
   documented owners. Verify later and alternate-hub choices through the
   actual dialog, including any deferred store branch.
3. Port Savepoint prompt/use, card-state gates, local save UI and auto-save.
   Then implement the co-op countdown/proximity resurrection, free-spot
   placement and `player_respawn` half-max-HP rule. Compare a two-player
   dead/alive original trace; the current use fixture alone cannot verify it.
4. Port PushTrigger key/action, the mission map's availability and input
   gates, and the direct pending-level write. Keep the separate walk-in
   Trigger as a portal visual signal. Compare an integrated NPC → trigger →
   map → level request in each hub state.
5. Port gate discovery, party-distance gate, travel menu, destination
   request and arrival placement. Compare point, dialog, map and gate UI
   frames with the original before claiming visual parity. Finally verify
   player-record survival, save persistence and co-op resurrection in a
   running native session.

## 4. Verification boundary

Run `difftest_hub_npcs.py --elf ELF --iso ISO` with
`PYTHONDONTWRITEBYTECODE=1`. It asserts the two private archive hashes,
all interactive indices and roles, exact script-call counts and associated
dialog sizes. On each seed it executes accepted Savepoint use and two
refusals against `ref_hub_npcs.py` with controlled card/mutex answers, plus
the prompt text/submission call sites: eight EE
cases, zero mismatches.
External card, UI, audio and action dispatch services are stubs, and a
synthetic player record is used. The script census includes mutually
exclusive code; it is not a gameplay route. Related dialog, vendor,
story-route, quest-log, exit and full-unit results are recorded separately
in the worktree's ignored validation log. No native implementation or
retail-rendered screenshots result from these checks.

**Serial background rerun with `PYTHONDONTWRITEBYTECODE=1`:** vendor 25
bounded checks; story route 26 mission-menu snapshots per seed; mission-map
art 39 draw and 20 input cases per seed; quest-log 14 page probes over two
seeds plus three disc scripts; dialog 10 suites per seed, zero failures;
exit/trigger/gate comparisons 598 per seed; full unit suite 652/652.
After the reference/prompt edits, the focused hub probe was rerun and passed
eight EE cases over both seeds with zero mismatches. These are separate
function-level checks; the co-op resurrection and native visual result remain
open. The log is `local/hub-npc-checks.log` in this worktree, ignored by Git.
