# Animation and audio file formats

What a native rebuild needs to play the game's animations, sound effects, voice and music
from a player's own disc: the `.anm` animation format in full, every audio file type on the
disc, and the dialog files that tie voice lines to text. Tool: `tools/anim_audio_info.py`.

Everything was read from `SLUS_209.73` (US v2.00), from the sound driver module
`BG/0MOD/HELLO.IRX` on the same disc, and from the disc's own files. Nothing was run on a
console or emulator when this was written, and nothing in this document has been checked on
a running game since. Two things have changed around it: the animation step and the pose
have been executed function by function in `tools/ee_emu.py` (`docs/spec/animation.md`,
which corrected sections 2.5 and 2.6 below), and the project now has a live game — in the
Play! emulator, not a PlayStation 2 and not PCSX2; what was run there is listed in
`FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`, and it
has no sound or video output, so none of the formats here was exercised.
The tool was run over every file on the disc (section 7).

How to read the status marks:

- **O** (Observed) — read in the loader or driver code at the address given **and** confirmed
  in sample files.
- **I** (Inferred) — only one of the two: code that no file on the disc exercises, or a
  pattern in the files for which no reader was found. The text says which.
- **U** (Unknown) — not established.

All integers are little endian unless noted. Addresses without a file name are in
`SLUS_209.73`; addresses written `HELLO+0x…` are offsets in the `.text` of `HELLO.IRX`
(the module carries its symbol names: `alarm`, `func`, `stream`, `streamPitch`, …).

## 1. Where the data is

| What | Where on the disc | Count (NTSC v2.00) |
|---|---|---|
| Animations `.anm` | entries of `.LMP` lumps (creature, player, prop and `fx` lumps) | 4,510 in 274 lumps |
| Lip-sync animations `.anm` | byte ranges of the level stream files `.VAT` | 208 |
| Sound-effect samples `.vag` | lump entries | 4,933 in 137 lumps (1,193 distinct names) |
| Sound sequences | `.anm` entries whose sound-event list starts samples (mostly `fx.lmp`) | 2,921 of the `.anm` files carry sound tables |
| Streamed audio (voice, music, ambience) | `BG/DATA/<LEVEL>.VAT` and `MOUTH.VAT`, headerless | 117 files (19 empty), 5,351 audio entries |
| Stream directories | entry `ntsc_dialog.bin` (also `pal_*_dialog.bin`) of `<level>.lmp` and `MOUTH.LMP` | 482 tables, 122 of them NTSC |
| Dialog nodes `.dbin` | entries of `<level>.lmp` | 52 files, 300 nodes |
| Ambience schedule `ambient.bin` | entry of `<level>.lmp`, plain text | 93 |
| Unreferenced stream data | `BG/DATA/PORKO.VAG`, `BG/DATA/MAINMENU.VA1` | 2 |
| Sample bank of the network setup program | `NETGUI/EFF.HD` + `EFF.BD` (used by `NTGUI2.ELF`, not by the game) | 1 |

`PORKO.SMG`, `porko.bin` and the `.m2v` entries of `PORKO.LMP` are the intro movie
(`movie_open` 0x3202c0); they hold no audio and were not examined. The movie's soundtrack is
the stream entry `porko_l.vag` of `MOUTH.VAT`.

---

## 2. `.anm` — animation

One file is one clip: a header, the skeleton it animates, and a bit-packed stream of keys.
The same format is used for creature and prop animation, for sound sequences (a clip whose
only purpose is its sound-event list) and for the lip-sync clips stored in stream files.

### 2.1 Header (0x70 bytes)

Offsets in the header are relative to the start of the file; `anm_relocate` (0x1707b8) adds
the load address to +0x08, +0x0c, +0x10, +0x34, +0x38 and to every name pointer of the sound
name table.

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | u32 | joint count, 0…64 | **O** loop bound in `animtrack_decode` 0x16e468; decoder slots and pose buffers are sized for 64 (`anim_init` 0x16f9a8: slot 0xf1c = 0x1c + 64×0x3c bytes) |
| +0x04 | u32 | length in ticks; one tick is 1/60 s | **O** compared with track time in `anim_advance` 0x16d748; 1/60 in the event test there and in `dialog_syncMouth` 0x22fdd8 |
| +0x08 | u32 | offset of the key stream | **O** 0x16e468 |
| +0x0c | u32 | offset of the bind offsets: 8 bytes per joint, `s16 x, y, z, 0`, unit 1/64 | **O** read at the end of `anim_buildPose` (0x16f58c, 0x16f5d8) and fed to the VU0 program (2.5); fourth word is 0 in all 205,742 records |
| +0x10 | u32 | offset of the depth list: one byte per joint | **O** 0x16f590, 0x16f5c8 |
| +0x14 | 4 × {f32 seconds; u8 mask; u8 pad[3]} | the four event slots. **Zero in every clip on the disc**; game code fills them after loading (2.7) | **O** reader 0x16d748, writers 0x118378 / 0x1183d0 |
| +0x34 | u32 | offset of the sound name table, 0 = none | **O** `anm_bindSounds` 0x16cc38 |
| +0x38 | u32 | offset of the sound event list, 0 = none | **O** 0x16cc38, `animsound_fireRange` 0x16d558 |
| +0x3c | u8 | sound group: index into the group volume table 0x41bac8 and the group limit table 0x4f8a28 | **O** 0x16d9d8, `animsound_play` 0x16d360; values 0…98 on the disc |
| +0x3d | u8 | sound data version. 0: the pitch/volume/jitter bytes of every event are zeroed at load; below 2: out-of-range sound indices are repaired | **I** code only (0x16cc38): every file with sound tables has version 2 |
| +0x3e | u16 | zero | **I** zero in all files, no reader found |
| +0x40 | u32 | run-time only: duration of the sound sequence in ticks, written by `anm_bindSounds`; `soundSeq_updateAll` 0x2147c0 restarts a held sequence when its time passes this | **O** zero in all files |
| +0x44 | u32 | zero | **I** zero in all files, no reader found |
| +0x48 | u64 | joint mask: bit *j* set = this clip does not drive joint *j* (partial-body clip) | **O** `anim_buildPose` 0x16ed40; non-zero in 3 files only |
| +0x50 … +0x6f | — | zero | **I** zero in all files, no reader found |

