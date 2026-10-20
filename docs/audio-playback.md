# Return to Arms playback contract (SLUS-20973 v2.00)

For the shared C++/Godot client. **Observed** means read at an addressed executable or
IOP driver site (or measured in the named private run); **Inferred** means a consequence
of that evidence; **Unknown** is not ready to hard-code. File bytes, decompiler text
and recordings are intentionally absent. See [formats/audio.md](formats/audio.md)
for media layouts and `docs/issues/native-sound.md` for the recompiled-build study.

## Effects: from event to voice

**Observed** (`docs/audio-save.md`, `docs/formats/anim-audio.md` 2.7):

1. A caller chooses a `.anm` sound sequence from a lump, usually `fx.lmp`, and calls
   `sound_playOnObject(volume, sequence, object)` 0x214230 or
   `sound_playAtPos(volume, sequence, position)` 0x214428. The former follows its object;
   `soundSeq_updateAll` 0x2147c0 refreshes the position. A direct sample can be started
   with `sound_playSample(pitchScale, volume, delaySeconds, sample, position)` 0x2134e8.
   Scripts expose `sound` 0x1435e0 and `soundSequence` 0x143684; the latter makes its
   sequence play while frozen (`docs/script.md` 810–811).
2. A sound sequence uses an `.anm` clip's sound table (+0x34) and 0x1c-byte events
   (+0x38). Events are sorted by tick and terminated at tick 0x7fffffff. `anim_advance`
   0x16d748 fires only the top track's crossed events when given a sound position.
   Event +4 is sample index; −1 is silent, −2 calls `game_animEventFoley` 0x1ebd00;
   −3 and −4 are reserved/ignored. Selector +8 is 0 for unconditional or 1–6 for one
   cosmetic-random choice among events of the same tick and selector (0x16d558).
3. `animsound_play` 0x16d360 interprets +0x0a signed pitch semitones, +0x0b
   semitone variation in eighth steps, +0x0c signed volume units, +0x0d volume
   variation, +0x0e random start delay in ticks. It uses a 128-float
   `2^((index-64)/12)` table at 0x7b9238, the sound group's volume table 0x41bac8,
   then calls `sound_playSample`. Randomness comes from `g_cosmeticSeed`, not the shared
   gameplay seed (0x16d360; `docs/audio-save.md` A4). Name binding at 0x16cc38 uses
   `sample_findByName` 0x216798; unresolved names are silent.
4. A requested sequence occupies one of 32 slots (`g_soundSeqs` 0x871a68, stride
   0x4c). Start returns −1 when all slots are used or category +0x3c of its clip has
   reached the limit in byte table 0x4f8a28; category 0 has no category cap
   (`sound_playOnObject` 0x214230, `sound_playAtPos` 0x214428). A successful handle
   has bit 15 set and contains the slot plus generation shifted by 8. `sound_stop`
   0x213ea0 checks this generation and stops matching voices. `sound_release`
   0x213438 on a sequence makes it repeat at clip duration until stopped; it does
   **not** mean release the tail (`soundSeq_updateAll` 0x2147c0).

   **Observed table constants:** for the 0–98 groups present in the NTSC disc,
   `g_soundGroupLimit` at 0x4f8a28 is 2 except group 14 = 9 and groups 50/51 = 8.
   Group 0's sequence-concurrency check is bypassed despite its stored byte being 2.
   The same table bounds animation sound events per drawn frame at 0x16d9d8
   (`docs/spec/animation.md` 161). These are limits on starts, not a voice-stealing
   priority. **Unknown:** a separate priority system beyond the free-voice scan at
   0x2169f8; no evidence here establishes one.
5. Direct samples and sequence events use 43 effect voices, round robin among free
   voices (`voice_alloc` 0x2169f8). Their records are 43 × 0x14 at 0x872880;
   +0x00 sample, +0x04 flags (4 in use, 0x10 looping, 2 frozen, 8 play while frozen),
   +0x06 owning sequence slot, +0x08 generation, +0x0c pitch, +0x10 volume.
   Voice 0–23 is SPU core 0; 24–42 is core 1 voice 0–18. The driver reserves core 1
   voices 19–23 for streams (`docs/issues/native-sound.md` 1.3).

