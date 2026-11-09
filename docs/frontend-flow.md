# Front-end flow: boot to the first level request — SLUS-20973 US v2.00

Research date 2026-11-09. The executable is pinned by SHA-256 in
`tools/difftest_frontend_flow.py` (line 21). **Executed** means the original
function ran in `tools/ee_emu.py` on authored memory at seeds 20973 and 7, with
callees outside the case's follow set auto-stubbed (return 0) and recorded,
and every extra stub named where it is installed. Watched words are planted
with sentinels (`0xA5`/`0xA5A5A5A5`) so a missing store is visible.
**Observed** means the instruction or data at the address was read.
**Inferred** and **Unknown** are stated separately. Nothing here was rendered,
heard, or run on a console or in Play!.

No lookup key, localized string, level identifier or file name is written in
this note or in the new tools. Where a test needs one it compares the
executable's own bytes at run time (`same_cstr`, line 63) and stores nothing.
Rows are named by position and meaning; meanings are **Inferred** from the
key identifiers and from what the accept code does.

This note links audited work and does not repeat it:

- Character appearance: `t3/research-char-appearance` `153d1c3`,
  `docs/spec/created-character-appearance.md` lines 15–137.
- Starting equipment: `t3/research-loading-readiness` `366b65a`,
  `docs/starting-equipment-r4.md` lines 19–61.
- Save/load screen: `t3/research-save-screen` `c8895e2`,
  `docs/save-screen.md` lines 22–31 and 181–326.
- Options list and config image: `t3/research-options-menu` `603b2b7`,
  `docs/options-menu.md` lines 28–103 and 129–177.
- Screen layout, title sprite and per-phase draw calls: `t3/research-menus-layout`
  `29c90a5`, `docs/frontend-layout.md` lines 115–183.
- In-game menus, including save/load indices: `t3/research-menus` `099900e`,
  `docs/menus.md` lines 266–310 (read, not edited).
- Carousel order and class starting stats: this branch,
  `docs/spec/character-creation.md` and `tools/difftest_char_create.py`.

## 1. Boot to the title screen

**Observed** (`docs/mainloop.md` lines 455–475): `main` runs the boot memory-card
check `mainloop_runBootCardCheck` 0x32396c, then the publisher logo and the
intro movie in modal loops, then on its first offline pass calls
`frontend_start(0)` 0x1e1f34 and the session loop. The front end is not a
separate executable mode; it is the `frontend` run task on top of a backdrop
level.

**Executed** `frontend_start(0)` (`check_start`, lines 492–513):

| Effect | Address | Value |
|---|---|---|
| task added | `task_add` 0x19e4a0 at 0x1e20d0 | `(frontend_run 0x1e08f0, priority 25, name, 0)` |
| state / menu table | 0x4f6b78 / 0x4f6b7c | 0 / main table 0x4f6b88 (from 0x1e318c) |
| first-entry flag | 0x4f6b70 | 1 |
| theme-requested flag | 0x4f7024 | 0 |
| player count | 0x4d8ae0 | 1 |
| pending level | `g_pendingLevel` 0x41b6d0, marker 0x41b720 | the backdrop level string at 0x53d0d0, marker 0xff |

When byte 0x86ad50 is set (main-menu load chosen, section 3) and the
card-screen-done byte 0x4f8f29 is 0, `frontend_start` instead clears 0x86ad50,
calls `memcard_requestLoad(0, 1)` at 0x1e1fac and does **not** write the state
word (sentinel kept). With 0x4f8f29 set it resets to the main menu and leaves
0x86ad50 at 1 (**Executed**, same function). So a load abandoned by a session
restart reopens the load screen.

