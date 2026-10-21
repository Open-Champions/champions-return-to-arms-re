# Movement, collision and camera — implementation specification

What a rebuild has to reproduce so that a character moves, collides and is framed exactly as
in `SLUS_209.73`. Sections 2–6 are simulation code: in a net game every machine must get the
same bits out of them. Section 7 (the camera) is per machine; only two values cross from it
into the simulation, and section 7.1 says which.

Everything was read from the executable; nothing was run when it was written. Since then
parts have been executed function by function in `tools/ee_emu.py`
(`docs/issues/dynamic-tests.md` group m, `docs/spec/player-tick.md`), and the player's run
speed of section 4.1 has been measured on the live game — in the Play! emulator, not on a
PlayStation 2 and not in PCSX2 (`docs/issues/live-rig.md` 4c, 4d; `FINDINGS.md`, "Run on
the live game", row V3): 2.585831–2.585844 units per tick offline against 180 × 0.861945 /
60, from the first tick and along a facing that is still turning, 2.25000 per tick in a
net game, and linear in the stick value. Collision, the monster movement helpers and the
camera were not re-checked there. No test patch has been run on a live game. Marks: **[O]** Observed at the
address given, **[I]** Inferred, **[U]** Unknown. A paragraph or table without a mark is
[O] at the addresses in its section heading. Names are those of `names.tsv` and
`symbols/*.tsv`; new ones are in `symbols/movement.tsv`.

How deeply each function was read:

- **Instruction by instruction** (operand order of every float operation checked):
  `pad_decodeStick` 0x174ce0, the stick part of `pad_apply` 0x174410, `Player_move`
  0x1b4020, `Player_animStep` 0x1b9520, `math_cos16` 0x166630, `math_sin16` 0x1666e0,
  `math_atan2_16` 0x166798, `angle_approach` 0x166c18, `obj_moveWithCollision` 0x14d4b8,
  `world_slideMove` 0x14d238, `terrain_sweepCircle` 0x185a40, `Creature_moveBy` 0x113c48,
  `Creature_turnToward` 0x10bb08, `Creature_stepAnim` 0x1162b0, `net_getCamYaw` 0x13e0c8,
  `net_getCamFlag` 0x13e110, the yaw sampling in `net_main` 0x133464–0x1334a8.
- **From the decompile, spot-checked in the disassembly**: `terrain_collectElements`
  0x183248, `terrain_heightBelow` 0x1834a8, `terrain_height` 0x183820,
  `world_collectObjectsInBox` 0x14a928, `obj_moveAndCollide` 0x1509f8,
  `Creature_applyKnockback` 0x115eb8, `Creature_moveTo` 0x114510 and the other approach
  helpers, the slow-amount block of `Creature_run`, the parts of `Player_run` 0x1a5030 and
  `Player_processDamage` 0x1b2cc0 that are cited, `Player_clampToScreen` 0x1b3d90, and every
  camera function. Formulas from these give the arithmetic but **not** a checked operand
  order; they are marked *(dec)*.

## 0. Conventions

| | | |
|---|---|---|
| Time step | one simulated frame = 1/60 s. The constant used everywhere is `DT` = 0x3c888888 (0.016666666), which is below the nearest float to 1/60 (0x3c888889) | [O] |
| Position | object +0x10, +0x14, +0x18 = x, y, height (floats, world units) | [O] |
| Velocity | world units per second; multiplied by `DT` inside the move routines | [O] |
| Angle | signed 16 bits, 65536 per turn. Facing (object +0x38) 0 points along +x, 0x4000 along +y: a creature moving "forward" gets velocity (cos F, sin F) | [O] 0x114b88–0x114ba0 |
| Radius, height | object +0x1c, +0x20. Defaults 24 and 72 (`GameObject_ctor`, `docs/objects.md`). `Player_ctor` stores radius 12.0 (0x41400000) and no height, so a player's is 72 unless something outside the constructor changes it. `Creature_init` sets a monster's height to its model's vertical extent, at least 84.0; monster radii are set per class | [O] 0x1a1d28, 0x10a230 *(dec)*; [I] player height |
| Vertical velocity | object +0x30, units per second | [O] |
| Constants | given as IEEE-754 bit patterns. Use the bits, not the decimal: this toolchain stored decimal literals rounded toward zero (1.2 is 0x3f999999, 0.4 is 0x3ecccccc, 0.001 is 0x3a83126e) | [O] bits; [I] cause |

In pseudo-code every `+ − × /` is **one single-precision operation, evaluated in the order
written, left to right, parentheses first**. `f32(i)` is the integer-to-float conversion,
`int(x)` the float-to-integer conversion (the hardware truncates toward zero), `s16(i)` keeps
the low 16 bits as a signed number. Section 8 lists what the hardware does differently from
a PC.

## 1. Order of work in one simulated frame

Offline, `tasks_run` 0x3226e4 calls the run tasks by priority: object visibility (−1),
`runObjects` (10), `task_camera` (11), scripts (125), cutscene (300). In a net game
`net_frameLoop` 0x139e88 first, for every peer in slot order, decodes that peer's input
record, rebuilds `g_pads[slot]` with `pad_apply`, stores the record's yaw word in
`g_netCamYaw[slot]` and runs the peer's game messages; then it calls `tasks_run`, then
`path_service(1)`, then hashes the players' integer positions. [O] `docs/netcode.md`,
`docs/OVERVIEW.md`; not re-read here.

`runObjects` 0x14b910 calls virtual slot 4 of each object: the every-frame list (most
recently linked first), then list `frame % 15`, then list `frame % 60`. [O] `docs/objects.md`.
The order matters to collision because **an object only ever moves itself** (section 5.9).

Inside `Player_run` 0x1a5030, per frame, the parts that concern position:

1. `Creature_run` (0x1a5248): timers and the slow amount (section 4.6).
2. `Creature_applyKnockback(1.0)` (0x1a5254): section 4.8.
3. If the creature's inert byte +0x231 is non-zero (cutscene control): in action state 1 the
   player is walked with the monster helper `Creature_moveToDest` (call at 0x1a5604),
   otherwise only animated; return. *(dec)*
4. Choice of the pad: the real `g_pads[slot]`, or an all-zero pad at 0x8667f0 (section 4.5).
5. The action state code, which calls `Player_animStep` and then `Player_move` (table in
   section 4.4). The one exception to that order is the bow "aim" branch of state 2.

A monster class's run function calls, in an order of its own, `Creature_run`,
`Creature_processDamage`, a turn (slot 26), `Creature_stepAnim` and one of the move helpers
of section 6. [O] for the helpers; per-class order not read here — see `docs/monsters.md`.

## 2. From the pad to a stick vector

Functions: `pad_apply` 0x174410, `pad_decodeStick` 0x174ce0.

`pad_apply(pad, rec, prev)` receives the 8 bytes at input record +4: u16 buttons, then six
bytes. The four stick bytes are read unsigned.

```
pad.lx, pad.ly (+0x14, +0x18) = decodeStick(rec[2], rec[3])     movement stick
pad.rx, pad.ry (+0x1c, +0x20) = decodeStick(rec[4], rec[5])     camera stick

decodeStick(bx, by):
    x = f32(bx - 128) × 0x3c000000          (1/128, exact)
    y = f32(by - 128) × 0x3c000000
    m = sqrt(x×x + y×y)
    if m < 0x3ea3d70a:  return (0, 0)        radial dead zone 0.32
    g = (1.0 - 0x3ea3d70a / m) × 0x3fbc3c3c  (0x3fbc3c3c = 1.4705882)
    return (x × g, y × g)
```

Afterwards four synthetic button bits are OR-ed into the held word +8: 0x800000 when
`lx` > 0x3f4ccccc (0.8), 0x400000 when `lx` < −0.8, 0x200000 when `ly` > 0.8, 0x100000 when
`ly` < −0.8 (0x1745bc–0x174640).

Consequences [I]: a byte of 0 gives exactly −1.0 before scaling, a byte of 255 gives
0.9921875; after scaling a full push left or up is about 1.0 and a full push right or down
about 0.988. Diagonals exceed 1 and are cut off later by the speed clamp.

Offline the bytes are the pad's. In a net game they are the output of the stick codec
(`netcodec_encodeAxis` 0x13c450 / `netcodec_decodeAxis` 0x13c970), which the local player's
own input also passes through; `docs/netcode.md` and `docs/issues/lag.md` §8 specify it. Not
re-read here.

## 3. Shared arithmetic

Functions: `math_cos16` 0x166630, `math_sin16` 0x1666e0, `math_atan2_16` 0x166798,
`angle_approach` 0x166c18, `angle_turnDir` 0x166bc8.

```
cos16(a):
    a = s16(a);  sign = 1.0
    if bit 15 of a differs from bit 14:           (|angle| of a quarter turn or more)
        sign = -1.0;  a = a sign-extended from 15 bits
    x  = f32(a) × 0x38490fda                      (half the angle in radians)
    x2 = x × x
    t  = x × x2;   p = x - t × 0x3e2aaa57
    t  = t × x2;   p = p + t × 0x3c086b24
    t  = t × x2;   p = p - t × 0x39458017         (p = sine of the half angle)
    return sign × (1.0 - (p + p) × p)

sin16(a) = cos16(a - 0x4000)

atan2_16(u, v) = s16( int( atan2f(u, v) × 0x4622f983 ) )      (0x4622f983 = 10430.378)
```

`atan2f` is the C library routine at 0x3a5a80 → 0x3a7328, which calls `atanf` 0x3aa558 and
`fabsf` 0x3aa7e8. [O] The constants in them (π as 0x40490fda, π/2 as 0x3fc90fda, a low part
0x34222168, range tests against 0x3edfffff, 0x3f2fffff, 0x3f97ffff and 0x401bffff) have the
shape of the single-precision `atan2f`/`atanf` of newlib [I]. π is stored one unit in the
last place below the nearest float 0x40490fdb, so a host `atan2f` will not do: straight "up"
on the stick comes out as 0x7fff, not 0x8000 [I]. The first argument is the "y" of the usual
`atan2(y, x)`.

```
angle_approach(rate, lo, hi, cur, target):        (cur, target s16; returns the new angle)
    d    = s16(cur - target)
    step = f32(|d|) × rate
    if lo != -1.0 and step < lo: step = lo
    if hi != -1.0 and hi < step: step = hi
    return s16(cur + int(step) × (d > 0 ? -1 : +1))
```

Because the step is truncated, an approach with rate *r* stops as soon as |d| × r < 1.

`angle_turnDir(a, b, out)` returns +1 when `s16(a − b) ≤ 0`, otherwise −1, and stores
|s16(a − b)| in `*out` when given. *(dec)*

## 4. Player movement

Functions: `Player_move` 0x1b4020 (14 call sites), `player_speedScale` 0x1bea10,
`Player_animStep` 0x1b9520, `Player_clampToScreen` 0x1b3d90, `creature_moveSimple` 0x1186d8,
`Player_tryBlockMove` 0x1bf150, parts of `Player_run` and `Player_processDamage`.

`ev = Player_move(player, mode, pad, vec)` — `mode` 0…6 is chosen by the caller, `vec` is
used by mode 5 only.

### 4.1 Steps of `Player_move`, in order

**(a) Stick suppression.** If byte +0x481 is non-zero, decrement it and store 0 in
`pad.lx`/`pad.ly` (the pad structure itself is written). If `dialog_isOpen()` (0x22fbc0),
store 0 in both as well. (0x1b4080–0x1b40d4)

**(b) Speed scale `S`.** (0x1b40d8–0x1b41bc; `player_speedScale` is the same code without
the last line)

```
base = 0x3f5ca86d (0.861945)
if g_networkMode != 0 and (g_pvpModeB == 0 or word 0x4f7124 != 0):  base = 0x3f400000 (0.75)
if g_levelName equals "watmedal":                                    base = 0x3f5ca86d
base = base × record[slot].speedMul            (player record +0x4c20, normally 1.0; skipped for slot -1)
S = base × g_runSpeed                          (float 0x4f8418)
if 0x3f999999 < S:  S = 0x3f999999             (cap 1.2)
if s16 +0x31a > 0 and the player carries a SpellDrowsy:  S = S × SpellDrowsy_getStat3Fraction()
```

`g_runSpeed` is 1.0 after `game_clearLevel` (0x1e4ff0) and is overwritten by a level's
`runSpeed=` setting (`levelSettings_parse` 0x22eb9c). The record multiplier is written by
`SpellGiantGrowth` (0x3093c4, 0x30965c) and `SpellResurrect` (0x312a28, 0x312adc) code, and
by three set-up paths: the arena set-up function 0x307c80 (store at 0x307d04; called from
`arena_init` and `arena_startWave`) gives every player 1.25 in a net game and 1.75
offline, and `player_importCharacter` (0x1bdb0c) and `player_initNewCharacter` store 1.0.
So "normally 1.0" above holds for the campaign only: in the arena game mode the base is
multiplied by 1.25 (or 1.75) before the 1.2 cap. An earlier version of this paragraph said
"written only by" the two spells; the reference search behind it missed the arena store
because part of the table's address is folded into the index register
(`docs/issues/claims-audit.md` row 99 and 6.1). Set-up runs in lockstep, so this is not a
sync matter. [O] the stores; the spell bodies were not read here.

**(c) Magnitude and target angle.** (0x1b41c0–0x1b420c)

```
s = S × sqrt(lx×lx + ly×ly);   if S < s:  s = S
T = s16( atan2_16(lx, ly) - net_getCamYaw(slot) - 0x41c2 )
```

The yaw is that of section 7.1. The constant is 0x41c2, not 0x4000: with the camera straight
behind the character (yaw = 0x4000 − facing, section 7.5) a push straight up asks for
facing − 0x1c3, 2.5° to one side of straight ahead. [O] constant; [I] reading.

**(d) Turning.** Only when `mode != 5` and 0x3c23d70a (0.01) < `s`:

| mode | new facing `F` (object +0x38) |
|---|---|
| 0, 2 | `angle_approach(0x3ecccccc, −1, −1, F, T)` — 40 % of the remaining angle per frame. Mode 2 with a `SpellCharge` attached uses `SpellCharge_getStat3Scaled()` as the rate. (If the word 0x4d8a28 were non-zero the rate would be `s × 0x3d0f5c28`; no code writes that word, so this branch is dead. [O] search, [I] dead) |
| 1 | rate 0x3e4ccccc (0.2). Before the turn, if the action state is 8: `a = min(f32(|T − F|) × 0x393ea672, 1.0)` and the time of animation track 5 (+0x1d4) is advanced by `a × 0x3f7fffff`. `|T − F|` here is a plain 32-bit difference, not wrapped to 16 bits |
| 3 | no turn |
| 4 | rate 0x3d5266e5 (0.05136766) |
| 6 | rate `s × 0x3da3d70a` (0.08 × s) |

Then, still inside the same condition, `cs = sin16(F + yaw + 0x4000) × s` and
`cc = cos16(F + yaw + 0x4000) × s` with the **new** `F`. When the condition fails,
`cs = cc = 0`. (0x1b4234–0x1b4400)

**(e)** If `mode == 2` or the action state is 1, `s = 1.0` (used by (f) and (g) only).

**(f) Water.** The creature flag bit 61 at +0xa8 means "standing in water". Clear: on frames
with `g_simFrame & 3 == 0`, `water_test(12.0, …)`; on a hit set the bit, advance
**`g_randSeed` once** (0x1b461c–0x1b4654: seed = seed × 0x19660d + 0x3c6ef35f), play a
splash and call `water_disturb`. Set: when level flag 0x1000 of word 0x44fe08 is set, every
16th frame call `damage_apply` on itself (0x1b4490); call `water_disturb` every frame while
`s ≥ 0.01` and every 16th otherwise; clear the bit when it returns 0. [O]; what the level
flag stands for is [U].
The arguments, the depth band (enter at surface − feet in [−1, 60], stay in [−13, 48]) and
the absence of any speed effect are executed in `docs/spec/player-wading.md`.

**(g) Mode 0 only: animation rate, blend ramp, velocity.** (0x1b4794–0x1b4b88)

```
if s < 0x3edc28f5 (0.43):       rate = s × 0x4014d653
else if s < 0x3f333333 (0.7):   rate = ((s - 0x3edc28f5) × 0x406d097a) × 0x3eb33330 + 1.0
else:                           rate = ((s - 0x3f333333) × 0x40555554) × 0x3e1999a0 + 0x3faccccc

w = float +0x46c
if 0x3c23d70a < rate:  w = w + 0x3dcccccc;  if 1.0 < w: w = 1.0 and track 0 time (+0x134) = 0
else:                  w = w - 0x3dcccccc;  if w < 0:   w = 0

if rate < 0x3c23d70a and w < 0x3d4ccccc:  Player_animStep(1.0);  ev = 0
else:  ev = Player_animStep(rate);  ev = ev & (0x3f199999 <= s ? 4 : 1)

if (float +0x468) - s < 0xbd4ccccc:  s = (float +0x468) + 0x3d4ccccc     blend speed rises 0.05/frame
float +0x468 = s
track 1 weight and life (+0x144, +0x14c) = w
track 2 weight and life (+0x164, +0x16c) = float( (double(w) × (double(s) - 0.45)) × 3.0 )
track 3 weight and life (+0x184, +0x18c) = float( (double(w) × (double(s) - 0.7 )) × 3.0 )
```

The three doubles are 0x3fdccccccccccccc, 0x3fe6666666666666 and 0x4008000000000000, and the
arithmetic is the software double library (0x3aef58 widen, 0x3af468 subtract, 0x3af4d0
multiply, 0x3afb90 narrow). [O] calls; [I] that the library rounds as IEEE does.

So the walk/run thresholds are: animation rate knees at 0.43 and 0.7, footstep event bit
switching from 1 to 4 at 0.6, the second and third locomotion tracks fading in above 0.45
and 0.7. **None of them touches the velocity.**

```
C  = net_getCamYaw(slot)
A  = ( -cos16(-C - 0x4000), -sin16(-C - 0x4000), 0 )
B  = ( -cos16(-C - 0x8000), -sin16(-C - 0x8000), 0 )
p  = cc × 0xc3340000 (-180.0);   q = cs × 0x43340000 (180.0)
V  = A × p + B × q                         per component: (A.i × p) + (B.i × q)
if byte +0x47e != 0 and byte +0x47c != 0:  V = V × 0x3fa00000 (1.25)     airborne, state 7 only
float +0x4bc, +0x4c0 = V.x, V.y
```

In exact arithmetic `V = 180 × s × (cos F, sin F)`: **the character moves along its facing,
never along the stick**, at 180 × s units per second. The round trip through the camera yaw
is how the original computes it and has to be kept for the low bits. Top speed offline is
0.861945 × 180 = 155.15, in a net game 0.75 × 180 = 135, and the cap of 1.2 allows 216.

**(h) Other modes.**

| mode | `V` |
|---|---|
| 1, 4, 6 | 0; also zeroes +0x46c and the six track fields of (g) |
| 2 | `(cos16(F) × 0x43960000, sin16(F) × 0x43960000, 0)` — 300 units per second forward |
| 3 | 0 (the initial value; nothing writes it) |
| 5 | `*vec` |

**(i)** If s32 +0x44c ≠ 2, byte +0x490 = 0. Then a block that only runs in action state 1
sets `V.x = V.y = 0` when `lo ≤ t ≤ hi`, with `t = f32(g_simFrame − s32 +0x448)`, by weapon
animation class (record +0x4a86) and "heavy" = (+0x44c == 2) (0x1b4c40–0x1b4ee8):

| Class | `lo` | `hi` |
|---|---|---|
| 0 | 0x410fffff (9.0) | 0x41b40000 (22.5); heavy 0x4206a3d6 (33.66) |
| 1 | 0x4220147a (40.02) | 0x42b40000 (90.0) |
| 2 | 0x3e199999 × 60.0; heavy 0x3dcccccc × 60.0 | 0x41b40000 (22.5) |
| 3 | 0x3eddb22d × 60.0; heavy 0x3dcccccc × 60.0 | 0x42c3f5c1 (97.98) |
| 4 and up | 0x40c5c28e (6.18); heavy 0x4130a3d6 (11.04) | 0x41bbae13 (23.46); heavy 0x4218e147 (38.22) |

`Player_run` calls `Player_move` in state 1 only with modes 3 and 4, where `V` is already 0,
so the block changes nothing there [I]; it would matter to a skill that moves a player with
mode 5 during a swing. Last, if +0x44c == 2 and `(byte +0x490) & 3` ≠ 0, `V.x = V.y = 0`.

**(j) Slow.** `n` = byte +0x2fc. If 1 ≤ n ≤ 60: `k = f32(60 − n) × DT`, then
`V.x = V.x × k`, `V.y = V.y × k`, `V.z = V.z × k`. (0x1b4f10–0x1b4f68)

**(k) Screen clamp**, offline only and only with two or more players alive:
`Player_clampToScreen(player, &V, &mask)` (section 4.7).

**(l) The move.** (0x1b4f9c–0x1b5034)

```
W = ( V.x + root.x × 60.0,  V.y + root.y × 60.0,  V.z )      root = floats +0xbc, +0xc0
bits = obj_moveWithCollision(player, W, 0, 0)                 section 5.5
root.x = root.y = 0
```

`root` is the animation root motion left by the last `Player_animStep`: a displacement per
frame, turned into a velocity here and multiplied by `DT` again inside the move.

**(m) After the move.** (0x1b5038–0x1b51e4)

- If `bits & 3`: byte +0x490 = bits.
- If `bits & 2`, the slot is local and the object is not the prediction copy:
  `g_forceGhostRebase` = 1.
- If `bits & 3` == 0: floats +0x308, +0x30c = floats +0x4bc, +0x4c0, each multiplied by
  `f32(60 − n) × DT` when slowed. Otherwise both 0. (Monster aiming reads them.)
- If `bits & 4` (on the ground): byte +0x482 = 15; if byte +0x47d is set (landing): footstep,
  action state = 2, top animation track's life rate = 0xbd6eeeee, bytes +0x47c, +0x47d = 0.
  In mode 2, when `bits & 3` and the object is not the copy, the `SpellCharge` is told
  (0x2c95f4 with argument 0 — body not read).
- Otherwise byte +0x482 counts down to 0.

**(n) Second half of the screen clamp** (same offline condition, and `net_getCamFlag(slot)`
== 0): if the position differs from `old + V × DT` and, for some plane *i* whose bit is in
`mask`, `dot(pos − old, normal_i) < 0`, then x and y are put back to their values from before
the call. (0x1b51e8–0x1b52e4)

Return `ev` (non-zero only from mode 0).

`Player_animStep(speed, player)`: `speed` is multiplied by the Drowsy fraction when the timer
+0x31a is positive, then `speed = (speed × f32(60 − n)) × DT` when slowed, then
`ev = anim_advance(speed, +0x114, soundPos, &root, 0)` — which overwrites `root`, it does
not add to it — and the delta is turned into world axes:

```
c = cos16(F - 0x4000);  s = sin16(F - 0x4000);  (rx, ry) = root
root.y = (-rx) × s - ry × c
root.x = (-rx) × c + ry × s
```

`soundPos` is null for the machine's own real player (flag 0x200000); that changes sounds
only. A player's root motion is not multiplied by a scale and not by the slow factor (a
monster's is, section 6.2).

### 4.2 Acceleration

There is none on the velocity: it is recomputed from the stick every frame [O]. What lags is
the **facing** (40 % of the angle per frame in mode 0), and the velocity follows the facing.
The 0.05-per-frame ramp at +0x468 limits animation blending only. In a net game the stick
value itself is delayed and smoothed by the codec; with the model numbers of
`docs/issues/lag.md` §8 a full cardinal push settles at 0.93–0.94, which by 4.1(c) is 93 % of
top speed [I] (that document left the question open).

### 4.3 What the character statistics do

- No statistic, and neither the carried load (record +0x120) nor the load limit (+0x124),
  enters `Player_move` or `player_speedScale`. A search for loads of those two offsets from
  a record pointer finds `player_recalcLoad`, `player_recalcStats`, import, the weight display
  `itemList_drawWeight` 0x1c7350 and one comparison, in the item-list input code
  (0x1ce158–0x1ce164: load + item weight ≤ limit, which gates an item transfer). So
  encumbrance is a carrying limit, not a speed penalty. [O] for the search; a reader that
  reaches the record through an unusual offset would be missed. (The hits at 0x1a41c0 and
  0x1ab7c0 are animation track weights on the object, not the record.)
- Status counters 2 and 4 (object +0x374, +0x37c) add 0.25 and 0.1 to the **swing rate** in
  action state 1 (0x1aa0f0–0x1aa11c), not to movement speed. The swing rate is the speed
  passed to `Player_animStep`, so it scales how fast the swing's root motion is delivered.
  [O]; FINDINGS D14 words this as "speed".
- Inputs that do reach the speed: the net-game base, the level's `runSpeed`, the record
  multiplier, SpellDrowsy, the slow amount.

### 4.4 Mode by action state

| State (+0x58c) | Call | Mode | Effect |
|---|---|---|---|
| 0 ranged attack | 0x1a95e0 / 0x1a95f8 | 6 in a net game, 1 offline | turn only; displacement is root motion |
| 1 melee | 0x1aa694 / 0x1aa6b0 | 4 while `f32(frame − start(+0x448)) ≤ t × 60.0`, with `t` = 0x3eddb22d (0.433), or 0x3f1126e9 (0.567) when +0x44c == 2; afterwards 3 | slow turn during the wind-up, then none; root motion only |
| 2 neutral | 0x1a8094 | 0 | stick movement |
| 2, bow in hand, attack and ability pressure both below 0.13 | 0x1a7ca8 | 1 | turn only (the pressure is 0 or 1 in a net game) |
| 3 staggered, 4 dead, 10, 0xc | — | no call | `Player_run` does not move the object: no gravity, no push-out. Offline the knock-back of 4.8 still does |
| 5 casting | 0x1ab5a4 / 0x1ab5c0 | 6 in a net game, 1 offline | turn only |
| 6 skill-driven | 0x1a6a7c | 5 with a zero vector | root motion only; the skill's own run may call `Player_move` again (`SpellCyclone_run` 0x2d1f14 mode 5 with its vector; `SpellBash_run` 0x2de870 and `SpellShieldBash_run` 0x2faf14 mode 3) |
| 7 airborne | 0x1a60cc | 0 | see below |
| 8 blocking | 0x1a656c | 1 | turn only |
| 9 rush | 0x1a60cc | 2 | 300 units/s forward; `Player_animStep(2.0)` |
| 0xb block move | 0x1a60cc | 1 | turn only; root motion |
| 0xe | — | no call | |

In every row but the bow one `Player_animStep` runs before `Player_move` in the same frame.

**Strafing and blocking.** There is no strafe: in every mode the character either moves along
its facing or does not translate. Blocking (state 8) turns toward the stick at 20 % per frame
and stays in place. `Player_tryBlockMove` 0x1bf150 starts state 0xb when the block-move button
is pressed while blocking: it starts an animation with root motion and sets byte +0x481 to
47, so the stick is ignored for 47 frames and the whole displacement comes from the
animation. *(dec)*

**State 7** applies a jump: once the top track's time reaches 0x4080a3d6 (4.02 ticks,
*(dec)*) it sets vertical velocity 360.0 (0x43b40000), raises the height by 0.02, and while
rising subtracts a further 0x4157fffe (13.5) per frame on top of gravity (0x1a5f98–0x1a60c0).
No code stores 7 in the action state (`docs/player.md`), so this is unreachable as far as
known. [O] code, [U] reachability.

