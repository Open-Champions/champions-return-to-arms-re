# audio-save — sound, save and load, memory card, player selection, dialog, mission menu (0x210000–0x232000)

293 functions. Read from the decompile and the disassembly only; nothing here was seen on a
running game when it was written, and no statement here has been checked on one since. The
project does have a live game now — the Play! emulator, which is not a PlayStation 2 and not PCSX2 — and
what was run on it is listed in `FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`.
Its boot passes through the memory-card check and the create-save question, and save data
appears on the blank card (4a there); that exercises card code without checking any
statement made about it here. The rig has no sound output, and nothing about sound was
looked at. No test patch has been run on a live game.
Names are in `symbols/audio-save.tsv`. Unless a line says *Inferred* or
*Unknown*, a statement is *Observed* at the address given.

## Layout of the range

Boundaries come from the static-constructor table (0x3e99e8 → 0x216bb8, 0x3e99ec →
0x222f54, 0x3e99f0 → 0x22436c) and from which functions call each other.

| Range | Contents |
|---|---|
| 0x210034–0x210cd0 | point lists: level path objects (keys `name`, `barrier`, `continous`, `norotate`, `pcount`, `p`). Not sound; used by creature path following |
| 0x210cd0–0x216bf8 | sound: SPU voices, sound sequences, three streams, IOP calls. The unit with the `sound.cc` asserts |
| 0x216bf8–0x222f74 | save: player snapshot, save buffer build/load, save daemon tasks, every memory-card screen |
| 0x222f74–0x22438c | memory-card operation queue, `monsters.bal` balance table loader, credits |
| 0x22438c–0x22e714 | player selection / character creation, name entry |
| 0x22e714–0x22ec9c | a level-settings parser called by the object factory (camera limits, dust colour …) |
| 0x22ec9c–0x231050 | NPC dialog: message handler, run and draw tasks |
| 0x231050–0x232000 | mission menu (its draw task 0x232300 is past the end of the range) |

Tasks registered here (`task_add(fn, priority, name, isDraw)`):

| Task name | Function | Kind | Priority |
|---|---|---|---|
| Async Load/Save Daemon RUN | `save_daemonRun` 0x2188a8 | run | 20 |
| Async Load/Save Daemon DRAW | `save_daemonDraw` 0x2189e0 | draw | 20 |
| playerSelectionCache | `playerSel_cacheTask` 0x225428 | run | 24 |
| playerSelection | `playerSel_task` 0x225478 | draw | 9 |
| Dialog Demon Run | `dialog_runTask` 0x22ff48 | run | 110 |
| Dialog Demon Draw | `dialog_drawTask` 0x230628 | draw | 110 |
| missionmenurun | `missionMenu_run` 0x2316fc | run | 20 |
| missionmenudraw | 0x232300 | draw | 20 |

`sound_update` 0x212670 is not a task: the session loop calls it once per displayed frame.

## Save format

### The buffer

`g_saveBuffer` at 0x895580 is 0x4bc78 bytes. The memory-card file is that buffer written in
one piece: `memcard_saveScreen` queues open (mode 0x202), write (0x895580, 0x4bc78), close
(0x218afc, state 2). Loading reads the same number of bytes back and calls `save_load`
(0x219360). Slot files are named `BASLUS-20973_slot<n>` in the directory `BASLUS-20973`
(`memcard_makeSlotName` 0x21effc). `save_init` also builds the name `BASLUS-20565_config`
(at 0x88d438); where it is used was not traced.

`save_build(savepointArg, onePlayer)` 0x221914 writes everything up to the level directory;
`save_storeLevelState` adds the current level's object state.