**Executed** first `frontend_run` pass (`first_pass`, lines 90–107): with
0x4f6b70 = 1 it loads three front-end lumps (`0x173558` with the names at
0x53cdf8, 0x53ce00, 0x53ce10), then calls 0x222a8c, `playerSel_initCache`
0x2243f8 and `frontend_allocScratch` 0x1e3d2c, and clears 0x4f6b70. With
0x4f7024 = 0 it calls 0x211ce8(2), requests the main theme (string 0x53ce20)
through 0x2110e0 with flags 5, or 1 when byte 0x4f701a is set, stores
0x4f7024 = 1 and keeps `0x216480(2)`'s result at 0x4f7028.

**Title screen.** There is no separate title state. The title sprite is drawn
by `frontend_run` in states 0–4 (`docs/frontend-layout.md` line 130 on
`t3/research-menus-layout`, **Executed** there). The draw is skipped while the
card machine is busy (0x217518), a net launch is pending (0x402793), or 0x327fc0
returns nonzero (**Observed** 0x1e0a60–0x1e0ac8). "Press start" behaviour,
attract-mode timing and the backdrop level's own script are **Unknown**.

## 2. Main menu and the input rule

**Executed** (`frontend_input`, lines 111–137; `check_tables`, lines 515–526):
menus are 16-byte rows ended by a zero key; the terminator's +4 word holds the
selected row. The retail main table has four rows. Accept is
`pressed(pad 0) & 0x41bfbc` (initial 0x40); cancel is `pressed(pad 0) &
0x41bfb8` (initial 0x120). Only pad slot 0 is scanned (**Observed** loop
0x1e1204–0x1e1240). A nonzero `0x1a14e4()` suppresses both (**Observed**
0x1e11c8, 0x1e1d40). Accept dispatches through the 13-entry table at 0x53d050
by state; cancel through the 15-entry table at 0x53d090 by state − 1.

Main-menu accept compares the row key with constants (`0x3b8534`), so rows
are dispatched by key (**Executed**, `check_accepts` lines 156–172):

| Row | Meaning (Inferred) | Result |
|---:|---|---|
| 0 | new game | state 1, game-type table 0x4f6bf8 |
| 1 | load game | clears 0x4f711c / 0x4f7124 / 0x4f7120, calls `memcard_requestLoad(0, 1)` at 0x1e166c, sets byte 0x86ad50 = 1; **no store** to the state word |
| 2 | options | `config_backup` 0x1e6428, state 11, table 0x4f6e88 |
| 3 | credits | state 15, table 0x4f6fb8, `credits_load` 0x223c64 |

**Observed:** a fifth key compare at 0x1e1718 leads to a developer quick start
(0x1e1728–0x1e17e4: sets 0x402792/0x402791, stops the front end, difficulty 1,
four `player_initNewCharacter` calls, writes a level name). No retail main-table
row carries that key (`check_tables`), so it is **Inferred** unreachable.

## 3. Load game

**Executed** (`load_request_chain`, lines 421–447, with `memcard_requestLoad`
and `memcard_setState` followed): the load row opens the card load screen. It
stores pad index 0 at 0x4f923c, copies `g_inFrontend` 0x41b510 (planted 1) to
0x8e1ab8, stores the apply flag 1 at 0x8e1ab9, clears 0x4f8f29, and calls
`memcard_setState(4, 0)` at 0x217764, so card state 0x88d3a0 = 4. The front-end
state stays 0.

**Executed** (`load_accept`, lines 450–475): on slot acceptance
`memcard_loadScreen` 0x219360 calls `frontend_stop(0)` at 0x21946c **only when
both** 0x8e1ab8 and 0x8e1ab9 are set; the other three combinations do not call
it. The audited save-screen fixture planted 0x8e1ab8 = 0 and so did not show
this branch. The slot list, card queue, pump, text and fade callees are stubs
(listed at lines 453–457).