### 4.5 What stops movement

- A zeroed stick: `Player_run` substitutes the zero pad (0x1a565c–0x1a5760) when any of
  these holds — `g_menuInputLockout` ≠ 0 offline; `dialog_isOpen()`; spawn protection +0x4b4
  ≠ 0; `g_recallCountdown`; `g_medalDialogTicks`; `net_getCamFlag(slot)` (the owner's camera
  is not in follow mode — carried in the input record, section 7.1); a run task named
  `jumpgate` or `missionmenurun` exists; `net_isSlotActive(slot)` is false; object flag
  0x400000; word 0x503890 ≠ 0; byte 0x4f66c8 ≠ 0; hit points ≤ 0. *(dec)* The list is in
  the order the code tests them, and the order matters: the tests short-circuit, so it
  decides which of the calls (`dialog_isOpen`, `net_getCamFlag`, the two task look-ups,
  `net_isSlotActive`) are made on a given tick; the hit-points test is the last
  (**executed**, `docs/spec/player-tick.md` section 2).
- Byte +0x481 and `dialog_isOpen()` again inside `Player_move`.
- A mode with `V = 0` (table above), a state with no call.
- The root timer and the slow amount do **not** stop a player the way they stop a monster:
  `obj_moveWithCollision` has no root test, and the slow factor of a player is at most 30/60
  (section 4.6).

