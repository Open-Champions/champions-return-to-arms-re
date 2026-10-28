# fire1 Remastered frame hitches — 2026-10-27

**STATUS: PARTIAL — causes isolated and exact-result optimizations implemented; fire1 stutter is not resolved.** The quiet baseline is dominated by CPU scene handoff plus waiting for the game/decoder, not steady GPU saturation. The retained-instance trial improved one matched pair and not the reverse-order repeat. Later full-resolution and 120 Hz runs were heavily contended. Do not treat the patch as a demonstrated hitch-free 60/120 Hz fix.

Base: `799d583`, equal to `origin/main` when work began. No commit or push. Private evidence is ignored under `local/fire1-codex/`; supplied evidence is `local/hitch-codex/l38-run/`. Original game files, captures and raw profiler output remain local.

## Method and controls

Godot 4.5.2, Metal Forward+, Apple M5 Pro, actual display **120.00 Hz**. Muted tests run with `nice -n 10` (effective nice 15 because the parent already had nice 5), the existing cache, separate card directories and the same hub → fire1 → arachna1 → water1 → drunare route. The shorter repeats use the identical hub/fire1 prefix. Other playtest processes were left alone. Only owned failed/stalled processes and obsolete owned measurement queues were stopped; no `pkill` or `pgrep -f` was used.

`gap_usec` ends at the next main-loop turn: compare it with the preceding row's `process_usec`, `wait_usec`, `submit_usec` and temporary phase samples. The following row's `draw_usec` is the intervening RenderingServer wall interval. `submit_usec` includes before-frame, native submission and after-frame work. Nested timings must not be added. These are engine loop intervals, not OS scanout measurements. Game frames/s below comes from `game_frame`, not the old `new_picture` flag that also counts some held turns at 120.

The existing **RtaGpuTimer** records the union of completed Metal command-buffer GPU spans without waiting or adding GPU work. Its `G` rows arrive asynchronously; a nearby sample is not an exact causal match to a particular hitch. Godot's ordinary viewport GPU columns are zero here. RenderingServer wall time includes CPU work and waits; it is not GPU time. The auxiliary injected Metal probe produced no data and is not evidence.

Temporary GDScript wrappers measured ER/remaster phases; native wall/thread-CPU scopes and sampling separated active CPU work from waits. Per-draw native scopes added substantial overhead, so that run is used for attribution, not speedup claims. All temporary probes were removed from production source and the named build; private instrumented test stages are retained as evidence.

The first full-size harness forced 16:9 and actually rendered 3492×1964. `before-full` and `fidelity-1` do not count as the requested size. Correct runs pass **`--size 3024x1964 --aspect 3024:1964`**, confirmed by image dimensions. Two owned attempts stalled in the intro: samples showed 3611/3622 and 2202/approximately 2205 main-thread samples under Metal `fence_wait` / `_stall_for_frame`. Both were captured and stopped, then repeated successfully. The trigger of those fence stalls remains unknown.

## Causes

1. **CPU handoff and game-frame waits recur without pipeline compilation.** The supplied fire1 data is p50 **12.313 ms**, p99 **36.103 ms**, **122/1357** intervals >25 ms. `before-1` reproduces **12.672 / 33.870 ms**, **144/1351**. All 144 baseline hitches have no pipeline-compilation delta. Their largest measured indicators are drawer work on 84, game-frame wait on 52, ER work on 2, and 6 outside the measured main turn. These identify contributors, not exclusive root causes.
2. On those hitches, medians are **4.484 ms wait**, **15.672 ms handoff**, **19.077 ms main process**, **8.666 ms RenderingServer wall**, and **4.627 ms nearby GPU**. Fire1's overall GPU p50/p99 is **4.053/7.565 ms**, at unchanged 4× MSAA / native scale throughout. Steady GPU saturation and governor transitions do not explain that quiet-run tail.
3. The native diagnostic shows submit wall/thread CPU close together (about **12.2/11.3 ms**, inflated by per-draw probes), active packet/batch construction and uploads. `RtaMachine.step` samples wait in `rtag_poll`'s condition variable. The rendering profile also includes **`place_mesh → instance_set_base → geometry_instance_free/create`**: earlier draws entering/leaving the list move retained meshes between pooled instances and rebuild renderer state.
4. In the crowded diagnostic window, ER frame work averages **5.678 ms**: `_draw_figure` **5.237**, `_skin` **1.408**, `_place` **0.659**, light lookup **0.574**, creature discovery **0.401 ms**. Native SH light fitting costs about **1.41 ms thread CPU** on measured fit turns. No bone, fit, animation or LOD cadence was reduced.
5. **Bake completions are not the repeated quiet-run cause.** Mean bake polling, merging and ER fit completion on baseline hitches are **0.021 / 0.029 / 0.000 ms**. Existing resource work is already asynchronous/budgeted. RenderingServer uploads and shared scene mutation remain on the main thread.
6. **Full-resolution entry has a separate allocation/pipeline component.** In `before-full-native-2`, the largest fire1 gap is **182.813 ms**, at blank 3426: **99.809 ms main**, **81.534 ms RenderingServer wall**, five new draw pipelines. Governor reallocation and GPU pressure matter there. The governor, upload semantics, shaders and quality settings are unchanged.
7. **Later runs are externally contended.** Host load rose from 9 to above 20; hub degraded along with fire1. A contemporaneous aggregate process check showed browser processes consuming about **947% CPU**, Godot processes about **320%**, and load **17.25**. See `host-pressure.json`. No browser/process state was changed. This is evidence of a confounded measurement window, not proof that all remaining fire1 stalls are external.

