# Codex test-matrix rerun

STATUS: COMPLETE: **26 PASS / 5 FAIL / 5 SKIP** across 36 rows (35 prior matrix rows plus the documented moved-table room)

Executed on 2026-10-26, macOS 27.2 arm64. Snapshot: **`b24e65569e1338a2e4bdebe3ad952511fb285205`**, also the locally recorded `origin/main` when the run began. No fetch, commit, or push. This replaces the earlier sandbox-blocked report; the results below are executions from this run.

The tracked source was archived into `local/codex-matrix-20261026/tree-codex` because several builders hard-code `local/recomp-out`. All new builds, cards, settings, logs, reports, and test artifacts are beneath the codex run directory. Existing Godot dependencies, VU translation, art, music, and the disc executable were reused as inputs. `RTA_DISC` came from the existing local launcher configuration; the disc image was neither copied nor moved. The installed emulator was tested as an existing dependency, not rebuilt from this snapshot. Its executable SHA-256 is `b9f3b0fe7ac9eb5fe061ee78a34aa1fe6d20d89052cfadd287711256f827f302`.

Only processes started by this run were stopped. Drop/hostquit and the intentional tester-kit crash are controlled exceptions to clean exit. All test services were configured and bound to loopback. **The emulator lobby has a routing defect: it replaces an explicitly supplied loopback server with this Mac's non-loopback interface.** Its three local attempts logged 468 / 612 / 420 refused TCP connections to this Mac, not a remote server. The attempt was stopped when that code path was identified; it was not retried afterward. This is row 5.2, not a claim of full compliance by the tested program.

## Results

A row passes only the scope described in its evidence. SKIP means an unexecuted prerequisite or platform gate, not a failure. For three-copy rooms, pair counts are host/joiner 1, host/joiner 2, and joiner 1/joiner 2. All reported successful room counts have zero differing shared columns and all surviving scripts completed.

