# Music volume `g_musicVolume` 0x4f8944

US `SLUS_209.73` v2.00. This is the prose of `tools/ref_music_volume.py`. It covers
where the player's music volume is stored, the value it starts with, every code path
that writes it, and the value the first level or boss music request sees. The level
and boss music paths, the gate, and the duck are in `docs/audio-playback.md`.

Labels: **Observed** means read at the address given. **Executed** means
`tools/difftest_music_volume.py` ran the original in `tools/ee_emu.py`, and the model
agreed on the calls and their arguments, on every word stored outside the stack, and
on the result. It ran with seeds 20973 and 7, 300 random cases per property where a
count is not given, and found 0 mismatches. The property name is in brackets.
**Inferred** and **Unknown** have their usual meaning. Nothing here was run on a
console, in PCSX2 or on the live rig.

## Answer

| Boot | Value at the first level or boss music request |
|---|---|
| No memory card, or no options file | 0.5 (0x3f000000) |
| An options file | the float at file +0x08, copied bit for bit, with no clamp |
| Either, after the player moves the music slider in the front end | the slider value (steps of 1/120, clamped to 0..1) |

**Executed [chain]** for the first two rows. The chain is: the ELF image, then
`config_setDefaults(-1)`, then the boot copy of the options file if there is one, then
`game_addCoreTasks`, then `music_playLevel`. It ran with no file and with file values
0, the gate pattern, one below the gate pattern, 1.0, 1.5, −1.0, 0.25, 0.5, and 11 random
values. The rows assume the boot order below, which is **Observed** from addresses and
not run as one program. With no card, the file copy is not reached. That is
**Inferred**: the copy is in the step after a successful read, and the no-card branches
of the browser were not traced.

A file value below the gate pattern 0x3d4ccccc means the game never queues level or boss
music. That includes 0 and any negative value. The pattern 0x3d4ccccc itself does queue,
**Executed [gate]**. This settles the open "equal pattern" case in
`docs/audio-playback.md`. A file value above 1 stays above 1 until the slider is
touched. One press then clamps it to 1.0.

The static 1.0 is real but never used. The ELF word at 0x4f8944 is 0x3f800000.
`save_init` replaces it with 0.5 before any session starts, so no music request
can read 1.0 from the image. A native client should start from 0.5 or from the options
file, not from 1.0.

## Storage

- 0x4f8944 is in `.data` (0x3e9c00–0x51e108), not `.bss`. Its ELF image word is
  0x3f800000 (1.0). **Observed, Executed [static]**.
- The options image `g_savedConfig` 0x4f8f38 is in `.data` too. Its music word +0x08
  (0x4f8f40) is 0 in the ELF image. **Observed, Executed [static]**.
- All code accesses 0x4f8944 as `lui 0x50` with offset −0x76bc. gp is 0x56c170, too far
  for a gp-relative access, and the text has no gp-relative loads or stores.
  **Observed.**
- Two data words point at 0x4f8944: 0x44f230 and 0x4f6ea0. Each is the value pointer of
  the `menu_music` entry, at index 1 and type 4 (float slider), in one of two option
  lists: the pause options list 0x44f218 (14 entries) and the front-end list 0x4f6e88
  (13 entries). **Observed, Executed [slider]**.

## Writers of 0x4f8944

Every store to 0x4f8944 found in the code, and both pointer words. **Observed**.

| Writer | Store | What | When |
|---|---|---|---|
| `config_setDefaults` 0x1e6238 | 0x1e627c | 0.5, only when `which` = −1 | at boot, from `save_init` 0x21700c |
| `game_addCoreTasks` 0x1e6cc0 | 0x1e6e2c | image +0x08, verbatim | at the start of every `mainloop_runSession` (0x322a20) |
| `memcard_optionsScreen` 0x222b40, state 2 | 0x222ccc | load buffer 0x4f9240 +0x08, also into image +0x08 | when the player loads options from the pause menu or front end |
| `menuList_handleInput` 0x1a01d0, type 4 | 0x1a0550/0x1a0554, 0x1a05a8/0x1a05ac | value ± 1/120, clamped | each frame a direction is held on the music entry |
| `config_restore` 0x1e6528 | 0x1e65d8 | backup 0x86af70 +0x08 | never: it has no caller and no data word holds its address |

`config_setDefaults(which)` **Executed [defaults]**. With `which` = −1 it stores the 17
scalar defaults in their globals and in the image, clears image +0x00, and calls
`music_applyVolume`. That call comes after 0x4f8944 and image +0x08 are both 0.5. It
then writes the button rows. With `which` from 0 to 3 it writes only that row. Any other
value writes nothing. Neither of these touches 0x4f8944. There are two callers. One is
`save_init` with −1. The other is `frontend_controlConfigRun` 0x1e2990 with the word at
0x4f701c, the controller slot that indexes the pad array (**Inferred**: it is used as a
pad index at 0x1e293c). That call resets one button row and not the music.

