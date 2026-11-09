STATUS: MORE (M1-9..M1-13 fixed and rerun; the Unknowns below remain open)

Second audit fix for ordinary mission 1 completion (M1-9..M1-13 of the re-audit at `74f11b6`). Code and spec `59f2bb4` on `t3/research-mission-unlocks` (prior `74f11b6`, `7428a00`, `82bf5b8`; base `e5c6176`). No push. `tools/ref_mission1_complete.py`, `tools/ee_emu.py`, and `tools/ref_natives.py` are unchanged. The call indexes 252, 877, 25, 50, and 277, and the four-record pattern `1,0,0,0` to `3,2,2,2`, stayed.

New oracle this round: `tools/difftest_mission1_complete.py` hooks the first instruction of every native handler that is not in `STUB_NAMES` (the original body still runs) and logs it with the stubbed ones, in order. It also logs each entry `script_runByName` `0x1ed694` starts. "Recorded" below means that log.

- M1-9: `callScria381`'s recorded list is `callScript`, `addDeferedCall`. The only entries started are `callScria381` and `bossDefeatedPause`. No stub runs, and the entry has no script-to-script `call` op. Running `bossDefeatedPause` alone stores 0 into global 0 and queues `bossDefeatedDelay`. That direct run is the evidence for attributing the store to it. The knight entries `setv4d6b`/`setv772a`/`setv5138`/`setvcccf` store 1 into `knight1`..`knight4` with the other three planted `0x5a`..`0x5d`, and the other three stay planted. `knightDefeatedPause` reads all four and queues `knightDefeatedDelay` only when all four are set. Globals, mission bytes, and the record sentinels stay. The completion entries have no `getv`, no `callScript`, no internal `call`, and no constant `knight*` argument. Two non-constant pushes in `shardCheckLoop` are named and not decoded.
- M1-10: `removeRallos`'s recorded list is five stubs and nothing else: `killMonster`/`hideMonster`/`deleteMonster` on `rallos`, then `hideMonster`/`deleteMonster` on `rallos2`. The earlier "those three" was a set and undercounted the calls.
- M1-11: the call-50 grant now reads back `3,2,2,2` on slots 0–3 and a planted global 0 `0x5c`.
- M1-12: `playGotItemSound` is asserted entered (stubbed) on both granting calls, and the full recorded list of each granting call is asserted.
- M1-13: the client note now says `blood1` has no `grantMission` site and gives no `blood1` exit request. `strife` → `drunarm` and `drundar` → `drunare` stay as executed with `demoRunning` 0.

Documented, in `docs/spec/mission-unlocks.md` lines 279–524:

- Full `grantMission` scan: one argument-1 site in `drunare` `0xac4`, `drunarm` `0x97c`, `strife` `0x1abc`, and `drundar` `0x19ec`; none in `blood1`; `hub` `start` is `grantMission(0)` at `0x28c4`. The four completion entries do not call `setMissionAvailable`, `grantBronze`, `grantSilver`, `grantGold`, or `givePlayerExp`.
- Real `demoRunning` returns 0. `strife` requests `drunarm` and `drundar` requests `drunare`. The planted available-only byte stays 1. Both deferred halves stay empty.
- Evil arena: `callScria381` starts only `bossDefeatedPause` (recorded). Planted global 0 `0x5a` becomes 0 in `bossDefeatedPause` (also run alone), and deferred call 1 stores 1. Knight deaths store their own `knightN` and queue `knightDefeatedDelay` only when all four are set. Calls 252 and 877 are asserted. The post action grants bit 1 on all four records and stores `hub2` with orientation `0xff`. Planted gold `0x01020304`, experience `0x05060708`, medal bytes `0x21`+mission, evil `0x2a`, decision `0x3c`, mission 2 `0x40`, and the other rows' `0x50` stay on all four player records. `cutScene` and `reapEnemies` are stubs. Difficulty 1 writes `2` into all four slots of that row.
- Good arena: `start` stores the stubbed item count into global `0xc` (planted `0x5a` becomes 0 or 1) and leaves planted global `0x8` and global 0. The probe then stores 0 into global `0x8`. Before call 25 the cell is 24 and the front half is `shardCheckLoop`. The greater-count call clears the cell and leaves both halves empty. A snapshot of 1 requeues on the front half and grants on call 50, writing `3,2,2,2` and leaving planted global 0. Paused calls leave the planted counter. Each granting call's recorded list is asserted. It enters the stubs `playGotItemSound` and `addHelpMessage`, and `endmission` enters the stubs `addHelpMessage` and `soundSequence`. `inventory_removeItem` records slot 0 and does not walk the bag.
- `rallosHPcheck` queues `endDelay` at stubbed hit points 0 and below, and stores 0 into global `0x10`. At 1 and above it requeues itself and leaves the sentinel. Deferred call 277 runs `playRallosRuns`: post action `removeRallos`, quest count 2 to 1, mission byte still the planted 1. `showMonster`, `cutScene`, and `setSaveInhibit` are stubs. `removeRallos`'s recorded list is the five stubbed calls `killMonster`/`hideMonster`/`deleteMonster` (`rallos`) and `hideMonster`/`deleteMonster` (`rallos2`); none is executed for real. Those three bodies have no `grantMission`.
- Node 7 choice 0 is `setMissic270` at `0x7b0`. Choice 1 is `setMissi3c49` at `0x2064` (also run directly; stubbed `changeSwoop` and `activateStore`). `setMissid125` at `0x7fc` is a third direct writer. Its dialog node is Unknown. `if441a` at `0x198` is the node-3 pending predicate. The unavailable offer stays `0x11c` (`if99a5`).
- Same-act bags and variable values are `6f8beb9` `docs/inventory-reset.md` lines 48–51. Lines 127–129 separate that from an act change.

Partial: `getHitPoints`, the bag walk, cutscenes, monster show/hide/kill/delete, item and help sounds, the store open, and `setSaveInhibit` are stubs. The demo/counter grant inside `exitzone` was not entered. `game_getHubName` is read after the probe stores evil and decision; the grant itself leaves the planted bytes.

Unknown: what `knightDefeatedDelay` / `knightDefeated` do (not run), reaching the avatar death or the Rallos trigger, the real hit-point float, cutscene playback, the real bag cell, the loader and arrival after `hub2`, the good path's later return to a hub, the dialog node that reaches `setMissid125`, and `blomedal`.

Commands and results, Mac mini, single process. Logs: `local/mission1-complete-seed20973.log`, `local/mission1-complete-seed7.log`, `local/mission1-complete-unit.log`.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","20973"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","7"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["unittest","discover","-s","tools","-p","test_*.py"]; runpy.run_module("unittest", run_name="__main__")'
```

Seed 20973: PASS, checks 1229, notice-call 252, end-call 877, hp 0/1, rallos-call 277.
Seed 7: PASS, checks 1229, notice-call 252, end-call 877, hp 0/1, rallos-call 277.
Analysis tests: 659, OK, 5.047s.

The check total rose from 1170 to 1229 because of the new static assertions and the eight knight runs.
