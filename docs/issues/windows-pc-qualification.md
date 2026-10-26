# Windows PC qualification and fixes

Status: **Ran on a physical Windows x86-64 PC, 2026-10-21 to 2026-10-22.**
These are bounded checks of the translated native game. They do not establish a
completed campaign, recovered original source, or original-console pixel fidelity.
The rules in [DIRECTION.md](../DIRECTION.md) apply; every player supplies their own disc.

## Scope and identity

- Original qualification base: `f3fe79166a5714b3b4c3d29c0209bf40b91194f5`.
- Input: US v2.00 `SLUS_209.73`, 5,777,312 bytes, SHA-256
  `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
- Windows build 26200, x86-64; RTX 4080 SUPER, OpenGL 4.1, driver 616.56;
  LLVM-MinGW UCRT 20261006, clang 23.1.3; the existing 189-word fix set.
- Results span successive fixes, not one rebuilt binary. The final installed
  sample/depth build was SHA-256
  `d7c2258b9fa65ea1dd5616b0d64e29e8491aef7e567ecab3431f3cb97b07eb93`.
  Later private prototypes were separate and remained uninstalled.
- Only authored source, fixtures and summarized results are contributed. Disc data,
  generated translations, binaries, saves, raw captures and full receipts stay local.

## Defects and fixes in this change

| Defect | Change and bounded evidence |
|---|---|
| Releasing one keyboard alias cleared another held alias | Aggregate physical scan-code identities, including the extended flag; retain separate identities for posted test keys and clear on focus loss. Native regressions cover both release orders, two Shift keys and NumLock changes. |
| Mouse side-button messages never reached existing controls | Route XBUTTON down/up through the existing five-button mapping. Native message tests pass; physical side-button play remains open. |
| Windows vibration requests never reached XInput | Map large/small motors, cache successful output, and release on focus loss, detach, synthetic takeover and shutdown. Mocked callbacks test retries and cleanup; felt vibration remains open. |
| Empty GS copies were reported as unsupported transfers | Do not count zero-area transfers; retain upload flushes and command order. The 54-check GIF fixture and 3,011-frame counter-only replay pass. Nonempty unsupported copies still count. |
| Missing 1x1 indexed textures could bypass texture alpha rejection | Resolve only a proven uniform 256-entry palette with the required complete upload and CLD2 load; invalidate on overlapping writes and ambiguous state. The 95-check GIF fixture covers load/alias/continuation guards; an authored GPU alpha/depth canary passes 16 checks. General retained VRAM is still unsupported. |
| Historic display metadata incorrectly clamped a wider reused surface | Use fresh FRAME/transfer stride evidence while preserving narrow/film behavior and main's newer wide boot-card fix. The 33-check fixture covers both. Historically, the three-scene diagnostic's missing-texture states fell from 72 to three. These counts are draw states, not missing pixels. |
| Same-size framebuffer reuse ignored requested MSAA changes | Include the requested mode in reuse, remember unsupported fallback, retain colour, and preserve depth only when physical size and actual GL sample counts match; other transitions keep cleared depth. Authored WGL fixtures cover transitions, reuse, rounding and fallback; see the image-change note below. |
| Normal Windows completion lost buffered network-log tails | Flush the tick stream on the game thread through the existing finish callback, then chain its predecessor once. A matched two-copy trial retains all 613 complete ticks instead of 604 plus a partial row; 22 shared columns match. |
| Rendezvous qualification was not portable or strict enough | Support Windows child startup/default programs and require successful script completion, expected game logs and positive matching-frame coverage. Window launches pass the Windows-only logging flag only on Windows. |
| Qualification test failed with a symlinked `local/` | Compare resolved destinations and checkout roots; retain the restriction against output in tracked directories. Real symlink regressions accept external private output and reject links back into tracked directories. |

**Expected default image change:** the GS extent correction and backend allocation
fix restore **4x MSAA on the 3D surface**. It had silently been off on the earlier
main build, so default captures change, including smoother edges. The maintainer
accepts this as a fix and will refresh references at merge. The maintainer reports
identical output with `--plain`; the earlier Windows no-AA three-scene comparison
also matched. This does not establish original-PS2 pixel fidelity. Separate small
readback differences occurred even between unchanged Windows baselines; their
cause remains unassigned and strict equality is not claimed for those captures.

## Recorded PC qualification

These are historical receipts for the builds above; software injection, offscreen
runs and mocked output are identified explicitly.

| Area | Recorded result | Boundary |
|---|---|---|
| Authored native input | 129 state/message, 22 rumble and 39 mapping checks; zero failures | Rumble callbacks mocked; no full physical-controller session pass |
| Python tools | 675 tests passed at the original qualification revision | Later main and review-fix revisions require their own run |
| Arithmetic / PNG / boot | Checksums `2e77df4dc13ec9c5` / `b4ed3d8917871960`; hub at 2,309 frames, 2,413 fields, 113,069,252 units | Supported disc identity checked; original data remains private |
| Application input | 62 held/released software cases passed through the compiled window handler/test adapter | Does not measure physical latency or control feel |
| GS fixtures | Transfer 54, uniform palette 95, display extent 33; zero failures | Authored public-interface packets |
| WGL target lifecycle | 157 checks per mode passed, normal and simulated two-to-four sample rounding | One physical GPU/driver; simulated rounding is not another driver |
| Ordinary gameplay | Creation, first-mission dialogue/portal, combat for all seven starting classes, earned level/stat/skill allocation, inventory and shop actions | Bounded scripted routes; matched no-attack controls used for class combat |
| Save / Load / Recall | Earned XP and checked equipment/allocations survive normal writes and fresh Loads; installed checkpoint retains 1,888 XP and armour 54 | A later 1,913-XP kill was unsaved; first mission remains unfinished |
| Local co-op | Tested two-owner combat, owner saves, party-wipe recovery, survivor revival and hub return | Software inputs and selected routes; not all combinations or physical multi-pad play |
| Four network clients | One-PC direct/forced-relay hub intervals: 1,072/1,087 common ticks, 37 shared columns matching | Loopback native launch adapter; not retired login screens or WAN/NAT |
| Separate online cameras | Two installed clients: 908 common ticks, 29 shared columns matching; independent local follow/rotation | Offscreen one-PC test, sound disabled; no display-performance claim |
| Visible pacing / audio | Selected sessions around 60 pictures/s; normal device/mixer output captured | No sustained performance bar or audible-quality qualification |

Some headless repeatability fixtures pinned initialization CPU-counter inputs;
reported ordinary gameplay routes did not directly write HP, XP, positions or
inventory. Destination-request rendering sweeps were diagnostic setup, not normal
mission transitions. Failed controls, timed-out attempts and corrected offline
checkers remain failed or partial in the private receipts.

The [maintainer's PR review](https://github.com/Open-Champions/champions-return-to-arms-re/pull/3)
on 2026-10-25 separately reports byte-identical simulation in overhead and
first-person modes, including the Godot library; passing GS tests on macOS,
Windows and Linux; and two-copy level changes with 4,555 direct / 4,595 relay ticks
in step. Those are maintainer results on the reviewed revision, not additional
Windows runs by this contributor or a test of subsequent review fixes.

## Open work and separate prototypes

- Complete good/evil campaigns, quests, difficulties, skill ranks, wider combat and
  durable mission/world progression remain unqualified by these PC tests.
- Reference rendering remains open: general retained VRAM, three remaining texture
  states, repeat-edge sampling and rendered CT16 precision. Authored no-AA CT16
  canaries showed native red 255 versus reference red 248. Private CT16/CT16S and
  frame-queue experiments are not part of this change and do not close that gap.
- Private discovery/launcher, multi-pad/multitap and live-control prototypes have
  bounded software-input, combat, party-save/fresh-Load and stored-return evidence.
  Their implementation is not contributed here. Full Save acknowledgement and
  story progression remain open; later passage stalls and input-expiry attempts
  added no completion coverage. Strict default-off visual equivalence failed for
  the live-control candidate, which remains private and uninstalled.
- Separate-PC/WAN/NAT rooms, public directory deployment, physical multi-controller
  sessions/hotplug, side buttons, felt vibration, audible quality and long-session
  performance still need PC qualification. One physical controller had partial
  actuation coverage and positive user feedback, but its full planned trial failed.
- The standalone PC tests do not qualify the Godot host. Follow-up changes to shared
  GS code still require the project's cross-platform/Godot/lockstep checks.

## Repeat the authored and disc-based checks

Review follow-up on `f36a8ba` main, 2026-10-26: all 2,235 Python tests pass,
including real symlink and Windows/POSIX launcher regressions. Native input,
mocked rumble and mapping pass 129/22/39 checks; GS fixtures pass 54/95/33,
including main's newer wide boot-card behavior. WGL passes 178 checks in each
of normal and simulated two-to-four rounding modes on the same GPU. The old
PR backend fails eight checks in the expanded depth fixture. These are authored
fixture runs; the merged game, other platforms, Godot and live rooms were not
rerun for this follow-up.

Use your own supported disc and an existing locally built package. Build outputs
and game-derived output must remain under ignored `local/` or outside the checkout.

```text
python tools/recomp/app/win/tests/run.py --cxx <Windows-C++17-compiler>
python tools/recomp/render/tests/run.py --cxx <C++17-compiler>
python tools/recomp/render/tests/run_gl.py --cxx <Windows-C++17-compiler>
python tools/recomp/app/win/qualify.py --disc <own-US-v2-disc>
python -m unittest discover -s tools -p "test_*.py"
```
