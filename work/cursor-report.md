STATUS: MORE

2026-10-27 — mission-unlock research at base 7efd3ce, branch
t3/research-mission-unlocks. Sibling research-quest-log @03c2304 and the
client play-progression report were read only.

Documented / executed:
- Kept and finished the recovered composed original dialog/script VM probe.
  Fixed direct Python startup despite the repository's stdlib-module shadowing;
  initialized a matching closed-dialog state for admission controls; reject
  implicit emulator fallback calls while retaining explicit host stubs.
- docs/spec/mission-unlocks.md records the 31 normal-mode hub node predicates,
  their script offsets, twelve private variable-pool offsets and start priority.
  General expressions are labeled inferred from bounded original execution.
- First offer's multi-node choice traversal and both second-offer choices execute
  the original mission writer. Dialog opening alone does not write availability.
- Active incomplete missions with nonzero associated quest variables override
  offers. Recall and an existing mission menu suppress entry entirely.
- No copied level-file names, game text, raw disassembly or extracted bytes in
  tracked changes. Private inputs were read through ignored local/ symlinks.

Partial / unknown:
- This is one selected shipped hub dialog on constructed states, with synthetic
  actor/resource lookup and presentation/service stubs. It is not running-game
  or physical actor/trigger reachability proof.
- Full campaign graph AND complete first-act chain remain unknown. Outstanding:
  real level startup and dialog binding/containment, first-act completion writers
  and item/boss gates, other hub/alignment paths, variable mission arguments,
  mission 8/9 grant paths, other turn-ins and replay/repeat conditions, physical
  travel, entire imported records and save/load composition.
- Do not remove the client's general campaign refusal on this evidence.

Commits:
- b6ad45b — early preservation of the recovered 32-case executed baseline.
- d38dad037fae6378e0c6fdc7e164c3b640f0007f — bounded hub predicates and offer
  choices, documentation and strengthened difftest.
- This report is committed separately; its own commit is reported in the reply.

Verification:
- python3 tools/difftest_mission_unlocks.py --elf local/SLUS_209.73 --iso local/game.iso
  PASS: 1,280 first-to-second dialog cases; 3 admission suppressors; 16 isolated
  offer-predicate cases; 20 first-offer choice traversals; 352 hub states and
  10,912 original/model predicate comparisons. Strict implicit-call rejection
  enabled throughout. Exit 0; local/mission-unlocks-final.log.
- python3 tools/difftest_mission_unlocks.py --elf local/SLUS_209.73 --iso local/game.iso --hub-only
  PASS: 352 states; 10,912 predicate comparisons (before final strict-call pass).
- Targeted final-code original-execution controls: PASS, admission 3; first-offer
  traversal/choice 20. These are also included in the full command above.
- python3 -m unittest discover -s tools -p 'test_*.py'
  PASS: 659 tests, 6.170 seconds; local/mission-unlocks-unit-final.log.
- git diff 7efd3ce --check: PASS before report commit; repeat after final commit.

Evidence: local/mission-unlocks-final.log (full emulator run),
local/mission-unlocks-hub.log (bounded hub run),
local/mission-unlocks-unit-final.log. No pictures: no rendered or running-game
acceptance was attempted. No public server contact, push, PR or process killing.