From there the audited save-screen machine applies: the whole 0x40-byte
directory record is copied, 0x4bc78 bytes are read, `save_load` runs because
the flag is 1, the pending level comes from the save header (`name` or
`name_sub`), the marker becomes 0xfd and the loaded flag 0x8e1ad6 becomes 1;
the screen then waits until the live level name matches
(`docs/save-screen.md` lines 258–298 and 314–319 on `t3/research-save-screen`).
World reconstruction and difficulty restore (`+0x6c`) belong to the save-world
notes. A real card read, error prompts during a front-end load, and what the
player sees between `frontend_stop` and the first loaded frame are **Unknown**.

## 4. Options

**Executed** here only as the main-menu entry (row 2 → state 11) and the
cancel to the save-choice state 14 (`check_cancels`, lines 244–260). The list
records, slider/toggle edits, state 14 query/commit and 760-byte config image
are the audited contract in `docs/options-menu.md` lines 28–103 and 129–177 on
`t3/research-options-menu`. One addition: the first word of `g_savedConfig`
0x4f8f38 is also the difficulty unlock word (section 5).

## 5. New game setup states

All rows below are **Executed** in `check_accepts` (lines 154–241) and
`check_cancels` (lines 244–260). Offline means 0x4f70a0 = 0.

**State 1, game type** (table 0x4f6bf8, two rows). Row 0 stores 0x4f70a0 = 0 and
enters state 2 with the players table 0x4f6de8. Row 1 stores 0x4f70a0 = 1,
clears the 0x14c-byte net settings block 0x402a30 and, for its key, enters
state 10 and calls the lobby opener 0x327f80 at 0x1e1854. The other net rows
(states 6–10) are the netlib route in `docs/ui.md` lines 215–228.

**State 2, players** (four rows). Each pass, rows 1–3 get kind word 0 while
every earlier pad slot is present and 5 from the first absent slot on; the
present word is `0x41bfdc + slot × 0x58` (**Executed** for 1–4 present pads,
lines 191–196; ref `players_row_kinds`, ref line 94). Accepting row r stores
`g_numPlayers` 0x4d8ae0 = r + 1, clears the three mode flags and enters state 4
with the two-row mode table 0x4f6c68 for one player or the three-row table
0x4f6c28 for two to four. A planted disabled row was moved by the list
handler and accepted as row 0 in this fixture; the handler's re-selection rule
is **Unknown**.

**State 4, mode.** For the row key, 0x4f711c = contains the versus substring,
0x4f7124 = contains the scramble substring, 0x4f7120 = arena substring or
scramble (substring search 0x3b96a8; **Observed** 0x1e18e8–0x1e1990).
Scramble also forces one player (**Observed** 0x1e1980–0x1e1990; no retail
row reaches it). Executed flags per row (ref `MODE_FLAGS`,
ref line 74):

| Table | Row 0 | Row 1 | Row 2 |
|---|---|---|---|
| one player 0x4f6c68 | missions (0,0,0) | arena (0,0,1) | — |
| multi 0x4f6c28 | missions (0,0,0) | arena (0,0,1) | arena versus (1,0,1) |

No retail row sets scramble. Next: versus → state 5 kill-limit table 0x4f6c98;
arena → `g_difficultyIdx` 0x4f719c = 1 and `frontend_startPlayerSelect` at
0x1e19c0; missions → state 3 difficulty table 0x4f6e38.

**State 5, kill limit** (offline): rows 0/1/2 store byte 0x4f8408 = 5/10/25 and
call `frontend_startPlayerSelect` at 0x1e1a78. Difficulty is not written on
this route (sentinel kept).

**State 3, difficulty** (four rows). `0x1ec448` returns the highest unlocked
level from word 0x4f8f38: bit 0x40 → 5, 0x20 → 4, 0x11 → 3, 0x0c → 2, else 1
(ref `max_difficulty`, ref line 81). Accepting row r with r + 1 above that
value does nothing (difficulty sentinel kept, no call, state 3). Otherwise
`g_difficultyIdx` = r + 1 (1–4), 0x4f701c = 0, 0x41b4f4 = 0, and
`frontend_startPlayerSelect` is called at 0x1e1ad0. Executed for eight unlock
words × four rows. The executable's own default word is 0 and its initial
difficulty is 1 (`check_tables`). Who sets the unlock bits (a profile variable
via `setpv` is **Inferred**) and the meaning of value 5 are **Unknown**.

