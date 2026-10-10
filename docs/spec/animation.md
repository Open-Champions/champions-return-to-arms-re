# Animation: decoding a clip, stepping a state, building a pose

A specification for someone who has to reimplement the animation system of Champions:
Return to Arms (SLUS_209.73, US v2.00) so that it behaves like the original. Animation is
simulation, not decoration: the tick on which an animation reports an event decides when a
hit lands, root motion moves the creature, and cast points are read from the skeleton.

- `tools/ref_anim.py` is the same content as executable Python (standard library plus
  `tools/ref_core.py`); every function names the address it mirrors.
- `tools/difftest_anim.py` runs the original machine code and the model side by side on
  clips from your own disc. Section 12 says exactly what that covers.
- The file format of a clip is in `docs/formats/anim-audio.md`; this document only repeats
  what the run-time code reads. The cross-machine analysis of the pose cache is
  `docs/issues/pose-cache.md`; here the cache rules are stated, not judged.

Evidence marks: **O** observed — read in the instructions at the address given;
**X** executed — additionally compared by the differential test (bit for bit unless a
tolerance is stated); **I** inferred; **U** unknown. Nothing was run on a console.

## 1. Conventions

- All integers little endian. A *tick* is 1/60 s. Angles are signed 16-bit, 65536 to a turn.
- Floats are R5900 single precision: no NaN or infinity, results truncated toward zero.
  Formulas below are written with the grouping the code uses; where the order matters for
  the last bit it is spelled out. The compiler truncated its decimal constants, so use the
  bit patterns of this table, not the decimal values.

| Pattern | Value | Used for |
|---|---|---|
| 0x3f7fffff | 0.99999994 | one tick of track time at speed 1 (`K_STEP`) |
| 0x3c888888 | 1/60 (truncated) | seconds ↔ ticks (`K60`) |
| 0x42700000 | 60.0 | blend seconds → ticks |
| 0x3c800000 | 1/64 | initial positions, bind offsets, pose translation |
| 0x39800000 | 1/4096 | initial quaternions, pose rotation |
| 0x3b800000 | 1/256 | position velocity per tick |
| 0x37000000 | 1/131072 | quaternion velocity per tick |
| 0x3d800000 | 1/16 | sample-point coordinates |
| 0x3a83126e | 0.001 | smallest blend weight that is applied |
| 0x37800000 | 1/65536 | random draw → fraction |
| 0x40490fda, 0x40c90fda | π, 2π | the (inert) "unwrap" in the quaternion blend |

- `min(a, b)` and `max(a, b)` are the R5900 `min.s` / `max.s`: the first operand wins a tie
  (also between +0 and −0).
- `int(x)` is `cvt.w.s`: toward zero, saturating. `float(n)` is `cvt.s.w`.

## 2. Structures

### 2.1 Animation state (embedded in every animated object; a creature has it at +0x114)

| Offset | Type | Field | Notes |
|---|---|---|---|
| +0x00 | ptr | pose | the pose buffer that holds this state's pose, or 0 |
| +0x04 | s8 | count | tracks in use; track 0 is the bottom layer |
| +0x05 | s8 | capacity | creatures and players: 8 |
| +0x06 | u16 | flags | union of the flags of the tracks **visited** by the last `anim_advance`, plus status 0x0080 (a track with flag 0x0004 reached its end) and 0x0400 (that track was the top one). Push and start functions OR the new track's flags in immediately |
| +0x08 | track[capacity] | | 0x20 bytes each |

Track cell:

| Offset | Type | Field |
|---|---|---|
| +0x00 | ptr | clip (the loaded `.anm`) |
| +0x04 | ptr | decoder slot, or 0 (allocated on the first decode) |
| +0x08 | float | weight |
| +0x0c | float | rate: weight change per tick |
| +0x10 | float | life |
| +0x14 | float | life rate (0 or negative) |
| +0x18 | float | time, in ticks |
| +0x1c | u16 | flags |
| +0x1e | s16 | sound cursor: index of the next sound event |

The weight a track blends with is `min(weight, life)` limited to 0…1.

Track flags (**O** for every bit, **X** for all but 0x0020, which the engine never tests):

| Bit | Name in the model | Meaning |
|---|---|---|
| 0x0001 | LOOP | wrap at the end |
| 0x0002 | PURGE_BELOW | once `min(weight, life) ≥ 1`, delete the tracks below (except 0x1000) |
| 0x0004 | REPORT_END | at the end: hold time = length and raise status 0x0080 (0x0400 too on the top track) |
| 0x0020 | TALK | cutscene marker (`anim_findTrackByFlag`) |
| 0x0040 | FIXED_STEP | advance by 0.99999994 whatever the speed; rates are not scaled by the speed |
| 0x0100 | EASE | smoothstep the blend weight (pose only) |
| 0x0200 | KEEP | not removed when life ≤ 0 |
| 0x0800 | ROOT | joint 0's x/y leave the pose and are returned as a displacement |
| 0x1000 | PERSISTENT | survives PURGE_BELOW and `anim_dropNonPersistent` |
| 0x2000 | PAUSED | time does not advance (weights and events still do) |
| 0x4000 | YAW | joint 0's heading leaves the pose and is returned as an angle change |

