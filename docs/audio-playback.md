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
services delayed samples, sequences, streams and the register batch. Every eighth
sound frame it checks SPU end flags to reclaim non-looping voices. Up to 32 delayed
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
0x1e000 and 0x40000 bytes for streams 0, 1 and 2. Stream 0 was seen for the intro
movie soundtrack (`splash_introMovie` 0x321788); stream 1 serves voice and dialog
(0x196788, 0x22ec9c, 0x1b7ba8); stream 2 serves music and, only when no music is
active/queued, ambient one-shots (`ambient_update` 0x2149d0). Streams 0 and 2 each
use two SPU voices; stream 1 uses one. `audio_streamStatus` 0x211b20 and
`audio_streamPosition` 0x216480 are blocking driver queries, with position zero
when inactive.

Queue flag meanings read in 0x211548/0x211df8: 1 loop, 2 fade/stop current before
starting the new entry (flag 2 alone is a stop marker), 4 wait for current to end,
8 hold until released, 0x20 recognized by voice/ambience suppression, 0x80 on
ambience one-shots. **Unknown:** 0x40 and 0x100 are passed by callers but their full
meaning has not been traced (`docs/formats/anim-audio.md` 3.4). The stream driver
volume target RPC 0x70 changes current volume every 6 ms: −0x20 per tick,
+0x40 on stream 0 or +0xc0 on streams 1/2. A stop from full 0x3fff therefore takes
about 3.07 s before `stream_serviceQueues` clears the old stream and starts the next.
**Inferred:** one stream 2 cannot play two music entries simultaneously, so original
music changes are sequential fades, not overlapping crossfades. Do not substitute
the Godot client's optional custom boss soundtrack for this original rule.

**Observed music entry points:** `music_playGlobal` 0x2110e0 queues a `MOUTH.VAT`
entry on stream 2 with flags OR 0x22; `music_playLevel` 0x215f48 queues a level VAT
entry, with flags OR 0x22 when its volume gate passes; script `startMusic` 0x146b68
passes flags 3 and `endMusic` 0x146be4 queues a stop marker. `creature_startBossMusic`
0x1192b0 gets a per-creature name from `creature_bossMusicName` 0x10dbe0, stops
stream 2, then calls `music_playGlobal(name, 0x103)`; `creature_stopBossMusic`
0x1192f8 queues stream 2 stop. `script_applyCFlag` 0x1445fc triggers that boss path
when cflag bit 0 changes (`docs/script.md` 749). A cutscene dialog key type 7
releases a held stream-2 entry and queues the following level-directory entry
(`cut_execKey` 0x196788; `docs/engine.md` 509). Menu/title music is a global VAT
stream: a recompiled-build title capture had stream 2 playing a stereo entry and
matched the emulator (`docs/issues/native-sound.md` 4.3).

`music_updateDucking` 0x212500 reads stream 1 status; when its 0x20 bit is set it
sets the duck target to about 0.2, then eases its scalar by 1/60 per update and
applies it through `music_applyVolume` 0x215e78. `g_musicVolume` is 0x4f8944;
`audio_setChannelVolume` 0x216690 and `audio_sendVolumes` 0x2166e0 send stream
scales and stereo option. **Unknown:** the complete level-by-level and menu music
choice table, ordering of every boss override, and any additional transition path;
the per-level script/stream directory and caller path must be inspected before a
native client selects specific names. `game_loadLevel` 0x1e55c0 has an `enttag`
first-entry path, but no NTSC directory contains that tag (`docs/formats/anim-audio.md`
3.6). Never infer a track from the level name alone.

## Film, cutscenes and lip sync

**Observed:** intro movie setup queues `porko_l.vag` on stream 0 held and releases
it when the movie is ready (`splash_introMovie` 0x321788). **Unknown:** exact video
frame-to-audio resynchronization or drift correction for that movie; this evidence
only establishes the start hold.

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
VAT directory/interleave, duration and camera gain. It does not emulate SPU2 mixing,
queue state, cosmetic RNG, or disc reads. `docs/issues/native-sound.md` reports a
recompiled-game comparison, not verification of this separate Godot client. Sound in
the handwritten native client remains unverified until an affected scene is heard or
captured there, including a level change, speech, 3-D motion and a boss transition.
