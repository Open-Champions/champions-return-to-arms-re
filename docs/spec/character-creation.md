# New-character creation — SLUS-20973 US v2.00

This is a bounded trace of the original front end. **Observed** means the
executable was read at the address given. **Executed** means an original
function was run in `tools/ee_emu.py` with authored state. **Ran** refers only
to the earlier Play! rig observation cited below. The function-level tests do
not prove a rendered or controller-driven screen.

## Entry and carousel

**Observed:** `frontend_startPlayerSelect` 0x1e3ba0 calls
`playerSel_start` 0x2245b8, which registers the draw task
`playerSel_task` 0x225478. `playerSel_initCache` 0x2243f8 allocates the
selection scratch at pointer 0x4fdb7c; `playerSel_cacheTask` 0x225428
prepares resources. The task's phase byte is 0x8e2c02. Its 16-entry dispatch
table at 0x5404a0 includes the active selection, statistics, name, finish,
and reversal phases. The screen reads local pad state at 0x41bfb8 through
0x41bfd8; it is a draw task, outside the simulation tick (`docs/audio-save.md`).

**Observed:** the carousel has 13 cached entries with a 0x26c-byte stride in
the table starting at 0x4fbc00. Entry 0 repeats model 0 for wraparound;
entries 1–12 cover each playable model once. The model indices in visible
carousel order are 11, 10, then 0–9. Each entry carries a model index at +8
and derived class at +9. The current player's 0x2c-byte selection row starts
at 0x4fdb80; +0x20 is the chosen model index. `playerSel_task` interpolates
the carousel and renders the current model from its cached handles
(0x2254c8–0x2255a4, 0x2259d0–0x226418). `playerSel_raceLumpName`
0x22d2b4, `res_find` 0x17365c and the model animation setter 0x16cfe0
are on that preview path. The animated camera/preview helpers are
0x22a6f8, 0x22a83c and 0x22a968 (calls at 0x2257ac–0x2258c8).
**Observed:** `tools/difftest_char_create.py` checked the 13-row model
permutation in the executable image for seeds 20973 and 7. The model/resource pairings and the
`SELECT.LMP`/`SELECT2.LMP` rule are in `t3/research-player-model`
`7f13899`, tested there in 96 constructor cases. The carousel's full frame
timing and final camera image remain **Unknown** without a rendered run.

| Model indices | Derived class | Body codes | Class label |
|---|---:|---|---|
| 0, 1 | 0 | `bm`, `bf` | barbarian |
| 2, 3 | 3 | `wem`, `wef` | ranger |
| 4, 5 | 1 | `hem`, `hef` | cleric |
| 6, 7 | 4 | `em`, `ef` | wizard |
| 8, 9 | 2 | `dem`, `def` | shadowknight |
| 10 | 5 | `vm` | berserker |
| 11 | 6 | `im` | shaman |

The indices and body codes are **Observed** at 0x4fbc00 and 0x4ebbb8;
English class labels are **Inferred** from the named skill-tree resources, as
in `t3/research-player-model` `7f13899`.

## Appearance choices and statistics

**Observed:** the selection row carries appearance choices at +0x21,
+0x22, +0x24 and +0x23. The creation call at 0x2285bc–0x228618 passes
them, respectively, as hair style, hair/beard colour, beard style and body
skin. A comparison between two bytes of the selected model row at
0x228600–0x228614 sometimes replaces hair with −1. The exact meaning of
those two row bytes is **Unknown**. The four signed bytes become record
+0x20..+0x23 in that order through `player_initNewCharacter` 0x1b1d70
(**Observed:** 0x1b23b8–0x1b23e4). −1 suppresses an optional style. The
constructor's precise mesh/texture requests, null lookup behavior and
disc-available variant ranges were **Executed** in
`t3/research-appearance` `e088796`; disc availability alone does not prove
every choice can be reached on this menu. A native picker must use the
per-model option limits and the menu's hair-suppression condition, rather
than treating all disc entries as selectable. **Observed:** the active
appearance counts are copied into 0x8e2bc0, 0x8e2bd0, 0x8e2be0 and
0x8e2bf0 by 0x22d7c8–0x22d804. The option mutators at
0x22b720–0x22b888 bound style/colour changes using the selected model's
cached resource row; 0x22e6a4 normalizes the dependent style when a count
changes. A full menu run to enumerate every reachable variant is
**Unknown** here.

**Observed:** accepting the model initializes the four displayed base
statistics from class table 0x4ef400 into selection row +0x25..+0x28
(0x226c68–0x226d54). The rows are strength, intelligence, dexterity and
stamina, in that order. The screen sets 20 unspent points at 0x8e2bb0
(0x226cdc). On the statistics phase, a point spent raises one byte and
lowers that counter; the per-stat upper bound is 99 (0x227cfc–0x227d44).
The reverse input lowers a stat only above its class starting value and
returns a point (0x227d74–0x227e40). Continuing with unspent points opens
the warning path (0x227b78–0x227bc4). The seven class starting rows are:

| Class index | Strength | Intelligence | Dexterity | Stamina | Points to allocate |
|---:|---:|---:|---:|---:|---:|
| 0 | 35 | 20 | 25 | 35 | 20 |
| 1 | 26 | 36 | 27 | 26 | 20 |
| 2 | 28 | 30 | 27 | 30 | 20 |
| 3 | 28 | 25 | 35 | 27 | 20 |
| 4 | 23 | 39 | 25 | 28 | 20 |
| 5 | 32 | 22 | 31 | 30 | 20 |
| 6 | 26 | 37 | 24 | 28 | 20 |

