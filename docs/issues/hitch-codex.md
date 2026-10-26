STATUS: NOT MET — rendering fixes implemented and measured; steady 60+ fps with no visible hitches is not established.

2026-10-26. Baseline: `e1d87ed`. The requested isolated output is `local/godot-codex3`. The original approximately 128 ms result was reproduced: the first three baseline runs had a median hub maximum of **128.871 ms**. The final patch still has frames above 25 ms. The final core-route median hub maximum is **89.705 ms**, but machine load changed too much to treat the aggregate difference as a controlled causal estimate. Water/boss results become worse under the much higher later load. No commit or push was made.

The work fixes measured CPU stalls, redundant uploads/readbacks, and two scheduling problems encountered during the repair. It does **not** remove indivisible Godot uploads, all runtime pipeline work, or the long intervals inside rendering. Some per-frame causes and the exact visible/black boundary remain unresolved; the ledgers preserve those uncertainties.

**Build and measurement method.** Ran `RTA_GODOT_OUT=local/godot-codex3 python3 tools/godot/build.py all` through `nice -n 10`, then rebuilt the changed extension and staged the final scripts. [Initial build](../../local/hitch-codex/build.log), [all build](../../local/hitch-codex/build-final.log), [final clean extension/project build](../../local/hitch-codex/merge-clean-build.log). The final extension was checked for the absence of temporary profiler/assertion strings as well as checking source. Restoring an older source timestamp can otherwise leave an instrumented object in Ninja's output; the restored sources were explicitly rebuilt.

Godot 4.5.2, Metal 3.2 Forward+, Apple M5 Pro; requested scene size 1280 × 720, window 640 × 360, Remastered, chase/shoulder views, `--display-rate 60`, muted sound output while the sound system continues to run. Commands used `nice -n 10`; the inherited nice value made the observed process nice value 15, consistently. No unrelated processes were signalled or terminated. The test window used main.gd's partly offscreen test placement; these are engine frame timings, not measured OS display scanout timings.

Each run booted normally using the existing `boot-to-hub.rig`, then used the existing rig controls and pending-level route. Each stop includes intro-answer taps, idle, movement, camera turning, five attacks, shoulder view and chase view. The script also sets the documented test invulnerability flag and camera-follow mode; these are test inputs, not source changes. This is a bounded scripted workload, not a campaign playthrough. Core route: `hub → fire1 → arachna1 → water1 → drunare`. Supplemental route: `hub → islsm3b → fearboss`, added after visual inspection exposed limited water1/drunare coverage. Before and after use byte-identical scripts within each route, verified by SHA-256:

- Core: `e5dddae5e0fad178591a757c0ff988c0628c47f42c4e0fb354a463493ff4f005`
- Supplemental: `736f3371e64ca851bbe12202dc197824e7cca14eb8a09f7117be70048fff76ab`

The same art pack, ER folders, settings, game library and shared warm caches were used. No shader/asset caches were cleared between timed runs. First-use/cold-cache behavior is therefore **not** fully covered by the reported warm-run medians. Native profile, exact-result checks, screenshots, and GPU profiling used separate diagnostic runs and are not included in these medians.

Timing options were `--frame-log frames.csv --speed-log 120`, plus `RTA_SUBMIT_LOG=12`, `RTA_LOG_PIPELINES=1`, `RTA_MEASURE_VIEWPORTS=1`. Temporary wrappers recorded ER/remaster/scene phase times, level, simulation tick, loading flag, draw count and pipeline counter deltas. Native scopes isolated world classification, mesh creation, batching and art uploads. All instrumentation was removed from tracked source and the named build; reproductions and instrumented copies remain only under ignored `local/hitch-codex/`.

[Runner](../../local/hitch-codex/bench.py), [core route](../../local/hitch-codex/finish-1/route.rig), [supplemental route](../../local/hitch-codex/water-boss-after-1/route.rig), [analysis](../../local/hitch-codex/summarize.py). To repeat a staged route, use the runner's `run STAGE NEW_TAG` command; set `bench.LEVELS` as in [supplement runner](../../local/hitch-codex/run_supplement.py) for the supplemental route. Credentials and private source paths are read locally and are not embedded in this report.

