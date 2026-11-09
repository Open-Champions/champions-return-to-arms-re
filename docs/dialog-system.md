# NPC dialog system: the general machinery missions 1–5 need

SLUS-20973 v2.00. Researched 2026-11-09 on `t3/research-dialog`, after `docs/dialog.md`
(334578d, same branch).

**Status.** This document fills the general machinery that the mission audits used but did
not run themselves: how a choice turns into script work (`callScript`, `postAction`,
`addDeferedCall`), what each of those entries can see when it runs, the order at the end of
a conversation, chained and duplicate ends, the input map (paging, confirm, the missing
cancel, held buttons), the default use and confirm buttons, and how pause and lockout
interact with an open dialog. Every **Executed** line below was run in `tools/ee_emu.py` by
`tools/difftest_dialog_system.py` against `tools/ref_dialog_system.py`. 6 suites, 0 failed
with seed 20973 and with seed 7 (section 11). Status words are those of `CONTRIBUTING.md`:
**Observed** (read at the address given), **Inferred**, **Unknown**, **Executed** (suite
named). Nothing here was run on a game, so nothing is "Ran".

The machine itself (open, node display, run task, messages 1–4, box, voice, census) is
`docs/dialog.md` on this branch. It is cited by line and not repeated. Other work cited by
commit and not redone:

| Commit | Branch, document | What it settles |
|---|---|---|
| 79a2e4a | `t3/research-dialog-gaps`, `docs/spec/dialog-gaps.md` | the camera swoop; the 24 other `dialog_isOpen` sites, including the pause menu and the start button (lines 143–185); the cursor glyph and the confirm and cancel masks by layout (lines 207–225) |
| 7b924e1 | `t3/research-mission-unlocks`, `docs/spec/mission-unlocks.md` | the ordinary hub's 31 node conditions and dialog priority (lines 35–84); first and second offer (lines 86–125); mission-menu lifetime and dialog admission (lines 127–232); mission 1 completion through `callScript`, `addDeferedCall` and `postAction` call lists (lines 279–472) |
| d17b46f | `t3/research-mission2-route`, `docs/mission2-route.md`, `docs/mission2-compose.md`, `docs/mission2-offer-hub.md` | mission 2's two level conversations, turn-in and deferred reward (`mission2-route.md` lines 78–130); the same-session offer, admission on the registered task, hub2's choices and trigger (`mission2-compose.md` lines 76–190); the offer state handed to the menu (`mission2-offer-hub.md` lines 14–81) |
| 28b3712 | `t3/research-story-route-r3`, `docs/story-route.md` | the hub's opening conversation and the first menu request (lines 40–58); mission 3's conversations whose choices only post an action (lines 408–446); mission 4's hub entries (lines 481–502); mission 5's nine-node conversation (lines 732–756) |

No game text is copied here. Conversations, entries and names in the tests are neutral ids
(`e3_1`, `npc`, `chain6`).

Contents: 1 what was run · 2 open and close · 3 node selection · 4 choices to actions ·
5 paging and input · 6 pause and lockout · 7 hub and hub2 offers · 8 missions 1–5 ·
9 what a client implements · 10 unknowns · 11 reproduction.

## 1. What was run

| Address | Function | Run as | Suite |
|---|---|---|---|
| 0x13db38 | `net_sendGameMsg`, offline branch | original; handler table 0x5d1498 planted | `send` |
| 0x143ee4 / 0x1eda9c | `postAction` / `script_setPostAction` | original | `queue`, `endchain` |
| 0x1edac0 | `script_runPostAction` | original | `queue`, `endchain` |
| 0x144160 / 0x1ed52c | `addDeferedCall` / `script_queueDeferred` | original | `queue`, `endchain` |
| 0x1ed5a0 | `script_runDeferred` (run task "Script", priority 125) | original | `queue`, `endchain` |
| 0x1eda08 / 0x1eda78 | `script_clearDeferred` / `script_resetState` | original | `queue` |
| 0x143158 | `callScript` | original | `queue` |
| 0x22ee2c | `dialog_onMsg` 0, 1, 3 (with `dialog_showNode` and the rest of `docs/dialog.md` §1) | original | `endchain`, `input`, `sametick` |
| 0x22ff48 | `dialog_runTask` | original | `input`, `sametick` |
| 0x143824 / 0x22fa50 | `startDialog` / `dialog_start` | original | `endchain` |
| 0x144010, 0x143cb0, 0x143cc4 | `activateStore`, `dialogRunning`, `newWorldPost` | original | `endchain` |
| 0x174410 / 0x174ce0 | `pad_apply` / `pad_decodeStick` | original, model `tools/ref_netwire.py` (unchanged) | `input` |
| 0x1e6238 | `config_setDefaults(-1)` | original, everything followed | `defaults` |

