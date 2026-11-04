# Quest progression, quest page, and objective notices

US `SLUS_209.73` v2.00, 2026-10-23. This note joins the campaign state
research on `t3/research-quests` (`7efd3ce`), the script-effect research on
`t3/research-script` (`52984db`), and the hub/mission-map route on
`t3/research-story-route` (`76d4447`). `tools/difftest_quest_log.py` adds a
function-level comparison of the inventory quest page against the original
executable with `tools/ee_emu.py`, seeds 20973 and 7. The ELF is pinned by
SHA-256 in that test. It also asserts addressed mission-flow cells in the
three shipped `hub`, `strife` and `drundar` scripts directly from the disc.
`tools/difftest_quest_log_state.py` (2026-11-03) runs the original list
mutations, the page's text calls with a controlled wrap return, and the
player save/restore path on the same two seeds.
Disc files are read only; no game text or texture is stored here.

**Evidence boundary.** Addresses, records, script call sites and the texture
header are **Observed** in the executable or disc. UI calls and state probes
are **Executed** in `ee_emu.py` on constructed state. Texture lookup,
localization, font layout and GPU submission are stubbed for the new page
test: its coordinates are call arguments, not rendered pixel positions. The
mission 1 return branch is checked against shipped scripts, not played through.

## 1. Progression state and command path

The journal and the mission menu use different player-record data. In each
`g_players` record (`0x4d8af0`, stride `0x4c30`), active quest pairs occupy
`+0x41d0` as eight records of `0x40`: title key `[0x20]`, body key `[0x20]`;
count is `+0x43d0`. Mission bytes begin at `+0x4bbf` in five rows of 13,
indexed by `g_difficultyIdx` `0x4f719c`: bit 0 available, bit 1 complete.
Medals are at `+0x4c0d` (13 bytes). Quest variables are a separate packed
name/value table at `g_questVars` `0x86da80`. These addresses and mutations
were previously executed by `difftest_natives.py` and
`difftest_quests.py`; the relevant prior difftests were rerun for this note.

| Step | Original path | Effect and boundary |
|---|---|---|
| Gate | `getv` 0x143500, `getMissionAvailable` 0x1420fc, `getMissionComplete` 0x142084, item tests | A missing `getv` name is appended with value 0. Conditions choose a script branch; the call census alone does not select it. |
| Start/advance | `setv` 0x143540; `setMissionAvailable` 0x1420d0; `addQuest` 0x1433c8 → `quest_add` 0x1d386c | Variable values are signed bytes clamped to −128..127. Available writes mission bit 0. `quest_add` stores a title/body pair, up to eight; it stops the entire player loop at the first full list or duplicate title, so later players may not get the quest. |
| Turn in/complete | `removeQuest` 0x143448 → `quest_remove` 0x1d3968; `grantMission` 0x1420a4 → `mission_setComplete` 0x1bf770 | Remove shifts entries and lowers the count; duplicate titles can leave a placeholder behind. Complete sets bit 1 across all four player records. The journal does not retain a separate completed row: removal changes the active list while the mission bit records completion. |
| Reward | `grantBronze/Silver/Gold` 0x142164/0x142140/0x14211c; item and gold commands | Medal level rises only if lower; reward script entries run for each newly reached level. `givePlayerGold` splits by player count. Script `givePlayerExp` has zero calls in the 120-file census; combat experience follows `player_giveExp` 0x1d3150. Item creation/turn-in remains an integration boundary. |

**Observed disc census**, from `t3/research-quests/docs/quests.md` and
`docs/spec/script-builtins.md`: 43 `addQuest` calls in 20 files, 30
`removeQuest` in 19, 88 `setMissionAvailable` in 23, 33 `grantMission` in
32, 790 `getv`, 571 `setv`, and nine calls each to the three medal grants.
These count static calls, including mutually exclusive branches. Mission 0
starts available and complete. Mission-menu table row `i` is mission `i+1`,
so mission 0 has no selectable node.