**Load and repeatability.** Each final condition was measured twice, interleaved. Medians below are the median of each run's statistic, not pooled percentiles (each percentile uses linear interpolation); a fractional count is the arithmetic midpoint of two integer counts. All runs completed normally. Load averages are context, not proof of the cause of an individual hitch. In particular, control-finish-2 deteriorated without any code change; the later supplemental tests ran with load averages in the hundreds. These results cannot establish a reliable percentage speedup, nor can every residual delay be blamed on external load.

| Run, in execution order | Exit | Seconds | 1-minute load: start → end |
|---|---:|---:|---:|
| [finish-1](../../local/hitch-codex/finish-1/summary.json) | 0 | 135.883 | 8.73 → 10.94 |
| [control-finish-1](../../local/hitch-codex/control-finish-1/summary.json) | 0 | 135.763 | 10.86 → 20.05 |
| [finish-2](../../local/hitch-codex/finish-2/summary.json) | 0 | 137.786 | 20.05 → 13.17 |
| [control-finish-2](../../local/hitch-codex/control-finish-2/summary.json) | 0 | 230.157 | 13.17 → 66.30 |
| [water-boss-before-1](../../local/hitch-codex/water-boss-before-1/summary.json) | 0 | 125.920 | 28.55 → 269.75 |
| [water-boss-after-1](../../local/hitch-codex/water-boss-after-1/summary.json) | 0 | 182.855 | 269.75 → 490.29 |
| [water-boss-before-2](../../local/hitch-codex/water-boss-before-2/summary.json) | 0 | 161.177 | 490.29 → 408.27 |
| [water-boss-after-2](../../local/hitch-codex/water-boss-after-2/summary.json) | 0 | 284.010 | 408.27 → 431.87 |

**Frame-time results.** These are `main.gd`'s successive `_process` start gaps, in milliseconds. A gap belongs to the preceding turn's work, so the analyzer aligns phase timing to that preceding turn. On a ProMotion display, repeated refresh turns can be faster than the game's 60 Hz picture handoffs. An 8 ms p50 does not demonstrate 120 game frames per second.

The conservative exclusion is only `loading != 0 && draw_count == 0`. It retains fades, first-world work, visible loading art and uncertain boundary frames. It is not a pixel-exact detector of the actual blank screen. This intentionally avoids deleting all startup stalls, but means the retained counts can include some genuinely black frames. The exact requested count of *visible-only* hitches has not been established.

| Level | Before p50 / p99 / max (ms) | After p50 / p99 / max (ms) | Before >25 ms | After >25 ms |
|---|---:|---:|---:|---:|
| hub | 18.087 / 86.482 / 182.448 | 12.128 / 21.734 / 89.705 | 335.5 | 11.5 |
| fire1 | 19.874 / 106.484 / 215.712 | 10.639 / 30.697 / 72.915 | 294.5 | 148 |
| arachna1 | 21.476 / 39.418 / 76.440 | 14.823 / 32.843 / 38.923 | 328.5 | 153.5 |
| water1 | 12.043 / 46.615 / 82.779 | 7.090 / 20.989 / 30.944 | 80 | 4.5 |
| drunare | 22.706 / 52.361 / 83.531 | 7.561 / 33.035 / 52.678 | 557 | 173 |
| islsm3b | 24.882 / 53.380 / 151.291 | 35.049 / 78.472 / 154.201 | 528.5 | 564 |
| fearboss | 20.654 / 40.165 / 126.571 | 41.332 / 67.418 / 111.172 | 257.5 | 484 |

