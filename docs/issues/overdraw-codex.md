STATUS: PARTIAL — GPU cost reduced, image gates and two-copy lockstep pass; sustained native 4× at 60 FPS is NOT MET under the measured shared load. No commit or push.

2026-10-26–27. Baseline `2c01146`. Godot 4.5.2 Metal Forward+, Apple M5 Pro, 3024 × 1964 world target, native scale, 4× MSAA. The adaptive quality policy is disabled in the private measurement stages so it cannot obtain the gain by reducing quality. Production governor behavior is unchanged. Captures, traces, staged controls and diagnostic helpers stay in ignored `local/overdraw-codex/`.

**Why the pass was expensive.** `rta_drawer.cpp:255` maps the GS equation `(A - B) * C + D` into source and destination coefficients. `gs_draw.gdshaderinc` writes `ALPHA` even when its value is one, and `place`/`place_mesh` encode GS list order in transparent sorting offsets. Godot sends shaders that write `ALPHA` to its transparent pipeline. That preserves blending, decals, later effects and same-depth ordering, but keeps even opaque surfaces out of the engine's depth/opaque passes. [Godot spatial shader reference](https://docs.godotengine.org/en/4.5/tutorials/shaders/shader_reference/spatial_shader.html).

The existing custom solid-depth prepass is **inside the ordered transparent pass**. It draws colorless, unshaded depth for a contiguous solid batch segment before shading that segment. It is different from Godot's almost empty engine prepass. It was already useful and remains enabled for ordered solid world batches; promoted batches use the engine prepass instead. Removing all prepasses is not the fix.

The name “transparent world pass” includes remastered creatures, the player's subdivided body and fitted outfits. At arachna1 tick 2860 the input list has 25 exact level draws and 800 exact model/dome draws, including paired model packets; many model packets are hidden in favor of their host-side replacements. Moving level geometry alone was insufficient. The main remaining waste was repeatedly running the complex model/outfit material and lighting shaders on overlapping geometry.

`rta_world.cpp:323` selects solid exact geometry for ER material classification; `world_decal` at line 791 separately handles blended sheets/decals for grass exclusion. Its average texture opacity is not an opacity proof. Neither its classifications nor gameplay code have been changed.

**Accepted change and ordering boundaries.**

- Promote only the initial proven-solid Remastered world stretch, with ordinary depth test/write and no RGB mask. ABE-off and destination-independent GS equations qualify. Constant FIX factors also qualify when the destination coefficient is exactly zero. Source-alpha factors qualify only when texture alpha is unused and every full-packet corner has GS alpha 128 (one). Unknown texture alpha, destination-alpha factors, subtractive blends and cutouts stay ordered. Alpha-test enable alone is never treated as an opacity proof.
- Stop promotion at the first foreground ordering barrier, including hidden model/replacement draws, generated replacements, noncommuting draws and uncertain paths. Never resume promotion later in the list. Existing fused two-pass chunks are eligible only under their existing proof that the first pass covers and the second blends over that same geometry.
- Preserve batch order with opaque material priorities, including equal-depth ties; limit promotion to the 256 available priorities. The pinned engine's opaque sort key puts priority first. [Godot 4.5.2 opaque sort implementation](https://github.com/godotengine/godot/blob/4.5.2-stable/servers/rendering/renderer_rd/forward_clustered/render_forward_clustered.h).
- Sky/dome and generated skirt/rim backgrounds must not paint over newly opaque world surfaces. Their Remastered background variants use reverse-Z far depth after the opaque pass. Skirt/rim switching occurs only when a batch was actually promoted. Classic retains its original variants; ceilings retain their original depth.
- Keep models/outfits at their existing ordered color positions. Add a cheap depth twin immediately before each existing position, with identical mesh, skeleton, vertex displacement, alpha cutoff and LOD-dependent rejection. The twin writes zero color, casts no shadow and excludes material/lighting work. Visibility, transforms, interpolation, bounds and resource lifetime follow the original. The color shader bodies are unchanged. This avoids moving depth across earlier true blends or decals.

At the measured ticks, the classifier moves these source draws (fused pairs count as two):