**The cells are memory, and stale memory is read.** Removing a track moves the cells above
it down with block copies and leaves the old top cell's bytes in place (only its slot
pointer is zeroed). `anim_clear` only sets count = 0. Two later readers see such bytes: the
next push into the cell releases a slot pointer it finds there, and `animcache_alloc` reads
the flags of whatever cell a slot's owner pointer names. An implementation that keeps
tracks in a growable list must reproduce those two effects or show they cannot differ
(they are covered by the test because the model keeps the cells too).

### 2.2 What the code reads of a clip

| Offset | Field | Reader |
|---|---|---|
| +0x00 | joint count (≤ 64) | decoder, pose builder |
| +0x04 | length in ticks | everything |
| +0x08 | key stream | decoder |
| +0x0c | bind offsets, per joint `s16 x, y, z, 0`, unit 1/64 | pose builder |
| +0x10 | depth list, one byte per joint | pose builder |
| +0x14 | four event slots `{float seconds; u8 mask}` — zero in every file, written by game code after loading | `anim_advance` |
| +0x38 | sound events, 0x1c bytes each, first word = tick, ended by 0x7fffffff; 0 = none | `anim_advance` |
| +0x3c | sound group | `anim_advance` |
| +0x48 | u64 joint mask: bit *j* set = this clip does not drive joint *j* | weights, pose builder |

### 2.3 Decoder slot (0xf1c bytes; 165 of them at 0x6f6180, set up by `anim_init` 0x16f9a8)

| Offset | Field |
|---|---|
| +0x00 | key stream pointer |
| +0x04 | bit cursor of the next key record |
| +0x08 | key tick: tick of the last record consumed (1000000 right after allocation) |
| +0x0c, +0x10 | previous / next in the use-order list |
| +0x14 | owner: the track cell that uses the slot, or 0 |
| +0x18 | s16 yaw: heading of joint 0 at the last root-yaw step |
| +0x1c | 64 joint records of 0x3c bytes |

Joint record: `s16 ptick, rtick` (tick of the last position / rotation key), `float pos[3]`,
`float vel[3]`, `float quat[4]` (x, y, z, w), `float qvel[4]`.

The slots form a list from least recently used (`g_animCacheLruHead` 0x791e90) to most
recently used (0x791e8c). After `anim_init` the head is slot 164 and the tail slot 0.

