# Windows Godot rendering

**Ran, 2026-10-27:** Windows x64, official Godot 4.5.2 stable (`6ce3de25a`),
NVIDIA GeForce RTX 4080 SUPER. These are bounded rendering/timing checks.
They do not qualify a whole campaign, every platform, or sustained 60 FPS.
All game libraries, discs, cards, captures and raw receipts remain private.

## Earlier bounded rendering fixes

- Projected GS depth now passes through unchanged in the Forward+ branch of
  [gs_draw.gdshaderinc](../../tools/godot/project/shaders/gs_draw.gdshaderinc).
  The old Vulkan shader hid geometry behind the clear; all five authored depth
  cases pass on Vulkan, OpenGL and D3D12, with the old-shader negative retained.
- [RtaDrawer](../../tools/godot/extension/src/rta_drawer.cpp) retains colour when
  switching same-size MSAA backing, clears the selected depth once, and preserves
  copy orientation. The authored [MSAA fixture](../../tools/godot/tests/run_msaa.py)
  passes 60/60 phases across 4x/0x on those three APIs. This does not establish
  retained depth across frames or retained colour across physical resizing.
- Window-aspect resize has 137 bounded checks across draw/scene/picture and fixed
  versus automatic targets. Scene AA is controlled by `look.aa`; `--samples 0`
  alone does not prove applied scene AA is zero. Read effective settings.

## Five-view gameplay check

**Ran on Vulkan and D3D12:** the unchanged selected Windows candidate06 player
(`9756a87`) loads a private copy of the 1,888-XP test save, exercises Blood1,
returns through the ordinary pause-menu Exit to the Hub, and closes normally.
In both scenes, overhead, action, chase, shoulder and first-person views pass actual-view,
live-actor, movement, neutral-release, current-world geometry and surface/window
capture checks. All ten window captures per API were visually inspected.
Each case passes 167 existing owning checks and 61 additional checks; the private
card and packaged runtime hashes stay unchanged. Effective snapshots show 4x MSAA
and scale 1.

An earlier, longer itinerary ended with the character's health reaching zero
during the extra mission checks. Its test timeout and failed verdict are
preserved. The fresh passing route removes the unrelated timing/combat windows
and shortens settling/capture waits while retaining live-state guards. This is
a functional check under recorded ambient load, with no timing windows
or performance acceptance. OpenGL gameplay, aimed projectiles, physical controls,
long sessions and a full campaign are outside this check.

An initial D3D12 attempt never launched the game: its Windows counter subprocess
exceeded the old 20-second bound. A fresh case uses an owned 60-second preflight
with separate raw output, actual exit/timeout/cleanup records and strict typed
sample validation. It completes in 18.318 seconds, followed by a normal game
exit. Ambient admission applies only to this functional check; the separate
performance protocol retains its quiet limits. The failed attempt is preserved.

## Bounded Hub soak

**Ran on Vulkan:** the same unchanged candidate06 completes the compact mission
route and remains live in the Hub for 741.17 host seconds (12 minutes 21 seconds).
The 44,041 consecutive live, unpaused Hub observations span 44,040 simulation
advances with the same player actor and positive health. Twelve checkpoints cycle
through all five views, apply short balanced movement, and verify neutral release,
current world geometry, and surface/window captures. All twelve Hub checkpoint
window images were visually inspected; the independent audit decodes all 44
images from the complete route.

The game and its owner exit normally. All 395 owning, 61 compact-route and 84
soak checks pass, with no logged runtime errors; the cards and packaged runtime
stay unchanged. Effective snapshots retain 4x MSAA and scale 1. Each checkpoint
interval has at least ten distinct completed world GPU samples, but the overhead
intervals contain only 20--22: this does not establish continuously fresh GPU
coverage or a frame-rate target. The check covers bounded Hub rendering and
lifecycle survival. Sustained mission combat, campaign play and resource-count
or VRAM stability remain unqualified.

## First-person bow aiming

**Ran on Vulkan:** two unchanged candidate06 runs load separate private copies
of a legitimate level-one Ranger save, return normally to the Hub, and fire one
arrow at each of two opposite first-person camera pitches. The ordinary aim
option is off in one run and `look` in the other; no guest-state writes are used.

| Measured camera pitch | Arrow pitch, aim off | Arrow pitch, aim look |
|---|---:|---:|
| +24.9 degrees | +0.69 degrees | +25.00 degrees |
| -24.9 degrees | +1.03 degrees | -25.00 degrees |

The audit follows each actual player-owned `MissileWeapon` through at least three
consecutive simulation ticks. Across the first three, raw velocity remains
constant, speed is near 1,000 units/second, and two observed position deltas agree
with velocity/60 within 0.000006 units. Aim-on heading and pitch match the measured look direction;
the aim log corroborates the same object and velocity. Both runs exit normally,
all eight images decode, and cards/runtime hashes remain unchanged. Four window
images were visually inspected; the projectile proof comes from the raw tracks.

This qualifies four offline Ranger arrows, including the aim-off control. It
does not establish whole-simulation byte identity, other projectile classes,
target hits, physical controls, online room agreement or lockstep behaviour.

## Windows presentation capture

