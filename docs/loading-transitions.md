# Loading screens and level transitions (SLUS-20973 v2.00)

2026-10-23. Research head `034d0c0`; this document extends the bounded results on
`t3/research-fade` (`197f52a`), `t3/research-audio` (`6b08886`),
`t3/research-levels` (`13fafa4`), and `t3/research-story-route` (`76d4447`).
**Observed** means a read of the addressed original executable. **Executed**
means `tools/ee_emu.py` ran that function or slice against synthetic state in
`tools/difftest_loading.py` or the named prior difftest. **Disc census** means
the committed read-only `tools/check_loading_art.py` probe counted names and
texture headers in the operator's v2.00 image. **Inferred** and **Unknown**
retain their usual narrower meanings.
No claim below is a captured GPU frame, decoded art, heard soundtrack, or
whole-game transition run.

## What appears while loading

**Observed:** `game_loadLevel` calls `loadscreen_start` at 0x1e5758,
after level teardown and before the level archive at 0x1e5914. The start
routine at 0x321e60 first makes three dark frames using five texture handles,
then wakes a priority-5 render thread (0x32243c–0x322498). **Executed:** the
start slice through 0x322400 asserts those three frame submissions, handle
bindings, layer 6 and tint `0x80606060` against synthetic resources. Thread
creation and display pixels remain unexecuted. That thread
`loadscreen_renderLoop` 0x32187c draws one frame at a time while the main
thread loads. **Executed:** its calls are `gfx_beginFrame`, six plain sprite draws, eight
rotated sprite draws, and `gfx_endFrame`; it increments `g_loadscreenFrame`
0x506098 once per drawn frame. The call-capture difftest sees all 14 sprite
sites for seven frame values at each seed. Texture lookup, drawing and frame
presentation were stubbed; the call arguments are the measured result.

The large art is `shot.tex` in a level-specific loading lump. The function
`loadscreen_selectWorldAlias` 0x321c9c applies these rules in order, with
case-sensitive comparisons; `tools/difftest_loading.py` executed 19 representative
names at each seed. `loadscreen_start` prepends `l`, truncates that part to
eight characters, appends `.lmp`, and falls back to `lmiss.lmp` if both file
searches fail (0x321eec–0x321f90). The start-slice difftest asserts candidate
names and the two-search fallback with synthetic CD results. The second
search repeats the same candidate; it does not establish a distinct region
fallback. Case-insensitive matching is supplied by the CD stub, not verified
as a property of the original CD service.

| Input rule | Art alias |
|---|---|
| Contains `blo` | `blood1` |
| Exactly `innovat2` | `innova2` |
| Contains `val` | `valor` |
| Contains `bas` | `bastion1` |
| Exactly `nitdung1`, `nitdung2`, `nitdung4` | `nitdun1`, `nitdun2`, `nitdun4` |
| Exactly `tormenta`, `tormentb`, `torment2`, `torment3` | `torma`, `tormb`, `torm2`, `torm3` |
| Exactly `pvpfire2` | `pvpfir2` |
| Otherwise | Original base name |

**Disc census (`tools/check_loading_art.py`):** among 120 `.GOB` level archives, 18 computed candidates lack
their own loading lump and take `LMISS.LMP`; the selected set has 91 distinct
lump names including that fallback. This is art sharing by alias or filename,
not a separate region identifier in the loader. The 97 loading lumps that
contain `shot.tex` all expose a 640×320 header. `LBLOOD1.LMP`, `LHUB.LMP`,
`LINTRO.LMP`, and `LMISS.LMP` have that same header size. These counts read
names and dimensions, not pixel content. The per-level art decision is the
candidate rule above; avoid inventing a world-to-picture map beyond it.

`LOADMISC.LMP` supplies `scrollbar.tex` (640×128), `scrollbar2.tex` and
`scrollbar3.tex` (both 640×96), plus a localized *raster* title. The language
byte 0x44fddc selects `titleloadsp.tex` for 1, `titleloadit.tex` for 2,
`titleloadfr.tex` for 3, `titleloadgr.tex` for 4, and `titleload.tex` otherwise
(0x321fb0–0x322038). Their headers are respectively 216×72, 382×90,
244×70, 160×72 and 184×78. The title and `shot.tex` are looked up at
0x322034–0x322050. The first normal-thread frame submits the 640×320 shot
at (0,100) and the default 184×78 title at (228,185), layer 6, tint
`0x80808080` in the controlled capture. The difftest asserts the selected
texture descriptors, layer and tint. These are UI API coordinates in a
640×448 design space, not validated screen pixels.

