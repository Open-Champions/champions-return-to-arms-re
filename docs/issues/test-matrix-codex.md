# Regression matrix: main snapshot, execution blocked

Date: 2026-10-26. Revision: `849074465baefad0e5f6fc33f620a89ae7aa6bd9`.
`HEAD` matched the checkout's `origin/main`; the working tree was clean at the start.
This is the translated native/Godot line in this repository. No other checkout's build
or earlier test result is credited to this run.

At the final revision check, `HEAD` was unchanged but `origin/main` had advanced to
`623846382d4fcfed0f0cd890e04affc4916fed7a` (model-remaster round 2: eight changed files).
That update includes Godot C++, scripts, configuration and a shader. **This report
applies to the starting main snapshot, not that newer revision.** The worktree was
not switched during the run.

**Total: 35 rows, 2 PASS, 33 FAIL.** Of the 33 FAIL rows, **32 are blocked by the
execution environment and 1 is incomplete**. These are failures to complete the
requested validation, not 33 observed game defects. The full regression was **not
completed**. No runtime regression can be concluded from the blocked rows.

The first command was `python3 tools/doctor_home.py native godot`: exit 0,
**0 would hang or fail, 1 warning, 4 fine**. The warning concerned an old checkout
alias. The doctor found no evicted file among 763 native and 10,357 Godot entries.
Its successful input check did not establish permission to write build outputs.

The session allows writes in this checkout and temporary directories. Both private
input links resolve outside the checkout. Native, arithmetic, Godot, Linux, Windows
and setup builds encountered `PermissionError`, errno 1, when writing under `local/`.
The local rendezvous test separately encountered errno 1 at its loopback socket bind.
Process inspection, `ps -axo pid=,comm=`, was also denied. The session does not allow
permission escalation.

**0 game processes were launched by this run; 0 rooms and 0 gameplay ticks were
measured.** The pre-existing process count could not be inspected. Native build
commands used `rta_app_codex` and `rta_app_codex_orig`; the protected default binary
was not a build target. Godot's requested output was `local/godot-codex/`.
No public game service was contacted, no BIOS or disc was downloaded or shared,
and no commit or push was made. Private helper contents and raw logs are omitted.

Every original matrix row is retained below, in its original order. A blocked
prerequisite was actually attempted as recorded in the command ledger. Its dependent
game commands were **not run**: in particular, no existing private binary was used
as a substitute for a failed current-source build. Command letters identify how to
reproduce the observed blocker, not an executed gameplay recipe. The complete
gameplay recipes remain in [the source matrix](test-matrix.md).

