STATUS: MORE

Ordinary mission 1 completion is executed. Commit `1dbe373` on `t3/research-mission-unlocks` (base `e5c6176`). No push.

Documented, in `docs/spec/mission-unlocks.md` lines 279–424:

- Real `demoRunning` returns 0. `strife` `exitzone` requests `drunarm` and `drundar` `exitzone` requests `drunare`. Neither sets the complete bit.
- Evil arena: avatar death entry `callScria381` queues the delay. Deferred call 252 sets `endsound` and `firstmissionever`. Call 877 runs `endmission` (quest remove, post action `levelChange`) and still does not grant. `script_runPostAction` runs `levelChange`: `grantMission` `0x1420a4` sets bit 1 on all four records, and `newWorld` stores `hub2` with orientation `0xff` even when the evil and decision bytes are clear.
- Good arena: `start` snapshots `playerHasItem('shardofwar')`. Unpaused deferred call 25 grants when the live count is higher. A snapshot of 1 waits until call 50. The post action is help and sound only. No hub request. A count above 1 also removes one cell; a rise from 0 to 1 does not.
- Hub conditions and row helper `0x231078` see that byte. Mission 2 stays unavailable until `setMissic270` or `setMissid125`. `game_getHubName` still needs evil, decision, and the complete bit.

Partial: `getHitPoints` is stubbed, and the script takes the Rallos outro delay only when that cell is 0 or below. That chain does not grant. `inventory_removeItem` records the call and does not walk the bag. The demo/counter grant inside `exitzone` was not re-run; the real native does not enter it.

Unknown: reaching the avatar death or the Rallos trigger, cutscene playback, the real bag cell, the loader and arrival after `hub2`, the good path's later return to a hub, and `blomedal`.

Commands and results, Mac mini, single process:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","~/malik-champions/open-champions/private-validation/rta-disc/BG/DATA","--seed","20973"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","~/malik-champions/open-champions/private-validation/rta-disc/BG/DATA","--seed","7"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["unittest","discover","-s","tools","-p","test_*.py"]; runpy.run_module("unittest", run_name="__main__")'
```

Seed 20973: PASS, checks 1145, notice-call 252, end-call 877, hp 0/1.
Seed 7: PASS, checks 1145, notice-call 252, end-call 877, hp 0/1.
Analysis tests: 659, OK, 5.646s.