The fresh hub route is a bounded example. **Executed previously** through the
shipped `hub` script at both seeds in `difftest_story_route.py`: `start`
sets mission 0 to available and complete. Either first dialog ending action
sets mission 1 available and adds one quest. The hub `PushTrigger` script
opens `missionMenu_open` 0x231520; a fresh story confirmation writes
`blood1` to `g_pendingLevel` 0x41b6d0. The trigger's physical use dispatch
and an integrated level load remain unverified. The mission menu uses its own
`MSEL.LMP` map, not the journal parchment; its 12 nodes, detail text, art,
locks and column gates are in `t3/research-story-route/docs/spec/mission-menu-art.md`.

## 2. Journal page: routing, art, entries, and states

**Executed, 14 controlled probes over two seeds.** The inventory panel
(`itemList_draw` 0x1cd208) reads page `panel+0x50`: page 3 calls
`stats_screen` 0x1d1db8 with mode 0 at 0x1cd578; page 4 calls it with
mode 1 at 0x1cd594; page 5 calls it with mode 2 at 0x1cd5cc. The prior
`docs/issues/live-rig.md` §18.4 identifies pages 0–2 as bags, 3 as stats,
4 as quests and 5 as skills, with L1/R1 changing page. The new test checks
the original calls for pages 3–5, then enters mode 1 with 0, 1, 2 and 8
synthetic quest pairs. It keeps both random seeds fixed and sees no write to
the quest list/count in this draw branch.

| Item | Executed call/record | Limit of this probe |
|---|---|---|
| Background | `res_find` 0x17365c at 0x1d263c asks for `inventry.lmp/parchment.tex`; `0x17fb68` at 0x1d2668 submits `(x=0, y=−4, size/index=104, layer=5, tint=0x80808080)` | Read-only disc header is **Observed** as 320×350. The third sprite argument's role and displayed crop are not established here. |
| Populated list | One batch per entry, then `text_end` 0x180500 at 0x1d278c. `text_begin` 0x1800b8 at 0x1d26ac passes `(the word at 0x4f7104, 6, 0x80323c3c, −1)`. `text_setClip` 0x1803e0 at 0x1d26d0 is `(0,119,320,440)`. `0x1802e0` is called at 0x1d26e8 with `(0x80323c3c, −1)` and at 0x1d2744 with `(0x802d2d2d, −1)`. Lookups stay title then body, in storage order | A fresh ELF has 0 at `0x4f7104`, so the first probe's font argument was 0. The state probe stores `0x11111111` and the call receives it. `t3/research-ui` `3e39392` `docs/formats/ui-fonts.md` lines 74–76 names that word as the gamefontsmall pointer. What `0x1802e0` stores is **Unknown**: the state probe stubs that callee. `text_setClip` still clamps to 640×447. |
| Text placement | `text_drawWrapped` 0x181280 at 0x1d272c and 0x1d2784. The third argument is the pointer returned by the preceding `text_lookup`. The older fixed tuple stored 0 there because that lookup was stubbed with return 0. The other immediates are `24`, then `288, 82, 418, 21` | Y starts at 114. Each wrap return is added to y before the next draw, and 22 is added after the body (`tools/ref_quest_log.py` lines 121–132, checked at `tools/difftest_quest_log_state.py` lines 291–320). A stub return of 0 is why title and body shared a row in the first probe. The integer a loaded font's wrap returns is still **Unknown**. |
| Empty list | `text_begin` at 0x1d27d0 with the same four arguments, lookup of `NoQuests` at 0x1d27dc, then `text_drawWideCentered` 0x181ca0 at 0x1d2800 with `(160, 224, lookup pointer, 1000000)`, then `text_end` at 0x1d2808 | No clip and no wrap on this branch. The localized words are not captured. |
| Completion | `removeQuest` changes the list; the page reads only its current count and title/body records | There is no completed style in this tested branch. The state probe draws stored titles `Q1` then `Q0`, and those same two rows when mission bit 1 is set. Mission completion remains in the mission bit and its menu art. |