| ID | Original area and test | Result | Numbers and execution boundary | Reproduce |
|---|---|---|---|---|
| 1.1 | Core proof: arithmetic corner cases | FAIL (blocked) | `arith.py build` exit 1; 0 newly built proof executables; integer, FPU and VU stages not reached | A |
| 1.2 | Core proof: mode-off rig comparison, overhead and first person | FAIL (blocked) | Original native build exit 1; 0/2 reference comparisons run | N0 |
| 1.3 | Core proof: interpreter soak quick check | **PASS** | Flush **13 PASS, 0 FAIL**; sections **61 PASS, 0 FAIL**; **74/74** total; both commands exit 0 | Q |
| 2.1 | Native Mac: clean-tree fixed and original builds | FAIL (blocked) | Fixed build exit 1; original build exit 1; 0 new current-source application binaries completed | N, N0 |
| 2.2 | Native Mac: boot and art pack | FAIL (blocked) | 0 boots, 0 texture-resolution measurements; current native build unavailable | N |
| 2.3 | Native Mac: five views, body modes, aiming | FAIL (blocked) | 0/5 views and 0/3 body modes exercised; 0 aim transitions measured | N |
| 2.4 | Native Mac: boss music | FAIL (blocked) | 0 routes, 0 track-load or crossfade measurements | N |
| 2.5 | Native Mac: report, crash report and build line | FAIL (blocked) | 0 reports, 0 intentional crashes, 0 report archives inspected | N |
| 3.a | Native online: Classic, 2 and 3 copies | FAIL (blocked) | 0/2 rooms, 0 pair comparisons, 0 ticks; build and loopback prerequisites unavailable | N, C |
| 3.b | Native online: Hardcore, 2 and 3 copies | FAIL (blocked) | 0/2 rooms, 0 pair comparisons, 0 ticks | N, C |
| 3.c | Native online: look aiming, 2 and 3 copies | FAIL (blocked) | 0/2 rooms, 0 aim-message or projectile measurements | N, C |
| 3.d | Native online: Hardcore plus look aiming, 2 and 3 copies | FAIL (blocked) | 0/2 rooms, 0 ticks; no current-run synchronization conclusion | N, C |
| 3.e | Native online: drop, host quit, second game | FAIL (blocked) | 0/3 scenarios, 0 second-game launches | N, C |
| 4.1 | Hardcore offline: combat mechanics and death drops | FAIL (blocked) | 0 routes; parry, riposte, stance, counter, backstab, flask and drop counters unmeasured | N |
| 4.2 | Hardcore offline: weapons, load tiers, upgrades, arts, two-hand | FAIL (blocked) | 0/3 routes; no weapon or damage counters measured | N |
| 5.1 | Emulator Mac application: room host plus native join | FAIL (blocked) | 0 mixed rooms, 0 ticks; no emulator started against an unavailable native build | N, C |
| 5.2 | Emulator Mac application: local lobby and login-screen route | FAIL (blocked) | 0 lobby routes, 0 account submissions, 0 rooms | N, C |
| 6.1 | Linux: both builds, floating point, boot, rig | FAIL (blocked) | `--docker both --original` exit 1 before container work; 0/2 architectures rebuilt; 0 floating-point, boot or rig comparisons | L |
| 6.2 | Linux plus Mac room: Hardcore and aim | FAIL (blocked) | 0 rooms, 0 ticks; neither required current build completed | L, N, C |
| 7.1 | Windows VM: build and README checks | FAIL (blocked) | Cross-build exit 1; 0 VM executions; 0 floating-point, boot or image-decoder comparisons | W |
| 7.2 | Windows plus Mac room: Hardcore and aim | FAIL (blocked) | 0 rooms, 0 ticks, 0 desktop-session jobs | W, N, C |
| 8.1 | Godot: hub, scene mode, art pack, HUD | FAIL (blocked) | `build.py all` exit 1; 0 imports, 0 boots, 0 visual checks | G |
| 8.2 | Godot: 2-copy portal room, Hardcore and aim | FAIL (blocked) | 0/1 room, 0 ticks, 0 portal interactions | G, C |
| 8.3 | Godot: shop screens and boss music | FAIL (blocked) | 0 shop routes, 0 screenshots, 0 music routes | G |
| 9.1 | Setups: all three platforms and no-game-data proof | FAIL (blocked) | Builder exit 1 at output-directory creation; 0/3 platforms, 0/4 packages; package `--check` stage not reached | S |
| 9.2 | Setups: fresh-home Mac installation and boot | FAIL (blocked) | 0 installations, 0 installed-game boots; no new setup available | S |
| 10 | Repository hygiene: paths, identities, private endpoints, game data | FAIL (incomplete) | **1,308 tracked files**, **1,309 proof entries** including an archive member, **32 private executable samples**, **0 proof problems**; 2 home-prefix matches, both the documented virtual-filesystem exception, 0 real home-path matches; 3 context identity patterns, 0 matching lines. Exact private server-address/hostname scan incomplete: **0 configured non-loopback literals** in the checked default configuration sources | H |

Added coverage for changes since the original matrix:

| ID | Feature and required exercise | Result | Numbers and execution boundary | Reproduce |
| 11.1 | Hardcore attributes and spellbook: offline route plus 3-copy room; point spending, slot changes, spell hits, persistence through a level change | FAIL (blocked) | 0 offline routes, 0/1 three-copy room, 0 spell-hit comparisons; [combat evidence and repeat recipes](native-souls-combat.md), sections 4.9–4.11 and 7 | N, C |
| 11.2 | Cutscene hold-to-skip in a 2-copy Remastered room | FAIL (blocked) | 0/1 room; 0 solo-hold and joint-hold trials; no skip tick, prompt or shutdown result. Required route: one copy holds for 90 ticks without a skip, then both meet the 60-tick hold; compare the scene-ending tick on both. [Cutscene procedure](native-cutscenes.md), section 3 | G, C |
| 11.3 | Party scaling in a 3-copy room | FAIL (blocked) | 0/1 room, 0/3 pair comparisons, 0 scaling/elite/extra-creature counters; actual party count 3, then the documented forced-size case if repeated. [Party procedure](native-8-players.md), B.5 | N, C |
| 11.4 | Guest-memory map overlap check and module constants | **PASS** | Compiled both `partyscale.cpp` and `party8.cpp`: exit 0. **7 blocks, 21 distinct pairs, 0 overlaps**. Five module-map `static_assert` statements compiled. An intentionally overlapping temporary header failed compilation with the expected overlap assertion, exit 1: **1/1 negative control rejected** | M |
| 11.5 | Eight-player groundwork: relocated-table offline and mode-off regression gates | FAIL (blocked) | 0 relocated builds, 0 poison/check routes, 0 rig comparisons. This is the groundwork gate in [the eight-player document](native-8-players.md), C.1–C.2; no room larger than three was launched | N |
| 11.6 | Elden Ring presentation layer: fit, player identity, weapons, view modes, and layer-on/layer-off room equivalence | FAIL (blocked) | 0 visual states, 0 rooms, 0 ticks; [layer gates](native-er-layer.md) remain unverified on this revision | G, C |
| 11.7 | Model remaster: appearance gate and layer-on/layer-off room equivalence | FAIL (blocked) | 0 visual states, 0 rooms, 0 ticks; [remaster gate](native-model-remaster.md) remains unverified on this revision | G, C |
| 11.8 | Online WebSocket fallback via `check_client.py` | FAIL (blocked) | Client compilation completed; harness exit 1 after **66.851 s**. Local service failed at `bind`, errno 1. **0 client checks evaluated, 0 WebSocket fallback checks reached**; the TCP, TLS and WebSocket stages did not execute | C |

