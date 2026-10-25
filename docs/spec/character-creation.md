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

**Observed:** the table at 0x4fbc00 has 13 entries at a 0x26c-byte stride.
`tools/difftest_char_create.py` checks the exact +8 model order
0, 11, 10, 0–9 and the +9 class byte in every entry against the pinned
executable for seeds 20973 and 7. Entry 0 duplicates entry 3. The
model/resource pairings and the
`SELECT.LMP`/`SELECT2.LMP` rule are in `t3/research-player-model`
`7f13899`, tested there in 96 constructor cases. The carousel's full frame
timing and final camera image remain **Unknown** without a rendered run.
The selection-row layout at 0x4fdb80 (+0x20 chosen model), interpolation,
preview resource calls and camera helpers 0x22a6f8/0x22a83c/0x22a968 are
**Unknown** as executable behavior here; no committed check executes that
path. These addresses are investigation leads, not native port requirements.

| Model indices | Derived class | Body codes | Class label |
|---|---:|---|---|
| 0, 1 | 0 | `bm`, `bf` | barbarian |
| 2, 3 | 3 | `wem`, `wef` | ranger |
| 4, 5 | 1 | `hem`, `hef` | cleric |
| 6, 7 | 4 | `em`, `ef` | wizard |
| 8, 9 | 2 | `dem`, `def` | shadowknight |
| 10 | 5 | `vm` | berserker |
| 11 | 6 | `im` | shaman |

The carousel indices and derived classes are **Observed** by this difftest;
body codes are supported by `t3/research-player-model` `7f13899` at 0x4ebbb8;
English class labels are **Inferred** from the named skill-tree resources, as
in `t3/research-player-model` `7f13899`.

## Appearance choices and statistics

**Unknown in this menu:** the selection row's appearance fields at
+0x21/+0x22/+0x24/+0x23, the proposed handoff at 0x2285bc–0x228618,
the conditional hair replacement at 0x228600–0x228614, and the exact
meaning of the compared model-row bytes have no committed menu check.
The record's four signed appearance bytes and −1 optional-style suppression
are supported by the prior player-init and appearance research. The
constructor's mesh/texture requests, null lookup behavior and disc-available
variant ranges were **Executed** in
`t3/research-appearance` `e088796`; disc availability alone does not prove
every choice can be reached on this menu. The proposed active-count copies
at 0x22d7c8–0x22d804, option bounds at 0x22b720–0x22b888 and dependent
normalization at 0x22e6a4 are **Unknown** pending bounded execution or an
address trace. Reachable per-model choices remain **Unknown**.

**Observed:** the pinned executable's class table at 0x4ef400 contains
seven rows of four s32 values. The difftest asserts every value for both
seeds. The proposed copy into selection row +0x25..+0x28 at
0x226c68–0x226d54, 20-point counter at 0x226cdc, 99 cap at
0x227cfc–0x227d44, baseline floor and point return at 0x227d74–0x227e40,
and unspent-points warning at 0x227b78–0x227bc4 are **Unknown** here because
the menu control branches have not been executed or traced in a committed
check. The table's four columns are identified as strength, intelligence,
dexterity and stamina by the prior record research. The seven rows are:

| Class index | Strength | Intelligence | Dexterity | Stamina |
|---:|---:|---:|---:|---:|
| 0 | 35 | 20 | 25 | 35 |
| 1 | 26 | 36 | 27 | 26 |
| 2 | 28 | 30 | 27 | 30 |
| 3 | 28 | 25 | 35 | 27 |
| 4 | 23 | 39 | 25 | 28 |
| 5 | 32 | 22 | 31 | 30 |
| 6 | 26 | 37 | 24 | 28 |

**Ran:** the earlier Play! rig read a class-6 created record with
46/37/24/28 after assigning 20 points to strength, matching one screen path
(`docs/issues/live-rig.md` 4b). That is one observed path, not a survey of
every model or appearance choice.

## Name keyboard and confirmation

