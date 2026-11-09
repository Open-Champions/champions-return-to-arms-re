# Audio in ordinary play (SLUS-20973 v2.00)

What the shared C++/Godot client needs to make the original's sounds in normal play:
which music plays where and when it changes, which effect or voice each game event asks
for, what the volume options do, and why one mixer per process is the right shape. It
builds on [audio-playback.md](audio-playback.md) (queue flags, boss override, level poll,
duck, cadence) and [formats/audio.md](formats/audio.md); it does not repeat them.

Labels. **Executed** means `tools/difftest_audio_session.py` ran the original function,
or the named address slice of a larger one, in `tools/ee_emu.py`, and
`tools/ref_audio_session.py` agreed on every recorded call, every stored word and the
cosmetic seed. It ran with seeds 20973 and 7 and 300 random cases per property (600 for
foley and hits; the voice property runs every model × kind twice plus 600 random calls),
with 0 mismatches. The property name is in brackets. Each property's stubs are named in
its docstring: disc, IOP, directory and object-system callees are replaced by recorders
that return the case's value. **Observed** means read at the address given and not run.
**Disc** means counted from the NTSC level directories of the private disc on the mini
(read only; names and counts only). **Inferred** and **Unknown** have their usual
meaning. Nothing here was heard, run on a console, or run in PCSX2.

## 1. Client list

In the order a client would build it. Each line points to the section with the evidence.

1. **One mixer, created once.** `sound_init` 0x212f08 has one caller, `engine_init`
   0x19d73c. Keep `g_soundFrame`, `g_drawFrame`, the duck words, the channel volumes
   and the poll countdown for the whole process (section 7).
2. **Per frame:** `sound_update` calls `music_updateDucking` first, then pause/resume,
   the 4-frame queue service, sequences, ambient one-shots, the SPU flush, the 8-frame
   end-flag reads, the stream-0 volume, and the 16-frame volume send [update order]
   (section 6).
3. **Every level load:** stop every sequence and queue a stop on all three streams
   (`sound_unloadAbove`, Observed). Copy `g_randSeed` into `g_cosmeticSeed`. Unless the
   load is a recall, set the music countdown to 60 frames, so the level track is
   queued about one second into the level [level entry] [session countdown] (section 2).
4. **Level track:** the first directory name containing `_env_` or `mx_theme`, queued
   on stream 2 as 0x122: it fades the old entry, carries the music bit and the
   cutscene-keep bit, and **does not loop**. It is queued again every 14,400–21,599
   frames (section 2, and audio-playback.md 197–215). The per-level names are in
   section 2.2.
5. **Level ambience:** the first `amb_` name, on stream 0 with flags 3 (loop + fade),
   requeued whenever stream 0 is idle on a 16th drawn frame (audio-playback.md 197–215).
   Its volume is 0.5859375 × min(2 × music volume, 1) [music and stream-0 volume].
6. **PvP mode B levels:** one of the 11 boss tracks, chosen with the cosmetic seed,
   looped (flags 1 → 0x23) [pvp music]. Boss fights: audio-playback.md 178–254.
7. **Menus:** title `mx_maintheme_l.vag`; credits `mx_endcredits_ext_l.vag` (flags 3);
   moving the music slider plays `mx_main_l.vag` (pause) or `mx_maintheme_l.vag`
   (front end) with 0x41 when no music is playing, and fades it after 240 or 120 idle
   frames [pause preview] [front preview] (section 3).
8. **Voices:** `player_voice(slot, kind)` → stream 1, flags 0x24, name
   `<prefix><nnn>` picked at random among the `MOUTH.VAT` names with that prefix.
   `playGotItemSound` is kind 9 [player voice] (section 4.1).
9. **Footsteps:** armour foley from the boot item, or water steps; no plain ground step
   [foley] (section 4.2).
10. **Hits:** `hit_<material>_<type>_<weight>.anm` from `fx.lmp` [hit name] (section 4.3).
11. **Options:** effects and music default to 0.5, the stereo word to 1
    [option defaults]. Channel volumes are clamped to 0..1 and sent as `int(v × 256)`
    [channel volumes] (section 5).

## 2. Music in levels

### 2.1 Load and level-entry rules

