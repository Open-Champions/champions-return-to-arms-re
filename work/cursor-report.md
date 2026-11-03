STATUS: COMPLETE

2026-11-02 — bounded PPR2-1 mission-menu lifetime research completed on
`t3/research-mission-unlocks`, starting clean at
950b2538ef8f1cb4f5ad26cf3f88fd502c0184f6. COMPLETE describes this research
handoff, including explicit Unknowns; it does not mean full save/load or a
playable campaign is established. No client implementation was changed.

Documented / observed / executed:
- docs/spec/mission-unlocks.md:127-188: original state-4 subtraction tests
  negative, not <=0. Normal cancellation enters with 127; eight later run
  calls produce 111,95,79,63,47,31,15,0. Last call writes -1 then clamps to 0,
  requests chooser input lock 5 and removes both run/draw tasks when the
  transition word is zero. Residual state is 4, counter 0, pending retained.
- Exact-zero controls remain registered for one more call. Constructed nonzero
  transition words take state 5 instead of removing tasks. Explicit removal
  also leaves menu fields behind. Task registration is the observed lifetime
  signal; state/counter/pending proxies are insufficient.
- docs/spec/mission-unlocks.md:190-232: original state-8 arrival remains live;
  the next body removes tasks before publishing a destination. Fade completion
  requires exactly 128. Open resets state, transition word, countdown and
  animation counter, installs the chooser, and retains pending/orientation and
  row/column until state 0 runs. All four chooser slots were tested.
- Ten controls connect real task_isRunning to original dialog/VM execution.
  Closing, exact-zero, launch-arrival, reopened and restored-active menus
  suppress dispatch; terminated/explicitly removed menus admit the controlled
  second-offer node and its original availability writer.
- docs/spec/mission-unlocks.md:234-270: bounded original save_build/save_load
  leave current task registration intact. Build outputs match across five menu
  phases. Direct load publishes saved-level pending/orientation=0xfd but does
  not rewind live counters, restore a menu snapshot or resurrect an absent task.
  An empty-registry restore and same-process restore were both executed.
- Tools are additive: tools/ref_mission_lifecycle.py and
  tools/difftest_mission_lifecycle.py. Existing APIs, references and test vectors
  were untouched. Strict entry-stub and implicit-fallback rejection are enabled.

Partial:
- Original functions execute in tools/ee_emu.py on constructed states, with
  original task scheduling/add/remove/name lookup. No actual game was run.
- Save tests execute one-player header/record-copy paths, with explicit camera,
  jump-gate, snapshot/fixup, quest-variable, act and world-serializer host stubs.
  Current-level test text is synthetic, subname empty, I/O absent. These tests
  establish the direct-body boundary only, not an entire save/reload lifecycle.
- Audio, resources, input-lock/pause-close services and controlled slot/fade
  results are stubbed. Network-mode-byte controls are not network sessions.
- Reference expressions are Inferred client guidance grounded in addressed
  observations. The old countdown limitation and fade-threshold wording are
  superseded explicitly in the new section without modifying the older model.

Unknown:
- Natural reachability of state 4 with a nonzero transition word.
- Full save/load callers, unexecuted serializers, later level teardown and the
  time at which those services might remove/replace a still-registered menu.
- Ordinary-input saving in each tested phase, nonempty saved subnames, card I/O,
  multiplayer save/load, reconstructed world objects, fade/display timing and
  actual launch/travel completion. A pending string alone proves none of these.
- Previously retained first-act/campaign, actor-binding and physical-reachability
  Unknowns remain; no blanket campaign refusal is removed by this research.

Commits (local only):
- fbb90a8432fc16eb8ca2ff64f80dea94d8f0e871 — additive lifetime model and original
  scheduler/menu/save-body/dialog differential probes.
- 4a348fcbf0dcc94155e419516b9b21c59995e982 — addressed specification section.
- This report is a separate final commit; its SHA is the handoff HEAD reported
  in the final reply and the dated COORDINATION.md line.

Verification (all from the assigned research worktree; all exit 0 unless noted):
1. PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission_lifecycle.py --elf local/SLUS_209.73 --iso local/game.iso
   PASS: 30,737 assertions. For each register seed 20973 and 7: six cancellation
   sequences, 24 threshold/nonzero-word controls, three launch columns, three
   explicit-removal guards, four chooser/reopen controls, five save phases with
   same-process and empty-registry restores. Ten composed dialog controls total.
   Log: local/mission-lifecycle.log.
2. PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy,sys; sys.argv=["tools/difftest_quests.py","local/SLUS_209.73"]; runpy.run_path("tools/difftest_quests.py",run_name="__main__")'
   PASS: seven existing properties, zero failures (menu helpers/menu/quest clear/
   hub name/experience/act prefixes/flag-39 decisions).
   Log: local/menu-lifecycle-quests.log.
3. PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission_unlocks.py --elf local/SLUS_209.73 --iso local/game.iso
   PASS unchanged: 1,280 first-to-second dialog cases; three suppressors;
   16 isolated predicates; 20 first-offer traversals; 352 hub states and
   10,912 predicate comparisons. Log: local/menu-lifecycle-unlocks.log.
4. PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
   PASS: 659 tests in 4.250 seconds after final tool edits.
   Log: local/menu-lifecycle-unit.log.
5. PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission_lifecycle.py --elf /dev/null
   Expected refusal: exit 2, unsupported executable digest. A subprocess control
   asserted that result and exited 0. Log: local/menu-lifecycle-digest-refusal.log.
6. git diff 950b2538ef8f1cb4f5ad26cf3f88fd502c0184f6 --check
   PASS. Existing reference/test files unchanged; final status checked clean.

Private evidence: logs above; addressed disassembly used only under ignored
local/ or read-only tool output. No game bytes, raw disassembly, game dialogue
or private inputs are in the tracked delta. No pictures: there was no rendered
or running-game acceptance. No public-server contact, push or PR. Only the
assigned worktree was written, apart from the explicitly requested single dated
append to ~/Projects/open-champions/COORDINATION.md, recorded after the final commit.
