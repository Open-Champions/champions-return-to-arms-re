STATUS: NOT MET — the adaptive GPU-quality implementation is built and validated, but sustained 60 game frames/s is not established in arachna1, hub or fire1. The final arachna1 repeats reached 36.44 and 44.36 FPS under shared load. No commit or push.

2026-10-26, worktree baseline `73f789a`. Scope: Remastered, Godot 4.5.2 Metal Forward+, Apple M5 Pro, 3024 × 1964 world pixels. No commit or push. All private assets, images, traces and raw logs remain under ignored `local/aa-codex/` through the existing `local/` symlink.

**What the GPU is doing.** Read [fps-verdict.md](fps-verdict.md) for the original quiet-machine diagnosis. Godot's GPU profiler, RenderingDevice timestamp results and RenderingServer viewport GPU times were all zero in this run. Zero is unavailable data. The [4.5.2 Metal implementation](https://raw.githubusercontent.com/godotengine/godot/4.5.2-stable/drivers/metal/rendering_device_driver_metal.mm) clears timestamp results with `bzero`; it does not implement those queries.

A private Metal probe records completed command-buffer GPU start/end times and, for detailed experiments only, public stage-boundary counters on render and compute passes. A 60.89-second Metal System Trace attributes GPU activity to the task's child. The final runtime observer adds completion handlers only: no GPU commands, counters, altered render descriptors or CPU waits. Command-buffer elapsed times and stage intervals can include preemption and resource contention. Even process-attributed trace activity is measured on the shared GPU, not an isolated device. Diagnostic counter instrumentation is not used in the normal live FPS runs.

Fixed-tick probes retain the same presented game frame and camera, freeze animation time, discard 60 warm-up renders and collect the next 120. The AA/upscaler comparisons use the baseline host with the requested diagnostic setting held fixed, without the adaptive controller. Pictures come directly from the world target, RGB8. MAE uses the 0–255 channel scale; SSIM uses scikit-image, `data_range=255`, averaged across channels. Repeated baseline captures are pixel-identical. A displayed GS buffer can retain the preceding frame, so initial displayed-buffer comparisons were rejected. Moving the staged project also required explicit paths to the existing ER assets. Early probes without those paths are excluded. An out-of-order hub route mistakenly stayed in the previous level; those **hub-labelled image results are excluded**. The runner now requests hub explicitly when necessary, and the probe asserts the actual game level before capturing.

`cost-probe-2`, arachna1, presented tick 2860, first adjacent 4×/2× pair: median stage elapsed milliseconds below. Pass names were independently confirmed in `quality-probe-1` after correcting ownership of temporary diagnostic label strings. Vertex and fragment stages overlap; do not add the table into a frame total.

| Work | 4× | 2× | Interpretation |
|---|---:|---:|---|
| Engine depth prepass, vertex / fragment | 0.060 / 0.002 | 0.026 / 0.001 | Almost empty |
| Opaque pass, vertex / fragment | 0.046 / 0.001 | 0.025 / 0.001 | Almost empty |
| Shadow atlas passes, sum of fragment medians | 0.088 | 0.079 | Single-sampled 4096² targets; small |
| Light-cluster compute | 0.013 | 0.012 | Small |
| Ordered transparent world, vertex / fragment | 0.304 / **24.043** | 0.234 / **19.454** | Main cost, including the custom solid-depth prepass |
| Colour resolve, fragment | 0.778 | 0.422 | AA changes this, but it is not the main cost |
| Depth resolve, compute | 0.686 | 0.333 | Same |
| Glow compute, sum of medians | 0.259 | 0.234 | Small |
| Tone mapping, fragment | 0.682 | 0.642 | Single-sampled |
| Two canvas/copy passes, fragment | 0.330 | 0.275 | Single-sampled; separate presentation buffer also exists |
| World-containing command buffer elapsed, median | **28.983** | **24.265** | Includes contention; not the sum above |

The repeated alternating trace samples give a more useful comparison than a single sequential run:

| Pair | 4× command buffer p50 | 2× command buffer p50 | 4× attributed GPU union/frame | 2× attributed GPU union/frame |
|---|---:|---:|---:|---:|
| 1 | 28.219 ms | 24.265 ms | 24.258 ms | 20.973 ms |
| 2 | 28.337 ms | 23.625 ms | 24.232 ms | 20.787 ms |
| 3 | 29.200 ms | 25.467 ms | 24.975 ms | 20.908 ms |

Pair 1 has 73 fully captured baseline frames and 120 2× frames; the other rows have 120 per setting. The process-attributed reduction is **13.5–16.3%**. In pair 2 the main transparent fragment activity alone falls from 20.690 to 17.662 ms/frame. A late baseline repeat outside the trace rises to 58.370 ms command-buffer elapsed: contention is large enough to invalidate an unqualified before/after FPS claim.

Turning off the **custom** solid-depth prepass preserves the picture exactly but increases trace GPU union/frame to 26.713 ms, versus nearby 24.002–24.975 ms baselines. Retain it. Turning off the **engine** prepass removes a roughly 0.06 ms vertex pass and was pixel-identical at this tick; that is not a material solution. These are different prepasses. The world already uses a dedicated multisampled 3-D target; the canvas, presentation and shadow targets are single-sampled. Selective material MSAA would require separating the ordered world into different targets and preserving its compositing order. No such unverified renderer rewrite is included.

A tween calls the drawer's full retained-pass redraw, including the world. Fixed-tick redraws confirm that it pays the world pass again. In the heavy normal-play portions of the diagnostic route, the existing lag gate already prevented tween world draws; no additional FPS gain from the new GPU gate is claimed there. The new gate can hold them before average game-frame lateness becomes the only signal. Lighting, fog, bloom, world content and material shaders remain unchanged; the pass evidence does not identify a cheaper material substitution with a verified equivalent picture.

**Final fallback pictures, all four verified levels.** `final-picture-probe` checks the live level name before capture. Presented ticks: hub 2821, arachna1 3829, fire1 4846, water1 5848. Every ending 4× control equals its initial control exactly (MAE 0, SSIM 1). These are the corrected all-level results; the following experiments at other ticks are supplementary.

| Level | 2× native MAE / SSIM | No MSAA native MAE / SSIM | No MSAA, 95% bilinear MAE / SSIM | No MSAA, 75% bilinear MAE / SSIM |
|---|---:|---:|---:|---:|
| hub | 0.20227 / 0.9963676 | 0.36639 / 0.9921378 | 1.67197 / 0.9715655 | 2.26712 / 0.9534749 |
| arachna1 | 0.07690 / 0.9982195 | 0.12601 / 0.9967421 | 0.31054 / 0.9954242 | 0.63139 / 0.9930242 |
| fire1 | 0.04462 / 0.9986418 | 0.07512 / 0.9972726 | 0.43514 / 0.9916953 | 0.59042 / 0.9886785 |
| water1 | 0.04476 / 0.9990253 | 0.08256 / 0.9977056 | 2.05683 / 0.9414995 | 2.66757 / 0.9172072 |

The last row shows why a scale reduction is a last resort: water1's fine detail changes substantially more than native-resolution AA changes. The governor does not guarantee a pixel-identical picture while reducing quality.

The same final fixed-tick experiment measured the following world command-buffer medians (milliseconds, 120 samples per setting, stage-counter instrumentation enabled). Initial and ending 4× controls bracket each sequence. These durations include contention; their absolute values must not be compared directly with the uninstrumented live-route figures below.

| Level | Initial 4× | 2× | No MSAA | No MSAA, 95% | No MSAA, 75% | Ending 4× |
|---|---:|---:|---:|---:|---:|---:|
| hub | 23.164 | 23.682 | 8.857 | 8.448 | 5.855 | 24.809 |
| arachna1 | 68.230 | 48.819 | 33.844 | 28.749 | 20.735 | 65.613 |
| fire1 | 21.712 | 21.618 | 6.640 | 6.632 | 5.123 | 21.203 |
| water1 | 18.785 | 17.283 | 7.648 | 6.992 | 5.017 | 21.533 |