## Retained changes and locations

| Files / lines | Change and preservation rule |
|---|---|
| `tools/godot/extension/src/rta_drawer.h:144`, `rta_drawer.cpp:504`, `rta_drawer.cpp:936`, `rta_scene.cpp:276`; `tools/godot/project/scene_view.gd:456` | Reuse a render instance per retained mesh occurrence, keyed by the complete RID. Preserve material and draw order; hide unused instances immediately; retire after 30 unused frames through the existing 1 ms destruction budget. Multiple uses of one mesh stay separate. Enabled only for Remastered; Classic keeps the original pool. Extra retained instances are the memory tradeoff. |
| `tools/godot/extension/src/rta_remaster.cpp:1061` | Accumulate the upper triangle of the symmetric SH normal matrix and mirror it before the unchanged solver. Each cell keeps its original summation order. **13,080 live reference fits matched exactly**. Six alternating synthetic timing pairs were approximately **0.161–0.162 → 0.126 ms/fit** (22% less). |
| `tools/godot/extension/src/rta_remaster.cpp:994`, `rta_remaster.h:71`, binding `rta_remaster.cpp:1444`; `tools/godot/project/er_layer.gd:1570` | Submit the existing ER bone palette in one native call per mesh, retaining the old-extension fallback. Validate all input before mutation. Use the engine's `Variant` transform operator; an extension-side multiply differed in its final bit and was rejected. A 106-bone microbenchmark was roughly **10–14 → 4–5 µs/mesh**; this is not a whole-frame claim. |
| `tools/godot/project/er_layer.gd:1546`, `er_layer.gd:1683`; invalidation at `er_layer.gd:133`, `:168`, `:1510` | Skip identical light-parameter dictionaries and unchanged material/layer/depth installation. Compare actual resources/values, copy cache values, and invalidate on figure/weapon RID release. Pose, bounds, visibility and ordering still update. |
| `tools/godot/project/main.gd:498`, `:728`, `:1138`, `:1214` | Use the existing ahead-of-presentation release path for paced Remastered at the 60 setting. Keep the display-locked 60 Hz game clock, no additional world redraws at 60, and restore Classic scheduling when switching edition at the same rate. |
| `tools/godot/project/dev/frame_pacing_test.gd:1`, `dev/skin_palette_test.gd:1` | Regression checks for 60/120 displays/rates, jitter, stall recovery, Classic switching, exact RenderingServer bone transforms, missing bones and invalid-input refusal before mutation. |

The pacing change trades earlier input sampling/frame age for less waiting on the presentation turn. In the `before-final-3` / `after-safe-1` pair, wait p99 fell **13.962 → 7.051 ms**, while median release-to-take age rose **21.849 → 32.876 ms** and lead rose from 1 to 3 refreshes. **About 11 ms more frame age is a material tradeoff**, not an input-latency improvement.

A proposed `model_depth.gd` setter cache was removed entirely. Original depth setters remain unchanged. No gameplay/core source, shader, visual feature, governor threshold or fit cadence is changed.

## End-to-end measurements

All figures include the route's entry and camera transitions, as in the supplied benchmark. Raw logs, route hashes, load start/end and analyses live in each named directory. Counts depend on the number of main-loop turns, so both numerator and denominator are shown.

### 1280×720, 60 setting, fire1

`before-*` is original code. `stable-*` is the final patch, except `stable-control-*`, which has the palette/light/pacing changes but the original drawer pool. This separates the last optimization from the rest.

