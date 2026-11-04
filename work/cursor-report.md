STATUS: MORE

Audit fix for ordinary mission 1 completion. Code `7428a00` on `t3/research-mission-unlocks` (prior `82bf5b8`, base `e5c6176`). No push. `tools/ref_mission1_complete.py` is unchanged. The call indexes 252, 877, 25, and 50, and the four-record pattern `1,0,0,0` to `3,2,2,2`, stayed.

Documented, in `docs/spec/mission-unlocks.md` lines 279–480:

- Full `grantMission` scan: one argument-1 site in `drunare` `0xac4`, `drunarm` `0x97c`, `strife` `0x1abc`, and `drundar` `0x19ec`; none in `blood1`; `hub` `start` is `grantMission(0)` at `0x28c4`. The four completion entries do not call `setMissionAvailable`, `grantBronze`, `grantSilver`, `grantGold`, or `givePlayerExp`.
- Real `demoRunning` returns 0. `strife` requests `drunarm` and `drundar` requests `drunare`. The planted available-only byte stays 1. Both deferred halves stay empty.
- Evil arena: planted global 0 `0x5a` becomes 0 in `bossDefeatedPause`, and deferred call 1 stores 1. Calls 252 and 877 are asserted. The post action grants bit 1 on all four records and stores `hub2` with orientation `0xff`. Planted gold `0x01020304`, experience `0x05060708`, medal bytes `0x21`+mission, evil `0x2a`, decision `0x3c`, mission 2 `0x40`, and the other rows' `0x50` stay on all four player records. `cutScene` and `reapEnemies` are stubs. Difficulty 1 writes `2` into all four slots of that row.
- Good arena: `start` stores the stubbed item count into global `0xc` (planted `0x5a` becomes 0 or 1) and leaves planted global `0x8` and global 0. The probe then stores 0 into global `0x8`. Before call 25 the cell is 24 and the front half is `shardCheckLoop`. The greater-count call clears the cell and leaves both halves empty. A snapshot of 1 requeues on the front half and grants on call 50. Paused calls leave the planted counter. `addHelpMessage`, `soundSequence`, and `playGotItemSound` are stubs. `inventory_removeItem` records slot 0 and does not walk the bag.
- `rallosHPcheck` queues `endDelay` at stubbed hit points 0 and below, and stores 0 into global `0x10`. At 1 and above it requeues itself and leaves the sentinel. Deferred call 277 runs `playRallosRuns`: post action `removeRallos`, quest count 2 to 1, mission byte still the planted 1. `showMonster`, `cutScene`, and `setSaveInhibit` are stubs. `removeRallos` is only the stubbed `killMonster`, `hideMonster`, and `deleteMonster`. Those three bodies have no `grantMission`.
- Node 7 choice 0 is `setMissic270` at `0x7b0`. Choice 1 is `setMissi3c49` at `0x2064` (also run directly; stubbed `changeSwoop` and `activateStore`). `setMissid125` at `0x7fc` is a third direct writer. Its dialog node is Unknown. `if441a` at `0x198` is the node-3 pending predicate. The unavailable offer stays `0x11c` (`if99a5`).
- Same-act bags and variable values are `6f8beb9` `docs/inventory-reset.md` lines 48–51. Lines 127–129 separate that from an act change.

Partial: `getHitPoints`, the bag walk, cutscenes, monster show/hide/kill, the store open, and `setSaveInhibit` are stubs. The demo/counter grant inside `exitzone` was not entered. `game_getHubName` is read after the probe stores evil and decision; the grant itself leaves the planted bytes.

Unknown: reaching the avatar death or the Rallos trigger, the real hit-point float, cutscene playback, the real bag cell, the loader and arrival after `hub2`, the good path's later return to a hub, the dialog node that reaches `setMissid125`, and `blomedal`.

Commands and results, Mac mini, single process. Logs: `local/mission1-complete-seed20973.log`, `local/mission1-complete-seed7.log`, `local/mission1-complete-unit.log`.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","20973"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","7"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["unittest","discover","-s","tools","-p","test_*.py"]; runpy.run_module("unittest", run_name="__main__")'
```

Seed 20973: PASS, checks 1170, notice-call 252, end-call 877, hp 0/1, rallos-call 277.
Seed 7: PASS, checks 1170, notice-call 252, end-call 877, hp 0/1, rallos-call 277.
Analysis tests: 659, OK, 4.968s.