| Row | Test | Result | Evidence from this run |
|---|---|---|---|
| 1.1 | Full arithmetic proof | PASS | Integer: **156 instruction words, 156,000,000 operand sets, 0 differences**. FPU: **24 instructions × 1,980,400 sets = 47,529,600**, all three implementation/reference difference columns zero. VU: **225 forms; 52,500,000 lane results each with and without flush-to-zero, 0 / 0 differences**. Full defaults, `--jobs 3`; no reduced sample counts. |
| 1.2 | Original-mode comparison, overhead and first person | PASS | Newly built original binary. **5 episodes and 7,576 compared ticks per view**. Reports byte-identical to the saved expected reports: **34/34 overhead lines, 35/35 first-person lines**. Each native replay: **7,797 frames / 7,904 fields**. Expected cosmetic/loading differences in the saved baseline remain visible. |
| 1.3 | Soak flushing and section selection | PASS | `flush_test.py`: **13 passed, 0 failed**. `sections_test.py`: **61 passed, 0 failed**. **74/74** total. This is the documented soak test pair, not a multi-hour gameplay soak. |
| 2.1 | Native application build | PASS | `--as rta_app_codex`: exit 0, **55/55 game and 47/47 app objects**, **189 fix-set words + 2 existing private sign-in words**, **0 `rt_unimpl`**. Original build exit 0, **54/54 game and 32/32 app objects**. Elapsed **284.827 / 238.238 s**. |
| 2.2 | Native boot and art pack | PASS | Hub checkpoint at **frame 2,413 / simulation tick 60**. Completed **2,909 frames / 3,013 fields**. Pack: **122,205 files, 380 textures named / 378 found, 428 pictures read, 0 unreadable, 0 dropped**. Images inspected. |
| 2.3 | Native views, body modes, aim toggle | PASS | Five views and three first-person body modes captured and inspected. First-person near planes **4 / 14 / 4** for off/arms/full. Aim: **149 player ticks, 2 messages sent/applied**, pitch changed, then mode returned off. Projectile coverage is in room row 3c. |
| 2.4 | Native boss music | PASS | **82 tracks** found; engaged **tick 2,422**, playing **2,515**, fight over **3,009**, game music restored **3,189**. **538,941 audio frames mixed, 347 engaged blanks, 1 track played**. Route completed **5,790 frames / 5,897 fields**. No speaker-listening claim: execution used no-sound with the machine audio clock. |
| 2.5 | Tester-kit report, crash and restart | PASS | Report box visibly opened, typed text rendered, valid **5-file report zip**, **2,907 input/tick rows**, **1,280 × 896 screenshot**. Intentional crash exited **70**; valid **3-file crash zip**, **2,412 input/tick rows**. Restart exit 0 and discovered the prior crash report; **366 frames / 420 fields**. |
| 3a | Classic native, 2 and 3 copies | PASS | Hub → drunare. Two copies: **4,600** ticks. Three copies: **4,558 / 4,557 / 4,557**. |
| 3b | Hardcore native, 2 and 3 copies | PASS | Valor → drunare. Two copies: **5,593** ticks, **4 deaths / 2 all-dead reloads**. Three copies: **5,701 / 5,699 / 5,699**, **4 deaths / 1 reload**, final **3 drops** on all copies. |
| 3c | Aim native, 2 and 3 copies | PASS | Hub → drunare. Two copies: **6,085** ticks, **12 projectiles aimed** on each. Three copies: **5,981 / 5,980 / 5,980**. Guest aim watches use this revision's **`AIM_BASE = 0xE1800`**. |
| 3d | Hardcore + aim native, 2 and 3 copies | PASS | Two copies: **5,730** ticks, **2 deaths / 1 reload**, **2 drops** on both. Three-copy evidence: **5,640 / 5,640 / 5,652** ticks, **3 deaths / 1 reload**, all three scripts done. |
| 3e | Drop, hostquit, then another game | PASS | Drop **1,527** shared ticks and host finished; hostquit **1,581** and joiner finished. Only the deliberately dropped owned copy exited **-9**. Again: **1,414 / 1,219** ticks in two games in the same processes. |
| 4.1 | Hardcore combat offline | PASS | **11,258 frames / 11,374 fields**. Parries **3**, ripostes **1**, stance criticals **1**, backstabs **1**, guard counters **5**, flasks **3**, refills **1**, drops **3**, picked up **2 / 625 gold**, lost **250 gold**. |
| 4.2 | Weapons, load, upgrades, arts, two-hand | PASS | Axe and mace routes each **8,100 frames / 8,207 fields**. Axe: **2 arts, 4 upgrades, 1 material, 2 two-hand toggles, 4 interrupted heavies, 1 cancelled swing**. Mace: **3 arts, 4 upgrades, 1 material, 2 toggles**. All-weapon route: **11 arts**, **5,960 frames / 6,067 fields**. Counts are current observations, not copied historical expectations. |
| 5.1 | Installed emulator hosts native from title | FAIL | Both launched, both scripts completed, hub → drunare, **2,404 ticks in step**. Native exited cleanly; emulator then exited **-6 / SIGABRT** in its display-refresh callback. Diagnosis F1. |
| 5.2 | Emulator lobby login screen, then menu room | FAIL | **0 completed login-form arrivals, 0 game ticks**. Loopback-only lobby server started, but emulator rewrote its server address to this Mac's other interface and received connection refusals. Stopped without entering credentials or creating an account. Diagnosis F2. |
| 6.1 | Linux Docker build, fpcheck, boot and rig | SKIP | No running/usable local Docker daemon or configured local context. **0 Linux builds / runtime checks**. No Docker startup, remote context, or download attempted. |
| 6.2 | Linux + Mac room | SKIP | Same absent Docker prerequisite; **0 rooms / 0 ticks**. |
| 7.1 | Windows cross-build and VM checks | SKIP | **Build portion PASS** without Docker: clang cross-build exit 0 in **132.889 s**; `fpcheck.exe` **223,744 B**, `pnghash.exe` **249,344 B**, `rta_native.exe` **26,463,744 B**, `rta_app.exe` **29,087,232 B**. Windows VM runtime checks **not run** under the Mac/loopback-only scope. |
| 7.2 | Windows + Mac room | SKIP | The documented VM route requires a non-loopback VM connection. **0 rooms / 0 ticks**. |
| 8.1 | Godot build, import, hub, scene, art, HUD | PASS | Requested build into **`local/godot-codex`** and import both exit 0 (**2,942.428 / 37.138 s**). Offline scene **2,840 frames / 2,944 fields**; art **372 named / 370 found, 0 unreadable**. Four views inspected; full portal captures verify the new HUD, compass and quick slots. |
| 8.2 | Godot portal room, hardcore + aim | PASS | **1,860 shared ticks**, hub → drunare; both copies exit 0. Portal and in-game captures inspected. |
| 8.3 | Godot shop and boss music | PASS | Shop **7,067 frames / 7,171 fields**, **15 images**, Buy list, tabs, item card and cannot-buy state captured. Boss route **5,790 frames / 5,897 fields**, **82 tracks**, engaged **2,422**, playing, fight over **3,008**, game music restored. |
| 9.1 | Three-platform setup packages and data proof | PASS | Built with pinned source and the existing local Godot export inputs. Mac zip **71,648,975 B**, Windows exe **45,018,606 B**, Linux script/zip **63,826,910 / 63,827,056 B**. Rechecked all four: **1,326 / 1,318 / 1,321 / 1,322 entries**, **32 private code samples**, **0 game-data findings**. Existing export inputs were packaged, not freshly cross-built. |
| 9.2 | Fresh-home Mac installation | SKIP | The shipped installer writes the application/library outside `local/`; it has no complete output-root override. This conflicts with the required output boundary, and this session also forbids repurposing `HOME`. **0 installations**. No shared installation was replaced. |
| 10 | Repository hygiene | PASS | Snapshot: **1,310 tracked files**, proof **1,311 entries / 32 private samples / 0 findings**. **0 real home-path hits**, **0 matches for 4 personal/machine identity needles**, **0 matches for 2 configured endpoint needles** read from **10 local configurations**. Values were not printed. Emscripten's virtual home path is excluded. |
| 11.1 | Attributes and spellbook, offline + 3-copy room | PASS | Offline stats **6,920 frames**, **2 points spent**; spells **6,896 frames**, **5 casts / 5 hits / 0 refusals**. Three-copy evidence: **5,529 / 5,522 / 5,522** ticks through valor → drunare; **5 points spent, 1 slot change, 9 casts, 0 room spell hits, 26 refused casts**, equal on every copy at the end. Positive spell-hit coverage is the offline route. |
| 11.2 | Two-copy cut-scene hold-to-skip | PASS | **1,805 shared ticks**, **256 active-scene ticks** identical. Solo hold: **85 counted ticks**, **0 skips**, prompt **1/2**. Joint hold: prompt **2/2**, both skip at **network tick 1,377**, one skip each, exits 0. Raw comparator's only difference was stale `cutf` on **1,120 inactive-scene ticks**; active scene-frame values had **0 differences**. |
| 11.3 | Party scaling, actual 3 and forced size 8 | PASS | Offline size 1: **98 scaled creatures, 3 elites, 0 extras**; forced 8: **173 scaled, 48 elites, 75 extras, 19 refused spawns**. Three-copy evidence: Actual 3 and forced size 8 each **4,920 / 4,920 / 4,920** shared ticks. Actual 3: **107 scaled / 7 elites / 0 extras / 0 refused / 3 bosses**; forced 8: **184 scaled / 44 elites / 77 extras / 16 refused / 3 bosses**; all counters equal on all copies. Forced-size testing does not mean eight players were connected. |
| 11.4 | Guest-memory overlap and constants | PASS | Both modules compiled; **7 blocks / 21 pairs / 0 overlaps**, all five map/module static assertions compiled. Deliberately overlapping local header rejected by the expected compile-time assertion: **1/1 negative control**. |
| 11.5 | Relocated-table offline and mode-off gates | PASS | Dynamic-map and check builds exit 0. Unmoved, poison at first blank, and poison at title each **74/74 watched rows identical** to normal; all four dynamic/baseline routes **4,970 frames / 5,077 fields / 191,328,956 units**. Normal two-copy room **4,930** ticks; unmoved relocatable two-copy room **4,932**, both valor → drunare. Check-only diagnostic reported **8 reported old-address call sites** and **0/74 equal rows**; it is not the dynamic-map build and is not claimed clean. |
| 11.5b | Documented moved-table room, poisoned at boot | FAIL | Dynamic and check builds: **0/2 launched, 0 shared ticks, both copies exit 3**. The scripts timed out waiting to leave intro at **frames 8,454 / 7,876** (dynamic) and **8,457 / 7,876** (check), after **142 / 143 s**. Diagnosis F5 if failed. This exercises the document's explicitly unfinished launch, separately from the passing groundwork gates. |
| 11.6 | ER presentation layer and layer-on/off room | FAIL | Real layer and fallback observed in full captures; fitting and identity logs emitted. Room shared state matched for **1,856 ticks**, but copy A signalled **11** during background glTF import and eventually exited **-6**; copy B exited 0. Tester-kit captured the crash at **vertical blank 3,000**. Diagnosis F3. |
| 11.7 | Model remaster appearance and on/off room | PASS | Full images inspected; A reported **13 baked models / 31 mapped textures / 4.6 figures per frame**. B had `RTA_REMASTER_MODELS=off` and **0 remaster bake messages**, while retaining the same ER input path. **1,831 shared ticks**, no differing shared columns, both exit 0. |
| 11.8 | Rendezvous TCP/TLS/WebSocket fallback | FAIL | Shipped `check_client.py`: **130/136 checks passed** in **121 s**, six WebSocket-room checks fail. A separate ordering-only diagnostic passed **18/18**, including **60/60 tunnel datagrams**. The shipped suite remains FAIL. Diagnosis F4. |