**Observed event families, not an exhaustive name map:** player footstep dispatch is
`Player_footstep` 0x1beec8; animation id −2 reaches `sound_playFoley` 0x1e7c40,
which selects footstep/armour sequences and variation. Material and damage type reach
`sound_playHit` 0x1e7e40, which builds the hit sound name and plays it on the target
(`symbols/player.tsv`, `symbols/ui.tsv`). Spell constructors and cast/hit sites call
`sound_playAtPos`/`sound_playOnObject`; examples and addresses are in
`docs/spec/skills-35-68.md` sections for their respective spells. Local inventory
equip calls use the same effect path (`inventory_equipItem` 0x1c27c0). **Unknown:** a
complete event-to-sample catalog across every class, item and menu action; no one
global lookup table establishes it. Use each caller and `.anm` event table, not a
guessed filename rule.

## Position, gain and timing

**Observed** in `sound_panAtten` 0x213c50–0x213dd8: given camera position
0x44f038 and right vector at 0x44f110/0x44f11c/0x44f128, let
`delta = source - camera`, `distance = length(delta)`,
`attenuation = clamp((far - distance)/(far - near), 0, 1)` outside the near sphere,
and 1 inside it. Let `pan = clamp(dot(delta, cameraRight)/far, -1, 1)`.
The outputs are `left = attenuation*(1-pan)` and
`right = attenuation*(1+pan)`; each side can reach twice the centered factor.
Sequence slots store default near 360 and far 840 at +0x44/+0x48
(`sound_playOnObject` 0x214230). `voice_setPosition` 0x2168e8 and
`sound_setVolume` 0x214650 recalculate for moving/followed sounds. A non-looping
sample whose two scaled sides are zero is not started (`sound_playSample` 0x2134e8).
**Inferred:** world coordinates and the local camera affect presentation only; keep
this out of shared gameplay state (`docs/audio-save.md` A3).

**Observed** (`sound_playSample` 0x2134e8, `voice_setVolume` 0x213a78,
`sound_flushSpuCommands` 0x210cd0): sample base pitch is
`integer(rate*4096/48000)`, multiplied by event pitch scale and clamped to 0x3fff;
voice pitch 0x1000 corresponds to 48 kHz. SPU side volumes are positive 0–0x3fff,
scaled by `g_sfxVolume` 0x4f8940. Every new effect batch writes VOLL, VOLR, pitch,
sample start, ADSR1 0xff, ADSR2 0x1fc0 and loop address 0x5000, then key-on.
ADSR is effectively a gate (attack reaches full in about three output samples;
release silences within two). Every displayed frame `sound_update` 0x212670
services delayed samples, sequences, streams and the register batch. It services
the stream queues when `g_soundFrame` 0x4f8954 has its low two bits clear, and it
reads the end flags when that word's low three bits are clear, both before it
increments the counter. The 16-frame cases use two different counters; they are
recorded with the music policy below. Up to 32 delayed
samples wait at 0x8723f8. Freeze zeros pitch for voices without the play-while-frozen
flag (`sound_pauseResumeVoices` 0x212340). `sound_muteFor` 0x216588 makes direct
sample starts return −1 while its countdown at 0x877240 is active.

**Observed** (`sound_init` 0x212f08, level-effect setup 0x2156e0): the original
uses no audible reverb; all 91 observed level rows set effect mode/depth/delay/
feedback to zero (`docs/issues/native-sound.md` 1.3). Preserve an explicit unknown
for any different disc revision rather than fabricating effect presets.

## Three streams and music policy