After the header come, in this order in every file: the depth list (at 0x70), the bind
offsets, the key stream, then — only in files with sound tables — a 0x28-byte block, the
name table, the names, and the event list.

The 0x28-byte block is not referenced by the header. Its first two words are the offsets of
the name table (always 0x28) and of the event list **relative to the block**, bytes 8 and 9
repeat the header's group and version, the rest is zero (**I**: seen in all 2,921 files, no
reader found; it looks like the exporter's unrelocated copy of header +0x34…).

### 2.2 Skeleton

The clip carries its own skeleton; there is no separate skeleton file and no joint names.

- **Depth list.** Joints are stored in depth-first order. Byte *j* is the depth of joint *j*
  (0 = a root). The parent of a joint is the nearest earlier joint whose depth is one less.
  Several roots are allowed (one prop clip has 64 joints all at depth 0). Deepest chain on
  the disc: 16. **O** — the pose builder keeps a stack of matrices indexed by depth (2.5).
- **Bind offsets.** For each joint, minus the joint's position in the model's bind pose, in
  model space. The pose builder transforms this offset by the joint's world matrix to get
  the translation of the matrix it hands to the renderer, so that matrix moves bind-pose
  vertices directly (a skinning matrix; there is no bind rotation). **O** for the arithmetic
  (2.5). That the values are bind positions is **I** from samples: in 33,554 joints checked
  the distance between a joint's offset and its parent's equals the length of the joint's
  local position at tick 0 (median difference 0.001 units, 98.5 % within 2 %).
- Units: model units, the same as world units before the creature's scale; a humanoid
  pelvis sits about 45 units up. Axes: z is up; walk cycles travel along −y, and the game
  rotates model space by `facing − 0x4000` to get world space (`Creature_stepAnim`,
  `model_getAttachPoint` 0x1754a0).

### 2.3 Key stream

A sequence of 16-bit little-endian words. Bits are consumed from the most significant bit
of each word downward; a field may straddle two words. Signed fields are two's complement
of their stated width. All of this is **O** in `animtrack_decode` (0x16e468); the tool's
decoder follows it and gets through all 4,718 clips on the disc.

**Initial pose**, once per joint, in joint order:

| Bits | Meaning |
|---|---|
| 4 | *w* − 1: width of the three position values (1…16 bits) |
| 3 × *w* | position x, y, z, signed, × 1/64 |
| 4 | *v* − 1: width of the four rotation values |
| 4 × *v* | quaternion in the order **w, x, y, z**, signed, × 1/4096 |

The stored quaternion need not be unit length (lengths from 0.70 to 1.07 occur at tick 0);
it is normalised when the pose is built.

**Key records** follow until the end of the stream:

| Bits | Meaning |
|---|---|
| 8 | ticks since the previous record (0…255); the record's tick is the running sum |
| 1 | 1 = position key, 0 = rotation key |
| 6 | joint index |
| 4 | *w* − 1: width of the values |
| 3 × *w* or 4 × *w* | position key: velocity x, y, z, signed, × 1/256 units per tick. Rotation key: quaternion velocity w, x, y, z, signed, × 1/131072 per tick |

A key does not store a pose. It stores the **rate of change** that applies from its tick
until the joint's next key of the same kind. Each joint therefore has, per channel, a base
value, a velocity and the tick the velocity started at:

```
on a position key for joint j at tick T:
    pos[j]  += pvel[j] * (T - ptick[j])        # settle the old segment
    pvel[j]  = key values / 256
    ptick[j] = T
on a rotation key: the same with rot, rvel (key values / 131072), rtick

value at time t (ticks, may be fractional):
    position   = pos[j] + pvel[j] * (t - ptick[j])
    quaternion = normalise(rot[j] + rvel[j] * (t - rtick[j]))
```

All velocities start at zero and both ticks at 0. A joint with no keys holds its initial
value. Rotation is therefore piecewise-linear in the quaternion's components, renormalised
(the raw length drifts by 2 % at the median before normalising).

Decoding is strictly forward: the decoder consumes every record whose tick is ≤ the integer
part of the track time. To go back in time it starts again from the initial pose (the
`time < current tick` test at the top of 0x16e468).

**End of the stream.** After the last record the exporter writes one more 8-bit delta of 255
and pads with zero bits to a multiple of 4 bytes from the start of the stream. That rule
accounts for every byte of all 4,510 lump clips (**O** in samples). The game has no explicit
end test: it stops because `tick + 255` is beyond the clip's length, which it never reads
past. Two clips break this (`firegate.anm` in `EHUBANIM.LMP`, 599 ticks, and `empty6.anm` in
`FX.LMP`, 359 ticks: one joint, no keys, longer than 255 ticks): their closing delta falls
inside the clip, and once the track time reaches 255 the game decodes padding and then
whatever follows the clip in memory as key records (**I** — follows from the loop; both are
single-joint clips whose joint nothing draws). A native decoder should treat "delta 255
followed only by zero padding up to the end of the stream" as the end.

Largest widths used by key records on the disc: 14 bits for position velocities, 16 for
rotation velocities.

### 2.4 Time, frame rate, looping

- The unit of time is the **tick, 1/60 s**. A track's time is a float; simulation callers
  advance it by the speed argument (1.0 at normal speed) once per simulated frame. **O**
  (0x16d748; cross-check: the 208 lip-sync clips last, in ticks/60, what their voice streams
  last at 24,000 Hz — ratio 0.998 at the median).
- Keys may sit on any tick; there is no fixed key rate. Clip lengths on the disc run from 1
  to 999 ticks (median 92).
- **Looping is not stored in the file.** It is flag 0x0001 of the track that plays the clip
  (`docs/engine.md`, track flags). A looping track wraps with `time −= length`, so the
  period is exactly `length` ticks and tick `length` is the same pose as tick 0 (**O**:
  0x16d748; on the disc, idle and walk/run clips return to their first pose at tick `length`
  to within rounding, death clips do not).
- A non-looping track never passes `length`: with track flag 0x0004 its time is held at
  `length`, otherwise the track is retired there (`docs/engine.md`).