**Quality choice.** 2× native is the first reduction. Further pressure now removes MSAA at native resolution before resizing the world: in the measured scenes, this costs less GPU time and changes fewer reference pixels than scaled 2×. Spatial image metrics do not measure temporal edge shimmer; reduced edge coverage is the tradeoff of this emergency step.

| Same-tick setting | arachna1 MAE / SSIM | water1 MAE / SSIM |
|---|---:|---:|
| 2× native | 0.05865 / 0.9985266 | 0.03742 / 0.9992162 |
| No MSAA, native | 0.10496 / 0.9969780 | 0.07108 / 0.9980827 |
| No MSAA + FXAA, native | 0.18290 / 0.9958570 | 0.93993 / 0.9770688 |
| 2×, 95% bilinear | 0.42990 / 0.9920472 | 2.05780 / 0.9441373 |
| No MSAA, 95% bilinear | 0.43469 / 0.9917696 | 2.06136 / 0.9439150 |

`fxaa-probe-1`, arachna1 tick 2860, water1 tick 3864. FXAA is rejected because it changes texture detail more. Arachna1 command-buffer medians in this sequence: 4× 49.679 ms, 2× 43.144 ms, no MSAA 28.307 ms, FXAA 27.719 ms, ending 4× 54.514 ms. This supports the lower-cost fallback under that load; it does not establish 60 FPS.

For resizing, bilinear is closer to the reference than FSR or MetalFX in both test scenes and removes the FSR sharpening passes. `scaler-probe-1`, 2× at 95% scale:

| Upscaler | arachna1 MAE / SSIM | water1 MAE / SSIM | arachna1 / water1 command-buffer p50 |
|---|---:|---:|---:|
| Existing FSR | 0.81145 / 0.9828199 | 3.43792 / 0.9150876 | 30.339 / 13.919 ms |
| Bilinear | **0.42990 / 0.9920472** | **2.05496 / 0.9444545** | 28.177 / 12.624 ms |
| MetalFX spatial | 1.03030 / 0.9759034 | 4.10542 / 0.8950377 | 29.217 / 14.312 ms |

Absolute timing deltas between these sequential samples remain confounded by sharing. Bilinear's image result is consistent across 95%, 85% and 75% scales. Explicit user-selected scaling/upscaling retains its existing mode; the new bilinear choice applies to the governor's default fallback.

**Implementation.** Default Remastered quality remains requested 4×/native while measured GPU work fits. The controller targets 14 ms; it holds interpolated world redraws when they exceed 80% of a refresh, requires 0.4 seconds of sustained pressure after cooldown, and steps through 4× → 2× → no MSAA → 95/90/85/80/75% world scale. It restores the best predicted-safe quality after eight seconds below a conservative 11.5 ms prediction, and restores tweens after two seconds below 65% of a refresh. Quality changes have 1.5–2 second cooldowns. Invalid, stale and zero GPU samples cannot restore quality. `--look adaptive_aa=off` bypasses the policy.

Loading, warm-up, pending level changes, cutscenes, colour fades and fade-waits hold quality. The HUD fade word can retain 128 during normal play: the guard combines changes with actual submitted full-screen overlays, following [fade-lifetime.md](../fade-lifetime.md). All game-state reads are read-only. Classic bypasses the policy and never creates its native observer.

