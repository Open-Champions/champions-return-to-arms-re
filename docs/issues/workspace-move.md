# The workspace moved (2026-10-13)

Kept current while the work goes on. Every statement says whether it was **Ran** (with
what was seen) or only **Read**. Helpers and results of this work: `local/rehome/`
(nothing of it is in the repository).

## STATE (rewritten at every step; read this first after a stop)

**19:45 - the list is worked through; nothing of this work is running except the lobby.**

- The new home builds and tests: native programs, emulator application, lobby, Godot
  library. `python3 tools/doctor_home.py` says what is whole (output at the end).
- Candidates beside the program in place: `local/recomp-out/bin/rta_app_next` and
  `rta_app_orig_next` (standing checks passed). `bin/rta_app` (f3, 14:37) is untouched;
  the owner's running copy (pid 17482) was not disturbed.
- The lobby runs from `server/upstream-fresh` (pid 26138, same `bin/config.ini`, the
  database came across). The old one (pid 75327) was stopped.
- **An accident of this work at 19:31, read "The tool that replaced files"**: ten tracked
  files and seven files of `local/recomp-net2` were put back to their state of before the
  move. The tracked ones are restored to the last commit; uncommitted changes of the
  online-service work between 19:24 and 19:31 are lost.
- Still not in the new home: **78,444 files, 112 directories**; of them **19,234 cannot be
  made again** and must come from iCloud ("Inventory").
- Three things wait for a decision: the sign-in patch file, the extension's link, and
  which directory is "the" emulator tree ("Left for the owner").

## What happened

- The checkout lived at `~/Desktop/champions-re`, inside a Desktop that iCloud Drive
  synchronises with "Optimize Mac Storage" on. When the disk filled on the afternoon of
  2026-10-13, macOS **evicted** tens of thousands of its files: such a file is still
  listed with its size, but its data is not on this disk ("dataless"), and a read of it
  blocks until iCloud has brought it back - possibly for ever.
- 18:38: the project was moved. **The real home is `~/champions-re`** (not synchronised):
  a fresh `git clone` of the repository plus an APFS clone of every file that was on the
  disk at that moment. `~/Desktop/champions-re` is now a **symbolic link** to it, so old
  paths in scripts, in built programs and in notes still work.
- The old folder is kept as `~/Desktop/champions-re-icloud-old`. It still holds the
  evicted files as placeholders. Not brought across at 18:38: 78,547 files and 112
  directories. Eviction went on afterwards (13,164 more files of the old folder by 18:55;
  their clones in the new home are not affected).
- Everything tracked by git is complete in the new home (it came from GitHub; **Ran**, a
  stat-only comparison: of 623 tracked files 409 are evicted in the old folder, none with
  a size other than the committed one, so no uncommitted change of a tracked file is
  stuck in iCloud). What is missing is in untracked places: `local/`, `decomp/`,
  `extracted/`, `disc/`, `scripts/*.txt`, `scripts_raw/`, `server/upstream`, `work/`, and
  the files at the top (`SLUS_209.73` among them).

## The rules

1. **Never read inside `~/Desktop/champions-re-icloud-old`**: no `cat`, `cp`, `ls -lO`,
   `du`, `grep`, `git status`, no build. A read of an evicted file can hang the shell for
   good. The same for any path of the missing list.
2. To learn whether a file is evicted, ask only for its flags (this reads no data):
   `stat -f "%Sf" FILE` (the word `dataless`), or `find DIR -type f -flags +dataless`.