### 2.5 From joint values to matrices

`anim_buildPose` (0x16ed40) blends the tracks into one quaternion and one position per joint
(`docs/engine.md`, "Pose"), then calls two entry points of the VU0 microprogram that the
executable carries at 0x3e5c40 (`.vutext`; 77 instructions loaded at micro address 0). More
exactly, 0x3e5c40 is the DMA / VIF packet that loads the program: the first instruction is
at 0x3e5c50 (`docs/spec/animation.md` 8.3; the earlier wording put the program itself at
0x3e5c40). Entry
2 stores an identity matrix in slot 0 of a matrix stack. Entry 4, once per joint, does:

```
R = rotation matrix of the unit quaternion (x, y, z, w):
      [1-2yy-2zz   2xy-2zw     2xz+2yw ]
      [2xy+2zw     1-2xx-2zz   2yz-2xw ]
      [2xz-2yw     2yz+2xw     1-2xx-2yy]
L = [R | position]                       # 3x4, column vectors: v' = R v + p
W = stack[depth[j]] * L                  # parent first
stack[depth[j] + 1] = W
out[j].rotation    = W.rotation
out[j].translation = W.rotation * bindOffset[j] + W.translation
```

The result is written to the pose buffer as fixed point, 0x18 bytes per joint: three rows
of `s16 r0, r1, r2` (× 4096) and `s16 t` (× 64). `anim_getJointMatrix` (0x16f720) converts a
row set back to floats for game code. **O** (instruction-level reading of the microprogram
and of 0x16f594–0x16f674). The bind offsets and the depth list used for every joint are
those of the top track's clip, whatever clips the other tracks play (0x16f57c;
`docs/spec/animation.md` section 13).

Consequences for a rebuild: joint matrices are in model space; translations are limited to
±512 units by the 16-bit format (a rebuild can keep floats); points given in bind-pose model
space — vertices, and the attach points of a model — are transformed by `out[j]` directly.

### 2.6 Root motion

Root motion is also a property of the track, not of the file (flags 0x0800 and 0x4000).
What the file contributes is joint 0's ordinary keys:

- **Translation (track flag 0x0800).** Joint 0's x and y are taken out of the pose (the pose
  uses 0 for them) and returned to the caller as a displacement. The decoder skips joint 0's
  initial x/y for such a track and lets the position keys accumulate from zero; every
  advance reads `pos + pvel × (t − ptick)` for x and y, adds it (times the track's weight)
  to the output and subtracts it from the stored base. Across a loop wrap the remainder up
  to `length` is taken first. "The track's weight" is two weights, not one: the part up to
  the clip's end is weighted with the track's blend weight before that step's weight
  update, the rest with the weight after it; a track removed by the update gets no second
  part (**executed**, `docs/spec/animation.md` section 5, note 3). So the displacement per step is exactly the change of joint
  0's x/y track; the clip's initial x/y is ignored. z stays in the pose. **O** (0x16e468,
  0x16d748; `animcache_alloc` 0x16e388 zeroes the base).
- **Heading (track flag 0x4000).** The heading of joint 0's quaternion,
  `atan2(2(xy + zw), x² − y² − z² + w²)` as a 16-bit angle, is removed from the pose
  (`quat_stripYaw` 0x16caa8) and its change since the last step is returned. **O**.
- The creature turns the displacement by `facing − 0x4000`, scales it and moves
  (`docs/engine.md`, "Root motion in a creature").

`anim_audio_info.py info` prints joint 0's travel over the clip; a walk cycle of 49 ticks on
the disc travels about 83 units along −y.

### 2.7 Events

Three separate mechanisms.

**(a) The four event slots (+0x14).** `anim_advance` ORs a slot's mask into its return value
on the step in which `time/60` passes the slot's seconds. **In all 4,510 lump clips and all
208 stream clips the slots are zero.** The times and masks are written into the loaded clip
by game code: `creature_setDefEntryParams` (0x118378; 59 callers, the monster constructors)
and its twin at 0x1183d0 take four seconds values and four mask bytes for one animation of a
class's resource table, and a few classes store them inline (`AutoProp_ctor` 0x23c44c,
`AntTrap_ctor` 0x24290c, `SkillGroundPound_cast` 0x2c71ec, `SpellCyclone` 0x2d17c8 /
0x2d1a94, `SpellRoar_ctor` 0x30016c, `SpellBattleCry_ctor` 0x301714). **O**. A rebuild needs
those tables from the code, not from the disc; the list of inline writers above came from a
pattern search and may be incomplete (**U**: player animations were not traced).

**(b) Sound name table (+0x34).** Records of 8 bytes, `u32 nameOffset; u32 0`, ended by a
zero name offset. Names are NUL-terminated sample entry names such as `x.vag`. At load
`anm_bindSounds` looks each name up among the registered samples without regard to case
(`sample_findByName` 0x216798) and stores the sample's address in the second word; a name
that is not loaded leaves 0 and its events are silent. Two reserved names, `*bodyfall*` and
`*blank*`, turn the events that use them into ids −3 and −4. **O**.

**(c) Sound events (+0x38).** Records of 0x1c bytes sorted by time, ended by a record whose
first word is 0x7fffffff.

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | s32 | tick; the event fires on the step in which the track time passes it | **O** 0x16d748 |
| +0x04 | s16 | index into the name table. −1 none; −2 foley callback (`game_animEventFoley` 0x1ebd00 → `sound_playFoley`); −3, −4 reserved names, ignored by the callback | **O** 0x16d558; all four negative values occur in files |
| +0x08 | s8 | selector. 0: always plays. 1…6: of the events that share this tick and this selector, one is chosen at random | **O** 0x16d558; values 0…6 on the disc |
| +0x0a | s8 | pitch in semitones | **O** 0x16d360 |
| +0x0b | s8 | pitch variation: a random offset of up to ± this many semitones, in 1/8 steps | **O** |
| +0x0c | s8 | volume in decibels (the code uses 2^(2·v/12), within 0.4 % of 1 dB per unit) | **O** arithmetic, **I** that the author meant dB |
| +0x0d | s8 | volume variation, ± this many decibels | **O** |
| +0x0e | s8 | start delay: random 0…n ticks | **O** |
| +0x06, +0x09, +0x0f…+0x1b | — | zero | **I** zero in all 13,851 events, no reader found |