**Executed:** `scrollbar2.tex` draws twice at y=0 and `scrollbar3.tex`
twice at y=352, layer 6, tint `0x14808080`. Their horizontal positions are
`frame % 640` and `frame % 640 - 640` (0x32199c–0x321a50); the test crosses
the 639→640 wrap. Eight further `scrollbar.tex` rotated submissions form a
moving ornament: the difftest asserts that both trig calls receive
`100 × (phase + frame)` and that all eight rotated calls bind the strip
descriptor, layer 6, tint `0x80808080` and unit scale
(0x321a54–0x321c24). The rotated positions are **Observed** in the original
instructions but are not independently modeled by this difftest. The numeric
texture descriptors were synthetic; actual alpha and final geometry need a
renderer capture. No branch reads loaded byte counts, and no text/font
submission occurs in the render-thread body. Thus the moving strips are an
activity animation, **not a measured percentage**. No dynamic tip or prose
entry point was found there. The raster picture or localized title may contain
legible art text; its pixels were not decoded in this study.

## Timing and display handoff

**Observed, Executed in slices:** a pending level is acted on at the next
session-loop pass, before its normal input/tick frame (0x322cd4–0x3231d4).
The display is blanked at 0x322db8; `mainloop_loadRequestedWorld` runs and
starts the loading thread. `mainloop_startWarmup` stores 10 in
`g_warmupFrames` 0x506048 (0x322934–0x322950). Its loop runs at least those
idle-stream passes, resets the counter to 10 while terrain is busy, holds it
at 3 or more for pending equipment, and forces it to zero after 1,500
displayed frames (0x322eb0–0x322fd0). Those are local loading/display
waits, not simulation ticks or a fixed loading duration.

After player placement, deferred script calls, the warm-up, any network
load barrier and shop stock, `loadscreen_stop` sets a stop byte and waits for
the thread's dormant status before clearing `g_loadscreenActive`
(0x3224d8–0x322518). The session code then resets particles and draw
packets, blanks for six fields, and calls `gfx_setColorOffset(-128,-128,-128)`
(0x323104–0x323134). That stores colour multipliers 0,0,0 at
0x44fd8c/90/94. The `gfx_present` slice 0x19cf0c–0x19cf98 moves each channel
by four toward neutral 128 per present; the reference model matches 13
boundary values in all three channels. Starting at 0, it reaches 128 after
32 present calls. The fade is tied to presented frames, so wall-clock time
depends on display pacing. The first fully neutral multiplication uses the
value on the following present. No universal timed fade-out before the
loading screen was established; the observed boundary is a display blank.

The HUD fade word 0x4f66ac is separate. The `t3/research-fade` setter/step
probe found an image value of zero and retained a planted value across a
stubbed loader body; it did not prove an automatic reset on every level entry.
The hub mission menu has its own 16-tick fade to 127 and waits for at least
128 before writing `blood1` to the pending-level buffer (`t3/research-story-route`,
`docs/story-route.md` §2). Neither counter is the 32-present colour ramp.

## Music and ambience across the boundary

**Observed:** `mainloop_loadRequestedWorld` calls `sound_muteFor` with the
0.05-second float at 0x321134 before `game_loadLevel`. This gates direct
effect-sample starts; it is not a master stream mute (`t3/research-audio`,
`docs/audio-playback.md`). The loader copies the shared random seed to the
cosmetic seed at 0x1e59c4, then, outside either recall leg, scans the current
level stream directory in its stored order for the first name containing
case-sensitive `enttag` (0x1e59d8–0x1e5a34). It calls
`music_playLevel(name, 2)` on stream 2 for that entry. If no such entry is
found, or the directory is absent, it calls `stream_queueStop(2)` at
0x1e5a84. A recall leg skips both decisions and leaves the stream queue
as it was. `tools/difftest_loading.py` executed first-match, no-match,
empty-directory and recall cases at both seeds with a synthetic directory.
It compared API calls, not audible output or stream promotion timing.

