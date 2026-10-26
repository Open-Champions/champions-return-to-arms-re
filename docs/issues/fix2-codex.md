# F3 and F4 corrections

STATUS: F3 thread-safety fix verified in **3/3 final room replays**; F4 **136/136 PASS**.
Import work is spread across frames; the remaining full-frame startup hitch is
measured below and is not claimed eliminated.

2026-10-26, worktree based on `5e6d3c5`. Changes are local and uncommitted. No push.
The starting worktree was clean. The scope is presentation code and the rendezvous
test harness; no native simulation source, patch, translation, or gameplay constant
was changed.

## Changes

| File | Change |
|---|---|
| `tools/godot/project/er_layer.gd:688–765`, `:1521–1530` | The worker loads a private `GLTFDocument`/`GLTFState` only. The main thread joins it before accessing either. Mesh upload, armour-material preparation per surface, and `generate_scene` are separate budgeted stages. Godot's generated mesh cache is reused, and the existing figure remains visible until the replacement is ready. Shutdown joins outstanding tasks without freeing worker-created scene nodes, since there are none. |
| `tools/godot/project/resource_budget.gd:1–19` | A shared **4,000 µs per rendered frame** budget for ER imports and remaster uploads. It accounts for actual elapsed work and defers further operations after exhaustion. Godot calls are indivisible, so this is a cooperative budget, not a hard bound on an individual call or the entire frame. |
| `tools/godot/project/model_remaster.gd:379–391`, `:655–738`, `:822–895`, `:993–1006` | Merge workers now return surface arrays. The main thread creates meshes one surface at a time. Map workers return CPU images/mipmaps; texture creation happens on the main thread over three passes. Previously visible meshes stay in use until completion. A grouping change during upload finishes and caches the old job before requesting the new grouping. Task slots are allocated before scheduling workers, and shutdown distinguishes pending tasks from already-joined uploads. |
| `tools/rendezvous/check_client.py:766–771` | Wynn joins first; the test waits until the host reports Wynn in slot 1 before sending Wren's join. The existing room check also requires that first assignment to succeed, retaining **136** checks. |

The material preparation stage matters: the first implementation moved scene and
mesh creation correctly but still returned both outfits to a large synchronous
armour-material loop. The final implementation prepares those same materials
incrementally and lets `_in_order` reuse them.

## Thread audit

The audit covered every `WorkerThreadPool`, `Thread`, and threaded resource-load
site beneath `tools/godot/project`:

- `er_layer.gd`: fixed glTF scene generation. `ErFit.compute` already produces CPU
  arrays; fitted meshes/materials are created on the main thread.
- `model_remaster.gd`: fixed both `ArrayMesh` creation in `_merge_task` and
  `ImageTexture.create_from_image` in `_derive`. Cache workers only read/write
  serialized arrays. Native `RtaRemaster::merge` and `derive_maps` were inspected:
  they operate on arrays and CPU images, not scene nodes or GPU resources.
- `er_world.gd:429–440`: uses Godot's supported `ResourceLoader` threaded-loading
  API; its texture uploads and material/node construction are on the main thread.
- `gameart/gameart.gd`: worker reads/unpacks CPU images, publishes under a mutex,
  and defers notification. Texture creation occurs in the consumer.
- `cinematic.gd:176–203`: worker reads CPU images; texture creation is already on
  the main thread.
- `hud/music/music.gd:128–149`, `:185–188`: worker loads a private audio resource
  and defers application; it does not create render nodes, materials, or meshes.