Pitch and volume go through one table of 128 floats, 2^((i−64)/12) (0x7b9238, built by
`anim_init`); the volume is then multiplied by the sound group's entry in 0x41bac8 and the
sample is started with `sound_playSample(pitchScale, volume, delaySeconds, sample, position)`.
All random draws use the cosmetic generator. Only the **top** track of an animation state
fires sound events, and only when the caller passes a position. A per-group limiter drops
the events of a step when too many of the group started in the same drawn frame (0x16d9d8,
limits in 0x4f8a28).

251 events in 84 clips have a tick beyond their clip's length (for example a 49-tick walk
with footsteps at ticks 54 and 57, next to a 59-tick variant where the same events fit).
They can never fire (**I** from the wrap logic); they look like leftovers of retimed clips.

### 2.8 Binding a clip to a model

- A clip is fetched by entry name from the object's lump: `res_find(lump, "<name>.anm")`
  (0x17365c). Names come from class code and object properties; `obj_findRoleAnim`
  (0x160928) tries `<property>`, `<name>_<role>.anm`, then `<role>.anm`. **O**.
- Nothing matches joints by name. A model refers to joints **by index** into the pose the
  clip produces: the draw code uploads the pose buffer as is (`anim_emitPose` 0x16f880), and
  a model attach record starts with the joint index it hangs from (`model_getAttachPoint`
  0x1754a0 passes it to `anim_getJointMatrix`). So a clip fits a model when it was exported
  from the same skeleton; the game does not check. **O** for the mechanism. How vertices
  name their joints is in `docs/formats/model-texture.md` (joint index × 4 as a matrix
  address; vertices are stored in rest-pose model space, which agrees with 2.5). That
  document counts 63 matrix slots in the draw program's memory while 810 clips here have 64
  joints; whether a 64th joint is ever referenced by a vertex was not checked (**U**).
- Skeleton data is repeated in every clip. Within a lump, clips with the same joint count
  almost always carry identical depth lists and bind offsets (22 exceptions among 274
  lumps); 58 lumps hold clips for more than one skeleton (a creature and its props).
- Joint counts on the disc: 0 (one test clip) to 64; player characters use 63–64.

### 2.9 Variants

- **Sound sequences.** `sound_playOnObject` / `sound_playAtPos` take a clip pointer and run
  it in one of 32 sequence slots as a one-track animation whose sound events are the point
  (`docs/audio-save.md`). `fx.lmp` holds 394 clips; all but one have a single joint and no
  keys, and 376 of those carry sound events. Sequences are stepped once per displayed
  frame, one tick each.
- **Lip-sync clips.** Stored as entries of a stream file next to the voice line of the same
  name (`<voice>.vag`, `<voice>.anm`), padded to 0x800 bytes; read with `cd_readAsync` and
  passed through `anm_relocate` only (`dialog_startTalkAnim` 0x22fc70). All 208 have 36–64
  joints (143 have 63), no sound tables and zero event slots; they are dense (about 11 key
  records per tick).
- **Partial-body clips.** Joint mask at +0x48; only three files use it: `leverpull.anm`
  and `ohw_parry.anm` (in two lumps).

### 2.10 Not established

- The exporter's choice of key ticks and widths (irrelevant for playback).
- The meaning the game's classes give to event mask bits; that is per class, in the state
  handlers that receive `anim_advance`'s return value.
- Whether any caller plays the two clips with an in-clip closing delta past tick 255.

---

## 3. Audio

### 3.1 Codec

Every sound on the disc is **Sony PS2 ADPCM** ("VAG" coding): 16-byte blocks, each decoding
to 28 signed 16-bit samples.

| Byte | Meaning |
|---|---|
| 0 | high nibble: predictor filter 0…4; low nibble: shift 0…12 |
| 1 | flags: 1 = last block, 2 = inside a loop, 4 = loop start (so 6 = first block of a loop, 3 = last block of a loop, 7 = end marker that is not played) |
| 2…15 | 28 nibbles, low nibble of each byte first; `sample = (nibble << 12 as s16 >> shift) + (c1·s1 + c2·s2 + 32 >> 6)` with (c1, c2) = (0,0), (60,0), (115,−52), (98,−55), (122,−60) |

**O**: the game never decodes ADPCM itself, it hands the blocks to the SPU2; the block size
and 28 samples per block appear in its own arithmetic (`soundSeq_duration` 0x2132f8:
`(bytes >> 4) × 28 / rate`; `dialog_syncMouth` 0x22fdd8: seconds = bytes × 28 / (16 ×
24000)), and every block header on the disc is a legal one (filter ≤ 4, shift ≤ 12, flags
≤ 7; 4,933 samples and 5,351 stream entries checked). The decoder in the tool is the
standard one; its output was checked only statistically (no clipping, smooth waveforms,
left/right correlation), not by ear.

### 3.2 Lump samples (`.vag` entries)

A standard VAG file: 0x30-byte header, then blocks. Header fields are **big endian**.

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | char[4] | `VAGp`. Not checked by the game; 5 entries (in `SEL_EN.LMP`, `SEL_FR.LMP`, `SEL_GE.LMP`) have zeros here | **O** |
| +0x04 | u32 BE | version: 4 in 4,923 entries, 0x20 in 5, 0 in the 5 without magic. Not read | **I** |
| +0x0c | u32 BE | size of the data after the header, in bytes | **O** `sample_register` 0x2130d0; equals entry size − 0x30 in all 4,933 |
| +0x10 | u32 BE | sample rate in Hz | **O** 0x2169c8 |
| +0x20 | char[16] | name given by the conversion tool; **overwritten at load** | **O** |
| +0x30 | — | ADPCM blocks; the first block is all zero | **O** |

Always mono. At load `sample_register` turns the header into the run-time sample record:

| Offset | Run-time meaning |
|---|---|
| +0x20 | base pitch = rate × 4096 / 48000 (integer) |
| +0x24 | address of the data in SPU memory (64-byte aligned, first sample at 0x8040; 0x5000 = a silent block when memory ran out) |
| +0x28 | loop flag: 1 when some block **before the last** has flag value 4 set |
| +0x2c | data size in bytes |