**Observed; Executed:** `playerSel_nameKeyboardInit` 0x22bc9c fills a
64-glyph table in selection scratch +0x14b4: 26 lowercase English letters,
ten digits, then 28 distinct high-bit glyphs. The exact extended table at
0x540740 is **Unknown** because the difftest checks only uniqueness and the
high bit. The initializer sets
0x8e2ba8 to ten columns and 0x8e2bac to 64 glyphs. `playerSel_nameLower`
0x22bdb0 restores lowercase and places the cursor at −3. The input function
0x22be68 is **Unknown** here; −2 as SPACE and −1 as DONE were independently
**Ran** in `docs/issues/live-rig.md` phase 14. The character-name grid is
distinct from the lobby's 14-column keyboard. Case input at
0x22c2c4–0x22c354 is an **Unknown** branch pending a check.
`tools/difftest_char_create.py` executed the original keyboard initializer
and lowercase reset for seeds 20973 and 7. The position updater 0x22c704
was stubbed for the latter call; no keyboard image was rendered.

**Unknown:** the proposed 30-character bound and append paths
(0x22c4f8–0x22c544, 0x22c550–0x22c5a8, 0x22c664–0x22c6b0), deletion
(0x22c388–0x22c408), trailing-space trim and nonempty DONE rule
(0x22c5b0–0x22c660) have no committed input check. The proposed
edit/accept/cancel handoff at 0x2284c0–0x2286ac, constructor call at
0x228618, lobby character-kind branch at 0x228584, and cancellation path
at 0x2286ac–0x2286c4 also lack a committed focused check. A prior rig
exercised one successful name and launch, not these branch boundaries.

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
health and mana to their maxima. The proposed subsequent 0x3278f0 call
at 0x228624 and finish/launch transition are **Unknown** in this menu.
`playerSel_finish` 0x22a360 is described in `docs/audio-save.md`, but its
path from confirmation needs a focused check. The
selection screen is local presentation until it commits a record; its state
must not be assumed to be a lockstep game-message stream.

## Ordered native port and research gates

1. Use the checked 13-row carousel order and +8/+9 model/class fields.
   Reuse the independently tested model/resource pairings. Check the
   selection-row layout, input and preview path before implementing their
   precise native behavior; frame timing and camera output need a rendered
   original/native comparison.
2. Execute or trace the per-model appearance counts, option bounds,
   normalization, and menu-to-record handoff. Until then, expose no claimed
   complete set of reachable variants. Reuse the independently tested
   appearance resource and record contracts only within their scope.
3. Use the checked seven class starting-stat rows. Establish the selection
   copy, allocation/reversal limits and warning branch with bounded original
   checks before making 20 points, a 99 cap or a baseline floor parity rules.
4. Use the executed 64-glyph, ten-column keyboard initialization and
   lowercase reset. Check case toggle, editing, length, trim, DONE and cancel
   branches before implementing their exact rules.
5. Check the confirmation path, including character kind, cancellation and
   finish transition, before wiring the record constructor. Then verify the
   created record and rendered preview against an original/native pair,
   including two local players and lifecycle recalc.

## Verification boundary

With `PYTHONDONTWRITEBYTECODE=1`, the focused
`python3 tools/difftest_char_create.py <local-v2.00-elf>` verifies the pinned
executable SHA-256 before any comparison and checks two keyboard executions,
the exact carousel model/class rows and seven starting-stat rows (seeds
20973 and 7). A different executable is refused.
The prior-branch difftests were rerun serially with the same pinned local
executable and disc: `difftest_player_appearance.py` passed 96 constructor,
1,072 item-index, 24 variant-row, eight mask and 504 draw-gate cases;
`difftest_player_model.py` passed 96 constructor cases and 12 animation
tables; `difftest_player_init.py` passed 60/60 each for record, recalc,
gear, maxima and current-value checks. The full
`python3 -m unittest discover -s tools -p 'test_*.py'` suite passed 652/652
in the original branch run and in this post-fix rerun. The post-fix suite
ran in 13.868 seconds. A mismatched executable was refused with a nonzero
exit before emulation.

The keyboard/carousel difftest is isolated; the original full selection task
requires front-end resources, pad frames, renderer and camera services beyond
`tools/ee_emu.py`. The prior appearance, model and record difftests likewise
prove function-level behavior only. Exact full-screen camera motion, visible
focus order, all reachable appearance choices and a complete confirm/cancel
walk remain **Unknown** here until a captured original/native screen run.