### 4.6 The slow amount (byte +0x2fc)

Set in `Creature_run` (0x113614–0x1137e4) *(dec)*:

- Chill timer (float +0x344) > 0: subtract 0x3d888888 (1/15) per frame; slow =
  `int(chill)`, 59 when the timer exceeds 60, 0 when dead; then at most
  `int(60.0 − resist[1] × 60.0)`. A monster is further capped at 30 (15 for a boss rank
  above 0 once the value reaches 16). A **player** is capped at 30 and loses another
  0x3d088888 (1/30) of timer per frame.
- Status counter 7 (+0x388) > 0 overrides it: `2 × (frame − +0xf0)` for the first 30 frames,
  then 60 for any counter value above 30 and the counter value itself only at 30 or below;
  capped by `resist[4]` the same way. (The earlier version said "then the counter value
  up to 60". Executed in `docs/issues/dynamic-tests.md`, check z6, and visible at
  0x113774–0x1137d8: after the ramp the byte is the counter only when the counter is under
  31, else the constant 60. So a player under counter 7 sits at exactly 60 — the
  divide-by-zero value of FINDINGS F4 — for as long as the counter is above 30.)

Users: `Player_move` (j), `Player_animStep`, and for monsters `Creature_stepAnim`,
`Creature_turnToward` and the speed in the move helpers.

### 4.7 The screen clamp (offline, two or more players alive)

`Player_clampToScreen` 0x1b3d90 *(dec)* first rebuilds four planes with 0x1e71b0: for each of
the four side planes of the view frustum (0x44f0a8, 16 bytes apart) the normal is flattened to
the ground and normalised, and the plane point is the camera position moved along that
normal by `(cam.z − player.z) × n.z / sqrt(1 − n.z²)` plus 60 units — the frustum's footprint
at the player's height, 60 units inside. Then, if the player is outside any plane: for each
plane it is outside of, set that bit in `mask`; if the step `V × DT` points further out,
remove that component; if a second plane also objects, the step becomes 0. It is never
called in a net game (0x1b4f7c–0x1b4f88).

### 4.8 Knock-back

`Creature_applyKnockback(scale, c)` 0x115eb8 *(dec)*:

```
if c is a player and (g_networkMode != 0 or g_pvpModeB != 0):  speed(+0x2e8) = 0;  return
if scale > 0 and speed != 0 and not (flags & 2):
    v = ( cos16(angle(+0x2e0)) × speed × scale,  sin16(angle) × speed × scale,  0 )
    save root motion and root yaw, zero them, bits = Creature_moveBy(c, v), restore them
    if speed > 0: speed = speed - 2.0;   if speed < 0: speed = 0
    if not in water, creature flag 0x100000 clear, and bits & 3 == 0:
        two dust puffs, each drawing 9 or more values from the creature's own generator
```

