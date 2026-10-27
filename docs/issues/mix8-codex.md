# Mixed eight-player Hardcore investigation

STATUS: PARTIAL — the Godot RAM-size build inconsistency is fixed; all three shared-simulation room gates and both rig checks pass. The historical tick-219 cause and a complete rendered mixed-room proof remain open.

## Recorded failure

Recompared `local/party8/g8/run/run1` with `tools/rig/compare.py ticks`, including all 28 pairs. Twelve pairs agree (the two groups internally); the sixteen cross-build pairs diverge. The pairs have 4,743–4,804 common ticks.

The first cross-build difference is **`p0state` at tick 219: Godot 3, native 2**. The seed first differs at tick 386. At tick 219 both still report seed `3f5d0b4c` and p0 HP `42033332`. State 3 is the Hardcore flask action (`soulscombat.cpp`, `start_drink`). In this recording, combat action states appear for slots 0, 1, 2 and 6 in the Godot group, and for slots 3, 4, 5 and 7 in the native group. Slot assignment is therefore distinct from the launcher's copy names.

Evidence: `local/mix8-codex/original-g8-pairs-codex/` contains every comparison and `summary-codex.json`. The supplied recording's native log identifies a **16:40** build of `rta_app_next`; the executable present at the start of this investigation was its **17:54** replacement. The old Godot library is still present. No exact copy of that 16:40 executable has been located.

## Confirmed build defect and fix

`tools/godot/build.py` gave the eight-player runtime, rendering and library modules `-DRAM_SIZE=0x04000000u`, but compiled `fpcontrols.cpp` with a separate plain flag list lacking that define. Its `RAM = RAM_SIZE` bounds consequently defaulted to **32 MB**. The native app builder gives every module **64 MB** under `--party8`.

The fix in **`tools/godot/build.py:257–265` and `303–305`** shares the same conditional memory define with the controls module. The affected bound is `tools/recomp/app/fpcontrols.cpp:33–34`, used by the player-body check at line 174; the native builder already applies the define to all jobs at `tools/recomp/app/build.py:197–200`. Ordinary and original builds retain their previous flags. There is no change to the Hardcore rules, guest addresses, or native app implementation.

A fixture linked against the **actual old and rebuilt controls objects**, not a replacement implementation, supplies the same living player at two addresses and calls `fpcontrols::translate`:

| Player address | Old Godot object | Corrected Godot object |
|---|---|---|
| `0x00100000` | Playing, state 2, x=12 | Identical |
| `0x02010000` | Rejected: not playing, state -1, x=0 | Playing, state 2, x=12 |

Fixture, programs and results: `local/mix8-codex/fpcontrols-ram-codex.cpp`, `fpcontrols-{old,fixed}-codex`, and `fpcontrols-ram-results-codex.txt`. `build-flags-codex.json` also records the builder's actual job flags: runtime, controls, Hardcore and library all receive the 64 MB define for a party-eight build, and none receive it for the ordinary build.

**This proves the bounds defect, not that it caused the historical split.** Several mixed runs using the uncorrected Godot controls object also stayed in step through the first flask actions. The tick-219 issue must not be marked resolved solely on this patch.

## Bisect observations

- The available saved Godot and native `soulscombat` objects agree byte for byte. Both compile the Hardcore code for 64 MB with the same arithmetic flags. Both link the Hardcore and party-scaling modules. This does not identify the contents of the replaced 16:40 executable. The second per-player Hardcore block is at `0xe2100`.
- The saved Godot snapshot interprets `party8=poison8` as relocation without poisoning. An older saved native `rta_app_p8` does likewise. Comparing those two alone is not a poison-versus-stale-data test.
- Mixed current-native/old-Godot runs do exercise poisoned native old tables against unpoisoned Godot old tables. The rendered diagnostic `mixed-render-trace-codex` agreed on all 28 pairs for 869–883 ticks. The headless diagnostic `mixed-headless-baseline-codex` agreed for 1,183–1,200 ticks.
- The original drawn-input generator consumes randomness according to the requested play duration. A shortened play duration changes the button sequence. `mixed-early1500-codex` therefore retained the original 1,500-frame input prefix and started input at net tick 200: all 28 pairs agreed for 1,565–1,572 ticks, including p0's flask at tick 226. Its trace records matching input masks, animation clip, pre-state and post-state in both builds. Run-to-run frame/packet timing need not put that input at precisely tick 219.
- The native-only poison/no-poison diagnostic also agreed. Poisoning alone has not reproduced the split with the available executable.
- The extension's 32 MB readers and the controls' four-slot presentation limit are separate known restrictions. They were inspected, but no evidence identifies either as the cause of the recorded shared-state difference. This patch does not claim to extend those interfaces.