| Level | Level draws in input | Promoted draws | Opaque batches | Ordered level batches remaining |
|---|---:|---:|---:|---:|
| arachna1 | 25 | 24 | 17 | 1 |
| hub | 199 | 3 | 3 | 155 |
| fire1 | 1887 | 1851 | 167 | 1 |
| water1 | 23 | 23 | 20 | 0 |
| islsm1 | 79 | 0 | 0 | 79 |

Hub/islsm1 deliberately hit early ordering barriers. They are not permission to globally sort the remaining surfaces as opaque. `RTA_OPAQUE_WORLD=0` and `RTA_MODEL_DEPTH=0` are independent diagnostic opt-outs.

**Overdraw and fragment work.** Godot's overdraw debug view at arachna1 tick 2860 estimates 8.55 raster layers per screen pixel on average, median 2.59, p90 25.63, p99 73.51 and maximum 102.54. About 83.11% of pixels have coverage; 24.90% exceed eight layers. The central overlapping model/outfit geometry is the dense region. With the old custom world depth draws included, the debug mean is 9.31; exclude those duplicates when describing scene geometry.

These counts come from additive debug output with linear tonemapping, exposure 0.05, glow/grade disabled and inverse-sRGB decoding of RGB8 red. The debug shader contributes `0.4 * 0.1` per layer. RGB8 and MSAA coverage quantize the result. The view replaces the real material shader, including its alpha rejection and culling behavior: it measures geometric coverage, **not actual expensive fragment invocations**. The device exposes timestamp counters only; no hardware shaded-fragment count was available. Evidence: `isolate-2b/arachna1-overdraw_no_prepass.png` and `isolate-2b/overdraw-stats.json`.

The baseline ordered fragment stage costs about 24 ms / 5.939 million output pixels = 4.03 ns per output pixel (about 4.85 ns per debug-covered pixel). Candidate opaque plus ordered color stages cost about 12.7 ms, or 2.14 ns per output pixel (2.57 ns per debug-covered pixel). These are normalized stage elapsed costs, not latency of one shader invocation; they include contention and all fragments in those stages.

GS solid variants already compile out discard. Remastered model/outfit shaders use alpha rejection and expensive normal/ORM/aux texture work, per-pixel form light, material highlights, atmosphere and scene lighting. The new twins resolve their covered depth with the same rejection before this expensive shading. The same alpha rejection is still needed in the color shaders at uncovered cutout samples. Turning off ER world materials or lighting would change the requested picture and did not explain most of the measured cost.

4× MSAA is not evidence of four full shader executions per pixel. The shaders do not request sample ID/position, and Godot's Metal driver reports requested sample shading as unsupported. MSAA still increases coverage/depth/color storage and resolve work. [Pinned Metal driver](https://github.com/godotengine/godot/blob/4.5.2-stable/drivers/metal/rendering_device_driver_metal.mm).

**GPU measurements.** All games are muted, launched at nice 10 or lower scheduling priority, with isolated test cards/configuration. Only this task's child processes are managed. Other playtest processes stay running. Fixed probes assert the actual level, hold the same presented tick and camera, freeze animation time, discard 60 renders and sample the next 120. Every sequence is baseline → candidate → candidate repeat → baseline end.

Godot's timestamp/viewport GPU values are unavailable (zero) on this Metal version. The private probe uses completed Metal command-buffer GPU start/end times; the detailed run also adds public stage counters. Elapsed times can include preemption/resource contention. Stage vertex/fragment intervals overlap and must not be summed as if sequential.

Detailed arachna1 stage medians, tick 2860, `fidelity-2`, milliseconds:

| Stage | Baseline | Candidate | Candidate repeat | Baseline end |
|---|---:|---:|---:|---:|
| Engine depth, vertex / fragment | 0.066 / 0.001 | 0.173 / 0.231 | 0.198 / 0.243 | 0.059 / 0.001 |
| Opaque, fragment | 0.001 | 3.367 | 3.433 | 0.001 |
| Ordered transparent, vertex / fragment | 0.318 / 23.802 | 0.289 / 9.242 | 0.285 / 9.346 | 0.309 / 24.047 |
| Resolve, fragment / compute | 0.634 / 0.981 | 0.630 / 0.845 | 0.662 / 0.895 | 0.606 / 0.935 |
| Tonemap, fragment | 0.708 | 0.684 | 0.719 | 0.735 |
| Union of sampled GPU stage intervals | 26.547 | 16.234 | 15.838 | 26.933 |
| Completed world command buffer elapsed | 29.148 | 18.154 | 17.758 | 29.039 |