**Ran:** the official standalone [PresentMon 2.6.0 console tool](https://github.com/GameTechDev/PresentMon/releases/tag/v2.6.0),
verified against the release digest and its Intel signature, runs a ten-second
capture against one owned candidate06 process. The display/QPC profile uses
`--no_track_gpu --no_track_input --v1_metrics`; display tracking stays enabled.
All 1,170 CSV rows name the actual game PID and one swapchain. The 28 dropped
and 1,142 non-dropped markers are retained, along with display timings and QPC.
The tracer and game exit normally, and the unique trace session is absent
afterward. No nonzero ETW loss or unknown diagnostic is reported.

The installed FrameView SDK helper exits before producing CSV in both tested
working directories. An earlier standalone capture with GPU/input tracking
reports 4,515 lost ETW events: its raw output is preserved and rejected for
performance use. The admission reader rejects reported event/buffer/present
loss and unknown diagnostics. Its ten pure controls include that actual loss
message and malformed output. The observed process-query privilege warning is
accepted only for a verified, live process owned by this test, targeted by PID.

This establishes the capture path during title/load under ambient conditions.
It does not establish complete gameplay coverage, alignment with engine timing
windows, a sustained FPS result or the project's 60 FPS requirement.

## Completed GPU timing

**Reproduced:** with one unchanged viewport RID, an authored workload requests
that viewport every third frame of 180-Hz render scheduling. Godot's cached
RenderingServer viewport time freezes while completed RenderingDevice (RD)
query pairs respond to low -> high -> low shader work. After warm-up, each sparse
phase contains 50 distinct completed GPU timestamp pairs:

| Driver | Cached RS time, all three phases | RD median low / high / low, ms |
|---|---:|---:|
| Vulkan / Forward+ | 0.010 ms | 0.012288 / 0.332800 / 0.029184 |
| D3D12 / Forward+ | 0.013 ms | 0.035840 / 1.360384 / 0.056320 |

This is an authored timing control, not game throughput. The pinned engine can
apply delayed viewport queries through its current-frame viewport-name map;
reading the completed RD pair directly avoids that cached-scalar path.

[RtaGpuTimer](../../tools/godot/extension/src/rta_gpu_timer.cpp) polls on the render
thread every engine frame, including held frames. A unique world-submission token
and epoch must occur in the same completed query batch as the exact current-world
`vp_begin`/`vp_end` pair. Replayed tokens, untagged work, old epochs and old RIDs
cannot become fresh samples. Integer GPU timestamp differences are converted
from nanoseconds to milliseconds; the batch ID is diagnostic, not a world token.

The consumer fences the viewport before reading. Level, safe-state boundaries,
adaptive disable/reentry, requested AA and applied AA/scale changes invalidate
pending observations. Only started Remastered world draws are tagged. Queued
callbacks retain their owner, shared snapshots use a mutex, and the provider adds
no GPU flush, sync or wait. The Metal completed-command-buffer observer is
unchanged; its frame floor rejects invalidated samples. **Mac runtime was not
rerun.** OpenGL has no completed RD identity: quality is held rather than adapting
from an unproven-fresh RS scalar. Cached RS diagnostics are not a freshness proof.

The production [authored GPU regression](../../tools/godot/project/dev/gpu_timer_test.gd)
passes **28/28 checks on Vulkan and 28/28 on D3D12**: sparse workload response,
unique world tokens, replay/held-frame rejection, epoch/RID invalidation and
pending-callback release. It needs no game library, disc or extracted assets.

The actual packed release repeats **56/56 authored checks** across Vulkan and
D3D12. A separate packed Remastered route passes **86/86 gameplay and freshness checks** through
the mission and hub, exits cleanly and preserves card/artifact hashes. It observes
592 and 569 distinct completed world tokens in the two admitted phases. In the
hub, the cached RS time stays at 3.857 ms while fresh GPU samples vary from
3.077 to 7.580 ms. Phase handovers are approximately **52.2/s mission and 60.0/s
hub** under that run's ambient load. These are host frame handovers, not OS
presents or a sustained-60-FPS verdict.

An experimental Separate rendering-thread run reports texture-update and
wrong-thread finalization errors and gives no throughput improvement. The
production Safe thread model is unchanged. A private, opt-in CPU profile places
most mission drawer time in traversal and batch flush; those aggregate buckets
do not identify an individual conversion or upload as the cause.

The host frame log's `wait_usec` measures the `RtaMachine.poll`/`step` call.
Besides queue synchronization, that call includes `fill_view` draw/metadata
conversion and `scene::fill`. A long sample does not isolate a wait for the
native producer; those costs need separate timing before attributing a stall.

### Opt-in poll/conversion timing

`RTA_POLL_PROFILE=1` enables a bounded, single-consumer diagnostic in the game
library. It separates mutex acquisition, the condition path, pop/unlock/notify,
draw/header conversion, auxiliary arrays and `scene::fill`. Disabled calls add
guarded control flow but no diagnostic clocks, allocation or formatting. Timing
and output perturb the enabled run; exact overhead is not established.

Rows cover 300 **poll attempts**, with separate successful/empty/terminal and
wait-mode counts, up to 64 rows. A terminal partial is labelled separately.
Reporting and shutdown threads never read these consumer-owned counters. Output
occurs after the queue lock is released. The raw record remains useful even when
its phase or clock cannot be qualified.

Four existing `app mark RSM_PERF_mission_START`, `...mission_END`,
`...hub_START` and `...hub_END` commands can identify measurement cuts. The
diagnostic observes the exact successful frame carrying each command; Godot
handles the same command before polling again. Pair cuts with the corresponding
host `M` records, without assuming host, library-take, native-list or simulation
counters are interchangeable. Recheck every native guard in the resulting
interval. Poll work excludes the START conversion and includes END; the original
host callback interval has the opposite one-frame membership.

**Ran:** the same private instrumented library with profiling disabled and
enabled passes the packed mission/Hub route, fresh GPU, quality, input, card and
normal-exit checks. Exact-source authored controls cover 25 cases, including
mutex/unwind ordering, caps, stale commands and interior native gaps. Both
shifted windows have 600 qualified native rows. Only whole contained batches
contribute timing: one mission batch has 300 attempts, 297 fills and three empty
returns; the Hub batch has 300 fills. Conversion averages 33.7 microseconds per
mission fill and 24.9 per Hub fill in those subsets. Condition-path means are
1.690 ms and 0.115 ms per attempt; they include wake/reacquire scheduling and do
not isolate producer starvation. These observations direct the next measurement
toward rendering submission rather than library conversion.

One earlier audit rejects an intact diagnostic row prefixed by concurrent native
console output. Its FAIL is preserved. A versioned read-only supplement and a
fresh confirmation pass with a reader that preserves the original line/prefix,
accepts one intact ASCII payload and rejects ambiguous or malformed records.
The private libraries and receipts stay local; the player runtime is unchanged.

## Pooled mesh bindings

Each pooled instance now remembers its last mesh RID, including the empty RID
assigned to unused slots. Identical bindings are skipped; mesh changes and
unused-slot clears still reach Godot. Caster caches follow their scenario and
pass caches follow their pass. Geometry uploads, material identities and ordering remain
unchanged. Godot 4.5.2's
[base setter](https://github.com/godotengine/godot/blob/4.5.2-stable/servers/rendering/renderer_scene_cull.cpp)
rebuilds base data even for the same RID; mesh-storage dependency notifications
already propagate surface replacement and bounds changes.

The authored [retained-placement GPU fixture](../../tools/godot/tests/run_retained_base.py)
passes 17 phases on each of Vulkan, OpenGL and D3D12; the old Vulkan extension
passes the same 17-phase functional control. It checks retained uploads, material
changes, mesh growth/shrinkage, retained/flat transitions, unused-slot cleanup and
return, physical resizing and target recreation. Kept-hit and update figures
confirm the production path. That fixture exercises caster recreation without
checking receiver pixels; the separate retained-shadow fixture below covers
retained model caster bounds. The existing MSAA fixture also passes
60/60 phases on the changed extension across 4x/0x and all three drivers.

One adjacent optimized-first/control A/B uses identical engine, PCK and game
library bytes, changing only the extension. Both runs pass 86 gameplay/freshness
checks plus eight timing/artifact gates, with 4x scene AA and scale 1 throughout
the observed settings snapshots. Median host handover work falls from 12.916 to
12.471 ms in the mission and 5.588 to 4.935 ms in the hub. Mission host list
advances are approximately 51.5/s and 53.0/s; the hub remains about 60/s. Order,
ambient load and cache effects remain possible: this is a small bounded result,
not sustained-60-FPS acceptance.

### Engine mesh-bounds control

The authored [bounds control](../../tools/godot/tests/bounds_engine_test.gd)
passes seven cases on Vulkan, OpenGL and D3D12 with the same mesh and instance
RIDs throughout. Moving vertices into view while retaining an off-screen custom
AABB leaves the image black. Temporarily bypassing culling reveals the uploaded
geometry; restoring culling hides it again. Updating only the mesh's custom AABB
then restores visibility without another instance-base assignment. Further
out-of-view and return updates pass. All three visible captures are byte-identical
within each API, as are all four blank captures. All processes exit normally
without engine errors or reported leaks.

This checks the pinned engine's observable bounds refresh. Ordinary production
pooled instances bypass culling, so this control does not qualify production
caster bounds or shadow-receiver pixels. It uses no game library or extension.
For reproduction, use a fresh minimal project containing a `project.godot` with
`config_version=5`, and an existing, empty output directory:

```powershell
PATH/TO/GODOT --path PATH/TO/MINIMAL_PROJECT --rendering-method forward_plus --rendering-driver vulkan --script ABSOLUTE/PATH/TO/tools/godot/tests/bounds_engine_test.gd -- --out PATH/TO/EMPTY_OUTPUT
```

Repeat with `d3d12`, then `opengl3` with `--rendering-method gl_compatibility`,
using fresh output directories. The result, capture checks and actual exit must
agree; headless execution cannot qualify these pixels.

### Retained model shadow casters

The authored [shadow fixture](../../tools/godot/tests/shadow_receiver_test.gd)
feeds complete, constant-identity model packets through production retained-mesh
updates and `scene_caster`. A separate authored receiver and directional light
make the shadow visible away from the cyan model. Eight phases cover an initial
off-screen mesh, movement into view, shadows off/on, movement to a second
position, a stationary repeat, movement outside and return. Production figures
show one held retained mesh and in-place writes; these rounded figures do not
expose exact mesh or caster RID values.

**Ran:** Windows extensions built from `70d958a`, using the pinned editor/debug
bindings with release optimization. The current cached-base implementation and
a private control restoring redundant base assignments each pass all eight
phases on Vulkan, OpenGL and D3D12: 48 passing phases. All 24 same-API
current/reference capture pairs have identical full RGBA bytes. A private negative
removes only the retained-update `mesh_set_custom_aabb` call. On every API the cyan
geometry still moves, and all base-pixel, camera and retained-path checks pass,
but all five required shadow phases fail. The initial outside, shadows-off and
later outside captures still pass. Expected negative exits are 1; positive and
reference exits are 0, without engine errors or reported leaks.

This closes the retained-model caster/receiver pixel gap under this directional
light setup on the tested Windows APIs. It does not qualify every caster source,
light mode, platform or campaign. Readback is RGB8 converted to RGBA8 with opaque
alpha, so original scene alpha is outside this comparison. No game library,
disc, extracted assets or production test hooks are used.

The reusable [fixture runner](../../tools/godot/tests/run_retained_base.py) accepts
`--fixture retained_shadow`; the default remains the existing retained-placement
fixture. The shadow sources stay outside the exported project and are staged
only when this fixture is selected. A minimal project needs `project.godot`
(at least `config_version=5`), the project's `rta_godot.gdextension`, and the built
extension in `bin/`. The runner stages its script and shader dependencies. Use
a fresh output path:

```powershell
python -B tools/godot/tests/run_retained_base.py --fixture retained_shadow --godot PATH/TO/GODOT --cxx PATH/TO/CXX --project PATH/TO/AUTHORED_STAGE --driver vulkan --out PATH/TO/NEW_OUTPUT
```

Repeat with `--driver opengl3` and `--driver d3d12`. The runner performs a bounded
headless import before the GPU test and saves captures plus the pixel report
under `NEW_OUTPUT/captures`. Its wrapper requires actual normal exits, no logged
errors, all eight phase verdicts, raw-image hashes and the full-image repeat/
return/outside equalities. The nine focused artifact-admission tests now run in
the standard Python discovery: all 2,300 tests pass.

The public CLI also passes all eight phases on each API from fresh minimal
extension-only stages, with normal exits and no logged runtime errors. All 24
raw captures match the qualified private same-API images. The existing default
also passes its 24 Vulkan phases.

## Material override lifecycle controls

The retained-placement fixture now has 24 phases, including an unused slot
returning as a flat draw and material retirement/recreation after 193 actual idle
submissions. Both extensions pass all 24 phases on Vulkan, OpenGL and D3D12;
all 23 paired captures per driver have identical RGB pixels. Material-held
counters fall during the idle period and material-made counters rise on return.
Retained-path activity is proven in one recorded snapshot before the idle
period; rounded final per-list figures can fall to zero after that period.

A separate [engine control](../../tools/godot/project/dev/override_engine_test.gd)
passes ten cases per driver: same-RID uniform/shader edits without reassigning
the override, base replacement, explicit clearing, material deletion and a new
full RID. This checks the pinned engine's dependency behavior separately from
the production helper. The unchanged MSAA fixture also passes 60/60 phases on
the experimental extension. These material controls do not check shadow-receiver
pixels; the separate fixture above covers retained model casters.

An extension-only experiment skipped identical pooled material-override requests,
retaining the last full RID across base changes. The functional controls above
pass, but one adjacent gameplay A/B shows no measured submission-time benefit:
mission median host handover work is 12.639 versus 12.550 ms, with a complete
300-list drawer block at 10.90 versus 10.89 ms. Hub handover work is 5.212 versus
5.245 ms. Ambient load, scheduling and order differ; the higher mission list
rate does not establish a material-cache benefit. The experiment remains private;
production material assignments are unchanged. The lifecycle controls are kept
for future renderer work.

## Material-key allocation

Material lookup reuses one string buffer per drawer, reserving room for both
binary key structures. Each lookup replaces the complete base key and appends
the second key only for a fused draw. The cache still owns a separate key copy
on a miss. Key fields, zeroing, lengths, hashing and rendering calls are unchanged.

The retained-placement and MSAA fixtures pass the same 128-phase matrix for this
change, including the old Vulkan control; all 16 old/new Vulkan captures have
identical RGB pixels. A separate adjacent A/B keeps the engine, PCK and game
library fixed. Both variants pass 89 gameplay, freshness and clock checks plus
nine artifact/timing gates. At the observed 4x AA/scale 1, mission median host
handover work changes from 12.554 to 11.798 ms and a complete 300-list drawer
block from 11.00 to 10.10 ms. The hub changes little (5.073 to 5.030 ms).
Mission host list advances are approximately 53.0/s versus 54.7/s. These are
single-pair ambient observations; sustained 60 FPS remains unqualified.

## Local co-op HUD

Remastered keeps its HUD when multiple local players force the camera to
overhead. Other local slots receive party frames with both health and mana bars; damage and
level-up feedback on the primary frame follow its own slot. Party frames sit above
the Hardcore controls hints. Portal notices cede drawing only to a visible,
nontransparent HUD with the same current notice ID, preserving older queued
cards, their deadlines and their actions. In original-HUD multiplayer, the notice
also leaves the native upper-right player panel clear using picture-relative
spacing, independent of the custom HUD/font scale.

The authored [visibility](../../tools/godot/project/hud/dev/multilocal_visibility_test.gd)
and [party/notice](../../tools/godot/project/hud/dev/party_notice_test.gd) regressions
pass 28 and 89 checks; the authored
[native notice layout](../../tools/godot/project/hud/dev/notice_layout_test.gd)
regression passes 189. Restored-old behavior, original party spacing, a removed
alpha guard and the old native-notice position fail their negative controls.
A packed normal-window Portal Load of
a copied two-local card passes 27 checks, shows both status frames and one notice,
preserves every saved inventory item and closes without product runtime errors or object
leaks. This is a bounded synthetic-input check, not physical controller or online
multiplayer qualification.

## Same-machine room transitions

Twelve frozen Windows candidate05 cases built from `462e0c0` pass a mission-to-Hub
transition: Classic and Remastered, two/three/four copies, direct and forced
relay. Each copy has one local player. The table gives accepted matching ticks;
every required peer pair matches the complete watched field set.

| Copies | Fields / peer pairs | Direct: Classic / Remastered | Forced relay: Classic / Remastered |
|---|---:|---:|---:|
| 2 | 43 / 1 | 3,511 / 3,646 | 3,498 / 3,613 |
| 3 | 60 / 3 | 3,581 / 3,680 | 3,534 / 3,710 |
| 4 | 77 / 6 | 3,707 / 3,508 | 3,620 / 3,571 |

All clients exit cleanly, input/artifact pins remain unchanged, and actual world
geometry and image checks pass. All six forced-relay cases succeed on the first
guarded Recall attempt, with 59 matching positive post-acknowledgement countdown
ticks per case. The service is a real loopback service; forced-relay routing is
confirmed by native peer telemetry.

The fresh three-player Remastered direct case, both four-player direct cases and
all relay cases retain early Hub observations, then require completed native
loading before a canonical level age of at least 60. They recheck the level and
unpaused state, current world geometry and pixels. Late captures require age 180
and at least 120 observed canonical changes after the primary capture. Earlier
two-player and Classic three-player direct cases have world/image evidence
without this later capture protocol.

An earlier three-player Remastered Hub capture is black at only two canonical
Hub ticks; its original run remains failed. The fresh steady/late captures show
the world, but do not establish recovery in the original run. The procedural
fallback floor can also disappear between primary and late captures, so level
age alone is not proof of complete asset preparation.

These are Vulkan functional checks with 320x240 scene targets and AA off. They
do not qualify intended-quality FPS, WAN play, the full Portal service handover,
full-RAM identity, a campaign, physical controllers or later runtime payloads.

## Bounded submission timing

`RTA_DRAW_PROFILE=1` enables fixed-storage nanosecond wall timers in
[RtaDrawer](../../tools/godot/extension/src/rta_draw_timing.h). Every other value
leaves diagnostic clocks, frame resets, command scans and output disabled;
guard branches remain. This changes neither the game ABI nor rendering calls.
Rows cover 300 submissions, with at most 64 rows, 16 marker cuts and 256 commands
per observed list. Exact mission/Hub START/END commands flush an explicitly
partial boundary row. Two following full rows can cover all 600 submissions.
An unflushed final tail is not reported.

Top-level textures, graph, scene-begin, world-wait, traversal, scene-end and rest
partition submission time. Nested scene, batch, material, packing, learning,
flat, copy and flush scopes report inclusive and exclusive costs; root scopes
reconcile with the sum of exclusive costs. Do not subtract global material
time from one parent: its traversal and scene-end contexts are separate.
Accepted batches include zero-corner cases. Packing bytes are logical position
and attribute bytes, not measured GPU transfers. Learning entries, admitted fill
attempts, sun scan starts and scans reaching 24 samples are counted separately.
No clocks or additional walks are inserted into vertex loops or workers.

**Ran:** a private diagnostic extension built from `12cb5ce` plus these changes,
using candidate06's unchanged engine, PCK and standard-32-MB game library. The
matched OFF/ON normal-Load routes use private 1,888-XP cards, Remastered Vulkan,
1920x1080, 4x MSAA, scale 1 and the Safe rendering thread setting. Both pass 89
owning checks; the wrapper passes 19 OFF and 22 ON checks. All four cuts pair
with the packed caller's exact command tags. Every native list in both shifted
600-list windows passes the live, unpaused, level, XP and fade guards.

| Instrumented mean, ms/submission | Mission | Hub |
|---|---:|---:|
| Total | 9.671 | 3.192 |
| Scene handling excluding measured child scopes | 5.620 | 0.574 |
| Material lookup/creation, all contexts | 0.127 | 0.064 |
| Batch packing | 0.931 | 0.315 |
| Batch flush | 1.619 | 0.616 |

These nested rows do not sum to total time. Each phase has two complete
300-submission rows and 100% coverage. The packed caller handles host commands
before `submit`; diagnostic/native membership excludes START and includes END,
while the original host-CPU window includes START and excludes END. Keep their
totals separate. There are about 7,012 mission and 4,386 Hub clock reads per
submission. Clock/scope/bookkeeping/output overhead is uncalibrated, and both
runs recorded ambient-load overrides. These are observed wall costs, with no
FPS improvement or exact uninstrumented decomposition claimed. The next
investigation narrows the scene-handling residual.

The authored retained fixture passes 24 phases on each of Vulkan, OpenGL and
D3D12 with diagnostics OFF/ON: 144 cases and 69 identical RGB comparisons.
The authored MSAA target-reuse fixture also passes 60 cases across those APIs
with diagnostics enabled and initial 4x/0x sample counts.
The portable [helper controls](../../tools/godot/tests/draw_timing_test.cpp)
pass 16 cases, including disabled clocks, nested accounting, marker alignment,
gaps, unwind and caps; 32 private reader/guard controls also pass. Build the
helper controls with a C++17 compiler and run the resulting executable. These
checks do not qualify other platforms, complete gameplay or a player release.

### Scene preparation split (schema 2)

These measurements use diagnostic version 2. It adds coarse pre-batch,
geometry, retained-mesh probe, mesh-update, placement and caster scopes. The
probe belongs to geometry; caster belongs to placement. Mesh-update time
includes CPU AABB/tween preparation and RenderingServer calls, not measured
GPU transfer duration. Original array lifetimes are preserved: their eventual
destruction remains in the scene's exclusive residual. Branch counters identify
packet/raw preparation, retained hits/updates/creation and stopped tween writes.

**Ran:** a private extension built from `70ced46` plus this split, with the same
candidate06 engine/PCK/game and route controls described above. OFF and ON pass
20/22 wrapper checks and 89 owning checks each, with normal exits and unchanged
private cards. All four exact command tags pair without assuming equal counter
values; both shifted 600-list native windows pass continuity, live-state/fade
guards and four monotonic attack events. Two complete 300-submission rows cover
each phase in full.

| Instrumented mean, ms/submission | Mission | Hub |
|---|---:|---:|
| Total | 9.555 | 3.158 |
| Geometry excluding measured child work | 3.983 | 0.121 |
| Retained-mesh probe | 0.348 | 0.088 |
| Mesh-update region | 0.871 | 0.210 |
| Placement excluding measured child work | 0.145 | 0.050 |
| Caster excluding material lookup | 0.066 | 0.022 |
| Remaining scene exclusive time | 0.105 | 0.067 |

These are nested regions. Geometry is the largest measured mission region;
the broad split does not yet identify its packet packing, smoothing or raw
parallel-fill subpath. About 13,677 mission and 7,803 Hub clock reads occur per
submission. Both runs record ambient-load overrides, so differences from the
earlier diagnostic do not establish an FPS change or calibrated timer overhead.
The 144 authored retained cases, 69 identical OFF/ON RGB comparisons and 60 MSAA
cases pass again with this extension. The updated portable helper passes 16
controls; the separate strict version-2 reader passes 40 controls. The private
runner's 43 mocked guard/execution controls include owned-process-tree timeout
cleanup and preservation of actual exits and failed verdicts.

### Coarse scene setup (schema 3)

The current opt-in diagnostic adds five call scopes inside scene setup: sky,
models, warm-up/retirement, world preparation and fill. Existing calls, order,
array lifetimes and rendering features stay unchanged. There are no new vertex
or worker clocks. Schema 3 records each scope's scene-setup context; the
[strict reader](../../tools/godot/tests/draw_rows.py) checks that accounting and
retains the original independent native/submit interval checks.

**Ran:** a private Release extension built from `f694b6c` plus these changes,
with all 14 translation units rebuilt, using the unchanged candidate06 engine
and game library and the common diagnostic pack. OFF/ON normal-Load runs each
pass 89 owning checks, eleven effective-quality observations, both guarded
600-submission phases and four attacks per phase. Both exit normally, cards and
runtime hashes remain stable, and all ten window captures were visually
inspected. Vulkan, 1920x1080 targets, 4x MSAA and scale 1 remain applied. OFF emits
no profiling records; ON has two complete 300-submission rows per phase.

| Instrumented mean, ms/submission | Mission | Hub |
|---|---:|---:|
| Sky | 0.001233 | 0.049777 |
| Model preparation (scan/clear group) | 1.284096 | 1.670224 |
| Warm-up and retirement | 0.009038 | 0.009712 |
| World preparation | 0.000385 | 0.000379 |
| Fill | 0.005737 | 0.002805 |
| Remaining scene setup | 0.057325 | 0.065499 |
| Total scene setup | 1.357813 | 1.798396 |

All five groups execute 600 times per phase. Model preparation dominates this
measured setup cost; the substeps inside that group remain unisolated. Both
runs use recorded ambient admission, and timer/bookkeeping overhead is
uncalibrated. This is wall-cost localization, with no OFF/ON speedup, sustained
FPS or explanation of the earlier adverse Hub comparison claimed.

The portable C++ helper passes 16 controls, including disabled-profile silence.
An executed native fake-clock emitter and the reader agree on all 167 fields,
four cuts and two 600-submission windows; these authored costs are not game
timings. The [Python reader controls](../../tools/test_godot_draw_rows.py) use
authored fake-clock fixtures and require no game data.

### Authored model and contact fixture

The [model fixture](../../tools/godot/tests/model_scan_test.gd) sends authored
skinned packets and a ground receiver through the production drawer. Its 13
phases keep one scene alive through repeated, moved, larger, empty, smaller,
hidden and far figures. Ordered contact floats must match exact authored bytes;
hidden and far figures still contribute contacts. Far geometry is offscreen, so
its retention is checked through contact bytes rather than pixels.

Positive curved-model figures and a smooth-1 pixel control establish PN output;
a zero-contact-texture control must change the ground image. These controls
cannot isolate shared-normal welding or inspect the complete weld table. Model
and curved totals are inferred from rounded averages using this fixture's even
draw-count invariant. Generated corners count rebuilds rather than retained hits.
Readback is RGB8 stored as RGBA8 with opaque alpha; original alpha is unqualified.

**Ran on Windows:** Vulkan and OpenGL pass all 13 phases. D3D12 passes every
individual phase's contact, count and visibility checks, but fails the exact
repeat-image guard: one blue byte changes by one between the first near image
and subsequent near images. That case remains failed; the guard has no tolerance
or driver exception. These are authored correctness checks, with no optimization
gain or FPS acceptance established.

Use a fresh authored project stage containing the built extension and shader
dependencies, with no game library, and a fresh output for each API:

```powershell
python -B tools/godot/tests/run_retained_base.py --fixture model_scan --godot PATH/TO/GODOT --cxx PATH/TO/CXX --project PATH/TO/AUTHORED_STAGE --driver vulkan --out PATH/TO/NEW_OUTPUT
```

Repeat with `--driver opengl3` and `--driver d3d12`. The runner owns bounded
import/render processes and rechecks all 26 capture hashes, phase order, contact
bytes, RGB visibility and actual raw-image controls. Its default fixture remains
`retained`. The mocked admission and CLI controls require no engine or game.

### Private Windows model-key investigation

**Executed:** a separate CPU study tests a Windows x64 scalar-conversion fast
path for the welded-normal key, with the original three `lrintf` calls retained
as fallback. Eligibility is checked before floating-point arithmetic; the path
preserves the current rounding mode and requires masked SSE exceptions. The
production translation unit uses the original Release flags, while a separate
strict control unit observes its results without defining the timed algorithm.
All 107,901 assertions pass, including 13,440 key, errno, exception-status and
floating-point-state observations, plus complete authored scan-state checks.
Additional isolated controls compare 24,828 paired keys, errno values and FP
control/status records (x87 CW/SW and MXCSR) across all 64 x87 exception-mask
patterns, three precision modes and independent x87/SSE rounding modes, with
SSE exceptions masked and an empty x87 stack. All pairs
match. Separate headless Godot runs verify that both actual Release DLLs bind
`lrintf` to the same local UCRT export as the new CPU control. This verifies those
live bindings, rather than retrospectively certifying earlier game processes.
Six genuine x87 operation controls confirm pending hardware flags and traps;
this Windows installation reports that denormal control as `INVALID`. The earlier
synthetic control's different expected code remains a failed attempt.
Arbitrary x87 stack/status combinations and other runtime math-library
implementations remain unqualified. Authored scan timings do not establish game
performance.

**Ran:** fresh baseline and candidate Release extensions, each rebuilding all
14 translation units from `89e2f9f`; the candidate changes only this helper and
its guarded intrinsic include. All 39 same-API baseline/candidate images match
exactly. Vulkan and OpenGL each pass both 13-phase fixtures; both D3D12 fixtures
retain the existing repeat-image failure. Separate full-quality Vulkan game
runs each pass 89 owning checks, eleven effective-quality observations and
guarded 600-submission mission and Hub windows with four attacks per phase.
Both close normally, retain 4x MSAA and scale 1, and preserve the cards and
runtime artifacts. All ten window captures were visually inspected.

A separate counted probe reaches the fast branch during the completed
full-quality Vulkan game route. Its bounded final totals agree between the
figures file and runtime log. These are caller-thread aggregates across model
scan and lookup; they do not attribute phase cost. The counted DLL is excluded
from performance evidence.

These private candidates are correctness experiments. Recorded ambient load
prevents performance acceptance; the installed player and production helper
remain unchanged.

The D3D12 discrepancy also survives a single explicit world-viewport redraw
with native frame, submitted scene, geometry, contacts and options frozen.
The one-blue-byte change is present in the RGB8 image returned by
`RenderingServer.texture_2d_get`, before the fixture's conversion and Y flip.
This excludes those fixture operations as necessary causes; it does not expose
the GPU attachment before readback or identify a driver or shader cause.
The exact-repeat guard remains failed and unchanged.

**Ran, 2026-10-28:** two bounded RenderDoc captures of the authored fixture
retain the same one-byte discrepancy and all original phase images. Recorded
model draws use Godot's uber shader on the first render and its specialized
shader on the frozen rerender. Both packets use the same pipeline within each
captured frame; corresponding consumed vertex and attribute bytes match.
The normal, form, rim and stored-colour calculation sequences in RenderDoc's
captured pixel-shader pseudocode match after temporary-value renaming.
Selected-event replays also find identical post-vertex bytes, consumed material,
global, instance and scene values, and recorded raster, depth and blend state.
The only changed dumped buffer field is engine time, which these captured
shaders do not read. Texture pixels, hardware interpolation and attachment
values remain unqualified, so the pipeline transition is an observation, not
an established numerical cause or a repair. Removing either form or rim
lighting suppresses this fixture's discrepancy; those private controls are
not production changes or acceptable quality reductions.

### Windows large raw-mesh scheduling

On Windows, a large raw mesh now fills its eight fixed ranges on the caller
instead of creating seven threads for each draw. The fill arithmetic, padding,
range boundaries and ordered AABB merge are unchanged. Other platforms keep the
existing threaded schedule. An authored CPU study found that a reusable worker
pool was slower than the existing schedule; that pool remains unintegrated.

**Ran:** one Windows baseline/candidate/baseline triplet using the same private
save, route, candidate06 engine/PCK/game library, Remastered Vulkan, 4x MSAA,
scale 1 and Safe 60 Hz target. All three use schema-2 diagnostics. Each passes
22 wrapper and 89 owning checks, with clean exits, movement, four attacks per
phase, ordinary return to the Hub, first-person rendering and unchanged cards.
Every phase covers two complete 300-submission rows and all 600 corresponding
native gameplay guards. Baseline extension `c9acee35` was built from `70ced46`
plus the scene split; candidate `8900b711` from `ec8d61a` plus this scheduling
change. Both retain their recorded dirty build provenance.

| Instrumented mean, ms/submission | Baseline A | Candidate | Baseline B |
|---|---:|---:|---:|
| Mission geometry excluding measured children | 5.081 | 1.758 | 5.345 |
| Mission total drawer | 10.935 | 9.228 | 12.534 |
| Hub geometry excluding measured children | 0.130 | 0.172 | 0.140 |
| Hub total drawer | 3.182 | 3.987 | 3.894 |

Mission geometry is 66.28% below the baseline mean; total drawer time is 21.36%
lower and below both baselines. The Hub result is adverse: 12.67% above the
baseline mean and 2.37% above baseline B. Baselines themselves differ by 14.63%
in mission total and 22.38% in Hub total. All three failed the quiet preflight
and used the recorded ambient-load override. Those prelaunch samples cannot
establish the cause of the Hub change. Counts also vary slightly between runs.
This establishes the observed mission-region result, with no general speedup,
sustained FPS target or player-release acceptance claimed. A cleaner comparison
must resolve the Hub result before promotion.

A later strict six-run cohort accepts its first candidate, then declines the
first baseline before launch for CPU/GPU load. The remaining cases stay unused;
no comparison is admitted from that partial cohort and the quiet limits remain
unchanged.

The candidate repeats the 144 retained phases, 69 identical OFF/ON RGB
comparisons and 60 MSAA phases. A separate authored large-raw fixture runs
eight transitions on both extensions across Vulkan, OpenGL and D3D12: 48 phases
and 24 same-API image pairs with no differing pixels. It exercises same-count
movement/recolouring, growth, shrink/reuse, zero geometry, flat/raw transitions
and 294,912 corners. Production allocation/reuse counters prove the large path
is reached; 60 CPU corpus cases compare complete padded buffers and AABB words.
Readback is RGB8 stored as RGBA8 with opaque alpha, so these comparisons do not
qualify original scene alpha. Mac/Linux runtime performance remains untested.

The reusable [GPU fixture runner](../../tools/godot/tests/run_retained_base.py)
accepts `--fixture big_raw`; its default remains the retained-placement test.
Use a fresh authored project stage containing the built extension, with no game
library, and fresh output paths:

```powershell
python -B tools/godot/tests/run_retained_base.py --fixture big_raw --godot PATH/TO/GODOT --cxx PATH/TO/CXX --project PATH/TO/AUTHORED_STAGE --driver vulkan --out PATH/TO/NEW_OUTPUT
```

Repeat with `--driver opengl3` and `--driver d3d12`. The fixture imports shader
dependencies before rendering and checks every tile, empty regions, production
path counters and saved captures. Its single-build result is separate from the
private baseline/candidate timing comparison.

**Ran through the public CLI:** all eight large-raw phases on each of the three
APIs, plus the existing default's 24 retained phases on Vulkan. All exit cleanly;
the 24 large-raw captures match the qualified candidate's same-API pixels.
The new fixture uses the bounded headless editor startup already used by
`build.py`. Immediate `--import --quit` reproduced the known first-import
shutdown crash on a cold stage; the bounded startup passes on a fresh cold
stage. This is a tested startup procedure, not a general engine lifecycle fix.
Twenty mocked runner controls and the full 2,291-test Python discovery pass.

### Bracketing the large-mesh counters

The opt-in rig command `app drawer-figures FILE.json` saves the existing drawer
totals, current host blank/native frame and an exact drawer instance ID. The ID
is a signed decimal string: RefCounted object IDs can be negative and exceed
JSON readers' exact numeric range. The command does not submit or advance a
frame. Current native metadata is not a completed-submission counter; rig
commands are handled before that submission, while socket delivery can occur
at a different point in the host loop.

For a rig-delivered bracket, require the same drawer instance, monotonic totals,
independent host/native ordering around both cut markers and enough completed
drawer lists to cover the window. A zero change in both BIG allocation and
reuse counters excludes direct execution of the changed fill block throughout
the contained window. A positive change is broader than that block, and the
bracket includes surrounding frames. Zero does not exclude effects of earlier
work, code generation or binary layout.

**Ran:** a fresh candidate and baseline with strict prelaunch checks, the same
engine/game and a common diagnostic PCK. A control repack reproduces C06 byte
for byte; the diagnostic pack changes only `main.gdc` among 183 payloads.
Both game runs pass 25 wrapper and 89 owning checks. In each, the full 600-list
Hub window lies within a 668-list bracket with unchanged BIG counters. The
modified fill loop therefore was not directly executed in those Hub windows.
Their instrumented Hub totals are 3.220 ms/submission for the candidate and
3.191 for the baseline. These two runs do not establish a performance result.

The planned six-run sequence remains incomplete: the next launch was declined
when Windows returned invalid performance-counter data. A follow-up capture
found invalid GPU counters for processes that exited during that sampling;
it does not identify the exact cause of the earlier counter error. The declined
attempt launched no game and is preserved. A separate earlier attempt was
declined for CPU load. No quiet limits were relaxed, and prelaunch sampling
does not describe continuous load during gameplay. The original adverse Hub
observation and release hold remain open.

The authored [command regression](../../tools/godot/tests/drawer_figures_command_test.gd)
passes 32 headless checks against the actual host handler with an unstarted
native machine and a formatter spy. Use a fresh private project stage containing
the built extension and patched `main.gd`, with no game library; provide a
fresh, empty output directory. Register the extension with the bounded editor
start first. The relative-path check writes one JSON file inside that private
project. Launch the test by its absolute path:

```powershell
PATH/TO/GODOT --headless --path PATH/TO/AUTHORED_STAGE --editor --quit-after 120 --frame-delay 50
PATH/TO/GODOT --headless --path PATH/TO/AUTHORED_STAGE --script ABSOLUTE/PATH/TO/tools/godot/tests/drawer_figures_command_test.gd -- --out PATH/TO/EXISTING_OUTPUT
```

## Reproduce with fresh staging and outputs

From the repository root, with the pinned dependencies available:

```powershell
$qaStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$env:RTA_GODOT_OUT = Join-Path (Get-Location) "local/godot-render-check-$qaStamp"
python -B tools/godot/build.py extension --platform windows --jobs 4
python -B tools/godot/build.py project --platform windows
python -B tools/godot/run.py import
foreach ($qaDriver in @('vulkan', 'd3d12')) {
    python -B tools/godot/run.py --display-driver windows --rendering-method forward_plus --rendering-driver $qaDriver --script res://dev/gpu_timer_test.gd -- --out "$env:RTA_GODOT_OUT/timer-$qaDriver"
    if ($LASTEXITCODE -ne 0) { throw 'Inspect the GPU fixture result and engine log.' }
}
python -B tools/godot/run.py --headless --script res://portal/dev/session_library_test.gd -- --lib 'PATH/TO/PRIVATE/librta_game.dll' --out "$env:RTA_GODOT_OUT/portal-session"
python -B tools/godot/run.py --display-driver windows --rendering-method forward_plus --rendering-driver vulkan --script res://dev/override_engine_test.gd -- --out "$env:RTA_GODOT_OUT/override-engine-vulkan"
```

The [portal session regression](../../tools/godot/project/portal/dev/session_library_test.gd)
uses the actual API-compatible library's authored mock before game boot: fixed
source passes 13/13 checks; the old packed portal and a same-extension control
without the library config key reproduce the unavailable-session failure. It
requires an explicit private library outside automatic search locations, but no
disc, simulation or GPU. Use fresh isolated profiles; never publish its private DLL.

A zero exit code, JSON checks and engine-error scan must agree. Headless execution
cannot qualify GPU rendering. See [native-godot.md](native-godot.md) for build options
and [windows-pc-qualification.md](windows-pc-qualification.md) for separate native evidence.