3. To bring across what iCloud has given back since:
   `python3 tools/rehome_fetch.py ~/Desktop/champions-re-icloud-old ~/champions-re local/rehome/fetch.log`.
   It clones what is on the disk **and the new home does not have**, never opens an
   evicted file, never touches a file the new home has, and prints how many are still
   missing. **Do not run the first tool of the move (`integrate/rehome.py` in the
   coordinator's scratchpad) again**: it replaces every file of the new home whose size or
   time differs from the old folder's - see "The tool that replaced files".
4. Do not delete or rename the old folder or anything in it; change no system or iCloud
   setting; no `brctl`, `tmutil`, `killall` on system services.
5. New working directories go under `~/champions-re/local/`, never under `~/Desktop` or
   `~/Documents` (both are synchronised).
6. Before a build or a test: `python3 tools/doctor_home.py` (or with the areas you need:
   `native checks emulator lobby godot soak proof analysis`). It only asks for names,
   sizes and flags, so it cannot hang; exit code 1 means a build would hang or fail.

## What was rebuilt, and how each was checked (all Ran)

**The game's executable.** `SLUS_209.73` was among the evicted files. Copied out of the
owner's disc image (`tools/recomp/disc.py extract SLUS_209.73`): 5,777,312 bytes, SHA-256
`292f6f48...dcd675`, the figure of `tools/doctor.py`, and the same as two copies that had
survived in work directories.

**The native build.**

- The translations: `python3 tools/recomp/app/build.py --as rta_app_next` (fix set: 99
  words of 29 sections, and the 2 words of the local sign-in patch) and `--original --as
  rta_app_orig_next`. 31 of `gen-app`'s and 35 of `gen`'s files had been evicted; all were
  written again. **Check: the headless by-products `bin/rta_native` and
  `bin/rta_native_fix` came out byte for byte the programs of 14:32 / 14:33** (`cmp`
  against copies kept for the comparison): translation and compilation repeat exactly.
- The vertex programs (`gen-vu`): both generated files were evicted. Copies of the same
  two files survive in six work roots, all with one checksum each; they were put back
  from `local/recomp-speed/root` and `local/recomp-fp/root`. **The recorded streams the
  translator needs are evicted** (`local/recomp-speed/streams/`: `hub`, `fire3-fight`,
  `fire3-start`, `drunare-start`, `drunare-fight`; also `hub12`, `pole`, `haze`; only
  `title.rtavs` is here). From the executable and `title.rtavs` the translator gives two
  of the three programs, **the same text as in the surviving file, line for line**; the
  third (pair 0x79a, 102 pairs: a fight's small program) cannot be translated again until
  a fight stream is back or recorded anew (`app record FILE` in a fight). The build does
  not need it: without the files the programs are interpreted, slower.
- **The local sign-in patch `local/SLUS-20973_4028A55F_signin.pnach` is evicted.** Without
  it `app/build.py` builds a program without the sign-in skip, silently. It was not
  copied. Three files of that name lie in `local/dist-web/play/` and
  `local/rel.nosync/site-*`; the one in `dist-web/play` gives the same two words as the
  translation of 14:31 that survived (compared by program, nothing printed), and the build
  was pointed at it with `RTA_SIGNIN_PATCH` (the variable `app/build.py` and `play.sh`
  read). Every build of the window program needs that variable until the file is back.
- **The window program did not compile at the commit of the move**, and had not since
  15:23: commit 86952c7 took `hostlook::state()` out of `app/look_host.h` and
  `look_mac.mm` while `app_main.cpp` still calls it (the Godot round's log of 15:5x shows
  the same error). The 18 lines were put back as they were in 1b5ce93. Not caused by the
  move.
- **The standing checks of `native-app.md` 12** on the two candidates
  (`s12/verify.sh h1 ...`): 11 tick-keyed pictures the same with the fast renderer, the
  reference switches, and against `prev-fast` / `prev-plain-fast`; the rig comparison
  (7,904 fields) the same file as `merge/rig-final-compare.txt` three ways, byte for byte;
  the tour: 60 pictures of 20 levels the same fast, reference, against `prev-fast` and
  against f3's, no time-out. Summaries: `local/rehome/verify-h1/`.
- Inputs of those checks that were evicted, and what stands in their place (the list:
  `local/rehome/stand-ins.tsv`; a file iCloud gives back does not replace a stand-in by
  itself, compare by hand):

  | Missing | Stand-in | Sure because |
  |---|---|---|
  | `app-test/rigsnd/boot-rig.tsv`, `boot-rig-breaks.log` (the rig's log) | the copies `s12/rig.sh` made for f3 (`s12/rig/f3-plain-fast/`) | `rig.sh` copies them with `cp` |
  | `app-test/merge/rig-final-compare.txt` | `s12/rig/f3-plain-fast-compare.txt` | `verify-f3.txt` records them as the same by `cmp` |
  | `local/recomp-out/fight3.rig` | `local/recomp-fp/work/rig/first/fight3.rig` | all 499 conditions f3's run logged are in it in order; the result file is the same |
  | `app-test/rigsnd/rc.py` (helper) | written anew: `rigcompare.py` with its directory from `RC_OUT` | the result file is the same |
  | `local/recomp-speed/out/det-fast.rig` | f3's route without the seven extra pictures | `mkdet.py` gives f3's route from it, line for line |
  | `local/play-out/tourplan.py` (the tour's camera points) | none; `local/rehome/tour-from-route.sh` runs the tour from f3's route | 60 pictures the same as f3's |

- The rig runs use the program's default data directory: they wrote the four files of the
  network setting again into `local/recomp-out/app-data/card/mc0/BWNETCNF` (evicted in the
  old folder; the program makes them itself, same sizes).

**The emulator application.** `local/play-playable` lost 5,108 files, its `.git` among
them. A new tree: `RTA_PLAY_SOURCE=local/play-playable-rehome
RTA_PLAY_BUILD=local/play-playable-rehome-build tools/play-net/build.sh` (clone of Play!
at 83700b2, `play-net.patch`, `src/`; 53 s).

- The built program is **the same as the two that survived, but for 99 bytes** (the
  link's identifier, a build time, the signature): `play-playable-build` (10:52) and
  `play-stable-build` (13:00).
- As a silent test copy without network (`play.sh`, `--rta-test`, `--rta-no-net`, a data
  directory of its own; driver `local/rehome/play-title.py`): title reached, the log reads
  **"patches: 29 sections, 99 words, set 073064bb"**. The same run with the two surviving
  applications: the same line, and the title picture is the same file in all three.
- The stable tree (`play-stable-src`, lost 4,510 files): `local/play-stable-tools` came
  across whole and is file for file `tools/play-net` and `patches/` of the repository, so
  its recipe makes the tree above; run on it, it says the patch is in and relinks.
- Stat-only: no file of either old source tree was changed after its last build, so no
  change is lost that was only in a tree.
- `/Applications/Play-RTA.app` was not touched.

**The lobby.** `server/upstream` lost 704 files (sources, `build.sh`, most of `.git`).
The fork was cloned beside it: `server/upstream-fresh` (branch `macos-port`, e693af1),
`sh build.sh`. The old process (pid 75327, started from the old folder) was stopped by
pid after the build; `bin/config.ini` (the owner's, 1,860 bytes; the repository's own
default is kept beside it as `config.ini.repository-default`) and
`bin/database/game.db` were cloned in - the database was on the disk and unchanged since
15:16 in the old folder (169 accounts, 91 characters, `integrity_check` ok). Started as
`nohup sh run.sh > bin/server.out 2>&1 &`: pid 26138, the same ports listening.

**The Godot side.** `local/godot-spike` came across whole (0 files missing).

- `build.py lib` and `lib --original` from the snapshot in place: **`librta_game.dylib`,
  `librta_game_orig.dylib` and `bin/rtag_host` byte for byte the files of 15:52**.
- The smoke test (`test/smoke/s.rig` through `rtag_host`): 409 blanks, both pictures the
  same files as this morning's. The staged project started in Godot without a window
  over the same script (`tools/godot/run.py --headless`): the same two pictures.
- `build.py snapshot` was not run again (it would replace the snapshot of 15:52); read
  and tried apart: `recomp.patch` applies to `tools/recomp` as it is, the compiled game
  it takes is there.
- **`build.py extension` does not link at the commit of 19:21** (c6791a2 and later):
  `tools/recomp/net2` gained `cardchars.cpp`, which `session.cpp` and `session_mock.cpp`
  need and `tools/godot/extension/CMakeLists.txt` does not compile
  (`net2impl::CLASS_WORDS`, `card_characters` undefined). Tried apart: with that file
  added the link succeeds; with `net2` as it was at the move the extension builds (683,352
  bytes, the size of the staged one). Not changed here: the file belongs to work that is
  under way. The failed link had removed the staged
  `project/bin/rta_godot.macos.template_debug.dylib`; it was put back from a copy taken
  before.

**Other files made again from the disc image**: `SYSTEM.CNF` and the 11 evicted files
of `disc/` (each the size of its placeholder), `disasm/text.asm`
(`tools/gen_disasm.py`; 26,305,822 bytes - the old one, made on 10-09, was 26,204,730). With
the executable and the disassembly back, `python3 -m unittest discover -s tools -p 'test_*.py'`
runs: 652 tests, OK.

**The soak farm and the proof tools (looked at, not rebuilt).**

- The farm's kit `local/recomp-out/soak/farm3.nosync/kit` is whole (the `.nosync` name
  kept it from being evicted), with its four programs. Missing: the frozen runtime
  objects `soak/rt-frozen` (no `--rt frozen` link; `--rt live` builds with the runtime as
  it is now, which is not the frozen state), `soak/objcache`, `obj-nofix`, `obj-fix26c`
  and two finished arms' programs (a rebuild by `build_soak.py` is possible), 14 section
  lists and one proposed patch file of finished arms, and the results (below).
- The proof programs are there (`proof/build/bin`: `rta_proof`, `rta_proof_vu`,
  `proof_driver`, `proof_test`), as is the rig (`local/rig-build/rta_rig`). Missing: 21
  files of the snapshot they were built from (`proof/snap`: a rebuild means a new
  snapshot, from today's sources), `proof/emu/Play.app` (a directory, evicted as a whole),
  the old places `bin/proof_test`, `bin/proof_driver`, and the results: recorded states
  (`proof/real/*/captures.bin`, `pages.bin`), comparisons, logs. `local/play` (the Play!
  tree the rig is built against) lost 5,152 files: clone again as `tools/rig/README.md`
  says.

## The tool that replaced files (19:31; an accident of this work)

The tool of the move (`integrate/rehome.py`) replaces a file of the new home when the old
folder's copy is on the disk and differs in size or time. On the day's first runs nothing
differed. Run again at 19:31, after an hour of work in the new home, it put **3,355 files
back to their state of before the move** (the list: `local/rehome/run-1935.put-back.txt`):

- 3,337 of them are objects, programs and generated lists this work had made again
  (Godot's cmake directory, `obj-*`, `bin/rta_native*`, `godot-spike/lib`): the same
  content, or made again by the next build. Nothing of the candidates was touched.
- **Ten tracked files**: `tools/recomp/net2/{launch,net2cli,session,session_mock}.cpp`,
  `session.h`, `session_impl.h`, `tools/recomp/app/look_host.h`, `look_mac.mm`,
  `docs/PROGRESS.md`, `docs/issues/native-rendezvous.md`. Restored at 19:34 to the last
  commit (dd45743, 19:23:57). **What was changed in them after that commit and not
  committed is lost**: at least one declaration - `session_net.cpp` (19:27, not touched)
  no longer compiles against the restored headers ("only virtual member functions can be
  marked 'override'", `carrier()`, line 802).
- **Seven files of `local/recomp-net2`** (the online-service work): `build.sh` (now the
  version of 14:02), `work/one.sh` (14:05), `bin/net2cli-mock` and four objects; and
  `local/rel.nosync/RELEASE-NOTES.txt` (now the version of 13:22). Their versions of after
  the move are gone. A note lies in `local/recomp-net2/PUT-BACK-BY-REHOME-1932.txt`.
- Two files were rightly brought across (newer in the old folder): the old lobby's last
  log lines.

`tools/rehome_fetch.py` replaces the tool: it never touches a file the new home has. Its
first version here did not skip `local/hd-pack/replace.old.nosync` (which the move left
out on purpose) and cloned its 122,207 files; they were removed again at once.
One thing it cannot do: a file that is newer in the old folder stays behind. None is
known now (the running native program finds its data through the old path, which is the
link into the new home).

## Inventory: what is still not in the new home

78,444 files and 112 directories at 19:40 (the list: `local/rehome/fetch-1940.log.missing`;
sorted by `local/rehome/inventory/classify.py`, names only; its lists are beside it).
"NOT re-creatable" is what must come back from iCloud.

| Group | Missing | by a build or tool | clone again | from history | from the disc | sync copies | NOT re-creatable |
|---|---:|---:|---:|---:|---:|---:|---:|
| `local/three-players` | 12,425 | 953 | 9,574 | 176 | - | 68 | 1,654 |
| `decomp/` | 6,693 | - | - | - | 6,693 | - | - |
| `local/rig-out` | 5,386 | 4 | - | - | - | 18 | 5,364 |
| `local/play` | 5,152 | - | 5,150 | - | - | 2 | - |
| `local/play-playable` | 5,108 | - | 5,106 | - | - | 2 | - |
| `local/play-web-src.before-release2-1013` | 4,785 | - | 4,785 | - | - | - | - |
| `local/play-web-perf-src` | 4,783 | - | 4,783 | - | - | - | - |
| `local/play-web-src.before-release-1012` | 4,743 | - | 4,743 | - | - | - | - |
| `local/play-stable-src` | 4,510 | - | 4,432 | - | - | 78 | - |
| `local/recomp-out/win` | 1,956 | 1,797 | - | - | - | 2 | 157 |
| `local/recomp-out/app-test` | 1,879 | - | - | - | - | 5 | 1,874 |
| `local/native-lobby` | 1,596 | 63 | - | - | - | 5 | 1,528 |
| `local/recomp-out/ (the rest)` | 1,368 | 1,037 | - | - | 7 | 219 | 105 |
| `local/play-web-out` | 1,301 | 1 | - | - | - | - | 1,300 |
| `local/recomp-web` | 1,200 | 537 | - | 355 | - | - | 308 |
| `local/hd-work` | 1,134 | - | - | - | - | - | 1,134 |
| `local/recomp-out/soak` | 1,062 | 287 | - | - | - | 1 | 774 |
| `local/play-stable-build` | 953 | 191 | - | - | - | 762 | - |
| `local/mixed` | 863 | 25 | - | - | - | - | 838 |
| `local/recomp-out/net` | 820 | 78 | - | - | - | - | 742 |
| `server/upstream` | 704 | 83 | 423 | - | - | 166 | 32 |
| `local/play-web-perf-out` | 695 | 47 | - | - | - | - | 648 |
| `local/recomp-speed` | 672 | 231 | - | 263 | - | - | 178 |
| `local/play-playable-build` | 634 | 469 | - | - | - | 165 | - |
| `local/qa` | 616 | - | - | - | - | - | 616 |
| `local/play-data` | 571 | - | - | - | - | 9 | 562 |
| `local/recomp-out/proof` | 546 | - | - | - | - | 1 | 545 |
| `local/play-web-build.before-release-1012` | 458 | 408 | - | - | - | 48 | 2 |
| `local/server-audit` | 421 | - | 174 | 167 | - | - | 80 |
| `local/play-web-perf-build` | 419 | 381 | - | - | - | 36 | 2 |
| `local/rig-build-fast` | 408 | 405 | - | - | - | 3 | - |
| `local/play-web-perf-build-eh` | 399 | 398 | - | - | - | - | 1 |
| `local/rig-build` | 395 | 371 | - | - | - | 24 | - |
| `local/server-audit2` | 395 | 136 | - | 170 | - | - | 89 |
| `local/play-web-build.before-release2-1013` | 393 | 391 | - | - | - | 2 | - |
| `local/play-web-build-prof` | 392 | 392 | - | - | - | - | - |
| `local/play-web-perf-build-base` | 390 | 388 | - | - | - | - | 2 |
| `local/rig-build-mixed` | 378 | 378 | - | - | - | - | - |
| `local/server-work` | 324 | - | 169 | 154 | - | - | 1 |
| `local/recomp-out/online` | 215 | - | - | - | - | - | 215 |
| `local/play-out` | 207 | 1 | - | - | - | - | 206 |
| `local/sound` | 185 | - | - | - | 160 | - | 25 |
| `work/` | 141 | 22 | - | 55 | 7 | 2 | 55 |
| `scripts_raw/` | 116 | - | - | - | 116 | - | - |
| `scripts/` | 110 | - | - | - | 110 | - | - |
| `extracted/` | 71 | - | - | - | 71 | - | - |
| `tools/` | 60 | 53 | - | - | - | 7 | - |
| 23 smaller groups | 412 | 38 | 45 | 77 | 11 | 44 | 197 |
| **All** | 78,444 | 9,565 | 39,384 | 1,417 | 7,175 | 1,669 | 19,234 |

What the columns mean:

- **by a build or tool** (9,565): objects, libraries, programs, translations, cmake and
  ninja files, Python caches - the build scripts make them (`tools/recomp/app/build.py`,
  `build_win.py`, `build_soak.py`, `net/build_net.py`, `tools/play-net/build.sh`,
  `tools/play-web/`, `tools/rig`); made PNG test files (`app/win/pngtest.py`); two
  downloads (the upscaler with its model, the Ghidra plug-in).
- **clone again** (39,384): eight Play! trees (`local/play`, `play-playable`,
  `play-stable-src`, `play-web-perf-src`, two `play-web-src.before-release-*`,
  `three-players/play-src` and `web-src`), reference copies of original files, and the
  lobby server's sources: `git clone` at the pinned commit and the patch from this
  repository (for a tree of an earlier day, the patch of that day from the history). A
  change that existed only in such a tree and was never written into a patch would be
  lost; for the two trees checked none was made after the last build.
- **from history** (1,417): work copies of tracked files (`recomp-speed/base` and
  `root/tools`, `recomp-web/src*`, `server-audit*/src`, `server-work/src`, site folders,
  the repository's files of before the split under `work/`).
- **from the disc** (7,175), all from the owner's own disc image and the tools here:
  `decomp/` (6,693: the decompiler's output - Ghidra with the plug-in, README "Getting
  started" step 3; hours), `scripts_raw/` and `scripts/` (226: the level scripts out of
  the level files, `tools/gob.py`, `tools/scr.py`), `extracted/` (71: `tools/gob.py
  extract`), `local/sound/irx` and two Ghidra projects, `ghidra/proj` (names applied by
  script from `names.tsv` and `symbols/`; anything typed only into the project by hand
  is not in the scripts).
- **sync copies** (1,669): "name 2.ext" - copies the synchroniser made of a file that
  has its own line.

### NOT re-creatable: 19,234 files (lists by kind: `local/rehome/inventory/LOST-*.txt`)

| Kind | Files | Where, and what it is |
|---|---:|---|
| results and logs | 8,595 | tick logs, comparison results, run output: `local/rig-out` (4,221: the emulator rig's sessions `oq`, `p11` to `p17`, `soak12*`, `soak13*`, `run6-*`, sweeps), `local/mixed` (673), `recomp-out/soak` (596: the first two parts' farms `farm/nofix`, `fix26c`, calibration `cal`, single games `t`), `recomp-out/net` (519), `native-lobby` (598), `recomp-out/app-test` (394), `three-players` (386), `recomp-out/proof` (289), `recomp-web/out`, `server-audit*`, 24 Ghidra run logs |
| pictures | 3,575 | `hd-work/interface-redo` (1,065: the reworked interface art's stages `turned`, `old-2x/4x`, `new-2x/4x`, `sigonly-4x`; the pack in use is installed outside the checkout and is not affected), `recomp-out/app-test` (1,066: `s11` 491, `merge` 118, `tour2`, `shots`, `film`, `screens`, emulator reference pictures), `qa` (564: `shots`, `sheets`), `play-data/player19/textures` (485), `play-out` (157), `recomp-out/render/pic`, `recomp-speed/out/pic` |
| test browser profiles | 3,415 | `play-web-out/chrome-online-a|b`, `three-players/chrome-*-fixed`, `native-lobby/chrome-1`, `play-web-perf-out/chrome-profile`, `recomp-web/chrome-profile`: nothing to recover |
| memory cards of test runs | 1,743 | the card folders of test data directories (`recomp-out/app-test` 304, `net` 186, `proof` 155, `online` 91, `rig-out`, `native-lobby`, `three-players`, `recomp-web/out`): made by each run. **Saved characters**: `local/play-data/player1`, `player7`, `player8`, `player19` (the development copies' cards, each with a `BASLUS-20973` save). The released application's cards are in `~/Library/Application Support/Play-RTA` and are not affected; `local/recomp-out/app-data/card` holds no save |
| scripts and notes written by hand | 1,315 | test scripts of the runs above (893 `.rig` files: `rig-out` 423, `soak` 157, `native-lobby` 82, `mixed` 68, `app-test` 54, `proof` 46); **helpers**: `local/play-out/*.py` (28: `tourplan.py`, `fxlib.py`, the `hd_*` and `fx_*` tools), `local/qa/tools` (14) and `qa/REPORT.md`, `local/hd-work/*.py` (15), `local/recomp-speed/out` (`record.py`, `identity.sh`, `pictures.sh`, `appperf.py`), `local/play-web-out` and `play-web-perf-out` (30), `local/recomp-web/out/*.sh`, `recomp-out/render/rt-snap`, `proof/snap`, `proof/chain-*.sh`, soak section lists; **notes**: `AGENT_BRIEF.md`, `AGENT_BRIEF_W2.md`, `local/readme-suggestions.md`, `server/FIXES.md`, `local/friend-download/*.sh`, `local/relay-limits/*.before`; **`local/SLUS-20973_4028A55F_signin.pnach`** |
| recorded machine data | 550 | `rig-out` (429: saved machine states `.state` / `.idx` / `.zip`, network captures `.pcap`, memory images), eight recorded picture streams (`.rtavs`), `proof/real` (captured states), `recomp-out/rig` memory images |
| databases | 41 | 30 `bootables.db` (the emulator's own list, made by every start) and 11 lobby databases of test runs (`server-audit*`, `relay-limits`, `three-players/server`): test accounts only. The lobby's own database came across |

Also evicted as whole directories (their content is not in the lists; 112, see
`inventory/evicted-directories.txt`): Xcode project folders inside the Play! trees (clone
again), `local/dist/Play-RTA 2.app` and three applications under `local/dist/old-copies`
(old copies of the released application), `proof/emu/Play.app`,
`three-players/play-build/.../Play.app`, `work/native-build/champions-data-tests.dSYM`.

## Left for the owner

1. **The sign-in patch file**: wait for iCloud, or allow a copy from
   `local/dist-web/play/` to `local/`. Until then: `export RTA_SIGNIN_PATCH=...` for every
   build of the window program and every `play.sh` that is to go online.
2. **The extension's link**: `tools/godot/extension/CMakeLists.txt` needs
   `${RTA_NET2_DIR}/cardchars.cpp` beside `session.cpp` and `session_mock.cpp`.
3. **Which emulator tree is the one**: `tools/play-net/build.sh` without variables still
   points at the incomplete `local/play-playable` and fails there (at once, with a git
   error). Either `export RTA_PLAY_SOURCE=~/champions-re/local/play-playable-rehome
   RTA_PLAY_BUILD=~/champions-re/local/play-playable-rehome-build`, or put the new tree in
   the old one's place (then `tools/rehome_fetch.py` must not be given that directory
   any more: it would add the old tree's files that come back). The same for
   `server/upstream` and `server/upstream-fresh`.
4. `bin/rta_app_next` is not f3: it is today's sources (the strafe wiring of 15:23 is in)
   with `hostlook::state()` back. Moving it over `bin/rta_app` is the owner's step.

## The check script

`python3 tools/doctor_home.py`, at 19:45:

```
[ok  ] home     ~/champions-re
[ok  ] disk     15.2 GB free
[WARN] native   local/SLUS-20973_4028A55F_signin.pnach is not there: app/build.py and play.sh then leave the sign-in skip out (two words fewer, no Internet Game). A file of that name is at local/dist-web/play/SLUS-20973_4028A55F_signin.pnach and local/rel.nosync/site-pages/SLUS-20973_4028A55F_signin.pnach: export RTA_SIGNIN_PATCH=<its path>
[ok  ] native   no evicted file among 649 entries looked at
[WARN] checks   local/play-out/tourplan.py is not there: s12/tour.sh (mktour.py) fails; run the tour from the last verified route: local/rehome/tour-from-route.sh NAME PROGRAM
[ok  ] checks   no evicted file among 2958 entries looked at
[FAIL] emulator the source tree local/play-playable is incomplete (.git/HEAD, .git/index, CMakeLists.txt ...): tools/play-net/build.sh fails there; a whole tree is at local/play-playable-rehome: export RTA_PLAY_SOURCE=~/champions-re/local/play-playable-rehome RTA_PLAY_BUILD=~/champions-re/local/play-playable-rehome-build
[WARN] lobby    server/upstream is incomplete (build.sh, Source/main.cpp, Dependency/sqlite/sqlite3.c ...): sh build.sh fails there
[ok  ] lobby    whole checkout: server/upstream-fresh
[ok  ] lobby    no evicted file among 353 entries looked at
[ok  ] godot    no evicted file among 10169 entries looked at
[WARN] soak     local/recomp-out/soak/rt-frozen/rt_runtime.o: absent - the frozen runtime objects are not there: build_soak.py --rt frozen cannot link (--rt live builds with the runtime as it is now)
[ok  ] soak     no evicted file among 50 entries looked at
[WARN] proof    local/recomp-out/proof/snap/TAKEN: absent - the snapshot the proof programs were built from is incomplete: a rebuild needs a new snapshot (from the sources as they are now)
[WARN] proof    local/recomp-out/proof/snap/recomp/recomp.py: absent - the snapshot the proof programs were built from is incomplete: a rebuild needs a new snapshot (from the sources as they are now)
[WARN] proof    local/recomp-out/proof/snap/recomp/rt/iop.cpp: absent - the snapshot the proof programs were built from is incomplete: a rebuild needs a new snapshot (from the sources as they are now)
[ok  ] proof    no evicted file among 355 entries looked at
[WARN] analysis decomp/all holds 1065 of about 7,700 decompiled functions: make it again (README.md, "Getting started" step 3) before relying on it
[ok  ] analysis no evicted file among 1753 entries looked at
doctor_home: 1 would hang or fail, 8 warnings, 10 fine  -> DO NOT BUILD the failing areas
exit 1
```

With `RTA_PLAY_SOURCE` / `RTA_PLAY_BUILD` set to the new tree and `RTA_SIGNIN_PATCH` set, the
failing line and the sign-in warning are gone:

```
[WARN] checks   local/play-out/tourplan.py is not there: s12/tour.sh (mktour.py) fails; run the tour from the last verified route: local/rehome/tour-from-route.sh NAME PROGRAM
[WARN] lobby    server/upstream is incomplete (build.sh, Source/main.cpp, Dependency/sqlite/sqlite3.c ...): sh build.sh fails there
[WARN] soak     local/recomp-out/soak/rt-frozen/rt_runtime.o: absent - the frozen runtime objects are not there: build_soak.py --rt frozen cannot link (--rt live builds with the runtime as it is now)
[WARN] proof    local/recomp-out/proof/snap/TAKEN: absent - the snapshot the proof programs were built from is incomplete: a rebuild needs a new snapshot (from the sources as they are now)
[WARN] proof    local/recomp-out/proof/snap/recomp/recomp.py: absent - the snapshot the proof programs were built from is incomplete: a rebuild needs a new snapshot (from the sources as they are now)
[WARN] proof    local/recomp-out/proof/snap/recomp/rt/iop.cpp: absent - the snapshot the proof programs were built from is incomplete: a rebuild needs a new snapshot (from the sources as they are now)
[WARN] analysis decomp/all holds 1065 of about 7,700 decompiled functions: make it again (README.md, "Getting started" step 3) before relying on it
doctor_home: 0 would hang or fail, 7 warnings, 12 fine  -> able to build and test
exit 0
```