| Offset | Size | Field | Per | Written at |
|---|---|---|---|---|
| +0x00 | char[0x14] | level name (0x41b721), or the text `gameComplete` after the end of the game | game | 0x2219e4 |
| +0x14 | char[0x50] | second part of the level name (0x41b771), empty if none | game | 0x2219f4 |
| +0x64 | u32 | play time in seconds (`g_playTimeSeconds`) | machine | 0x221a14 |
| +0x68 | u16 | size of a player record, 0x4c30 | — | 0x221a3c |
| +0x6a | u16 | number of players in the file | game | 0x221a28 |
| +0x6c | u8 | difficulty index (`g_difficultyIdx`) | game | 0x221a48 |
| +0x6d | u8 | first argument of `save_game` | game | 0x221a44 |
| +0x6e | u16 | act index (`g_currentAct`) | game | 0x221a04 |
| +0x70 | 0xc4 | camera state from `Camera_saveState` 0x203918: position (12), 4 × 4 words from 0x44f110, two u16, five words, 0x60 bytes of camera +0x100 | machine | 0x221a54 |
| +0x134 | 0x1e4 | jump-gate destinations: u32 count byte, 0x1e0 bytes from 0x8e3a50 (`jumpgate_saveDestinations`) | game | 0x221a60 |
| +0x318 | u32 | minimap mode (`g_minimapMode` 0x4f8400) | machine | after 0x221a60 |
| +0x31c | u32 | `g_numPlayers` | game | same |
| +0x320 | 4 × 0x4c3e | player blocks (below); blocks past the player count are left untouched | character | loop from 0x221abc |
| +0x13418 | n × 0x24 | quest variables: char name[0x20], s32 value; reading stops at an empty name | game | 0x221cf0–0x221d18 |
| +0x16010 | 10 × 0x18 | level directory: char name[0x14], u32 size | game | `save_storeLevelState` 0x21777c |
| +0x16118 | rest | level states, concatenated in directory order | game | `save_writeLevelState` 0x218600 |

The two variable-length sections at +0x70 and +0x134 have fixed sizes in this build (the
writers return 0xc4 and 0x1e4), but every reader recomputes the offsets by calling the
writers into a scratch buffer (`save_playerBlock` 0x2184a4), so treat the later offsets as
derived.

Player block (0x4c3e bytes):

| Offset | Size | Field |
|---|---|---|
| +0x00 | 2 | bytes +0x38 and +0x39 of the player's object (facing angle) |
| +0x02 | 12 | object position x, y, height |
| +0x0e | 0x4c30 | the player record, taken from the snapshot table `g_savedPlayers` 0x879ec0 |

If the player has no object, position and angle come from the "best" living player
(index 0x4f841c) or the first player that has one (0x221b20).

`save_snapshotPlayer(slot)` 0x216c80 copies the live record and makes it position
independent:

- each item record's first word (pointer into the static item table 0x3f7650, 0x40 bytes
  per row) becomes a row number (0x107ea4);
- the 17 equipped-item pointers at +0x43f0, the two at +0x4434/+0x4438 and the one at
  +0x443c become `bag * 1000 + index`, or −1 (`save_itemPtrToIndex` 0x216bf8).

`save_fixupPlayer(slot)` 0x216ea8 does the reverse on the live record and zeroes the object
pointer +0x43d8.

Level state: `save_storeLevelState(name)` looks the level up in the directory (adding it if
there is room; at most 10 levels and the whole buffer must stay under 0x4bc78) and has
`save_writeLevelState` write length-prefixed object and decal sections (0x14e5c8,
0x19ee10), then a fixed 0x16c8-byte explored-map section (0x16865c). The size
reserved per level comes from the act table (0x4f8e48:
per act a list of {name, u16 size}; 0x4f8e10 counts; 0x4f8e7c number of acts). Skipped
while the card state is 4 or bit 0x800 in 0x44fe08 is set.

The object-state overlay, class examples, script restart and terrain reload
boundary are detailed in `docs/save-world.md`.

### What is per character and what is per game

- Per character: the 0x4c30-byte record — name, class, level, experience, stats, points,
  gold, three bags of 64 items, equipment, quest list text, abilities, and the evil /
  decision bit bytes at +0x4c1a/+0x4c1b.
- Per game: level, act, difficulty, quest variables, jump-gate list, level states.
- Per machine but stored anyway: play time, camera, minimap mode.

In a net game the file holds only the local character: `save_packLocalPlayer` 0x2223d4
copies the local slot's block to position 0 and writes a player count of 1 before the
write; `save_unpackLocalPlayer` 0x222580 restores the buffer afterwards. Level, quest
variables and level states in that file are whatever this machine's buffer held.

### Reading back