For comparison with the reported starting point, the initial three baseline runs (`before-1`, `before-2`, `before-3`, load roughly 8–10) had these medians: hub **8.335 / 17.485 / 128.871 ms, 4** frames >25 ms; fire1 **8.800 / 16.767 / 49.666, 4**; arachna1 **8.810 / 15.650 / 24.322, 0**; water1 **8.333 / 9.294 / 24.748, 0**; drunare **8.609 / 19.894 / 44.840, 5**. These earlier low-load samples are retained, not substituted for the final paired controls.

The following second table uses intervals between turns with `new_picture == 1`. It describes game-picture handoffs, not OS presentation. It prevents repeated refreshes from hiding a slow game-picture rate.

| Level | Before p50 / p99 / max (ms) | After p50 / p99 / max (ms) | Before >25 ms | After >25 ms |
|---|---:|---:|---:|---:|
| hub | 22.280 / 91.190 / 182.448 | 16.018 / 32.257 / 89.705 | 392.5 | 84.5 |
| fire1 | 30.770 / 114.131 / 215.712 | 19.544 / 36.569 / 72.915 | 312 | 159 |
| arachna1 | 22.335 / 41.211 / 78.194 | 19.171 / 34.404 / 39.130 | 339 | 192 |
| water1 | 16.901 / 57.373 / 100.825 | 15.562 / 33.843 / 58.288 | 198.5 | 44.5 |
| drunare | 27.038 / 53.981 / 83.531 | 19.767 / 36.093 / 60.599 | 605 | 182.5 |
| islsm3b | 25.331 / 59.766 / 151.291 | 35.474 / 85.748 / 158.805 | 536 | 561.5 |
| fearboss | 20.797 / 43.051 / 138.869 | 41.621 / 83.887 / 160.846 | 266.5 | 481 |

Final median mean handoff rates: hub **58.73/s**, fire1 **49.94/s**, arachna1 **50.705/s**, water1 **59.155/s**, drunare **50.29/s**, islsm3b **32.165/s**, fearboss **36.41/s**. None of this is a steady-60 acceptance result. Boot/menus are retained separately in each summary: the final two runs include a **1027.226 ms** interval at blank 4, with **0.278 ms** in the main turn and **1025.925 ms** between render callbacks, no pipeline-counter increase. It is unresolved rendering/driver/scheduling time, not a removed CPU startup cost.

**Every recorded long interval.** [Combined refresh-hitch CSV](../../local/hitch-codex/final-hitches.csv) enumerates every logged gap >25 ms in the eight final runs, including rows marked `excluded_load_blank`. [Combined new-picture-hitch CSV](../../local/hitch-codex/final-picture-hitches.csv) also lists >25 ms picture-handoff intervals that span several shorter refresh turns. The combined ledgers contain **14,925 refresh gaps** and **16,046 picture-handoff gaps**; none of these >25 ms rows met the conservative no-draw loading predicate. Each run retains its original `frames.csv`, `output.log`, `figures.txt`, `summary.json` and individual ledgers. `usec` is monotonic microseconds since that Godot process began; `blank` is the game display-list number, **not a boolean blank-screen flag**. Rows include level, simulation tick, route marker, phase times, render wall time and pipeline deltas. The `cause` column identifies the largest measured contributor or explicitly says unresolved; nested phase times must not be added together.

**Hitches and changes.** Numbers in this table are diagnostic observations, not interchangeable with the repeated-run medians.