## Exact commands and retained evidence

In the commands below, run from the repository root:

```sh
MATRIX_CODEX="$PWD/local/codex-matrix-20261026"
TREE_CODEX="$MATRIX_CODEX/tree-codex"
RUN_CODEX="$MATRIX_CODEX/helpers-codex/run.py"
```

`run.py` supplies the existing disc path privately, clears inherited service endpoints, supplies the loopback test address, disables core dumps, captures raw logs privately, and records child exit status. It prints only the tag, exit and elapsed time. Its own exit is not the test verdict: use `results-codex/TAG.json`. Native/Godot local helpers redirect outputs and fixture paths into this run, use unique test ports, and limit owned concurrent game processes. The copied aim-room watches were updated to the current header's address. No implementation source was patched to manufacture a pass.

Core build/proof invocations (all executed in `TREE_CODEX`):

```sh
python3 tools/recomp/proof/arith.py build
python3 tools/recomp/proof/arith.py int --jobs 3
python3 tools/recomp/proof/arith.py fpu --jobs 3
python3 tools/recomp/proof/arith.py vu --jobs 3
python3 tools/recomp/app/build.py --as rta_app_codex
python3 tools/recomp/app/build.py --original --as rta_app_codex_orig
RTA_GODOT_OUT=local/godot-codex python3 tools/godot/build.py all
RTA_GODOT_OUT=local/godot-codex python3 tools/godot/run.py import
python3 tools/recomp/soak/flush_test.py
python3 tools/recomp/soak/sections_test.py
python3 tools/recomp/app/build.py --party8 --as rta_app_codex_p8
python3 tools/recomp/app/build.py --party8 --party8-check --as rta_app_codex_p8check
python3 tools/recomp/app/build_win.py --compiler clang --jobs 3
```