The final timing-only run (`timings-final`) uses completion callbacks/pass metadata, with **no stage-counter commands and no GPU profiler**. The table gives GPU milliseconds per rendered frame: the union of all completed command-buffer spans from one world draw through the buffers before the next world draw, including presentation. There are normally three buffers, two in islsm1. Medians use 120 frames per cell; `frame-gpu-stats.json` also retains world-buffer-only medians.

| Level / fixed tick | Baseline | Candidate | Candidate repeat | Baseline end |
|---|---:|---:|---:|---:|
| arachna1 / 2860 | 29.315 | 16.592 | 17.583 | 27.006 |
| hub / 3874 | 14.408 | 12.028 | 13.943 | 17.271 |
| fire1 / 4890 | 15.528 | 10.865 | 10.549 | 16.958 |
| water1 / 5893 | 15.475 | 10.248 | 9.927 | 13.758 |
| islsm1 / 6899 | 4.581 | 4.549 | 4.496 | 4.567 |

Arachna1 falls about 39% using the mean of the two control medians versus the two candidate medians. Its candidate repeat is still above 16.67 ms; this is not a sustained-60 verdict. Before this run, GPU utilization samples were 69/34/45%; system load changed from 7.41/8.25/8.92 to 25.70/17.66/12.90. Do not treat these as isolated-device benchmarks.

**Picture gate.** RGB8 world images are compared at 3024 × 1964, 4× MSAA, same presented tick within each run. MAE is on the 0–255 channel scale. SSIM is scikit-image with `data_range=255`, averaged across channels. Worst of the two candidate captures in `fidelity-2`:

| Level / tick | MAE | SSIM |
|---|---:|---:|
| arachna1 / 2860 | 0.000001179 | 0.999999989 |
| hub / 3874 | 0.000004154 | 0.999999961 |
| fire1 / 4890 | 0.000037941 | 0.999999402 |
| water1 / 5893 | 0 | 1 |
| islsm1 / 6899 | 0 | 1 |

Every ending control equals its starting control exactly. The separate timing-only run repeats the image gate. Against the untouched baseline build's earlier arachna1 tick-2860 capture, candidate MAE is 0.011204043 and SSIM 0.999900345; the new-path-disabled control has essentially the same cross-run difference (0.011203874 / 0.999900345). The within-run pair is the stronger isolation of the renderer change; both comparisons exceed the requested 0.999.

Full-window captures were inspected with HUD and transitions. The root window is constrained by the desktop to 3024 × 1688; numeric comparisons use the unscaled world target. The established route ends fire1 in the save menu, including its existing character-over-menu composition, so that endpoint is not uninterrupted combat evidence. Islsm1's sampled view contains little visible water. Additional `transparent-final` checks use wat1's underwater bubbles and fire3's broad lava surfaces, smoke and flames (33 blended world draws without depth writes). Dis2 adds a cutscene with overlapping alpha-tested figures and subtitles; it is not a river-view test.

| Additional level / tick | Worst MAE | Minimum SSIM | Baseline world GPU ms (start / end) | Candidate world GPU ms (two repeats) |
|---|---:|---:|---:|---:|
| wat1 / 2870 | 0 | 1 | 5.705 / 5.453 | 5.532 / 5.875 |
| fire3 / 3882 | 0 | 1 | 28.438 / 28.683 | 21.369 / 19.114 |
| dis2 / 4852 | 0.000002751 | 0.999999931 | 12.997 / 14.870 | 11.838 / 11.500 |

These supplementary GPU numbers have stage counters enabled and exclude the separate presentation buffers. The extra run logged 29 engine-profiler timestamp-budget messages; its engine timestamp results are not used. The independent Metal counters and completion records completed successfully (all 23,110 command buffers status 4); images and their ending controls pass. The main five-level image/timing runs had no errors.

**Classic.** Untouched build versus final candidate at fixed ticks 2860 (arachna1), 3873 (hub), 4891 (fire1), 5861 (water1): both corresponding captures are pixel-identical, MAE 0 / SSIM 1. Classic keeps its 4:3 2619 × 1964 target at the requested native scale and 4× AA. Its alternating arachna1 and hub control images differ from each other, but each candidate phase matches the same baseline phase exactly.