`save_load` 0x221d60:

1. copies the 0x70-byte header to `g_saveHeaderCopy` 0x879e38;
2. restores the camera and jump-gate sections (0x203a20, 0x27dd30), minimap mode and
   `g_numPlayers`;
3. for each player: angle to 0x4f8410, position to 0x4f70d0 (used when the objects are
   created), record straight into `g_players`, `save_fixupPlayer`;
4. `vars_clearAll`, then `vars_set` for each quest-variable record;
5. sets the "loaded from save" flag 0x8e1ad6, the act, the difficulty, play time;
6. builds the pending level name 0x41b6d0 from the two header strings (`a_b` when the
   second is not empty) and marks a level change (0x41b720 = 0xfd);
7. if flag 0x4f85b4 is set, `inventory_shareQuestItems(0)`;
8. sets the autosave countdown to 99, which the daemon treats as "skip one".

The level states are not parsed here; the level loader consumes them.

Callers: `memcard_loadScreen` (draw task, front end or pause menu) and `save_reload` from
`deathTask` (party wipe in a level with a checkpoint).

### When saves are made

- `save_game(arg, quiet)` 0x218128 — callers script `saveCheckPoint`, `Savepoint_run`, and
  the daemon. It needs at least one living player, shows "CheckPoint" or the level name on
  the HUD, then `save_build(arg, 0)`. It fills the buffer only; nothing is written to the
  card.
- `save_daemonRun` (run task) counts play time and runs the autosave: `save_armAutosave`
  0x217f14 sets the countdown to 1 after a level load (its test for card state 8 is never
  true — no call of `memcard_setState` passes 8 — and the same goes for the tests of that
  value at 0x322ddc in the level-change code and in `game_loadPlayerLumps`;
  `docs/issues/arena-entry.md`), and the daemon calls
  `save_game(0, 1)` when the card state is idle, not in the front end, not PvP, no
  full-screen menu, camera mode 1 and the game not paused.
- `memcard_requestSave(slot)` 0x2175b4 (script `saveGame`, pause menu, savepoint) opens the
  card screen, which rebuilds the buffer (offline) or only packs the local player into the
  existing buffer (net game, see A1) and writes the file.
- Config: `memcard_requestConfigSave` (state 5), `memcard_requestEndGameSave` (state 6).
- `save_clearBuffer(full)` 0x21f144 zeroes the buffer; with `full` = 0 it keeps the first
  directory entry and its level state.

### Memory-card machinery

`g_memcardState` 0x88d3a0 selects the screen `save_daemonDraw` runs: 0 and 1 config load,
3 save, 4 load, 5 config save, 6 end-game save, 9 import character, 10 options; −1 idle.
`memcard_setState` 0x21f238. Card calls go through a 256-entry ring (`mc_queueOp` 0x223470:
0 open, 1 close, 3 read, 5 write, 6 file info, 8 init) pumped by `mc_pump` 0x223064;
`mc_wait` blocks. Offline, opening a card screen pushes and sets `g_paused`
(`memcard_pushPause` 0x21e850); in a net game it does not touch it.

The import screen (0x21fa2c) lists saves under both `BASLUS-20973` and `BASLUS-20565`.

## Sound

### What game code calls

| Function | Arguments | Returns |
|---|---|---|
| `sound_playOnObject` 0x214230 (180 callers) | float volume, sequence, object or 0 | handle or −1 |
| `sound_playAtPos` 0x214428 (61 callers) | float volume, sequence, position | handle or −1 |
| `sound_stop` 0x213ea0 | handle | — |
| `sound_release` 0x213438 | handle. For a sequence handle it does not let the sequence play out, as the earlier version said: it sets slot +0x3c, clears flag 4 and sets flag 1 (loop) of the track flags at slot +0x24, and writes 1.0 to +0x10 and +0x18 and 0 to +0x14 and +0x1c; `soundSeq_updateAll` then skips the end test for that slot and sets its time back to 0 whenever it passes the clip's duration, so the sequence repeats until `sound_stop`. For a voice handle it sets bit 0 of the voice's flag word (meaning not read). The six callers were not traced (`docs/formats/anim-audio.md` section 5) | — |
| `sound_setVolume` 0x214650 | float volume, sequence handle | — |
| `sound_setPlaysWhileFrozen` 0x216ad0 | sequence handle | — |
| `sound_playSample` 0x2134e8 | float pitch scale, float volume, float delay in seconds, sample, position or 0 | voice index or −1 |
| `voice_setPosition` 0x2168e8 | float range scale, voice, position | — |
| `sound_muteFor` 0x216588 | seconds | — |
| `audio_streamStatus` 0x211b20 | stream 0–2 | non-zero while busy |
| `audio_streamPosition` 0x216480 | stream | driver position, 0 if the stream is inactive |
| `audio_streamStop` 0x211ce8 | stream | — |
| `stream_playLevel` 0x215fc8 / `music_playLevel` 0x215f48 / `music_playGlobal` 0x2110e0 | (stream,) entry name, flags | — |
| `stream_queueStop` 0x211338 | stream | — |