**Stubs (disclosed).** The rig is `difftest_dialog.Rig` (`tools/difftest_dialog.py` lines
101–531), with every callee outside the machine a recording stub. On top of it
(`tools/difftest_dialog_system.py` lines 85–179):

- `script_runByName` 0x1ed694 records each entry it is asked for, with the **sentinel**
  words the entry can see at that moment (menu mutex 0x4fe53c, `g_dialogData` 0x8e2d60 ≠ 0,
  `g_hudSuppressed` 0x4f66a8, pending store 0x4fdd30, in-post byte 0x4f8698, post-action
  name 0x86fa80, deferred counts 0x86da78 / 0x86da7c). It then plays a neutral program for
  that name by calling the **original** built-ins nested (lines 128–157). Missing names
  return −1, as the original does (`docs/script.md` 2.1).
- `net_sendGameMsg` records the bytes; offline it then calls `dialog_onMsg` at once, which
  is what the original's offline branch does (0x13db64–0x13db78; suite `send` runs that
  branch of the original). Online it holds the bytes until the test delivers them.
- `pad_apply` writes the raw pad the run task reads; the copy from `g_pads` to
  `g_rawPads` that `pad_readAll` makes (`docs/mainloop.md` line 257) is not run.
- `shop_openOrStock`, `mainloop_startFadeWait`, the camera and the stream are the dialog
  rig's recording stubs.

Fault checks: three wrong models (post action run before clearing its slot, no 64-name
limit, shop decided before the post action) were each caught by the suites listed against
them (local probe, not tracked).

## 2. Open and close

**Open** is `docs/dialog.md` §2 (lines 54–165): use button → `Creature_interact` takes the
menu mutex → `dialogScript` → `startDialog` → `dialog_start` sends message 0 from the
machine that owns the active player → every machine runs message 0. Added here:

- **Offline the open happens inside the use.** (Executed `send`, `sametick`.) Offline
  `net_sendGameMsg` calls the channel handler from the table at 0x5d1498 at once
  (0x13db64–0x13db78), so `dialog_onMsg(0)` runs inside `Player_run`'s interact
  (priority 10) and the dialog is open before the dialog run task (priority 110) runs in
  the same tick. In a net game the message lands `lead` frames later on every machine
  (`docs/netcode.md` line 468).
- `dialog_isOpen` 0x22fbc0 / `dialogRunning` 0x143cb0 is `g_dialogData` ≠ 0 (Executed in
  `docs/dialog.md`; here `endchain` records it from inside actions and post actions).

**Close** happens only through message 3 (`docs/dialog.md` §5.2, line 266). Added here
(Executed `endchain`, reference `tools/ref_dialog_system.py` lines 222–268):

1. A choice with next −1, or confirm on a node without visible choices, starts closing
   (fade). Each machine's run task then sends message 4 (swoop) or 3 (no swoop) once.
2. Message 3, in this order: free the lip-sync buffers, `g_hudSuppressed` = 0, **mutex =
   0**, `g_dialogData` = 0, camera mode, stop stream 1, focus to idle, unfreeze creatures,
   far clip, copy a `newWorldPost` name to the pending level 0x41b6d0 and orientation
   0x41b720 = 0xff, **then the post action** (0x22f7f0 → 0x1edac0), **then** the pending
   store test (byte 0x4fdd30) and the remote fade wait (byte 0x8e2ca0), both read after the
   post action returns.
3. **A second message 3 does nothing** when the dialog is already closed (the test of
   `g_dialogData` at the top of case 3). `endchain` sent a second copy 53 times over the two
   seeds. **But a late copy closes whatever dialog is open by then**: in 3 cases the post
   action had opened a new conversation and the copy closed it (`dup_closed_new`).
   **Inferred** (from the run task: every machine sends its own 3 once, `docs/dialog.md`
   line 248): in a net game one end produces one message 3 per machine, at frames that
   depend on each machine's fade. If a conversation opened by a post action (its message
   0 arrives `lead` frames later) is reached before the last copy, that copy closes it.
   No shipped post action opens a conversation (section 4.4), so this is a client rule, not
   a shipped behaviour.