Actual command ledger (elapsed time is wall-clock seconds). Output was captured
privately; only status and numeric observations are reproduced here. Build commands
were run from the checkout root. `--as` is the native Mac builder's option; the
platform-specific builders use their separate output directories.

| Key | Command actually attempted | Exit | Seconds |
|---|---|---:|---:|
| A | `python3 tools/recomp/proof/arith.py build` | 1 | 3.236 |
| N | `python3 tools/recomp/app/build.py --as rta_app_codex` | 1 | 52.454 |
| N0 | `python3 tools/recomp/app/build.py --original --as rta_app_codex_orig` | 1 | 16.353 |
| Q1 | `python3 tools/recomp/soak/flush_test.py` | 0 | 2.851 |
| Q2 | `python3 tools/recomp/soak/sections_test.py` | 0 | 2.786 |
| G | `RTA_GODOT_OUT=local/godot-codex python3 tools/godot/build.py all` | 1 | 0.283 |
| L | `python3 tools/recomp/app/build_linux.py --docker both --original` | 1 | 1.071 |
| W | `python3 tools/recomp/app/build_win.py --compiler clang` | 1 | 28.796 |
| S | `python3 tools/install/setup/build_setups.py --out local/test-matrix-codex/setups` | 1 | 0.969 |
| C | `python3 tools/rendezvous/check_client.py --work /private/tmp/rta-codex-matrix-yz8obnfq/client` | 1 | 66.851 |
| M | `clang++ -std=c++17 -fsyntax-only -Itools/recomp/app -Itools/recomp/rt tools/recomp/app/partyscale.cpp tools/recomp/app/party8.cpp` | 0 | 28.947 |

For A, the source matrix's command chain stops at the failed build. Its continuation
is `python3 tools/recomp/proof/arith.py int --jobs 3`, then `fpu --jobs 3`, then
`vu --jobs 3`, with the same script path. These stages were not run against old
executables. Q means both Q1 and Q2.

For M, the negative control changed only a temporary copy of the public header:
the aim interval's start from `0xE1800` to `0xE1400`, inside the Hardcore interval.
`clang++ -std=c++17 -fsyntax-only -x c++ TEMP_HEADER` rejected it with
`two guest-memory blocks of the native modules overlap (guestmap.h)`.
No tracked source was edited. This verifies the compile-time guard, not live
gameplay or the completeness of all possible guest-memory users.

For H, the data proof used `tools/install/setup/build_setups.py`'s `Proof` over
`git ls-files`, reading private samples only in memory. Matching lines and private
needles were not printed. The two additional endpoint sources checked were the
documented environment override and native application's default data-folder
configuration. Neither yielded a non-loopback endpoint. This does not establish
that no private endpoint exists elsewhere. The three context identity patterns
also do not establish an exhaustive personal-name inventory.

The remaining literal scan requires the actual private address and hostname,
supplied privately. A reproduction command for this missing-input gate and scan is:

```sh
: "${RTA_AUDIT_IP:?private address required}" "${RTA_AUDIT_HOST:?private hostname required}"
git grep -n -I -F -e "$RTA_AUDIT_IP" -e "$RTA_AUDIT_HOST" > /private/tmp/rta-codex-private-matches.txt
```

The command must not be interpreted as a pass when the inputs are absent. Its
matched text must remain private. The public report should record only counts.

To complete the matrix, the execution environment needs access to the designated
private build-output directories, local service socket binds, and process
inspection. Then select and record the current main revision, rebuild it, run every deferred source-matrix
recipe against those new binaries, and perform the added feature exercises above.
Godot gameplay and exports must come from `local/godot-codex/`; the setup builder's
older default Godot exports must not be credited as current-main builds. Keep at
most three game processes and use only test-local services. The missing private
literal inventory is a separate hygiene prerequisite.

The only repository file added by this run is this report. No implementation
change, historical-test result, or guessed gameplay count is included as a pass.