## Validation

All builds and evidence are below `local/mix8-codex/` or have `codex` in their binary name. Runs use their own loopback-only rendezvous service. Only processes created for this investigation were stopped. Heavy work used `nice -n 10`. No commit or push was made.

| Gate | Result |
|---|---|
| Python analysis suite | **PASS: 2,208 tests**, `unittest-codex.log` |
| Section 12 overhead rig, fresh `--original` native build | **PASS: byte-identical** to `reference-compare.txt`, 7,797 data rows |
| Section 13 first-person rig, same original build | **PASS: byte-identical** to `s13-first-compare.txt` |
| Eight native copies, Hardcore, forced encounters and level change | **PASS: 4,751–4,758 ticks on all 28 pairs; all eight scripts completed**, `proof-native8-pairs-codex/summary-codex.json` |
| Eight Godot copies, Hardcore, headless Godot engines, drawn input and level change | **PASS: 4,656–4,672 ticks on all 28 pairs; all eight scripts completed**, `proof-godot8-pairs-codex/summary-codex.json` (no forced-encounter pokes in this run) |
| Four headless Godot engines + four native window programs, Hardcore, forced encounters and level change | **PASS: 4,640–4,653 ticks on all 28 pairs; all eight scripts completed**, `proof-mixed8-headless-pairs-codex/summary-codex.json` |

The rig outputs are under `rig-overhead-codex/` and `rig-first-codex/`. `initial-manifest-codex.json` and `final-manifest-codex.json` pin source and executable/library hashes.

The three completed room comparisons include the standard game columns plus **680 per-player Hardcore words**, covering both blocks, and decoded pad fields. Every compared shared column agrees. The mixed run visits `valor` and `drunare`; its final per-slot consumed-flask counters are **8, 6, 5, 9, 7, 5, 8, 11**. Native programs run offscreen through the supplied `as-app.py` adapter. Headless Godot still runs the actual Godot engine, extension and game library; it does not establish rendered-client behavior.

The first long rendered mixed attempt, `proof-mixed8-codex`, is **not a pass**. A frame-based script timeout caused a peer to exit before the level-change gate. Its shortest pair ended at tick 1,840; three pairs later differed from tick 1,859, with a differing dropped-player flag in those ticks. The logs distinguish this departure from the original two-group split at tick 219. Acceptance scripts now allow 90,000 frames for waits while retaining a wall-clock limit and an explicit minimum net-tick gate.

The later `baseline-exact-controls-codex` diagnostic restores the captured Godot library, normal 640×360 rendered context and original small watch set, with logging reduced. The saved mid-run comparison agrees through 1,080 ticks, including p0's flask at tick 654. It was stopped because of rendering stalls, not counted as a 3,000-tick pass. A one-second sample of an owned Godot process contains 703 samples in `RenderingDeviceDriverMetal::fence_wait` (`render-stall-sample-codex.txt`). No other session's process was stopped to obtain a rendered proof.

## Local reproduction and remaining work

`local/mix8-codex/run-room-codex.py` wraps the repository's `n2party.py`; `as-copy-codex.py` selects Godot roles and the pinned native program. Each run preserves its exact `.rig`, watch and tick-command files. `compare-room-codex.py RUN_DIR OUTPUT_DIR 8` invokes the existing comparator for all 28 pairs and requires at least 3,000 common ticks plus completion of every script. Its summary does not equate a launcher exit status with acceptance.

Completed diagnostic `.out` files may be losslessly compressed as `.out.gz`; the original supplied `g8` evidence was left untouched. Generated translations, game files, raw disassembly and logs remain local and are not part of the patch.

The remaining historical-cause gate is a reproducible failing run or the exact native executable used by `g8`; the remaining rendering gate is a complete rendered mixed room without a peer timing out or leaving. The next causal comparison should capture each build's decoded pad row and `w_player_run` pre/post-state around the first difference. Successful current-build comparisons cannot establish a causal fix for a failure that has not been reproduced before the change. **C.11 is not closed by this report.**