**Observed** (`docs/issues/sync-breakers.md` 168; `sound_unloadAbove` 0x215418): every
`game_clearLevel` reaches `sound_unloadAbove` through `lump_unloadUpToLevel` 0x1713e8.
After its sequence loop (0x215538–0x21556c, `sound_stop` on every active slot) the body
from 0x215570 has no branch except a three-pass loop. It sends two driver RPCs, one of
them 0x70 (volume target), then calls `stream_queueStop` for streams 0, 1 and 2
(0x215684–0x215698). It could not be run as a whole function here (it walks object
lists), so this is Observed, not Executed. **Inferred:** every level change, including a
recall, fades all three streams out.

**Executed [level entry]** (`game_loadLevel` 0x1e59a4–0x1e5a90;
`ref_audio_session.level_entry`, lines 36–57):

- First, unconditionally, `g_cosmeticSeed` 0x404460 = `g_randSeed` 0x404464
  (0x1e59b4–0x1e59c4). From here on, every cosmetic draw in audio (voice numbers,
  foley index, the poll countdown, animation sound jitter) starts from the shared seed
  of the load.
- If byte 0x41b51c or 0x41b51e is set, nothing else happens. Their writer is
  `player_recallTick` 0x1b5fa0 (0x1b6260 sets 0x41b51e, 0x1b628c sets 0x41b51c), and
  `mainloop_loadRequestedWorld` clears them after `game_loadLevel` (0x3211c4, 0x3214c0;
  `docs/mainloop.md` 389). **Inferred:** they mark the two directions of a recall.
- Otherwise the level directory (`stream_levelDirectory` 0x216860) is walked in order
  until an empty name. The first name containing `enttag` is queued with
  `music_playLevel(name, 2)`, then `game_set4f83b8` 0x1ec0e0 receives
  `(next cosmetic draw >> 16) % 1200 + 1800`. With no such name, or no directory,
  `stream_queueStop(2)` is queued instead.
- **Disc:** none of the 90 level directories contains `enttag` (section 2.2), so in the
  shipped game every non-recall load queues the stop. What 0x4f83b8 does is not traced
  here (**Unknown**).

**Executed [session countdown]** (`mainloop_runSession` 0x322d94–0x322db8;
`ref_audio_session.session_countdown`, lines 60–64): unless one of the two recall bytes
is set, `g_ambientCountdown` 0x50608c = 60 before the load. The poll
(`mainloop_pollAmbientAudio` 0x322520, once per displayed frame) decrements it, and at 0
it queues the level track (audio-playback.md 197–215). **Inferred:** on an ordinary load
the level track is queued on the 60th poll, about one second at 60 Hz, and then waits
for the fade of whatever stream 2 was playing (audio-playback.md 153–161). After a
recall, the countdown keeps the value it had in the previous level. The level track then
returns only when that countdown runs out: up to 360 seconds, although the load has
already faded the old music.

**Observed** loop rule: the poll queues 0x102 and `music_playLevel` adds 0x22, giving
0x122 (audio-playback.md 136–140, 149). Bit 1 (loop) is clear, so the level track plays once.
It is queued again only when the countdown, reset to 14,400–21,599 frames, runs out.
**Inferred:** silence between plays is normal and must not be filled by looping.

**Executed [pvp music]** (`game_loadLevel` 0x1e5e00–0x1e5e58;
`ref_audio_session.pvp_music`, lines 77–82): when `g_pvpModeB` 0x4f7120 is nonzero, the
load draws the cosmetic seed once and calls `music_playGlobal(table[(draw >> 16) % 11],
1)`. The table is at 0x4f8320; it holds the 11 boss names of audio-playback.md 178–193
in this order: avataroffear, broon, cazicthule, dozekar, droon, ironguardian,
matanielmarr, proon, ralloszek, vanerhost, whitetormentor. It is null-terminated
[image]. The flags become 0x23, so the track loops. All 11 were drawn in each run.
**Inferred:** the level poll still runs in these levels. It does not replace the track,
because it tests `stream_queuedFlags(2)` 0x216310, which ORs the active entry's flags
(when +0x14 is set) with every queued entry's, and 0x23 carries 0x20 (0x3225a4–0x3225b0;
audio-playback.md 201–203).

### 2.2 Level track and ambience per level (Disc)

