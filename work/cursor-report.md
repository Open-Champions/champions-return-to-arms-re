STATUS: MORE

2026-10-27 — research-arena-live, branch t3/research-arena-live; starting pin 77c2f70.

Documented
- Addressed mode-B begin/preload/start/task scheduler, intro and intermission timing,
  runtime recipe grouping and table-wrap level requests. See docs/spec/arena-live-scheduler.md.
- Original-function emulator matrix: seeds 20973 and 7, 1–4 players, offline/online,
  30 reconstructed wave states each: 480 wave cases, 4,160 spawn requests,
  512 preload requests, 160 level requests. Occupied-grid/high-score control passed
  on both seeds. Runtime private table outputs are counts only.
- The addressed scheduler wraps recipes and requests continuation; it contains no
  terminal-win check at table exhaustion. Repeating survival is inferred, not proof
  that no external victory condition exists.

Partial
- Spawn, factory, player construction, grid contents, audio/UI and loading remain
  fixture services. Each wave case is reconstructed independently; empty waves are
  supplied by the walker fixture, not earned by combat. No successful load, actual
  creature construction, rendered results or live/native match claim.
- Runtime recipe/class-pointer structural checks cover every recipe group; full
  class-name/factory bindings and a portable shipped-table contract remain incomplete.

Unknown
- Controller-only kills, later creature ticks, natural match completion/final victory,
  results display, fixed reward collection, actual next-level load, destructor flag
  semantics, purchase-candidate qsort tie order, and signed-wave overflow gameplay.
  Existing native refusals remain warranted. No client files were changed.

Commits
- 4b20d40: exact import of mode reference/difftest and prose from audited d4f58da.
- 2df46b01fbae3cd335fdd520bb304c97ddc30343: new scheduler difftest and addressed findings.
- This report is committed separately after those research changes.

Verification (run from this worktree)
- python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_arena_live_scheduler.py",run_name="__main__")' local/SLUS_209.73 --seed 20973
  PASS: all eight configurations, 240 wave cases. Log local/arena-scheduler-20973.log.
- Same command with --seed 7: PASS all eight configurations, 240 wave cases.
  Log local/arena-scheduler-7.log.
- python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_arena_modes.py",run_name="__main__")' local/SLUS_209.73
  PASS: 302 passed, 0 failed.
- python3 -m unittest discover -s tools -p 'test_*.py'
  PASS: 652 tests in 5.446 seconds; log local/unittest.log.
- git diff --check and git diff --cached --check: PASS.
- Initial scheduler invocation without tools on sys.path failed import before any
  execution; corrected command above passed. No emulator execution failures.

No pictures generated (function-level research). No network/public-server contact,
no push/PR, no main commit, no process termination. Private source inputs were read
through local/ symlinks only. No tracked game bytes, raw disassembly or decompiler output.
One dated handoff line is appended to the authorized open-champions COORDINATION.md.


2026-10-27 — A1 audit fix (starting pin 9077656)
- Removed both literal original level-file name lists from docs/arena-modes.md.
  The replacement table records only addresses 0x5037b8 / 0x503798, entry counts
  13 / 7 (excluding null terminators), and mode-selection/rotation roles.
  No name contents are needed as retained evidence; none were copied elsewhere.
- Reviewed all six tracked files added by git diff 77c2f70..9077656 for other
  copied game names/strings, including Python string/byte literals. No additional
  copied game content found; remaining text is research prose, identifiers,
  authored check labels and synthetic fixtures. Removed-name grep over those
  current files returns zero matches. Runtime private-table reads are unchanged.
- Read-only inspection confirms older research-arena-match pin d4f58da carries
  the same two original rows. That branch/pin was not edited.

A1 verification (same commands as Verification above, after the documentation fix)
- Scheduler --seed 20973: PASS, eight configurations / 240 wave cases;
  local/arena-scheduler-a1-20973.log.
- Scheduler --seed 7: PASS, eight configurations / 240 wave cases;
  local/arena-scheduler-a1-7.log.
  Combined: 4,160 spawn, 512 preload and 160 level requests; occupied-grid controls
  passed on both seeds. All commands exited 0.
- Arena-mode difftest: PASS, 302 passed / 0 failed; local/arena-modes-a1.log.
- Unit discovery: PASS, 652 tests in 5.265 seconds; local/unittest-a1.log.
- git diff --check and git diff --cached --check: PASS.
- Only docs/arena-modes.md and this report changed. All execution logs remain
  ignored under local/. No writes to the primary checkout or other worktrees,
  no push, no main commit, and no process termination.