**Cancel** (offline): 1 → 0 main; 2 → 1; 3 → 4 with the mode table chosen by
player count; 4 → 2; 5 → 4 (multi table); 11 → 14 with the table unchanged
(ref `cancel_offline`, ref line 134).

## 6. Character selection entry

**Executed** `frontend_startPlayerSelect` 0x1e3ba0 (`check_select_entry`, lines
278–304): stores the player count byte at 0x4fdcb0 and offline flag 0x4fbbe3 =
1, clears 0x4f701c, 0x41b4f4, 0x4fbbe1 and 0x4fdcb4, and copies the level to
queue into 0x4fdc30: the executable's level string at 0x53d3e8 offline, or
the string returned by 0x304bc8 on the arena route (stubbed to an authored
name). It then calls `playerSel_start(difficulty >= 2)` at 0x1e3c58, for all
four difficulties and one or four players.

**Executed** `playerSel_start` 0x2245b8 (`check_player_sel_start`, lines
307–340, memset followed, other callees stubbed): clears the four 0x2c-byte
selection rows at 0x4fdb80, sets the current slot's carousel row (+0x20) to 1,
copies 0x4fbbe3 to `g_playerSelPending` 0x4fbbd8, runs the keyboard
initializer 0x22bc9c and adds `playerSel_task` 0x225478 as a draw task with
priority 9; then 0x4fbbdc = 1. With argument 1 it also sets scratch +0x1554,
sets the carousel row to 0 and the phase byte 0x8e2c02 to 1; with argument 0
the phase byte is not written (sentinel kept). Phase 1 is the import
selection (**Inferred**, `docs/frontend-layout.md` lines 148–167 on
`t3/research-menus-layout`). So new characters are offered first only on
difficulty 1; from difficulty 2 the screen opens on import. Which phase byte
the plain path starts in, and how import continues, are **Unknown**.

## 7. Creation phases

Phase dispatch is the jump table at 0x5404a0, reached only while float
0x8e2c44 is 1.0 (`docs/frontend-layout.md` lines 144–151 there). Phase changes
go through next-phase byte 0x8e2c03 and the transition float 0x8e2c18
(**Observed** 0x227970–0x2279f4). Each case below runs the whole original
`playerSel_task` with that phase forced and all callees stubbed, or the named
slice. Pad words are per slot at `0x41bfd8 + slot × 0x58`: +8 held, +0xc
pressed, +0x10 repeat.

**Class and appearance.** Carousel order, class bytes and starting stats are
pinned by `tools/difftest_char_create.py`. Appearance counts, bounds and the
model-10 normalizer are the audited contract in
`docs/spec/created-character-appearance.md` lines 15–112 on
`t3/research-char-appearance`.

**Point pool** (**Executed** slice 0x226c68–0x226d58, `check_point_pool`, lines
611–635, slot 1, all twelve carousel rows): the appearance accept copies the
four appearance values, sets next phase 3, ability points 0x8e2bb0 = 20,
cursor 0x8e2bbc = 0, warning 0x8e2bbd = 0, and copies the class starting stats
into row +0x25..+0x28. Slot 0's row is untouched.

**Phase 3, ability points** (**Executed**, `check_stats` lines 576–608, carousel
rows 1, 2, 3, 12; ref `stat_input`, ref line 206):

- repeat 0x101000 moves the cursor up to 0; 0x204000 down to 3;
- repeat 0x802000 adds 1 to the stat under the cursor and takes a point while
  points remain and the stat is below 100, so **the maximum is 100** (99 → 100
  executed; 100 refused). The older "99 cap" lead in
  `docs/spec/character-creation.md` is corrected by this run;