From the NTSC `dialog.bin` directory of each `g_levelTable` row (90 rows, US v2.00):
the first `_env_`/`mx_theme` name (what the poll queues) and the first `amb_` name.
88 levels have exactly one `mx_` row and two have none. Each chosen name occurs once in
its table, so the last-match lookup of `stream_findLevelEntry` 0x210e60 finds that same
row. There are 54 distinct level tracks and 20 distinct ambience entries.

| Level track (`mx_env_…_l.vag`) | Levels |
|---|---|
| `hub`, `hub2`, `blood1`, `strife`, `drunarm`, `drundar`, `drunare` | the level of the same name; `blood1` also `blomedal`, `compblo`, `stobonus`; `drundar` also `boar1` |
| `innovat1`, `inmine1`, `inmine2` | same name; `innovat1` also `innmedal`, `pvpinn`, `innpit` |
| `islc1`, `islc2`, `islsm1`, `islsm2a`, `islsm2b`, `islsm3a`, `islsm3b`, `islgnome`, `islgoth` | same name |
| `wat1`, `watg2a`, `watg2b`, `watg2c`, `wate2a`, `wate2b`, `wate2c` | same name; `wate2c` also `watmedal`, `compwat`, `watbonus` |
| `tormenta`, `tormentb`, `torment2`, `torment3` | same name; `torment3` also `tormedal`, `pvptor`, `torbonus` |
| `grimror` | `swamp1`, `swamp2`, `dis2`, `dismedal`, `compdis`, `disbonus`, `faybonus` |
| `arachna_caves` | `arachna1` |
| `valor`, `valor1`, `honor` | `valor`, `valmedal`, `compval`, `stomedal` → `valor`; `valor2` → `valor1`; `honor`, `honor2` → `honor` |
| `fire1` … `fire5` | same name; `fire1` also `firmedal`, `pvpfire`, `firbonus` |
| `storm1b`, `storm1c`, `storm2` … `storm5` | same name; `storm1a` → `storm2` |
| `fay1`, `fay2`, `fay3`, `nit1` | same name |
| `thunder1` | `nit2`, `nitmedal`, `pvpnit`, `nitbon2`, `pvpbas` |
| `thunder2` | `nitdung1`, `nitdung2`, `nitdung4`, `nitbonus` |
| `thunder3`, `thunder4` | `bossgood`, `bossevil` |
| none | `storm1` (24 rows, no `mx_` row), `innovat2` (empty directory) |

The ambience entry is one of 20 `amb_…_l.vag` names, each shared by several levels (for
example, `hub` uses `amb_act5_airhub_l.vag`). `fay2` and `innovat2` have no `amb_` row;
`storm1` has one (`amb_act3_desert_l.vag`) but no level track. A client should read both names from the directory
at load with the poll's substring rule, not hard-code this table. The table is here so a
playthrough can be checked against it.

### 2.3 Other level-time music

All **Observed** call sites of the three music entry points (`jal` scan of the text):

| Entry point | Callers |
|---|---|
| `music_playGlobal` 0x2110e0 | boss 0x1192dc; pause slider 0x18d7a0; front end 0x1e09b0, 0x1e09c4, 0x1e10b8, 0x1e114c, 0x1e16f4; `frontend_start` 0x1e20fc; PvP load 0x1e5e50 |
| `music_playLevel` 0x215f48 | script `startMusic` 0x146b8c; load `enttag` 0x1e5a34; level poll 0x322634 |
| `music_playLevelIndex` 0x215ec8 | `cut_execKey` 0x196c88; `cut_setup` 0x19ae98 |

There is no combat music. Apart from the boss override (audio-playback.md 163–254), no
damage, aggro or creature-state code queues music. Script `startMusic`, `startAudio` and
`endMusic` are used by no shipped script (`docs/script.md` 812–814, use counts 0 / 0).

## 3. Menus

**Observed** (`frontend_run` 0x1e08f0): the title queues `mx_maintheme_l.vag` with flags
1 or 5 (audio-playback.md 172–175). Choosing `menu_credits` (0x1e16b4–0x1e16f8) runs
`stream_clearQueue(2)` 0x216130, then `music_playGlobal("mx_endcredits_ext_l.vag", 3)`.
`frontend_start` 0x1e20d8–0x1e2100 does the same when byte 0x86ad58 is set, then clears
the byte. Its only references are the read and clear here and at 0x1e1154–0x1e117c, so
its writer is **Unknown**. Leaving front-end screen 15 when 0x223d3c returns 0
(0x1e1118–0x1e1150) queues `stream_queueStop(2)`, then `music_playGlobal(
"mx_maintheme_l.vag", 1)`.