## 3. Node selection

Settled; nothing new was run. The rule is `docs/dialog.md` §2.4 step 5 (lines 135–140) and
§4 step 5 (lines 213–217): the start node is the first node, in file order, whose condition
is non-empty and returns non-zero (a name the level script does not export returns −1, so
it counts as true); node 0 when none does. Visible choices are those whose condition is
empty or non-zero, computed once when the node is shown. A confirm does **not** re-test
the choice condition (`docs/mission2-route.md` on d17b46f, lines 122–128). On the shipped
hub file all 31 conditions were run with the original script machine (7b924e1,
`docs/spec/mission-unlocks.md` lines 35–84).

## 4. How choices map to actions

### 4.1 The action entry (Executed `endchain`)

Message 1 at end-of-text with visible choices: stop stream 1, then
`script_runByName(action)` of the selected choice, synchronously inside the message
handler (`docs/dialog.md` line 264). The sentinel recorded at every action entry is:
dialog **open**, mutex **held** (as `Creature_interact` left it), HUD **suppressed**, in-post
0. So, while an action runs:

| Built-in in an action | Effect | Status |
|---|---|---|
| `callScript(name)` 0x143158 | runs the named entry nested, now, and returns its result (−1 when missing); its own built-ins behave as in this table | Executed `queue` |
| `postAction(name)` 0x143ee4 | copies the name to the slot 0x86fa80 (a second call replaces the first); nothing runs yet; returns 0 | Executed `queue`, `endchain` |
| `addDeferedCall(name)` 0x144160 | appends to the back half of the queue (4.3); returns 0 | Executed `queue`, `endchain` |
| `activateStore(i)` 0x144010 | stores the index, sets the pending byte; the shop opens at message 3 | Executed `endchain` (and `docs/dialog.md` 6.1) |
| `newWorldPost(name)` 0x143cc4 | the name is copied to the pending level at message 3 | Executed `endchain` |
| `startDialog(…)` 0x143824 | loads the level lump, then `dialog_start` does `Camera_update` and `g_swoopDone` = 0 and sends nothing while a dialog is open | Executed `endchain` |
| `dialogRunning()` 0x143cb0 | 1 | Executed `endchain` |
| `activateMissionMenu`, `showBust`, `showCompass`, `trigger` of a talker | refused or no effect while open | `docs/dialog.md` 6.1 (lines 298–326) |

The next node is then shown (its choice conditions run, in order) or closing starts.

### 4.2 The post action (Executed `queue`, `endchain`)

`script_runPostAction` 0x1edac0: if the slot is non-empty, copy it to the stack, **clear
the slot**, set the in-post byte 0x4f8698 = 1, run the copy, clear the byte. Reference
`tools/ref_dialog_system.py` lines 67–80. Consequences, all Executed:

- Only the last `postAction` of a conversation runs, once, at message 3. A post action set
  by an action on an earlier node survives node changes.
- A `postAction` made by the post action itself is kept for the next caller of
  `script_runPostAction` (cutscene end, a help box, the next level load or the next
  dialog end, `docs/script.md` 2.5), not run now. `endchain` ran 107 post actions over
  the two seeds; in `queue`, 66 entries started while the in-post byte was 1 (post
  actions and what they called), and a post set during them was compared afterwards.
- What the post action sees (sentinel at its entry): dialog **closed**, mutex **free**, HUD
  **not suppressed**, the `newWorldPost` level **already pending** (26 post actions; directed cases at
  `tools/difftest_dialog_system.py` lines 353–357 and 414–415), the deferred shop **not
  yet opened**, in-post 1. So `activateStore` in a post action opens the shop at once
  (the closed branch of `activateStore`, `tools/ref_dialog.py` lines 952–966), and
  `startDialog` in a post action can open a new conversation.

### 4.3 Deferred calls (Executed `queue`, `endchain`)