**Observed** (`g_streams` 0x876c10, 3 × 0x1c4; `stream_serviceQueues` 0x211df8;
HELLO.IRX RPC server 0x163a5): each stream has an eight-entry EE queue at +0x40,
with 0x30-byte entries and count at +0x1c0. The driver has rings of 0x19000,
0x1e000 and 0x40000 bytes for streams 0, 1 and 2. Stream 0 serves the intro
movie soundtrack (`splash_introMovie` 0x321788) and level `amb_` entries
(`mainloop_pollAmbientAudio` 0x322650–0x3226c4); stream 1 serves voice and dialog
(0x196788, 0x22ec9c, 0x1b7ba8); stream 2 serves music and, only when no music is
active/queued, ambient one-shots (`ambient_update` 0x2149d0). Streams 0 and 2 each
use two SPU voices; stream 1 uses one. `audio_streamStatus` 0x211b20 and
`audio_streamPosition` 0x216480 are blocking driver queries, with position zero
when inactive.

Queue flag meanings, read in `stream_startQueued` 0x211548 and
`stream_serviceQueues` 0x211df8, and for 0x40 and 0x100 executed at the callers
below (`tools/difftest_audio.py`, properties "queue promote", "stream status" and
"flag callers"): 1 loop, 2 fade/stop the current entry before the new one starts
(flag 2 alone is a stop marker), 4 wait for the current entry to end, 8 hold until
released, 0x20 recognized by voice and ambience suppression, 0x80 on ambience
one-shots. Bits 0x40 and 0x100 are stored on the entry. `audio_streamStatus`
returns them with bit 0 set, except that a held entry which is only queued reports
idle. Neither service routine branches on 0x40 or 0x100.

**Executed:** bit 0x40 tells a later caller to fade-stop stream 2. These slices
call `stream_queueStop(2)` when `audio_streamStatus(2)` has bit 0x40, and make no
stream-2 call otherwise: 0x18c468–0x18c488, 0x18d7cc–0x18d7e8, 0x18e2d4–0x18e2f4,
0x1d9040–0x1d922c and 0x1e10f4–0x1e1114. `music_playGlobal` is entered with flags
0x41, stored as 0x63, for `mx_main_l.vag` at 0x18d7a0 and for `mx_maintheme_l.vag`
at 0x1e10b8. Boss music is stored as 0x123 and the level-poll track as 0x122, so
those fade-stops leave both of them playing. The front end's first queue of
`mx_maintheme_l.vag` uses flags 1 or 5 (0x1e09b0, 0x1e09c4), which also lack 0x40.

**Executed:** bit 0x100 tells cutscene teardown to leave that stream-2 entry
alone. Both slices read the gate word 0x44fd10. In the `cut_runFrame` slice
0x199e54–0x199e98, a set gate plus status bit 0x80 and no 0x100 calls
`audio_streamStop(2)`; every other combination leaves stream 2. In the `cut_end`
slice 0x19a114–0x19a168, a clear gate does nothing to stream 2, a set gate with
0x100 does nothing, a set gate with 0x80 and no 0x100 hard-stops stream 2, and
any other set-gate status, including idle, calls `stream_clearQueue(2)` and leaves
the active entry. Boss music is queued with 0x103 and the level poll with 0x102,
so both carry 0x100. An ambience one-shot is 0x80 without 0x100, so a cutscene
hard-stops it. A music entry with neither bit loses its queue and keeps playing.

The stream driver volume target RPC 0x70 changes current volume every 6 ms: −0x20
per tick, +0x40 on stream 0 or +0xc0 on streams 1/2. A stop from full 0x3fff
therefore takes about 3.07 s before `stream_serviceQueues` clears the old stream
and starts the next. **Executed** for a queued fade bit, including a second boss
(`stream_startQueued` 0x211548, property "queue promote"): while the driver status
volume word at 0x8771c0 + stream×16 + 8 is nonzero, the entry stays queued and the
service sends RPC 0x70. At volume 0 it sends 0x60 and 0x70 and promotes the entry.
The two spans are not heard together. Do not substitute the Godot client's
optional custom boss soundtrack for this original rule.