**Executed [pause preview]** (`pauseMenu_task` 0x18d728–0x18d7e8) and **[front preview]**
(`frontend_run` 0x1e1048–0x1e1114, only while the current list is the front-end options
list 0x4f6e88, 0x1e1038–0x1e1040). `ref_audio_session.slider_preview`, lines 95–122:

- If the edited value changed (pause: the selected entry; front end: `g_sfxVolume`), and
  the low bits of `g_drawFrame` are 0 (pause: 3 bits, front end: 2 bits), a tick sound
  plays: `sound_playOnObject(1.0, lump_get(…), 0)`. The names are `menu_shop_tab.anm`
  in the pause menu and `game_butn_tab.anm` in the front end (Observed strings at
  0x18d754 and 0x1e106c).
- If `g_musicVolume` changed (an R5900 float compare, so +0 equals −0), the screen asks
  for stream 2's status. When it lacks 0x20 it calls `music_playGlobal(name, 0x41)`:
  `mx_main_l.vag` in the pause menu, `mx_maintheme_l.vag` in the front end. Either way
  the idle timer is reset to 0. The timer is 0x44fa7c in the pause menu and 0x4f7030 in
  the front end.
- The front end then calls `music_applyVolume` and `audio_sendVolumes`. The pause menu
  calls them right after the slice, at 0x18d7e8 and 0x18d7f0.
- The timer is incremented. When the signed result reaches 241 (pause) or 121 (front
  end), the screen asks for the status again, every frame, and calls `stream_queueStop(2)`
  when it has 0x40. Only the preview carries 0x40, so this stops the preview and no other
  music (audio-playback.md 133–140).

## 4. Effects

### 4.1 Script natives and voices

The script side is in `docs/script.md` 810–814 and 718. `sound` plays a raw sample at the
camera. `soundSequence` plays a sequence at the camera that keeps going while the game is
frozen; 26 shipped scripts use it 27 times. `playGotItemSound` calls `player_voice(slot,
9)` with the slot quirk N8.

**Executed [player voice]** (`player_voice` 0x1b7ba8, whole function, 12 models × kinds
−2..23; `ref_audio_session.player_voice`, lines 138–169). In this order:

1. `net_isLocalSlot(slot)` 0x13e150 is called. A remote slot returns.
2. A cutscene byte 0x44fcd0 that is nonzero returns.
3. When byte 0x402791 is 0, a nonzero 0x41b69d returns. (0x41b69d is the local-menu byte
   of `docs/script.md` 1128; **Inferred:** 0x402791 is the network byte, so offline a menu
   silences voices.)
4. Kinds 0–9 read `stream_activeFlags(1)` 0x216388. Bit 0x20 (a voice playing) returns.
5. Record +0xac (hit points) ≤ 0 returns, by the R5900 compare: −0 counts as 0, and every
   other pattern, including NaN patterns, compares by sign and magnitude.
6. Kinds outside 0–9 return. Otherwise the record model +0x54 selects the line:

| Kind | Callers (Observed `jal` sites) | Models 0–9 (`bwm bwf erm erf ecm ecf ewm ewf esm esf`) | Models 10, 11 (`vm`, `im`) |
|---|---|---|---|
| 0 | no constant site (see below) | 001 | 001–002 |
| 1 | `Player_run` 0x1a5450 | 011–013 | 011–012 |
| 2 | idle voice 0x322bf4 | none (see below) | none |
| 3 | `Player_processDamage` 0x1b357c | 014 | none |
| 4 | `Player_run` 0x1a5e00, 0x1a76b8; `Player_spendMana` 0x1be8dc | 018 | 021–022 |
| 5 | `Player_run` 0x1a7630, 0x1a7dec | 019 | 031–032 |
| 6 | `Player_run` 0x1a6d30, 0x1a6ddc, 0x1a77a0 | none | none |
| 7 | `DoorSwing_interact` 0x28ab68, `DoorSecret_interact` 0x28b2c4 | 043 | none |
| 8 | no constant site | 041–042 | none |
| 9 | `playGotItemSound` 0x146558 | 035–036 | 041–042 |
| 10–17 | `damage_apply` 0x1e8e34 and `SpellCyclone_ctor` 0x2d19dc (10); `Player_run` 0x1a6844 (10), 0x1a7694 (11), 0x1a605c (13), 0x1aaa84 (17); `Player_processDamage` 0x1b2efc, 0x1b382c and `SpellCharge_run` 0x2c9014 (12) | none | none |