`game_addCoreTasks` **Executed [coretasks]**. It copies the 17 image scalars to their
globals with no clamp: 0, negative values, 1.5 and 0x7fffffff all went through
unchanged. It also copies the four button rows to the per-slot arrays 0x41b980–0x41ba30.
0x4f8940 and 0x4f8944 are stored before `music_applyVolume`, and the rest after it. The
call order is two task adds, then `music_applyVolume`, then `lump_load("globsnd.lmp")`,
`help_addTask`, `game_resetState`, 0x171060, 0x18b930 and `save_setAct(-1)`. Its only
caller is `mainloop_runSession` at 0x322a20, which is straight-line code from 0x322a08.
The session loop comes after it. **Observed.**

`memcard_optionsScreen` **Executed [optionsload]**, all states.

- State 0 shows `options_warn`. Choice 1 calls `memcard_setState(-1, 0)`, and choice 2
  moves to state 1.
- State 1 calls `memcard_browser(0, "options_config", 0)`. A result of −1 cancels, and 1
  moves to state 2.
- State 2 copies the 17 scalars from 0x4f9240 into the globals and the image. Music and
  effects go first, then `music_applyVolume`, then the rest. The screen then goes to
  state 3 and calls `memcard_setState(-1, 0)`. The button rows and image +0x00 are not
  copied.
- State 3 calls `memcard_setState(-1, 0)`.
- Any other state does nothing.

It is card state 10 and is reached only through `memcard_requestOptions` 0x222b10. Its
callers are the pause menu task at 0x18d83c and `frontend_run` at 0x1e11c0. Both test
bit 0x10 of a pad word at +0xc first, so the call follows a button press. The pause
menu also requires its current list to be the options list. So it is a player action,
not part of boot. **Observed.** The front end's screen condition was not traced.

`menuList_handleInput` **Executed [slider]**. The tests used both lists, the cursor on
the music entry, and no edge bits. The per-slot timer at 0x4d8a10 gains 0x3e4fdef8 and
is capped at 1.0. Below 1.0 the call does nothing else, so the first four calls after
the cursor arrives are idle. After that, every call does the following. If a held bit
of 0x408000 is set, the value drops by 0x3c088888 (1/120) and becomes 0 if the result is
below 0. If a held bit of 0x802000 is set, the value rises by the same step and becomes
1.0 if the result is above 1.0. Both can happen in one call. The handler calls nothing
for a type-4 entry.

Holding down from 0.5 reaches 0 after 60 steps. The value first drops below the gate at
step 54 (0x3d4ccc08). Holding up from 0.5 reaches 1.0 after 61 steps. **Executed [slider]**,
as whole walks.

The caller, the pause menu task at 0x18d714–0x18d7e8 or `frontend_run` at
0x1e100c–0x1e10c8, compares the value before and after the handler. If it changed and
stream 2 is not playing, the caller previews the main music stream (pause) or
the main theme stream (front end) through `music_playGlobal(…, 0x41)`. The preview is
subject to the same gate. On every path through that block, the caller then
calls `music_applyVolume`. **Observed.**

## Writers of image +0x08 (0x4f8f40)

- `config_setDefaults(-1)`, **Executed [defaults]**.
- `memcard_optionsScreen` state 2, **Executed [optionsload]**.
- `config_commitOptions` 0x1e6650 at store 0x1e6a24, **Executed [commit]**.
  (`force`, `queryOnly`, `noCardSave`) counts the options that differ. Unless
  `queryOnly` is set, a non-zero count copies the live values, music included, into the
  image. `memcard_requestConfigSave` 0x217bdc is then called when the count or `force`
  is non-zero and `noCardSave` is 0. The executed state had every other option equal,
  and the count was 1 exactly when the music differed. The callers are the pause menu
  (0x18d180, 0x18d2c8, 0x18d2e0), 0x18e2f8 and `frontend_run`.
  Because of this commit, a slider change survives the next `game_addCoreTasks`.
  **Inferred.**
- `memcard_browser` 0x219b90, step 29 at 0x21b9d8, **Executed [bootload]**, 60 cases.
  Step 28 (0x21b96c) reads 0x2f8 bytes of the options file into 0x4f9240. Step 29 runs
  after a good read. When the mode argument (kept in s5) is non-zero, it copies all
  0x2f8 bytes over `g_savedConfig`. Then, unless the word at 0x88d3cc is −1, it ORs that
  word and 4 into image +0x00. It never writes 0x4f8944. `memcard_configScreen0`
  0x219a88, card state 0 at boot, passes mode 1. `memcard_configScreen1` and the
  options screen pass mode 0.