Supplementary islsm1 tick 6867: the untouched build's first capture differs slightly from its own repeat at a sky edge. Both candidate captures equal that untouched repeat exactly. First-to-first MAE is 0.000308856 / SSIM 0.999995336, 2,521 changed pixels, maximum difference 3/255. The focused `classic-island-before` / `classic-island-after` repeat at tick 2858 has three corresponding captures; all three are pixel-identical (MAE 0 / SSIM 1). That resolves the renderer comparison; the original first pair remains recorded as a differing control state.

**Rejected experiments.** These are explanatory measurements under different shared load, not numbers to mix into the final table. `isolate-1`: world-only opaque 40.758 ms versus nearby baseline 41.023 ms (later repeat 29.189, ending baseline 36.542); ER detail off 41.329 ms with SSIM 0.946343; contacts off 39.541 ms with SSIM 0.992952. `isolate-2b`: globally opaque models/outfits 15.440 ms versus baseline 39.557, but SSIM 0.993971 / MAE 0.401139. Disabling the extra opaque shadow casting still failed: SSIM 0.994060 / MAE 0.377953 (`isolate-3`). Remastered-body-only opaque reached SSIM 0.9999876 / MAE 0.001792, but moving its depth across earlier draws was not generally justified. The accepted ordered body-depth experiment instead gave 26.800/25.941 ms versus controls 37.906/37.055 and pixel-identical captures. Extending that approach to fitted outfits gives the final candidate.

**Repeated live FPS.** Normal paced runs, no fixed-tick probe, stage counters or GPU profiler; adaptive AA off. Both builds follow the same route and controls. FPS counts game frames over idle → movement → camera turn → attacks → end, not 120 Hz interpolated pictures. GPU figures union completed command-buffer spans by game-frame tag. Every measured frame with GPU data had a 3024 × 1964 4× world target (726–735 samples per level/run); no quality reduction supplied the gain. Each cell is **game FPS · GPU p50 / p90 ms**.

| Level | Untouched build 1 | Candidate 1 | Untouched build 2 | Candidate 2 |
|---|---:|---:|---:|---:|
| arachna1 | 31.83 · 23.699 / 103.985 | 40.64 · 15.634 / 43.219 | 35.01 · 23.102 / 74.031 | 36.60 · 19.280 / 74.852 |
| hub | 45.97 · 13.116 / 20.525 | 48.60 · 11.117 / 17.962 | 40.24 · 16.940 / 29.642 | 41.41 · 12.906 / 22.348 |
| fire1 | 30.64 · 11.667 / 18.498 | 33.88 · 9.134 / 15.490 | 35.82 · 13.714 / 20.853 | 34.85 · 10.233 / 17.229 |
| water1 | 58.79 · 12.982 / 22.062 | 59.03 · 10.092 / 18.006 | 55.03 · 20.709 / 32.073 | 55.86 · 14.804 / 29.162 |

Slowest one-second game-frame counts for arachna1 are 15 → 22 in pair 1 and 18 → 17 in pair 2. This does not pass sustained 60. Fire1's FPS also regresses slightly in the second pair despite lower median GPU time; the measurements do not support a uniform live-FPS improvement under sharing.

GPU preflight utilization samples, in run order: 73/86/78%, 80/46/32%, 74/39/46%, 84/64/65%. All four runs exit 0. Load and tails vary substantially; report each pair instead of treating this as an isolated-device speedup. The candidate's first fire1 run also spends median 15.599 ms in `_process`, including 14.382 ms in scene submission, versus GPU p50 9.134 ms. There is material host-side work in addition to the GPU overdraw cost. These durations overlap and must not be added as sequential pipeline stages.

**Files changed.** Line numbers refer to this uncommitted working tree.