**Ran:** the earlier Play! rig read a class-6 created record with
46/37/24/28 after assigning the 20 points to strength, matching the screen
(`docs/issues/live-rig.md` 4b). That is one observed path, not a survey of
every model or appearance choice.

## Name keyboard and confirmation

**Observed; Executed:** `playerSel_nameKeyboardInit` 0x22bc9c fills a
64-glyph table in selection scratch +0x14b4: 26 lowercase English letters,
ten digits, then 28 extended Latin-1 letters from table 0x540740. It sets
0x8e2ba8 to ten columns and 0x8e2bac to 64 glyphs. `playerSel_nameLower`
0x22bdb0 restores lowercase and places the cursor at −3. The input function
0x22be68 uses cursor 0x8e2ba0; −2 is SPACE and −1 is DONE, as independently
**Ran** in `docs/issues/live-rig.md` phase 14. The character-name grid is
distinct from the lobby's 14-column keyboard. The case input toggles the
26 English letters between lower and upper case (0x22c2c4–0x22c354).
`tools/difftest_char_create.py` executed the original keyboard initializer
and lowercase reset for seeds 20973 and 7. The position updater 0x22c704
was stubbed for the latter call; no keyboard image was rendered.

**Observed:** typing appends one selected glyph or space to the current
selection row while length is below 30 (0x22c4f8–0x22c544,
0x22c550–0x22c5a8, 0x22c664–0x22c6b0). The row has 0x20 bytes for a
zero-terminated name. Deletion decrements the length and clears its last
byte (0x22c388–0x22c408). DONE trims trailing spaces and accepts only a
nonempty result (0x22c5b0–0x22c660). The keyboard yields editing,
accepted or cancelled to the task at 0x2284c0–0x2286ac. A successful
selection calls `player_initNewCharacter` at 0x228618, after a lobby-state
check at 0x228584; the lobby branch passes character kind 2, while the
ordinary branch uses the default kind 1. Cancellation returns through the
task's earlier phase without creating a record (0x2286ac–0x2286c4).

## Record and handoff

**Observed; Executed in** `t3/research-player-state`: the constructor call
passes slot, selected model, name, four appearance bytes, the four chosen
stat bytes, character kind and team. `player_initNewCharacter` zeroes the
0x4c30-byte record at `g_players` 0x4d8af0 + slot × 0x4c30, copies the
name and appearance, derives class from model, sets level and acknowledged
level to 1, gold to 500, and grants starting items. `tools/difftest_player_init.py`
compared 60 authored cases; see `docs/issues/player-init-recalc.md` in that
branch. Init alone has no Player object pointer and does not establish the
on-screen maximum hit points; the first object-present recalc trims current
health and mana to their maxima. **Observed:** selection subsequently calls
0x3278f0 at 0x228624 and enters the finish/launch phase. `playerSel_finish`
0x22a360 sets `needPlayers` and queues the hub (`docs/audio-save.md`). The
selection screen is local presentation until it commits a record; its state
must not be assumed to be a lockstep game-message stream.

## Ordered native port

1. Create the selection task's phase and per-slot scratch; read the 13
   carousel entries and retain model index, derived class and selection
   order. Load the exact model, animation and selection resources from the
   player-model trace. Preserve absent resource handles.
2. Reproduce local carousel input, interpolation and preview-camera/model
   updates from `playerSel_task` and helpers 0x22a6f8/0x22a83c/0x22a968.
   Check frames and navigation in the native renderer before claiming visual
   parity.
3. Implement the per-model appearance controls and option bounds. Carry
   selection row +0x21/+0x22/+0x24/+0x23 to the four signed record bytes,
   including the conditional hair suppression. Resolve body, hair and beard
   pairs through the appearance/resource traces.
4. Initialize the four class statistics from 0x4ef400, allow exactly 20
   allocations with the observed 99 upper bound and baseline floor, and
   retain the unspent-points warning/return path.
5. Build the separate ten-column name keyboard with its 64 glyphs, case
   toggle, space, deletion, DONE and cancel behavior. Enforce 30 characters,
   trailing-space trim and a nonempty final name.
6. On confirmation, call the player-record initialization contract with
   model, four appearance bytes, four stat bytes and correct character kind;
   then perform selection finish and object-present recalc at its actual
   lifecycle point. Verify the created record and rendered preview against a
   live original/native pair, including cancellation and two local players.

## Verification boundary

With `PYTHONDONTWRITEBYTECODE=1`, the focused
`python3 tools/difftest_char_create.py <local-v2.00-elf>` check passed two
keyboard executions and two carousel table checks (seeds 20973 and 7).
The prior-branch difftests were rerun serially with the same pinned local
executable and disc: `difftest_player_appearance.py` passed 96 constructor,
1,072 item-index, 24 variant-row, eight mask and 504 draw-gate cases;
`difftest_player_model.py` passed 96 constructor cases and 12 animation
tables; `difftest_player_init.py` passed 60/60 each for record, recalc,
gear, maxima and current-value checks. The full
`python3 -m unittest discover -s tools -p 'test_*.py'` suite passed 652/652.

The keyboard/carousel difftest is isolated; the original full selection task
requires front-end resources, pad frames, renderer and camera services beyond
`tools/ee_emu.py`. The prior appearance, model and record difftests likewise
prove function-level behavior only. Exact full-screen camera motion, visible
focus order, all reachable appearance choices and a complete confirm/cancel
walk remain **Unknown** here until a captured original/native screen run.