`script_queueDeferred` 0x1ed52c writes the name into the back half ((flip & 1) ^ 1) of
0x86b278 (2 × 64 × 0x50 bytes) at index `queued` (0x86da7c) and increments it; a name past
the 64th of a frame is dropped without notice and without counting (1,346 drops over the
two seeds). `script_runDeferred` 0x1ed5a0 runs the front half 0 … `run_count` − 1 (0x86da78)
in order, re-reading the count and the parity after every name, then flip += 1,
`run_count` = `queued`, `queued` = 0. Reference lines 82–102. So:

- A name queued by a choice action (message phase of frame N) runs in the Script task of
  frame N + 1. One queued by a deferred entry runs one frame later again.
- A deferred entry that clears the queue (`script_clearDeferred`, as a level teardown does)
  stops the loop at once; the flip still advances.
- **A deferred entry queued by the closing choice runs with the dialog still open** when
  the next Script task comes before message 3. Executed: in the directed cases
  (`tools/difftest_dialog_system.py` lines 348–352 and 412–413: closing choice, two
  frames, then message 3) the reward ran with the dialog open, mutex held, HUD suppressed,
  and its `activateStore` was deferred to message 3; over the two seeds 26 deferred entries
  ran with the dialog open and 2 with it closed. Inferred: closing waits for the UI fade
  (and, with a swoop, the camera move) before message 3 is sent, so this is the normal
  case. (Inferred for the
  shipped data: mission 2's turn-in queues its reward this way, `docs/mission2-route.md`
  line 120; the reward entry therefore runs under the 6.1 gates of `docs/dialog.md`.)

### 4.4 A post action that opens a conversation

Executed (`endchain`, directed cases at `tools/difftest_dialog_system.py` lines 341–347 and 410–411):

- **Offline** the new conversation opens **inside** message 3, before the shop test: the
  open clears the pending-store byte, so a shop asked for in the first conversation is
  **dropped** (27 times over the two seeds: `shops_lost`), and the remote flag read after it is the new
  conversation's. The new conversation runs **without the menu mutex** (message 0 does not
  take it; only `Creature_interact` does).
- **Net** the message 0 waits; message 3 finishes first and opens the shop; the open
  arrives later and calls `net_closeLocalMenus(0)` (`docs/dialog.md` line 132). Whether that
  closes the open shop is **Inferred** (not run).
- **Shipped data:** no condition, action or post action on the disc reaches `startDialog`
  (`docs/dialog.md` line 344, the census of `tools/dialog_census.py`). Chaining is not
  reachable as shipped. A client may refuse it, or reproduce the rules above.

## 5. Text paging, confirm and cancel

Paging is `docs/dialog.md` §5.1 step 8 and §5.2 type 1 (lines 249–252, 264): with the text
option on, a page of 76 waits for a confirm ("more"), scrolls 5 per tick, and confirm first
finishes the typewriter. Added here (Executed `input`, `sametick`, `defaults`):

- **The run task reads the pressed word, not the held one.** It reads 0x4028dc + 0x58 ×
  slot, which is `g_rawPads` +0x0c, and `pad_apply` 0x174410 writes there `buttons &
  ~previous` (with the stick turned into bits 0x100000 up, 0x200000 down at ±0.8). Holding a
  button for 2–30 ticks gave **exactly one** message per press for confirm, d-pad up/down
  and stick up/down; auto-repeat (+0x10) is never read, so a held direction moves the
  cursor once.
- **Map** (`tools/ref_dialog_system.py` lines 272–287): up 0x101000 → message 2 (−1), down
  0x204000 → message 2 (+1), both only with the cursor blend at 1.0; `g_btnConfirmMask`
  0x41bfbc → message 1. **Nothing else sends anything**: cancel (0x120 as the executable
  starts, 0x20 / 0x140 by layout), start, select, triangle, the shoulders, left/right and the
  default use button were run and sent no message.
- **No cancel, no lockout.** In 0x22ec9c–0x231078 the only read of the button words is the
  confirm mask at 0x2303d0; there is no read of `g_btnCancelMask` 0x41bfb8 or of
  `g_menuInputLockout` 0x41b4fc (Observed, scan of the disassembly). A conversation can
  only be left by a choice with next −1 or a node without choices.