| File / location | Change |
|---|---|
| `tools/godot/project/gpu_quality.gd:1` | Pure GPU-pressure controller, quality order, bounds, cooldown and recovery prediction |
| `tools/godot/project/scene_view.gd:888`, `:936` | Apply world-only quality; read completed samples; fade/loading guards and optional diagnostic G rows |
| `tools/godot/project/main.gd:1056`, `:1280`, `:1295` | Mark world draws, gate tween redraws, bracket renderer frames |
| `tools/godot/extension/src/rta_gpu_timer.h:9`, `rta_gpu_timer.cpp:8` | Godot binding and public native-queue acquisition |
| `tools/godot/extension/src/rta_gpu_metal.mm:1` | Passive completed-buffer observer, frame-span union and callback lifetime management |
| `tools/godot/extension/src/rta_drawer.cpp:937`, `rta_drawer.h:72` | Read-only detection of submitted full-screen flat overlays |
| `tools/godot/extension/CMakeLists.txt:76`, `src/register.cpp:27` | Apple Objective-C++ build/link and class registration |
| `tools/godot/project/dev/gpu_quality_test.gd:1` | Budget, redraw, AA order, fade hold, invalid sample, hysteresis, recovery and bounds assertions |

The Metal observer installs the public `commit` selector on the concrete class returned by Metal and filters to this renderer's queue; it does not name a private driver class. Pending callbacks retain their state. The extension already disables hot reload. Other rendering backends use RenderingServer viewport timings when available; their runtime behaviour has not been verified here.

**Final live measurements.** These are normal paced route runs, with completion callbacks only, no stage counters or GPU profiler. All use `--mute` and `nice -n 10`, isolated cards/configuration and the established FPS-verdict route, in order hub → arachna1 → fire1 → water1. Only task-owned processes have been stopped. GPU figures union completed command-buffer spans for game-frame tags in idle→end play; FPS counts actual game frames, not 120 Hz pictures. Each cell is **game FPS · GPU p50 / p90 milliseconds**.

| Level | Baseline (`baseline-final-1`) | Final candidate, run 1 | Final candidate, run 2 |
|---|---:|---:|---:|
| hub | 43.64 · 13.775 / 19.725 | 37.13 · 9.085 / 19.445 | 45.78 · 7.525 / 12.926 |
| arachna1 | 29.17 · 25.958 / 93.805 | 36.44 · 9.028 / 29.519 | 44.36 · 8.482 / 40.215 |
| fire1 | 36.06 · 12.073 / 19.083 | 29.12 · 6.893 / 12.865 | 38.95 · 6.498 / 10.930 |
| water1 | 59.02 · 14.975 / 24.983 | 59.29 · 7.924 / 14.872 | 59.94 · 7.045 / 11.252 |

Candidate run 1's slowest seconds were 26/22/20/56 game frames; run 2's were 35/29/29/59, in the level order above. A lower median GPU span does not prove a 60 FPS frame budget: arachna1 still has large GPU-duration tails, and other host work and scheduling also take time.

Execution order and sharing evidence:

| Run | Exit | Duration | GPU utilisation before launch | One-minute CPU load, start → end |
|---|---:|---:|---|---|
| `candidate-final-1` | 0 | 180.562 s | 68/52/52% | 9.8 → 25.4 |
| `baseline-final-1` | 0 | 161.960 s | 75/0/40% | 10.3 → 10.2 |
| `candidate-final-2` | 0 | 150.289 s | 49/0/69% | 8.0 → 11.2 |

All three completed without script errors. In candidate run 2, the sampled hub, fire1 and water1 play frames used native resolution without MSAA; arachna1 stepped as low as 80% then restored native resolution. Run 1 reached the 75% floor in arachna1. Therefore the final all-level image table describes the actual fallback tradeoffs, not a claim that lighter levels always retain 4× under contention.

Baseline repeats also varied: `baseline-live-3` gave arachna1 27.45 FPS / 31.609 ms GPU p50; `baseline-live-repeat` gave 24.56 FPS / 22.985 ms. Earlier `candidate-live-*` results used the superseded 2×-minimum/FSR prototype and are not final-policy acceptance results. Their complete data remains in `live-comparison.jsonl` and each run's `aa-stats.json`.

No run satisfied the original quiet gate of GPU <25% and CPU load <20 across the preflight samples. A final 12-group quiet check, after the task's games had exited, also failed every group: GPU group means were 35.7–85.3%, with CPU load 7.3–10.2 (`quiet-check.json`). The runs demonstrate lower GPU cost and the quality tradeoff; they do not isolate a causal FPS improvement from changing machine load. Host processing wall time can include waits and scheduling, so it is not proof of a new CPU-bound diagnosis.

