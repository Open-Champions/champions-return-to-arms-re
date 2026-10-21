# NPC dialog: how a conversation starts, runs, ends and what it changes

SLUS-20973 v2.00. Researched 2026-10-21 on `t3/research-dialog`.

**Status.** The whole NPC dialog machine is documented and **Executed**: every function
listed in section 1 ran in `tools/ee_emu.py` against `tools/ref_dialog.py`
(`tools/difftest_dialog.py`, 10 suites, seeds 20973 and 7, 0 failed). The shipped data was
counted with `tools/dialog_census.py` (section 10). Nothing here was run on a game, so
nothing is "Ran". Status words are those of `CONTRIBUTING.md`: **O** observed at the
address given, **I** inferred, **U** unknown, **E** executed (the test is named).

**2026-10-21, `t3/research-dialog-gaps`:** the camera functions, the 24 remaining
`dialog_isOpen` checks, the box where `box.tex` is not loaded, the cursor glyph and the
`TestLocation` talkers are executed in [spec/dialog-gaps.md](spec/dialog-gaps.md); the
sections below point there where it corrects them.

Companions: [reference](../tools/ref_dialog.py), [synthetic tests](../tools/test_ref_dialog.py)
(no game file needed), [difftest](../tools/difftest_dialog.py), [census](../tools/dialog_census.py).
Earlier notes this document builds on and corrects: `docs/audio-save.md` ("Player
selection, dialog, mission menu" and A2), `docs/formats/anim-audio.md` 4.2–4.3,
`docs/script.md` (rows 9, 10, 11, 15–18 and P5), `docs/monsters-2.md` (NPC class),
`docs/spec/player-tick.md` step 4. Quest and mission state: `docs/quests.md` on
`t3/research-quests`. UI conventions (640 × 448 arguments, layers, text calls):
`docs/hud-dynamic.md`, `docs/formats/ui-fonts.md`, `docs/formats/ui-text.md` on
`t3/research-ui`.

Contents: 1 functions · 2 how a dialog starts · 3 the file · 4 showing a node · 5 how it
advances · 6 what it changes · 7 the box on screen · 8 input · 9 seeds, lockstep, save ·
10 disc census · 11 what the native client needs, in order · 12 open questions.

## 1. The functions

| Address | Name | Kind | What it does | Status |
|---|---|---|---|---|
| 0x1b2640 | `Player_interact` | simulation, priority 10 | nearest interactable object, its prompt, the use button | O |
| 0x116d50 | `Creature_interactPrompt` | creature slot 13 | `TalkTo` / `CannotTalk` / `UpToShop` prompt | O |
| 0x116bd8 | `Creature_interact` | creature slot 14 | takes the menu mutex, runs `dialogScript` | E `interact` |
| 0x11a5f0 | `Creature_trigger` | creature slot 3 | script `trigger(name, v)` on a talker | E `interact` |
| 0x22fc04 / 0x22fc2c / 0x22fc38 | `menuMutex_tryAcquire` / `_isHeld` / `_release` | | the word 0x4fe53c | E |
| 0x143824 | `script_startDialog` | built-in 15 | loads `<level>.lmp`, calls `dialog_start` | E `builtins` |
| 0x22fa50 | `dialog_start` | | the owner of the active player sends game message 0 | E `message` |
| 0x22ee2c | `dialog_onMsg` | game-message handler, channel at 0x8e2e94 | types 0 open, 1 confirm, 2 move, 3 end, 4 leave | E `open`, `messages`, `sequence` |
| 0x230c74 | `dialog_showNode` | | text, visible choices, layout, voice | E `open` |
| 0x22ec9c | `dialog_queueLineAudio` | | voice on stream 1, lip-sync read | E `open` |
| 0x22ff48 | `dialog_runTask` | run task "Dialog Demon Run", priority 110 | camera, voice, pad → messages, scroll, typewriter | E `tick` |
| 0x230628 | `dialog_drawTask` | draw task "Dialog Demon Draw", priority 110 | the box | E `draw` |
| 0x22fc70 / 0x22fdd8 | `dialog_startTalkAnim` / `dialog_syncMouth` | | speaker's mouth | E `mouth` |
| 0x22f99c | `dialog_free` | `game_clearLevel` 0x1e50c8 | reset at level teardown | E `free` |
| 0x22f910 | `dialog_loadBox` | `game_loadLevel` 0x1e617c | `box.tex` of `dlgbox.lmp` | O |
| 0x22fbc0 / 0x143cb0 | `dialog_isOpen` / `dialogRunning` | | `g_dialogData` 0x8e2d60 ≠ 0 | E |
| 0x1438b0 / 0x1438c4 / 0x143cc4 / 0x1471dc | `changeSwoop` / `startWithSwoopDone` / `newWorldPost` / `forceMutexRelease` | built-ins | words the machine reads | E `builtins` |
| 0x144010 / 0x143fa8 | `activateStore` / `activateMissionMenu` | built-ins | deferred / refused while open | E `builtins` |
| 0x22fc44 | (unnamed) | | `prompt_shown && n == prompt_node`; **no caller found** (no `jal`, no stored pointer) | O |

The pointer 0x22ee2c reaches `net_registerMsgHandler` from `dialog_registerMsgHandler`
0x22f974 (startup 0x323e60); the two tasks are added by `dialog_addTasks` 0x22f8bc
(startup 0x323ec4), which also clears `g_dialogData`.

## 2. How a dialog starts

### 2.1 The player uses the NPC (O)

`Player_run` reaches `Player_interact(P, pad, 0)` only when the game is not paused, there is
no menu input lockout, **no dialog is open**, and the spell selector is not held
(`docs/spec/player-tick.md` step 4). `Player_interact`:

1. collects objects in the box ±48 units in x and y, from the player's height to 60 above
   (`world_collectObjectsInBox`, up to 256), keeps those with flag 0x100000
   (interactable) and picks the nearest by squared distance;
2. asks its slot 13 for a prompt. A creature's prompt (`Creature_interactPrompt`) needs a
   display name (+0x368) and a player object, and refuses some flag combinations (0xc00000
   at +0xa8; a dead `MummyKing`). With property `shop` and
   `net_anyAlivePlayerFlag800000()` it says `UpToShop` (button kind 1). Otherwise the player
   must be inside the cone: the dot product of the normalised offset with the NPC's facing
   must exceed `talkCone` (property, float, default 0.5). Then it looks for a hostile
   creature within ±180 of the NPC (flag 0x20 with +0x312 = 0 and not bit 26 of +0xa8,
   skipping dead 0x8, 0x40 and friendly 0x1000000 objects): if there is one the prompt is
   `CannotTalk` (kind 0, no use); else `TalkTo` followed by a space and the looked-up display
   name (kind 1);
3. kind 1 uses the button mask `g_btnUse[slot]`, kind 2 uses 0x10. When the pad word at
   +0xc has the bit: `g_scriptActivePlayer` = slot, then slot 14 (`Creature_interact`).

### 2.2 `Creature_interact` (E `interact`)

Needs a display name and a player object for the slot. With `shop` non-zero **and**
`net_anyAlivePlayerFlag800000()`: opens the shop for that slot if it is local, and stops.
Otherwise: the unnormalised facing test `(px − ox)·cos16(facing) + (py − oy)·sin16(facing) > 0`,
then `menuMutex_tryAcquire()`. On success `g_scriptActivePlayer` = slot and
`script_runByName(dialogScript)`.

- The mutex is taken **before** the script runs and the script is expected to open a
  dialog (which releases it at the end) or call `forceMutexRelease`. If the object has no
  `dialogScript`, `script_runByName(0)` returns −1 and **the mutex stays held** until a
  dialog end, `forceMutexRelease`, an inventory close (offline, 0x1c52b0) or the level's
  `dialog_free`. On the disc 5 objects have `showName` without `dialogScript` and without
  `shop` (section 10).
- `Creature_trigger` (script `trigger(name, v)` reaching a creature's slot 3) needs a display
  name and a `dialogScript` and the mutex; it does **not** set the active player.
- `JumpGate_interact` and `Savepoint_interact` test `menuMutex_isHeld` (0x27d760, 0x28dc54);
  `menu_openInventory` takes the mutex too (0x1c1608), so an open inventory blocks talking.

### 2.3 `startDialog(name, a, b)` (E `message`, `builtins`)

Every `dialogScript` entry on the disc reaches `startDialog` (28 of 28). The built-in formats
`<name>.dbin` into a buffer nothing reads, loads `<level>.lmp` (the level name at 0x41b721;
blocking when not resident) and calls `dialog_start(name, a, b)`:

1. `Camera_update(local camera)`; `g_swoopDone` 0x4fdce8 = 0;
2. only if `net_isLocalSlot(g_scriptActivePlayer)` and no dialog is open: send game message 0.

Message 0 (`ref_dialog.start_message`):

| Bytes | Content |
|---|---|
| 0 | 0 |
| 1 | name length (s8; the handler copies nothing for a negative value) |
| 2 … | name, no terminator, then 0xff up to the next multiple of 4 from the message start |
| +0 | the sender's `g_scriptActivePlayer` (byte) |
| +1, +2 | `a`, `b` (bytes) |
| +3 | 0 |
| +4 … +0xf | `g_cameraPos` 0x44f038–0x44f040, the sender's camera position (three raw floats) |
| +0x10, +0x12 | the sender's camera yaw (0x207450) and pitch (`Camera_getPitch`), s16 |

`a` is the **swoop** flag (0x4fdce4; `changeSwoop` writes the same word): when non-zero the
camera moves to a conversation view and back. `b` is passed to `Camera_setupDialogView` as
its third argument (which side of the NPC; stored at 0x8e2cc4 and read by nothing else).
The disc uses (a, b) = (1, 0) 30 times, (0, 0) 11, (1, 1) 4.

### 2.4 Opening on every machine: message 0 (E `open`)

In this order:

1. **Refusal.** If `g_recallCountdown` 0x41b51d ≠ 0 or the task `missionmenurun` is running:
   `menuMutex_release()` and nothing else. (So a talk request during the mission menu or a
   recall is dropped, and the mutex taken in 2.2 is given back.) There is **no** test of an
   already open dialog here.
2. `net_closeLocalMenus(0)`.
3. Camera: `Camera_pushState`, set yaw and pitch from the message, `Camera_apply(cam, 0,
   x, y, z)` with the sender's position — every machine takes the sender's view.
4. `lump_findEntry(lump_load("<level>.lmp"), "<name>.dbin")`; its data is the file.
5. **Start node**: the first node whose condition is not empty and whose entry returns
   non-zero; node 0 when none does. Conditions run in node order (node 0's too) and the
   search stops at the first acceptance. `script_runByName` returns **−1 for a name the
   level script does not export**, so a missing condition entry counts as true. The
   lookup is a case-sensitive binary search of the export table (`scr_findEntry` 0x13eac8).
6. **Speaker object.** If the player byte in the message is a valid slot with an object:
   the nearest of `world_findObjectsByName(name, …, 100)` to that object (3D distance,
   strictly nearer replaces, first wins ties). Otherwise `world_findObjectByName(name)`.
   No object at all makes the original read address 0xc (the reference refuses).
7. If the speaker has flag 0x20: focus = the speaker (`dialog_setFocusObj`, which stores
   only while no dialog is open), focus word = speaker + 0x3c8 for class `NPC`, else the
   word `*(speaker + 0x24)`. Idle animation of the focus: role `dialogidle`, else `idle`
   (`obj_findRoleAnim`) → 0x4fdccc.
8. Display name: `text_lookup(showName property)` copied to 0x8e2d68, its length to 0x8e2cdc.
9. `creatures_freezeAll()`; clear the text buffer; file pointer 0x8e2d5c;
   `g_hudSuppressed` 0x4f66a8 = 1; typewriter on; `newWorldPost` buffer 0x4fdcf0 = "";
   drawn-once 0x8e2cd4 = 0; closing 0x8e2cd8 = 0; swoop and side from the message; end-sent
   0x8e2ce0 = 0; pending store 0x4fdd30 = 0.
10. Two lip-sync buffers of the size of the largest `<voice>.anm` stream entry over **all**
    nodes of the file, rounded up to 0x800 (`mem_allocTagged`).
11. `dialog_showNode(start)` (section 4).
12. remote 0x8e2ca0 = `!net_isLocalSlot(g_scriptActivePlayer)`; if remote,
    `mainloop_startFadeWait(20)`.
13. If swoop: `Camera_setupDialogView(cam, focus, b)` and camera move 0x8e2d50 = 1.

`Camera_setupDialogView` 0x203bb8 reads the object's `dialogOffset` property
(`"%d,%d,%d,%d"`: distance added to 80, height added to 70, sideways offset, pitch added
to 4000) and, when `b` ≠ 0, chooses among three angles (±6000 or straight) by where the
living players stand within 80 units. Executed in `docs/spec/dialog-gaps.md` 2.2, which
also shows that without the property the sideways offset is an uninitialised stack word
(4 swoop openings on the disc).

## 3. The file: `<npc>.dbin` in `<level>.lmp`

Fixed 0x448-byte nodes; byte 0 of the file (an s8, only in node 0) is the node count. The
handler uses only that byte; the census found it equal to size / 0x448 in all 52 files.

| Node offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | s8 | node count (node 0 only) | O 0x22ee2c |
| +0x01 | char[0x20] | condition: a level-script entry; empty = never a start node (except the default 0) | E |
| +0x21 | char[0x10] | text key for `text_lookup` | E |
| +0x31 | char[0x10] | voice: `<voice>.vag` and `<voice>.anm` in the level's stream directory | E |
| +0x41 | char[0x13] | speaker object name — cutscene files only (`docs/engine.md`); the NPC machine never reads it | O (no reader in 0x22ec9c–0x231078) |
| +0x54 | s32 | choice count as stored, 0…12 | E |
| +0x58 | 12 × 0x54 | choices | |

| Choice offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | char[0x10] | text key of the choice (drawn with `text_lookup`) | E `draw` (was I in anim-audio.md) |
| +0x10 | char[0x20] | condition entry; empty = always offered | E |
| +0x30 | char[0x20] | action entry, run when the choice is taken; empty = none | E |
| +0x50 | s32 | next node, −1 = end the conversation | E |

The same file type is a cutscene's line list when a `<name>.cut` is beside it (18 of the 52
files); conditions and choices are unused there (`docs/engine.md`). `tools/ref_dialog.py`
`parse_dbin` / `build_dbin` read and write the layout; `tools/anim_audio_info.py` lists a
file.

## 4. Showing a node: `dialog_showNode(n)` (E `open`)

1. Current node 0x8e2d60 (= 0x4fdcd0) = file + n × 0x448, index 0x8e2e88 = n, prompt node
   0x8e2e8c = −1. Resets: cursor blend 0x8e2d54 = 1.0, typewriter 0x8e2cb0 = 1, reveal done
   0x8e2cb4 = 0, reveal count 0x8e2d4c = 0, end-of-text 0x8e2ca8 = 0, more 0x8e2cac = 0,
   cursor and target 0x8e2cb8 / 0x8e2cbc = 0, scroll and target 0x8e2ccc / 0x8e2cc8 = 0,
   held voice 0x4fdcd4 = 0, word 0x8e2cc0 = 0 (no other writer: it is always 0).
2. `audio_streamStop(1)`; the focus goes back to its idle animation (count +0x118 capped at
   1; if its first track is not the idle one, count = 0 and `anim_push(idle, 1)`).
3. Text: `text_lookup(key)` is copied as 16-bit units after two spaces (0x20, 0x20); `^`
   (0x5e) becomes a newline (10); NUL-terminated at 0x4fdd38 (0x800 bytes, no bound
   check), length at 0x8e2d48.
4. Voice (`dialog_queueLineAudio`): blocks until the previous `.anm` read is done; queues
   `<voice>.vag` on stream 1 with flags 0x28 (held), stores its length; held = 1. If the
   directory has `<voice>.anm`, an asynchronous read of it into the next lip-sync buffer
   (ready flag 0x4fdcd5); otherwise ready = 1 and "no lip-sync" for this line. A missing
   `.vag` queues nothing (`stream_playLevel` returns when the entry is absent or empty), so
   `stream_heldEntryReady` reports ready and the line goes on silently (O 0x215fc8,
   0x211c18).
5. Visible choices: for i in 0 … count−1 the choice is kept when its condition is empty or
   its entry returns non-zero (missing entry: −1, kept). Indices go to 0x8e2d20, the number
   to 0x8e2d18. **The list has room for 10**: entries 10 and 11 land on the text length
   0x8e2d48 and the reveal count 0x8e2d4c (E `open`, overlap cases). The disc never has more
   than 8 choices in a node.
6. Layout: the text is measured with `text_drawWrapped(56, 0, text, 524, 0, 0, 19)` (font
   0x4f7100, layer 1); choice i of n gets y = 417 − 19 × (n − i) (0x8e2ce8; not cleared, so
   entries past n keep older values); scroll limit 0x8e2cd0 = max(height + 19 n − 95, 0).

## 5. How the dialog advances

### 5.1 The run task, every simulated tick, on every machine (E `tick`)

1. Prompt-shown 0x8e2e90 = 0.
2. **Camera move** (0x8e2d50 ≠ 0). The float at 0x44f130 — the z of the camera's forward
   vector in `g_cameraMatrix` — is read once (`docs/spec/dialog-gaps.md` 2.4, executed). Opening (1):
   `Camera_lookAt(cam, 45, …)`; far clip 720 while that float > −0.491; repeated in the
   same tick until it arrives when `g_swoopDone` is set. Closing (−1): only while
   `g_shopOpen` 0x41b50c = 0, `Camera_lookAt(cam, −45, …)` and far clip 1800 while the float
   < −0.645. Not arrived (result ≠ 1): return. Arrived: opening → move = 0; closing →
   send message 3 and move = 0. Return either way: the rest waits for the camera.
3. Closed (no node): return.
4. `music_setDuck(0.3)`; prompt node 0x8e2e8c = node index.
5. Pad, unless the `pauseMenu` task runs (then 0): offline, the raw pad of
   `g_scriptActivePlayer`, and if that player has no object or it is dead (flag 8) the
   active player becomes `slot ^ 1`; net, the raw pad of the first living player that is
   local to this machine.
6. Voice and mouth: when a held voice is ready and the `.anm` read is done, held = 0, note
   `stream_queueCount(1)` and `stream_clearHold(1)`. Once the read is done, not held, the
   queue count changed and the stream position is > 0: `dialog_startTalkAnim` and
   talking = 1. While talking: `dialog_syncMouth` (5.4).
7. Input or close:
   - while not closing, or the UI fade `g_uiFadeIn[0]` 0x506070 ≠ 1.0: if the dialog-text
     option 0x4fdcc8 ≠ 0, or the voice is neither held nor playing
     (`audio_streamStatus(1)` = 0): with the cursor blend at 1.0, pad bits 0x101000 send
     message 2 with −1 and 0x204000 with +1; `g_btnConfirmMask` 0x41bfbc sends message 1;
   - closing and the fade at 1.0: once (0x8e2ce0), send 4 when swoop is set, else 3.
8. Scroll: when scroll = target and neither "more" nor end-of-text: at the limit →
   end-of-text = 1; else with the text option off the target advances by 76 (capped at the
   limit) on its own; with it on, "more" = 1 (wait for a press). Otherwise scroll += 5,
   capped at the target.
9. Typewriter: a measuring pass lays the text out with a zero-width clip (budget = reveal
   count) and `text_drawWrapped` leaves the number of characters it showed at 0x44e028.
   While the typewriter runs: if that number < the reveal count, reveal done = 1; else
   reveal count += 1. One character per tick.
10. Cursor blend += 0.12; above 1.0 it is 1.0 and the cursor takes the target. Offline a
    move therefore lands on the ninth tick.

### 5.2 Messages 1–4, in lockstep on every machine (E `messages`, `sequence`)

| Type | Bytes | Effect |
|---|---|---|
| 1 confirm | 1 | typewriter running and not done → stop it (done). Else, not at end-of-text or blend ≠ 1.0 → if "more" and scroll = target: more = 0, reveal done = !typewriter, target += 76 (capped). Else (at the end): `audio_streamStop(1)`; with visible choices, run the selected choice's action entry, then, if it has a next node, clear the text and `dialog_showNode(next)`; otherwise (no choices, or next −1) start closing: `ui_restartFadeIn(0)`, closing = 1 |
| 2 move | 2: s8 delta | with more than one visible choice, no "more" and at end-of-text: target = cursor + delta if inside the list; offline blend = 0 (5.1 step 10 moves it), net blend = 1.0 and the cursor moves at once |
| 3 end | 1 | wait for the `.anm` read; free both buffers; `g_hudSuppressed` = 0; **mutex = 0**; node = 0; `Camera_setMode(cam, 1)`; stop stream 1; held = 0; focus back to idle, focus = 0; `creatures_unfreezeAll`; far clip 1800; if `newWorldPost` named a level: copy it to the pending level 0x41b6d0 and 0x41b720 = 0xff (`docs/quests.md` §4); `script_runPostAction`; if a store was asked for during the dialog: offline `shop_openOrStock(active player, 0, 1)`, net `net_closeLocalMenus(0)` and the shop for the first local slot; if remote, `mainloop_startFadeWait(20)` |
| 4 leave | 1 | camera move = −1 (5.1 step 2 then sends 3) |

A choice's action runs inside the message handler, i.e. in the lockstep message phase
before the tasks (`docs/script.md` 2.6 item 4). Its effects are therefore simulation
effects on every machine.

### 5.3 The life of one conversation

```
use button ─► Creature_interact (mutex) ─► dialogScript ─► startDialog ─► msg 0 (owner only)
msg 0 ─► start node ─► showNode ─► [camera in] ─► typewriter / scroll ─► end-of-text
   ├─ pad up/down ─► msg 2 ─► cursor
   └─ confirm ─► msg 1 ─► action ─► next node ─► showNode …
                               └─► no next ─► closing: fade 0→1 ─► msg 4 ─► camera out ─► msg 3
                                                             (no swoop) ─► msg 3
msg 3 ─► unfreeze, mutex free, pending level, post action, deferred shop
```

### 5.4 The speaker's mouth (E `mouth`)

`dialog_startTalkAnim`: with a lip-sync read for the line, relocate it and start it
(blend 0.3, flags 0x26), then chain the idle track (flags 3). Without one: the `talk` role
animation (0.3, flags 3) and the idle track under it (0.4, flags 3) whose time is set to
−(vag bytes × 28 / (16 × 24000) × 60) ticks, so the idle takes over when the line ends.
`dialog_syncMouth`: for the speaker's track with flag 0x20, when the stream position
changed, compare (position − 0x400) × 28 / (16 × 24000) seconds with (track time / 60 −
0.07); differing by 0.02 or more sets a nudge of +0.1 or −0.1 tick, else 0; a non-zero
nudge is added to every track's time each tick.

## 6. Every game-state effect a dialog can have

### 6.1 While a dialog is open

- Creatures frozen (`creatures_freezeAll` at open, unfrozen at end).
- `g_hudSuppressed` = 1: the HUD draw skips its work, and the **`showBust` / `showCompass`
  setters refuse** (their gate tests it first, `docs/script-effects.md` on `t3/research-script`).
  A bust asked for by a choice action is dropped; one asked for in a post action (run after
  the flag is cleared) is shown. (I, by composing two executed functions.)
- `dialog_isOpen` has 34 call sites. Simulation readers: `Player_run` (input gate, 0x1a565c,
  0x1a5774, 0x1a5bb4), `Player_processDamage` (no damage taken, 0x1b2d08),
  `Player_move` (horizontal velocity zeroed, 0x1b40c0), `game_isFrozen` 0x1ebe8c,
  `game_inNoSaveZone` 0x1e7b94, `player_pollRecallButton` 0x1bcf18, `hud_onMsg`
  0x1d8df4 (recall refused), `activateStore`, `activateMissionMenu`, `Camera_update` /
  `Camera_apply`, `mainloop_runSession` 0x322b8c (idle voice). Draw-only readers:
  `Prop_draw`, `PhProp_draw`, `Player_draw`, `Player_drawMarker`, the pause menu, the HUD
  controller-out, compass and net-camera prompts, `hud_spellSelect`,
  `fx_modelStatusEffects`, `memcard_saveScreen`, two unnamed functions (0x1de8c4 twice,
  0x31deec) and `dialog_objIfOpen` (the only activity centre of `gameSetObjectVis` while a
  dialog is open). The branch was followed for 10 sites (`Player_run` ×3,
  `Player_processDamage`, `Player_move`, `activateStore`, `activateMissionMenu`,
  `dialog_objIfOpen`, here; `hud_onMsg`, `game_inNoSaveZone` in `docs/spec/game-messages.md`
  and the symbol notes). The other 24 are followed and executed in
  `docs/spec/dialog-gaps.md` section 3 (props, markers, compass hidden; pause, recall,
  spell and HUD input refused; `game_isFrozen`'s controller-out exception; the camera
  shake; the idle voice).
- `activateStore(i)`: stores the store index (if < 21) at once, but only sets the pending
  flag 0x4fdd30; the shop opens at message 3.
- `activateMissionMenu`: **refused** (does nothing) while a dialog is open; the other way
  round, message 0 is refused while `missionmenurun` runs. No dialog action on the disc
  reaches it (0 of 155, also not through `postAction` / `addDeferedCall`); the four calls
  are in hub entries run by triggers.
- `Creature_trigger` of a talker from an action finds the mutex held and does nothing.
- The music is ducked to 0.3 each tick.

### 6.2 Scripts the dialog runs

| When | Entry | Runs on |
|---|---|---|
| use button | the object's `dialogScript` | every machine (simulation) |
| message 0 | node conditions, in order, until one accepts | every machine |
| `dialog_showNode` | every choice condition of the node | every machine |
| message 1 at the end | the selected choice's action | every machine |
| message 3 | the post action (`postAction(name)` set by an action) | every machine |

Built-ins reached by the 231 condition entries and 155 action entries of the disc
(direct, through `call` and `callScript`; the number is how many distinct entries reach
each):

| Conditions | Actions (now) | Actions, later through `postAction` / `addDeferedCall` |
|---|---|---|
| `getv` 158, `getMissionAvailable` 99, `getMissionComplete` 51, `getEvil` 16, `checkPlayerGold` 8, `playerHasItem` 5, `demoRunning` 4, `callScript` 4, `getMadeDecision` 1 | `setMissionAvailable` 76, `setv` 46, `activateStore` 44, `changeSwoop` 43, `addQuest` 28, `postAction` 22, `removeQuest` 15, `addDeferedCall` 7, `callScript` 6, `addHelpMessage` 5, `newWorldPost` 5, `getv` 4, `removePlayerItem` 4, `givePlayerGold` 3, `grantMission` 3, `showBust` 3, `soundSequence` 3, `trigger` 3, `setEvil` 2, `setMadeDecision` 2, `givePlayerItem` 1, `onePlayerHasItem` 1, `setEntrance` 1, `setSaveInhibit` 1 | `newWorld` 20, `setEntrance` 20, `cutScene` 5, `getv` 5, `addDeferedCall` 6, `addHelpMessage` 4, `deleteMonster` 4, `gamePaused` 4, `givePlayerItem` 4, `onePlayerHasItem` 4, `postAction` 4, `removePlayerItem` 4, `setv` 4, `getScaledTime` 3, `grantMission` 3, `hideMonster` 3, `soundSequence` 3, … (1 each: `addQuest`, `getEvil`, `removeQuest`, `setSaveInhibit`, `showBust`, `showCompass`, `showMonster`) |

So, in the shipped data:

- **Mission unlocks** (`setMissionAvailable`), **quest lines** (`addQuest` / `removeQuest`),
  **mission completion** (`grantMission`), **quest variables** (`setv`) and the **good/evil
  decision** (`setEvil`, `setMadeDecision`) are set by choice actions; their rules are in
  `docs/quests.md`.
- **Item checks** are made by conditions (`playerHasItem`) and actions (`onePlayerHasItem`);
  **turn-ins** take the item with `removePlayerItem` and grant the mission or a reward
  (`grantMission`, `givePlayerGold`, `givePlayerItem`), partly from a post action after
  the box closes.
- **Shops** open through `activateStore` in an action and open when the dialog ends.
- **Level changes** come from `newWorldPost` (pending level at the end) or `newWorld` /
  `setEntrance` in a post action.
- The **mission menu** is never opened by a dialog (above).

## 7. The box on screen (E `draw`)

Draw task priority 110 (after the HUD at 51, before text messages 125 and cutscenes 300,
`docs/hud-dynamic.md` §1). Nothing is drawn while the camera moves. On the first draw
`ui_restartFadeIn(0)`; alpha = (int)(f × 128) << 24 with f = `g_uiFadeIn[0]`, or 1 − f
while closing. All text uses the word at 0x4f7100, **`gamefontmed.fnt`** (store at
0x323f78; the small font is 0x4f7104, `docs/formats/ui-fonts.md`). Coordinates are the
640 × 448 API arguments; `ui_drawSprite` adds one row inside the callee
(`docs/hud-dynamic.md`).

| Element | Call | Where | Colour (or-ed with the alpha) | Layer |
|---|---|---|---|---|
| box | `ui_drawSprite(box.tex)` | (35, 280); the texture is 560 × 156 texels (`dlgbox.lmp`, header +0/+2) | 0x808080 | 5 |
| body | `text_drawWrapped` | x 56, y 314 − scroll, width 524, line 19; scissor (0, 320)–(640, 409); line visible when 295 < y < 390 (text option on) or never (off) | 0x3a5262 | 6 |
| typewriter | budget = reveal count while running, then reset | | | |
| choices | `text_drawWrapped`, per visible choice | x 86, y = 417 − 19 (n − i), width 524, visibility −100 … 580 | picked 0x36775a, others 0x404040 | 6 |
| no choices | `text_drawWide("Affirmation")` | (86, 409) | 0x36775a | 6 |
| cursor | `text_drawAscii("%c" of byte 0x41b978)` | x 56; y = 398 when the node stores no choices, else between the old and new choice rows by `math_hermite(blend, 0, 1, −1, −1)`, rounded | 0x606060 | 6 |
| more | glyph, then `text_drawWide("dialogMore")` | (51, 398), (81, 398) | 0x606060, 0x36775a | 6 |
| name | `text_drawWideCentered(showName)` | (174, 285), text option on only; while closing it loses max(1, ⌊0.6 n⌋) characters per frame | 0x806464 | 6 |
| player name | `ui_fitText(…, 218)` then `text_drawAsciiCentered` | (176, 256), only when the active player is not on this machine | 0x806464 | 6 |

The choices, cursor and "Affirmation" appear once the typewriter is done, at end-of-text,
and (with the text option off) only when the voice is not held or playing; then the
prompt-shown word 0x8e2e90 = 1. Text batches are ordered as `docs/hud-dynamic.md` §1
describes (layers 0 → 7, reverse submission inside a layer); the box (layer 5) is under
all dialog text.

- `dialog_loadBox` (`game_loadLevel` 0x1e617c) finds `box.tex` in `dlgbox.lmp` unless the
  level is `intro` or arena mode B (`g_pvpModeB`) is on; in those the word 0x4fe538 keeps
  its last value (0 from the executable, or the previous level's box). With 0 the sprite
  call reads addresses 0 and 2. No dialog can open there with the shipped data
  (`docs/spec/dialog-gaps.md` section 4).
- The cursor and "more" glyph byte 0x41b978 is 0x7e or 0x7b, set by `game_initCamera`
  from the layout byte 0x41b69c (`docs/spec/dialog-gaps.md` section 5).
- **Bust / portrait**: the dialog machine draws none. The only portrait-like element is the
  HUD bust panel (`showBust`, `hud_drawBust` 0x1dfb6c, `docs/hud-dynamic.md` §7), refused
  while the dialog is open (6.1). `docs/ui-parity.md` on `t3/research-ui` lists "dialogue
  boxes" under the menu-frame styles; the NPC box is this one sprite, not a frame.
- **Option 0x4fdcc8** (options file +0x18, default 1, in neither menu table; the name
  "dialog text" is ours, I from these uses): on = body and name drawn, scroll waits for a
  press ("more"), input not gated by the voice; off = no body or name, the text scrolls by
  itself, and the player must wait for the voice before choosing.

## 8. Input

- Read from the **raw** local pad words (0x4028dc + slot × 0x58, `docs/ui.md`), not the
  lockstep pads, by the run task, and turned into game messages; only the messages change
  shared state.
- Up: bits 0x101000, down: 0x204000, confirm: `g_btnConfirmMask`. There is no cancel: a
  conversation ends only through a choice with next −1 or a node without choices.
- Moves need the blend at 1.0, more than one visible choice, end-of-text and no "more".
- With the pause menu running the pad is 0. With the text option off, input waits for the
  voice (5.1 step 7).
- Offline the active player is the one whose pad counts; in a net game, the first living
  local player's pad on each machine — every machine can send confirm and move messages.

## 9. Seeds, lockstep and the save

**Seeds.** (Correction: the dialog's camera calls `Camera_apply`, which draws the cosmetic
seed three times when `g_cameraShake` > 0 — even while frozen if a dialog is open; and
the dialog holds the idle-voice draw and skips `fx_modelStatusEffects`;
`docs/spec/dialog-gaps.md` section 7.) The dialog machine itself draws none: no instruction in 0x22ec9c–0x231078,
`Creature_interact`, `Creature_trigger`, `Camera_setupDialogView` or the script built-ins
above touches `g_randSeed` 0x404464, `g_cosmeticSeed` 0x404460 or 0x404468
(`tools/gxref.py`), the animation calls it makes do not reach `anim_randomizeTopTime`, and
no suite of the difftest wrote any of the three words. Two callees do draw: the deferred
`shop_openOrStock` (cosmetic seed and 0x404468, `tools/gxref.py`) and whatever built-ins
the condition and action entries call (`givePlayerItem` goes through
`item_parseDescriptor`, `docs/quests.md` §7).

**Lockstep** (adds to `docs/audio-save.md` A2 and `docs/script.md` P5):
- message 0 comes from one machine and carries its camera; every machine opens;
- confirm and move messages can come from any machine (8);
- the cursor moves at once in a net game but after the blend offline (5.2);
- whether a confirm reveals, scrolls or chooses depends on per-machine text layout, voice
  state and camera arrival (A2): a client must apply the same rules or send its decisions
  in the message;
- `dialog_runTask`'s offline active-player flip (5.1 step 5) is the writer `docs/script.md`
  2.3 lists.

**Save.** Nothing of the dialog machine is saved: the node, cursor, mutex, pending store,
`newWorldPost` buffer and swoop words are runtime only, and `dialog_free` resets them at
level teardown (prompt node −1, focus 0, mutex 0, node 0, active player 0, index −1,
prompt-shown 0, camera move 0, swoop 0). What a conversation leaves behind is saved by its
owners: quest variables, mission bits, the quest list, inventory and gold
(`docs/quests.md` §6, `docs/save-format.md` on `t3/research-saves`). The option 0x4fdcc8 is
in the options file (+0x18), not in the game save.

## 10. Disc census (counts only; `tools/dialog_census.py --disc`)

US v2.00, 120 archives, 120 level scripts, 18,675 objects.

| What | Count |
|---|---|
| `.dbin` files / nodes / bytes | 52 / 300 / 328,800 |
| cutscene line lists (a `.cut` beside them) / their nodes | 18 / 37 |
| NPC conversation files / nodes | 34 / 263 |
| NPC files no `startDialog` of their level names | 4 |
| nodes per NPC file | 1: 3, 2: 11, 3: 4, 4: 3, 5: 3, 7: 2, 9: 2, 26: 1, 27: 3, 29: 1, 31: 1 |
| choices per NPC node | 1: 96, 2: 111, 3: 1, 4: 7, 5: 16, 8: 32 (none with 0 or more than 8) |
| NPC nodes with a condition / unreachable from a start candidate | 241 / 4 |
| NPC choices / with condition / with action / ending (−1) / jumping / action and jump | 685 / 319 / 511 / 379 / 306 / 250 |
| distinct condition / action entries; not exported by the level script | 231 / 155; 0 / 0 |
| NPC node voices with a `.vag` / of those with a lip-sync `.anm` / without a `.vag` | 191 / 181 / 72 (68 in started files) |
| `startDialog` calls / naming a `.dbin` of the same lump / name not a literal | 45 / 45 / 0 |
| objects with `dialogScript` / resolving / reaching `startDialog` | 28 / 28 / 28 |
| … by class | `NPC` 21, `GnomeNavigator` 2, `Orc2Leader` 2, `TestLocation` 2, `MattMarr` 1 |
| objects with `showName` / `shop` / `dialogOffset` / `talkCone` | 33 / 4 / 20 / 0 |
| objects with `showName` but neither `dialogScript` nor `shop` | 5 |
| `activateMissionMenu` call sites / reached from a dialog action | 4 / 0 |

## 11. What the native client needs, in order

1. **Open a conversation** (2.1–2.4, 4): the use-button path to `dialogScript` with the
   mutex; `startDialog` → message 0 (or its local equivalent); the `.dbin` loader; start
   node by condition entries with the −1-for-missing rule; visible choices by condition;
   freeze creatures, `g_hudSuppressed`, close local menus. This needs only the level-script
   machine the client already runs. Without it no NPC talks.
2. **Take choices and end** (5.2 types 1 and 3): run the action entry synchronously in
   the lockstep phase, jump or close, and the end handler's order (mutex free, pending
   level from `newWorldPost`, post action, deferred shop, unfreeze). This is what unlocks
   missions, adds and removes quests, grants missions, takes and gives items and opens
   shops — the blockers `docs/quests.md` §7 item 1 names.
3. **Gates while open** (6.1): refuse `activateMissionMenu`, defer `activateStore`, refuse
   `showBust`/`showCompass`, no player damage or movement, no interact or recall, and refuse
   message 0 during the mission menu or a recall.
4. **Progress rules** (5.1): typewriter one character per tick, scroll pages of 76 by 5 per
   tick, "more", the blend (9 ticks offline, at once in a net game), the closing fade and the
   3 / 4 messages. A client without the camera swoop must still send 3 (never 4).
5. **Draw** (7): one sprite and gamefontmed text at the listed places and colours.
6. **Voice and mouth** (4 step 4, 5.1 step 6, 5.4): stream 1 with the held start; the voice
   gate when the text option is off; lip-sync `.anm` or the talk/idle pair.
7. **Camera** (2.4 step 13, 5.1 step 2): `Camera_setupDialogView`, the swoop in and out,
   far clip, the sender's camera in message 0 — now executed; the ranked list in
   `docs/spec/dialog-gaps.md` section 9 moves it first.

## 12. Open questions

- (Settled in `docs/spec/dialog-gaps.md`: the two camera functions, the float at 0x44f130,
  the 24 call sites, the box without `box.tex`, the `TestLocation` talkers.)
- What `cd_readAsync` does with the ready flag between the call and completion (the
  harness models "cleared, set when done"; I from the spin loops on it).
- `Creature_interactPrompt`'s flag tests were read, not executed; the meaning of +0x312 and
  of bit 26 of +0xa8 in the hostile test is not named.
- Which built-in branch a turn-in takes depends on the item and quest state; this document
  counts reachability, it does not run the entries (`docs/quests.md` §7 item 7).
- No run on a game (Play!, PCSX2 or a console).