Four sites pass the kind in a register: `itemprop_tryPickup` 0x154ffc, `itemList_input`
0x1ce230, `SpellSummonAxe_ctor` 0x2fed60 and `SpellSummonArrows_ctor` 0x2ffa58. A range
draws the cosmetic seed once: number = first + `(draw >> 16) % count`. A single
number draws nothing. The call is `stream_playGlobalRandom(1, "<prefix><nnn>", 0x24)`
0x2160c0, which picks at random among the `MOUTH.VAT` names that start with that string
(`stream_queueRandomByPrefix` 0x211190, `docs/formats/audio.md`). Flags 0x24 wait for
the current voice (4) and carry 0x20, so the voice ducks music (audio-playback.md
217–237). Kind 2 compares the string at 0x41b721 with 34 fixed names, by `strcmp` or
`strstr`. Those names are not Return to Arms levels, and with each of the 90
`g_levelTable` names in that string no call is made, so in this game the idle voice is
silent. **Inferred:** that list was carried over from another game. **Unknown:** what
0x41b721 holds during play.

### 4.2 Footsteps

**Executed [foley]** (`sound_playFoley` 0x1e7c40, whole function;
`ref_audio_session.foley`, lines 179–193). `Player_footstep` 0x1beec8 passes the player's
position, the in-water bit (bit 61 of +0xa8) and the word +0x08 of the boot item (record
+0x4400, else +0x4418). Without an item it passes 0x80000 (**Observed** 0x1beef4–0x1bef44).

- In water: `fs_water1.anm` or `fs_water2.anm`, from `(draw >> 16) & 1`.
- Otherwise, the first armour bit set, in this order: 0x400000 `foly_plate1–5`,
  0x200000 `foly_chainmail1–5`, 0x100000 `foly_leather1–5`, 0x80000 `foly_cloth1–4`. The
  index is `(draw >> 16) % 5` for the first three and `& 3` for cloth, plus 1.
- With none of 0x780000 set: no sound, and no draw.
- The call is `sound_playAtPos(1.0, lump_get("fx.lmp", name), copy of the position)`.
  There are 21 names; both runs reached all of them.

`game_animEventFoley` 0x1ebd00, the animation event −2 callback, passes flags 0
(**Observed** 0x1ebd24–0x1ebd38), so an animation foley event on land makes no sound.
**Inferred:** player steps on dry ground are armour rustle only; there is no surface step
table in this path.

### 4.3 Hits

**Executed [hit name]** (`sound_playHit` 0x1e7e40, whole function;
`ref_audio_session.hit_name`, lines 208–245). `damage_apply` calls it at 0x1ea7b8 with
`landed` = 1 unless flag 0x4000 is set, and at 0x1eac24 with `landed` = 0 unless flag
0x8000 is set (**Observed**). Its arguments are (amount, victim-is-player, victim,
victim slot, damage flags, landed).

- Damage flags with 0x4000 or 0x8000: no sound.
- Material, for a creature victim: the first set bit of the 64-bit word +0xa8, in the
  order 35 `lthr`, 36 `chnmail`, 37 `mtlplate`, 40 `bone`, 39 `exo`, 38 `stone`, 34
  `cloth`, else `flesh`. For a player victim it is the armour item of record +0x4400:
  0x80000 `cloth`, 0x100000 `lthr`, 0x200000 `chnmail`, 0x400000 `mtlplate`, else, or
  with no item, `flesh`.
- Type: flag 8 `slash` (spelled `slsh` for `stone` and `exo`), else flag 4 `pierce`,
  else `bludg`.
- Weight: `miss` when not landed. Otherwise amount ÷ maximum hit points (creature +0x22c,
  player record +0xb0): below 0.25 `lt`, below 0x3f199999 `med`, else `hvy`.