**Validation checkpoint.** The requested build was run successfully:

```
RTA_GODOT_PARTY8=1 RTA_GODOT_OUT=local/godot-codex-aa python3 tools/godot/build.py all
```

The final extension was rebuilt and scripts staged after later changes. `dev/gpu_quality_test.gd` passes; `git diff --check` passes. The initially built game library is pinned back into the final output because rebuilding regenerates tester metadata. Baseline and candidate gameplay libraries have identical SHA-256 `413e20a4551ab08b7fd3efe1b603eb9b7c08839b9fb22c059926378beff2bc2e`. No gameplay source was edited.

A real two-client baseline/candidate local room passed (`lockstep-2`): A recorded 1,396 ticks, B 1,393, and **all 1,393 shared ticks matched every shared watched column**. This includes 1,120 hub ticks and 273 arachna1 ticks. Only expected per-machine input/draw-frame columns differ. The candidate made seven quality transitions, including AA and scale changes; none occurred in an ineligible/fade record. The two final live routes had 10 and 7 transitions, respectively, with zero ineligible transitions across 5,583 and 5,567 quality records. This is a bounded two-client check, not a campaign or long-session verdict. The private portal test fixture inherited current portal defaults and selected the current party-size menu; the initial failed fixture launch is excluded.

`classic-control-1` confirmed no native observer, policy disabled and zero G-quality records in all four levels. Explicit adaptive-on captures equal the initial control pixel-for-pixel; adaptive-off captures equal the ending control pixel-for-pixel. There is a small alternating difference between the two control captures themselves: maximum MAE 0.01521 and minimum SSIM 0.999634, in arachna1. It is not an additional difference caused by the policy. Post-probe movement/attack FPS was hub 57.129, arachna1 49.393, fire1 58.793, water1 59.948. Even this unchanged Classic path did not pass the quiet-machine 60 FPS gate under the current sharing (GPU preflight 71/58/77%).

Full-window captures were inspected, including the HUD and the route's end-of-fire1 save menu and end-of-water1 completion dialogue. The baseline has the same end-state menus and the existing character-over-menu drawing in fire1. These captures are not evidence of uninterrupted combat in those end states. The world target is 3024 × 1964; the desktop constrained the captured root window to 3024 × 1688. Same-tick numeric comparisons use the native world target, not a resized window screenshot. All four repeated world-picture controls are pixel-identical. The final staged scripts contain none of the private probe or injected-library hooks.

**Remaining acceptance gate.** Sustained 60 in arachna1, hub and fire1 remains unfinished. Water1 reached 59.94 in the final repeat, but one successful level does not satisfy the request. A quiet-machine repeated route is still required to establish whether this implementation meets the target and whether hub/fire1/water1 retain requested quality when headroom is available. Reduced-MSAA temporal shimmer also remains unquantified by the static SSIM/MAE tests. Shared-load measurements cannot settle those questions; no unrelated process was stopped to manufacture a quiet result.

Evidence under `local/aa-codex/`: `cost-probe-2/{passes.trace,gpu.xml,trace-stats.json,metal-stats.json}`, `quality-probe-1/` (exclude hub-labelled captures), `scaler-probe-1/`, `fxaa-probe-1/`, `final-picture-probe/{image-stats.json,metal-stats.json}`, `baseline-final-1/`, `candidate-final-{1,2}/`, `baseline-live-*`, `candidate-live-*`, `classic-control-1/`, `lockstep-2/`, `lockstep-2-safe.log`, `quiet-check.json`, `build-baseline.log`, `build-candidate-2.log`, `build-final-extension.log`, `governor-tests-final.log`. Reproduction helpers: `run.py`, `probe.gd`, `metal_probe.m`, `metal_stats.py`, `trace_stats.py`, `image_stats.py`, `live_stats.py`, `launch_room.py`. These local diagnostic helpers are not shipped in the build.