The dust loop draws from `GameObject_rand` (object +0x44): three for a position, then
triples until one falls inside the unit ball, then three more — per puff. That generator is
simulation state, so the count of draws must match.

- Direction +0x2e0 is set by `Creature_takeDamage` (0x1166d0–0x116700):
  `0x4000 − atan2_16(victim.x − attacker.x, victim.y − attacker.y)`, the bearing from attacker
  to victim. `Creature_knockbackTarget` 0x119d10 stores a speed argument and the same bearing
  computed the other way round, `atan2_16(target.y − c.y, target.x − c.x)` *(dec)*.
- Speed for a player comes from the hit's flag bits in `Player_processDamage`
  (0x1b2da8–0x1b2e7c): 0x40000 → 100, 0x80000 → 150, 0x100000 → 200, 0x200000 → 250; halved
  in PvP mode A. For a dying monster `docs/creatures.md` gives 100 / 150 / 200 / 312.5.
- A speed of 100 lasts 50 frames and carries 42.5 units [I].
- A knocked-back **player** is moved by `Creature_moveBy`, i.e. with the monsters' terrain
  mask 3 (section 5.7). In a net game players are never knocked back.

## 5. Collision

Functions: `terrain_collectElements` 0x183248, `terrain_sweepCircle` 0x185a40,
`world_slideMove` 0x14d238, `terrain_heightBelow` 0x1834a8, `terrain_height` 0x183820,
`world_collectObjectsInBox` 0x14a928, `obj_updateGridCell` 0x14f028,
`obj_moveWithCollision` 0x14d4b8, `Creature_moveBy` 0x113c48, `obj_moveAndCollide` 0x1509f8.

**Executed since, with no error found** (`docs/spec/world-queries.md` section 12): 5.2
(collecting elements), 5.3 (the sweep, operand for operand, including the quarter-distance
normal), 5.4 (the slide), the ground and gravity lines of 5.5, 5.8 (`terrain_heightBelow`)
and the terrain part of 5.10 were run in `tools/ee_emu.py` on real level files and agree
bit for bit with that document's model. So the *(dec)* marks on 5.2 and 5.10 no longer
mean an unchecked operand order for those parts. The object parts of 5.5, 5.9 and 5.10
were not run there; `Creature_moveBy` (5.6) is executed in `docs/spec/creature-tick.md`
section 8 and the box query in `docs/spec/object-system.md` 4.3. Four additions from that
run are noted in place below (5.3 twice, 5.4, 5.10).

### 5.1 Shapes

Every mover is an upright cylinder: radius +0x1c around (x, y), from height z to z + (+0x20).
Terrain is a set of **point samples** 4 units apart, each with a height and flag bits
(`docs/formats/world.md`); a wall is nothing but samples that are too high or flagged. Other
objects are cylinders too.

### 5.2 Collecting terrain elements — `terrain_collectElements(minX, minY, maxX, maxY, world, out, max)` *(dec)*

Cell range on each axis: `int(floorf(coord × 0x3bcccccc)) − gridOrigin`, clamped to the
grid (cells are 160 units). Rows (y) outer, columns inner, each cell's index list in file
order. An element is taken when its visit stamp differs from `g_terrainStamp` (0x44f08c,
incremented by every caller before the call), its flag 2 is clear and its s16 rectangle
overlaps the box (`f32(min) ≤ boxMax` and `boxMin ≤ f32(max)` on both axes); it is then
stamped. The list ends with 0 and holds at most `max − 1` entries.

### 5.3 The sweep — `t = terrain_sweepCircle(r, world, &P, &S, mask, &N)`

A circle of radius `r` at `P` tries to move by `S`. Returns the fraction of `S` it can go
(1.0 = all of it) and, when blocked, the contact normal `N`.

```
g_terrainStamp += 1
E.x = P.x + S.x;  E.y = P.y + S.y
elements = collect( min(P.x,E.x) - r,  min(P.y,E.y) - r,  max(P.x,E.x) + r,  max(P.y,E.y) + r,  max 256 )

sx = S.x × 0.25;  sy = S.y × 0.25            everything below is in sample units (4 world units)
r4 = r × 0.25;    r4sq = r4 × r4
len  = sqrt(sx×sx + sy×sy)
inv  = 1.0 / len
dir  = (sx × inv, sy × inv)
dzPer = S.z × inv                             note: S.z is NOT scaled by 0.25
rc    = int(ceilf(r4))
baseZ = int(floorf( min(P.z, P.z + S.z) ))
best  = len

for each element e, in list order:
    hf = e.heightField
    if e.flags & 4 == 0  and  hf.maxHeight(s16 +0x12) + e.z  <  baseZ + 12:   skip e     (integers)
    c = f32(e.cos) × 0x38000100;  s = f32(e.sin) × 0x38000100                 (1/32767)
    ux = P.x - f32(e.x);  uy = P.y - f32(e.y)
    if e.flags & 1 (mirrored):
        lx  = ux×c + uy×s;        ly  = ux×s - uy×c
        dlx = dir.x×c + dir.y×s;  dly = dir.x×s - dir.y×c
    else:
        lx  = ux×c + uy×s;        ly  = (-ux)×s + uy×c
        dlx = dir.x×c + dir.y×s;  dly = (-dir.x)×s + dir.y×c
    lx = lx × 0.25;  ly = ly × 0.25
    i0 = int(floorf(lx));              j0 = int(floorf(ly))
    i1 = int(floorf(lx + dlx × len));  j1 = int(floorf(ly + dly × len))
    for j = min(j0,j1) - rc  ..  max(j0,j1) + rc + 1:            rows first
      for i = min(i0,i1) - rc  ..  max(i0,i1) + rc + 1:
        skip unless 0 <= j - hf.y0 < hf.rows  and  0 <= i - hf.x0 < hf.cols
        v = s16 sample[(j - hf.y0) × hf.cols + (i - hf.x0)]
        h = (v & mask) != 0  ?  32000  :  (v >> 4) + e.z          arithmetic shift; integers
        if h < baseZ + 12:  continue                              integers
        a = f32(i) - lx;  b = f32(j) - ly
        perp = a × dly - b × dlx
        if r4 + 0x3c23d70a < |perp|:  continue
        along = a × dlx + b × dly
        if along < 0:  continue
        if f32(h) < (P.z + along × dzPer) + 12.0:  continue
        q = r4sq - perp × perp
        t = (0 < q)  ?  along - sqrt(q)  :  along - 0
        if not (t < best):  continue
        best = t
        X = f32(i << 2);  Y = f32(j << 2)                         remember the sample, world axes
        mirrored:      hit = ( X×c + Y×s + f32(e.x),  X×s - Y×c + f32(e.y) )
        not mirrored:  hit = ( X×c - Y×s + f32(e.x),  X×s + Y×c + f32(e.y) )

if len <= best:  return 1.0
if N wanted:
    n = ( (P.x + dir.x × best) - hit.x,  (P.y + dir.y × best) - hit.y )
    k = 1.0 / sqrt(n.x×n.x + n.y×n.y)          one hardware instruction (reciprocal square root)
    N = ( n.x × k, n.y × k, 0 )
return best × inv
```

Points a re-implementation is likely to get wrong:

- **A sample blocks** when one of its flag bits is in the mover's mask, or when its ground is
  12 or more above the mover — tested twice, once in integers against `floor` of the lower
  end of the step and once in floats against the height the mover would have on arrival.
  Lower samples never block: **there is no limit on stepping down**.
- `t` may be negative: a circle that already overlaps a blocking sample is pushed **back**
  along its direction of travel.
- Ties keep the first sample met (strict `<`), so the iteration order above is part of the
  result.
- The centre used for the normal is `P + dir × best` with `best` in sample units — one quarter
  of the distance actually travelled. [O] 0x186088–0x1860c4. It looks like an oversight, and
  it must be kept.
- With a purely vertical step `len` is 0 and `inv = 1.0 / 0`. The console's divide gives the
  largest finite float, not infinity (section 8). `Creature_moveBy` never gets there (5.6);
  `obj_moveWithCollision` can, for a player moved with a vertical velocity only. [O] tests;
  [U] whether any skill does that. Executed since (`docs/spec/world-queries.md` section 7):
  the case is worse than a wrong result. With a blocking sample under the circle the
  returned time is −0x7fffffff, and the slide of 5.4, which has no bound on its step, then
  asks for a step of the order of 10^35 units and walks the whole index range of every
  element it collected.
- For an element that is not rotated the cosine is not 1.0: `f32(32767) × 0x38000100` is
  0x3f7fffff truncated (1.0 only if rounded to nearest), in 5.3–5.8 alike. A mover an exact
  multiple of 4 units from an element's origin can therefore fall on a different sample
  than exact arithmetic gives (`world-queries.md` section 4.1; executed under both rules).

### 5.4 Slide — `hit = world_slideMove(r, &pos, &delta, mask, &normalOut)`

```
D = delta;  P = pos;  remain = 1.0;  hit = 0
repeat at most 11 times:
    step = D × remain                                  per component
    t = terrain_sweepCircle(r, world, &P, &step, mask, &N)
    remain = remain - t
    P = P + step × t                                   per component (z included)
    if 0x3a83126e < remain:
        hit = 1
        k = 0x3a83126e - ((N.x × D.x + N.y × D.y) + N.z × D.z)
        if 0 < k:  D = D + N × k                       drop the part going into the wall, plus 0.001 outward
    else: stop
pos = P;  normalOut = N (if wanted);  return hit
```

Sliding along a wall is this loop: what is left of the step is re-aimed along the contact
tangent and tried again, up to ten more times. `N` keeps the value of the last blocked
sweep; when no sweep was blocked, `normalOut` receives an uninitialised stack slot
(Observed in `docs/spec/world-queries.md` section 7; `Creature_moveBy` uses the normal only
after a reported hit, the other callers were not checked).

### 5.5 Players and plain objects — `bits = obj_moveWithCollision(obj, vel, ignore, skipCreatures)`