[Godot 4.5's thread-safety documentation](https://docs.godotengine.org/en/4.5/tutorials/performance/thread_safe_apis.html)
permits loading resources owned by one worker, warns against render-node
instantiation on workers, and recommends avoiding GPU operations there. The
remaining `append_from_file` is that resource-loading case, with a separate
document/state per job and no main-thread access until completion. The
[4.5.2 importer implementation](https://github.com/godotengine/godot/blob/4.5.2-stable/modules/gltf/gltf_document.cpp)
creates skeletons and the node tree during scene generation; this now runs on the
main thread. No rendering-thread setting was changed.

## Executed checks

All artifacts and copied helpers are private under `local/fix2-codex/`; the build
is under `local/godot-codex2/`. Heavy work used `nice -n 10`. Only processes
started by these helpers were managed. Game and rendezvous traffic used loopback;
inherited endpoint variables were cleared. No other agent's running program or
build output was replaced.

```sh
RTA_GODOT_OUT=local/godot-codex2 nice -n 10 python3 tools/godot/build.py all
nice -n 10 python3 tools/rendezvous/check_client.py --work "$PWD/local/fix2-codex/client"
nice -n 10 python3 -m unittest discover -s tools -p 'test_*.py'
```

- Build: **exit 0**, extension built and project staged;
  `build-verified.log`. Editor import: **exit 0**, no script errors;
  `import-verified.log` / `.json`. After removing local instrumentation, the
  staged scripts match the tracked sources and editor import still exits 0
  without script errors (`import-clean.log` / `.json`).
- F4: **`136 of 136 checks passed (71 s)`**, exit 0; `check-client.log`.
- Python suite: **`Ran 2208 tests in 47.330s` / `OK`**, exit 0;
  `unittest.log`.
- Actual glTF comparison: **3/3 identical** against eager main-thread loading:
  the two room outfits and a weapon. Compared node transforms, skeleton names,
  parents/rests/poses, skin bindings, surface arrays, original materials/textures,
  and prepared armour materials. Cancellation while another file was loading
  drained successfully. `import-verify.log`,
  `candidate/project/import_verify.gd`.
- Remaster checks: identical mesh arrays and group metadata after changing the
  requested grouping during an outstanding merge; an exhausted frame budget
  defers uploads; the three uploaded maps retain their pixels and mipmaps.
  `remaster-verify.log`, `candidate/project/remaster_verify.gd`.
- `git diff --check`: passed.

## Room replays and frame timing

The helper is a local copy of the original row 11.6 `room33-codex.py`, redirected
to this worktree, the isolated build, unique test ports, and fresh per-run cards.
It retains the original seeded input, two Remastered clients, Hardcore/aim,
640 × 448 request, hub → drunare, 420 initial play ticks and 600 second-level
play ticks. A has the real ER inputs; B has no ER model folder. A must load both
outfits, while B's effective settings disable ER models. The helper checks both
process exits and `compare.py ticks`; screenshots capture the resulting figures.

Local-only timing instrumentation surrounds `_gltf` with request/return markers.
The existing `--frame-log` records actual frame gaps and main-thread processing.
The import window starts in the frame containing the first request and ends in
the frame returning the last scene; its final gap is measured at the next frame.
This includes normal game/presentation work happening during import. It is not
just a stopwatch around `generate_scene`. Diagnostic CSV `L`/`M` rows are excluded.
The parser and complete retained results are `summarize.py` and
`room-summary.json`.

```sh
nice -n 10 python3 local/fix2-codex/run.py baseline-4 local/fix2-codex/baseline
nice -n 10 python3 local/fix2-codex/run.py fixed-2 local/godot-codex2
nice -n 10 python3 local/fix2-codex/run.py fixed-3 local/godot-codex2
nice -n 10 python3 local/fix2-codex/run.py fixed-4 local/godot-codex2
```

`baseline-4` and all three final runs used byte-identical extension and game
libraries (`binary-identity.json`, `final-binary-hashes.json`). The baseline uses
the original presentation scripts; the final runs use the corrections above.
All use warm renderer caches and fresh per-run cards. Scheduling and other
programs on the machine still vary; these are measured runs, not an isolated
machine benchmark.

| Run | Shared ticks, zero differences | A / B exit | Caller-thread / script / other errors | Import frames | Max one-frame gap during import | Max main-thread turn during import |
|---|---:|---|---|---:|---:|---:|
| Matched baseline `baseline-4` | 1,865 | 0 / 0 | 0 / 0 / 0 | 6 | **144.598 ms** | **136.482 ms** |
| Final `fixed-2` | 1,850 | 0 / 0 | 0 / 0 / 0 | 57 | 128.604 ms | 89.967 ms |
| Final `fixed-3` | 1,852 | 0 / 0 | 0 / 0 / 0 | 58 | 125.302 ms | 86.783 ms |
| Final `fixed-4` | 1,849 | 0 / 0 | 0 / 0 / 0 | 57 | 120.544 ms | 84.352 ms |

**Before/after maximum frame hitch: 144.598 → 128.604 ms.** Maximum main-thread
turn: **136.482 → 89.967 ms**. Both outfits loaded in every final replay; B had
ER models disabled and made no glTF import request. All three comparisons say
`RESULT: no shared column differs on any tick`. No final replay produced a crash
report or abnormal process exit. Evidence: each run's `.log`/`.json`,
`a.txt`/`b.txt`, tick TSVs, frame CSVs, cards, and pictures.

Additional per-call timing in `fixed-3` and `fixed-4` sums all `_gltf` main-thread
work by rendered frame: maxima **15.549 / 13.303 ms**. Their first request frame
spent only **0.022 / 0.018 ms** in `_gltf`. The soft 4 ms budget stops the next
operation, but individual engine calls can exceed it. These timings do not
justify a strict 4 ms bound or a claim of hitch-free 60 fps; the larger frame gaps
include other presentation work.

A separate final-code diagnostic replay, `profile-1`, timed the existing
`before_frame → drawer.submit → scene.frame` phases and enabled
`RTA_SUBMIT_LOG=15`. At the first import frame (blank 2,957), the two `_gltf`
calls totalled **0.037 ms**; the drawer took **81.174 ms**. Its own breakdown
reported **142 new textures, 148 materials and 652 meshes**, with **64.6 ms**
in runs/draws and **13.4 ms** in texture handling. A later ER `before_frame`
also took **47.402 ms** outside the budgeted `_gltf` calls. Thus a large overall
startup hitch remains in the existing presentation path; moving scene generation
to the main thread with a budget does not by itself remove it. The diagnostic
edits were confined to the staged project and removed after measurement.
Evidence: `profile-1/a.txt`, its frame CSV and `profile-1.log`.

Actual `a-level-1.png` output in the final room was inspected against the
baseline: both fitted outfits, materials, player rings and the scene remain
present. `b-level-1.png` confirms the original-figure fallback. Screenshot poses
vary with display interpolation; the separate structural comparisons above
establish unchanged imported geometry/material/skeleton data.

Earlier retained runs: `baseline-1` had a cold-renderer **4,496.138 ms** frame gap
(**4,399.274 ms** in drawing), so it is not used as the warm comparison.
`baseline-2`/`baseline-3` measured **159.908 / 111.410 ms** gaps and
**149.249 / 106.039 ms** main-thread turns. The intermediate `fixed-1` measured
**141.560 / 137.133 ms** before armour-material preparation was budgeted; it is
not counted as a final-code replay. All evidence is retained, including these
setup and intermediate runs. The current baseline replays did not reproduce the
intermittent crash; its recorded stack and failure remain in
`docs/issues/test-matrix-codex.md`, F3.