Room recipes and exact options are retained in `helpers-codex/room_task.py`, `helpers-codex/party_rooms.py`, the copied Godot room helpers, and `results-codex/room-*-recipe.json`. `room_task.py MODE N` covers classic, hardcore, aim, both, drop, hostquit, again, stats, party0, and party8; its N is the actual number of copies. Fixtures, every stdout/stderr log, tick traces, and exit records remain beneath `local/codex-matrix-20261026`.

Arithmetic reports: `tree-codex/local/recomp-out/proof/arith/{int,fpu,vu}.txt`. Original comparison reports: `runs-codex/compare-rta_app_codex_orig-{overhead,first}/compare.txt`; byte-equality result: `results-codex/original-reference-comparison.json`. Visual review contact sheets: `pictures-codex/native-contact-codex.jpg`, `godot-contact-codex.jpg`, `godot-rooms-shop-contact-codex.jpg`, `cutscene-contact-codex.jpg`; the individual report-box image is `native-report-box.png`. Raw artifacts are private and are not added to Git.

## Failure reproductions and code diagnoses

### F1 — Emulator display-clock lifetime (row 5.1)

Exact isolated invocation:

```sh
python3 "$RUN_CODEX" emulator-title-installed -- python3 "$MATRIX_CODEX/helpers-codex/emulator_room.py"
```

The helper runs `tools/play-net/roomparty.py` with the installed emulator, the new native binary, `--copies app,native --app-start title --play 900 --level drunare --play2 900`, isolated data and loopback room service. Both scripts finished and 2,404 ticks matched before shutdown. The captured macOS crash stack is `std::mutex::lock → Play image offset 484256 → CVDisplayLink::performIO`, with `mutex lock failed: Invalid argument`.