- The call is `sound_playOnObject(1.0, lump_get("fx.lmp", name), object)`, where the
  object is the victim, or the player record's object word +0x43d8.

The test pairs are exact quotients or far from both thresholds, so the result does not
depend on the divide's last bit. A maximum of 0 was not tested.

### 4.4 Interface and reward sounds (Observed names)

Straight `lump_get("fx.lmp", …)` calls followed by a sequence start, read from the
string loads before each call:

| Event | Site | Sequence |
|---|---|---|
| level up | `player_giveExp` 0x1d327c | `menu_lvlup.anm` |
| help / quest message | `hud_showHelpMessage` 0x1d98f4 | `butn_message.anm` |
| save point | `Savepoint_run` 0x28cecc | `game_lvl_save.anm` |
| gold picked up / dropped | `Gold_onTouch` 0x157b04 / `Gold_run` 0x157ba8 | `inv_equip_coin.anm` / `inv_drop_coin.anm` |
| pickup refused | `itemprop_tryPickup` 0x154e44 | `game_butn_cantdo.anm` |
| pickup taken | `itemprop_tryPickup` 0x154fc8 | name built at run time (not read) |
| mission menu | `missionMenu_open` 0x23169c, `missionMenu_run` 0x231b08 | `spel_gatescroll.anm`, `menu_main_accept.anm` |
| spell put on a quick slot | `hud_onQuickSlot` 0x1de2e8 | `menu_spell_assign.anm` |
| script heal | `script_healPlayer` 0x1468e0 | `spel_cas_curelw.anm` |

424 `jal` sites start a sequence, a sample or a music entry. This table covers the
reward and feedback ones that came up for this question. It is not a catalogue; the rest
are spells, projectiles, creatures and menus, at their own call sites.

## 5. Volume and options

**Executed [option defaults]** (`config_setDefaults(-1)` 0x1e6238, every callee stubbed):
`g_sfxVolume` 0x4f8940 = 0x3f000000, `g_musicVolume` 0x4f8944 = 0x3f000000 and 0x4f8948
= 1. The same values go to the options image +0x08, +0x0c and +0x10 (0x4f8f40–0x4f8f48).
Then `music_applyVolume` is the only call. The executable image holds 1.0, 1.0 and 1 for
the three globals, and `save_init` replaces them before play. How an options file and the
slider change the music value, in steps of 1/120, is executed on branch
`t3/research-combat-ctors-4` (commit 22408a1, `docs/spec/music-volume.md`). The effects
slider uses the same menu type. **Unknown:** what 0x4f8948 = 1 means; it is sent to the
driver unchanged (below), and `voice_setVolume` averages the two sides for the mono
setting (`docs/audio-save.md` 278).

**Executed [channel volumes]** (`audio_setChannelVolume` 0x216690, `audio_sendVolumes`
0x2166e0; `ref_audio_session.set_channel_volume` and `send_volumes_payload`, lines
298–313). The three driver channels, one per stream, are floats at 0x4f8a18; the image
holds 1.0 in each. Setting a channel clamps the value to 0..1. If the result equals the
stored float, nothing happens. Otherwise it is stored, and RPC 0x80 is sent with 16
bytes at 0x877200: the stereo word, then `cvt.w.s(channel × 256)` for channels 0, 1 and 2.

- **Channel 2 (music)** [music and stream-0 volume]: `music_applyVolume` 0x215e78 asks
  for stream 2's status. With 0x20 it sets channel 2 to duck × music × 0x3f480000
  (0.78125), multiplied in that order. The same product is set by `music_playGlobal`,
  `music_playLevelIndex` and `music_playLevel` (0x211130, 0x215f18, 0x215f98, Observed),
  and by `music_updateDucking` (0x21264c).
- **Channel 0 (intro and level ambience)** [music and stream-0 volume]: every
  `sound_update` checks stream 0's active flags and the flags of every queued entry
  (0x2127f0–0x212840). When none carries 0x20, it sets channel 0 to
  min(music + music, 1) × 0x3f160000 (0.5859375). Ambience therefore follows the music
  slider, not the effects slider.