- repeat 0x408000 returns a point while the stat is above the class starting
  value (the floor);
- accept with points left sets the warning (0x8e2bbd = 1, step 0x8e2bb8 = 16);
  accept with 0 points calls `playerSel_nameLower` 0x22bdb0 at 0x227e64 and
  sets next phase 4; cancel sets next phase 2 and keeps the points;
- while the warning is up, its alpha 0x8e2bb4 steps by 0x8e2bb8 and clamps at
  0..126; accept at 126 sets the step to −16; at 0 with a negative step the
  warning clears.

**Phase 4, name** (**Executed** `nameEntry_run` 0x22be68 with strlen followed
after the original keyboard initializer, `check_name` lines 662–693; ref
`name_accept`, ref line 235). The name is the selection row's first bytes,
length word 0x8e2ba4, cursor 0x8e2ba0 (glyph index, −1 done, −2 space).

- accept on a glyph or space appends while length < 30;
- accept on done returns 1 when the name has any non-space byte; an empty or
  all-space name returns 0 and sets warning 0x8e2bbf. Spaces are **not
  trimmed** here (`'a '` is accepted as is);
- either cancel bit returns −1 with the name unchanged;
- repeat bit 0x80 deletes the last byte (no-op when empty);
- held bit 0x08 switches the 26 letters to upper case, released restores lower;
- keyboard character 0x8e2c5c: printable bytes append, 8 deletes, 0x0d acts as
  done, 0x11/0x12/0x1a/0x08 are not appended;
- a warning is dismissed by accept;
- accept at cursor −3 (the value `playerSel_nameLower` sets) increments the
  length and stores scratch +0x14b1, which is zero in this fixture. Whether
  real input can accept at −3 is **Unknown**.

**Name result** (**Executed** phase 4 with `nameEntry_run` stubbed to 0, 1 or
−1, `check_name_phase` lines 712–724; ref `name_phase_result`, ref line 244):

| Result | Last local player | Earlier player |
|---|---|---|
| 1 | phase byte 5 directly, fade scratch +0x14b0 = 0 | next phase 6 (next-player box), step 16 |
| −1 | next phase 3; ability points become 0 | same |
| 0 | stays | stays |

"Last" is slot − first slot 0x4fbbe1 = players 0x4fdcb0 − 1. Offline no
record constructor, lobby send or finish runs here (0x327fc0 stubbed to 0).
The lobby branch with kind byte 0x4fbbe4 (constructor at 0x228618, send at
0x228624, phase 12) is **Observed** only. The summary phase 8, the next-player
phase 6 and two-player slot advance are **Unknown** as executed behaviour.

## 8. Finish and the first level request

**Observed:** `playerSel_finish` 0x22a360 is called with 1 at 0x225d48 (import
phase) and with 0 at 0x2287e4 in phase 5 once `hud_stepFade(4)` returns 0x80
(the instruction words are asserted in `check_finish`).

**Executed** chain `frontend_startPlayerSelect` → `playerSel_finish(0)`
(`finish_chain` / `check_finish`, lines 343–413; `game_getHubName` 0x1ec300
followed, its three predicates stubbed):

- `vars_set` 0x1ed854 with the quest-variable key at 0x5404e0 and value 0; 0x4fbbe2 = 1;
  0x4fbbdc = 0; `frontend_stop(0)` at 0x22a46c;
- marker 0x41b720 = 0xff and `g_pendingLevel` = 0x4fdc30; because that equals
  the hub constant at 0x540530, it is replaced by `game_getHubName()`: the
  second hub name (0x53d6c0) only when the decision predicate 0x1bf960, the
  side predicate 0x1bf8d8 and `mission_isComplete(difficulty, 1)` 0x1bf730 all
  return nonzero, otherwise the first (0x53d6b8);
- 0x322954(10) is called; the float 0x8e2c48 is then scaled by 100
  (**Observed** 0x22a4e4–0x22a4fc, not asserted);