```
d = vel × DT                                           per component
if 0x3a83126e < (d.x×d.x + d.y×d.y) + d.z×d.z:
    mask = 1;  if obj is a creature (flag 0x20): mask = 3;  if obj is a player (0x40): mask = 5
    bits = world_slideMove(obj.r, &obj.pos, &d, mask, none) ? 1 : 0
    relink obj at the head of grid cell ( (int(x) + 0x3c00) >> 8, (int(y) + 0x3c00) >> 8 ),
        or of the off-grid list when either index is outside 0..119
else bits = 0

list = world_collectObjectsInBox( pos - (r, r, 1000),  pos + (r, r, 1000),  max 64 )
top  = pos.z + obj.height;   stand = 0xc7c35000 (-100000.0)
for each o in list, in list order:
    skip if o.flags & 1, o is obj, o is ignore, or (skipCreatures and o is a creature)
    dx = pos.x - o.x;  dy = pos.y - o.y;  dist = sqrt(dx×dx + dy×dy)
    if not (dist + 0x3a83126e < obj.r + o.r):  continue
    if (o.flags | obj.flags) & 0x10:                            one of them has a top
        if top < o.z + 3.0:  continue                           obj is entirely below o
        oTop = o.z + o.height
        if oTop < pos.z:  continue                              obj is above o
        if oTop - pos.z < 5.0:                                  within 5 of the top
            if o.flags & 0x200:        touch(o)
            else if obj.flags & 0x400: touch(o)
            else:  if stand < oTop: stand = oTop                stand on it; no touch call
            continue
    if o.flags & 0x200  or  obj.flags & 0x400:  touch(o);  continue
    if 0x3a83126e < |dist|:
        k = ((obj.r + o.r) - dist) / dist
        push = (dx × k, dy × k, 0)
        world_slideMove(obj.r, &obj.pos, &push, 1, none);  relink as above;  bits |= 2
    touch(o)

touch(o):  if obj is not the prediction copy (flag 0x20000): o.slot6(o, obj)
           obj.slot6(obj, o);  re-read obj.r

ground = terrain_heightBelow(obj.r, world, &pos);   if ground < stand: ground = stand
vz = vz - 0x410fffff (8.999999);   pos.z = pos.z + vz × DT
if pos.z - 0x3c23d70a <= ground:
    pos.z = ground
    if vz < 0:  vz = 0;  bits |= 4
return bits                                            1 terrain, 2 pushed out of an object, 4 on the ground
```

`pos` is re-read for every object, so each push-out starts from where the previous one left
the mover. The push-out slide uses mask 1 whatever the mover is. `creature_moveSimple`
0x1186d8 is this routine with `ignore = 0, skipCreatures = 0`; besides `Player_move` its
callers are 0x260928 and, directly, `AutoContainer_run`, `Container_run` and
`SpellShadowStep_run` (not read).

### 5.6 Monsters — `bits = Creature_moveBy(c, vel)`

```
if c.inert(+0x231) & 8:  return 0
old = c.pos
V.x = vel.x + root.x × 60.0;  V.y = vel.y + root.y × 60.0;  V.z = vel.z
c.facing = c.facing + rootYaw(+0xc4)
if rootTimer(+0x314) != 0:  V = 0
floats +0x308, +0x30c = V.x, V.y;   root = 0;  rootYaw = 0
water bookkeeping (one GameObject_rand draw when the creature enters water; test every 8th frame, staggered by serial)
d = V × DT
if 0x3a83126e < d.x×d.x + d.y×d.y:                     two components only
    bits = world_slideMove(c.r, &c.pos, &d, 3, &N) ? 1 : 0;   obj_updateGridCell(c)
list = world_collectObjectsInBox( pos - (r, r, 1000),  pos + (r, r, 1000),  max 16 )
... the same object loop as 5.5, with these differences:
      - no ignore arguments;
      - the push-out needs (c.flags & 0x401) == 0 and uses mask 3;
      - every touch, pushed or not, sets bits |= 2, calls only o.slot6(o, c) and appends o to a list;
      - while c.flags & 0x8000000 (Creature_settle): stop the loop when o is c's target
ground, gravity and landing exactly as 5.5
if bits & 1:  c.slot10(c, &N)                           "moved into terrain"
if bits & 2:  if c.flags & 0x8000000: c.pos = old, obj_updateGridCell(c)
              c.slot11(c, touched list)
return bits
```

Differences that matter: the box query returns at most 15 objects (63 for 5.5), so in a
crowd some overlaps are not resolved and which ones depends on list order; the mover's own
slot 6 is not called; a creature with a root timer is not translated but is still pushed out
of overlaps and still falls.

### 5.7 Who obeys which sample flag

| Mask | Used by | Blocked by |
|---|---|---|
| 1 | non-creature objects in 5.5; every push-out in 5.5; `Prop_run` (`docs/formats/world.md`) | flag 1 |
| 3 | both slides of `Creature_moveBy`: monsters, knocked-back players, the cutscene walk of a player; the monster probe rays (section 6.4) | flags 1 and 2 |
| 5 | a player's own step in 5.5 | flags 1 and 4 (no sample in the shipped levels has 4) |

So flag 2 is a monster fence that players walk through.

### 5.8 Ground, steps and drops

`terrain_heightBelow(r, world, &pos)` *(dec, float tests checked)*: collect elements in the
box `pos ± r` (at most 63); `r4 = r × 0.25`, `rc = int(ceilf(r4))`; start with −1000000. For
each element whose `hf.maxHeight + e.z` exceeds the best so far and whose
`f32(hf.minHeight(+0x10) + e.z) ≤ pos.z + 12.0`: transform `pos` to `(lx, ly)` as in 5.3,
`i0 = int(floorf(lx))`, `j0 = int(floorf(ly))`, and for rows `j0 − rc … j0 + rc + 1`, columns
`i0 − rc … i0 + rc + 1`, a sample counts when `h = (v >> 4) + e.z` is above the best,
`f32(h) ≤ pos.z + 12.0` and `(f32(i) − lx)² + (f32(j) − ly)² < r4 × r4`; when a sample
reaches the element's maximum the element is finished. Returns `f32(best)`. Flags are not
looked at. `terrain_height` 0x183820 is the same without the two "+ 12" tests.

Put together:

- **Step up:** less than 12 units. The mover stands on the highest sample under its disc
  that is no more than 12 above it, and the height snaps to it in one frame.
- **Step down / drop:** unlimited. Gravity takes 8.999999 units/s off the vertical velocity
  per frame (540 units/s²); a mover stays "on the ground" while the ground is within 0.16
  below it at the end of the frame.
- **Standing on objects:** only on an object with flag 0x10 (or when the mover has it), when
  the mover's base is within 5 units below the object's top.
- **Edge of the level:** nothing but samples. Where the level's border samples carry flag 1
  the mover is stopped; where there are no samples at all the sweep blocks nothing and
  `terrain_heightBelow` returns −1000000, so the mover falls without end. A sample of height
  −2000 ("no floor") is a floor at −2000 + element z for this code. The kill plane that
  would catch a falling player is disabled in every level (FINDINGS G15). Outside ±15360
  units an object leaves the grid and box queries no longer find it. [O] code; [I] that
  shipped levels are fenced.

### 5.9 Objects against objects

`world_collectObjectsInBox` *(dec)* walks grid cells from `(int(min) + 0x3ba0) >> 8` to
`(int(max) + 0x3c60) >> 8` on each axis (96 units of padding), rows outer, and each cell's
list from its head; skips flags in `g_excludeMask` and the prediction copy; accepts an object
when its square of half-width `o.r` overlaps the box in x and y, `o.z ≤ max.z` and
`min.z ≤ o.z + o.height`; stops dead when the output is full.

- Overlapping creatures are **not pushed apart symmetrically**. Each mover, in its own move
  call and even with zero velocity, moves itself out of every solid object it overlaps by the
  full overlap along the line between centres, through a terrain slide (so a wall wins). The
  other object is not moved. Two creatures at the same point (distance ≤ 0.001) are left
  there.
- Walking into a creature at an angle therefore slides round it: the step goes in, the
  push-out comes straight back out along the radius.
- Flag meanings as in `docs/objects.md`: 0x1 not solid (a corpse gets it), 0x10 has a top,
  0x200 touch only, 0x400 mover is not pushed, 0x20000 prediction copy.
- Players are solid to each other; no code in these routines treats a player specially
  apart from the terrain mask and the copy test.
- Call order of slot 6 ("touched") is part of the simulation: other first, then self in 5.5;
  other only in 5.6.

### 5.10 Projectiles — `bits = obj_moveAndCollide(obj, vel)` *(dec)*

```
pos = pos + vel × DT                                    no sweep: a fast projectile can skip thin walls
obj_updateGridCell(obj)
if terrain_height(r, world, &pos) > pos.z:              inside the ground
    bits = 1
    k = 0x3dcccccc (0.1)
    repeat:
        try = pos - (vel × DT) × k                      back along the step
        if terrain_height(r, world, &try) <= try.z:  stop
        k = k + 0x3dcccccc
    while k < 2.0
    pos = try                                           also when no clear point was found
    first time only (byte +0x50): if water_test(12.0, …): one GameObject_rand draw, splash
list = world_collectObjectsInBox( pos - (r, r, height),  pos + (r, r, height),  max 256 )
for each o: skip flags 0x201, flag 0x20000000, obj itself and obj's owner (+0x4c)
    if pos.z - height <= o.z + o.height  and  o.z <= pos.z + height
       and  dx×dx + dy×dy < (r + o.r) × (r + o.r):
        bits |= 2;  o.slot6(o, obj);  obj.slot6(obj, o)
```

`Projectile_ctor` 0x150e48 sets radius 12. What each projectile class does with `bits`, its
velocity and any gravity is in the class's run function (26 callers of this routine; only
`MissileWeapon_run` 0x15153c was opened: it passes the stored velocity at +0x1b0 unchanged).
The exact loop bounds of the back-off were read from the decompile only when this was
written; executed since (`docs/spec/world-queries.md` 8.3): with the truncated 0.1 the loop
makes at most 20 tries (k = 0.1 … 1.9999989), and the last try is kept also when none was
clear.

## 6. Monster movement

Functions: `Creature_turnToward` 0x10bb08 (virtual slot 26), `Creature_stepAnim` 0x1162b0,
`Creature_moveTo` 0x114510, `Creature_moveToDirect` 0x1155e0, `Creature_moveToTarget`
0x1143e8, `Creature_moveToDest` 0x119f38, `Creature_fleeFrom` 0x115910, `Creature_settle`
0x119e38, waypoint access 0x11a020–0x11a1e0, `Creature_requestPath` 0x1164c0,
`Creature_probeThreeMovementRays` 0x108fd8, `Creature_computeAvoidanceTarget` 0x109280,
`Creature_computeAvoidanceOffset` 0x108a60.

### 6.1 Turning — `d = Creature_turnToward(c, mode, &point)`