The title/body fields are localization identifiers. The test uses synthetic
`Q0/B0` etc. and does not store or assert dialogue or translated quest prose.
It checks resource name and header size, not decoded texture pixels. The
function-level execution does not establish a retail screenshot or native
visual parity.

## 3. On-screen objective and notification text

The script and HUD paths are separate from the inventory quest page.
**Previously Executed**, with the script-effect difftest rerun here:

- `setInfo` 0x14318c (95 static calls in 25 scripts) looks up a key and
  calls `hud_showMessage` 0x1d92a0 with 180 frames, slot −1, force 0. A
  non-forced message is refused while the local menu is open; the HUD owns
  buffer 0x86ab78, timer 0x4f66e0 and force byte 0x4f66e2. The separate
  `t3/research-ui/docs/hud-dynamic.md` capture places the controlled one-line
  draw at `(320,78)` with a framed background. It is time limited.
- `addHelpMessage` 0x1431d8 (65 calls in 47 scripts) looks up title and body,
  then calls `hud_showHelpMessage` 0x1d9830. `addHelpMessageF` 0x143270
  (seven calls in three scripts) formats two looked-up keys with numbers and
  calls the same setter. The box state uses `g_helpMessageOpen` 0x41b928,
  title/body pointers 0x86aa64/0x86aa68 and close delay 0x4f66cc. The
  `help_task` 0x1dcc78 draw/dismiss path is a modal box. The prior UI capture
  records title `(324,100)`, wrapped body `(132,130)`, width 404 and line 21
  as draw API arguments. The new page probe did not rerun the help drawer.
- `showCompass` 0x1427b4 (three script calls) is another explicit script
  label/target path, gated by HUD, menu, camera and loading state. A quest
  entry by itself is not shown to invoke it. Which of these calls presents an
  objective during a real mission is **Unknown** until the corresponding
  script entry, HUD task and rendered frame are followed together.

## 4. Mission completion, hub return, and menu unlock

**Observed** in shipped script bytecode, with entry offsets, calls, argument
pushes and branch operands asserted by `check_mission_scripts` in
`tools/difftest_quest_log.py` (not a gameplay run): `strife` entry `exitzone` has
the demo-running path that calls
`grantMission(1)` at `0x1abc`, then `newWorld('hub')` at `0x1ae8` when its
counter passes 150 on the demo-running branch. `drundar` has the same pair
at `0x19ec`/`0x1a18`. Earlier `addHelpMessage` calls in those branches
provide a completion notice. A different branch requests `drunarm` or
`drunare`; the branch condition is material. `grantMission` alone does not
warp the player: `newWorld` 0x143dd0 calls `newWorld_netGate` 0x143d04 and,
when allowed, writes the requested level through `script_setNextWorld`
0x1472c4. Dialog-posted changes use `newWorldPost` 0x143cc4 and a later
dialog-end transfer instead.

On `hub` arrival, `game_getHubName` 0x1ec300 chooses `hub2` only when
record 0's current-difficulty evil and decision bits are both set and
mission 1 is complete; otherwise it returns `hub`. **Executed previously**
for difficulty and bit combinations by `difftest_quests.py`. The ordinary
mission 1 completion therefore does not by itself select `hub2`.
**Observed and asserted** `hub` script actions `setMissic270` at `0x07e4` and
`setMissid125` at `0x0830` each call `setMissionAvailable(2,1)`. That is a
separate action entry, so do not infer mission 2 is unlocked just from
the return to hub. If one of those entries runs and changes the mission byte,
mission-menu row 1 can brighten and be selected; `missionMenu_run` 0x2316fc
checks availability and writes the
chosen row's level pointer. The `t3/research-story-route` art difftest
separately verifies row tint and selection with forced mission bytes; those
fixtures do not prove that the hub action was reached through live dialog.