The loader parses the new level's `ambient.bin` at 0x1e5ab4–0x1e5b3c and
applies its sound setup at 0x1e5df8. In PvP mode B it may queue a selected
global track at 0x1e5e50. It calls `sound_update` twice at
0x1e6088/0x1e6090. The loading render thread itself does not call
`sound_update`, so the normal per-displayed-frame audio service resumes in
the session frame at 0x323358. `mainloop_pollAmbientAudio` 0x322520 is also
called there: the loader normally seeds its countdown to 60 (0x322db4);
at zero it scans for a level `_env_` or `mx_theme` stream-2 entry and
re-seeds a 14,400–21,599-frame wait. Separately, every 16th
`g_drawFrame`, if stream 0 is idle, it queues the first level `amb_` entry
on stream 0. These are distinct from `ambient.bin` one-shots that use stream
2 when music is free. The branch `t3/research-audio` difftest covers the
stream flags, queue promotion, service cadence and ducking. A fade-stop
can take about 3.07 seconds at full driver volume; queuing a destination
track does not mean it is already audible. Front-end theme calls and
script/cutscene overrides can also change stream 2; preserve their owner
and flags rather than forcing a track based only on the level name.

## Systems ready before player control

The ordering below is **Observed** at the stated original sites, except
where a separate Executed check is named. It is a loader contract, not an
integrated emulation of the entire system. `t3/research-levels`
`docs/level-flow.md` §§3,5,7 gives the detailed archive and marker rules.

1. A simulation/menu writer fills `g_pendingLevel` 0x41b6d0. On the next
   pass the session loop performs any save wait and network flush, zeros
   `g_simFrame`, sets the normal ambient countdown to 60, blanks display,
   and resets the local camera when allowed (0x322cd4–0x322e30).
2. `mainloop_loadRequestedWorld` 0x320edc saves the prior level state,
   processes act changes, applies pending character selection, retains the
   qualified previous name, splits the request at its first `_`, clears it,
   copies the base into `g_levelTexName`, and briefly mutes direct effects
   (0x320f28–0x321148). Quest/player state is cleared on the documented
   act-change branch, not every level transition.
3. `game_loadLevel` 0x1e55c0 flags loading, clears old objects/lumps,
   ensures HUD/item and player resources for non-front-end worlds, then
   starts the loading thread (0x1e55f0–0x1e5758). It selects the level-table
   row, loads `<base>.gob` and its required `.TEX`, binds the first `.world`,
   then selects entry music and parses ambient groups
   (0x1e5790–0x1e5b3c). `g_gameLevelLoaded` becoming 1 during this step
   is not a grant of player control.
4. The loader applies level statistics, water pool, arena resources when
   needed, prepared world texture cells, dome/water environment, light and
   sound setup, timer reset, world bounds, and optional hub resources
   (0x1e5b54–0x1e5fec). It resets level objects and loads the level script
   and authored objects (0x1e5fec–0x1e6028), then disables unclaimed moving
   pieces, joins paths and runs any carried post action in the new script
   (0x1e6060–0x1e60b8). It clears the script-visible loading flag at
   0x1e60d4, configures level light, arms autosave/dialog box state, and
   grants 30 entry-immunity ticks to each player record
   (0x1e60e0–0x1e61f0).
5. Back in `mainloop_loadRequestedWorld`, spawn markers, terrain height and
   free-spot rules place eligible slots, then `Player` objects are built
   from living active records (0x321160–0x321414). The level reference
   difftests cover selected row, placement and floor cases; the story route
   difftest covers a hub-menu request and state snapshots, not one full
   hub-to-`blood1` game run.
6. The session starts the 10-count warm-up, runs deferred script calls once,
   repeats camera/world/cutscene setup while streaming is busy, waits for
   peers in a net game, and stocks four named stores
   (0x322e58–0x3230f4). The loading thread retains the display during this
   interval. `drawWorld` omits minimap/backdrop while it is active;
   `cut_runFrame(1)` may set up a load-time cutscene but skips time advance.
7. Only then does it stop the loading thread, reset particles, blank six
   fields, set the colour offset to black and upload `env.lmp`'s environment
   texture when present (0x323104–0x32318c). The normal session frame
   follows at 0x3231d8: input is polled, simulation/tasks run, draw/audio
   service occurs, and the 32-present colour recovery begins. The first
   control opportunity is this normal frame; an active cutscene/menu or
   other game freeze can still withhold movement.