**Observed music entry points:** `music_playGlobal` 0x2110e0 queues a `MOUTH.VAT`
entry on stream 2 with flags OR 0x22; `music_playLevel` 0x215f48 queues a level VAT
entry, with flags OR 0x22 when its volume gate passes; script `startMusic` 0x146b68
passes flags 3 and `endMusic` 0x146be4 queues a stop marker. `creature_startBossMusic`
0x1192b0 gets a per-creature name from `creature_bossMusicName` 0x10dbe0, stops
stream 2, then calls `music_playGlobal(name, 0x103)`; `creature_stopBossMusic`
0x1192f8 queues stream 2 stop. `script_applyCFlag` 0x1445fc triggers that boss path
when cflag bit 0 changes (`docs/script.md` 749). A cutscene dialog key type 7
releases a held stream-2 entry and queues the following level-directory entry
(`cut_execKey` 0x196788; `docs/engine.md` 509). The front-end task
`frontend_run` 0x1e08f0 queues global `mx_maintheme_l.vag` on stream 2 at
0x1e09b0/0x1e09c4 (flags 1 or 5 according to its state byte 0x4f701a), and
also requeues it at 0x1e10b8/0x1e114c. The title capture matched the
emulator with this stereo stream (`docs/issues/native-sound.md` 4.3).

**Observed boss-name mapping** (`creature_bossMusicName` 0x10dbe0–0x10de0c):
the creature type name at +0x34 is compared without case (`libc_strcasecmp`
0x3b81a0). The two cyclops cases also compare the object's `name` property
(`obj_getPropStr` 0x14f4c0). No match returns no boss music name.

| Creature type | Additional `name` | Global `MOUTH.VAT` entry |
|---|---|---|
| `cazicavatar` | — | `mx_ba_avataroffear_l.vag` |
| `fatcyclops` | `broon` | `mx_ba_broon_l.vag` |
| `fatcyclops` | `droon` | `mx_ba_droon_l.vag` |
| `cyclops` | `proon` | `mx_ba_proon_l.vag` |
| `cazicthule` | — | `mx_ba_cazicthule_l.vag` |
| `reddragon` | — | `mx_ba_dozekar_l.vag` |
| `ironguardian` | — | `mx_ba_ironguardian_l.vag` |
| `mattmarr` | — | `mx_ba_matanielmarr_l.vag` |
| `raloszek` | — | `mx_ba_ralloszek_l.vag` |
| `vampirelord` | — | `mx_ba_vanerhost_l.vag` |
| `snowboss` | — | `mx_ba_whitetormentor_l.vag` |

**Observed level poll** (`mainloop_pollAmbientAudio` 0x322520–0x3226dc,
`libc_strstr` 0x3b96a8): once per displayed frame the countdown word at 0x50608c
(the load is 0x32254c) is decremented. The image word is 0x2a30. At zero it is
reset to 14,400–21,599 frames (240–360 seconds at 60 Hz) using `g_cosmeticSeed`
0x404460. If stream 2's queued flags lack 0x20, the routine walks the current
level's `dialog.bin` directory in order and queues the first name containing
`_env_` or `mx_theme` through `music_playLevel(name, 0x102)` at 0x322634.
Separately, when `g_drawFrame` 0x44fdd0 has its low four bits clear, if stream 0
is idle, it queues the first level-directory name containing `amb_` through
`stream_queueLevelIndex(0, index, 3)` at 0x3226c0. The image value of that counter
is 0x400, so the image frame itself is one of those frames. This corrects the
earlier **inference** in `docs/formats/anim-audio.md` 3.4 and `docs/audio-save.md`
that stream 0 was only seen for the intro. The `amb_` scan is separate from
`ambient.bin` one-shots (`ss_*`), which use stream 2 only when no music is active
or queued (0x2149d0).