An act change (`mainloop_loadRequestedWorld` 0x320f8c–0x321020) clears
quest lists, flag-39 items and quest-variable values when its guards allow,
but keeps mission bytes and medals. `save_findAct` 0x217d30 treats `hub`
and `hub2` as the current act's prefix match where present, so a return to
the hub in the same act does not trigger that clear. `difftest_quests.py`
executed these helper rules; an end-to-end save/load and world transition is
still open.

## 5. Ordered native port and verification gate

1. Port the original script VM entry dispatch and quest-variable/mission-bit
   model before attaching UI. Preserve the per-difficulty row, read-created
   variables, and observed `quest_add`/`quest_remove` edge cases.
2. Connect dialog choices, trigger actions and item gates to the shipped
   quest commands. Keep title/body identifiers as localization keys. Preserve
   the asserted `exitzone` demo/counter branch and the two separate hub
   mission-2 actions. Execute a mission-1 turn-in and a mission-2 hub action
   on constructed state through their shipped entries; the addressed static
   checks alone do not establish either state change or live dialog reachability.
3. Load `inventry.lmp/parchment.tex` from the owned disc, validate its 320×350
   header and the page-4 routing. Submit the section 6 text calls, including
   the empty-state arguments and the y recurrence. The parchment crop and a
   loaded font's wrap return are still open, so do not claim pixel parity.
4. Port `setInfo`, `addHelpMessage/F` and `showCompass` as explicit script
   effects, with their menu, local-slot, timer and modal gates. Test the HUD
   draw and dismiss paths separately from the quest page.
5. Port the hub mission map's actual table, unlock, medal and evil gates,
   then its lockstep input and pending-level write. Keep the map separate
   from the quest list and verify mission 1's return plus the subsequent
   mission 2 hub action in an integrated session.
6. Keep the journal span in `savePlayer`/`restorePlayer` and in the player
   block of `save_build`/`save_load`, as section 6 measured. Apply act-change
   clearing only under the original guards. A device save, the stubbed act
   lookup, and a played campaign transition are still open.

Verification commands for this worktree (all with
`PYTHONDONTWRITEBYTECODE=1`) are `tools/difftest_quest_log_state.py` and
`tools/difftest_quest_log.py` with
`--elf` and `--iso` (including the three disc-script assertions); the prior
`difftest_quests.py`,
`difftest_script_effects.py`, `difftest_story_route.py` and
`difftest_mission_menu_art.py` checked out under ignored `local/prior-tests/`
from the named branches; `tools/difftest_natives.py` with seeds 20973 and
7; and `python3 -m unittest discover -s tools -p 'test_*.py'`. The two
route tests use the read-only ISO's `HUB.GOB` and `BLOOD1.GOB` extracted
only under ignored `local/story-route/`. The audit-fix logs are
`local/quest-log-fix-verification.log` and `local/quest-log-fix-hub-*.log`.
No original disassembly, script bytes, prose or texture bytes are tracked.

**Results, 2026-10-23 audit fix:** quest-page 14/14 controlled probes, now
asserting all four `text_begin` arguments for populated counts; three
disc-backed script checks assert the named entries, calls, arguments and
mission-1 branch operands. Quest model 7/7 properties; script effects
15/15 suites; story route 26/26 menu
snapshots per seed; mission-map art 39/39 draw and 20/20 input cases per
seed; native command quick probes 203/203 properties per seed. A separate
hub-only `difftest_natives.py --scripts local/story-route/scripts_raw
--quick -k hub.scr` run passed 3/3 properties at each seed, including all
82 shipped hub entry points; the general native quick run had skipped
shipped scripts because its default `scripts_raw/` was absent. The full
Python unit suite passed 652/652. These are function-level or static
fixture results, not an integrated quest playthrough.

