# Quest progression, quest page, and objective notices

US `SLUS_209.73` v2.00, 2026-10-23. This note joins the campaign state
research on `t3/research-quests` (`7efd3ce`), the script-effect research on
`t3/research-script` (`52984db`), and the hub/mission-map route on
`t3/research-story-route` (`76d4447`). `tools/difftest_quest_log.py` adds a
function-level comparison of the inventory quest page against the original
executable with `tools/ee_emu.py`, seeds 20973 and 7. The ELF is pinned by
SHA-256 in that test. It also asserts addressed mission-flow cells in the
three shipped `hub`, `strife` and `drundar` scripts directly from the disc.
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
| Populated list | Each of count 1, 2 and 8 issues `text_begin` 0x1800b8 with `(font=0, second argument=6, colour=0x80323c3c, fourth=−1)` and `text_setClip` 0x1803e0 with `(0,119,320,440)`; `text_lookup` 0x173c84 sees each title then body key in stored order | The four `text_begin` arguments are asserted on constructed state; font resource 0 is not a loaded-font capture. The second argument is not named in `symbols/engine.tsv`. `text_setClip` clamps its rectangle to 640×447, so the requested bottom 440 is within bounds. |
| Text placement | `0x181280` at 0x1d272c and 0x1d2784 each receive `(24, 114+22i, 0, 288, 82, 418, 21)` for row `i` when font calls return the test's stub value | Both calls share the same controlled y because font measurement and localization are stubbed. Actual body position, wrapping and glyph dimensions need a real font/layout capture. |
| Empty list | No entry text calls; lookup at 0x1d27dc requests the short key `NoQuests` | The localized words and their draw result are not captured. |
| Completion | `removeQuest` changes the list; the page reads only its current count and title/body records | There is no completed style in this tested branch. Mission completion remains in the mission bit and its menu art. |

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
   header and the page-4 routing. Draw current entries and `NoQuests` through
   the same font/localization path. Compare text layout with real glyph
   metrics and a rendered original frame before claiming visual parity.
4. Port `setInfo`, `addHelpMessage/F` and `showCompass` as explicit script
   effects, with their menu, local-slot, timer and modal gates. Test the HUD
   draw and dismiss paths separately from the quest page.
5. Port the hub mission map's actual table, unlock, medal and evil gates,
   then its lockstep input and pending-level write. Keep the map separate
   from the quest list and verify mission 1's return plus the subsequent
   mission 2 hub action in an integrated session.
6. Preserve mission/quest state through same-act level changes and saves;
   apply act-change clearing only under the original guards. Verify a real
   campaign transition, including player input, dialog, game code, art and
   saved state. Function-level probes alone do not close that gate.

Verification commands for this worktree (all with
`PYTHONDONTWRITEBYTECODE=1`) are the new `tools/difftest_quest_log.py` with
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