- **Default buttons** (Executed `defaults`): `config_setDefaults(-1)` writes 0x80 as every
  slot's use word (options +0x40 + 0x24 × slot; `game_addCoreTasks` copies those rows into
  `g_btnUse` 0x41b9c0, Observed 0x1e6d58–0x1e6df8). The executable starts with confirm
  0x40, cancel 0x120 and layout byte 1. So the use button is not the confirm button in
  either layout (confirm 0x40 or 0x20).
- **The same tick as the open** (Executed `sametick`, offline): with no swoop, the run
  task reads the pad in the tick the use opened the dialog. The use button alone (0x80)
  sends nothing; confirm pressed in that same tick (0x40, alone or with 0x80) sends message
  1, which finishes the typewriter at once (26 of 26 over the two seeds). With a swoop the camera
  step returns first and nothing is read (40 of 40).

## 6. Pause and lockout

| Interaction | Rule | Status |
|---|---|---|
| Pause menu running | the run task's pad is 0 (`task_isRunning("pauseMenu")`) | Executed, `docs/dialog.md` line 235 |
| Start button while a dialog is open | offline the pause menu cannot open (an open one can still close); online there is no such test | Executed, `docs/spec/dialog-gaps.md` (79a2e4a) line 159 |
| Run tasks while paused | the run task and the Script task are not skipped while paused (`tasks_call(1, −1)` filters only draw tasks), so the typewriter, scroll and deferred calls go on | Inferred from `docs/script.md` 2.6 (0x19e798) |
| `g_menuInputLockout` 0x41b4fc | not read by the dialog machine (5); it gates `Player_run`, which `dialog_isOpen` already gates | Observed (scan); `docs/spec/player-tick.md` step 4 |
| Recall or mission menu at message 0 | the open is refused and the mutex released | Executed, `docs/dialog.md` lines 128–131 |
| Mission menu while open | `activateMissionMenu` refused | Executed, `docs/dialog.md` line 321 |
| Mission menu just cancelled | the dialog asks the registered task, not the menu state; a menu at counter 0 still blocks | Executed, 7b924e1 lines 141–188, d17b46f `mission2-compose.md` lines 102–122 |
| Inventory | `menu_openInventory` takes the same mutex: open inventory blocks talking; a chained conversation (4.4) has no mutex | Observed `docs/dialog.md` line 95; Executed 4.4 |
| Pause entries, recall, spell selector, HUD inputs, camera control | gated while open | Executed, 79a2e4a lines 143–185 |

## 7. How the hub and hub2 offers use it

Nothing below was re-run; the column says where it was.

| Offer | What the dialog machine does | Where |
|---|---|---|
| Ordinary hub, first offer | node conditions select the unavailable branch; two confirms with unconditioned choices walk three nodes; either ending action makes mission 1 available and adds a quest; message 3 closes | 7b924e1 lines 86–94; 28b3712 lines 40–58 |
| Ordinary hub, later offers | dialog priority from the 31 conditions; each offer action writes one availability bit; some also call `activateStore` (deferred to message 3) | 7b924e1 lines 95–125 |
| Ordinary hub, after the offer | message 3 closes, mutex free; then a trigger (not the dialog) opens the mission menu, which the dialog cannot open (`activateMissionMenu` refused while open) | d17b46f `mission2-compose.md` lines 76–96 |
| Admission | a talk during a registered mission menu (even at counter 0) is refused at message 0 | d17b46f `mission2-compose.md` lines 102–122 |
| hub2 | one NPC; the selector follows mission 2's byte; choices call `mission_setAvailable` for missions 2 and 3, or `changeSwoop` + `activateStore` and stay on the node | d17b46f `mission2-compose.md` lines 124–156 |
| hub2 trigger | `callScript` into a gate entry; then `setEntrance` + `activateMissionMenu`, or a help message + `addDeferedCall` | d17b46f `mission2-compose.md` lines 157–190 |
| Later hub nodes (missions 4 and up) | entries that set mission 4's bit, some with `addQuest`; which node reaches them was not run | 28b3712 lines 481–502 |

## 8. Missions 1–5: what their conversations need from the machine

