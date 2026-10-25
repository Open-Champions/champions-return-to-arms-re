# Engine layer (0x160000–0x1a0000)

The Snowblind engine code that the game classes sit on: math, animation, the lump/resource
loader, controllers, model and text drawing, the world (terrain, water, pathfinding, camera),
particles, cutscenes, the task list and the frame loop helpers. 546 functions, 255 KB.

Everything here was read from the decompile and disassembly of `SLUS_209.73`; nothing was run
when it was written. Since then the math library, the animation step and pose, and the pad
code have been executed function by function in `tools/ee_emu.py` (`docs/spec/core.md`,
`docs/spec/animation.md`; results folded in here are marked **executed**), and the project
has a live game: what was run on it is listed in `FINDINGS.md`, "Run on the live game" (rows
V1–V23) and `docs/issues/live-rig.md` — in the Play! emulator, not on a PlayStation 2 and not
in PCSX2. Of this document only the names and call rates of a few functions
(`pad_readAll`, `pad_readPort`, `pad_apply`, `gfx_endFrame`, `engine_frameStep`), the held
and stick fields of a pad, and the cosmetic seed following the frame counter while a
cutscene runs were checked there; the rest was not re-checked on the live game. No test patch has
been run on a live game.
Each claim is **Observed** unless it says *Inferred* or *Unknown*. Names are the ones in
`symbols/engine.tsv`, `names.tsv` and the other area files.

How far the reading went: the math library, animation core, resource lookup, pads, terrain
queries, pathfinder, cutscene runtime and task list were read function by function. Model
drawing, textures, text, world drawing, particles and the frame/GS code were only skimmed
(entry points identified from callers, strings and the first lines of each function). The
section "Not covered" lists what was not opened at all.

## Module map

| Range | Module | Main entry points |
|---|---|---|
| 0x1605b8–0x1622ff | object helpers that landed here: role animation lookup, `ParticleMorphEffect`, radius damage, arc query, `StrongStancePhantom`, a static initialiser for gold-pile particles | `obj_findRoleAnim`, `world_damageInRadius`, `world_collectObjectsInArc` |
| 0x162310–0x166fff | math | `math_cos16`, `math_sin16`, `math_atan2_16`, `mat34_*`, `quat_*` |
| 0x167008–0x1685ef | rigid-body helpers for the physics props | `rigidbody_init`, `rigidbody_integrate` |
| 0x16865c–0x16a88b | automap (grid at 0x4044f0, icons) | `automap_revealAll`; 0x168cac is the big map routine (not read) |
| 0x16a88c–0x16b7ef | static constructors of the Skill tables (belongs with the skills area) | — |
| 0x16b7f0–0x16ca87 | sorted draw entries, GS/DMA setup | `gfx_addSortedPacket` |
| 0x16caa8–0x1711c7 | animation | `anim_start`, `anim_advance`, `anim_getJointMatrix` |
| 0x1711e8–0x173e9f | lumps, CD files, string table | `res_find`, `lump_load`, `text_lookup` |
| 0x173ea8–0x174e77 | controllers | `pad_apply`, `pad_readPort`, `pad_rumble` |
| 0x174e78–0x179b07 | model drawing and model queries | `model_draw`, `model_getAttachPoint` |
| 0x179b08–0x17ff9f | texture cache, VRAM pages, 2D sprites and frames, assert | `ui_drawSprite`, `ui_drawRect`, `dbg_assertFail` |
| 0x17ffb0–0x181d2f | fonts and text | `text_begin` … `text_end` |
| 0x181d30–0x182c97 | world file setup, moving world pieces | `world_movePiece`, `world_setPieceCollision` |
| 0x182f28–0x183e3f | terrain height queries | `terrain_height`, `terrain_heightBelow` |
| 0x183e40–0x185447 | pathfinder | `path_search`, `path_service`, `path_request*` |
| 0x185448–0x18617b | terrain sweep test and two routines that nothing calls (0x185448, 0x1857e4; the earlier version said "unread" — open question 6) | `terrain_sweepCircle` |
| 0x18617c–0x18a51f | camera projection, frustum, world and water drawing, water queries | `camera_setView`, `world_draw`, `water_disturb` |
| 0x18a520–0x18b6ff | camera focus, ray casts, level-start reset | `camera_updateFocus`, `terrain_raycast`, `world_raycast` |
| 0x18b810–0x18c22f | effects drawn with the world (not read; role *Inferred* from callers), static init | — |
| 0x18c230–0x18e627 | recall action and the pause menu | `recall_execute`, `pauseMenu_task` |
| 0x18e628–0x196087 | particles, glow sprites, trails, beams | `particle_spawn`, `glow_add`, `trail_addPoint` |
| 0x196344–0x19b673 | cutscenes | `cut_start`, `cut_runFrame`, `cut_advance`, `cut_execKey`, `cut_evalCamera` |
| 0x19b694–0x19e49f | screen effects, IOP boot, GS frame begin/end, engine init | `engine_init`, `gfx_beginFrame`, `gfx_endFrame` |
| 0x19e4a0–0x19e853 | task list | `task_add`, `task_remove`, `tasks_call` |
| 0x19e854–0x19ee0f | wide-string helpers | `wstr_format` |
| 0x19ee10–0x19ffff | floor decals | `decal_add` |

The brief described 0x18c230–0x18e334 as "dialog state". It is the pause menu and the recall
potion. NPC conversations (`dialog_start`, `dialog_isOpen`) are in the audio-save range at
0x22ee2c–0x2305ff. The only dialog code in this range is cutscene dialog (below).

## Conventions

- Angles are signed 16-bit, 65536 to a full turn. `math_cos16` (0x166630) and `math_sin16`
  (0x1666e0) take them; `math_atan2_16` (0x166798) returns one. The script built-ins
  `cos1000` and `sin1000` call the first two, which is how they are told apart.
- `mat3` is 9 floats, `mat34` is a `mat3` followed by a translation (12 floats), `mat4` is 16.
  A vector is transformed as `v.x*m[0..2] + v.y*m[3..5] + v.z*m[6..8] (+ m[9..11])`
  (`mat34_transformPoint`, 0x1660a0).
- Time inside animation is in ticks (1/60 s). Cutscene key times are seconds.
- World units: terrain samples are 4 units apart, path cells 24, terrain grid cells 160,
  object grid cells 256.

## Math (0x162310–0x166fff)

Small leaf functions; the symbol file lists all of them with argument order. The ones game
code calls most:

| Address | Name | What it does |
|---|---|---|
| 0x166630 / 0x1666e0 | `math_cos16` / `math_sin16` | polynomial on the half angle, not a table; 245 functions call the cosine (507 sites) and 282 call the sine (604 sites). Neither ever returns 0: `sin16(0)` and the other quarter-turn values are ±2⁻²² (`docs/spec/core.md` section 4, `docs/spec/trig16.md`, executed over all 65,536 angles) |
| 0x166798 | `math_atan2_16` | `atan2f` × 65536/2π |
| 0x166c18 | `angle_approach` | turn `current` toward `target` by `rate × |difference|`, clamped to [min, max] |
| 0x166bc8 | `angle_turnDir` | which way to turn, optional absolute difference |
| 0x163b30 | `mat34_setPosRotZ` | world matrix from position and facing |
| 0x163000 | `mat34_rotateAxis` | rotate in place about X, Y or Z |
| 0x162808 / 0x162698 | `mat34_mul` / `mat4_mulMat34` | matrix products |
| 0x1660a0 / 0x166158 | `mat34_transformPoint` / `mat34_rotateVec` | apply a matrix |
| 0x1658f0 | `math_hermite` | cubic Hermite; with tangents 0 it is the smoothstep the camera and blend code use |
| 0x166480, 0x166550, 0x1668b8, 0x164330 | `quat_mul`, `quat_normalize`, `mat3_fromQuat`, `quat_fromMat3` | quaternions are x, y, z, w |
| 0x166b48 | `math_noise` | smooth noise from a 256-entry table; **the table is different on every machine** (see Per-machine state) |