```
limit  = int( turnRate(+0xb0) × 0x44888888 )                    (0x44888888 = 1092.2666 = 65536/60)
target = atan2_16(point.y - c.y, point.x - c.x);   if mode == 1: target += 0x8000   (face away)
d  = s16(target - c.facing)
av = u16 angVel(+0x110) + int( f32(d) × 0x3d4ccccc )            spring 0.05
av = av - int( sqrt(0x3e4ccccc) × f32(s16(av)) )                damping; the square root is taken at run time
angVel = s16(av);  if limit < angVel: angVel = limit;  if angVel < -limit: angVel = -limit
if 1 <= slow <= 60:  c.facing += int( f32(angVel) × (f32(60 - slow) × DT) )
else:                c.facing += angVel
return d                                                        the difference from BEFORE the turn
```

The return value is not in `docs/creatures.md`; every move helper uses it (6.3).
`Player_ctor` sets a player's turn rate to 0x3fb33333 (1.4) for the cases where a player is
driven by these helpers.

### 6.2 Root motion — `ev = Creature_stepAnim(speed, c)`

```
if AI state(+0x232) == 3:  speed = speed × player_speedScale(-1)     the chase state runs at the players' scale
if s16 +0x31a > 0 and c carries a SpellDrowsy:  speed = speed × its fraction
if creature flag bit 63 (active):
    if 1 <= slow <= 60:  speed = (speed × f32(60 - slow)) × DT
    ev = anim_advance(speed, +0x114, soundPos, &root, &rootYaw)       overwrites root and rootYaw
root.x = root.x × scale(+0xdc);  root.y = root.y × scale
c = cos16(facing - 0x4000);  s = sin16(facing - 0x4000);  (rx, ry) = root
root.x = (-rx) × c + ry × s
root.y = (-rx) × s - ry × c
if 1 <= slow <= 60:
    k = f32(60 - slow) × DT
    root.y = root.y × k;  root.x = root.x × k
    rootYaw = s16( rootYaw × int(k) )                                 int(k) is 0: any slow removes the root yaw
```

The next `Creature_moveBy` adds `root × 60` to its velocity and the yaw to the facing, then
clears them (5.6). So a slowed monster's root motion is slowed twice — once through the
animation speed, once through `k` — and its animated turning stops altogether. [O]
0x116420–0x116498.

`soundPos` is the position unless creature flag 0x2000000 is set (0x116330–0x116348). That
flag therefore mutes animation sound cues; `docs/creatures.md` describes it as "root motion
not applied", which this code does not do.

### 6.3 Approach and retreat helpers *(dec)*

All of them end the same way:

```
d = c.slot26(c, 0, &aimPoint)                       turn toward the aim point
v = moveSpeed(+0xb8)                                units per second
if s16 +0x31a > 0 and a SpellDrowsy is attached:  v = v × its fraction
if |d| > 16000:  v = moveSpeed × 0.5;  root.x = root.x × 0.5;  root.y = root.y × 0.5
if 1 <= slow <= 60:  v = v × (f32(60 - slow) × DT)
Creature_moveBy(c, (cos16(facing) × v, sin16(facing) × v, 0))
```

A monster also moves **along its facing**, not toward the point. Turning through more than
88° halves the speed (and, as written, discards the Drowsy factor).

| Helper | Aim point and return |
|---|---|
| `Creature_moveToDirect(c, &p)` | returns 1 when within one radius of `p` (3-D). Every 8th frame (staggered by serial, `(frame ^ serial) & 7 == 0`), within two radii and facing more than a quarter turn away, also returns 1. Every 32nd frame, unless inert, the steering offset +0x2ec is recomputed by `Creature_computeAvoidanceOffset`, with the ray length `min(distance, radius + 10)`; the offset replaces the aim point by position + offset only when its x **and** its y are both non-zero (two tests, 0x115778 and 0x115788; the earlier version said "a non-zero offset"; executed, `docs/spec/creature-tick.md` 9.4) |
| `Creature_moveTo(c, &p)` | path following, 6.4. Returns 1 on arrival |
| `Creature_moveToTarget(c)` | `moveTo` a point on the target's rim: target position + (cos, sin)(bearing from target to c) × (target radius + 5). With no target, sets AI state 0 |
| `Creature_moveToDest(c)` | `moveTo` the destination +0x104; sets AI state 0 on arrival; after four failed path searches picks a random point near home |
| `Creature_fleeFrom(c, threat, kind)` | keeps a flee point +0xf8 (a random point within 300 of home, or home itself when the creature is near the edge of its home range); steers by the avoidance offset when there is one, otherwise by waypoints of a path requested from the threat's position with search type 1 or 2 and radius 600. Not stated in the earlier version and executed since (`docs/spec/creature-tick.md` 9.4): the avoidance offset is refreshed on every staggered 8th frame, and on the waypoint branch the aim that results is **written back as the flee point** |
| `Creature_settle(c)` | `Creature_moveBy` with zero velocity and object flag 0x8000000: if anything is touched the old position is restored |

### 6.4 Following a path — `Creature_moveTo` *(dec)*

State: 16 waypoints of integer (x, y) at +0x23c ended by −1, index +0x2bc (16 = none or
search pending), steering point +0x2ec, retry frame +0x2c0, progress record +0x2c8/+0x2d4,
side-step deadline +0x2d8, creature clock +0x300.

1. If the steering point is (0, 0) it becomes `p`. Arrival: 3-D distance² below radius²
   → return 1; every 8th frame, below 2 × radius² and facing more than 0x4000 away → return 1.
2. While clock < side-step deadline: aim at the steering point.
3. Otherwise, **no current waypoint**: every 64th frame probe the straight line with
   `Creature_probeThreeMovementRays` (three `world_raycast` calls with terrain flags 3, from
   the centre and from one radius to each side, 11 units above the feet, length factor
   0x3f8ccccc = 1.1); if blocked, `Creature_advanceWaypoint`, which requests a path
   (`Creature_requestPath`: output buffer +0x23c, 16 points, index set to 16). The aim is the
   steering point, refreshed like this: if the creature already faces it within 1000 units,
   every 8th frame it becomes `Creature_computeAvoidanceTarget` (a point 1200 units along
   the straight line when the probes are clear or the obstacle is more than two radii away,
   otherwise 1200 units along the facing turned by 0, +0x2000 or −0x2000 according to two
   side probes), and on other frames `p` itself; if it does not face it, the steering point
   is replaced by `p` only when `p` is the farther of the two.
   Two details of that parenthesis are wrong, executed in `docs/spec/creature-tick.md`
   section 10: the straight-line point is `pos + (p − pos) × 1200` — 1200 times the
   vector, not 1200 units along it (0x109344–0x109380); and "more than two radii away" is
   the test `t × |D|² < (2 × radius)²` failing, with the probe's fraction `t` not squared
   (0x1093c0–0x1093c8). The turned headings are 1200 units along the facing, as written.