- `g_playerSelPending` is **not** cleared (sentinel kept).

`playerSel_finish(1)` clears `g_playerSelPending` and copies the level at
0x4fdc70 to `g_pendingLevel` (marker 0xff) without stopping the front end; an
empty name there requests nothing (**Executed**).

The records are built at level entry, not at confirmation: `mainloop` calls
`playerSel_applyPending` 0x2247ec at 0x321024, which calls
`player_initNewCharacter` for every nonzero selection row and clears the
pending word (`docs/spec/created-character-appearance.md` lines 113–137 on
`t3/research-char-appearance`). The initializer's starting items and equipped
slots are `docs/starting-equipment-r4.md` lines 19–61 on
`t3/research-loading-readiness` `366b65a`. Loading screen and arrival are that
branch's `docs/loading-transitions.md`. Whether the first hub frame differs
for a second or third local player is **Unknown**.

## 9. Client-implementable list

Each item names its evidence; implement in this order.

1. Boot: card check → logo → intro → `frontend_start(0)`; front end runs over
   the backdrop level, state 0, main table, player count 1; first pass loads
   the three front-end lumps and requests the theme with flags 5 (1 when
   0x4f701a is set). (Sections 1; **Executed**.)
2. Menus as key-dispatched rows with a terminator selected index; accept 0x40
   and cancel 0x120 by default, pad 0 only in the front end. Draw the title in
   states 0–4. (Section 2; layout from `t3/research-menus-layout`.)
3. Main menu: new → game type; load → open the card load screen with
   (pad 0, apply 1) and remember "load chosen" (reopen it on a front-end
   restart until the card screen reports done); options → backup config,
   state 11; credits → state 15. (Sections 1–3; **Executed**.)
4. Load: card state 4; on slot acceptance stop the front end when it was
   opened from the front end with apply set; then follow the audited
   save-screen load machine and wait for the live level name. (Section 3.)
5. Game type → players with rows disabled past the first absent controller →
   mode table by player count → arena (difficulty 1) / versus (kill limit
   5/10/25, difficulty unchanged) / missions (difficulty). (Section 5.)
6. Difficulty rows 1–4, locked above the profile unlock level from config
   word 0; store the index; keep it in game setup and the slot save, not in
   the options image. (Section 5; `docs/options-menu.md` lines 95–102.)
7. Selection entry: player count, offline flag, queued hub level; open on
   import from difficulty 2, else on creation. (Section 6.)
8. Class carousel and appearance from the audited contracts; on appearance
   accept, copy class starting stats and set 20 points. (Section 7.)
9. Ability points: up/down cursor 0–3, right adds while points remain and
   value < 100, left returns down to the class starting value; accept needs 0
   points, else show the dismissible warning; cancel returns to appearance.
10. Name: 64-glyph ten-column grid, 30-byte limit, space and done targets,
    done needs a non-space byte, no trim, delete on the repeat button, upper
    case while the hold button is down, keyboard input; cancel returns to
    stats with 0 points.
11. After the last local player's name, fade and run the finish: stop the
    front end, request the hub (second hub only for the decided, side and
    mission-complete case), and build each record at level entry from the
    selection rows, then grant starting equipment. (Section 8.)

Still **Unknown** and not to be invented: the import phase and summary phase
behaviour, multi-player slot advance, the list handler's disabled-row rule,
the unlock writer, title attract timing, rendered pixels, sounds as heard, and
any network path.

## 10. Reproduction

On the mini, serially, with `PYTHONDONTWRITEBYTECODE=1` and the pinned owned
executable under `local/`:

```
python3 tools/difftest_frontend_flow.py local/SLUS_209.73
python3 tools/difftest_char_create.py local/SLUS_209.73
python3 -m unittest discover -s tools -p 'test_*.py'
```

The first prints the per-seed counts and one PASS line for seeds 20973 and 7.
Logs are kept under `local/frontend/` and are not committed.