| Run | Load start → end | p50 / p99 / max ms | >25 ms / intervals | Game frames/s | GPU p50 / p99 ms |
|---|---:|---:|---:|---:|---:|
| `before-1` | 6.53 → 5.34 | 12.672 / 33.870 / 61.814 | 144/1351 | 51.97 | 4.053 / 7.565 |
| `before-quiet` | 1.92 → 5.14 | 11.780 / 37.189 / 55.455 | 157/1354 | 50.71 | 4.193 / 8.272 |
| `before-final-2` | 6.51 → 5.40 | 12.539 / 38.213 / 65.706 | 129/1355 | 51.87 | 3.993 / 7.860 |
| `before-final-3` | 7.03 → 6.29 | 14.932 / 38.085 / 72.534 | 162/1277 | 50.00 | 4.458 / 8.659 |
| `stable-control-1` | 4.35 → 5.63 | 13.372 / 38.030 / 61.257 | 173/1363 | 51.15 | 4.141 / 8.621 |
| `stable-1` | 5.63 → 7.64 | 13.006 / 33.203 / 54.914 | 136/1378 | 52.67 | 4.042 / 8.364 |
| `stable-2` | 7.83 → 7.29 | 20.113 / 49.395 / 163.817 | 487/1111 | 40.07 | 4.672 / 10.298 |
| `stable-control-2` | 7.29 → 8.61 | 19.846 / 49.409 / 147.355 | 472/1123 | 39.68 | 4.712 / 9.965 |

The isolated first pair improves p99 **38.030 → 33.203 ms**, >25 ms intervals **173/1363 → 136/1378**, and RenderingServer p99 **13.989 → 12.217 ms**. The reverse-order pair is essentially flat at **49.4 ms p99**, with 487 vs 472 >25 ms intervals; hub is also slow (~56 ms p99). Earlier palette/light/pacing repeats likewise did not consistently reduce hitch counts. **A repeatable quiet-run end-to-end reduction is not established.**

### Exact 3024×1964, 60 setting

| Run | Load start → end | p50 / p99 / max ms | >25 ms / intervals | Game frames/s | GPU p50 / p99 ms |
|---|---:|---:|---:|---:|---:|
| `before-full-native-2` | 5.59 → 7.17 | 23.064 / 48.262 / 182.813 | 508/1093 | 39.44 | 7.790 / 11.135 |
| `stable-full` | 9.01 → 15.85 | 25.073 / 65.069 / 140.438 | 562/1119 | 33.30 | 7.894 / 16.112 |

| Level, 3024×1964 / 60 setting | Original p99 ms / >25 ms | Final p99 ms / >25 ms |
|---|---:|---:|
| hub | 51.279 / 136 | 49.472 / 97 |
| fire1 | 48.262 / 508 | 65.069 / 562 |
| arachna1 | 32.192 / 125 | 54.370 / 245 |
| water1 | 16.520 / 6 | 25.825 / 18 |
| drunare | 43.696 / 114 | 39.532 / 70 |

The original full-resolution fire1 spends 1080 logged intervals at 2× MSAA/native and 13 at 4×/native. The final full run is reported under the much higher load shown above; it cannot confirm an improvement. An earlier candidate without retained-instance reuse completed a quieter full route (`after-full-safe-2`, load 4.74→4.77) at **33.848 ms p99, 189/1244 >25 ms**. That is preserved as intermediate evidence and is **not substituted for the final patch's result**.

### 120 setting on the verified 120 Hz display, 1280×720

| Run | Load start → end | p50 / p99 / max ms | >25 ms / intervals | Game frames/s | GPU p50 / p99 ms |
|---|---:|---:|---:|---:|---:|
| `before-120` | 6.53 → 6.31 | 20.148 / 54.464 / 159.874 | 500/1130 | 39.07 | 4.982 / 10.668 |
| `before-120-repeat` | 15.85 → 22.30 | 30.101 / 78.541 / 163.570 | 644/1059 | 29.86 | 6.112 / 15.349 |
| `stable-120` | 22.30 → 20.78 | 29.781 / 89.987 / 256.273 | 655/1085 | 28.47 | 6.205 / 25.250 |

The final high-load pair does not demonstrate improvement or sustained 120 Hz. The existing controller suppresses intermediate pictures when the game frames themselves miss their deadlines; those held turns must not be counted as fresh game frames. The earlier pre-retained-instance candidate reached 52.64 game frames/s in a quieter run (`after-120-safe`), but that does not establish final-patch performance.

A five-minute wait did not obtain a load ≤8 measurement window. No other process was stopped or reprioritized. A quiet final-patch confirmation remains blocked by concurrent host activity.

## Visual and Classic verification