| File / lines | Change |
|---|---|
| `tools/godot/extension/src/rta_scene.cpp:209,747,811,884,1312,1450` | Prefix eligibility/barriers, blend proof, opaque batch priorities, retained ordered prepass, diagnostic counts |
| `tools/godot/extension/src/rta_drawer.cpp:147`; `rta_variant.h:32` | Opaque and background shader variants |
| `tools/godot/extension/src/rta_fill.cpp:107,154,458`; `rta_drawer.h:415` | Background skirt/rim variant lifecycle and selection |
| `tools/godot/project/scene_view.gd:170,253,448` | Remastered-only opaque routing and sky variant |
| `tools/godot/project/model_depth.gd:1` | Shared ordered depth-twin helper, caches and cleanup |
| `tools/godot/project/model_remaster.gd:41,661,780,997` | Model depth material/instance/pose/visibility lifecycle |
| `tools/godot/project/er_layer.gd:92,124,1494,1644,2437` | Creature, weapon and fitted-outfit depth twins, restricted to supported shader materials |
| `tools/godot/project/shaders/gs_draw.gdshaderinc:61,247,577` | Opaque no-ALPHA path; far-depth background |
| `tools/godot/project/shaders/remaster_model.gdshader:19,146,311`; `er_armour.gdshader:16,86,164` | Cheap depth variants using original transform/cutoff; original color bodies retained |
| `tools/godot/project/shaders/sky.gdshader:5,23`; `fill.gdshaderinc:22` | Background depth variants |

**Validation and remaining work.** The requested `RTA_GODOT_PARTY8=1 RTA_GODOT_OUT=local/godot-codex-od python3 tools/godot/build.py all` completed on the baseline and final source; extension/project rebuilds and headless import completed. The full build recompiles `testerkit.cpp` with a build ID/time even when gameplay source is unchanged. The final full build pins `RTA_BUILD_ID="2c01146 2026-10-26 23:48"`, the baseline library's original ID, to retain exact binary identity. The unpinned intermediate hash is not the final artifact. Evidence: `build-final-all.log`, `build-final-pinned.log`. No shader/script error was observed in the completed final Remastered matrices. `git diff --check` passes. The last classifier review added a conservative destination-alpha guard; none of the five measured world input lists contains that factor, and subsequent validation uses the rebuilt guard.

Gameplay sources are untouched. Baseline and candidate `librta_game.dylib` SHA-256 are both `ecf79a8e929b33ee6d1a03cafe7a8f3afd0dc57b5d1be4a941245d5d1dc11be7`. The final room uses two candidate copies with that same gameplay library. The initial room setup failed before gameplay because the older baseline extension lacks the `RtaNet2` class; no tick logs were produced and those attempts do not count as lockstep validation. The untouched build remains the offline image/performance control. `lockstep-3` passes: A logs ticks 1–1395, B logs 1–1394; all 1,394 common ticks match across 53 shared columns. These include 1,120 hub ticks and 274 arachna1 ticks. Per-machine/pacing columns are excluded by the existing comparator. Both processes exit 0 with no engine/script errors. This is a two-copy smoke test through a level transition, not a full campaign or an assertion that every RAM byte is identical. Evidence: `lockstep-3/final-compare.txt`, both private tick logs and `lockstep-3-driver.log`. The longer scripted second-level input sequence is not claimed complete; the timed harness ended after the recorded ticks.

**Remaining acceptance gate.** Sustained native 4× at 60 FPS is not achieved in these live runs. The fixed arachna1 frame is near the GPU budget, with one candidate median above it; live GPU tails and host scene-submission work remain substantial. A controlled-load repeated route is needed to separate device headroom from sharing, and further cost reduction may still be required. Nothing here justifies disabling the quality governor or claiming guaranteed 60 FPS. The optimization preserves requested quality in the measured comparisons; it is not a complete performance-target fix.

The final staged runtime scripts/shaders match the working tree (`export_presets.cfg` is deliberately excluded by staging), the shipped stage contains no private probe hooks, and the gameplay/recomp/lib source diff is empty. The repository remains uncommitted and unstaged.

Reproduce the main fixed matrix with the private harness: `nice -n 10 python3 local/overdraw-codex/run.py NEW_TAG --stage NEW_STAGE --source local/godot-codex-od --probe --timings --no-profile --variants baseline,candidate,candidate_repeat,baseline_end --levels arachna1,hub,fire1,water1,islsm1 --windowshots`. For stage counters use `--metal` instead of `--timings --no-profile`. Do not reuse an evidence directory. Helpers inject only host-side diagnostics into private staged copies; no probe hooks are in the shipped project.