and uploads the blocks to the SPU; the lump then keeps only the first 0x40 bytes of the
entry (`lump_fixupEntry` 0x17153c returns `size − 0x40` as freed). **O**.

- **Looking a sample up.** The lump entry's name (for example `x.vag`) is the sample's name.
  Registered samples sit in a table of {name, record, end address} (0x872bf0, count
  0x4f89e0). A second lump that carries an entry of the same name does not upload again: it
  shares the first one's SPU address and loop flag (**O** 0x2130d0; comparison ignores
  case). Code that wants one sample without a sequence asks the lump for the entry
  (`res_find(lump, "coins.vag")` at 0x1c8830); the entry's data is the sample record that
  `sound_playSample` takes (**I**: the layouts agree, the later call was not followed).
- **Playing.** Pitch register = base pitch × pitch scale, clamped to 0x3fff; envelope
  registers 0xff / 0x1fc0; a one-shot's loop address is set to the silent block at 0x5000 so
  it falls silent after its last block (**O** `sound_playSample` 0x2134e8). In a rebuild:
  play at `rate × pitchScale` Hz, stop after the block flagged 1 (do not play a block
  flagged 7), or loop from the block flagged 6 to the block flagged 3.
- **On the disc.** Rates: 16,000 Hz (1,630 entries), 14,000 (834), 18,000 (739), 20,000
  (600), 22,050 (297), 12,000 (237), 8,000 (87), 24,000 (51), 44,100 (2), three odd ones —
  and **1,000 Hz for 453 entries** (106 names), which are 112–928 bytes long (the median of
  the others is 3 KB) and exist only in that form: placeholders (**I**). 28 entries loop.

### 3.3 Sound sequences

A sound effect that game code starts is almost always a **sequence**: an `.anm` entry (2.9)
whose sound events (2.7c) start samples with per-event pitch, volume, random variation,
delay and random choice. The sequence's sound group (+0x3c) selects a volume from 0x41bac8
and a concurrency limit from 0x4f8a28. Call interface, slots and voices are in
`docs/audio-save.md`. Samples named by a sequence must be registered before the sequence's
lump is fixed up or come from the same lump: `lump_fixup` (0x1717d0) registers all samples
of a lump first and binds sound names in a second pass. **O**.

### 3.4 Streamed audio: `.VAT` files and their directories

A `.VAT` file has **no header and no internal structure**: it is the concatenation of
entries, each padded to a multiple of 0x800 bytes. Its directory is a lump entry:

- `<LEVEL>.VAT` ← entry `dialog.bin` of `<level>.lmp` (`stream_levelDirectory` 0x216860,
  file name from `stream_levelFileName` 0x216820);
- `MOUTH.VAT` ← entry `dialog.bin` of `MOUTH.LMP` (resource reference 0x8723e8).

On the disc the entry is stored once per region as `ntsc_dialog.bin`, `pal_en_dialog.bin`,
`pal_fr_dialog.bin`, `pal_de_dialog.bin`; `lump_fixup` (0x1717d0) strips an `ntsc_` prefix
and removes entries whose name starts with `pal_`. Only the NTSC tables match the `.VAT`
files of this disc (all 117 files match exactly: the directory's closing offset equals the
file size).

**Directory record, 0x50 bytes** (the table ends with a record whose name is empty):

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | char[0x40] | entry name, lower case, NUL padded: `<something>.vag` or `<something>.anm` | **O** `stream_findLevelEntry` 0x210e60 |
| +0x40 | u32 | byte offset in the `.VAT`; always a multiple of 0x800. The entry's length is the next record's offset minus this one; the closing record's offset is the file size | **O** 0x211018, 0x215fc8 |
| +0x44 | u32 | sample rate: 24,000 for audio (48,000 in 23 NTSC entries), 0 for `.anm`. Passed to the driver, which stores and **never uses** it | **O** (`func` case 0x40 at HELLO+0xd28 stores it; `alarm` never reads it) |
| +0x48 | u16 | 1 = stereo, 0 = mono | **O** EE 0x211548 → driver command 0x40 → `alarm` HELLO+0x35c; confirmed by channel correlation in samples |
| +0x4a | s16 | language; an entry in the current language (0x44fddc) is preferred, language 0 is the fallback. All NTSC records are 0 (PAL tables use 0, 3, 4) | **O** 0x210e60 |
| +0x4c | u32 | loop restart position for an entry queued with the loop flag: the stream restarts at `offset + (value & 0x7ffffc00) × 2` | **I** code only (`stream_serviceQueues` 0x211df8); 0 in every record |

**Finding an entry.** By exact name, case sensitive; the whole table is walked and the
**last** match wins (0x210e60, 0x210f38); 108 records in the NTSC level directories repeat
an earlier name of the same table. `stream_queueRandomByPrefix` (0x211190) instead picks at
random among all names that start with a given prefix.

**Entry data.** Raw ADPCM blocks in the same shape a VAG file's body has — a zero block,
data, a block flagged 1, an all-zero block flagged 7, zero padding — but **the flags do not
matter**: the driver overwrites the flag byte of every block before it reaches the SPU and
plays an entry for exactly its directory length. **O** (HELLO+0x5f4–0x610).

- **Mono** (flag 0): the blocks in order.
- **Stereo** (flag 1): alternating **0x400-byte chunks, left then right** (64 blocks = 1,792
  samples per chunk). **O**: for a stereo stream the driver gives the left voice the first
  half and the right voice the second half of each 0x800-byte transfer (loop addresses set
  at HELLO+0x648–0x6a8); in samples the two de-interleaved channels correlate at chunk size
  0x400 and at no other size.
- **Sample rate.** The driver sets the pitch of all five stream voices to 0x7fe once, at
  start-up (`streamPitch` in HELLO `.data`; HELLO+0x1018), which is 48000 × 2046 / 4096 =
  **23,976.6 Hz**, and never changes it. The game's own arithmetic assumes **24,000 Hz**
  (0x22fdd8). A rebuild should play every stream entry at 24,000 Hz (or 23,976.6 Hz to match
  the console to the cent) whatever the directory says. 16 `mx_env_*` entries in level
  files (and the 7 narration entries of the missing `ACTINTRO.VAT`) are marked 48,000;
  whether they are mislabelled or really play at half their authored speed on the console
  is **U** — it can only be heard.