| When / evidence | Cause found | Fix and source | Result / remaining cost |
|---|---|---|---|
| Boot, list 57; `profile-1/2` | Warming the complete GS shader history synchronously: `scene_begin` 220.552 / 248.013 ms. | [rta_drawer.cpp:186](../../tools/godot/extension/src/rta_drawer.cpp#L186): sorted warm queue, stop starting work after 1 ms; retain warm instances through several render turns. [rta_scene.cpp:784](../../tools/godot/extension/src/rta_scene.cpp#L784) retires them after completion. | A diagnostic incremental first turn was 5.547 ms. An individual shader/mesh call can still exceed the budget; this is not a hard 1 ms deadline. |
| First use of Remaster/ER materials | `user://rta_variants.txt` records GS variant bits; it does not cover these independent shaders or mesh layouts. | New [material_warmup.gd:1](../../tools/godot/project/material_warmup.gd#L1), driven by [scene_view.gd:469](../../tools/godot/project/scene_view.gd#L469): zero-area meshes in the real scenario for remaster_model, er_armour, er_ruin and ER grass MultiMesh; 0/4/8 bone layouts where applicable, compressed/uncompressed, grass colors/custom data. One item per turn within the shared resource budget. | Same shader files and visual settings. This covers the exercised base layouts, not every shadow/render-state pipeline permutation; runtime pipeline increments remain in the ledger. |
| Hub first world, list 2365; `profile-2` | Classifying 177 textures cost 37.813 ms inside a 39.617 ms world scan, alongside 972 surface additions (11.409 ms). | [rta_world.cpp:145](../../tools/godot/extension/src/rta_world.cpp#L145), [315](../../tools/godot/extension/src/rta_world.cpp#L315), [rta_scene.cpp:837](../../tools/godot/extension/src/rta_scene.cpp#L837): at most four native worker tasks over immutable CPU textures and captured light/options; join before consumption; exact-input cache, serial fallback. Model-only texture classification is deferred while retaining its original first-draw light/options. | 639 live comparisons matched the serial calculation exactly. A later native diagnostic showed 2.196 ms main-thread world scan but 18.145 ms worker join under load; surface additions still cost 28.335 ms. First-world submission remains a major boundary hitch, not solved outright. |
| ER body fitting at first appearance | `_fit_job` repeatedly fetched render mesh arrays back from Godot; its maximum was 21.307 / 21.125 / 20.726 ms in the initial runs. | [er_layer.gd:696](../../tools/godot/project/er_layer.gd#L696), [2216](../../tools/godot/project/er_layer.gd#L2216), [2602](../../tools/godot/project/er_layer.gd#L2602): reuse the exact arrays read for winding; persist them in a private compressed cache keyed by GLB SHA-256, cache version and Godot version. Worker file I/O; atomic replacement; no object deserialization. | Final `_fit_job` maxima 0.805 / 0.622 ms. First cold-cache readback remains. `ImporterMesh.get_mesh()` is still indivisible and reached 22.854 ms in a final run. |
| First full body snapshot for fitting | Thousands of PackedArray `push_back` bindings in `get_skeletons(with_mesh)`; one diagnostic measured 13.296 ms. | [rta_machine.cpp:303](../../tools/godot/extension/src/rta_machine.cpp#L303): resize once and fill writable storage with the same expressions/order. | Exact comparison of all nine output arrays against the original loop passed. No game memory is written. |
| First fitted outfit/material arrivals | Multiple surfaces/materials could be uploaded in one turn; alpha readback was performed even on materials whose names cannot use an alpha cutout. | [er_layer.gd:2283](../../tools/godot/project/er_layer.gd#L2283): surface-at-a-time fitted-mesh upload under the shared 4 ms budget. [2563](../../tools/godot/project/er_layer.gd#L2563): check the existing card-name rule before reading alpha. [model_remaster.gd:486](../../tools/godot/project/model_remaster.gd#L486): budget packet preparation. | Original fallback remains until complete. Exact mesh arrays, surface names and effective shader parameters passed; a spent-budget test deferred work. A single API call may overrun. |
| First HUD draw; `visual-entry` | Lazy image/cache decoding, Lanczos resizing and texture creation: status 21.990 ms plus bottom 23.465 ms, outside the main submit timing. | [gameart.gd:53](../../tools/godot/project/gameart/gameart.gd#L53), [88](../../tools/godot/project/gameart/gameart.gd#L88), [hud_skin.gd:41](../../tools/godot/project/gameart/hud_skin.gd#L41): private CPU image preparation on a worker, same resize algorithm; textures uploaded on the main thread within the shared budget. | 27 warmed texture sizes matched original pixels. Extra retained CPU images/textures trade memory for first-use work. This does not precompile every HUD canvas pipeline. |
| Periodic character-card capture during play | The same private game texture was uploaded separately for many of roughly 246 captured packets; scene-end bursts were about 22 ms in diagnostics. | [rta_card.cpp:51](../../tools/godot/extension/src/rta_card.cpp#L51), [164](../../tools/godot/extension/src/rta_card.cpp#L164): one exact private texture copy per texture ID per capture, shared by packets, freed once. | No geometry, pixel, draw-state or capture-selection change. Packet mesh creation is still synchronous; no claim that every capture is below 25 ms. |
| Bursts as art-pack workers finish | The original limit was bytes (48 MB), allowing several expensive uploads in one turn. | [rta_drawer.cpp:1031](../../tools/godot/extension/src/rta_drawer.cpp#L1031): additionally stop starting uploads after 2 ms. | Existing pixels/mipmaps/RID replacement preserved. A single upload still reached 27.333 ms in a diagnostic; public calls cannot be preempted. |
| Periodic resource cleanup | Expired mesh/material destruction shares the main frame with new work. It was a contributing burst, not isolated as the sole cause of every affected >25 ms gap. | [rta_drawer.cpp:243](../../tools/godot/extension/src/rta_drawer.cpp#L243), [rta_scene.cpp:1466](../../tools/godot/extension/src/rta_scene.cpp#L1466): retire unused RIDs and drain with a 1 ms budget; fully drain on release. | Visual lifetime/expiry criteria preserved. Destruction can overrun for one indivisible call; temporarily retains unused resources. |
| Repeated control-run script errors | A whole figure deliberately assigned to ER had no remaster `name`, but the material loop indexed it. Core controls logged 988 such errors per run. | [model_remaster.gd:427](../../tools/godot/project/model_remaster.gd#L427): skip those ER-owned figures in remaster material preparation. | Zero script errors in final core and supplemental timed runs. |
| Regression in an intermediate native-worker candidate | Speculative classifications skipped by fusion were thrown away, launching 35–60 unnecessary jobs per sampled fire1 frame. | [rta_world.cpp:307](../../tools/godot/extension/src/rta_world.cpp#L307), [366](../../tools/godot/extension/src/rta_world.cpp#L366), [rta_drawer.h:316](../../tools/godot/extension/src/rta_drawer.h#L316): keep results, compare exact tint/options, invalidate on texture replacement/deletion. | Steady sampled frames returned to zero jobs; rare new inputs still schedule work. Rejected runs are retained and excluded from final medians. |
| Arachna1 regression after spreading preparation | Finished merge jobs only released their two worker slots when the same model was visited again. A model leaving the view/level, or a cached grouping being reused, could strand both slots and leave later figures on costly fallback rendering. | [model_remaster.gd:137](../../tools/godot/project/model_remaster.gd#L137), [664](../../tools/godot/project/model_remaster.gd#L664), [678](../../tools/godot/project/model_remaster.gd#L678): reap completed CPU merges globally; retain exact results for later budgeted upload. | Reproduction occupied both slots with departed models, blocked a third, then verified both slots released and the third started. Crossed script/native builds isolated the regression. Arachna1 median native submit returned from 8.535 ms to 3.316 ms (baseline 3.233 ms). |
| Residual steady arachna1 intervals | In finish-1, 143 of 148 retained >25 ms gaps were dominated by rendering. Example: blank 4724, 86.853283 s, 39.373 ms gap; main turn 6.314 ms, render wall 31.938 ms; no pipeline increment. | No speculative visual-quality reduction or gameplay change applied. | Unresolved within Godot/driver/scheduling. The render-wall timer is not GPU duration. |

Godot allows private CPU resource preparation on workers but restricts active scene-tree work; GPU-facing calls and scene generation stay on the main thread here. See [Godot 4.5 thread-safe APIs](https://docs.godotengine.org/en/4.5/tutorials/performance/thread_safe_apis.html). The GLTF importer call's unsliced surface loop is visible in [Godot's ImporterMesh implementation](https://github.com/godotengine/godot/blob/4.5/scene/resources/3d/importer_mesh.cpp). Pipeline counts are interpreted using [Godot's pipeline-compilation guidance](https://docs.godotengine.org/en/4.5/tutorials/performance/pipeline_compilations.html); a counter increment alone is not a measured compilation duration.

**Visibility and remaining attribution limits.** Separate captures were inspected for hub, fire1, arachna1, water1, drunare, islsm3b and fearboss. The ER outfit, world materials, foliage, lighting and creature geometry remain present. These are visual spot checks, not whole-frame pixel identity across asynchronous runs. The earlier water1 route ends on a mission-complete dialog; drunare includes scripted scenes. The supplemental fearboss route also reaches a mission-complete dialog (simulation stops at tick 452), so it is a boss-entry/short-sequence measurement, not a sustained boss-fight soak. Images: [core](../../local/hitch-codex/gpu-visual/), [water/boss](../../local/hitch-codex/water-boss-visual/).

Earlier world-viewport entry captures were black around the first hub frame, but that alone does not establish the whole window was blank. The later root-viewport probe sampled only the first 60 distinct display lists after each level-name change, which can precede the first world submission; [visibility samples](../../local/hitch-codex/visibility-samples.json) are partial evidence, not permission to discard the 128 ms boundary. Exact per-frame blank-screen classification remains open. No additional hitch was silently excluded on the strength of these screenshots.

`--gpu-profile` was tried in the separate `gpu-visual` diagnostic. All 166 reported GPU totals were 0.0 ms; the default 256 timestamp-query limit also overflowed. This run is excluded from performance numbers. The viewport GPU timer likewise returned zero, so GPU execution time and the precise driver/scheduler contribution are **unavailable**, not zero. A trial reconstruction of picture-completion intervals from later callback rows was rejected because callbacks can remain stale across loading/unchanged rendering; only the documented main-loop/handoff measurements above are used.

**Validation and boundaries.** [Exact-result checks](../../local/hitch-codex/checks-result3.txt) passed for barbarian/necromancer/sword GLTF geometry, skeletons and effective material parameters; cancellation drained workers; remaster regrouping preserved surfaces/groups; fitted uploads preserved mesh arrays/names/parameters and obeyed an exhausted budget. [HUD check](../../local/hitch-codex/art-verify.log) passed 27 pixel comparisons. [Merge lifecycle check](../../local/hitch-codex/merge-verify.log) passed with the final scheduling fix. [Native cache validation](../../local/hitch-codex/cache-validation/output.log) passed 639 exact serial/worker classifications; the earlier skeleton comparison checked all nine arrays.

The game library used for every comparison is byte-identical to the initial one:
`0150c220e0f5486ea1dab5a28c834de4e5cb8079eb8473d777d6006b3925a220`.
An `all` rebuild regenerated testerkit's build timestamp, so the original library was deliberately pinned back into this task's output/staged comparisons. No native gameplay, party8, net2 or reloc source was changed. A bounded two-client comparison with the earlier rendering candidate compared **1298 shared ticks with no shared-column differences**, both exits 0; it ended before the requested full second-level interval and is not a completed multiplayer soak of the final merge-scheduling change. [Bounded room result](../../local/hitch-codex/room-result.log).

`er_world.gd`, `er_world_fit.py`, and `er_ruin.gdshader` have **no edits** from this work. The changes are the five changed extension `.cpp` files plus `rta_drawer.h`, `er_layer.gd`, `model_remaster.gd`, `scene_view.gd`, the two gameart scripts, and new `material_warmup.gd`. Cache and deferred-release memory costs were not isolated under the changing load; the helper's cumulative child high-water RSS is not used to claim a per-run memory improvement. All private assets, game libraries, raw logs and diagnostic copies remain local. `git diff --check` passed.

The remaining gates are concrete: eliminate or move the measured indivisible first-use work into proven non-visible preparation; attribute the residual renderer intervals with usable GPU/CPU scheduling evidence; obtain exact blank-screen classification; repeat full active water/boss gameplay and final multiplayer validation. The current implementation must not be described as hitch-free or steady 60+ fps.

**Per-run refresh figures, retained for audit.**

| Run | Level | Samples | p50 / p99 / max (ms) | >25 ms |
|---|---|---:|---:|---:|
| finish-1 | hub | 1392 | 14.027 / 26.248 / 104.733 | 19 |
| finish-1 | fire1 | 1383 | 12.477 / 34.035 / 72.353 | 256 |
| finish-1 | arachna1 | 1243 | 15.105 / 33.581 / 39.373 | 148 |
| finish-1 | water1 | 2187 | 6.912 / 18.073 / 26.442 | 2 |
| finish-1 | drunare | 1777 | 7.673 / 30.760 / 52.461 | 96 |
| control-finish-1 | hub | 1575 | 10.853 / 31.051 / 158.569 | 39 |
| control-finish-1 | fire1 | 1404 | 10.652 / 24.554 / 50.449 | 14 |
| control-finish-1 | arachna1 | 1163 | 16.895 / 28.813 / 33.628 | 61 |
| control-finish-1 | water1 | 1534 | 9.767 / 21.231 / 30.573 | 2 |
| control-finish-1 | drunare | 1246 | 13.996 / 39.653 / 75.228 | 295 |
| finish-2 | hub | 1856 | 10.230 / 17.220 / 74.677 | 4 |
| finish-2 | fire1 | 1580 | 8.800 / 27.360 / 73.476 | 40 |
| finish-2 | arachna1 | 1287 | 14.541 / 32.105 / 38.474 | 159 |
| finish-2 | water1 | 1773 | 7.268 / 23.905 / 35.445 | 7 |
| finish-2 | drunare | 1705 | 7.449 / 35.310 / 52.895 | 250 |
| control-finish-2 | hub | 1249 | 25.322 / 141.913 / 206.328 | 632 |
| control-finish-2 | fire1 | 1104 | 29.096 / 188.415 / 380.975 | 575 |
| control-finish-2 | arachna1 | 1034 | 26.056 / 50.023 / 119.252 | 596 |
| control-finish-2 | water1 | 1213 | 14.318 / 71.998 / 134.985 | 158 |
| control-finish-2 | drunare | 1078 | 31.416 / 65.069 / 91.834 | 819 |
| water-boss-before-1 | hub | 1148 | 26.753 / 62.499 / 459.260 | 762 |
| water-boss-before-1 | islsm3b | 1007 | 21.816 / 48.097 / 139.681 | 364 |
| water-boss-before-1 | fearboss | 1028 | 16.975 / 35.970 / 109.311 | 63 |
| water-boss-after-1 | hub | 1174 | 26.163 / 64.807 / 293.929 | 713 |
| water-boss-after-1 | islsm3b | 1008 | 19.429 / 41.419 / 107.475 | 185 |
| water-boss-after-1 | fearboss | 1024 | 16.657 / 26.939 / 86.252 | 15 |
| water-boss-before-2 | hub | 1142 | 34.118 / 77.944 / 509.123 | 997 |
| water-boss-before-2 | islsm3b | 1004 | 27.948 / 58.664 / 162.900 | 693 |
| water-boss-before-2 | fearboss | 1013 | 24.333 / 44.359 / 143.831 | 452 |
| water-boss-after-2 | hub | 1162 | 63.832 / 123.209 / 672.689 | 1008 |
| water-boss-after-2 | islsm3b | 1008 | 50.669 / 115.525 / 200.927 | 943 |
| water-boss-after-2 | fearboss | 1020 | 66.007 / 107.897 / 136.093 | 953 |