`music_updateDucking` 0x212500 is **executed** (`tools/difftest_audio.py` "duck",
repeated under the six `tools/ee_emu.py` rounding setups). The current scalar is
0x4f894c, image 0x3f800000, and the target is 0x4f8a0c, image 0. When
`audio_streamStatus(1)` has bit 0x20, the target is set to 0x3e4cccd0 (about
0.20000005, one ulp above the ordinary 0.2 pattern 0x3e4ccccd). The target then
always gains 0x3c888888 (about 1/60) and is clamped to 0x3f800000 when the sum
exceeds 1. While the voice bit stays set, the target therefore holds at
0x3e5ddde1. With the bit clear, the target stays where it is and keeps taking that
same step toward 1. The current scalar moves toward the target by 0x3c23d70a
(about 0.01) per call, and snaps to the target when one step would pass it. If
the level name at 0x44fe18 compares equal to `actintro` and the language byte
0x44fddc is nonzero, the scalar is then stored as the integer 0. Language 0
leaves it; the image name is empty and the image language is 0. When the scalar's
float value changed and stream 2's status has bit 0x20,
`audio_setChannelVolume(2, scalar * g_musicVolume * 0x3f480000)` runs.
`g_musicVolume` is 0x4f8944. `music_setDuck` 0x216570 writes `1 − argument` to
the target and leaves the current scalar alone: argument 0 stores 0x3f800000,
argument 1 stores 0, and the ordinary 0.2 pattern 0x3e4ccccd stores 0x3f4ccccc.
The next duck update still adds 0x3c888888 to that target. `music_playGlobal`
queues only when `g_musicVolume` compares at or above 0x3d4ccccc; the equal
pattern is open and a smaller pattern, including 0, queues nothing.

**Executed boss override** (`creature_startBossMusic` 0x1192b0,
`creature_stopBossMusic` 0x1192f8; property "boss override"). A creature with no
boss name leaves stream 2 untouched. A creature with a name calls
`audio_streamStop(2)` and then `music_playGlobal(name, 0x103)`. A second start
does the same thing: the stop clears the queue, and the new call leaves exactly
one `mouth.vat` entry, flags 0x123, whose offset, length and restart are the new
directory span. The active name stays empty until `stream_startQueued` promotes
the entry. The queued file name is always `mouth.vat`; the VAT span is what
distinguishes the two bosses. The fade bit inside 0x123 then applies the volume
rule above, so the replacement waits until the status volume word reads 0.
`audio_streamStop` does not itself write that word. A start whose music volume
is below 0x3d4ccccc, or whose directory row is missing or has length 0, has
already stopped stream 2 and then queues nothing. `creature_stopBossMusic`
appends an empty-name entry with flags 2 whenever the creature has a boss name,
including when the queued span belongs to a different boss. A creature with no
boss name does not append.

**Executed frame counters** (properties "cadence image", "sound cadence" and
"draw cadence"). `g_soundFrame` 0x4f8954, image 0, is the counter for the 4-frame
queue service, the 8-frame end-flag reads, and the 16-frame volume send. Inside
`sound_update` the service runs when the low two bits are 0. The increment is
stored next. The two end-flag reads, `0x35ee38` with register ids 0x1700 and
0x1701, run when the new value's low three bits equal 1, the same calls as a
low-three-bits test of the value on entry. `audio_sendVolumes` 0x2166e0 runs
after the increment, when the new value's low four bits are 0, so the value on
entry ended in 0xf. The 16-frame `amb_` poll and the group-volume refresh use
`g_drawFrame` 0x44fdd0, image 0x400. `animsound_updateGroupVolumes` 0x170238
writes on the same low-four-bits test as the poll. The poll also requires stream
0 status 0 and a directory name containing `amb_`. Both counters are
process-lifetime words, and their image phases match a counter that started at 0.
They move apart when one advances alone. The loading-screen thread increments
`g_drawFrame` (`docs/mainloop.md`) and `game_loadLevel` calls `sound_update`
twice (`docs/issues/sync-breakers.md`); those two splits were not re-executed
in this round.

