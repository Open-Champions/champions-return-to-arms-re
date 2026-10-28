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

Separate actual Remastered evidence passed **81 functional checks**, reached the
mission and hub, exited cleanly and preserved card/artifact hashes. Phase handovers
were approximately **50.5/s mission and 60.1/s hub** under that run's ambient load.
These are host frame handovers, not OS presents or a sustained-60-FPS verdict.
That packed run preceded the new provider; repeat the paced route after rebuilding.

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