[tools/play-net/src/RtaMac.mm](../../tools/play-net/src/RtaMac.mm), lines 105–152, owns a namespace-static mutex and starts a display link. `OnRefresh` locks that mutex at line 125. There is no paired `CVDisplayLinkStop`/release before static destruction. The observed exit-time callback is consistent with locking the destroyed mutex. This is a display-clock lifetime failure, not a measured lockstep divergence. Stack evidence: `results-codex/emulator-crash-stack.json`; room evidence: `rooms-codex/emulator-title-installed-codex/`.

### F2 — Emulator rewrites loopback to a non-loopback interface (row 5.2)

Recorded invocation, **not to be rerun under the present loopback-only restriction**:

```sh
python3 "$RUN_CODEX" --timeout 1800 emulator-lobby-default -- python3 "$MATRIX_CODEX/helpers-codex/emulator_lobby.py"
```

The helper starts its own loopback-bound lobby and rendezvous services, then uses `--app-start lobby --signin-patch FILE --menu-start`, with the loopback value supplied to both server options. No login name, password, or account creation was supplied. The final attempt reached login state 0 with a message box, not state 2; it logged 420 refused connection attempts before termination. Earlier attempts are retained, including an initial test-port allocation error and the custom-port retry.

[tools/play-net/src/Rta.cpp](../../tools/play-net/src/Rta.cpp), lines 1320–1335, treats a loopback address as “own”, then unconditionally replaces `config.serverIp` with `PrimaryAddress()` when one exists. [RtaNet.cpp](../../tools/play-net/src/RtaNet.cpp), lines 971 and 995–997, connects to that rewritten address. Private log comparison verified that it was this Mac's interface, not loopback. The code therefore cannot satisfy this row's loopback-only requirement as shipped. `results-codex/lobby-routing-evidence.json` records booleans and counts without revealing addresses. The misleading “NO SIGN-IN PATCH” notice also appeared despite “2 more words” being applied; the packaged explicit-extra-patch path does not populate `g_launch.signinPatch` (Rta.cpp:3217–3238), but that notice is not the cause of the refused TCP connection.

### F3 — glTF scene generation on a worker thread (row 11.6)

```sh
python3 "$RUN_CODEX" --timeout 1800 godot-room-er -- python3 "$MATRIX_CODEX/helpers-codex/godot_task.py" godot-room-er
```

[tools/godot/project/er_layer.gd](../../tools/godot/project/er_layer.gd), lines 699–705, puts `GLTFDocument.append_from_file` and `generate_scene` inside `WorkerThreadPool.add_task`. The crash report follows `WorkerThreadPool → GDScript lambda → GLTFDocument::generate_scene → ImporterMesh::get_mesh → ArrayMesh::surface_set_material → MaterialStorage::material_set_shader`, fault address `0x38`. Godot also reports “Caller thread can't call this function in this node” at `er_layer.gd:704`. This directly implicates scene/material creation in the background task. Waiting for tasks in `_exit_tree` does not make those renderer operations safe on that worker. The race may not reproduce on every run; another model-layer room completed cleanly. Evidence: `helpers-codex/godot-room-er/a.txt` and its `a/card/reports/crash-*/about.txt`. **1,856 equal ticks do not excuse the crash.**

### F4 — WebSocket test assumes the opposite join order (row 11.8)

```sh
python3 "$RUN_CODEX" rendezvous-absolute -- python3 tools/rendezvous/check_client.py --work "$TREE_CODEX/local/client-absolute-codex" --verbose
```

[tools/rendezvous/check_client.py](../../tools/rendezvous/check_client.py), lines 766–767, sends Wren's join before Wynn's without waiting. Lines 779–797 then assume Wynn occupies slot 1 and Wren slot 2. This run assigned Wren slot 1 and Wynn slot 2. The six failures are the two route assertions, three datagram direction checks, and the 60-datagram burst check, all using those incorrect slot assumptions.

`helpers-codex/ws_diagnostic.py` loads a private in-memory copy of the suite, changes only the join ordering to Wynn first, waits for count 2, then joins Wren, and executes the WebSocket portion. **18/18 checks pass**, including the complete burst. This isolates a harness ordering bug; no tracked implementation or test file was changed, and the original 130/136 result remains a failure.