- Lengths: an entry lasts `bytes / 16 × 28 / 24000` seconds, half that when stereo.

**Naming on the disc** (NTSC, level directories): `ss_*_l.vag` ambience one-shots (2,518,
stereo), `mx_*_l.vag` music (96, stereo), `amb_*_l.vag` ambience (96, **mono**), voice lines
(221, mono) with their lip-sync `.anm` (208), and `cs_*_l.vag` narration (7, stereo, in the
directory of `actintro.lmp`, whose `.VAT` is not on this disc). `MOUTH.VAT`: 2,406 player
voice lines (mono) named by a three-letter voice code and a three-digit line number, most
with a variant letter after the number; 13 music tracks and the intro soundtrack (stereo).
The `_l` suffix does not imply stereo; use the flag.

**How the game plays them.** Three streams, each with an 8-entry queue
(`docs/audio-save.md`); the driver gives streams 0 and 2 two voices each (stereo) and
stream 1 one voice (mono) — `voicesStream` = {0, 0, 1, 2, 2}, SPU voices 19–23 of core 1.

| Stream | Used for | Evidence |
|---|---|---|
| 0 | intro movie soundtrack `porko_l.vag` (queued held, released when the movie is ready) | **O** `splash_introMovie` 0x321788; other users not traced |
| 1 | all speech: cutscene and NPC dialog lines, script `startAudio`, player voice lines | **O** 0x196788, 0x22ec9c, 0x146ba4, `player_voice` 0x1b7ba8 |
| 2 | music, and the ambience one-shots of `ambient.bin` when no music entry is active or queued | **O** `music_playGlobal` 0x2110e0, `ambient_update` 0x2149d0 |

A mono entry on a stereo stream is duplicated to both voices; a stereo entry on stream 1
would be played as one channel with the chunks in file order (**I**; not seen in the data).

Queue entry flags as far as read (**O** in `stream_startQueued` 0x211548 and
`stream_serviceQueues` 0x211df8 unless noted): 1 = loop (restart when the entry ends),
2 = fade out and stop what is playing before this entry starts (an entry with only this
flag and no file is a stop), 4 = wait until the current entry has ended, 8 = hold until
released, 0x20 = tested by `player_voice` and `ambient_update` to keep quiet while such an
entry plays, 0x80 = set on ambience one-shots. 0x40 and 0x100 are passed by callers and were
not traced (**U**). A non-looping entry lets the service routine read the next queued file
behind it, so consecutive entries play without a gap.

**Driver interface** (`HELLO.IRX`, SIF RPC server 0x163a5; **O** in `func` HELLO+0x9d8):

| Command | Arguments | Effect |
|---|---|---|
| 0x20 | — | init: voice volumes 0x3fff, pitch 0x7fe, envelope 0xff / 0x1fc0, a 0x1000-byte buffer per stream in SPU memory at 0x5010 + stream × 0x1000 filled with silence, key on, start a timer (first after 10 ms, then every 6 ms) |
| 0x30 | stream, buffer address, size | reset a stream and give it its ring buffer in IOP memory (sizes 0x19000, 0x1e000, 0x40000 from 0x4f89f0) |
| 0x40 | stream, bytes added, rate, s16 stereo, s16 first-chunk flag | account for data the EE has read into the ring buffer (queue of 32) |
| 0x50 | — | status, four words per stream: write position, read position, current volume, bytes played since the entry started |
| 0x60 | stream | stop: drop buffered data |
| 0x70 | stream, volume | target volume (ramped by the timer) |
| 0x80 | stereo on/off, three channel volumes | output mode and per-stream volume scale |
| 0x10, 0x90, 0xa0–0xc0 | | read an SPU parameter; load a module; stop / restart the timer |

The timer (`alarm`) refills, for each stream, the half of the 0x1000-byte SPU buffer that
the voice is not playing: 0x800 bytes of mono, or 0x400 + 0x400 of stereo, or the same
0x400 twice for a mono entry on a stereo stream; silence when the ring buffer is empty.

### 3.5 Other audio files

- **`PORKO.VAG`** (749,568 bytes) and **`MAINMENU.VA1`** (2,555,904 bytes): headerless
  stereo stream data with 0x400 interleave, 27 s and 93 s at 24 kHz. `MAINMENU.VA1` has loop
  flags already set per channel (6 … 2 … 3). No string in the executable names either file
  and `PORKO.VAG` is not the `porko_l.vag` of `MOUTH.VAT`: unreferenced leftovers (**I**).
- **`NETGUI/EFF.HD` + `EFF.BD`**: a standard Sony sample bank (IECS chunks `Vers`, `Head`,
  `Vagi`, `Smpl`, `Sset`, `Prog`): four 44,100 Hz ADPCM samples for the network setup
  program. The `Vagi` chunk gives each sample's offset in the `.BD`, its rate and a loop
  byte. Not used by `SLUS_209.73` (**I**: no reference; its IOP module list has no
  `modhsyn` / `modmidi`).

### 3.6 Not established

- Whether the pitch of 0x7fe instead of 0x800 is deliberate.
- Queue flags 0x40 and 0x100; every user of stream 0.
- The loop restart field (+0x4c) was never seen non-zero, so its unit is read from code only.
- `game_loadLevel` (0x1e55c0) starts as level music the first directory entry whose name
  contains `enttag`; no NTSC directory has such a name, so that path does nothing here.

---

## 4. Dialog files

### 4.1 `*_dialog.bin` is not dialog

`docs/FORMATS.md` lists `*_dialog.bin` with the dialog files. It is the **stream directory**
of section 3.4 and holds no text.

### 4.2 `.dbin` — dialog nodes