## 6. List order, writers, text calls, and save

**Observed, Executed** on seeds 20973 and 7 by
`tools/difftest_quest_log_state.py` lines 138–232 and the model at
`tools/ref_quest_log.py` lines 73–118. Synthetic keys only.

| Transition | Original call | Result |
|---|---|---|
| Add | `quest_add` 0x1d386c `(title, text)` | Appends on each player in order. The call returns at the first player whose count is already 8 or whose stored title matches. A later separate call still runs. Each free title and body starts as `0x5a`; after a successful add, the bytes past the new terminator are still `0x5a` (lines 144–165). |
| Remove one | `quest_remove` 0x1d3968 | The matching entry is covered with the nine-byte `NoQuests` placeholder and the entries after it slide up by one `strcpy`. Count drops by one. |
| Remove duplicates | same | Every match is covered. Only the entries after the last match slide. Count still drops by one, so an earlier placeholder stays inside the visible count. Planted `A, B, A` becomes visible `NoQuests, B`. |
| Complete | `mission_setComplete` 0x1bf770 `(difficulty, mission, value)` | Does not read or write the quest span: all four spans are snapshotted, slot 3 starts as `0x3c`, and no recorded read or write falls in the span. Every mission byte starts at `0xf5`. Value −1 sets bit 1 and leaves the other bits (`0xf7`) on all four records; value 0 clears bit 1 and leaves the other bits. Mission 13, against that seeded table, writes nothing. The probe calls this function directly (lines 186–225). `grantMission` 0x1420a4 remains the script wrapper already recorded in `docs/spec/script-builtins.md`. |
| Clear | `quest_clearAll` 0x1d3adc | Covers each used entry of the first `g_numPlayers` records and stores count 0. A later record stays, including its count. |

The page then reads that stored order. Titles planted as `Q1`, `Q0` are
looked up in that order, not sorted. The same list with bit 1 set at
difficulty 1, mission 1 (byte `0xf7` on all four records) draws those two
rows and no extra row (lines 241–244, 255–257, and 320). The span compare at lines
278–279 is only the check that the draw does not write the list.

**Script events that write a journal entry.** The only script commands that
do are `addQuest` 0x1433c8 and `removeQuest` 0x143448. A disc walk in the
same file, lines 434–499, counts 43 `addQuest` calls in 20 files and 30
`removeQuest` calls in 19. Title keys are not stored. `strife` and `drundar`
`exitzone` contain `grantMission` and neither journal command. Hub actions
`setMissic270` and `setMissid125` call `setMissionAvailable` and neither
journal command. The hub entries that cover script offsets 0x1e68 and
0x1ee8 do contain `addQuest`. That static check does not re-run the dialog.

These audited runs already executed particular writers. They are not
repeated here:

- `t3/research-story-route` `76d4447` `docs/story-route.md` line 46: both
  hub actions at 0x1e68 and 0x1ee8 call `addQuest` and leave count 1.
- `t3/research-loading-readiness` `366b65a` `docs/loading-arrival-r4.md`
  lines 171–174: route ordinal 2 calls `0x1433c8` / `0x1d386c` when the
  completion bit is clear, including one add onto an empty list, and a full
  list stays at eight. The completion-set control omits that call.
- `t3/research-mission2-route` `b8e2d11` `docs/mission2.md` lines 57–60:
  the innovat1 turn-in removes the journal title. A later deferred task
  grants mission 2. This file only checks that `innovat1` contains both
  journal commands.
- `t3/research-mission-unlocks` `e5c6176` `docs/spec/mission-unlocks.md`
  lines 245–264: a direct `save_build` / `save_load` does not snapshot the
  mission-menu task registry. That run stubbed the player snapshot, so it
  does not say whether the journal span is in the image.