The block 0x167008–0x1685ef is a small rigid-body integrator used by the physics props in the
objects area (`PhProp_initPhysics` 0x155110, `PushPhysicsProp`). Body layout as far as read:
+0x00 inverse mass, +0x04 inverse inertia (3 floats), +0x10 position, +0x1c orientation
quaternion, +0x2c linear momentum (`rigidbody_pointVelocity` multiplies it by the inverse
mass), +0x38 angular momentum (*Inferred* by symmetry), +0x44 rotation matrix, +0x8c angular
velocity.

## Animation (0x16caa8–0x1711c7)

### State structure

Every animated thing embeds an animation state. In a creature it is at object+0x114
(so the track count is the byte at +0x118 and the first track's time is at +0x134).

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | ptr | pose buffer currently holding this state's blended pose, or 0 | cleared at the top of `anim_advance`; set by `anim_buildPose` |
| +0x04 | s8 | number of active tracks | every push/start function |
| +0x05 | s8 | capacity (tracks) | compared before pushing |
| +0x06 | u16 | union of the flags of all tracks alive at the last advance, plus status bits 0x80 and 0x400 | written at the end of `anim_advance` (0x16d748); start functions OR the new flags in |
| +0x08 | track[] | 0x20 bytes per track, index 0 is the bottom layer | |

Track (0x20 bytes):

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | ptr | `.anm` data |
| +0x04 | ptr | decoder slot (lazy, from `animcache_alloc`), or 0 |
| +0x08 | float | weight |
| +0x0c | float | weight change per tick (blend-in rate) |
| +0x10 | float | second weight ("life"); the effective weight is min(weight, life) |
| +0x14 | float | life change per tick (0 or negative) |
| +0x18 | float | time in ticks |
| +0x1c | u16 | flags |
| +0x1e | s16 | index of the next sound event |

Track flags (all read in `anim_advance` or `anim_buildPose`):

| Bit | Meaning |
|---|---|
| 0x0001 | loop |
| 0x0002 | when this track is fully blended in, delete every track below it except those with 0x1000 |
| 0x0004 | report the end: sets status 0x80 in state+6, and 0x400 as well if it is the top track |
| 0x0020 | used by the cutscene to mark the speaker's talk track (`anim_findTrackByFlag(…, 0x20)`); the engine itself does not test it |
| 0x0040 | ignore the speed argument (weights too). The earlier version said "advance exactly one tick": the step is 0.99999994 (pattern 0x3f7fffff, 0x16d8cc), the same constant the speed is multiplied by, not 1.0 (**executed**, `docs/spec/animation.md` section 5) |
| 0x0100 | ease the weight with smoothstep when blending the pose |
| 0x0200 | keep the track after its life reached 0 |
| 0x0800 | root motion: joint 0's x/y translation is removed from the pose and returned as a delta |
| 0x1000 | persistent: survives the 0x0002 purge and `anim_dropNonPersistent` |
| 0x2000 | paused: time does not advance |
| 0x4000 | root yaw: joint 0's rotation about Z is removed from the pose and returned as an angle delta |

### `.anm` header

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | int | joint count | loop bound in `animtrack_decode` |
| +0x04 | int | length in ticks | compared with track time everywhere |
| +0x08 | ptr | bit-packed key stream (16-bit words) | `animtrack_decode` (0x16e468) |
| +0x0c, +0x10 | ptr | relocated by `anm_relocate`. Use, *Unknown* in the earlier version, found by `docs/formats/anim-audio.md` (2.1, 2.2): +0x0c points to the bind offsets (8 bytes per joint: s16 x, y, z, 0 in units of 1/64), +0x10 to the depth list (one byte per joint); both are read at the end of `anim_buildPose` and fed to the VU0 pose program | 0x1707b8; 0x16f58c, 0x16f590 |
| +0x14 … +0x33 | 4 × {float seconds; u8 mask; pad} | the four **event slots**. They are zero in every clip on the disc; game code fills them after loading — `creature_setDefEntryParams` 0x118378 (59 callers, the monster constructors), its twin `anm_setEventSlots` 0x1183d0, and a few inline writers such as `AutoProp_ctor` 0x23c44c (`docs/formats/anim-audio.md` 2.7) | first loop of `anim_advance` |
| +0x34 | ptr | sound name table: {name, sample} pairs ending with 0 | `anm_bindSounds` (0x16cc38) |
| +0x38 | ptr | sound events, 0x1c bytes each, ended by time 0x7fffffff: +0 time in ticks, +4 s16 sound index (negative = special id), +8 group selector, +0xa…+0xe volume/pitch/delay jitter amounts — byte by byte, from `docs/formats/anim-audio.md` 2.7c (read in `animsound_play` 0x16d360): +0x0a pitch in semitones, +0x0b pitch variation, +0x0c volume, +0x0d volume variation, +0x0e start delay in ticks; so +0x0a and +0x0c are base values, not jitter amounts | `animsound_fireRange`, `animsound_play`; the field meanings were *Inferred* here and are Observed there |
| +0x3c | u8 | sound throttle group | `anim_advance` 0x16d9d8 |
| +0x3d | u8 | data version; `anm_bindSounds` zeroes the jitter fields when 0 | |
| +0x48 | u64 | joint mask: a set bit means the joint is not driven by this file. Non-zero marks a partial-body animation, which does not use up blend weight | `anim_buildPose` |

The key stream is delta coded with per-joint bit widths; a decoder slot (LRU pool, head at
`g_animCacheLruHead` 0x791e90) holds, per joint (0x3c bytes from slot+0x1c): the key tick for
position and rotation (two s16), position, position velocity, quaternion, quaternion velocity.
Slot+0x18 is the last root yaw, slot+0x14 points back at the owning track.
`animcache_alloc` (0x16e388) never steals a slot whose owner has flag 0x0800 or 0x4000, because
for those tracks the slot holds the root-motion base and is simulation state, not a cache.

### Starting, stopping, blending

| Function | Effect |
|---|---|
| `anim_push` (0x170838) | append at weight 1, no blending; ignored when the state is full |
| `anim_start` (0x16cfe0) | append with weight 0 rising by 1/(blendIn×60) per tick (the first track of an empty state reaches full weight on the next tick). When the state is full the top track is replaced. The rule in brackets is wider than "empty state": the blend time is forced to 0 whenever the track goes into cell 0, which is also the case when a full state of capacity 1 has its only track replaced (**executed**, `docs/spec/animation.md` section 4) |
| `anim_startBlendInOut` (0x16ceb0) | as `anim_start`, and life = length × r falling by r = 1/(blendOut×60) per tick, so the track fades out over the last `blendOut` seconds and is gone exactly at its end. "As `anim_start`" does not include the cell-0 rule: here the blend-in time is **not** forced to 0 in cell 0 (**executed**, same place) |
| `anim_pushChained` (0x170938) | append at weight 1 with start time = previous track's time − previous length + 2 (negative: it waits) |
| `anim_pushWithWeights` (0x1708c0) | append with explicit weight, rate, life, life rate |
| `anim_stop` (0x16d1a0) | remove the tracks playing a given file: at once, or by giving them a negative weight rate |
| `anim_clear` (0x1707b0), `anim_dropNonPersistent` (0x16cb50) | drop all / all non-persistent tracks |
| `anim_jumpTopToEnd` (0x170bc8), `anim_snapTopToEnd` (0x170c80) | put the top track on its last frame |
| `anim_syncToSimFrame` (0x1709f8) | time = `g_simFrame` mod length for every track |
| `anim_randomizeTopTime` (0x16d0b8) | time = random fraction of the length, **from the cosmetic generator** |

A track at time < 0 is skipped by the advance (it only counts up), which is how chained and
delayed tracks wait.

### `anim_advance` (0x16d748)

`eventBits = anim_advance(speed, state, soundPos, rootDelta, yawDelta)`; called once per tick
per creature by `Creature_stepAnim` (0x1162b0) and `Player_animStep` (0x1b9520), and once per
drawn frame for world scenery by `world_draw` (0x189910).

Per call, from the top track down:

1. **Events.** For each of the four header slots, if `time/60 ≤ slot.seconds < (time+step)/60`
   the slot's mask byte is OR-ed into the return value. As the code computes it the window is
   `time×(1/60) ≤ slot.seconds < time×(1/60) + step×(1/60)` — two products and a sum, not one
   sum and a division, which matters in the last bit — with `step` = `speed × 0.99999994`
   also for a paused track and for a track with flag 0x40, although those do not advance by
   `step` (0x16d838–0x16d888; **executed**, `docs/spec/animation.md` section 5 and 7.3).
   Events of every track are merged, also
   those of tracks that are fading out. The engine attaches no meaning to the bits. The
   earlier version said "the animation file and the caller's state handler define them";
   the file defines none — its four slots are zero in every clip, and the constructors
   write the times and masks at run time (0x118378, 0x1183d0 and a few inline stores;
   `docs/formats/anim-audio.md` 2.7). What each bit means is still per class
   (`docs/monsters-2.md` gives them class by class).
2. **Time.** Unless paused, time += `speed × 0.99999994` (or one tick with flag 0x40 — "one
   tick" there is 0.99999994 as well, not 1.0: 0x16d8cc loads the same constant).
3. **Sounds** (only when `soundPos` is non-zero and only for the top track): sound events whose
   time was passed are played through `animsound_fireRange`. A per-group limiter keyed on the
   low byte of `g_drawFrame` skips them when too many started in the same rendered frame.
   Special ids below −1 go to `g_animSoundCallback` (set to `game_animEventFoley`, which only
   plays sounds).
4. **End of file.** Looping tracks wrap (root motion and root yaw are carried across the
   wrap). Non-looping tracks get life 0; with flag 0x0004 the status bits are raised.
5. **Weights.** weight += rate, life += life rate (both × speed unless 0x40). A track whose
   life is ≤ 0 is removed unless it has 0x0200. A track with 0x0002 whose min(weight, life)
   reached 1 removes the tracks under it. That also ends the loop over the tracks (the
   branch out at 0x16e0b8): the lower tracks that survive, those with 0x1000, are not
   stepped on that tick — no time, no events, no weight change — and the test is made again
   on every later tick, so they stay frozen for as long as the 0x0002 track sits above them
   at full weight (**executed**, `docs/spec/animation.md` section 5, note 1).
6. **Root motion.** For each track with 0x0800 the decoder gives joint 0's x/y at the new
   time; the change since the last call, times the track's effective weight, is added to
   `rootDelta[0..1]`. For 0x4000 the change of joint 0's yaw is added to `*yawDelta`.
   "The track's effective weight" is two weights (**executed**, same section, note 3): the
   part of the displacement up to the clip's end is weighted with the weight before the
   update of step 5, the rest with the weight after it; a track removed in step 5 gets no
   second part, so a non-looping root-motion track without 0x0004 loses the displacement of
   its final step. The yaw is not weighted.

Effective weight of a track = clamp(min(weight, life, what the tracks above left over), 0, 1).

### Root motion in a creature

`Creature_stepAnim` passes creature+0xbc (two floats) and creature+0xc4 (s16) as the outputs.
After the call it multiplies the delta by the creature's scale (+0xdc), rotates it by
`facing − 0x4000` into world x/y, and multiplies delta and yaw by `(60 − slow)/60` when the
slow amount at +0x2fc is 1…60 (the same factor already scaled `speed`). For the yaw that is
not what the code does: the factor is converted to an integer first (0x11648c) and the yaw
delta is multiplied by that integer, which is 0 for every slow amount of 1…60 — a slowed
creature gets no root yaw at all. The delta is scaled by the fraction as said
(0x116478–0x116498; **executed**, `docs/spec/animation.md` 7.1). The code that adds
+0xbc/+0xc0 to the position is in the creatures area. So position depends on: track times,
weights, the facing angle, scale and the slow amount.

### Pose

`anim_buildPose` (0x16ed40) walks down from the top track to the first fully weighted track
at which every joint is covered (joint masks AND-ed to zero), decodes it, then blends every
track above it by its effective weight (quaternion blend per joint, joint
mask respected). The result is 0x18 bytes per joint (3×3 rotation as s16/4096, translation as
s16/64) in a pose buffer taken from a second LRU pool (0x7b8340/0x7b8344). Draw callers may get
no buffer and then draw a default pose; simulation callers (`anim_getJointMatrix` 0x16f720,
used by `model_getAttachPoint` and `model_getSamplePoint`) always get one (a shared scratch
buffer at 0x7b89c0 as last resort). The values do not depend on which buffer was used.

Two things this section did not say. The per-joint matrix is not computed on the main
processor: `anim_buildPose` hands each joint to a VU0 microprogram (`g_vu0PoseProgram`
0x3e5c40 in `symbols/fmt-anim.tsv` — that address is the DMA / VIF packet that loads the
program, its first instruction is at 0x3e5c50; the two calls are at 0x16f594 and 0x16f5f4), which is
why the vector unit's rounding and clamping settings matter to the simulation and not only
to drawing (FINDINGS F6, `docs/issues/float-divergence.md`). And the pose is cached per
animation state: `anim_getJointMatrix` rebuilds only when no pose is attached, so whether a
simulation query gets a fresh build or one made earlier by drawing depends on what was
drawn (P11 below; FINDINGS D34, `docs/issues/rescan.md` R1).

## Lumps and resources (0x1711e8–0x173e9f)

`g_lumps` (0x7b9480, count `g_lumpCount` 0x41bf7c), 0x28 bytes per loaded lump:

| Offset | Meaning |
|---|---|
| +0x00 | name, 16 chars |
| +0x10 | pointer to the data |
| +0x14 | flags; bit 0 = this record is a single entry loaded on its own: the data starts with the entry name and the payload is at +0x100 |
| +0x18 | size kept after fix-up |
| +0x1c | sound memory the lump took |
| +0x20 | keep level |
| +0x24 | 1 when the loader owns the memory |

A lump in memory starts with a 16-bit entry count, then 12-byte records
{name pointer, data pointer, size} sorted by name (`lump_findEntry` does a binary search).

- `res_find(lump, entry)` (0x17365c, 429 callers) is the one lookup everything uses. It loads
  the lump with `lump_load` (blocking CD read) when it is not in memory.
- `resref_init` / `resref_get` (0x173768 / 0x17377c) cache a pointer and refresh it when
  `g_lumpGeneration` changes.
- `lump_fixup` (0x1717d0) walks a fresh lump and calls `lump_fixupEntry` (0x17153c), which
  dispatches on the file extension: `.anm` → `anm_relocate` + `anm_bindSounds`, `.vif` →
  `model_relocate`, `.tex` → `tex_relocate`, `.world` → `world_fixup`, `.uni` →
  `text_registerTable` (`.txt` only for `credits.txt`, which `credits_splitLines` 0x223ba0 cuts
  into lines; corrected in `docs/strings.md` 1.1), plus `.fnt`, `.vag`. Region prefixes (`ntsc_`, `pal_…`) are handled
  there.
- Lifetime: `lump_raiseKeepLevel(n)` marks everything loaded so far; `lump_unloadUpToLevel(n)`
  frees lumps from the end of the table whose level is ≤ n.
- CD access: `cd_findFile`, `cd_readAsync` (one read at a time, completion flagged from
  `lump_pollAsync`), `cd_readBlocking`, `cd_isBusy`, `cd_waitIdle`.
- `text_lookup(key)` (0x173c84, 267 callers) returns the wide string stored after the key in
  the string files; 8192-slot open-addressing hash (`text_hash`). A missing key yields the text
  "NF:" + key.

## Controllers (0x173ea8–0x174e77)

`pad_readPort` produces an 8-byte raw record: u16 buttons, four stick bytes, two analog
bytes. `pad_apply` (0x174410) turns a record into a pad structure (`g_pads`, 0x58 bytes each):

| Offset | Meaning |
|---|---|
| +0x08 | buttons held (plus four synthetic stick-direction bits 0x100000–0x800000) |
| +0x0c | buttons pressed this tick |
| +0x10 | pressed, with auto-repeat after 20 ticks |
| +0x14, +0x18 | left stick x, y |
| +0x1c, +0x20 | right stick |
| +0x28 … +0x54 | per-button pressures (0 or 1 from the bits; +0x38 and +0x50 from the two analog bytes) |

`pad_buttonValue` (0x174d80) returns the pressure offline and a plain 0/1 from the held bits
in a net game. `pad_rumble` is called from simulation code but only stores local motor state;
`pad_updateRumble` (called by `tasks_run`) drives the motors of local slots.

Note for finding G5: `pad_updateRumble` does store to 0x41c138 (it decrements it and clamps
at 0; reference at 0x174760) and `pad_apply` decrements 0x41bfc0 while it is non-zero. Neither
store can make the value non-zero and no other reference exists, so the finding stands, but
"never written" should read "never set".

## Models, sprites, text (skimmed)

- `model_draw` (0x1779b0): one call per model per frame. Draw parameters are globals at
  0x41c149–0x41c170 that callers set before and `model_resetDrawState` clears after.
- Model queries usable from simulation code: `model_getAttachPoint` (attach records of 0x34
  bytes: joint index, local matrix), `model_getSamplePoint` / `model_getSamplePointCount`
  (surface points as s16/16 with a joint index), `model_buildHideMask` (despite the name it
  returns a *show* mask: the complement of the model's hidden-by-default set, adjusted by
  the variant records — a set bit draws the mesh; `docs/formats/model-texture.md`),
  `model_getBounds`.
- Every drawer first checks that `g_dlCapacity − used` leaves 3000 units and silently draws
  nothing otherwise (this is the "render buffer" test of finding D13).
- Text: `text_begin(font, …)`, any number of `text_draw*`, `text_end()`. Strings are 16-bit.
  `wstr_format` is the engine's sprintf: `%%`, `%d`, `%c`, `%s` (8-bit), `%u` (a 16-bit string) and
  `%f` (always two decimals), every argument a float in f12–f19; executed in `docs/strings.md`
  section 2 (the earlier line said %d, %s, %.2f).

## World, terrain and water

`g_world` (0x44fdc8) points at the fixed-up `.world` structure:

| Offset | Meaning | Evidence |
|---|---|---|
| +0x04 | root of the chunk tree | `world_collectChunksInBox` |
| +0x08, +0x0c | terrain grid origin (cells of 160 units) | `terrain_collectElements` |
| +0x10, +0x14 | terrain grid width, height | |
| +0x18 | grid of pointers to s16 element-index lists ended by −1 | |
| +0x20 | terrain elements, 0x24 bytes each | |
| +0x24 | chunks, 0x3c bytes each (+0x08…+0x1c bounds, +0x24 flags: 0x80 water) | |
| +0x28, +0x2c, +0x30, +0x34 | path grid origin x, y, width, height (cells of 24 units) | `path_search` |
| +0x38 | path cells, one u32 each | |
| +0x50, +0x54 | moving pieces: count, array of 0x1c bytes (+0 chunk index, +0x14/+0x16 rotation, +0x18 terrain element index) | `world_movePiece` |

Terrain element (0x24 bytes): +0 s16 bounds (minX, minY, maxX, maxY), +8 visit stamp, +0xc
pointer to a height field, +0x10 flags (1 mirrored, 2 ignored, 4 the height field has
flagged samples, so a caller that passes a flag mask must test the element even when it
lies below the query — 0x18a5c0, 0x185a40; the earlier version said "tested by ray casts";
`docs/formats/world.md`),
+0x14/+0x18/+0x1c position (ints), +0x20/+0x22 rotation cos/sin (s16/32767).
Height field: +0 origin x, +4 origin y, +8 width, +0xc height (in samples), +0x12 s16 maximum
height, +0x14 u16 samples: height = sample >> 4 (signed), low 4 bits are flags.

| Function | Use |
|---|---|
| `terrain_height(radius, world, pos)` 0x183820 | highest ground under a disc; −1000000 when there is none. 49 callers |
| `terrain_heightBelow` 0x1834a8 | same but ignores anything more than 12 above pos.z (walking under bridges) |
| `terrain_heightAtPoint` 0x182f28 | single sample |
| `terrain_testFlag1` 0x183b48 | is any sample under the disc flagged with bit 0. The answer is a float in `$f0`, 1.0 or 0.0, which its two callers compare with a float (0x14aeec); not an integer 1 (executed, `docs/spec/world-queries.md` section 5) |
| `terrain_raycast` 0x18a5c0 | first terrain hit along a ray. The earlier version said "marching 240 units at a time": 240 units is the length of the segment for which terrain elements are collected; inside it each element is marched one 4-unit sample at a time (at most 1001 steps), and the first segment in which any element is hit decides, with the smallest parameter among that segment's elements. A vertical ray returns a distance, not a parameter. The height carried from one segment to the next is advanced four times too far (the rise per sample step times 240, where a segment is 60 steps), so only a horizontal ray is exact beyond the first segment. Sample flags do not block as such: each flag bit in the caller's mask adds 65536 to the sample's height. Executed, `docs/spec/world-queries.md` 9.1 |
| `world_raycast` 0x18ad94 | terrain plus object circles (objects from `world_collectObjectsInBox`) |
| `terrain_sweepCircle` 0x185a40 | moving circle against the samples (physics props, projectiles) |
| `world_setPieceCollision`, `world_movePiece`, `world_setPieceHeight` | doors, lifts and bridges. Only the first and the last change the terrain element of a moving piece (its flag 2 and its height offset). `world_movePiece` 0x182c98 does not, as the earlier version said: its stores go into the piece's chunk record only (+0x28, +0x2c, +0x30, +0x36, +0x38; 0x182ea0–0x182ed8), so the collision of a piece never moves or turns with its drawing. Observed, not executed (`docs/spec/world-queries.md` section 12) |
| `water_test` 0x189438 | is the position inside a water chunk; optional water height |
| `water_disturb` 0x189514 | add a ripple to the 32×32 grids of the water chunks around a position; returns how many chunks were found |

## Pathfinding (0x183e40–0x185447)

- Requests go into `g_pathQueue` (128 entries of 0x30 bytes: world, start, goal, radius, output
  buffer, capacity, requester handle, type). `Creature_requestPath` (0x1164c0) is the only
  caller of the four `path_request*` functions; its output buffer is creature+0x23c, 16 points.
  When the queue is full the requester is told "no path" immediately.
- `path_service(blocking)` (0x184798) takes the oldest request, clears the marks of the
  previous search, and runs `path_search`: a wave over the 8-connected cell grid
  with four ring buffers of 512 cells, stopping when a cell passes the request's goal test or
  after 80 rounds. The earlier version called the wave breadth-first; executed, it is not
  (`docs/spec/world-queries.md` 10.5): going on in the same straight direction costs 2
  rounds and every other move 3; a round is finished after a hit and the **last** node of
  the round that passed the test is taken, not the first; five empty rounds in a row also
  end the search; a node that finds its ring full is marked but lost. Cell word: low 8 bits
  = which neighbours can be entered; bits 8–15 = search mark, which is the direction it was
  reached from **plus one**, the start node carrying 15 (0x184bec); the upper 16 bits are
  not a blocked flag but a counter, 0–16, that 0x18b6c0 raises and 0x18b584 lowers over a
  rectangle of nodes (callers: `Torch_ctor` 0x2b200c and `StaticFire_initCommon` 0x2c58e4
  block, `StaticFire_dtor` 0x2c57cc unblocks); a node with a non-zero counter is never
  entered (`world-queries.md` 10.1).
- Goal tests by type, corrected from the code and executed (`world-queries.md` 10.4; the
  earlier version had type 1 the wrong way round ("the ray to the goal is clear"), type 2
  as a test inside the radius only, and type 3 as "not read").
  A ray that hits nothing returns −1.0. Type 0: within the radius of the goal point. Type 1
  (0x1844f0): within the radius **and** `world_raycast` toward the goal returns more than
  0.98 — so a completely clear line *fails* the test (0x18452c, 0x1845a0). Type 2
  (0x1845bc): every node **outside** the radius passes (0x1845f8); inside it, unless the
  radius is above 120 and the node nearer than 120, a node passes when `terrain_raycast`
  returns less than 0.98, which includes hitting nothing (0x184688). It is requested by
  `Creature_requestPath` mode 1, which `docs/spec/movement-camera.md` 6.3 describes as
  fleeing, not by ranged attackers. Type 3 (0x1846a4): as type 2 with `world_raycast`
  (requester ignored) and the limit 0.75 (0x184774).
- The result is written as (x, y) integer pairs ending with (−1, −1), and delivered by calling
  the requester's virtual slot 7 with 1 or 0.
- `g_pathEnabled` (0x44f090): while 0, `path_search` returns "no path" at once. It is cleared
  when a net game is set up (0x13dce0) and set by `world_resetRuntime` at level start.
- Timer: `path_service` returns when not blocking and hardware timer T0 > 8999;
  `path_search` suspends when not blocking and T0 > 7512. All search state is in globals, so
  a suspended search continues exactly where it stopped. In a net game `net_frameLoop` and
  `cut_advance` call `path_service(1)`, so every request queued in a tick is answered in that
  tick on every machine (finding D5).

## Camera

`camera_setView(pos, mat34)` (0x18a2b0) writes `g_cameraPos` (0x44f038) and `g_cameraMatrix`
(0x44f110); other writers were not searched for exhaustively. Its callers are `cut_runFrame`, the inventory
and stats screens, and the game camera (`Camera_apply` 0x2035c8). `camera_setProjection`
builds the projection and frustum planes; `camera_setFarClip` caps at 1800.
`camera_updateFocus` (0x18a520) derives `g_cameraFocus` = position + forward × 600 and is
called by `cut_runFrame` and by `drawWorld`.

## Cutscenes (0x196344–0x19b673)

### Runtime state

| Global | Meaning |
|---|---|
| `g_cutActors` 0x83d184, `g_cutActorCount` 0x83d188 | actor table from the file |
| `g_cutKeys` 0x83d190, `g_cutKeyCount` 0x83d194, `g_cutKeyIndex` 0x44fcfc | key list and the next key to run |
| `g_cutFrame` 0x44fce0 | clock in ticks; key time = frame / 60 |
| `g_cutFlags` 0x83d19c | header flags |
| `g_cutDialogLines` 0x44fd1c, `g_cutDialogLineCount` 0x44fd20, `g_cutDialogLine` 0x44fd0c | dialog lines and the next line |
| `g_cutLipsyncReady` 0x83d180, buffers 0x83d170 / 0x83d178 with state words 0x83d174 / 0x83d17c | lip-sync animation preload |
| `g_cutVoiceDoneCount` 0x44fd28, `g_cutVoiceDoneSent` 0x44fd2c, `g_cutVoiceDoneMsg` 0x83d1c8 | "voice finished" hand-shake |
| `g_cutCamPos` 0x83d110, yaw 0x44fcd4, pitch 0x44fcd6, roll 0x44fcd8, fov 0x44fcdc | camera track output |
| `g_cutSpeaker` 0x83d18c | creature speaking the current line |

Actor record (0x2c bytes): +0x00 object pointer (filled at setup), +0x04 a value copied from
or passed to the object, +0x08 name, +0x1c position (3 floats), +0x28 s16 facing, +0x2a byte
copied to creature+0x230, +0x2b non-zero = create the object for the cutscene, zero = bind an
existing level object found by name within 240 units of the position.

Header flags: 1 = already set up (positions were converted with `cut_anchorToWorld` relative
to the level object named like the cutscene); 2 and 4 each extend the key list by three keys
and are treated differently when `g_networkMode` is set (tests at 0x19aa18 and 0x19aae0; details *Unknown*); 8 selects
a different way of hiding and restoring the rest of the level's objects; 0x10 is set by the
code for ordinary cutscenes and controls the letterbox. Header word +0x70 × 0.1 is passed to
`light_setScale`.

### Per tick

`cut_start` (from script `cutScene`) resets the state and adds `cut_runTask` (run, priority
300) and `cut_drawFrame` (draw, 300). `cut_runFrame` then does, each tick:

1. lip-sync preload (see Dialog);
2. on the first tick `cut_setup`: bind/create actors, load dialog, hide other objects. A
   bound object is moved to the actor's start position unless it has an `autoprop` or
   `autodoor` property. Actors
   named `Player` and `Player2` are stand-in `Player` objects created with `Player_ctor` when
   that player is alive; other created actors go through `world_createObject`. All actors get
   object flags 0x88000;
3. `cut_advance(clock)`: sets `g_cosmeticSeed = g_cutFrame + i` and runs actor *i*'s `run`
   (slot 4) for every actor, calls `path_service(1)`, increments `g_cutFrame`, then executes
   every key whose time has come with `cut_execKey`;
4. `cut_evalCamera(clock)`, `camera_setProjection`, `camera_setView`, `camera_updateFocus`;
5. skip test: any player's pressed bit 0x800 in `g_pads` sets `g_cutSkip` (in a net game on
   levels `endgood` / `endbad` only after 300 ticks). Skipping stops the streams and runs
   `cut_advance` in a loop until the key list is exhausted;
6. when the key list is exhausted: `cut_end`, which moves the real players to where the
   `Player` stand-in ended (other players are spread around it with `world_findFreeSpot` and
   `terrain_height`), deletes created actors and restores bound ones.

### Key types

Keys are 20 bytes: `float time; s16 actor; s16 type; s32 a, b, c`.

Camera keys (actor −100). All but type 6 are evaluated every tick by `cut_evalCamera`
(0x19712c), which looks up the keys before and after the clock with `cut_findKeyBefore` /
`cut_findKeyFrom` and interpolates with Hermite splines whose tangents come from the
neighbouring keys:

| Type | Meaning | Evidence |
|---|---|---|
| 0 | camera position (a, b, c) | writes `g_cutCamPos` |
| 1 | yaw, a = 16-bit angle (default −0x2000) | writes 0x44fcd4 |
| 2 | pitch, a = 16-bit angle (default 10000) | writes 0x44fcd6 |
| 3 | look-at: a = actor index or −1. Yaw and pitch are aimed at the actor (its position plus half its height) and blended from the previous type-3 key's aim to the next with smoothstep over the interval | 0x198958–0x198d08 |
| 4 | tangent break: splines stop (zero tangent) at this time | compared against key times in every spline section |
| 5 | cut: the camera jumps at this time. Raises `mainloop_startFadeWait(4)` just after it, and when the next key is a cut it asks the world to preload the next view (0x189df0) | calls at 0x198e98 and 0x198f10 |
| 6 | far clip = a × 12 | `cut_execKey` → `camera_setFarClip` |
| 7 | fade through black centred on the key (colour offset from the distance in time, ±0.64 s) | `gfx_setColorOffset` call 0x198db8 |
| 8 | roll in degrees (a × 182) | writes 0x44fcd8 |
| 9 | field of view in degrees (default 50) | writes 0x44fcdc |
| 10 | "screen darken" ramp around the key. The value `gfx_setScreenDarken` keeps is the FIX alpha of the present pass, which mixes the new image with the previous one; it does not darken by itself (`docs/spec/render-pipeline.md` section 8; the visible result is Inferred there) | `gfx_setScreenDarken` call 0x198e84 |

Dialog keys (actor −99):

| Type | Meaning |
|---|---|
| 0 | next dialog line (below) |
| 1 | sets 0x44fd04, which hides the subtitle |
| 3 | wait until the voice line has ended on every machine (handled in `cut_advance`) |
| 7 | start the next queued entry of the level's stream directory on stream 2 (`stream_clearHold(2)`, queue the one after with `music_playLevelIndex`) |

Object keys (actor ≥ 0, `cut_execKey` 0x196788):

| Type | Meaning |
|---|---|
| 0 | walk to (a, b, c): creature virtual slot 27 with argument 1, target stored at +0x104…+0x10c |
| 1 | follow / face actor a: handle at creature+0x234, slot 27 with argument 3 |
| 2 | play animation. a = index among the object's animations, or a name hash when c = 0xbadfeed. b = mode: 0, 1, 6 one-shot with end report; 2 loop; 3 short blend in and out; 4, 5 loop that replaces lower tracks |
| 3 / 4 | virtual slot 3 with argument 1 / 0 |
| 5, 6, 7 | take the object off the world grid (`obj_moveOffGrid`); creatures get bit 8 of +0x231 |
| 8 | put it back (`obj_updateGridCell`) |
| 9 | `obj_addToAlwaysDraw` |
| 10 | teleport to (a, b, c) and put back; a creature other than the speaker is reset with slot 27 argument 0 |
| 11 | facing = a |
| 12 | toggle bit 0x200000 of the creature's 64-bit flags at +0xa8 |

Case 10 runs on into 11 and 12 in the decompile; whether that is real fall-through or a
decompiler artefact was not checked in the disassembly (*Unknown*).

### Dialog lines and voice

- `cut_loadDialog` (0x1964d4) finds `<cutscene>.dbin` in `<level>.lmp`. A line is 0x448
  bytes: +0x21 string-table key of the subtitle, +0x31 voice entry name, +0x41 name of the
  speaking object.
- Voice audio is stream 1. At setup the first line is queued held
  (`stream_playLevel(1, "<voice>.vag", 0x28)`). A type-0 key releases the hold
  (`stream_clearHold(1)`), reads the entry length (`stream_levelEntryLength`), and queues the
  following line held. So each line starts on its key and the next one is already buffered.
- Speaker: the line's speaker name is resolved with `world_findObjectByName`; it must be a
  creature. Its u16 at +0x3c4 is set to 44000 (the previous speaker's back to 1150). This
  said "meaning *Unknown*"; `docs/creatures.md` identifies +0x3c4 as the creature's
  activity radius, the value `Creature_updateActive` 0x10c0f0 passes to `obj_updateActive`,
  so 44000 keeps the speaker active wherever the players are (*Inferred*: it is larger
  than the whole object grid).
- Speaker animation, two paths (0x196a9c):
  - lip-sync: if the per-line animation `<voice>.anm` has finished loading, it is started with
    `anim_start(0.3, …, flags 0x26)` and the creature's `idle` animation is chained after it;
  - otherwise the generic `talk` animation loops, and `idle` is started with a negative time
    computed from the voice entry length, so that it takes over when the line should be done.
- Lip-sync preload (`cut_runFrame` 0x199958–0x199b60): while line *n* plays, the animation for
  line *n+1* (an entry `<voice>.anm` of the level stream file) is read with `cd_readAsync`
  into one of two buffers; when the read completes, `g_cutLipsyncReady` is incremented on the
  next tick. The read is only started when `cd_isBusy()` is false.
- While the speaker has a track with flag 0x20, `cut_advance` compares that track's time with
  `audio_streamPosition(1)` and nudges every track time of the speaker by ±0.1 per tick
  (finding D8).
- Wait key (type 3): each machine sends game message `g_cutVoiceDoneMsg` once its own
  `audio_streamStatus(1)` reports the stream ended; the handler at 0x198f64 counts them, and
  the key list does not advance until the count reaches max(1, `net_countActivePeers()`).
  While waiting, `g_cutFrame` is held.
- Subtitles are drawn by `cut_drawFrame` from the line before `g_cutDialogLine`.

## Pause menu and recall (0x18c230–0x18e627)

`pauseMenu_open(pad)` adds `pauseMenu_task` as a **draw** task; it reads `g_rawPads` and, in a
net game, sends its choices as game messages (0x1d9250). `g_paused` is only touched offline.
`pauseMenu_isOpen` is read by `net_frameLoop` and `net_predictLocalPlayer` to decide about
the prediction copy. `recall_execute(slot)` is reached from `hud_onMsg`; it consumes a
`recallpotion` item and creates a gate object at each living player.

## Particles, glows, trails, beams (skimmed)

Read in full since: `docs/effects.md` (formats, spawn and retirement rules, emitters,
decals, gore, skill visuals) and `docs/lighting.md` (light nodes and sources).


- Particle definitions are static objects built by `particleDef_ctor` / `particleDef_init`.
  `particle_spawn(…, def, pos, vel)` (175 callers) takes a particle from a fixed pool and does
  nothing when the pool is empty.
- `particle_updateTask` is registered with task flags 2 and runs in the **run** phase, once per
  simulated tick; `particle_drawTask` runs in the draw phase.
- Particle groups (`particleGroup_create` … `_free`) are 16 slots with their own lists and
  matrix; a group that stays empty for 30 ticks is freed by the update task.
- `glow_add` queues up to 1024 camera-facing sprites per frame; `trail_*` (64 trails) and
  `beam_*` (20 beams) are handle based, handle = generation << 8 | slot.
- Random numbers in all of this come from `g_cosmeticSeed` only (see below).

## Tasks and frame

`g_tasks` (0x840100): 16-byte records {function, priority, name, flags}, kept sorted by
priority by `task_add`; `g_taskCount` 0x44fdb8. Flags: 0 = run phase, 1 = draw phase, 2 = run
phase (used only for `updateParticles` and one other task). `tasks_call(exclude, include)`
(0x19e798) calls every task whose flags have none of `exclude` and, unless `include` is −1,
at least one of `include`: `tasks_run` uses (1, −1), the draw phase in
`mainloop_runSession` uses (0, 1). A task may add or remove tasks while the list is being
walked (`g_taskCursor` is adjusted).

`gfx_beginFrame` / `gfx_endFrame` bracket a rendered frame; the second increments
`g_drawFrame` (0x44fdd0). `g_simFrame` (0x44fdcc) counts ticks: `tasks_run` increments it
offline, `net_frameLoop` sets it to `g_netFrame` around each tick. `engine_frameStep` returns
1 or 2 depending on how many vertical blanks the last frame took. Not stated before
(`docs/spec/render-pipeline.md` sections 8 and 13): the packets queued during frame N are
rasterised at `gfx_beginFrame` of frame N+1, so anything that reads "what was drawn" lags
the draw tasks by a frame.

`engine_init` (0x19d19c) is the boot sequence: stack check, IOP modules, GS, `engine.lmp`,
fonts, then the `*_init` functions of this range.

## Per-machine state

Places in this range where something that differs between machines can reach, or is next to,
shared game state. "Shared" means it can affect what the lockstep simulation computes.

| # | What | Kind | Where |
|---|---|---|---|
| P1 | `g_cosmeticSeed` is seeded from the CPU cycle counter (COP0 Count) at boot. Anything derived from it differs per machine from the first frame | Observed | `engine_init` 0x19d1e0 (mfc0), store 0x19d1f8 |
| P2 | `g_noiseTable` is built from that seed, so `math_noise` returns different values on every machine. Its simulation-side callers are `Torch` run 0x2b2088, `Lantern` run 0x2b3554 and `Lamp` run 0x2b3858, which also index it with their own object pointer; they write only light radius and light position fields (+0x68…+0x84) | Observed for the table and callers; that those fields are render-only is Inferred | `math_buildNoiseTable` 0x1646c8; `math_noise` 0x166b48 |
| P3 | `anim_randomizeTopTime` sets a track's time from `g_cosmeticSeed`. The `Critter` constructor (0x2547fc; spawned by `VampireLord` run and by creature code 0x1125e0) calls it right after `anim_push(…, 0x801)`: a **looping root-motion** track. Its root-motion deltas, and so its position, start from a different phase on each machine. Narrowed since (`docs/issues/sync-breakers.md` section 8): the branch is taken only when the object has a `path` property — 115 `Shark` and 4 `vulture` placements in level files. The critters spawned in play (corpse scavengers, VampireLord's bats) are built one-shot with no path and skip it | Observed for the calls and flags; the effect on position is Inferred | 0x254e2c–0x254e34; seed use 0x16d0d8 |
| P4 | The same call follows a plain looping `anim_push(…, 1)` in the constructors of FireBeetle (0x24587c), FireFly (0x24726c; the earlier version listed it as a second FireBeetle constructor — the old `vtables.txt` labelled FireFly's table 0x5108c8 `FireBeetle`), Ghoul 0x266088, AutoProp 0x23c44c, SmallSpider 0x2ab450, SpiderQueen 0x2ad1c0, BlackWidow 0x2ab958, NPC 0x29dcc4 / 0x29df04 / 0x29e2a4, VampireLord 0x2b76e4, Vampire 0x2b69d0, UserParamProp 0x15711c and PoisonProjectile 0x2b153c. Idle phase, and therefore the tick on which that animation's event bits fire, differs per machine. Harmless only if those animations carry no events the class acts on. Checked since, class by class (`docs/issues/sync-breakers.md` section 8): no animation file has events at all; code assigns them, and for every class in this list but one the constructor puts none on the randomised entry. The exception is the `AutoProp` constructor, which for a prop whose type starts with `pipepistona` writes four event slots into that same looping animation inline (0.25 s and 1.85 s mask 1, 1.0 s and 2.6 s mask 2; stores after the `anim_randomizeTopTime` call in 0x23c44c), and the prop's run function opens and closes its damage window on those masks — FINDINGS D27 and D30, `docs/monsters-2.md` M5. (sync-breakers B6 says no randomising constructor does this; it looked only at callers of `creature_setDefEntryParams` and missed the inline stores.) For props placed in a level file the phase is still the same on every machine if the seeds are equal at load (Inferred there) | Observed for the calls; consequence answered (was Unknown): none for the other classes, the piston trap as D27 says | call sites in the symbol note of `anim_randomizeTopTime` |
| P5 | `rigidbody_init` draws the initial orientation of a physics body from `g_cosmeticSeed`. Callers: `PhProp_initPhysics` 0x155110 (reached from `loot_generateDrops`), `PushPhysicsProp` slot 8 0x15dbd4, 0x15dddc. If where a prop or dropped item comes to rest depends on its orientation, its position differs per machine. Read since, caller by caller: `PhProp_initPhysics` overwrites the drawn orientation from the prop's matrix (`quat_fromMat3` at 0x155310, then normalise), so for props and dropped items the start state is shared (`docs/issues/arena-desync.md`); `PushPhysicsProp` slot 8 (load from a level record) overwrites it too; only the crate constructor 0x15dddc keeps it, and no crate is created outside level load, when the cosmetic seed equals the shared one (FINDINGS D36, `docs/issues/rescan.md` R4) | Observed for the draw and the overwrites; the equality of the seeds at level load is Inferred | 0x168350 |
| P6 | Cutscene lip-sync choice: whether the speaker gets the per-line lip-sync animation or the generic talk loop depends on whether a local asynchronous disc read has completed (`g_cutLipsyncReady`, slot state) by the time the dialog key runs, and the read cannot start while the local CD is busy. Different animation → different tracks, flags and end-status bits on the speaker | Observed for the dependency; that the read can actually be late is Inferred | read start 0x199a24, busy test 0x199a64, choice 0x196a9c |
| P7 | Speaker track times are nudged toward the local audio stream position (finding D8) | Observed | `cut_advance` 0x199444–0x1995c8, `audio_streamPosition` call 0x199468 |
| P8 | Wait key: the local stream status decides when this machine sends its "done" message; the cutscene clock resumes when the count is complete. Correct only if the message handler runs on the same tick everywhere | Observed here; delivery timing belongs to netcode (Unknown) | status 0x199398, handler 0x198f64 |
| P9 | `cut_advance` and `cut_runFrame` overwrite `g_cosmeticSeed` with shared values (`g_cutFrame + i` before each actor's run, `g_simFrame` at the end of the tick, `i + 0x392fa` before creating actor *i*). This makes cosmetic draws inside actor `run` calls repeatable during cutscenes, but only there | Observed | 0x1992a8, 0x199f88, 0x19af20 |
| P10 | `anim_advance` reads `g_drawFrame` to limit sounds, and skips sound bookkeeping when the caller passes no position (the real local player while its prediction copy exists). Only the sound cursor (track+0x1e) and sounds are affected; event bits, weights and root motion are not | Observed | 0x16d9d8; `Player_animStep` passes 0 for flag 0x200000 |
| P11 | `anim_buildPose` reads `g_drawFrame` to choose a pose buffer. Values do not depend on the buffer — true of one build. Whether a build happens at all depends on drawing: the pose is cached per animation state, drawing attaches one, a least-recently-drawn rule keyed on the render frame counter detaches them, and several animation calls change the tracks without detaching, so a simulation query can read a pose that drawing computed earlier (FINDINGS D34, `docs/issues/rescan.md` R1; a route to shared state was not found there, and not excluded). In addition (`docs/issues/pose-cache.md` section 2): the buffer's draw stamp is written by `anim_emitPose` only (0x16f8e4), never by `anim_buildPose`, so a pose built by a simulation query keeps an old stamp and is short-lived on a machine that does not draw the object — any later build may take the buffer — while on a machine that draws it the pose stays. `pose-cache.md` followed the arena classes and found no sequence in which this reaches shared state (D34 answer, D40) | Observed | 0x16ed9c; 0x16f8dc–0x16f8e4 |
| P12 | World scenery animations are advanced from draw code, once per rendered frame | Observed; nothing in this range reads them from simulation code (Inferred cosmetic) | `world_draw` 0x189910 |
| P13 | Pathfinder reads hardware timer T0 (finding D5). The blocking call each tick makes the outcome the same; see Pathfinding for why a suspended search resumes identically | Observed | `path_service` 0x184de4–0x184df8, `path_search` 0x184324 |
| P14 | `water_disturb` is called from simulation code and writes ripple grids for the water chunks that have one (which chunks get a grid was not traced; *Inferred* to be decided by drawing). Its return value counts chunks whether or not they have a grid, but it is forced to 0 while `g_cutSkip` is set | Observed except as marked | 0x189514 |
| P15 | `decal_add` creates floor decals depending on the local option `g_decalDetail` (0x44fdc0); decals are written into the save by `decal_serialize` (from `save_writeLevelState`). The same option is read by creature death code 0x110d30 (0x1113fc, 0x1116bc, 0x1116f8) and `Player_processDamage` (0x1b31f4). The sites at 0x1113fc and 0x1b31f4 also accept `g_networkMode`, 0x1116bc requires an offline game; the decal site at 0x1116f8 has no network test and draws twice from a **fourth generator at 0x404468** (the third global seed word; "fourth" counts the per-object generators, and `docs/OVERVIEW.md` lists it as a further cosmetic one) | Observed; whether anything shared depends on the decals or on 0x404468 is Unknown (0x404468 is used by 7 functions, none in this range) | 0x19f158 |
| P16 | `engine_frameStep` returns the local frame cost (1 or 2). Callers in this range: `pad_updateRumble` only | Observed | 0x19e3a8 |
| P17 | `pauseMenu_task` is draw code driven by `g_rawPads`; `recall_execute`, reached from a game message, closes the pause menu of whichever machine runs it, sets `g_paused` to 0 and the input lockout 0x41b4fc to 60 | Observed | 0x18cc08, 0x18c230 |
| P18 | `cut_end` (moves players, deletes actors) is also called from the HUD draw task `hud_netStatusDraw` when the net session is being abandoned after a long stall | Observed; only on the way out of a broken session | calls at 0x1dbe64 and 0x1dc0b4 |
| P19 | `beam_create` records whether it was called inside a simulation tick (`g_inSimTick`) | Observed, cosmetic | 0x1932e4 |

Checked and found clean:

- **No function in 0x160000–0x1a0000 reads or writes the shared seed `g_randSeed` (0x404464).**
  Particle, trail, beam, water, weather and animation-sound code uses `g_cosmeticSeed` only
  (0x16d360, 0x16d558, 0x170cd8, 0x186e38, 0x1876e0, 0x18ba18, 0x192a40, 0x192c50, 0x192e80,
  0x193ad0, 0x195400). `ParticleMorphEffect_run` uses its own per-object generator from `run`.
- Animation, pathfinding and cutscene code does not read the camera to make a decision.
  `cut_evalCamera` reads the camera position only to preload the next shot.
- `cut_start` always sets the voice flag 0x44fcd1 to 1, so the wait-key logic is not gated by a
  local setting.
- Cutscene skip reads the lockstep pads (`g_pads`), not `g_rawPads`.
- Decoder slots of root-motion tracks cannot be stolen by drawing (`animcache_alloc`).

## Open questions

1. What the animation event bits mean per class. The engine only merges them; read the
   creature state handlers that receive the result of `Creature_stepAnim`.
2. P3/P4/P5: does a `Critter`'s position, a monster's idle event timing or a physics prop's
   resting place reach the sync hash? P3 looks the most direct; it needs the Critter run code
   (0x2547fc class, vtable 0x510ca0) read, or a two-machine run with VampireLord.
3. P6: can the lip-sync read really miss its key? Depends on disc timing; an emulator with a
   fast disc may never show it.
4. Camera during cutscenes (finding D7): `Camera_update` (0x203400) is called from
   `net_predictLocalPlayer`. `cut_start` sets the camera mode to 0 with `Camera_setMode`, but
   `Camera_update` still runs its transition branch when camera+0x48 is non-zero and can then
   call `camera_setView`. If that happens between ticks, `drawWorld`'s `camera_updateFocus`
   leaves a per-machine `g_cameraFocus` for the tasks that run before `cut_runTask` (priority
   300) in the next tick. Not traced further.
5. Cutscene header flags 2 and 4 (the three extra keys) and what object key types 3/4 do in
   each class (virtual slot 3).
6. Path request type 3 goal test (0x1846a4) and the two routines at 0x185448 and 0x1857e4.
   (Answered by `docs/spec/world-queries.md` sections 10.4 and 12: the goal test is in
   "Pathfinding" above. 0x1857e4 is a straight-line walk probe — the height below, then a
   sweep, in steps of min(2 × radius, 24), with a 3-unit retry mode; 0x185448 walks the path
   grid calling `terrain_height` and a particle routine. Neither has a caller or a stored
   pointer anywhere in the executable, so neither runs.)
7. Whether object key 10 really falls through into 11 and 12.
8. The creature field +0x3c4 written for the cutscene speaker (44000 / 1150). (Answered by
   `docs/creatures.md`: the activity radius; see "Dialog lines and voice".)

## Not covered

Not opened beyond the first lines or not at all: the automap routine 0x168cac and map icons
0x1689a4; the GS/DMA setup 0x16b998–0x16c9d0; the model packet builders 0x174e78, 0x175670,
0x1762e8 (creature draw helper, 5.8 KB), 0x1786c8; the texture cache and streaming
0x179b08–0x17f9f8 (0x17d830 reads `g_cameraFocus` to stream world textures); world drawing
0x1863fc–0x1887b8 and water simulation 0x186e38; weather 0x18b810–0x18ba18; the pause menu
body 0x18cc08 and 0x18c7bc; particle, trail and beam drawing 0x18fe18–0x194888; the frame
code 0x19b6e4–0x19d0c4 and the standalone loop 0x19dea4; decal drawing 0x19f4e8. The Skill
table constructors at 0x16a98c–0x16b7d0 belong to the skills area.