- **Channel 1 (voice):** stays at its image 1.0, except that `cut_advance` sets it to 0
  when the language byte 0x44fddc is nonzero (0x19925c–0x199274, Observed). That byte is
  0 in the NTSC image.
- **Effects:** `g_sfxVolume` scales each voice's SPU side volume (`voice_setVolume`
  0x213a78; audio-playback.md 87–92). No channel is involved.

## 6. Frame order

**Executed [update order]** (`sound_update` 0x212670, every callee auto-stubbed to
return 0; `ref_audio_session.update_order`, lines 264–276). The callees, in order:

1. `music_updateDucking` 0x212500, at 0x212690;
2. `sound_pauseResumeVoices` 0x212340;
3. `stream_serviceQueues` 0x211df8, when `g_soundFrame & 3 == 0`;
4. `soundSeq_updateAll` 0x2147c0;
5. `ambient_update` 0x2149d0;
6. `sound_flushSpuCommands` 0x210cd0;
7. two end-flag register reads 0x35ee38, when `g_soundFrame & 7 == 0`;
8. `audio_setChannelVolume(0, …)` when stream 0 carries no 0x20 (section 5);
9. `audio_sendVolumes` when the incremented `g_soundFrame` has low four bits 0.

`g_soundFrame` gains exactly 1 per call. `music_updateDucking` has no other caller
(`jal` scan). This answers the call-site question the client left open: duck once per
`sound_update`, before the queue service. The 4-, 8- and 16-frame phases are as in
audio-playback.md 256–272. That run returns 0 from every callee, so the delayed-sample
and mute countdown branches between the listed calls only take their zero paths.

## 7. One mixer per process

The client keeps one native mixer per process and ends a session instead of rebuilding
it (open-champions-godot `docs/PLAYABLE_AUDIO.md` on `codex/session-music`, "Clock and
authority"). The original
supports that shape:

- **Observed:** `sound_init` 0x212f08 has one caller, `engine_init` 0x19d73c, and
  `sound_allocStreamBuffers` 0x212b28 has one, `sound_init` 0x2130a0. Nothing frees or
  re-creates the mixer at a load.
- **Executed (audio-playback.md 256–272):** `g_soundFrame` and `g_drawFrame` count for the
  whole process. Their image phases match a counter that started at 0.
- **Process-lifetime words touched here:** the duck scalar and target (0x4f894c,
  0x4f8a0c), the channel floats 0x4f8a18, `g_ambientCountdown` 0x50608c (kept across a
  recall load [session countdown]), the preview timers 0x44fa7c and 0x4f7030, and the
  sequence generation counter 0x4f8950 (`docs/audio-save.md` 202–223). None is reset by a
  load.
- **Reset at every load:** sequences and stream queues (`sound_unloadAbove`, Observed),
  and `g_cosmeticSeed`, copied from `g_randSeed` [level entry].

**Inferred client rule:** a session boundary should do what a level load does. Stop the
sequences, queue stream stops, and leave the counters, the channel floats and the duck
words alone. When the client models the cosmetic generator, it should copy the shared
seed at each load. The client's `end_session()` already keeps the counters and the duck
words. Whether it reseeds a cosmetic generator was not checked here.

## 8. Not established

- What 0x4f83b8 (set by the unused `enttag` path) and the 0x86ad58 credits flag are for.
- The meaning of the stereo word values, and how voice and effect panning react to them.
- The `MOUTH.VAT` name counts behind each voice prefix. The pick among them is random
  (cosmetic), and this round did not count them.
- The run-time name of a taken pickup's sound (0x154fc8), and every spell, creature and
  menu sound not listed in 4.4.
- `sound_unloadAbove` as a whole was read, not run.
- Everything about the heard result: no capture was made for this round.

## 9. How to repeat

```
python3 tools/difftest_audio_session.py path/to/SLUS_209.73 --seed 20973
python3 tools/difftest_audio_session.py path/to/SLUS_209.73 --seed 7
python3 -c "import dis, unittest, sys; sys.path.append('tools'); import test_ref_audio_session as t; unittest.main(module=t, argv=['x'])"
```

The per-level table of section 2.2 needs the disc's level lumps. It was produced by a
throw-away script that reads each `ntsc_dialog.bin` through `tools/anim_audio_info.py`'s
container reader. The script stays under `local/`.