### F5 — Poisoned moved-table room remains unfinished (row 11.5b)

```sh
python3 "$RUN_CODEX" party-room-poison -- python3 "$MATRIX_CODEX/helpers-codex/party_rooms.py" poison
python3 "$RUN_CODEX" party-room-check-poison -- python3 "$MATRIX_CODEX/helpers-codex/party_rooms.py" check-poison
```

Both copies connected, chose characters and received a room start, but neither reached `net2: launched`; the trace contains no game ticks. The check build reported only the out-of-line `LD32` access to old `g_pads + 0x10` on each copy. The same relocatable binary with `party8=0` completed 4,932 ticks, while the dynamic mapping also passed all three offline 74-row comparisons.

The failure is localized to the **moved-memory game launch path**, not service registration. [net2/launch.cpp](../../tools/recomp/net2/launch.cpp):218–260 prepares the direct launch; its completion path at 321–339 requires the game's launch flag to clear. That completion is never observed after moving/poisoning the 16 tables. [rt/recomp.h](../../tools/recomp/rt/recomp.h):94–115 checks/maps translated memory accesses, while native raw readers are outside that check; for example [app/cinematic.cpp](../../tools/recomp/app/cinematic.cpp):15,23–26 still reads fixed `g_pads` without `party8_at`. The latter is a verified incomplete reader, **not proven to be the particular launch-blocking reader in this Classic test**. The exact offending reader/instruction remains unidentified. The evidence reproduces the incomplete relocation boundary documented in [native-8-players.md](native-8-players.md):373–408; it does not justify a fabricated one-line root cause or a claim of eight-player support. Logs and traces: `rooms-codex/party-room-{poison,check-poison}/`.


## Harness corrections, controls and limits

- Initial combat and axe runs hit the helper's **480-second wall guard**, exits 4 at **11,084 / 4,878 frames**. Fresh-data reruns with an **1,800-second guard** completed. These are retained workload/time-limit results, not hidden gameplay failures. Wall times include contention from unrelated work and, for wrapper records, time waiting for this run's game slots; they are not performance benchmarks.
- The initial original-comparison wrapper stopped on `boot-compare`'s exit 1, which reflects expected differences from the emulator trace. Independently comparing the generated reports to the documented expected reports showed exact byte equality in both views. The wrapper was corrected to apply that actual gate.
- A relative `--work local/client-codex` fails before rendezvous checks: [check.py](../../tools/rendezvous/check.py):65–90 forms a relative `pki/test.cnf`, then runs OpenSSL with `cwd=pki`, duplicating the relative path. Using an absolute work path reaches all 136 checks. This was a setup defect, not a socket sandbox failure.
- Building setup sources from the nested archive directory initially yielded an empty Git archive because Git walked up to the enclosing checkout. The successful builds ran the builder at the real repository root with explicit `--ref` and a codex output directory. The related `buildid.py` ancestor-discovery issue still prints a `+` on archive builds; it does not change the pinned source snapshot used here.
- The cut-scene fixture labels a stale inactive-scene frame counter as shared. Its raw compare exit is 1, solely for `cutf` before the new scene. `results-codex/cutscene-comparison.json` records all 1,805 ticks, the 256 active-scene ticks, and equal skip tick 1,377. The scene's actual hold/skip gate passed; the raw diagnostic is preserved.
- The first emulator attempt used the old default local binary, whose control socket did not implement the current room commands. It timed out with 0 game ticks. The installed application's supported room commands were then used for the measured title result. This is not evidence that the obsolete default binary passes.
- Godot's macOS launcher emitted a sandbox-extension warning, but build/import and scene execution actually ran. The boss fixture's obsolete `music say` command is retained as a harmless unsupported diagnostic; music state transitions were independently observed.
- Fresh-home install was not forced outside the allowed output tree: [setup-mac.sh](../../tools/install/setup/mac/setup-mac.sh):33–35 and [fromdisc.py](../../tools/install/fromdisc.py):283–286,326–330 target the user's application/library locations. Docker/VM exclusions above remain explicit skips. No remote servers, new dependencies, authentication steps, commits, or pushes were requested to complete them.

Only `docs/issues/test-matrix-codex.md` is intended to change in tracked files. Source fixes for the observed failures are outside this rerun's scope.