## Ordered native port and verification list

1. Preserve the request, save/act, previous-name and player-record ownership
   in `mainloop_loadRequestedWorld`; do not consume input while its load
   branch owns the main loop.
2. Implement the alias/truncation/fallback lookup from `ref_loading.py` and
   bind `shot.tex` plus the language-specific title and three strip textures.
   Keep this loading display active until the load barrier completes. Use the
   frame-based animation, not a fabricated byte-progress bar or tips list.
   Verify CD service case matching separately; the start probe supplies
   synthetic search results. Use the read-only art census for measured headers.
3. Bring up the archive, world, sound groups, objects, scripts, lights, paths,
   player constructors and spawn placement in their observed order. Keep
   script loading-flag lifetime and the carried post action intact.
4. Implement stream-2 entry policy with recall preservation and ordered
   `enttag` search, then resume the ordinary stream-0 and stream-2 ambience
   polls. Respect queue/fade timing from `t3/research-audio`.
5. Run warm-up, deferred calls, any peer barrier and store stock before
   hiding the loading display. Match the six blank fields, colour ramp and
   first input frame. Keep the HUD/mission-menu fades as separate owners.
6. Compare start and render traces with `tools/difftest_loading.py`, disc
   headers with `tools/check_loading_art.py`, and the named prior difftests.
   Extend the rotated-position model before treating its geometry as verified.
   A renderer capture of actual art, a heard transition and a running
   hub/menu/level interaction are still needed for visual/audio parity and
   integrated-control claims.

## Verification and limits

The local private executable is pinned by SHA-256 inside the difftest.
`tools/difftest_loading.py` compares 19 aliases, six start cases, seven draw
frames, 14 fade cases and four music cases, per seed 20973 and 7 (the alias
and fade inputs are deterministic repeats). UI/GPU, IOP, CD service internals,
texture pixels and thread timing are stubbed or outside the slices. The
committed read-only disc census checks 120 archive names, selected art
candidates and `.tex` header sizes. The
rerun commands and pass/fail counts are recorded in the research worktree's
ignored `local/loading-research/` logs. `PYTHONDONTWRITEBYTECODE=1` was used
for all difftests and the full unit suite. No private input, raw disassembly,
or game asset is tracked here.

**2026-10-23 rerun:** with `ELF` set to the operator's v2.00 executable,
`DATA` to the extracted disc data directory and `ISO` to the read-only disc
image, all commands below exited zero. They ran serially in the background;
the reference-branch scripts and inputs were read-only.

| Command (`PYTHONDONTWRITEBYTECODE=1`) | Result |
|---|---|
| `python3 tools/difftest_loading.py "$ELF"` | 19 aliases, 6 start cases, 7 frames, 14 fade cases, 4 entry-music cases per seed |
| `python3 tools/check_loading_art.py --iso "$ISO"` | 120 archives, 18 fallback, 91 distinct selections, 97 shot and 8 misc headers |
| `python3 tools/difftest_fade_lifetime.py "$ELF"` from `t3/research-fade` | 2 setter, 2 step, loader retention; 9 direct setter sites scanned |
| `python3 tools/difftest_audio.py "$ELF"` from `t3/research-audio` | 23 passing property lines, including alternate FPU models |
| `python3 tools/difftest_levels.py "$ELF" --quick --seed N` from `t3/research-levels`, N=20973,7 | 12/12 properties per seed |
| `python3 tools/difftest_levels_r3.py "$ELF" --quick --seed N --disc "$DATA"` from the same branch | 6/6 properties per seed, including 18 real archive spawn cases |
| `python3 tools/difftest_levels_r4.py "$ELF" --quick --seed N --disc "$DATA"` from the same branch | 2/2 properties per seed, including 3 cold-origin archives |
| `python3 tools/difftest_story_route.py --elf "$ELF" --hub-gob HUB.GOB --blood-gob BLOOD1.GOB` from `t3/research-story-route` | 26 menu snapshots per seed; archive links checked |
| `python3 tools/difftest_mission_menu_art.py --elf "$ELF" --iso "$ISO"` from the same branch | 39 draw and 20 input cases per seed; 32 disc texture headers |
| `python3 -m unittest discover -s tools -p 'test_*.py'` | 652/652 pass |