Level scripts and cutscene keys can also queue named tracks, so the poll's first
match is not an exhaustive level playlist. `game_loadLevel` 0x1e55c0 has an
`enttag` first-entry path, but no NTSC directory contains that tag
(`docs/formats/anim-audio.md` 3.6). Never infer a track from the level name alone.

## Film, cutscenes and lip sync

**Executed** (`splash_introMovie` 0x321788; the `movie_update` slice
0x3209f8–0x320af0; properties "intro drift" and "movie drift"). The splash queues
`porko_l.vag` on stream 0 with flag 8 and does not write the sync gate byte
0x506034. The image gate is 0. `movie_enableAudioSync` 0x3205c8 sets that byte
and zeroes `g_movieFrame` 0x506038; `movie_disableAudioSync` 0x3205e0 clears the
byte. The US v2.00 executable contains no `jal` encoding of either address and no
pointer-sized word equal to either address. `movie_update` 0x3205ec itself has
two `jal` encodings. With the gate clear, each update decodes, increments
`g_movieFrame`, does not read a stream position, and leaves the last position at
0x8eb000 unchanged.

With the gate forced on, the compared stream is stream 2, which is not the
intro's stream 0. An unchanged position decodes and increments the frame. A
changed position is stored as the last sample before the choice. Video time is
`float(g_movieFrame) * 0x3d08ab85 − 0x3d8f5c28`. Audio time is
`float(position − 0x400) * 0x3798eadb`, with the subtraction wrapped to 32 bits
before the conversion. The picture is held, and the frame stays, when the
absolute gap is at least 0x3ca3d70a and the video time is greater than or equal
to the audio time. A video time behind the audio time decodes even when the gap
is larger than that threshold. The intro never takes this path: nothing in the
executable calls the enable function.

Cutscene and NPC `.dbin` nodes name their text key and voice entry separately; there
is no text-to-audio naming rule (`cut_loadDialog` 0x1964d4,
`dialog_queueLineAudio` 0x22ec9c). A cutscene line queues `<voice>.vag` on stream 1
with 0x28 (held), releases it at its dialog key, and preloads matching `<voice>.anm`
from the VAT for mouth motion (0x196788, 0x199958–0x199b60). A missing or late clip
uses a generic talk animation (`docs/engine.md` 545–555).

**Observed** (`cut_advance` 0x199444–0x1995c8; `dialog_syncMouth` 0x22fdd8):
stream position is converted to time as `played_bytes * 28 / (16*24000)` seconds.
The cutscene speaker's animation tracks receive a per-frame correction of +0.1,
−0.1 or zero toward that local audio time (`g_cutAudioCorrection` 0x44fd30).
Dialog key type 3 waits for each machine's voice to finish and report a done message
before advancing the cutscene (`cut_advance` 0x199398–0x1993cc; FINDINGS D18).
This is local timing state that can alter track times across peers (FINDINGS D8;
`docs/issues/native-proof.md` 113), so a native client should expose real stream
position even if output is muted. **Unknown:** exact threshold branch for the
±0.1 correction in a standalone native implementation; use the addressed code or a
controlled differential test before claiming bit-exact cutscene synchronization.

## Implementation and proof boundary

`tools/ref_audio.py` is a pure, synthetic-fixture contract for headers, ADPCM blocks,
VAT directory/interleave, duration and camera gain. `tools/ref_audio_playback.py`
is the queue, duck, loop-restart, cadence and movie-sync half, checked against
the original functions by `tools/difftest_audio.py`. Neither emulates SPU2 mixing,
cosmetic RNG, or disc reads. `docs/issues/native-sound.md` reports a
recompiled-game comparison, not verification of this separate Godot client. Sound in
the handwritten native client remains unverified until an affected scene is heard or
captured there, including a level change, speech, 3-D motion and a boss transition.