For a track without ROOT or YAW a slot is a cache: it can be taken away at any time and is
rebuilt from the stream. For a ROOT or YAW track it is **simulation state** — it holds the
root-motion base (joint 0's `pos.x`, `pos.y`) and the yaw baseline — and is never taken.

### 2.4 Pose buffer (0x620 bytes; 100 pooled at 0x791ec0, plus two static ones)

| Offset | Field |
|---|---|
| +0x004 | u32 tag `0x6d008000 | (3·n + 1) << 16` (a VIF unpack code for the draw path) |
| +0x008 | s16 joint count *n* |
| +0x010 | 64 × three rows `s16 r0, r1, r2, t`: rotation × 4096, translation × 64 |
| +0x610 | owner: the state whose pose this is, or 0 |
| +0x614, +0x618 | previous / next in the use-order list |
| +0x61c | stamp: `g_drawFrame` when the buffer was last **drawn** |

List ends: `g_poseLruHead` 0x7b8344 (oldest), `g_poseLruTail` 0x7b8340. Static buffers:
the fallback buffer 0x7b89c0 (not in the list) and the default pose 0x7b8380 (64 identity
matrices, never owned).

### 2.5 Globals

| Address | Name | Role here |
|---|---|---|
| 0x44fdd0 | `g_drawFrame` | pose buffer age; sound-cue limiter. Per machine |
| 0x44fdcc | `g_simFrame` | `anim_syncToSimFrame` |
| 0x404460 | `g_cosmeticSeed` | `anim_randomizeTopTime`, and every sound event played |
| 0x7b8fe0 | `g_animCueThrottle` | per sound group `{u8 frame, u8 count}` |
| 0x4f8a28 | `g_soundGroupLimit` | per sound group one signed byte |
| VU0 data memory | | the matrix stack of the pose builder (section 8.3) |

## 3. The decoder — `animtrack_decode` 0x16e468 (**X**)

The stream is a sequence of 16-bit words; bits are taken from the most significant bit of
each word down, a field may straddle two words, signed fields are two's complement of their
width (1…16 bits).

`decode(track)`:

1. If the track has no slot, take one (3.1) and link them. Move the slot to the most
   recently used end.
2. `T = int(time)`. **If `T < slot.keyTick` the slot starts over**: key tick = 0, and for
   every joint in order: `ptick = rtick = 0`; 4 bits *w*−1; three *w*-bit values
   `pos = float(v) × 1/64`; 4 bits *v*−1; four *v*-bit values in the order **w, x, y, z**,
   `quat = float(v) × 1/4096`; both velocities 0. For a ROOT track the x and y of joint 0
   are skipped in the stream and **keep their slot values** (the root-motion base). Then
   the cursor is stored and `slot.yaw = heading(joint 0's quaternion)` (3.2).
3. Repeat: read 8 bits *d*; if `T < keyTick + d` stop (the cursor does not move).
   Otherwise `keyTick += d`, then 1 bit kind (1 = position), 6 bits joint, 4 bits *w*−1 and
   three or four *w*-bit values:
   - position: `pos += vel × float(keyTick − ptick)` (each component: product, then sum);
     `vel = float(v) × 1/256`; `ptick = keyTick`.
   - rotation: `quat += qvel × float(keyTick − rtick)`; `qvel = float(v) × 1/131072`
     (file order w, x, y, z); `rtick = keyTick`.

There is no end-of-stream test: decoding stops because the next record's tick is beyond
`T` (the exporter ends every stream with a delta of 255).

The value of a joint at the track time *t* — the float, not *T* — is formed by each reader:

```
position   = pos  + vel  × (t − float(ptick))
quaternion = quat + qvel × (t − float(rtick))        (normalised only by the pose builder)
```

Consequences an implementation must keep:

- **Forward only.** Stepping forward is incremental; any step back (a loop wrap, a seek,
  a time below the slot's key tick) re-decodes from the initial pose. Because `pos` is
  advanced key by key with float products, the values reached incrementally and after a
  restart are the same sequence of operations, so they are bit-identical (**X**: the test
  seeks back and forward on every clip).
- A negative time gives `T = 0` for −1 < t < 0 (truncation) and a restart on every call
  for t ≤ −1.
- A key's joint index is not checked against the joint count; the slot always has 64
  records, and records of joints the clip does not have keep older contents.

### 3.1 `animcache_alloc` 0x16e388 (**X**)

Take the slot at the least-recently-used end. While that slot's owner cell has ROOT or YAW
in its flags, move the slot to the other end and look at the next one. (If every slot is
pinned this never returns; with 165 slots that needs 165 root-motion tracks.) The previous
owner's slot pointer is zeroed. Reset in the slot: key tick = 1000000, joint 0's `pos.x` and
`pos.y` = 0.0, owner = 0. **Everything else is left as it was**, including `yaw`.

### 3.2 Heading of a quaternion (**X**)

```
heading(x, y, z, w) = atan2_16(S + S, ((x·x − y·y) − z·z) + w·w)      S = x·y + z·w
```

`math_atan2_16` (0x166798) is the C library's `atan2f` times 10430.378, truncated to 16
bits (`docs/spec/core.md`). `quat_stripYaw` (0x16caa8) removes it:
`q ← quat_fromAxisAngle((0, 0, 1), −heading) ⊗ q`.

## 4. Track operations (**X** for every row)

`rate(s)` = 1.0 when `s < 1/60` (pattern 0x3c888888), else `1.0 / (s × 60.0)`.

"New cell" means: `count = index + 1`; `state.flags |= flags`; clip, time and (except where
noted) sound cursor = 0 are stored; a slot pointer found in the cell is released (its
owner zeroed); flags stored. None of the functions in this table except the two "to end"
ones detaches the pose.

| Function | Rule |
|---|---|
| `anim_clear` 0x1707b0 | `count = 0`, nothing else |
| `anim_push` 0x170838 (state, clip, flags) | nothing when clip is null or `count ≥ capacity`; else new cell at index count: weight 1, rate 0, life 1, life rate 0, time 0 |
| `anim_pushWithWeights` 0x1708c0 (f12 unused, f13 weight, f14 rate, f15 life, f16 life rate; state, clip, flags) | as `anim_push` with the four values given |
| `anim_pushChained` 0x170938 | as `anim_push` with `time = (below.time − float(below.length)) + 2.0`, where *below* is the current top track. Normally negative: the track waits and starts two ticks after the one below ends. The sound cursor is **not** reset: the cell keeps the cursor of the last track that lived in it (section 6). On an empty state it reads the cell before the array |
| `anim_start` 0x16cfe0 (f12 blendIn; state, clip, flags) | index = count if `count < capacity`, else count − 1 (**the top track is replaced**, its slot released). If index is 0 the blend time is forced to 0. New cell: weight 0, rate = rate(blendIn), life 1, life rate 0 |
| `anim_startBlendInOut` 0x16ceb0 (f12 blendIn, f13 blendOut; …) | same index rule, blend-in **not** forced to 0 in cell 0. weight 0, rate = rate(blendIn), `r = rate(blendOut)`, life rate = −r, `life = ((float(length) × 1/60) × 60.0) × r` |
| `anim_stop` 0x16d1a0 (f12 blendOut; state, clip) | for each track playing clip: if `blendOut == 0`: `anim_releaseCaches` on the whole state, remove the track (cells above move down), continue with the same index; else: weight = min(weight, 1) (only written when above 1), rate = −rate(blendOut), life capped at 1, life rate 0, flags &= ~0x1004 |
| `anim_dropNonPersistent` 0x16cb50 | remove every track without 0x1000; a kept track that moves takes its slot (owner pointer updated, old cell's slot pointer zeroed) |
| `anim_releaseCaches` 0x171118 | detach the pose (state.pose = 0, buffer owner = 0) and release the slot of every track in use |
| `AnimState_dtor` 0x171098 | the same over every cell up to the capacity |
| `anim_syncToSimFrame` 0x1709f8 | every track: `time = fmodf((float(g_simFrame) × 1/60) × 60.0, float(length))`; ROOT tracks are rebased |
| `anim_randomizeTopTime` 0x16d0b8 | `seed = seed × 0x19660d + 0x3c6ef35f` on `g_cosmeticSeed`; top track `time = (float(seed >> 16) × 1/65536) × float(length)`; ROOT rebased |
| `anim_jumpTopToEnd` 0x170bc8 | detach the pose; top track `time = float(length)`; ROOT rebased |
| `anim_snapTopToEnd` 0x170c80 | detach the pose; top track weight = life = 1, `time = float(length)`; no rebase |
| `anim_findTrack` 0x170d88 | first track playing clip, or 0 |
| `anim_findTrackByFlag` 0x171178 | index of the first track with `flags & mask`, or −1000000000 |

**Rebase** (the same instructions at 0x16d140, 0x170a7c, 0x170b64, 0x170c20): decode the
track at its new time, compute joint 0's `x = pos.x + vel.x × dt`, `y` likewise, and
subtract them from `pos.x`, `pos.y`. The jump in time is thereby not reported as movement.

A track that `anim_stop` fades is **not removed when its weight reaches 0**: `anim_advance`
removes by life only. Its weight keeps falling below 0 (blend weight 0) and the cell stays
occupied until the track ends (if it does not loop), is purged by a PURGE_BELOW track
above, or is replaced because the state is full.

Four more functions in the range have no caller that was found (**O**, **X**; proposed names):

| Address | Proposed name | Rule |
|---|---|---|
| 0x170b08 | `anim_syncTopToBelow` | with ≥ 2 tracks: top time = time of the track below, or 0 if that is ≥ the top clip's length; ROOT rebased |
| 0x170e00 | `anim_fadeInTrack` (f12 seconds; state, clip) | weight = max(min(weight, life), 0), rate = rate(seconds), life = 1 |
| 0x170ee8 | `anim_fadeOutTrack` (f12 seconds; state, clip) | weight = min(min(weight, life), 1), rate = −rate(seconds), life = 0 |
| 0x170fc8 | `anim_setTrackWeight` (f12 weight; state, clip) | weight as given, life 1, both rates 0 |

## 5. The step — `anim_advance` 0x16d748 (**X**)

`events = anim_advance(f12 speed, a0 state, a1 soundPos or 0, a2 float rootDelta[2] or 0,
a3 s16 *yawDelta or 0)`.

```
step = speed × 0.99999994
if state.pose: pose.owner = 0; state.pose = 0            # every step detaches the pose
rootDelta = (0, 0); *yawDelta = 0; events = 0; union = 0; left = 1.0

for i = count−1 down to 0:                               # TOP track first
    a. union |= flags
       lo = time × 1/60;  hi = lo + step × 1/60          # the OLD time; `step` even for
       for each of the clip's 4 event slots:             #   paused / fixed-step tracks
           if lo ≤ slot.seconds < hi: events |= slot.mask
    b. if not PAUSED: time += (FIXED_STEP ? 0.99999994 : step)
       if time < 0: continue                             # a waiting track only counts up
    c. sounds (section 6) — top track only, only when soundPos ≠ 0
    d. raw = min(weight, life)
       w = min(raw, left); if w > 1: w = 1; if w < 0: w = 0
       if clip.jointMask == 0: left −= max(raw, 0); if left < 0: left = 0
    e. if float(length) ≤ time:
         LOOP:
            ROOT: time = length; decode; (x, y) = joint 0 x/y at length;
                  slot base x, y = 0; rootDelta += (x, y) × w; time restored
            YAW:  time = length; decode; h = heading(joint 0 quaternion at length);
                  *yawDelta += h − slot.yaw (16-bit); slot.yaw = h; time restored
            repeat: time −= float(length)  until time < float(length)
         else REPORT_END:
            time = float(length); union |= 0x80; if i is the top track: union |= 0x400
         else:
            life = 0; life rate = 0
    f. weight += rate × speed;  life += lifeRate × speed       # FIXED_STEP: not × speed
       (the multiplier is `speed`, not `step`)
    g. if life ≤ 0 and not KEEP: remove track i (cells above move down, their slots'
          owner pointers follow, the vacated top cell's slot pointer is zeroed)
       else if PURGE_BELOW and min(weight, life) ≥ 1 and i > 0:
          remove every track below i that lacks PERSISTENT, compact, and LEAVE THE LOOP

state.flags = union

if union has ROOT:                                       # second pass, top down
    left = 1.0
    for i = count−1 down to 0:
        raw, w, left as in step d, but with the weights as they are NOW (after step f)
        if ROOT: decode; (x, y) = joint 0 x/y at the track time
                 slot base −= (x, y);  rootDelta += (x, y) × w

if state.flags has YAW:                                  # third pass, bottom up
    for each YAW track: decode; h = heading at the track time
                        *yawDelta += h − slot.yaw (16-bit);  slot.yaw = h
return events                                            # a signed byte
```

Details that are easy to get wrong (**X** unless marked):

1. **Purge ends the loop.** When a PURGE_BELOW track fires, the tracks below it that
   survive (PERSISTENT) are not stepped on that tick: no time, no events, no weight
   change, and their flags do not join the union. The test is made again on every later
   tick, so those tracks stay **frozen for as long as the PURGE_BELOW track sits above
   them at full weight**, and start moving again when it is gone. A purge with `i == 0`
   does nothing.
2. **Removal is by life only**, and only in step g. A track whose weight is ≤ 0 stays.
3. **Two root-motion weights.** The part of the displacement up to the end of the clip is
   weighted with the weight *before* the update (step d); the part from the last step (or
   from tick 0 after a wrap) with the weight *after* it, and with a fresh `left`. A track
   that is removed in step g contributes only its wrap part. A waiting track (time < 0)
   is not skipped by the second pass.
4. **`left`** is reduced only by clips whose joint mask is zero; partial-body clips do not
   use up weight. It is reduced by `max(raw, 0)`, not by the clamped `w`.
5. **Yaw is not weighted** and is summed over all YAW tracks.
6. **Root motion without an output pointer is a null write**; callers that pass 0 must not
   hold a ROOT (or YAW) track. `Player_animStep` passes no yaw pointer.
7. The union includes the flags of tracks removed during the call, so `state.flags` can
   show ROOT for one tick after the last root-motion track ended.
8. The x/y of a root-motion track is exactly the change of joint 0's x/y track; the clip's
   initial x/y is never read (section 3, step 2). Across a restart of the decoder the base
   carries the part already reported, with opposite sign, so the sum is continuous.
9. With `speed` 1 a 60-tick clip needs 61 steps to reach its end the first time
   (60 × 0.99999994 < 60); time is not an integer after the first step. Event tests and
   `int(time)` see those fractions.

## 6. Sound events inside the step (**X** for the cursor and the ranges; playing is not modelled)

Only for the top track, only if the clip has a sound table and `soundPos ≠ 0`. With `old`
the time before the step, `t` after it, `e[k]` the tick of event *k* as a float, `c` the
cursor:

```
if c > 0 and old ≤ e[c−1]: c = 0                         # time went back
while e[c] < old: c += 1                                 # skipped without sound
muted = false
if group ≠ 0:
    if throttle[group].frame ≠ low byte of g_drawFrame: throttle[group] = (frame, 1)
    else if limit[group] − 2 < throttle[group].count: muted = true
    else: throttle[group].count += 1
while e[c] < t:
    end = one past the run of events with the same tick as event c
    if not muted: animsound_fireRange(clip, c, end, soundPos)
    c = end
if float(length) ≤ t and LOOP:                           # tested before the wrap of step e
    t2 = t − float(length);  c = 0
    if e[0] < t2: do { end = …; fire unless muted; c = end } while e[c] < t2
```

**Cursor left by an earlier track.** `anim_pushChained` does not reset the cursor, and
the code above indexes the event table without a bound. If the cell's old cursor lies
beyond the new clip's table, `e[c−1]` and `e[c]` are read from whatever memory follows the
table. With the usual negative start time the first test (`old ≤ e[c−1]`) resets the
cursor as long as that word is not negative as an integer; with a start time ≥ 0 (the
track below was within two ticks of its end, or held there) the skip loop walks through
foreign memory. Executed: a cursor of 47 left in the cell, a two-entry table and a start
time of 2.0 made the loop at 0x16d988 run until it left mapped memory in the interpreter.
Only the cursor and the sounds depend on it; a reimplementation should reset the cursor
(the model raises `HostFault` for a cursor outside the table).

The limiter reads `g_drawFrame`, which differs between machines, but it only gates
`animsound_fireRange`; the cursor moves the same either way (**X**: the cursor is part of
the compared state under random frame numbers). What is *not* the same on every machine
is the cosmetic random generator, which `animsound_fireRange` advances (0x16d558,
0x16d360; **O**, not modelled) and `anim_randomizeTopTime` reads.

## 7. From the step to the simulation

### 7.1 `Creature_stepAnim` 0x1162b0 (**X** for everything after the two multipliers)

```
speed = argument
if kind (s16 +0x232) == 3: speed ×= player_speedScale(−1)             (O, not executed)
if s16 +0x31a > 0 and a Drowsy spell is attached: speed ×= its fraction (O, not executed)
slow = u8 +0x2fc
if bit 63 of the u64 at +0xa8 ("active"):
    s = speed;  if 1 ≤ slow ≤ 60: s = (speed × float(60 − slow)) × 1/60
    events = anim_advance(s, +0x114, (flags & 0x2000000) ? 0 : +0x10, +0xbc, +0xc4)
else events = 0                         # no step; +0xbc / +0xc4 keep their old contents
(dx, dy) = (+0xbc, +0xc0) × scale (+0xdc)
a = facing (s16 +0x38) − 0x4000;  c = cos16(a);  s = sin16(a)
+0xbc = (−dx)·c + dy·s;   +0xc0 = (−dx)·s − dy·c
if 1 ≤ slow ≤ 60:
    f = float(60 − slow) × 1/60
    +0xc0 ×= f;  +0xbc ×= f
    +0xc4 = +0xc4 × int(f)             # int(f) is 0: a slowed creature gets no root yaw
return events
```

Two things to note. The yaw is multiplied by the **integer part** of the factor, which is 0
for every slow amount from 1 to 60 (**X**); `docs/engine.md` describes it as scaled like
the displacement. And for an inactive creature the delta left at +0xbc by the previous call
— already rotated and scaled — is scaled and rotated again on every call (**X**).

### 7.2 `Player_animStep` 0x1b9520 (**X**)

The speed is slowed the same way; `soundPos` is 0 when bit 0x200000 of the word at +0x0c is
set; the yaw pointer is 0; the delta is rotated by `facing − 0x4000` and is neither scaled
nor slowed.

### 7.3 Events

The return value is the OR of the mask bytes of all event slots passed on this tick by any
track, fading and waiting ones included. The engine attaches no meaning to the bits; the
class's state handler does. The four `{seconds, mask}` slots are zero in every file and
are filled in by constructors after loading (`creature_setDefEntryParams` 0x118378 and the
inline writers listed in `docs/formats/anim-audio.md` 2.7), so a rebuild needs those tables
from the code. An event fires on the step where

```
time × 1/60 ≤ seconds < time × 1/60 + (speed × 0.99999994) × 1/60
```

with the pre-step time, so each event fires exactly once per pass when the step is
constant, and can fire twice or not at all when the speed changes between two steps
(the two intervals overlap or leave a gap) — the original has the same behaviour.

## 8. The pose

### 8.1 `anim_buildPose` 0x16ed40 (a0 state, a1 forDraw) (**X**, VU0 part see 8.3)

1. **Buffer.** Walk the pose list from the oldest end; take the first buffer with
   `stamp < g_drawFrame − 3` (signed). The buffer at the newest end is never taken. If
   none: a draw caller ends with `state.pose = 0`; any other caller uses the fallback
   buffer 0x7b89c0. `state.pose` is set to the buffer at once.
2. **Base track.** From the top track down, among tracks with `min(weight, life) ≥ 1` and
   `time ≥ 0`: AND their joint masks; the track at which the result becomes 0 is the base.
   None: `state.pose = 0`, return (the buffer keeps its owner and contents).
3. The buffer's previous owner gets `pose = 0`; owner = this state; the buffer moves to the
   newest end of the list (the fallback buffer is not in the list).
4. Decode the base track. For each joint *j* of the **base clip**: local quaternion and
   position at the track time (section 3). YAW: `quat_stripYaw` on joint 0. ROOT: joint 0's
   x = y = 0.
5. For every track above the base, in order, with `time ≥ 0`:
   `w = min(max(min(weight, life), 0), 1)`; EASE: `w = hermite(w, 0, 1, 0, 0)`
   (`math_hermite` 0x1658f0); skip the track if `w < 0.001`. Decode it. For each joint *j*
   below the base clip's joint count whose bit in this clip's joint mask is clear:
   - `q2` = this track's quaternion (YAW: stripped for joint 0);
   - if `Σ(q1 + q2)² < Σ(q1 − q2)²` (sums in the order w, x, y, z) negate `q2`;
   - (the w component then goes through an angle-style ±2π unwrap against `q1.w`; it
     cannot trigger for quaternion-sized values);
   - `q1 = q1 × (1 − w) + q2 × w` per component; position the same, except that for joint
     0 of a ROOT track x and y become `x × (1 − w)`, `y × (1 − w)`.
6. Header: joint count = base clip's; tag as in 2.4.
7. Normalise each quaternion: `q × (1 / sqrt(((w² + x²) + y²) + z²))` (`rsqrt.s`), and
   compose (8.3) with the depth list and bind offsets of **the top track's clip** —
   whatever that track's weight or time. All clips of one model carry the same skeleton,
   so this shows only if clips of different skeletons are mixed in one state.
8. If the joint count is below 64, the matrices of joint *n* are written as zeros.

The blend loop runs over the base clip's joint count and reads the other tracks' slots for
those indices whatever their own joint count; a slot keeps 64 records (2.3).

### 8.2 Pose cache rules (**X**: owner, list order and stamps are compared after every operation)

- A state's pose pointer is cleared by: `anim_advance` (every call), `anim_jumpTopToEnd`,
  `anim_snapTopToEnd`, `anim_releaseCaches`, `AnimState_dtor`, `AnimState_copy` (in the
  copy), and by `anim_buildPose` when another state takes the buffer or no base track is
  found. Nothing else clears it — in particular not push, start, stop, clear, sync or
  randomize.
- `anim_getJointMatrix` builds only when the pointer is 0. Otherwise it converts whatever
  is attached, however old.
- `anim_emitPose` 0x16f880 (drawing): a pose in the fallback buffer is detached first; a
  state without a pose gets one built with forDraw = 1; then the buffer is stamped with
  `g_drawFrame` and moved to the newest end. With no pose the default pose is drawn.
- Only drawing stamps. A buffer filled by a simulation query keeps its old stamp and is
  taken again as soon as the walk reaches it.
- The values in a pose do not depend on which buffer holds it (**X**: runs with the list
  cut to 5 buffers give the same matrices through the fallback buffer).

### 8.3 Composition: the VU0 microprogram at 0x3e5c50 (**O** instruction by instruction; **X** against an interpreter of the same instruction words, see section 12)

The packet at 0x3e5c40 loads 77 instructions at VU0 address 0. `anim_buildPose` calls entry
2 once, then entry 4 once per joint. The matrix stack lives in VU0 data memory: level *d*
occupies quadwords 3d … 3d+2, one row `(r0, r1, r2, t)` each.

Entry 2: level 0 = identity.

Entry 4, inputs: quaternion `(x, y, z, w)`, position `p`, bind offset `b` (integers
`s16 × 64`, converted with ITOF12, i.e. `b/64`), depth `d`:

```
x2 = x + x;  y2 = y + y;  z2 = z + z
xx = x·x2  wx = w·x2   xy = x·y2  yy = y·y2  wy = w·y2   xz = x·z2  yz = y·z2  zz = z·z2  wz = w·z2
L0 = ((1 − yy) − zz,  (0 + xy) − wz,  (0 + xz) + wy,  p.x)
L1 = ( xy + wz,       (1 − xx) − zz,  (0 + yz) − wx,  p.y)
L2 = ( xz − wy,        yz + wx,       (1 − xx) − yy,  p.z)
P  = level d (three rows)
W_r[c] = ((L0[c]·P_r[0] + L1[c]·P_r[1]) + L2[c]·P_r[2]) + e[c]·P_r[3]     e = (0, 0, 0, 1)
level d+1 = W
t_r = (((b.x·W_r[0] + b.y·W_r[1]) + b.z·W_r[2]) + 1·W_r[3]) × 4.0
out row r = ( FTOI12(W_r[0]), FTOI12(W_r[1]), FTOI12(W_r[2]), FTOI4(t_r) )
```

FTOI12 / FTOI4 multiply by 4096 / 16 and truncate toward zero (so the translation is
× 64); the CPU then keeps the **low 16 bits** of each (`ppach`), without saturation: a
translation beyond ±512 units wraps.

So `W = P · L` (parent first, column vectors: `v' = R·v + t`), and the stored translation
is `W.R · b + W.t`: the matrix takes bind-pose model-space points straight to posed model
space. Levels deeper than 0 keep what the previous joint at that depth wrote — across
builds too — so a depth list that starts above 0 or skips a level reads old matrices.

### 8.4 `anim_getJointMatrix` 0x16f720 (state, joint, out mat34) (**X**)

Build if `state.pose == 0`; read the default pose if it is still 0. Clamp the joint to
`0 … jointCount − 1`. With `m[k]` the buffer's row *k* of that joint:

```
out[3·r + k] = float(m[k][r]) × 1/4096      (r, k = 0…2)
out[9 + k]   = float(m[k][3]) × 1/64
```

`out` is the engine's row-vector `mat34` (a point is `v·M + t`), i.e. the transpose of the
stored rotation. The simulation therefore sees the pose quantised to 1/4096 and 1/64.

### 8.5 `model_getAttachPoint` 0x1754a0 (**X**)

`(f12 scale, a0 model, a1 pos, a2 facing, a3 state or 0, t0 index, t1 posOut or 0,
t2 dirOut or 0)`. Record = `model + 16 × u8(model+0x22) + 0x34 × index`: joint at +0x00,
direction at +0x10, origin at +0x28. `M` = joint matrix (identity when state is 0).

```
p = mat34_transformPoint(M, origin);  d = mat34_rotateVec(M, direction)
a = facing − 0x4000;  c = cos16(a);  s = sin16(a)
X = p.x × scale;  Y = p.y × scale;  Z = p.z × scale
posOut = ( ((−X)·c + Y·s) + pos.x,  ((−X)·s − Y·c) + pos.y,  Z + pos.z )
dirOut = ( (−d.x)·c + d.y·s,  (−d.x)·s − d.y·c,  d.z )            (not scaled)
```

### 8.6 `model_getSamplePoint` 0x178e18 (**X**)

`(f12 scale, a0 model, a1 state or 0, a2 pos, a3 facing, t0 index, t1 posOut,
t2 radiusOut or 0, t3 mat3Out or 0)`. Block = `model + 16 × u8(model+0x24)`; count at +4;
point *i* at `block + 0x20 + 8·i + 16·(i / 45)`: `s16 x, y, z, word`.

```
if index ≥ count: p = (0, 0, 0); radius = 0; mat3Out = identity
else:
    M = joint matrix of joint (low byte of word) >> 2   (identity without a state)
    p = mat34_transformPoint(M, (x, y, z) × 1/16)
    radius = float(word as s16) × scale                 (the whole word, joint bits included)
    mat3Out = M's rotation with columns 0 and 1 turned by facing − 0x4000 (0x162df0)
a = facing − 0x4000
posOut = ( ((−p.x)·c + p.y·s) × scale + pos.x,  ((−p.x)·s − p.y·c) × scale + pos.y,
           p.z × scale + pos.z )
```

## 9. Copying a state — `AnimState_copy` 0x16ffe8, `AnimState_copySmall` 0x16fbc8 (**X** for the first)

0x108 bytes (header and eight cells; the small variant 0x28 bytes, one cell) are copied,
the copy's pose pointer is zeroed, and for each cell up to the capacity: no slot if the
source cell has none or the cell has neither ROOT nor YAW; otherwise a slot from
`animcache_alloc` whose stream pointer, cursor, key tick and all 64 joint records are
copied from the source's slot. **`yaw` at slot+0x18 is not copied** and the allocator does
not reset it: the first root-yaw step of the copy measures from whatever the slot held
before. (Whether any state that is copied holds a YAW track was not checked — **U**.)

## 10. Order within a frame

For one animated object on one simulation tick (**O** for the calls, **I** for "typical"):

1. The object's run function changes tracks (start, push, stop …) and calls its step
   wrapper once (`Creature_stepAnim` / `Player_animStep`; scenery is stepped from draw
   code with `anim_advanceUnitSpeed` 0x1709d8, speed 1). The step detaches the pose.
2. The returned event bits and `state.flags` (status 0x80 / 0x400) drive the state
   handler; the world-space delta at +0xbc/+0xc0 and the yaw at +0xc4 are applied by the
   creature movement code (`docs/engine.md`, `docs/spec/movement-camera.md`).
3. Skeleton queries (attach points, sample points) build the pose on first use and reuse
   it until the next step. Track changes made after that build are not seen by later
   queries of the same tick (8.2).
4. Drawing, zero or more times per tick, builds a pose if none is attached, stamps it and
   keeps it attached.

Inside one `anim_advance` the order is the listing in section 5: per track events → time →
sounds → weights for the wrap → end handling → weight update → removal/purge; then the
root pass, then the yaw pass.

## 11. Hazards for a reimplementation

- Use the constants of section 1 as patterns and keep the operation order; time is
  accumulated in floats over thousands of ticks and compared with integers.
- Keep decoder slots of ROOT / YAW tracks alive and private per track; they are state.
- Keep the track cells as cells (2.1), or prove the stale reads cannot matter.
- Do not "fix" the purge that ends the loop, the removal by life, the unweighted yaw, the
  zeroed yaw of a slowed creature or the 0.99999994 step: they change event ticks and
  positions.
- The pose is quantised (s16) before the simulation reads it. A rebuild that hands
  float matrices to attach-point queries will place projectiles differently.
- What a query returns depends on the pose cache (8.2); see `docs/issues/pose-cache.md`.

## 12. What the differential test covers

`python3 tools/difftest_anim.py [SLUS_209.73] <directory of .anm files> [--quick] [--all]`

The original functions run under `tools/ee_emu.py`; each clip file is copied into memory
and relocated by the game's `anm_relocate`; the pools are set up by the game's `anim_init`.
Every operation is applied to both sides and the original's memory is then compared byte
for byte with an image built from the model. "Bit for bit" means identical under the
interpreter's floating-point model; each property is repeated on a smaller sample under
the interpreter's three other adder models and with its multiplier-bias and
divide-rounding switches, with the model switched the same way
(`docs/issues/dynamic-tests.md`, "Floating point"). Agreement under all six shows the same
operations in the same order; it does not show what a console does in the last bit.

RESULTS_TABLE_PLACEHOLDER

Not covered, and why:

- **The vector unit itself.** `tools/ee_emu.py` has no COP2 and no VU. The test hooks the
  seven COP2 instructions of `anim_buildPose` (two `lqc2`, `qmtc2`, `ctc2`, two `vcallms`
  targets, three `qmfc2`) and interprets the microprogram's own words with the
  interpreter's FPU add and multiply. The pose properties therefore show that the model
  does what those instructions say, in their order. Whether the hardware's VU adder and
  multiplier round every case like the FPU model is not established here (**U**); after
  truncation to s16 a last-bit difference shows only when a product lands within one unit
  of an integer boundary.
- **Sound playback** (`animsound_fireRange` and below) is stubbed; the ranges it is called
  with are compared. Its draws from the cosmetic generator are not modelled.
- **The two multipliers at the top of `Creature_stepAnim`** (player speed scale, Drowsy)
  are bypassed by the test objects.
- **`anim_emitPose`'s display-list output**: only which buffer it sends, and the cache
  side.
- **`AnimState_copySmall`**: read, not executed.
- Clips are used as they are on the disc, plus random event slots; no synthetic stress of
  16-bit field widths beyond what the disc contains (the unit tests exercise the model's
  own encoder/decoder round trip, without the original).
- States with all decoder slots pinned, `anim_pushChained` on an empty state or onto a
  cell whose old sound cursor lies beyond the new clip's event table, root motion without
  an output pointer, clips of length 0 that loop: the original does not return, writes
  through a null pointer or reads foreign memory; the model raises `HostFault` and the
  test's sequences stay clear of them.

## 13. Corrections to earlier documents

| Document | Says | Found |
|---|---|---|
| `docs/engine.md`, "Root motion in a creature" | delta and yaw are multiplied by (60 − slow)/60 | the yaw is multiplied by the integer part of that factor, i.e. set to 0 (0x11648c–0x116498) |
| `docs/engine.md`, `anim_advance` step 2 | "one tick with flag 0x40" | 0.99999994 (pattern 0x3f7fffff), the same constant the speed is multiplied by (0x16d8cc) |
| `docs/engine.md`, step 1 | `time/60 ≤ s < (time+step)/60` | `time×(1/60) ≤ s < time×(1/60) + step×(1/60)`, with `step` also for paused and fixed-step tracks (0x16d838–0x16d888) |
| `docs/engine.md`, step 5 | a 0x0002 track "removes the tracks under it" | and the loop over tracks ends there: surviving lower tracks are not stepped that tick (0x16e0b8) |
| `docs/engine.md`, track table | `anim_start`: "the first track of an empty state reaches full weight on the next tick" | true for cell 0 in general (also a full state of capacity 1); `anim_startBlendInOut` does **not** have this rule |
| `symbols/engine.tsv`, `anim_pushWithWeights` | (w, dw, w2, dw2, state, anm, flags) | the four values are f13…f16; f12 is passed by the callers (0x237a48) and not read |
| `symbols/engine.tsv`, `AnimState_copy` | 0x100 bytes | 0x108 bytes; the slot's yaw baseline is not copied (0x170130–0x170154) |
| `docs/formats/anim-audio.md` 2.5 | the VU0 program is at 0x3e5c40 | 0x3e5c40 is the DMA/VIF packet; instruction 0 is at 0x3e5c50. Bind offsets and depth list are those of the top track's clip (0x16f57c) |
| `docs/formats/anim-audio.md` 2.6 | the displacement is added "times the track's weight" | two weights: before the weight update for the part up to the clip's end, after it for the rest (section 5, note 3) |

## 14. Not established

- Whether the console's vector unit matches the FPU model in the last bit of the
  composition (section 12).
- Whether any copied state (prediction copy) holds a YAW track, i.e. whether the uncopied
  yaw baseline (section 9) is reachable.
- The meaning each class gives to event bits, and the event tables written by player code.
- Callers of the four unnamed helpers in section 4, if they are reached through pointers.