4. **With a waypoint**: if the straight line to `p` is clear, drop the path and aim at `p`.
   Otherwise advance through waypoints (at most 16 per call) while the current one is within
   24 units (576 = 24²), or the creature has passed it (dot product of "to next" and "to
   creature" positive), or the retry frame has passed; each advance sets the retry frame to
   now + 30. Aim at the current waypoint, or at `p` when the list runs out.
5. The common ending of 6.3.
6. **Stuck recovery.** If a cutscene is active or the creature is more than 4 units from its
   progress record, record position and clock. Otherwise, when 30 clock ticks have passed
   without progress and no side-step is running: side-step deadline = clock + 30 and the
   steering point becomes 1200 units along facing ± 0x6000, the sign from one draw of the
   creature's own generator. When a side-step ends with still no progress for 300 ticks:
   `world_findFreeSpot` (shared seed) within 72 units and teleport there. "Ends" is exact:
   the test is that the clock **equals** the side-step deadline, so the teleport can happen
   only on that one tick (executed, `docs/spec/creature-tick.md` 9.5).

Waypoints are path-grid node positions (multiples of 24 units) written by `path_search`;
`docs/engine.md` describes the search. The path result arrives through virtual slot 7, which
resets the index to 0 and counts failures at +0x2c4 (0x11a260).

`Creature_computeAvoidanceOffset` 0x108a60 casts three forward rays (centre and both edges,
13 units up), remembers a side in byte +0x2f8, and returns an offset along facing ∓ 12000
units of angle scaled by the radius; its side-selection logic and the exact length were read
only in outline. [U] for the exact rule when this was written; answered and executed in
`docs/spec/creature-tick.md` section 10: the offset is 2 × radius long, along facing − 12000
for side 1 and facing + 12000 for side 2, and the side is chosen from the three forward
rays and two side rays of length radius + 5 by the three rules listed there (a side once
chosen is kept until all three forward rays are clear).

The follower of a level path (`PathName`) and the `followPlayer` logic are in
`Creature_run` and were not read here; both are specified and executed in
`docs/spec/creature-tick.md` 4.3 and 4.5.

## 7. The camera

Functions: `Camera_init` 0x2071a8, `Camera_reset` 0x203210, `Camera_update` 0x203400,
`Camera_updateFollow` 0x204938, `Camera_computeTarget` 0x206538, `Camera_pickControllingPad`
0x206d18, `Camera_followRecenter` 0x206400, `Camera_followZoomInput` 0x205880,
`Camera_followRotateInput` 0x205db0, `Camera_followCollide` 0x204fe0, `Camera_apply`
0x2035c8, `Camera_setDistance` 0x207318, `Camera_clampStep` 0x207618, `Camera_cycleSpectated`
0x2074c8, `hud_drawNetCamPrompt` 0x1e01b8, `gameSetObjectVis` 0x1e4d48. All *(dec)*; the
camera is per machine and need not be bit-exact, with the two exceptions of 7.1.

### 7.1 What the simulation reads from the camera

1. **The yaw**, through `net_getCamYaw(slot)` in `Player_move`.
   - Offline: the live value `Camera_getYaw` (+0x68). `runObjects` runs before `task_camera`,
     so a player moves with the yaw of the previous camera update [I].
   - Net game: `net_main` samples it with each input frame (0x133464–0x133498):
     `word = s16(yaw & ~1) | (mode != 1 ? 1 : 0)`. The word travels in the input record, is
     approximated by the yaw codec (`docs/netcode.md`), and its low 16 bits land in
     `g_netCamYaw[slot]` when that frame is simulated. `Player_move` uses all 16 bits, flag
     included, as the angle (0x13e0f8–0x13e100). A rebuild's camera can differ; the value it
     **sends** is what every machine steers that character with.
2. **The mode**, as "not following" = `mode (+0x34) != 1`.
   - `net_getCamFlag(slot)`: offline the live mode, in a net game bit 0 of the same word.
     `Player_run` zeroes the pad of a player whose flag is set (4.5); `Player_move` uses it
     in the offline screen clamp. In a net game this is lockstep data.
   - `gameSetObjectVis` 0x1e4d48 (first run task) reads the **local** mode directly:
     `g_cullByCamera = (mode != 1)`, forced to 0 in a net game unless a cutscene is active.
     While it is set, object activity is measured from the camera focus (FINDINGS D6). Mode
     writers are `Camera_setMode` 0x2072e8 from: `cut_runFrame` 0x199f5c, cutscene start
     0x19b5b0, the inventory screens 0x1c1728 / 0x1c5154 / 0x1c880c, 0x1e21a0, the dialog
     code 0x22f728, and `Camera_pushState` / `Camera_popState`. D24 argues the local ones are
     locked out during a cutscene; not re-checked here.

Nothing else in sections 4–6 reads the camera in a net game. Offline, `Player_clampToScreen`
reads the frustum planes and camera position.

### 7.2 When it runs

- Offline: `task_camera` 0x1ebbe0, run task priority 11, once per simulated frame.
- Net game: from `net_predictLocalPlayer` 0x131d88. With no prediction copy,
  `engine_frameStep()` times per call (0x131dd8). With one, once after each predicted frame's
  run of the copy, unless the game is frozen, the pause menu is open or the copy is still
  catching up (0x132c30–0x132c88). It follows whatever object the player record points at,
  which during prediction is the copy.
- Also once from `player_respawn`, dialog start and the session loop.

`Camera_update`: sets "user control allowed" (+0x60) to 1 only when the game is not frozen, a
world is loaded, no dialog is open, `g_menuInputLockout` is 0, the words 0x41b4f8, 0x506048
and byte 0x4f66c8 are 0 and `game_localPlayerFlag400000()` is false. Then: mode 1, or a
pending transition (+0x48 ≠ 0), → `Camera_updateFollow`; modes 3–5 → free fly from pad 0;
mode 2 → orbit of the object named `InnoruukB`. Mode 0 is "held": nothing moves.

### 7.3 Tuning values (`Camera_init`, `Camera_reset`)

| Field | Value | Meaning |
|---|---|---|
| +0x54 / +0x58 | 1 / 0 | zoom index (0 near, 1 middle, 2 far) and the previous one |
| +0xb0, +0xb4, +0xb8 | 170.0, 340.0, 450.0 | distance per zoom index |
| +0x6c, +0x6e, +0x70 | 7500, 10000, 12000 | pitch per zoom index, angle units |
| +0xbc, +0xc0, +0xc4 | 90.0, 60.0, 60.0 | look-at height above the target per zoom index |
| +0xdc, +0xe0, +0xe4 | 150.0, 40.0, 20.0 | upper limit of the pitch velocity per zoom index |
| +0xe8, +0xec, +0xf0 | −20.0, −25.0, −25.0 | lower limit |
| +0x7e … +0x88 | 100, 4000, 6000, 8000, 9000, 10000 | probe pitches for 7.6 |
| +0x68 | −0x2000 | yaw after a reset |
| +0xa4 | −1.0 | height of a limiting plane, −1 = none |
| +0x161 | 0xff | spectated slot, none |

The distance in use (+0x8c) and height offset (+0xfc) are interpolated between the previous
and current zoom index by the blend +0x90; `+0xd8 = 1 − (distance − 170) / (450 − 170)`.
Pitch grows toward 0x3fff = straight down [I] from the limit in 7.6.

### 7.4 Follow mode, one update

1. **Target** (`Camera_computeTarget`). The local alive list (count 0x4f8424, slots
   0x4f8430) decides:
   - **one local player**: its position, height + offset. (The code goes through camera space
     and back, so the result is the position only to rounding.)
   - **several local players**: each position is brought into camera space and divided by
     its depth; the target is the centre of the bounding box of those projections at the
     middle depth, brought back to world space, height + offset. The box's width and height
     (each capped at 1) go to +0xcc and +0xd0 and their length, capped at 1, to +0xd4 — the
     "spread".
   - **all alive players in one vehicle**: the vehicle's position plus one eighth of the
     camera distance along a camera axis.
   - **no local player alive**: offline the camera stays put. In a net game, if anyone is
     alive (or the spectated slot is about to respawn) and the spectated slot has an object:
     that object's position, height + offset, and the byte 0x4f66c9 is set.
   - on a transition frame (+0x48 ≠ 0): the plain average of the local players, and the
     spread from the largest distance of any alive player to the first, divided by 480.
2. **Look-at smoothing.** `look (+0x24) += (target − look) × g × (1 − b)` with `g` =
   0x3f7ffee2 (0.99998) on x and y — effectively none — and 0x3d75b5fa (0.059988) on the
   height (0x3e9991bc, 0.29994, during a zoom change). `b` (+0xc8) is 1 right after the
   number of local alive players changes (offline only) and decays by 5 % per frame. With
   one local player and `b` ≠ 0 the
   step is limited to 5 units; with several it is weighted by
   `max(0, 0.9 − spreadX) × max(0, 0.7 − spreadY)` along the camera axes and limited to
   ±3, ±3, ±1. On a transition frame or while the snap counter +0x16d runs (set to 5 by
   `Camera_snapFor5Frames`), `look = target`.
3. **Controlling pad** (`Camera_pickControllingPad`): the previous controller keeps the
   camera while its camera stick is at |x| ≥ 0.5 or |y| ≥ 0.9 or it pressed R3 (0x400);
   otherwise the local alive player with the largest |x| + |y| (+0.5 for R3), the first
   listed winning ties. (Button names follow the layout `docs/netcode.md` infers.)
4. If user control is allowed: recenter, zoom, rotate, collide (7.5, 7.6).
5. **Placement.** Orientation: identity, rotated about X by `s16(pitch + 0x3fd3)`, then
   about Z by the yaw (`Camera_apply`; which way `mat34_rotateAxis` composes was not read
   [U]). Position = `look − distance × forward`, where `forward` is the three floats at
   `g_cameraMatrix` +8, +0x14, +0x20. If +0xa4 ≠ −1 the distance is shortened to where that
   ray meets the horizontal plane at that height. `Camera_apply` also adds the shake: while
   `g_cameraShake` > 0, three cosmetic random offsets scaled by it, and it decays by 0.5 per
   call.

### 7.5 Player control

**Rotate** (`Camera_followRotateInput`). Disabled by level flag 0x2000000 and during a zoom
change. `a = |rx|`, multiplied by 0.59499496 at zoom index 0 or in PvP mode B. The yaw
velocity +0x3c is an integer in angle units per frame:

- stick beyond 0.01, and at most two local players alive, and (one local player or spread ≤
  0.7): `want = powf(a, 0.95) × g_camRotationSpeed (0x4f8404) × 192.0`, negated for a
  negative `rx` and again when the invert option 0x4f8460 is set;
  `vel = int(vel + (want − vel) × 0.125)`.
- stick centred: `vel = vel − int(vel × 0.25)`, and 0 once |vel| < 20. Unless the auto-follow
  option 0x4f845c is on, with one local player, at zoom index 0 with the zoom settled: then
  the camera is drawn behind the character — toward yaw `0x3fff − facing`, with strength
  `124 × min(1, |difference| × 6.25e-05)²` scaled by the movement stick's length, approached
  10 % per frame.
- all players in a vehicle: `vel = direction × 96 × min(1, |difference| × 0.00025)` toward
  the same "behind" yaw.
- `vel` is limited to ±274 except in the two automatic cases. Then
  `yaw += int(f32(vel) × 0x3f7fffff)`.

`g_camRotationSpeed` is 1.0 unless the level sets `camRotationSpeed=`.

**Recenter** (`Camera_followRecenter`): pressing L3 (0x200) with the movement stick inside
its dead zone (length² < 0.032), one local player, not in a vehicle, sets the yaw goal +0x8a
to `0x4000 − facing` of the followed (or spectated) player, or −0x2000 when there is none,
and a turn direction +0x38. While it runs, `vel += direction × 24` per frame until within
1000 units of the goal, then `vel = round(vel × 0.85)` until below 50, which ends it.

**Zoom** (`Camera_followZoomInput`), one local player: pushing the camera stick's y beyond
0.9 — once per push; the stick must return inside 0.9 first — steps the zoom index up
(positive y) or down. The change takes 25 frames: a timer advances by 0x3d23d70a (0.04) per
frame and the blend is `math_hermite(t, 0, 1, 0.5, 0.5)`. Not while the button mask at
0x41b9e0[slot] is held, and not at all when the level locked the zoom (+0x50, set by
`Camera_selectZoom1`). With several local players the zoom is automatic: index 1 against
"previous" 2 with a blend that approaches `1 − clamp(2 × max(0, spread − 0.1), 0, 1)` by 5 %
per frame, i.e. it backs out toward 450 as the players spread.

Which physical direction is "positive y" follows from the stick bytes (section 2); not
checked against a pad [U].

### 7.6 Collision with the level

`Camera_followCollide` never shortens the distance. It **raises the pitch** until the
characters are visible:

- For each followed player (the local alive ones; the spectated slot when none), rays are
  cast with `terrain_raycast` 0x18a5c0 from 40 units above the player, length +0xb4 (340),
  at five pitches (table +0x80…+0x88) in four horizontal directions fanned around the
  direction from the look-at point to the camera — a fan of `4000 + 6000 × (+0xd8)` angle
  units, 12000 with several players. One direction per update in turn (all four on a
  transition or snap frame). Hit/no-hit bits are kept at +0x100 (6 bytes × 4 directions per
  slot).
- The lowest blocked pitch level over all directions and players gives a required pitch
  `0x3fff − table[+0x7e + 2 × max(0, level − 1)]` (`level − 2` with several players). The
  wanted pitch is the larger of that and the zoom index's pitch.
- The pitch follows with a velocity (+0x98): rising, it gains
  `(wanted − pitch) × (0.002 + 0.008 × (+0xd8)) × clamp(wanted × 6.25e-05, 0, 1)` per frame;
  falling, `(wanted − pitch) × 0.001`; then × 0.92, limited to the table of 7.3 and to
  `(0x3fff − pitch) × 0.05`. With several players the gains are 0.001 both ways, the damping
  is `0.95 × (1 − spread³)` and the limits −15 and 35.
- During a zoom change the pitch is interpolated instead.

### 7.7 Spectating after death (net game)

`hud_drawNetCamPrompt` 0x1e01b8 — HUD draw code — runs when the local player has no hit
points and no pending respawn while someone is alive. It keeps the spectated slot +0x161 on
an alive player (`Camera_cycleSpectated(cam, 0)`), moves to the next one when the local raw
pad has the button in 0x41bfbc newly pressed (not during a dialog, cutscene or pause menu),
and draws the name. A change calls `Camera_reset(cam, 0, 0)` and a short fade. While
spectating, `Camera_computeTarget` follows that player's object. All of it is local; the
dead player's own input record keeps flowing with whatever yaw the spectating camera has.

## 8. Where floating-point details decide the position

Background, **not from the executable** — from published descriptions of the console's CPU;
treat as [U] until checked on hardware or against the emulator the other players use: the
FPU is single precision only; it always rounds toward zero; it has no infinities, NaNs or
denormals (a division by zero or an overflow gives the largest finite value, an underflow
gives zero); float-to-integer conversion truncates and saturates; and emulator authors report
that its multiply and divide can differ from a correctly truncated result in the last bit. A
rebuild that must stay in step with consoles or emulators has to run sections 2–6 on a
software model of that arithmetic, and every peer's emulator has to be configured alike.

From the executable [O]:

| # | Place | What matters |
|---|---|---|
| F1 | every literal | stored truncated, not rounded: `DT` 0x3c888888, 0.4 = 0x3ecccccc, 0.2 = 0x3e4ccccc, 0.05 = 0x3d4ccccc, 0.001 = 0x3a83126e, 1.2 = 0x3f999999, gravity 0x410fffff. Take bit patterns from this document, not decimals |
| F2 | `atan2f`, `atanf`, `ceilf`, `floorf`, `powf` (0x3a5a80, 0x3aa558, 0x3a5710, 0x3a57e8, 0x3a5ac8 → 0x3a7930) | the game's own copies, built by the same toolchain (π is 0x40490fda where the nearest float is 0x40490fdb) and run on the console's arithmetic. A host math library gives different last bits. Their bodies were identified, not transcribed: a rebuild needs them constant by constant. `powf` is used here by the camera only |
| F3 | `Creature_turnToward` 0x10bbc8 | `sqrt(0x3e4ccccc)` computed by the FPU on every call: 0x3ee4f92d if the result is truncated, 0x3ee4f92e if rounded to nearest. Every monster turn depends on it. [U] which — one read of the register settles it |
| F4 | `Player_move` 0x1b4fd4–0x1b5004, `obj_moveWithCollision` 0x14d53c–0x14d550 | position advance: `W = V + root × 60.0` first, then `d = W × DT`, then the slide adds `step × t`. Not the same bits as `pos + V × DT + root` |
| F5 | `Player_move` 0x1b4a40–0x1b4b30 | the velocity is built as `A × p + B × q` through two cosines and two sines of the camera yaw. Computing `180 × s × (cos F, sin F)` directly is not bit-identical |
| F6 | `Player_move` 0x1b41c4–0x1b41e4 | `S × sqrt(lx×lx + ly×ly)`; product order of `S` in 4.1(b): base × record multiplier × level speed, cap, then Drowsy |
| F7 | slow factor | three different groupings: `V × (f32(60−n) × DT)` in `Player_move`, `Creature_moveTo`, `Creature_turnToward`; `(speed × f32(60−n)) × DT` for the animation speed in `Player_animStep` and `Creature_stepAnim`; integer `rootYaw × int(k)` in `Creature_stepAnim` |
| F8 | `math_cos16` | half-angle polynomial in the exact operation order of section 3; `sin16` is `cos16` of the angle minus 0x4000, not a second polynomial |
| F9 | `terrain_sweepCircle` | all of 5.3: positions scaled by 0.25 after the rotation; `inv = 1.0 / len` then multiplied (not `x / len`); `t = best × inv`; the reciprocal-square-root instruction for the normal; the quarter-distance centre; `1.0 / 0` for a vertical step |
| F10 | `world_slideMove` | `k = 0.001 − ((N.x×D.x + N.y×D.y) + N.z×D.z)`; `P += step × t` per component; iteration cap 11 |
| F11 | push-out, 5.5 / 5.6 | `k = ((r1 + r2) − dist) / dist`, `push = (dx × k, dy × k)`; overlap test `dist + 0.001 < r1 + r2` |
| F12 | ground, 5.5 | `vz − 0x410fffff`; `z + vz × DT`; `(z − 0.01) ≤ ground`; heights compared as `f32(int)` |
| F13 | float → integer, truncating | `atan2_16`; `angle_approach` step; three conversions in `Creature_turnToward`; grid cell `(int(x) + 0x3c00) >> 8` (truncation first, then an arithmetic shift: every x in (−1, 1) is integer 0); box-query cells; `int(floorf(…))` and `int(ceilf(…))` in the terrain code; the slow amount `int(chill)`; the sync hash's `int(x), int(y), int(z)` of each player (`docs/netcode.md`) |
| F14 | integer → float | stick bytes; `f32(60 − n)`; element positions, sample indices and heights in the terrain code; waypoints (`f32` of integer x, y); frame differences in the melee timing tests |
| F15 | 16-bit wrap | facings and yaws wrap by `s16`; but `|T − F|` in mode 1 (4.1 d) and the 16000 test on slot 26's return are done on unwrapped or already-wrapped values exactly as written |
| F16 | double precision | the three locomotion track weights in 4.1(g) are computed in software doubles and narrowed; they feed animation weights, hence root motion and event timing |
| F17 | random draws tied to movement | `g_randSeed` once when a player enters water (4.1 f); the creature's own generator when a monster or projectile enters water, in the knock-back dust (a data-dependent number of draws) and in the stuck side-step; `world_findFreeSpot` on the shared seed for the stuck teleport |
| F18 | order of evaluation across objects | LIFO run list; box-query order (rows, columns, cell list head first, relinked on every move); caps of 15 / 63 / 255 results; the stamp counter of `terrain_collectElements` (only equality with the current value matters) |
| F19 | stick codec | single-precision spring and truncation to a byte before any of this (`docs/netcode.md` item 11) |

## 9. Corrections, proposed ledger rows, patches

**Corrections to earlier documents**

- `docs/creatures.md`, creature flag 0x2000000 "animation root motion not applied to the
  position": the flag selects whether `Creature_stepAnim` passes a sound position to
  `anim_advance` (0x116330–0x116348). Root motion is produced and applied regardless.
- `docs/creatures.md`, slot 26: it returns the signed angle to the point as it was before the
  turn (0x10bb9c–0x10bbb4 leave it in the result register); the move helpers halve the speed
  when it exceeds 16000.
- `docs/issues/lag.md` §8 "whether movement speed scales with that value is Unknown": it
  does, linearly (4.1 c, g).
- FINDINGS D14 "counter 2 gives the player +0.25 speed … counter 4 gives +0.1 speed": that is
  the melee swing rate (0x1aa0f0–0x1aa11c), not movement speed.
- `docs/gameplay.md` §5, `Camera_followCollide` "keeps the view clear with world ray casts":
  it does so by raising the pitch; the distance is never shortened by terrain.
- `docs/player.md`, open question "does creature move/collide call the touched slot of other
  objects when the mover is the copy": no (0x14d9b0–0x14d9b8); `docs/objects.md` O7 already
  says so.

**Proposed ledger rows** (for review; not added to FINDINGS.md)

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| MV1 | Movement results depend on the console's floating-point behaviour in at least one run-time-visible way: `Creature_turnToward` takes the square root of 0.2 on every call, and the truncated and nearest results differ (0x3ee4f92d / 0x3ee4f92e). Two machines whose FPU emulation rounds differently diverge on the first monster turn | Observed (instruction, both values); the divergence is Inferred; which value real hardware gives is Unknown | 0x10bbc8 |
| MV2 | `Player_move` zeroes the stick while `dialog_isOpen()`, with no test for a net game, and `Player_run` swaps in the zero pad on the same test. `docs/script.md` records that dialog progress is driven by a local task. If a dialog can be open on one machine and not another for a frame, that player's position differs | Observed (reads); whether the state can differ is Unknown | 0x1b40c0, 0x1a565c |
| MV3 | The contact normal of the terrain sweep is taken from a point one quarter of the travelled distance along the step. Harmless to sync (same on all machines) but a faithful rebuild must copy it | Observed | 0x186088–0x1860c4 |
| MV4 | A player's facing in a net game uses the 16-bit yaw word of the input record including its bit 0, which is the "camera not following" flag | Observed | 0x133464–0x133498, 0x13e0f8 |
| MV5 | In a net game a player in action state 3, 4, 10 or 0xc is not passed to any move routine: no gravity, no push-out, no knock-back | Observed (no call in those states; knock-back zeroed at 0x115ef4) | `Player_run` switch 0x1a5e80 |

**Patches.** None proposed. Nothing found here is a defect that a one-word change would
repair without changing the simulation for every player.

## 10. Not reached

- `Creature_run` beyond the slow amount: the `PathName` follower, `followPlayer`, the
  drawing-height smoothing at +0x3c. (Reached since: `docs/spec/creature-tick.md` section 4.)
- Per-class movement: each monster's run function (order of turn, animation and move; which
  helper; move speed +0xb8 and turn rate +0xb0 values), and each projectile class's velocity,
  gravity and reaction to `obj_moveAndCollide`.