| Mission | Conversation use | Machinery (this document) |
|---|---|---|
| 1 | hub offer (7); completion runs through `callScript`, `addDeferedCall` and `postAction` outside dialogs (7b924e1 lines 279–472) | 4.1–4.3 |
| 2 | two level conversations: offer, then turn-in that removes items, removes the quest and queues the reward (`addDeferedCall`) | 4.1, 4.3 (reward runs next frame, usually with the box still open) |
| 3 | a three-node conversation whose action sets a variable and adds a quest; a two-node conversation whose four choices only `postAction` a travel entry (28b3712 lines 408–446) | 4.2: the travel entry runs at message 3, after the close, with the dialog closed and the mutex free |
| 4 | hub entries that set mission 4's bit (28b3712 lines 481–502) | 4.1 |
| 5 | a nine-node conversation, conditions on alignment and three variables, an action that adds a quest, a last node whose action is a `callScript` (28b3712 lines 732–756) | 3, 4.1 (`callScript` nested, now) |

The audits above ran the condition and action entries, not `dialog_onMsg` on those files.
With sections 3–5 the client has every rule needed to walk them.

## 9. What a client implements (in order)

1. **Deliver offline messages at once** and net messages in the message phase; open on
   message 0 only, close on message 3 only, and ignore a 3 when nothing is open (2).
2. **Start node and visible choices** exactly as section 3; never re-test a choice at
   confirm.
3. **Run the choice action synchronously** in the message phase with the dialog open, the
   mutex held and the HUD suppressed (4.1).
4. **One post-action slot**: `postAction` overwrites; message 3 copies, clears, sets
   in-post, runs; a post set during the run is kept (4.2).
5. **Message 3 order**: HUD, mutex, dialog closed, camera, stream, unfreeze, pending level
   from `newWorldPost`, post action, then the pending shop and the remote wait (2).
6. **Deferred queue**: two halves of 64; drop the 65th silently; run next frame in the
   Script task (priority 125), re-reading count and parity per entry (4.3). Expect a
   reward queued by the last choice to run while the box is still open.
7. **`callScript`**: nested, synchronous, returns the entry's value or −1 (4.1).
8. **Input**: read newly pressed buttons only; up/down (d-pad and stick at ±0.8) move once
   per press when the blend is 1.0; confirm finishes the typewriter, pages "more", or
   chooses; no cancel, no lockout, no auto-repeat (5). Use 0x80 and confirm 0x40 (layout
   1) by default.
9. **Gates**: pause menu zeroes the dialog pad; offline no pause while open; refuse open
   during recall or a registered mission menu; refuse `activateMissionMenu`, defer
   `activateStore` while open (6).
10. **Chaining** (not on the disc): refuse a `startDialog` from a post action, or reproduce
    4.4 (offline: opens inside message 3, drops the pending shop, no mutex; net: the late
    message 3 copies close it).

## 10. Unknown

- Whether `net_closeLocalMenus(0)` in a chained net open closes a shop the end just opened
  (4.4). Running message 0 with that callee real would settle it.
- The frames at which each machine's message 3 lands in a net game (they depend on each
  machine's UI fade, `g_uiFadeIn` 0x506070); a two-machine run would settle whether the
  duplicate-end hazard of section 2 can happen with shipped data (it needs a chained open,
  which the disc does not have).
- Whether the options screen can remap the use button onto the confirm button (only the
  defaults were run, section 5). If it can, the use press would also confirm in a no-swoop
  open.
- `pad_readAll`'s copy from `g_pads` to `g_rawPads` was not run; the input suite writes the
  raw pad with `pad_apply` directly.
- No run on a game.

## 11. Reproduction

Needs your own US v2.00 `SLUS_209.73` in `local/`. Run single-process; `tools/dis.py`
shadows the standard `dis`, so the unit tests preload it.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog_system.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog_system.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis, unittest, sys; sys.path.append("tools"); import test_ref_dialog_system as t; unittest.main(module=t, argv=["t"])'
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_dialog.py local/SLUS_209.73 --seed 7
```

Results after the last code edit (40 cases per suite for the new difftest, 60 for the old):

| Command | Seed 20973 | Seed 7 |
|---|---|---|
| `difftest_dialog_system.py` | 6 suites, 0 failed | 6 suites, 0 failed |
| `difftest_dialog.py` (unchanged, regression) | 10 suites, 0 failed | 10 suites, 0 failed |
| unit tests (`test_ref_dialog_system`, `test_ref_dialog`, `test_dialog_census`) | 61 run, OK | (no seed) |