Other references to `g_savedConfig` do not write +0x08: net launch, script end-config
flags, controller rows, difficulty bits, and card writes of the image. **Observed**,
each reference read.

## Boot order

**Observed** from `main` 0x323dcc. `docs/mainloop.md` section 8 has the full sequence.

1. `save_init` 0x216fcc, called at 0x323e88, calls `config_setDefaults(-1)` at 0x21700c
   before any branch. 0x4f8944 and image +0x08 become 0.5. At that point
   `music_applyVolume` would set the channel only if stream 2 were playing.
2. `mainloop_runBootCardCheck` 0x32396c is called at 0x323fec with no branch around it.
   It requests card state 0 and runs a modal loop, which runs no tasks, until
   `g_sessionExitCode` is non-zero. `memcard_configScreen0` sets that code when the
   browser finishes. With a file, step 29 copies the file over the image. 0x4f8944
   still holds 0.5.
3. Splash screens, then the main loop calls `mainloop_runSession` 0x322998.
   `game_addCoreTasks` copies image +0x08 into 0x4f8944.
4. The front end and the levels run inside that session. A level change does not leave
   it (`docs/mainloop.md` section 8). Level music (`mainloop_pollAmbientAudio` and
   script `startMusic`) and boss music (`creature_startBossMusic`) are requested only
   there. Each session that starts after a return to the front end copies the image
   value again.

No level or boss music request can come before step 3. **Inferred**: those requests
belong to the session's tasks and scripts, and the modal loops before it run no tasks.

## `music_applyVolume` 0x215e78

**Executed [apply].** It calls `audio_streamStatus(2)`. If bit 0x20 of the result is
set, it calls `audio_setChannelVolume((duck × volume) × 0.78125, 2)`, where the duck is
0x4f894c and the two products are truncated in that order. It stores nothing and never
reads the image. Its callers are `config_setDefaults`, `game_addCoreTasks`,
`memcard_optionsScreen`, the pause menu, and `frontend_run`.

The gate is **Executed [gate]** for `music_playLevel` 0x215f48 and `music_playGlobal`
0x2110e0. `c.olt.s volume, 0x3d4ccccc` skips the queue. When the gate passes,
`music_playLevel` calls `audio_setChannelVolume(…, 2)` and then the stream queue
0x215fc8(2, name, flags | 0x22). `music_playLevelIndex` 0x215ec8 has the same test,
**Observed**.

## Side finding

The research-saves branch's `docs/save-format.md` options table lists image +0xc4..+0xd4
as an unknown pairing. All three of `game_addCoreTasks`, `memcard_optionsScreen` and
`config_backup` 0x1e6428 pair them as follows. **Observed; Executed [coretasks]
[optionsload].**

| Image | Global |
|---|---|
| +0xc4 | 0x50391c |
| +0xc8 | 0x505af0 |
| +0xcc | 0x505af4 |
| +0xd0 | 0x505b00 |
| +0xd4 | 0x505afc |

## Coverage

Instructions executed, out of the range given by `tools/dis.py`'s heuristic bounds
(trailing padding included). The counts are the same for both seeds.

| Function | Executed |
|---|---|
| `config_setDefaults` | 122 of 124 |
| `music_applyVolume` | 19 of 20 |
| `music_playLevel` | 31 of 32 |
| `music_playGlobal`, the gate and first call | 22 of 22 |
| `game_addCoreTasks` | 165 of 166 |
| `memcard_optionsScreen` | 180 of 180 |
| `memcard_browser` step 29 | 67 of 100 (the unaligned-copy path and the error branches were not run) |
| `menuList_handleInput` | 162 of 359 (cursor movement and the type 1, 2 and 3 entries are outside this contract) |
| `config_commitOptions` | 322 of 326 |

## Open

- What the card browser does with no card, an unformatted card, or no options file.
  The claim that the image keeps its defaults in those cases is **Inferred** from the
  copy sitting after a good read. Running `memcard_configScreen0` through the browser's
  error steps would settle it.
- Whether the retail options file can hold a music value outside 0..1. Nothing on the
  load path clamps it. The slider cannot produce one, but a hand-edited or corrupt file
  can.
- Whether any music request can reach the gate before the first `game_addCoreTasks`.
  None is known, and it was not checked by running a full boot.
- On a console or PCSX2: the last bit of the slider walk, since the adder model is
  `ps2`, and whether the boot order holds. Neither has been tried.