An array of fixed 0x448-byte **nodes**; the first byte of the file is the node count
(`s8`, equal to size / 0x448 in all 52 files). Strings are NUL-padded ASCII.

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | s8 | node count (first node only; 0 in the others) | **O** `dialog_onMsg` 0x22ee2c; the cutscene loader divides the entry size instead (`cut_loadDialog` 0x1964d4) |
| +0x01 | char[0x20] | condition: name of a level-script entry point. An NPC conversation opens at the first node whose condition is not empty and returns non-zero, else at node 0 | **O** 0x22ee2c |
| +0x21 | char[0x10] | key of the text in the string tables, exactly as `text_lookup` takes it (the files store it with its double quotes) | **O** `dialog_showNode` 0x230c74 |
| +0x31 | char[0x10] | voice: base name of the stream entries `<voice>.vag` and `<voice>.anm` in the level's `.VAT` | **O** `dialog_queueLineAudio` 0x22ec9c |
| +0x41 | char[0x13] | name of the speaking object (cutscenes; set in 7 of 300 nodes) | **O** `docs/engine.md`, "Dialog lines and voice" |
| +0x54 | s32 | number of choices, 0…12 (0…8 on the disc) | **O** 0x230c74 |
| +0x58 | 12 × choice | 0x54 bytes each | |

Choice:

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | char[0x10] | text key of the choice | **I** position and use fit; the draw code that looks it up was not read |
| +0x10 | char[0x20] | condition script; the choice is offered when this is empty or returns non-zero | **O** 0x230c74 |
| +0x30 | char[0x20] | action script, run when the choice is taken (empty = none) | **O** 0x22ee2c case 1 |
| +0x50 | s32 | next node, −1 = end the conversation | **O** |

Two users:

- **NPC conversation.** `<npc>.dbin` in `<level>.lmp` (script `startDialog`); the node graph
  is walked as above.
- **Cutscene.** `<cutscene>.dbin`; the nodes are simply lines in order, advanced by dialog
  keys of the `.cut` timeline (key type 0 = next line). Conditions and choices are unused.

### 4.3 How a voice line is tied to its text

There is no naming rule between text keys and audio. Each node names both: the text key at
+0x21 and the voice at +0x31. Showing a node queues `<voice>.vag` on stream 1 with flags
0x28 (held, then released when the line starts) and starts an asynchronous read of
`<voice>.anm` from the same `.VAT` for the speaker's mouth. When the directory has no such
entry the speaker falls back to a generic talk animation (`docs/engine.md` for the cutscene
path; the NPC path makes the same lookup at 0x22ec9c, its fallback was not followed). While
the line plays, the game compares the animation time with the stream position (bytes × 28
/ (16 × 24000) seconds) and nudges the animation (`dialog_syncMouth` 0x22fdd8; FINDINGS D8
for the cutscene twin). **O**.

Player voice lines are not in `.dbin` files: `player_voice` (0x1b7ba8) either formats an
exact name `<voice code><number, 3 digits>.vag` or asks for a random entry among the names
that start with a prefix (which is how lettered variants of a line are chosen), and plays
it from `MOUTH.VAT` on stream 1 with flags 0x24. **O**.

### 4.4 `ambient.bin`

Plain text (`game_loadLevel` copies it into a 5,120-byte buffer), parsed by `ambient_parse`
(0x214eb0) after lower-casing.
Lines starting with `;` are comments. A **group** is:

```
<min>-<max>          seconds between one-shots (or a single number)
<volume group>       optional: index into the group volume table 0x41bac8
<attenuation>        optional: random attenuation of up to this many decibels
<name>.vag           one or more stream entry names (up to 16)
```

Up to 16 groups. Each group counts down a random time between min and max; when it expires
and stream 2 has no music entry active or queued, one name that has not yet been played in
the current round is queued on stream 2 (`ambient_update` 0x2149d0). Draws use the cosmetic
generator. **O**. Some files have a stray control character at the end of a number line;
the game's `sscanf` ignores it and so does the tool.

---

## 5. Corrections to earlier documents

| Document | Statement | What the code and files show |
|---|---|---|
| `docs/FORMATS.md` | `*_dialog.bin` is dialog, "indexed by cutscene dialog keys" | it is the directory of the level's `.VAT` stream file (3.4); dialog is `.dbin` (4.2) |
| `docs/engine.md`, `.anm` header | +0x0c, +0x10: use unknown | bind offsets and depth list (2.1, 2.2) |
| `docs/engine.md`, `.anm` header and `anim_advance` step 1 | "the animation file and the caller's state handler define" the event bits | the file's four slots are zero in every clip; constructors write them at run time (2.7a) |
| `docs/engine.md`, `.anm` header | sound event +0xa…+0xe "volume/pitch/delay jitter amounts" | +0x0a pitch, +0x0b pitch variation, +0x0c volume, +0x0d volume variation, +0x0e delay (2.7c) |
| `docs/audio-save.md`, Streams | "three driver parameters" in a queue entry; status "word 3 is the position" | rate (unused by the driver), stereo flag, loop restart; status words are write position, read position, volume, bytes played (3.4) |
| `docs/audio-save.md` and `symbols/audio-save.tsv` | stream 0 = ambience (inferred) | ambience one-shots go to stream 2; stream 0 was seen only for the intro soundtrack (3.4) |
| `docs/audio-save.md` | `sound_release` (0x213438) lets a sequence "play out"; slot +0x3c "release requested" | for a sequence handle the function sets slot +0x3c, clears track flag 4 and sets flag 1 (loop); `soundSeq_updateAll` then skips the end test and restarts the sequence each time its duration (clip +0x40) has passed. It makes the sequence repeat. Worth a second reading by whoever owns that area; I did not trace its six callers |

Proposed rows for the table in `docs/FORMATS.md` (replacing the two rows that mention
dialog, animation and audio; models and textures have their own document):

| Format | Status | Tool |
|---|---|---|
| `.anm` animation and sound sequence | understood: header, skeleton, key stream, sound tables; the four event slots are filled by code, not by the file — see [formats/anim-audio.md](formats/anim-audio.md) | `tools/anim_audio_info.py` |
| audio: `.vag` lump samples, `.VAT` streams with their `*dialog.bin` directory | understood (PS2 ADPCM; streams are 24 kHz mono or 0x400-interleaved stereo) | `tools/anim_audio_info.py` |
| `.dbin` dialog nodes, `ambient.bin` | understood | `tools/anim_audio_info.py` |