At each probe, the game tick, camera, animation state and spring starting state are held; quality is fixed to 4× MSAA and native scale. Eight states cover all five levels plus fire1's idle, visible 19-figure crowd, attack and shoulder views. Captures and the rendered window were inspected.

- **ER material/light caching and native palette:** `fidelity-safe-run`, 24 world comparisons at exactly 3024×1964 and 24 window comparisons. Every comparison is pixel-identical: **SSIM 1.0, MAE 0**.
- **Retained native instances:** `fidelity-retained-run` holds the already posed ER/remaster actors unchanged and switches only original/new native placement. All 24 world comparisons pass **SSIM ≥0.999999878775**; 23 are pixel-identical. All 24 window comparisons are pixel-identical. It includes repeated candidate and ending original controls.
- **SH fit:** 13,080 live old/new coefficient comparisons are exactly equal, in addition to the synthetic check and rendered-image gates.
- **Replay caveat:** repeatedly resubmitting held poses produced arachna1 differences below 0.999, including in ending original-setter controls (0.997221; combined pose/placement replay 0.997493). The cause of that replay instability is not isolated. The discarded depth cache is not retained. The passing gates isolate each changed path and apply a pose once, rather than treating repeated original-control instability as a new-code regression. They do not prove every frame of an arbitrary live session identical.
- **Classic:** the original and pre-retained-instance candidate hub/fire1 captures are exactly equal, SSIM 1.0. The final Classic repeat and its result are recorded below. Classic has no GPU timer records, no Remastered models or extra world redraws; its 60 Hz scheduling branch and drawer pool remain selected.

## Build, checks and remaining gate

Requested initial commands completed:

```sh
RTA_GODOT_PARTY8=1 RTA_GODOT_OUT=local/godot-codex-f1 python3 tools/godot/build.py snapshot --refresh
RTA_GODOT_PARTY8=1 RTA_GODOT_OUT=local/godot-codex-f1 python3 tools/godot/build.py all
```

The final all-build also passes. Build IDs normally include a timestamp and dirty marker, so an ordinary relink changed only that metadata in the game library. The final rebuild pins the original ID to preserve **the complete gameplay library byte for byte**:

```sh
RTA_GODOT_PARTY8=1 RTA_GODOT_OUT=local/godot-codex-f1 RTA_BUILD_ID='799d583 2026-10-27 05:08' python3 tools/godot/build.py all
```

SHA-256 of original, every measured stage and final `librta_game.dylib`:
`158864b7a34b92429b26c960ab3f8022938221f91b9c7e9cab029f869e699903`.
The final extension SHA-256 is `5eca6f6861a2b9ac0b6028c0a35c9bfef005f18be4598d325eab411e17400e01`, identical to the measured `stable-trial` extension. See `final-build-hashes.json` and `gameplay-preservation.json`. No measurement used the relink with the newer build-ID stamp.

Final named-build checks: `gpu_quality_test` PASS, `frame_pacing_test` PASS, `skin_palette_test` PASS.

Final Classic screenshots: hub SSIM 1.000000000, exact=True, fire1 SSIM 1.000000000, exact=True.

Remaining gate: **repeatable reduction of fire1's >25 ms intervals under comparable quiet load, including final full-resolution and 120 Hz behavior**. CPU work and renderer/decoder synchronization still exceed the budget in measured runs; the separate Metal intro fence-stall trigger is unresolved. The local patch is reviewable and its retained changes pass the stated isolated visual gates, but the requested stutter fix must not be marked complete. `git diff --check` passes. No commits or pushes were made.

Reproduction harness: `local/fire1-codex/run.py` (private configuration is read internally; no secret arguments need to be printed), `analyze.py`, `images.py`, `check_windows.py`. `stable-trial/project` contains the instrumented measurement stage; `local/godot-codex-f1/project` is the clean runnable build. Native diagnostic source, samples and failed/repeated controls remain private for audit. All seven final performance/fidelity/Classic runs exited zero with no script or engine errors (`final-log-check.json`). `final-audit.json` records the clean-build source match and absence of temporary probes.

**Merged 2026-10-27 without the pacing change.** The main.gd change (ahead-of-presentation release at 60, about 11 ms more frame age) was left out: input delay is not traded for smoothness. With the remaining exact-result changes, back-to-back on a quiet machine (load 2-4), fire1 on the bench route: before p50 12.9 / p99 31.8 ms, 62 intervals over 25 ms; after p50 11.7 / p99 22.0 ms, 5 over 25 ms. A first run of the merged build gave p99 19.3 ms, 2 over 25 ms; hub, arachna1, water1, drunare stayed at p99 16-17 ms.