**Text call contract. Observed, Executed**, same probe, lines 235–322.
Resource, font, lookup, wrap, clip and GPU calls are stubbed. The page
passes the word at `0x4f7104` as the font (`docs/formats/ui-fonts.md` lines
74–76 on `t3/research-ui` `3e39392` names it gamefontsmall). One case stores
`0x11111111` and both the populated and empty `text_begin` receive it. The
page does not write that word back.

Populated entry, in order: `text_begin(font, 6, 0x80323c3c, −1)`,
`text_setClip(0, 119, 320, 440)`, `0x1802e0(0x80323c3c, −1)`, lookup of the
title, `text_drawWrapped(24, y, pointer, 288, 82, 418, 21)`,
`0x1802e0(0x802d2d2d, −1)`, lookup of the body, the same wrap at the updated
y, `text_end`. Y follows section 2. Empty count: `text_begin` at 0x1d27d0,
lookup of `NoQuests`, `text_drawWideCentered(160, 224, pointer, 1000000)`,
`text_end`. No clip and no wrap.

**Save and restore. Observed, Executed.**

- `savePlayer` `game_savePlayerRecord` 0x1ec720 copies the medal player's
  quest span to `save_playerCopy` for medal slots 0 and 1. The copy span is
  filled with `0xa5` before the call and matches the live span afterward,
  including the bytes past each terminator. `restorePlayer`
  `game_restorePlayerRecord` 0x1eb6f8 writes that span back over a live span
  filled with `0x5a`, so the title, the body, and those tail bytes all
  return. The live medal byte stays 4 after it was changed from 9. The other
  player's span is left alone. This compares the quest span, not the rest of
  the record. Lines 325–361.
- `save_build` 0x221914 and `save_load` 0x221d60, lines 364–396. Camera,
  jump gates, `save_findAct`, `save_getAct` 0x217edc, `save_setAct`, the
  level store, deferred-script clear and `vars_clearAll` are stubbed (lines
  60–64). Snapshot and fixup are not. The image's first player block holds
  the quest span and the planted mission byte. After `save_build`, the object
  pointer at +0x43d8 is still the pointer stored beforehand. It is seeded
  again, the live span is filled with `0x5a`, and `save_load` writes the
  saved span back and stores 0 at +0x43d8. This is not a memory-card device
  transfer, and the stubbed act lookup is not an act change.

**Still unknown.** The wrap return of a loaded font, so a multi-line body
position is not a measured pixel. The stores inside `0x1802e0`, which this
probe stubs. The parchment sprite's displayed crop. Which of the 43 `addQuest` sites a
played session reaches, beyond the three cited runs. Quest-variable
round-trip, because `vars_clearAll` was stubbed. Physical dialog, item
turn-in and arrival remain the limits named by those runs.

**A client can implement now:** append and remove with the duplicate
placeholder left visible; mission completion as bit 1 on every record
without deleting the line; act-change clear of the first `g_numPlayers`
lists; the page's call arguments, font word, empty-state position and y
recurrence; and the quest span across `savePlayer`/`restorePlayer` and the
player block of this bounded `save_build`/`save_load`. It still has to
refuse pixel parity, the parchment crop, and any claim that `grantMission`
or the mission-menu registry is the journal.

**Results, 2026-11-03 audit fix:** `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_quest_log_state.py --elf local/SLUS_209.73 --iso local/disc.iso` on the Mac mini passed 24 original cases across seeds 20973 and 7, and 73 journal script calls, in 0.25s. The 2026-10-23 page probe was rerun with stdlib `dis` preloaded and passed 14 probes, 3 disc scripts, parchment `(320, 350)`, in 0.10s; its assertions were not edited. `python3 -c` with stdlib `dis` preloaded, then `unittest` discover of `tools/test_*.py`, passed 657 tests in 4.728s. Logs: `local/quest-log-r2-fix-state.log`, `local/quest-log-r2-fix-page.log`, `local/quest-log-r2-fix-unittest.log`.