No patches and no ledger rows are proposed: nothing here changes shared game state.

---

## 6. What a native player needs, and in what order

Each step is usable on its own and is checked by the tool's output on real files.

1. **Containers.** ISO9660 → `.GOB` → `.LMP` (`tools/gob.py`); region prefix handling
   (`ntsc_` entries lose their prefix, `pal_*` entries are ignored).
2. **ADPCM decoder** (3.1): 16-byte blocks to 16-bit PCM. Everything audible depends on it;
   about 20 lines.
3. **Lump samples** (3.2): parse the 0x30-byte header, decode once at load into a PCM buffer
   keyed by lower-cased entry name; remember rate and loop points. First name registered
   wins. Mixer: at least 43 one-shot/looping voices with per-voice pitch and stereo volume.
4. **Streams** (3.4): load `dialog.bin` of `<level>.lmp` and of `MOUTH.LMP`; decode entries
   incrementally from the `.VAT` at 24,000 Hz, mono or 0x400-interleaved stereo; three
   stream channels with an 8-entry queue each and the flags listed. This gives music, voice
   and ambience without touching animation. `ambient.bin` (4.4) is a small addition.
5. **`.anm` decoder** (2.1–2.4): header, skeleton, forward key decoder with per-joint base /
   velocity / tick state, rewind by restarting. Unit test: loop clips must return to their
   first pose at `length`.
6. **Pose** (2.5): quaternion/position per joint → model-space matrices through the depth
   stack, bind offset applied. Needed by rendering and by gameplay (attach points). Use
   floats; the console's 16-bit packing is not required.
7. **Tracks and blending**: the run-time layer of `docs/engine.md` (weights, layers, flags,
   `anim_advance`), with root motion (2.6). This is simulation state: for online play it
   must reproduce the original arithmetic, including the float tick time.
8. **Sound events and sequences** (2.7b–c, 3.3): bind names to samples after a lump's
   samples are loaded; fire events from the top track; 32 sequence slots; group volumes and
   limits; foley callback for id −2.
9. **Event-slot tables** (2.7a): lift the (seconds, mask) quadruples from the 59 callers of
   0x118378 and the inline writers into data, keyed by class and animation. Combat timing
   depends on them and they are not on the disc.
10. **Dialog** (4.2–4.3): `.dbin` nodes, voice on stream 1 with the held start, lip-sync
    clip from the `.VAT`, mouth sync against the stream position.

Not needed: the IOP driver's ring-buffer protocol, SPU addresses, the 0x7fe pitch, the
pose buffer's fixed-point layout, the unreferenced files of 3.5.

---

## 7. The tool and how it was tested

```
python3 -I -B tools/anim_audio_info.py info  SOURCE [--events] [--keys N] [--dir SOURCE --entry NAME]
python3 -I -B tools/anim_audio_info.py list  CONTAINER
python3 -I -B tools/anim_audio_info.py csv   SOURCE OUT.csv [--keys] [--step TICKS] [--dir SOURCE --entry NAME]
python3 -I -B tools/anim_audio_info.py wav   SOURCE OUT.wav [--dir SOURCE --entry NAME] [--raw mono|stereo] [--rate HZ] [--bd FILE --index N]
python3 -I -B tools/anim_audio_info.py scan  PATH...
```

`SOURCE` is a file or a path into containers with `::` between steps, for example
`game.iso::/BG/DATA/SKELETON.LMP::1_walk.anm` or
`DRUNARE.GOB::drunare.lmp::ntsc_dialog.bin`. An entry of a `.VAT` (a voice line, or a
lip-sync clip for `info` and `csv`) is named with `--dir <its directory> --entry <name>`.
Standard library only. A file of a type it does not cover, or one that fails a structural
check, ends with `error: …` and exit status 2.

- `info` prints the structure: for a clip the header, skeleton with parents and bind
  positions, key counts, sound names and events; for a sample its header, rate, length and
  loop; for a directory its entries; nodes of a `.dbin`; groups of an `ambient.bin`.
- `csv` writes either the sampled tracks (per tick and joint: local position, local
  quaternion x y z w, model-space joint origin) or, with `--keys`, the raw key records.
- `wav` decodes a lump sample, a stream entry (`--dir` + `--entry`), headerless stream data
  (`--raw`) or a bank sample (`--bd`). Stream entries are written at 24,000 Hz.
- `scan` parses everything it recognises under the given paths (directories, lumps, `.GOB`s,
  a disc image) and counts successes and failures. Given a disc image it pairs every `.VAT`
  with its directory and checks each entry.

Result of `scan` on the whole disc image (13 seconds):

| Kind | Parsed | Failed |
|---|---|---|
| `.anm` in lumps | 4,510 | 0 |
| `.anm` inside stream files | 208 | 0 |
| `.vag` samples | 4,933 | 0 |
| stream directories (all regions) | 482 | 0 |
| `.VAT` files matched with their directory | 117 | 0 |
| stream audio entries (every block header checked) | 5,351 | 0 |
| headerless stream files without a directory | 2 | 0 |
| `.dbin` | 52 | 0 |
| `ambient.bin` | 93 | 0 |
| IECS `.hd` | 1 | 0 |
| **total** | **15,749** | **0** |

6,494 other files and entries (models, textures, worlds, scripts, …) are outside its scope
and are counted as not examined. "Parsed" means every structural check passed: for a clip,
that offsets and the depth list are sane, the whole key stream decodes inside its section
and ends with the closing delta, and the sound tables are terminated and consistent; for
audio, that sizes agree and every block header is legal. (That the closing rule accounts
for every byte of the stream was checked separately for the 4,510 lump clips; `info`
prints a note when it does not.)

Also checked: six WAV decodes (lump sample, sample without the `VAGp` magic, mono voice,
stereo ambience, raw stereo, bank sample) and three CSV dumps into a scratch directory;
4,000 deliberately damaged inputs (flipped bytes, truncation, random data, corrupted header
words) across all parsers: every one was either accepted as structurally valid or rejected
with a message, none crashed. Not checked: nobody listened to the output, and no decoded pose was compared
with the game on screen.