A *sequence* is a `.anm` entry of a sound lump (usually `fx.lmp`, fetched with 0x17365c):
an animation whose events start samples. A handle with bit 15 set is `slot | generation <<
8 | 0x8000`; without it, a voice index.

### Sequence slots (`g_soundSeqs` 0x871a68, 32 × 0x4c)

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | — | animation player state (initialised by 0x170838) |
| +0x04 | u8 | active |
| +0x06 | u16 | flags; 0x80 = finished |
| +0x08 | ptr | the sequence; its byte +0x3c is a category |
| +0x28 | handle | object being followed (linked into the object's handle list) |
| +0x2c | Vec3 | position, refreshed from the object each update |
| +0x38 | u16 | generation, from a 7-bit counter (0x4f8950) |
| +0x3a | u8 | 1 = no position: plays at the camera |
| +0x3b | u8 | 1 = keeps playing while the game is frozen; initialised from `game_isFrozen()` at start |
| +0x3c | u8 | set by `sound_release`: the update skips the end-of-sequence test and restarts the sequence when its time passes the clip duration ("release requested" in the earlier version) |
| +0x40 | float | volume |
| +0x44, +0x48 | float | near 360 and far 840 attenuation distances |

Starting a sequence fails (−1) when all 32 slots are busy or when the number of active
sequences in the same category has reached the limit in the byte table 0x4f8a28 (category
0 is unlimited). `soundSeq_updateAll` 0x2147c0 steps every slot once per `sound_update`;
while a slot is being stepped its index is in `g_curSoundSeq` (0x4f8a00) and any sample it
starts is stamped with the slot and generation.

### Voices (`g_voices` 0x872880, 43 × 0x14)

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | ptr | sample (sample +0x20 base pitch, +0x24 SPU address, +0x28 loop flag) |
| +0x04 | u16 | 1 release, 2 paused by freeze, 4 in use, 8 plays while frozen, 0x10 looping |
| +0x06 | s16 | owning sequence slot or −1 |
| +0x08 | s16 | owning sequence generation |
| +0x0c | s32 | pitch |
| +0x10 | float | volume |

`voice_alloc` 0x2169f8 walks the 43 voices round robin. Table 0x4f8960 maps a voice to
(SPU core, voice bit). Register writes are batched as 8-byte commands at 0x875c00 (count
0x4f89e8, at most 512) with key-on / key-off masks per core at 0x872be0 / 0x872be8;
`sound_flushSpuCommands` 0x210cd0 sends the batch. When `g_soundFrame` 0x4f8954 has
its low three bits clear, `sound_update` reads SPU registers 0x1700 and 0x1701
(**Executed**, `docs/audio-playback.md`) and frees non-looping voices whose bit is
set. Stopping a sequence stops every
voice stamped with its slot and generation. `g_delayedSamples` holds up to 32 samples
waiting for their start frame.

Left / right volume come from `sound_panAtten` 0x213c50: distance from the camera position
0x44f038 (full volume inside 360, zero at the far distance) and the dot product with the
camera's right vector (0x44f110, 0x44f11c, 0x44f128).

### Streams (`g_streams` 0x876c10, 3 × 0x1c4)

Stream 2 is music (every music call uses it) and stream 1 is speech (dialog).
`docs/audio-playback.md` now establishes stream 0 for the intro movie soundtrack and
the first matching level `amb_` entry when idle (0x322640–0x3226c4). The
`ambient.bin` one-shots go to stream 2 when no music is active; they are a separate
path (0x2149d0). Each stream has an
8-entry queue at +0x40 (0x30 bytes per entry: file name, offset, length, three driver
parameters, flags) with the count at +0x1c0. The three parameters are, per
`docs/formats/anim-audio.md` 3.4: the sample rate (passed to the driver, which stores and
never uses it), the stereo flag, and the loop restart position. Entry flags seen: 2 stop marker, 8 hold until
released, 0x20 music, 0x40 fade-stop stream 2 from the recall, menu-timer, level-change,
HUD and front-end slices, 0x80 ambience one-shot, 0x100 kept across cutscene teardown
(`docs/audio-playback.md`). The
audio data is in `<level>.vat` (or `mouth.vat` for global entries) and the index is a
`dialog.bin` table of 0x50-byte entries (name, s16 language at +0x4a, offset at +0x40; the
length is the next entry's offset minus this one). Despite its name that file is the
directory of the stream file, not dialog; dialog text and structure are in `.dbin`
(`docs/formats/anim-audio.md` sections 3.4 and 4.2).

The IOP driver is called through `sceSifCallRpc` with client data 0x877160: function 0x50
returns a 0x40-byte status block at 0x8771c0 (four words per stream; word 3 is the
position — more exactly, per `docs/formats/anim-audio.md` 3.4, the four words are write
position, read position, current volume, and bytes played since the entry started), 0x60 stops a stream, 0x80 sets volumes, 0x40 is issued by `stream_startHeld` (*Inferred*:
starts a held entry). Calls are
made in blocking mode, so `audio_streamStatus` and `audio_streamPosition` cost a round trip
to the IOP each time.

Volume: `g_sfxVolume` 0x4f8940, `g_musicVolume` 0x4f8944, stereo flag 0x4f8948; music is
ducked while stream 1's status has bit 0x20. The target written for that case is
0x3e4cccd0 and then one more 1/60 step, so it holds at 0x3e5ddde1 (`music_updateDucking`
0x212500; `docs/audio-playback.md`).

## Player selection, dialog, mission menu

- Player selection (0x2243f8–0x22e6a4) runs from the front end: `playerSel_start` 0x2245b8
  is called by `frontend_startPlayerSelect` and by netlib 0x324288. `playerSel_task` is one
  18.7 KB draw-task function (class, sex, appearance, name entry, import). It writes
  `g_players` through `player_initNewCharacter` and the quest variable `needPlayers`. No
  level script calls `setupPlayerSel`, `startPlayerSel` or `playerSelRunning` (searched the
  120 decompiled scripts), so none of this runs inside the simulation.
- Dialog (executed contract: `docs/dialog.md`). Script `startDialog` → `dialog_start` 0x22fa50, which sends message 0 only from
  the machine that owns the script's active player. Channel id at 0x8e2e94, handler
  `dialog_onMsg` 0x22ee2c:

  | Type | Content | Effect |
  |---|---|---|
  | 0 | name length, NPC name, padding, player slot, two flags, sender's camera position (3 floats) and two camera angles (s16) | closes local menus, sets every machine's camera from the message, loads `<npc>.dbin`, runs each node's condition script until one accepts, shows that node |
  | 1 | — | confirm: finish the text reveal, scroll, or take the selected choice (runs the choice's script, then the next node or the end) |
  | 2 | s8 delta | move the choice cursor |
  | 3 | — | end: frees buffers, stops stream 1, queues a level change if the dialog named one, runs the post-action script, opens the shop if the dialog asked for it |
  | 4 | — | request the closing camera move |

  `dialog_runTask` (run task) reads the **raw** pad of the local player and sends 1, 2, 3 or
  4. It sends "confirm" only when the local speech stream is idle or speech is disabled.
- Mission menu: `missionMenu_run` is a run task that reads the lockstep pad of the player
  who opened it (0x4fe7ec) and so behaves the same on every machine.

## Per-machine state

### A1. The save buffer is compared between machines, but is built and edited per machine — Observed mechanism, Inferred consequence

The character checksum exchange (ui area: `net_sendChecksums` 0x1de46c, handler case 10 in
`hud_onMsg`) runs when `net_allPlayersState2` (0x1ec5d8) is true, every 240 simulated
frames. Each machine computes two values per player: the checksum of the live record, and
the checksum of that player's record **inside this machine's save buffer**
(`save_playerBlock(i)`, call at 0x1de4d0). It sends the pair for its own slot; every
machine compares each received pair with its own pair for that slot, and on a difference
sets `g_checksumFailed` and, unless the slot is its own, calls `net_disconnectPlayer` for
it. So the player blocks of `g_saveBuffer` are shared state as far as this check goes.
These things change them on one machine only:

- **Memory-card save in a net game.** `memcard_saveScreen` calls `save_packLocalPlayer`
  (0x218d80), which overwrites block 0 with the local player's record and sets the count
  to 1, queues the 0x4bc78-byte write, and calls `save_unpackLocalPlayer` (0x218e88) only
  when the card operations have finished. The simulation keeps running meanwhile. On a
  machine whose local slot is not 0, a checksum round inside that window compares player
  0's received value with the checksum of the local player's record: a false "bad
  checksum" for player 0 on that machine. *Unknown*: how long the write takes relative to
  the 240-frame round, and how often `net_allPlayersState2` holds (it needs flag 0x4f7134
  and a type value of 2 in every record's +0x4c1c). Answered in
  `docs/issues/sync-breakers.md` section 1: 0x4f7134 is `g_lobbyLaunch` and the type value
  2 is the lobby-stored character kind, so the exchange is on only in a lobby-launched
  game whose characters are all lobby-stored — and in exactly that case this bullet and
  the next two cannot occur: script `saveGame` returns when any player is kind 2
  (0x146c04) and `Savepoint_interactPrompt` refuses while `net_allPlayersState2()` holds
  (0x28da7c), so the save screen is never opened (B1, B3 there).
- **A failed card write** (cannot occur while the exchange is on, see above). The only call to `save_unpackLocalPlayer` is in sub-state 3 of
  the save screen. A card error (result word 0x88d3bc non-zero) sends the screen to
  sub-state 9 instead (test before the sub-state switch in 0x218afc), so the buffer stays
  packed on that machine until the next `save_build`.
- **A reload during the same window** (likewise). `save_load` (from `deathTask` → `save_reload`)
  would read a player count of 1 and the local player as player 0 on that machine only.
- **Checkpoint autosave** (this one stands). `save_daemonRun` is a run task, but its test (0x218924,
  0x218978 and the lines between) reads the memory-card state, the local full-screen-menu
  flag 0x41b4f8 and the local camera mode before calling `save_game(0, 1)` at 0x2189cc. If
  one machine is held back by one of those, it snapshots the players on a later frame than
  the others, and its blocks differ in whatever changed in between. Savepoints and script
  `saveCheckPoint` call `save_game` in lockstep and do not have this problem.

`save_game` itself changes nothing else that is shared: it fills the buffer, shows a HUD
line and calls `game_sendCharacterToLobby(−1)`, which reads `g_randSeed` without writing it.

### A2. Dialog progress depends on local audio and local text layout — Observed mechanism, Inferred consequence

- The handler for message 1 (0x22ee2c, case 1) decides between "reveal", "scroll" and
  "take the choice" from 0x8e2cb0/0x8e2cb4 (reveal), 0x8e2ccc/0x8e2cc8/0x8e2cd0 (scroll
  position, target, total height) and 0x8e2ca8/0x8e2cac. Those are advanced by
  `dialog_runTask`, and the total height comes from laying out the localised text
  (`dialog_showNode` 0x230c74). Machines running different languages, or a text that wraps
  differently, would read the same confirm message differently: one takes the choice and
  runs its script, the other scrolls.
- `dialog_runTask` returns early while the opening camera move (0x204250, calls at
  0x22ffa8 and 0x230018) has not finished, so those counters start on the frame the local
  camera arrives. Message 0 forces the camera to the sender's position and angles; whether
  the rest of the camera state is equal was not checked.
- Sending "confirm" is gated by `audio_streamStatus(1)` (0x23032c) and reads the raw local
  pad (0x2300b4, 0x23019c). That only delays a message, which is safe by itself.
- Message 3's handler spins on the engine's loader (0x172ca8) until the asynchronous load
  flag 0x4fdcd5 is set. Blocking only.
- *Unknown*: whether a dialog with choices is reachable in a net game between machines
  set to different languages; the disc carries `sel_en/fr/ge` lumps and a language index
  at 0x44fddc.

### A3. Sound return values are per machine — Observed

`sound_playOnObject` / `sound_playAtPos` / `sound_playSample` return −1 or a slot that
depends on what else is playing on this machine: free slots, the per-category limit, the
mute counter 0x877240 (0x2134f0), the frozen state, and for samples the distance from the
local camera (a non-looping sample whose two volumes come out as zero is not started; test
before 0x2138b0). Sequences end when `sound_update` sees them finish, once per displayed
frame. Any simulation code that branches on a returned handle, or on `audio_streamStatus`,
differs between machines. The 241 call sites were not audited from this side. Known users
of stream state in shared paths: cutscenes (FINDINGS D8, D18), and recall (0x18c230) and
the level-change handlers in `hud_onMsg`, which only decide whether to queue a stream stop.

`sound_playOnObject` links a handle into the object's handle list. That changes the list
contents by machine (which sounds exist), not anything the simulation reads by value.

### A4. Random choices in sound use the cosmetic seed — Observed

0x211238 (random variant among stream entries), 0x214afc and 0x2150c8 / 0x21516c (ambient
and music selection) draw from `g_cosmeticSeed`. `gxref` shows no reference to `g_randSeed`
anywhere in this range.

### A5. Save contents differ by machine — Observed

A save holds this machine's camera, minimap mode, play time and, through the record, the
menu bytes +0xed/+0xee/+0x4a58 (docs/ui.md P4). `save_load` puts them back into
`g_players`. In a net-game file only the local character is present, and its level, quest
variables and level states are those of this machine's buffer.

### A6. Debug flag from the memory card — Observed

`save_init` 0x216fcc sets `g_debugCheats` (0x4f8ee0) when the card has `debug.sht`. Its
readers are in the ui area (docs/ui.md P5).

### A7. Quest variables written outside lockstep — Observed

`save_load` (`vars_clearAll` + `vars_set`) runs from the load screen, a draw task; from
`deathTask` it runs in lockstep. `playerSel_finish` 0x22a360 and 0x229d94 write
`needPlayers` from the selection screen. `profile_setVar` 0x22274c (script `setpv`) writes
a per-profile table and requests a config save on this machine. The selection screen and
the load screen run before the simulation starts.

## Open questions

- A1 and A2 need a running pair of machines. For A1: time the card write against the
  240-frame checksum round with a save made by the player in slot 1.
- The three level-state sections (0x14e5c8, 0x19ee10, 0x16865c) belong to the object,
  engine and animation code; their contents are not described here.
- The 0x60 camera bytes and the meaning of the jump-gate table rows.
- Header byte +0x6d: `save_game`'s first argument; callers pass a savepoint-related value
  that was not traced.
- Not read beyond their strings and callers: `memcard_browser` 0x219b90 (10 KB),
  `memcard_slotList` 0x21c3a4 (8.7 KB), `memcard_importScreen` 0x21fa2c (7 KB),
  `playerSel_task` 0x225478 (18.7 KB) and its helpers 0x22a524–0x22e6a4, the credits, the
  stream service functions 0x2149d0 / 0x214eb0 (0x211548 and 0x211df8 are executed
  for queue flags and loop restart in `docs/audio-playback.md`), sample upload, the
  mission-menu helpers 0x231078–0x2314c8, and the point-list code apart from its accessors.
- Unreferenced functions (0x2128c8, 0x215bf0, 0x215c98, 0x215d28, 0x216050, 0x2161c0,
  0x216230, 0x216b58, 0x217488, 0x217ee8, 0x217fb8, 0x218418, 0x2186a8, 0x21f0dc,
  0x21f210, 0x222694, 0x222964, 0x2234fc) were not read.