- `Creature_computeAvoidanceOffset` side selection; `creature_findClearHeading` 0x10eaa8;
  `Creature_pickWanderDest` 0x119618; `Creature_randomPointNearHome` 0x110b58. (Reached
  since: `docs/spec/creature-tick.md` sections 10 and 11.)
- `terrain_raycast` 0x18a5c0 and `world_raycast` 0x18ad94 (used by the probes and the
  camera), `world_findFreeSpot` 0x14acf8, `water_test` / `water_disturb`. (Reached since,
  the water routines excepted: the two rays in `docs/spec/world-queries.md` section 9,
  `world_findFreeSpot` in `docs/spec/object-system.md` 4.8.)
- The path search itself and `path_request*` (`docs/engine.md` has them; specified and
  executed in `docs/spec/world-queries.md` section 10, which corrects `engine.md`).
- `anim_advance` — how the root delta is produced; `docs/formats/anim-audio.md` and
  `docs/engine.md` cover it. Root motion is taken here as an input.
- The stick and yaw codecs (specified in `docs/netcode.md`; not re-derived).
- Vehicles: `Vehicle_collideObjects` 0x20e33c is the fifth caller of `world_slideMove`.
- Camera: `Camera_updateFree`, `Camera_updateOrbit`, `Camera_setupDialogView`, 0x204250, the
  save/load of camera state, the composition order of `mat34_rotateAxis`, and exact operand
  order anywhere in section 7.
- The functions 0x260910 (a caller of `creature_moveSimple`), 0x2c95f4 (told when a rush hits
  something), 0x1857e4 and 0x185448 (terrain routines beside the sweep).
- Nothing was run (when this was written; the run speed has been measured on the live rig
  since, see the head of the document). In particular the hardware facts at the head of section 8 and the value in
  F3 want one emulator or console trace each.
