# Creature tick: the base class every monster shares, one tick in order

This document is the prose of `tools/ref_creature.py`, the reference model of the `Creature`
base class (most of it in 0x108a60–0x11a920 of `SLUS_209.73`, US v2.00). Every statement in sections
2–12 was read from the instructions at the address given and then **executed**:
`tools/difftest_creature.py` runs the original functions under the instruction interpreter
`tools/ee_emu.py` and the model on the same inputs and compares calls, stores, seeds and
results (section 15 gives the counts and the coverage). Statements about code that was
read but not executed are marked **[O]** (Observed) and are few; **[I]** is Inferred.
Nothing here was run on a console or a whole-machine emulator
(`docs/issues/dynamic-tests.md`).

Read `docs/creatures.md` for the object layout and `docs/monsters.md` section 1.3 for how a
class uses the base. Offsets below are creature offsets unless a register or object is
named.

## 0. Conventions

- `c` is the creature. `flags` is the object flag word `c+0xc` (0x20 monster, 0x40 player,
  8 dead, 0x20000 prediction copy); `cflags` the 64-bit creature flag word `c+0xa8`;
  `state` the AI state `c+0x232`; `slow` the slow amount byte `c+0x2fc`; `frame` =
  `g_simFrame` 0x44fdcc; `serial` the signed byte `c+0x230`; `clock` the creature clock
  `c+0x300`.
- Floats are given as bit patterns where the decimal would mislead (the game's literals are
  truncated: 0.1 is 0x3dcccccc). `DT` = 0x3c888888 (1/60, truncated). "×", "+", "−" on
  floats are one R5900 single-precision operation each, in the order written. `int(x)`
  truncates toward zero, `f32(i)` converts an integer.
- `slowK` = `f32(60 − slow) × DT`, used only when `1 ≤ slow ≤ 60` (tested as unsigned
  `slow − 1 < 60` at five sites). A slow byte of 0, or of 61–255, changes nothing.
- A **shared draw** advances `g_randSeed` 0x404464 (`s = s × 0x19660d + 0x3c6ef35f`, value
  `s >> 16`). An **own draw** is `GameObject_rand` 0x1509d0 on `c+0x44`, the same generator
  on the object's own seed. The **third generator** 0x404468 is per machine.
- `slot N` is a virtual call through the table at `c+0x48` (8 bytes per slot: a 16-bit
  `this` adjustment, then the function). A handle is a word pointing at a node whose `+0xc`
  is the object; `target` is the object behind `c+0x234`.
- Every 8th / 32nd / 64th frame "staggered" means `(frame ^ serial) & 7 / 0x1f / 0x3f == 0`.

## 1. There is no single tick function

The base class's own run (virtual slot 4) is an empty stub. One tick of a monster is its
class's run function, which calls base-class functions in this order (`docs/monsters.md`
1.3; the addresses in the last column are the calls in `Skelight_run` 0x2a8b84, the one
class whose run was re-read for this document **[O]**):

| # | Call | Section | In `Skelight_run` |
|---|---|---|---|
| 1 | `Creature_processDamage(c, model)` 0x110d30 | 3 | 0x2a8bb0 (skipped in state 0x17) |
| 2 | `Creature_run(c, model)` 0x112948 | 4 | 0x2a8bc0 |
| 3 | `Creature_updateActive(c)` 0x10c0f0 | 2 | 0x2a8bd4 |
| 4 | the weapon holder at `c+0x50`, if any (section 12.4) | 12.4 | 0x2a8be0–0x2a8c48 |
| 5 | `Creature_stepAnim(c; speed)` 0x1162b0 → event bits | 7.2 | 0x2a8c54 |
| 6 | `Creature_applyKnockback(c; scale)` 0x115eb8 | not modelled | 0x2a8c6c |
| 7 | slot 23 `Creature_pickTarget(c, 0)` 0x10ded0 | 6 | 0x2a8c88 (table offset 0xb8) |
| 8 | `switch (state)`: the movement helpers of sections 8–11, attacks, and one slot-27 set-state | 8–12 | 0x2a8c90 |

So the things a reader might look for at the top of "the creature tick" are in different
places:

| Looked for | Where it really is |
|---|---|
| "dead" entry test | no test at the top of `Creature_run`. A corpse is AI state 0x14; each function tests it for itself (`Creature_processDamage` 3.1, `Creature_pickTarget` 6, `Creature_spawnScavenger` 4.11, the corpse deletion 4.14), and the class's switch only calls `Creature_deadUpdate` in that state |
| inert bits `c+0x231` | tested by slot 2 (any bit: no damage), slot 23 (any bit: no target work), `Creature_moveBy` (bit 8: no movement), the boss meter (any bit), `Creature_moveToDirect` (any bit: no avoidance refresh), `Creature_filterState` (any bit refuses state 1). `Creature_run` itself runs in full for an inert creature |
| frozen by a cutscene | the freeze is inert bit 0x10 (`creatures_freezeAll`); see the row above. `g_cutsceneActive` 0x44fcd0 is read once, in the stuck recovery of `Creature_moveTo` (9.5) |
| far from every activity centre | `Creature_updateActive` (section 2). Its answer is the function's result, which the class may use to return early, and creature flag bit 63, which `Creature_stepAnim`, the follower warp, the boss meter, the scavenger and the corpse deletion read |
| regeneration | none. No function of the base class adds hit points; `c+0x228` is written only by slot 2 (minus) and by callees outside this model |
| pending damage, target selection | separate functions the class calls (rows 1 and 7), not parts of `Creature_run` |

`Creature_run` returns 0 on every path (0x113c10). The class code tests the result
(`bnezl` at 0x2a8bc8) and would leave; that exit is never taken.

## 2. Activity — `Creature_updateActive` 0x10c0f0

```
was = cflags bit 63
cflags bit 62 = was                                             "was active"
r   = max(u16 c+0x3c4, u16 c+0x3ac, u16 c+0x3ae)                activity radius, pointblankrange, visualrange
now = obj_updateActive(c, was, r) != 0
if (flags & 0xc00000) and was != now:                           OBJECT flag bits, see docs/creatures.md C12
    s = obj_getPropStr(c, now ? "followFoundScript" : "followLostScript", 0);  if s: script_runByName(s)
if now: cflags bit 63 = 1
else:   anim_releaseCaches(c+0x114);  cflags bit 63 = 0
return now
```

`obj_updateActive(obj, was, r)` 0x14db08: `r` is replaced by 44000 for an object with flag
0x80000; the test is `dx² + dy² + dz² < f32(r × r)` (3-D, strict; `r × r` is a 32-bit
integer product, so a radius above 46340 can never be met). The centre is
`g_cameraFocus` 0x44f048 when the byte `g_cullByCamera` 0x4039c1 is non-zero, otherwise each
of the `g_activityCenterCount` (0x403a08, s8) entries of `g_activityCenters` 0x4039c8 in
turn. When the answer differs from `was`, the object's run-list node (`obj+4`) is removed
and the object is linked into `g_runListActive` 0x5db3a8 (now active) or into one of the
sixty slow lists `g_runLists60` 0x5db3f0, chosen by a round-robin cursor 0x4039fc that is
advanced first and wraps at 60.

`isNearView(pos; d)` 0x1e77c0, used by the path follower (4.3): a square test,
`|pos.x − cx| ≤ d` and `|pos.y − cy| ≤ d` (as four `≤` on `cx ± d`), against the camera
focus when `g_cullByCamera` is set, else against each player object of slots
`0..g_numPlayers−1` (a slot without an object is skipped).

Both the camera branch and the list of activity centres are per machine while a cutscene
runs in a net game (FINDINGS D6); section 14 lists what follows from bit 63.

## 3. Pending damage — `Creature_processDamage(c, model)` 0x110d30

Slot 2 (12.1) has already subtracted the hit points; this function reacts to what it
accumulated: the amount `c+0xc8` and the OR of the hit flags `c+0x2dc` ("df").

### 3.1 Entry

```
if not (0 < c+0xc8):                                            nothing pending (0x112320)
    if state != 0x14:
        knock(df; 50, 75, 100, 156.25)
        if df == 0x2000 exactly and state != 0x12:  reaction()
    df = 0;  return
if g_numPlayers == 1:  world_notifyObjectsNear(0, pos, c; 600.0)
c+0xc8 = 0
if state == 0x14:  return                                       a corpse: df is NOT cleared here
flags |= 0x100
if df & 0xd:  hitEffect()                                       3.2
if hp > 0:                                                      survived (0x112250)
    if state != 0x14:
        knock(df; 100, 150, 225, 375)
        if not (df & 0x400000) and state != 0x12:  reaction()
    df = 0;  return
die()                                                           3.4
df = 0
```

`knock(df; a, b, c, d)` stores the knock-back speed `c+0x2e8` for the **first** set bit of
0x40000, 0x80000, 0x100000, 0x200000 and leaves it alone when none is set. The three
tables (patterns): no pending damage 0x42480000, 0x42960000, 0x42c80000, 0x431c4000;
survived 0x42c80000, 0x43160000, 0x43610000, 0x43bb8000; death 0x42c80000, 0x43160000,
0x43480000, 0x439c4000.

### 3.2 The hit effect (flags with any of bits 1, 4, 8)

The effect position: `model_getBounds(model, −1)` gives six integers (zeros without a
model). With a radius of 25 or more the point is pushed 0.75 radius toward the attacker:
`pos + (cos, sin)(s16(c+0x2e0) + 0x7fff) × (radius × 0x3f400000)`; otherwise x, y are the
position. z = `pos.z + 36.0`, except for a model whose sixth bound is below 36 and above
its third: then `pos.z + f32((sixth − third) / 2) + 12.0`.

The first matching row decides; all draws are own draws, and "gib(k)" is
`pool_new(0x268)` and, only when a block came back, `GutChunk_ctor(block, point, 2, k; 1.0)`:

| Condition | What happens |
|---|---|
| chill `c+0x344` > 0, or cflag 0x4000 | `fx_spawn(10, point)` |
| cflag 0x8000 | `fx_spawn(0xb, point)` |
| cflag 0x10000 | `fx_spawn(2, point)` |
| cflag 0x20000 | `libc_sprintf` + `res_find` in the effects lump + `sound_playOnObject(…, c; 1.0)`; two `model_getAttachPoint` (indices 0, 1); fifty `particle_spawn(def 0x5bf608, midpoint, v; 0.0)`. `v` starts as `(cos F × 10, sin F × 10, 10)` and each spark **adds** `5 ×` a random point of the unit ball to it (three own draws per try, `2u − 1`, retried while the squared length exceeds 1): the velocity accumulates over the fifty |
| cflag 0x2000 | `fx_spawn(3, point)`, gib(5); one own draw, `% 3 == 0` → gib(5) again; and when `hp ≤ 0` a second own draw, `% 3 == 0` → gib(5) |
| cflag 0x1000 | the same with `fx_spawn(9, …)` and gib(3) |
| cflag 0x40000 **and** (`g_decalDetail` 0x44fdc0 > 0 **or** `g_networkMode` ≠ 0) | `fx_spawn(0, point)`; one own draw, `% 3 == 0` → gib(1) |

The draw before a gib is made whether or not the pool then has a block. The last row is
the per-machine option arranged so that a net game does not depend on it
(`docs/creatures.md` C6).

### 3.3 The hit reaction

```
reaction():
    if cflags & 1 (MiniBoss):
        if g_numPlayers >= 2:  return
        if own draw is even:   return
    if df & 0x4380000:                        (0x4000000, 0x200000, 0x100000, 0x80000)
        slot 27 (c, 0x12);  return
    if cflags & 0x400 and (own draw % 3) != 0:
        slot 27 (c, 0x12);  return
    if (own draw % 3) != 0:  return
    slot 27 (c, 0x12)
```

The flag test is made on the high half of a 64-bit load at `c+0x2d8` (0x112418), which is
`c+0x2dc`. In the no-pending case df is exactly 0x2000, so only the one-in-three (or, with
cflag 0x400, seven-in-nine) branch can fire there.

### 3.4 Death (hit points ≤ 0), in order

1. `flags |= 9`. Each of the five second-timers `c+0x340 … c+0x350` above 1.0 becomes 1.0.
2. One of (first match):
   - `df & 0x20` → `flags |= 0x2000000`. (The code also tests `1.0 < c+0x340` here,
     0x1114fc; after step 1 that cannot hold.)
   - `df & 0x10` and a model → `fx_disintegrateModel(c, model, c+0x114, pos, F, 0; c+0xdc, c+0xe0)`.
   - `df & 0x2000000` and a model → the same with 1.
   - otherwise ice or gibs:
     - not a MiniBoss, cflag 0x20000000 clear, chill > 0, a model, and an own draw with
       `& 7 == 0`: `fx_shatterToLooseIce(model, c+0x114, pos, F, c+0x320; radius, c+0xdc, c+0xe0)`,
       then "body removed" below. (The draw is made only when the four conditions hold.)
     - else, when cflags has neither 0x20000000 nor 1, and `df & 0x800`, and
       `df & 0x3c0000`, and (cflag 0x3000, **or** cflag 0x40000 with `g_decalDetail > 0`
       and `g_networkMode == 0`): the gib burst.
       With `g_decalDetail > 0` only: two draws of the **third generator** for
       `decal_add(pos, angle, kind, 0; 44.0)` (`angle` = the first draw as a signed 16-bit
       value, `kind` = bit 0 of the second + 4 / 7 / 1 for cflag 0x2000 / 0x1000 / neither),
       then three `fx_spawn(9 / 3 / 1, pos + (0, 0, 36) + 10 × ball)` with the ball point
       from the third generator (three draws per try).
       Then, on every machine: two chunks and four chunks. Each: `pool_new(0x268)`; with a
       block, one own draw `% 3` → `GutChunk_ctor(block, pos, that, k; 1.0)` with k = 2 /
       5 for cflag 0x1000 / 0x2000, else 0 for the first two and 1 for the last four; then
       two more own draws: push = `f32(d) × 2⁻¹⁶ × 80.0 + 20.0` (last four: `× 50.0 + 10.0`),
       angle = `s16(0xe0c0 + d % 16000)` (last four: `s16(0xb1e0 + d % 40000)`);
       `block+0xfc = block+0xfc × 0x3e999999 + cos(s16(c+0x2e0) + angle) × push`, `block+0x100`
       likewise with the sine; `PhProp_initPhysics(block, 0x12)`. Then "body removed".
     - "body removed": `flags |= 0x4002`, `cflags |= 0x20000000000`.
3. `knock(df; 100, 150, 200, 312.5)`.
4. **slot 27 (c, 0x14)** — the class's set-state; it is where `Creature_dropLoot`, the
   death animation and slot 28 are called (`docs/issues/kill-loot-xp.md` section 2).
5. `flags |= 0x2000`.
6. `obj_getPropInt(c, "Dead", 0)` non-zero → `anim_snapTopToEnd(c+0x114)` and nothing more.
   cflag 0x100000000 → nothing more.
7. `sum` = the level bytes (record +0x59, signed) of slots `0..g_numPlayers−1`;
   `base = int(powf(c+0xd8 / f32(sum), 0x3fb33333))`.
8. The killer: the object behind `c+0x2e4` compared with each record's object pointer;
   slot 0 wins if it matches, otherwise the **last** matching slot of 1…; −1 for no player.
9. With a killer: `player_getSkillRank(killer, 0x3b)`, then
   `SkillLifeTap_getStat0Fraction(*0x41b25c, rank)` → fraction, then **one own draw** `d`;
   when `f32(d) < fraction × 65536.0`: `pool_new(0xb8)` and, with a block,
   `OniBall_ctor(block, pos, F, c, 0)`.
10. `xp = int(f32(base) × 0x3f400000)`.
11. One player (`g_numPlayers < 2`): if its record hit points are above 0:
    `xp = min(xp, cap)`, `player_giveExp(slot, xp)`, and for record class 0 (record +0x50)
    mana (+0xc0) += `c+0x22c × 0x3d088888`, capped at +0xc4 — whoever made the kill.
    Several: for each slot, share 0x3f000000 with no killer, else 0x3f199999 for the
    killer and 0x3ecccccc for the others; `n = int(f32(xp) × share)`; a player with record
    hit points ≤ 0 gets `int(f32(n) × 0.5)`; `player_giveExp(slot, min(n, cap))`; class-0
    mana for the killer only.
    `cap` = `g_expTable[level + 1] − g_expTable[level]` below level 80, `g_expTable[level]`
    from 80 (table 0x41b558).

No shared draw is made by this function itself; constructors and `fx_shatterToLooseIce`
make their own (section 13).

## 4. `Creature_run(c, model)` 0x112948, in order

### 4.1 Spells follow (0x112984)

Non-players only: slot 17 with the point `(pos.x + 0.0, pos.y, pos.z + height × 0.5)`. The
base body `Creature_updateSpells` 0x11a868 walks the attached-spell list `c+0x364`
(`iter_begin(…, 0)` / `iter_next` / `iter_end(…, 2)`) and calls each spell's slot 2 with
the point and the facing.

### 4.2 Flash colours (0x112a00)

Each of the eight signed halfwords `c+0x98…0x9f`, `c+0x90…0x97` moves 2 toward 0 and
stops at 0. Presentation only.

### 4.3 The `PathName` follower (0x112a80) — cflag 0x8000000

```
name = obj_getPropStr(c, "PathName", 0);  if none: skip
pathFollower_init(follower, name, pos);   list = paths_findByName(name)
i = s16 c+0x58;  if i == −1:  i = pointList_snapToNearest(follower)
p = pointList_getPoint(list, i);  if none: skip
if sqrt((pos.x − p.x)² + (pos.y − p.y)²) < 48.0:
    q = pointList_getPoint(list, i + 1)                         NOT tested for null
    dest(c+0x104) = home(c+0x3b4) = q.pos;  c+0x54 = clock + 600;  c+0x58 = u16 q+0x3c
else:
    dest = home = p.pos
    if s16 c+0x58 != u8 p+0x3c:  c+0x54 = clock + 600;  c+0x58 = u16 p+0x3c
    if u8 p+0x3c == s16 c+0x58 and c+0x54 < clock and not isNearView(pos; 1000.0):
        pos = home;  obj_updateGridCell(c)                      600 clock ticks late and unseen: jump there
```

The last line is `docs/creatures.md` C4. The unchecked `q` is a read through a null
pointer at the end of a list (0x112b68; the test made both sides fault there, section 15).

### 4.4 Frame timers (0x112c6c)

| Field | Rule | Extra |
|---|---|---|
| `c+0x316` no-target | non-zero: −1 | `fx_spawn(0x12, pos + (0, 0, height))` when `frame & 3 == 0` |
| `c+0x314` root | −1 unless 0 or −1 (−1 = permanent) | |
| `c+0x318` attack cooldown | non-zero: −1 | |
| `c+0x31a` spell speed | non-zero: −1 | |
| `c+0x31c` stun | non-zero: −1 | `fx_spawn(0x10, pos + (0, 0, height))` when `frame & 3 == 0` |

### 4.5 Charm and followPlayer (0x112d64)

```
if c+0x312 == 0:
    if cflags & 0x2000000000000 and state != 0x14:  slot 27 (c, 0x14)       dies when its charm has ended
else:
    if c+0x312 != −1:  c+0x312 −= 1
    if c+0x312 == 0:   team(c+0x310) = 0xff;  cflags &= ~0xc00000
    if cflags & 0xc00000:  follow()
```

So the followPlayer bits act **only while the charm timer is non-zero**.

```
follow():
    s = s8 c+0x5a
    if s < 0 or s >= g_numPlayers or no object in slot s or that object is dead:
        c+0x5a = players_findNearestOnTeam(pos, s8 team; 500.0)
    else:
        home = leader.pos;  o = (cos, sin)(leader.facing) × 30.0
        home.xy = cflags & 0x400000 ? home.xy + o : home.xy − o        ahead of / behind the leader
        if Creature_isAwayFromHome(c):  dest = home
    if cflags bit 63 (active):  return
    origin = home + (0, 0, 11.0);  b = atan2_16(pos.y − home.y, pos.x − home.x)
    for i in 0..31:   a = s16(b + k),  k = 0, 0, +0x800, −0x800, +0x1000, −0x1000, … ±0x7800
        dir = (cos a, sin a, 0) × g_followTeleportDist(0x40278c)
        t = terrain_raycast(g_world, origin, dir, 3; 0x3f8ccccc);  if t < 0: t = 1.0
        if not (1.0 <= t):  continue
        spot = home + dir × t
        if players_anyWithinRadius(spot; 450.0):  continue
        pos = spot;  obj_updateGridCell(c);  obj_runEveryFrame(c);  cflags bit 63 = 1
        dest = home;  Creature_clearPath(c);  return
```

`players_findNearestOnTeam` 0x1124e0: live player objects in slot order within the reach
(3-D); a team of −1 accepts everyone, otherwise the record's team byte +0x4c24 must match;
of two at exactly the same distance the later slot wins. The warp at the end runs only for
a creature that is **not active** — see section 14.

### 4.6 The creature clock (0x113178)

`clock += 1` unless `slow == 60` exactly. (For `1 ≤ slow ≤ 59` the code computes
`frame % (60 / (60 − slow))` and `frame % (60 / slow)` and uses neither result.)

### 4.7 The slow amount: three writers in this order (later wins)

1. Level flag 0x100 of 0x44fe08 (the cold level): `slow = 10` for a player, `15` otherwise,
   every tick (0x1131e8).
2. Chill, when `c+0x344 > 0` (0x113608):
   ```
   c+0x344 −= 0x3d888888 (1/15);  if c+0x344 <= 0:  c+0x344 = 0, slow = 0
   slow = dead ? 0 : (c+0x344 <= 60.0 ? int(c+0x344) : 59)
   lim = 60.0 − c+0x60 × 60.0;  if lim < f32(slow):  slow = int(lim)          cold resistance
   player:                if slow >= 31: slow = 30;   c+0x344 −= 0x3d088888 (1/30)
   creature_bossRank(c):  if slow >= 16: slow = 15
   anyone else:           if slow >= 31: slow = 30
   ```
3. Status counter 7, when `c+0x388 != 0` (0x113738):
   ```
   if c+0x388 <= 0 or dead:  c+0x388 = 0;  slow = 0
   else:  e = frame − c+0xf0
          if e < 31:  slow = low byte of 2e;  if that byte, signed, is 61 or more:  slow = 60
          else:       slow = c+0x388 < 31 ? low byte of c+0x388 : 60
   lim = 60.0 − c+0x6c × 60.0;  if lim < f32(slow):  slow = int(lim)          lightning resistance
   ```
   `Creature_run` never decrements the counter. A start frame in the future gives a
   negative ramp value, which no reader treats as a slow amount.

### 4.8 Glow, burn, shock (0x113214)

- Glow `c+0x354 > 0`: `c+0x96 = 0x20`; `c+0x90, 0x94, 0x98, 0x9c = int(min(1.0, glow) × 128.0)`;
  `glow −= DT`.
- Burn `c+0x340 > 0`: when `net_objOrGhost(c) == c` and object flag 0x4000000 is clear:
  `fx_burnModel` (0x1f5210) with the model, `c+0x114`, the position, the facing, `c+0x320`
  and (burn, `c+0xdc`, `c+0xe0`, `f32(u8 c+0x28)`). Then `burn −= DT`. Then, unless the
  prediction copy, when `frame & 0x1f == 0`: one element record of id 0x15 and
  `damage_apply(c, c, 100000, 0, 0, 0x1180c040, record, 0; 0.0, 0.0)`. A monster's record
  is (min 1, max 1). A **player's** (object flag 0x40) is made from
  `n = skill(*0x41b1a4).slot 11 (0, int(g_levelMonsterLevel), 0)`, `b = f32(n) × 0x3e199999`,
  then **one shared draw** `d`: `min = int(b)`,
  `max = int(b + (b × 0x3e4ccccc) × (f32(d) × 2⁻¹⁶))`.
- Shock `c+0x348 > 0`: under the same two conditions `fx_shockModel` (0x1f61c0) with the
  colour 0x5e808080; `shock −= DT`; at or below 0 the words `c+0x33c`, `c+0x334`, `c+0x32c`
  are zeroed.

### 4.9 Damage over time (0x113818)

For (`c+0x34c` with `c+0x358`, `c+0x35a`) and then (`c+0x350` with `c+0x35c`, `c+0x35e`):
when the timer is above 0 it loses `DT`, and — unless the prediction copy — when
`frame & 0x1f == 0`: `damage_apply(c, c, 100000, 0, 0, 0x1080c040, 0, 0; f32(s16 lo) × 0x3dcccccc, f32(s16 hi) × 0x3dcccccc)`.

### 4.10 The boss meter (0x113960)

Only for cflag 1 (MiniBoss) with `c+0x231 == 0`:

```
shown = false
if cflags bit 63 and not dead and g_localAliveCount(0x4f8424) > 0:
    for each slot in g_localAlivePlayers(0x4f8430), in order:
        p = that slot's player object;  if none: continue
        if |p.pos − pos|² (3-D) < HomeRange(c+0x3c0)²:
            shown = true
            if not (cflags & 0x80000000):  cflags |= 0x80000000;  0x41b6a8 = 0x41b6a4 = 0x41b6a0 = 0
            else:  slot 19 (c, g_bossMeterName 0x41ba40);  0x41b6a4 = int(c+0x22c);  0x41b6a0 = int(c+0x228)
            break
if not shown and cflags & 0x80000000:  0x41b6a0 = 0x41b6a4 = 0;  cflags &= ~0x80000000
```

Bit 31 of the creature flags is object state written from two per-machine inputs: the
local alive list (FINDINGS E11) and, through bit 63, the activity test.

### 4.11 The corpse scavenger — `Creature_spawnScavenger` 0x1125e0 (called at 0x113ae4)

Does nothing unless all of: `state == 0x14`; animation flag 0x80 of `c+0x11a` (top clip
finished); cflags bit 63 set and bit 62 clear (active this tick, not the last); the ally
handle `c+0x238` empty or its object without cflag 0x40000000000; object flag 2 clear.
Then:

```
ONE SHARED DRAW;  turn = (s32 seed) >> 16                       signed
a = facing + turn;  spot = (pos.x + cos a × 30.0, pos.y + sin a × 30.0, pos.z)
f = atan2_16(pos.y − spot.y, pos.x − spot.x)
kind = g_corpseScavengerKind(0x402768):  1 or 2 →  b = pool_new(0x448);
       if b:  Critter_ctor(b, kind == 1 ? "raven" : "rat", spot, f, 0x402770 / 0x402780)
no block: done                                                  (the draw has been made all the same)
h = b.facing;  best = 0, bestT = 0.0
up to 32 times:  t = terrain_raycast(g_world, b.pos + (0, 0, 24), (cos h × 240, sin h × 240, 0x3e4ccccc × 240), 0; 1.0)
                 if t < 0 or 1.0 < t: t = 1.0;   if bestT < t: bestT = t, best = h
                 if bestT == 1.0: stop;   h = s16(h + 0x800)
b.facing = best;  handle_clear(c+0x238);  c+0x238 = 0;  handle_link(c+0x238, b, b)
```

### 4.12 Drawn height (0x113aec)

`v = c+0x40 + (pos.z − c+0x3c) × 3.0;  v = v − sqrt(0x3db851eb) × v;  c+0x40 = v;  c+0x3c += v × DT`
(the square root is taken at run time). Read by drawing.

### 4.13 Touched by a player (0x113b48)

In state 0 or 5 with a non-zero charm timer: if cflag bit 59 (set by slot 6 when a player
touches the creature) is set, slot 27 (c, 1); the bit is cleared either way.

### 4.14 Corpse deletion (0x113bc4)

cflag 0x1000000 set, bit 63 clear, `state == 0x14`: `flags |= 0x4002`, `obj_delete(c)`.

## 5. Status counters and timers: what reaches the simulation

| Field | Written by this code | Read by this code | Effect on simulation |
|---|---|---|---|
| counter 7 `c+0x388` | zeroed when ≤ 0 or dead (4.7) | every tick (0x113738) | the slow amount. **The value read is per machine**: `Creature_draw` decrements the first non-zero counter each time the creature is drawn (FINDINGS D12, D13). The ramp (first 30 frames from `c+0xf0`) does not depend on the value; afterwards any value above 30 gives 60, and from 30 down the counter itself is the slow amount |
| counters 0–6, 8–15 | never | never | none in the base class. (Counter 12 is read by the damage function, 2 and 4 by the player: FINDINGS D14.) Because drawing decrements only the first non-zero counter, a non-zero lower counter delays counter 7's decay on a machine that draws the creature |
| slow `c+0x2fc` | 4.7 | 4.6, 7.1, 7.2, the common ending 9.1 | scales the turn step, the animation speed, the root motion (twice), the move speed; removes the root yaw; stops the clock at 60 |
| root `c+0x314` | 4.4, `Creature_filterState` | `Creature_moveBy`, `Creature_filterState` | zeroes the velocity and root motion of a move; redirects set-state |
| no-target `c+0x316` | 4.4, slot 31 | slot 23 | no target while it runs |
| cooldown `c+0x318`, stun `c+0x31c` | 4.4, `Creature_filterState`, slot 30 | `Creature_filterState` | redirect set-state |
| spell speed `c+0x31a` | 4.4 | 7.2, 9.1 | with a `SpellDrowsy` attached: its fraction scales animation and move speed |
| charm `c+0x312`, team `c+0x310` | 4.5 | 4.5, 4.13, slots 20 / 37 | team; follow logic; death at expiry |
| burn, DoT timers | 4.8, 4.9, slot 2 (IgnoreDamage), death | 4.8, 4.9 | self-damage every 32nd frame, real object only |
| chill `c+0x344` | 4.7, slot 2, death | 4.7, 3.2, 3.4 | slow amount; ice hit effect; ice shatter |

## 6. Target selection — `Creature_pickTarget(c, force)` 0x10ded0 (slot 23)

```
if c+0x231 != 0:  return
if c+0x316 != 0 or cflags & 0x4000000:  handle_clear(c+0x234);  c+0x234 = 0;  return
if state != 0x14 and target exists and target is dead (flag 8):
    slot 27 (c, 0);  return                                     the handle is left to the set-state
best = (target exists and slot 20 (c, target) != 0) ? target : none
if staggered 32nd frame, or force != 0:                         the scan starts from nothing
    R = HomeRange(c+0x3c0)
    saved = g_excludeMask(0x4039b8);  g_excludeMask = 8
    list = world_collectObjectsInBox(pos − (R, R, R), pos + (R, R, R), capacity 0xc0)
    g_excludeMask = saved
    best = none;  bestScore = 0;  bestD = R × R
    for o in list, in order:
        score = slot 20 (c, o);  if 0: continue
        d = (pos.x − o.x)² + (pos.y − o.y)²
        if o is the object behind c+0x2e4 (last attacker):  score += 1
        if o is the current target:                         score += 1
        take = bestScore < score or (score == bestScore and d < bestD)
        if not take and force and a current target exists:  take = (o is not the current target)
        if best and force and o is the current target:      take = false
        if not take: continue
        if not (frame − 480 < c+0x304):                         not hit in the last 480 frames: the leash
            h = (home.x − o.x)² + (home.y − o.y)²
            if R × R < h and (pos.x − home.x)² + (pos.y − home.y)² < h
               and (o.radius + radius + 60.0)² < d:  continue
        best = o;  bestD = d;  bestScore = score
if best is none, or a target exists and is not best:  handle_clear(c+0x234);  c+0x234 = 0
if best and c+0x234 == 0:  handle_link(c+0x234, best, best)
```

What follows from it:

- **No draws** of any generator. The outcome depends on the order of the box query's list.
- The mask 8 excludes dead objects from the query for this one call and is restored at
  once (FINDINGS D13, `docs/creatures.md` C11); nothing else in the creature tick writes
  the mask.
- On a scan frame the current target is kept only if the query returns it and it wins;
  a target outside the ±HomeRange box, or beyond the 191 objects the list can hold, is
  dropped that frame.
- With equal scores the first candidate must already be nearer than HomeRange (2-D) to be
  taken, because `bestD` starts at HomeRange².
- `force` does more than "scan now": with a current target every other candidate is taken
  whatever its score, and the current target is refused once anything has been taken. A
  forced scan therefore ends on the **last** other enemy in list order that passes the
  leash, and keeps the current target only when it is alone.
- The leash refuses a candidate that is outside HomeRange of home, farther from home than
  the creature is, and more than `60 + both radii` away. It is off for 480 frames after any
  hit (`c+0x304`, stamped by slot 2).

Slot 20 (`Creature_isEnemy` 0x119328) is in 12.2.

## 7. Turning and the animation step

### 7.1 `Creature_turnToward(c, mode, point)` 0x10bb08 (slot 26)

```
limit  = int(c+0xb0 × 0x44888888)                               turn rate × 65536/60
target = atan2_16(point.y − pos.y, point.x − pos.x);  if mode == 1: target += 0x8000
d  = s16(target − facing)
av = u16 c+0x110 + int(f32(d) × 0x3d4ccccc)
av = av − int(sqrt(0x3e4ccccc) × f32(s16(av)))
c+0x110 = s16(av);  if limit < s16(av): c+0x110 = limit;  else if s16(av) < −limit: c+0x110 = −limit
facing += (1 <= slow <= 60) ? int(f32(s16 c+0x110) × slowK) : c+0x110
return d                                                        the angle BEFORE the turn
```

### 7.2 `Creature_stepAnim(c; speed)` 0x1162b0

```
if state == 3:  speed = speed × player_speedScale(−1)
if s16 c+0x31a > 0 and s = creature_findSpellByType(c, SpellDrowsy_typeinfo()):  speed = speed × SpellDrowsy_getStat3Fraction(s)
ev = 0
if cflags bit 63:
    if 1 <= slow <= 60:  speed = (speed × f32(60 − slow)) × DT
    ev = anim_advance(c+0x114, cflags & 0x2000000 ? 0 : &pos, &root(c+0xbc), &yaw(c+0xc4); speed)
root.xy = root.xy × c+0xdc
(cs, sn) = (cos, sin)(facing − 0x4000);  (rx, ry) = (−root.x, root.y)
root.x = rx × cs + ry × sn;   root.y = rx × sn − ry × cs
if 1 <= slow <= 60:  root.y = root.y × slowK;  root.x = root.x × slowK;  yaw = s16(yaw × int(slowK))
return ev
```

`int(slowK)` is 0 for every slow amount, so a slowed creature gets no root yaw (FINDINGS
AN1). An inactive creature's animation does not advance, but whatever is in `root` is
scaled and rotated again on every call.

## 8. The collision step — `Creature_moveBy(c, vel)` 0x113c48

```
if c+0x231 & 8:  return 0
old = pos
V = (vel.x + root.x × 60.0, vel.y + root.y × 60.0, vel.z);  facing += yaw
if c+0x314 != 0:  V = 0
c+0x308 = V.x;  c+0x30c = V.y;  root = 0;  yaw = 0
water()
d = V × DT;  bits = 0
if 0x3a83126e < d.x² + d.y²:  bits = world_slideMove(&pos, d, 3, &N; radius) ? 1 : 0;  obj_updateGridCell(c)
list = world_collectObjectsInBox(pos − (r, r, 1000), pos + (r, r, 1000), capacity 0x10)
top = pos.z + height;  stand = −100000.0
for o in list, in order:
    if o.flags & 1 or o is c:  continue
    D = pos.xy − o.xy;  dist = sqrt(D.x² + D.y²);  if not (dist + 0.001 < radius + o.radius):  continue
    if (o.flags | flags) & 0x10:
        if top < o.z + 3.0 or o.z + o.height < pos.z:  continue
        if (o.z + o.height) − pos.z < 5.0:
            if not (o.flags & 0x200) and not (flags & 0x400):
                stand = max(stand, o.z + o.height);  continue
            (else: touch without a push)
    if not (o.flags & 0x200) and not (flags & 0x401) and 0.001 < dist:
        k = ((radius + o.radius) − dist) / dist
        world_slideMove(&pos, (D.x × k, D.y × k, 0), 3, none; radius);  obj_updateGridCell(c)
    bits |= 2;  o.slot 6 (o, c);  touched += o
    if flags & 0x8000000 and o is the target:  break
g = terrain_heightBelow(g_world, pos; radius);  if g < stand: g = stand
c+0x30 −= 0x410fffff;  pos.z += c+0x30 × DT
if pos.z − 0x3c23d70a <= g:
    pos.z = g                                                   also while moving up
    if c+0x30 < 0:  c+0x30 = 0;  bits |= 4
if bits & 1:  slot 10 (c, N)
if bits & 2:  if flags & 0x8000000: pos = old, obj_updateGridCell(c);   slot 11 (c, touched)
return bits
```

`water()` (0x113d78): with cflag 0x100000 the in-water bit 61 is cleared and nothing else.
In water: `water_disturb(g_world, pos; 300.0, 12.0)` every tick — only on frames with
`frame & 0xf == 0` when the move speed `c+0xb8` is below 0x3c23d70a — and a zero result
clears bit 61. Not in water, on staggered 8th frames: `water_test(g_world, pos, 0; 12.0)`
non-zero → bit 61 set, **one own draw whose value is not used**, the splash sound (always
number 1; volume 0x3f199999) and `water_disturb(…; 1500.0, 24.0)`.

`Creature_settle(c)` 0x119e38 is `flags |= 0x8000000`, `Creature_moveBy(c, 0)`,
`flags &= ~0x8000000`: gravity and touches, but the old position is restored when
anything was touched, and the object loop stops at the target.

## 9. Moving somewhere

### 9.1 The common ending (0x114aa8, 0x1157dc, 0x115d90)

```
d = s16(slot 26 (c, 0, aim))
v = c+0xb8;  if Drowsy applies (7.2):  v = v × its fraction
if |d| >= 16001:  root.x = root.x × 0.5;  root.y = root.y × 0.5;  v = c+0xb8 × 0.5      the Drowsy factor is lost
if 1 <= slow <= 60:  v = v × slowK
Creature_moveBy(c, (cos F × v, sin F × v, 0))                   along the facing, not toward the aim
```

### 9.2 `Creature_moveTo(c, p)` 0x114510 → 1 on arrival, else 0

1. If the steering point `c+0x2ec` has x = y = 0.0 it becomes `p`.
2. Arrival: `|p − pos|² < radius²` (3-D) → 1. On staggered 8th frames, when
   `|p − pos|² < 2 radius²` and `|atan2_16(D.y, D.x) − facing| ≥ 0x4001` (the difference
   is **not** wrapped to 16 bits) → 1.
3. The aim:
   - `clock < c+0x2d8` (side-stepping): the steering point.
   - no current waypoint (`Creature_getWaypoint` x = −1.0): on staggered 64th frames, when
     `Creature_probeThreeMovementRays(c, p − pos, 0) < 1.0`: `Creature_advanceWaypoint`
     (which, without a waypoint, asks for a path). Then, with
     `|atan2_16(steer.y − pos.y, steer.x − pos.x) − facing| < 1000`: the steering point
     becomes `Creature_computeAvoidanceTarget(c, p)` on staggered 8th frames and `p` on the
     others; otherwise it becomes `p` only when `|pos − steer|² < |pos − p|²` (2-D). The aim
     is the steering point.
   - a current waypoint: if the probe toward `p` is 1.0 or more, `Creature_clearPath`,
     steering point = `p`, aim = `p`. Otherwise up to sixteen times: advance when the
     waypoint is within 24 units (`< 576.0`, squared, 2-D), or `c+0x2c0 < frame`, or the
     creature has passed it (`(next − wp) · (pos − wp) > 0`, with a next waypoint); each
     advance stores `c+0x2c0 = frame + 30` first; stop when nothing calls for an advance or
     the list runs out. The aim is the waypoint (x, y and z = −1.0), or `p` when the list
     has run out.
4. The common ending.
5. Stuck recovery (9.5).

### 9.3 Waypoints

Sixteen integer pairs at `c+0x23c`, index `c+0x2bc` (16 = none / search pending).

- `Creature_getWaypoint` 0x11a020 / `Creature_getNextWaypoint` 0x11a090: entry `index`
  (`index + 1`) as floats with z = −1.0, or all −1.0 when that index is 16 or more. The
  stored end marker −1 reads as x = −1.0 as well.
- `Creature_advanceWaypoint(c, &wp, dest, kind; radius, distance)` 0x11a108: sets
  `wp.x = wp.y = −1.0`; with `index < 16`: if the current entry is not the end marker the
  index goes up by one (stored even when it reaches 16), and a valid next entry is returned
  (result 1); in every other case `Creature_requestPath` and result 0.
- `Creature_requestPath(c, dest, kind; radius, distance)` 0x1164c0: kind 1 →
  `path_requestType2`, kind 2 → `path_requestType3`, else `path_requestType1` when
  `distance != 0.0`, else `path_requestToPoint`; arguments (`g_world`, position,
  destination, `c`, `c+0x23c`, 16) and the float (distance, or the radius for the last);
  then `index = 16`.
- Slot 7 (0x11a260), the search's answer: `index = 0`; found → failures `c+0x2c4 = 0`;
  not found → the first waypoint becomes the end marker and `c+0x2c4 += 1`.
- `Creature_clearPath` 0x11a1e0: first two waypoints = end marker, flee point x, y = −1.0,
  index 0, failures 0, progress record = position and clock, steering point = 0.

### 9.4 The other approach and retreat helpers

| Helper | Rule |
|---|---|
| `Creature_moveToTarget(c)` 0x1143e8 | no target: slot 27 (c, 0), result 0. Else `Creature_moveTo` to `target.pos + (cos b, sin b) × (target.radius + 5.0)`, `b = atan2_16(pos.y − target.y, pos.x − target.x)` (z = the target's) |
| `Creature_moveToDest(c)` 0x119f38 | `Creature_moveTo(c, c+0x104)`; on arrival slot 27 (c, 0). Result 1 — except, for a creature that is not a path follower and has 4 or more failed searches: `Creature_clearPath`, `dest = Creature_randomPointNearHome(300)`, result 0 |
| `Creature_moveToAlly(c)` 0x119e98 | `Creature_moveTo` to the ally's position (`c+0x238`); none: slot 27 (c, 0), result 0 |
| `Creature_moveToDirect(c, p)` 0x1155e0 | arrival as 9.2 step 2 but on the distance itself (`dist < radius`, `dist < 2 radius`). On staggered 32nd frames, unless inert: steering point = `Creature_computeAvoidanceOffset(c, 0; min(dist, radius + 10.0))`. Aim = `p`, or `pos + offset` when the offset's x **and** y are both non-zero. The common ending; result 0. No path, no stuck recovery |
| `Creature_fleeFrom(c, threat, kind)` 0x115910 | nothing without a threat. Flee point `c+0xf8`: unset (x = y = −1.0) or within one radius (2-D) → `Creature_randomPointNearHome(300)`; else, when `HomeRange² − 400.0 < |pos − home|²` (3-D) → home. On staggered 8th frames: steering point = `Creature_computeAvoidanceOffset(c, 0; radius + 10.0)`. With an offset (x and y non-zero) the aim is `pos + offset`. Otherwise waypoints as in 9.2, with these differences: "within reach" is `dist < radius`, there is no time-out, and the path is asked for with the **threat's position** as destination, kind 1 (2 when `kind ≠ 0`), distance 600.0; the aim is the waypoint, or the flee point when the list has run out, and **the aim is then stored as the flee point**. The common ending |
| `Creature_fleeFromTarget(c, kind)` 0x119f08 | `Creature_fleeFrom(c, target, kind)`; nothing without a target |

### 9.5 Stuck recovery (end of `Creature_moveTo`, 0x114bb8)

```
if g_cutsceneActive or 16.0 < (pos.x − c+0x2c8)² + (pos.y − c+0x2cc)²:
    c+0x2c8.. = pos;  c+0x2d4 = clock;  return 0                progress
if c+0x2d8 < clock and f32(c+0x2d4) < f32(clock) − 30.0:        30 ticks without progress, not side-stepping
    c+0x2d8 = clock + 30
    a = s16(facing − 0x8000);  ONE OWN DRAW:  odd → a += 0x2000, even → a −= 0x2000
    steer.xy = pos.xy + (cos a, sin a) × 1200.0;  return 0
if c+0x2d8 == clock and c+0x2d4 < c+0x2d8 − 300:                the tick a side-step ends, 300 ticks stuck
    world_findFreeSpot(&spot, pos, 72, int(radius), &found, 0)
    if found:  pos = spot;  obj_updateGridCell(c)
return 0
```

## 10. Probes and avoidance

All rays here are `world_raycast(g_world, origin, direction, c, &hit or 0, 3, flag; factor)`
(mask 3). A negative result is a miss.

- **`Creature_probeThreeMovementRays(c, D, hitOut)` 0x108fd8.** Up to three rays along `D`
  (factor 0x3f8ccccc, flag 1), 11 units up: from the position, then from one radius to the
  left (`facing + 0x4000`), then to the right. A ray with `0 ≤ t < 1` ends the probe with
  its `t`. Otherwise the result is the third ray's `t`, a miss counting as 1.0 — so the
  result can exceed 1. Every caller passes 0 for `hitOut`.
- **`Creature_computeAvoidanceTarget(c, p)` 0x109280.** `D = p − pos`,
  `t = probe(c, D)`. When `1.0 ≤ t`, or when not (`t × |D|² < (2 radius)²`): the point
  `pos + D × 1200.0` — **1200 times the vector**, not 1200 units. Otherwise two side rays of
  length 2 radius from `pos + (0, 0, 12)`: left (`facing + 0x4000`, factor 0x3f8ccccc), and,
  only if the left one is blocked (`0 ≤ tl < 1`), right (`facing − 0x4000`, factor 1.0).
  Heading: left open → `facing + 0x2000`; right open → `facing − 0x2000`; both blocked →
  `facing` when `tl² < t × |D|² < tr²`, else `facing + 0x2000` when `tr < tl`, else
  `facing − 0x2000`. The point is `pos.xy + (cos, sin)(heading) × 1200.0` with the
  creature's z.
- **`Creature_computeAvoidanceOffset(c, ignore; length)` 0x108a60.** Three forward rays
  (factor 1.0, flag 1, each reporting the object it hit), 13 units up, from the position
  and from one radius to the left and to the right; direction
  `(cos F × length, sin F × length, radius)` — the radius is the z component. A miss counts
  as 1.0.
  - None below 1.0: side byte `c+0x2f8 = 0`, offset 0.
  - A side already chosen (non-zero byte): kept.
  - Otherwise `m` = the smallest of the three, and two side rays of length `radius + 5.0`
    from the position (left, then right; z component the radius again):
    1. `ignore ≠ 0` and a forward ray both hit `ignore` and equals `m` → offset 0, the
       byte stays 0 (what is ahead is what the creature is walking to);
    2. the left side ray's object is `ignore` and `tsl < m` → side 2; the right one's and
       `tsr < m` → side 1 (with `ignore = 0` "its object is `ignore`" means it hit no
       object);
    3. right side ray below 1.0 → 2; left side ray below 1.0 → 1; else 1 when the right
       forward ray is clear, 2 when it is not.
  - Offset: side 1 → `(cos, sin)(facing − 12000) × radius`, doubled; side 2 → the same
    with `facing + 12000`; any other byte value → 0. So the offset is 2 radius long.
- **`creature_findClearHeading(c, pos, angle, dir; factor)` 0x10eaa8.** Up to 32 headings
  from `angle`, stepping `+0x800` when the low byte of `dir` is non-zero, else `−0x800`.
  Per heading, rays of length `factor × radius` (flag 0, no hit object), 13 units up, from
  `pos` and from one radius to each side of the heading; the score is the smallest clear
  fraction (a miss, or more than 1, counts as 1). A side ray is cast only while the score
  still beats the best so far. The first heading that beats the best replaces it; a best
  of exactly 1.0 ends the search. Result: the best heading (the starting angle if nothing
  scored above 0).

None of these draws anything.

## 11. Wander helpers

- **`Creature_isAwayFromHome(c)` 0x10eed8.** Path follower: `48² < |pos − home|²` in 2-D
  (0x45100000). Player follower (cflags 0xc00000): `120² < |pos − home|²` in 3-D
  (0x46610000). Anyone else: `(HomeRange × 0x3f2a7ef9)² < |pos − home|²` in 3-D.
- **`Creature_randomPointNearHome(c, reach)` 0x110b58.** `reach` is lowered to
  `int(HomeRange)` when HomeRange is smaller. Home itself is returned when
  `f32(reach²) ≤ |pos − home|²` (3-D), or for cflag 0x400000 more than 120 away. Otherwise
  up to ten tries, **two own draws each**:
  `x = home.x + f32((d1 & 2·reach) − reach)`, `y` likewise with `d2`, z = home's — a
  bitwise AND with `2·reach`, not a remainder, so the points lie on a sparse lattice (for
  reach 300: sixteen values per axis). A try is accepted when
  `pos.z − 12.0 < terrain_heightBelow(g_world, point; radius) < pos.z + 12.0`; after ten
  failures the tenth point is returned anyway.
- **`Creature_pickWanderDest(c)` 0x119618.** Nothing for a path follower, nor for a player
  follower that is away from home. Otherwise `dest = Creature_randomPointNearHome(120)` for
  a player follower, `(300)` for anyone else.

## 12. Default bodies of virtual slots

The model decides per call: when the table entry is the base body listed here it runs its
own method, otherwise the call is a subclass hook (a callback).

### 12.1 Slot 2 — `Creature_takeDamage(c, attacker, df; amount)` 0x116638

```
if c+0x231 != 0:  return
visualarc(c+0x3b0) = 0x7fff                                     also for IgnoreDamage
if cflags & 0x1000000000000:  c+0x340 … c+0x350 = 0;  return
c+0x304 = frame;  c+0x2dc |= df
if attacker and hp > 0:
    c+0x2e0 = 0x4000 − atan2_16(pos.x − attacker.x, pos.y − attacker.y)
    handle_clear(c+0x2e4)
    who = attacker
    if attacker.flags & 0x80:      n = attacker+0x4c;  if n: who = n→object       the owner of a projectile
    else if df & 0x10000000:       n = c+0x360;        if n: who = n→object       the source of the timed effect
    if who:  handle_link(c+0x2e4, who, who)                     0x116740
hp −= amount;  c+0xc8 += amount
```

The link is made to whatever pointer arrives; nothing tests that it is still an object
(FINDINGS ST3). The handle is rewritten only while hit points are above zero, so it names
whoever landed the killing blow; it is the "last attacker" of section 6 and the killer of
3.4.

### 12.2 Slot 20 — `Creature_isEnemy(c, o)` 0x119328 → 0, 1 or 4

0 for no object, for `c` itself, for an object without flag 0x20 or 0x40, for one with flag
8 or 0x20000, and for one with cflag 0x4000000 or 0x800. Otherwise slot 37 of `c` and
slot 37 of `o` (the team: base body 0x3c2730 returns the signed byte `+0x310`): equal → 0;
different → 4 when `o` has cflag 0x100000000000, else 1. The creature's **own** flags are
not looked at (its friendliness is tested by slot 23).

### 12.3 The small ones

| Slot | Body | What it does |
|---|---|---|
| 6 | 0x11a418 (c, toucher) | a player's touch sets cflag bit 59 |
| 7 | 0x11a260 | 9.3 |
| 10, 11 | 0x11a3f0, 0x11a448 | nothing (moved into terrain / touched objects) |
| 17 | 0x11a868 | 4.1 |
| 23, 26 | 0x10ded0, 0x10bb08 | sections 6, 7.1 |
| 27 | 0x3c2688 (c, state) | `c+0x232 = state` and nothing else: no filter, no timers, no handle |
| 30 | `Creature_stun` 0x118a58 (c, frames, flash) | nothing for `creature_bossRank(c) ≠ 0` or a corpse; else `c+0x31c = frames`, slot 27 (c, 0x13), and with `flash`: 0x3a, 0x9b, 0x9a into `c+0x90…0x94` and into `c+0x98…0x9c`, 0x48 into `c+0x96` |
| 31 | 0x118af8 (c, frames) | nothing in PvP mode A (0x4f711c) or for a boss rank; else `c+0x316 = frames`, target handle cleared |
| 35 | 0x118c50 | `int(g_levelMonsterLevel × 0x3e999999)` |
| 36 | 0x118c78 | `creature_bossRank(c)`: 1 → 4, 2 → 10, else 0 |
| 37 | 0x3c2730 | the team byte, signed |

`Creature_filterState(c, &state)` 0x10a9c0 is not a slot but what every derived slot 27
runs first; result 1 = refuse:

```
if g_pvpModeB(0x4f7120) and not g_pvpModeA and word 0x503890 and not word 0x503894:  return 1
if c+0x231 != 0 and state == 1:  return 1
if state == 0x14:  c+0x31c = c+0x318 = c+0x314 = c+0x31a = 0
if c+0x314 != 0 and state is not 0, 5 or 6..15:   state = target ? 5 : 0
else if c+0x31c != 0 and state != 0x13:           state = 0x13
else:  if no target:  c+0x318 = 0                               Creature_isAttackReady 0x1195f0 stores this
       if c+0x318 != 0 and state != 0x10:         state = 0x10
if state == 0:  handle_clear(c+0x234);  c+0x234 = 0
return 0
```

### 12.4 The weapon holder **[O]**

Not part of the base class's own code. In `Skelight_run` (0x2a8be0–0x2a8c48), between
`Creature_updateActive` and `Creature_stepAnim`: with `w = *(c+0x50)` non-null,
`i = w.slot 15 (w, 1)` (table at `w+0`); the model pointer is the word at
`g_itemModels 0x3e9ce0 + i × 16 + 8` (index 0 without a holder); then
`w.slot 22 (w, thatPointer, c; 0.5)`. The two bodies were not read; the model treats the
whole step as the subclass's business.

## 13. Draws of one tick, in order

Shared seed, made by this code itself:

| # | Where | Condition | Count |
|---|---|---|---|
| 1 | `Creature_run` burn tick, 0x1133f0–0x113440 (after the skill's slot 11, before `damage_apply`) | object flag 0x40 (a player), burning, not the prediction copy, `frame & 0x1f == 0` | 1 |
| 2 | `Creature_spawnScavenger` 0x1126b4–0x1126dc (before `pool_new`) | the conditions of 4.11 | 1 |

Shared seed, made by callees (callbacks of the model; their counts belong to their own
documents): `damage_apply` (burn and the two damage-over-time ticks, 4.8, 4.9),
`fx_shatterToLooseIce`, the constructors `GutChunk_ctor`, `OniBall_ctor`, `Critter_ctor`
(each object's own seed is drawn from the shared one in `GameObject_ctor`),
`world_findFreeSpot` (9.5), and whatever a set-state hook, `script_runByName` or
`player_giveExp` does. In tick order: section 3 callees, draw 1 and its `damage_apply`, the
two damage-over-time `damage_apply`, draw 2 and its `Critter_ctor`, then the movement
helper's `world_findFreeSpot`.

Own draws (`c+0x44`): metal sparks 3 per try × 50 (3.2); gib rolls (3.2); the reaction
(3.3: MiniBoss 1, cflag 0x400 1, 1); ice 1; death chunks 3 per chunk made; the skill-0x3b
roll 1 (3.4); entering water 1 (section 8); a side-step 1 (9.5);
`Creature_randomPointNearHome` 2 per try.

Third generator 0x404468 (per machine): 2 for the death decal and 3 per try for each of
three effect positions, only with `g_decalDetail > 0` (3.4).

## 14. Reads that are not lockstep state

| Read | Where | What it gates |
|---|---|---|
| `g_cullByCamera`, `g_cameraFocus`, the activity centres (D6) | `obj_updateActive` 0x14db28; `isNearView` 0x1e77c4 | cflags bits 63 / 62 and the run lists; the path follower's jump (C4) |
| cflags bit 63, written from the row above | 0x116324 `Creature_stepAnim`; 0x112f80 follower warp; 0x113980 boss meter; 0x11264c scavenger; 0x113bc8 corpse deletion | whether the animation advances (events, root motion); **whether a follower is moved next to its leader** (position, grid cell, path state, bit 63 itself); bit 31; one shared draw and a `Critter`; `obj_delete` |
| `g_localAliveCount`, `g_localAlivePlayers` (E11) | 0x11399c | cflags bit 31 and the three boss-meter words |
| status counter 7 as left by `Creature_draw` (D12) | 0x113738 | the slow amount, hence turning, animation, root motion, speed and the clock |
| `g_decalDetail` (C6) | 0x1113fc, 0x1116bc, 0x1116f8 | offline: blood effect and gibs. Net game: only decals and three effects, with the third generator |
| third generator 0x404468 | 0x11171c–0x111924 | decal angle and kind, effect positions |
| `net_objOrGhost(c)` (C7) | 0x113284, 0x113550 | burn and shock visuals only |
| the prediction-copy flag 0x20000 (C8) | 0x1132f8, 0x113834, 0x1138d8; slot 20 | timed damage and its shared draw skipped for the copy |
| `g_excludeMask` | saved, set to 8, restored at 0x10e014–0x10e060 | the list the target scan sees (C11); the value restored is the caller's |

Proposed ledger row (not yet on the ledger; `docs/creatures.md` lists
`Creature_run`'s follow logic without it):

| # | What | Kind | Addresses |
|---|---|---|---|
| new | The followPlayer warp in `Creature_run` runs only while creature flag bit 63 (active) is clear. That bit comes from `obj_updateActive`, which uses the camera focus while `g_cullByCamera` is set (D6). A charmed follower can therefore be moved to its leader, have its path cleared and be put on the every-frame run list on one machine and not on another during a cutscene in a net game: one more member of the D6 / D29 / D35 family, with a position write | Observed code, executed in isolation; reachability in a net-game cutscene Inferred | 0x112f7c–0x113130; 0x14db28 |

## 15. What the differential test covers

`python3 tools/difftest_creature.py` builds one creature, six other objects and four
players in the interpreter's memory and plays 1,500 ticks per run in the order of section
1, with the driver acting as the rest of the game (timers, counters, damage through slot
2, death and respawn, followers, path answers, activity and camera changes). There are
eight runs: monster / MiniBoss / object-flagged-as-player × base slots / subclass hooks ×
machine A / B × offline / net game. Machine A decrements the first non-zero status counter
every tick (a drawn creature), keeps the local alive list empty or far away, never uses the
camera for activity and has the decal option at 0; machine B is the opposite on all four.
Every original call is compared with the model on: the callbacks in order with arguments,
the set of bytes stored outside the stack with their final values, the shared seed and the
number of draws, and the result.

Result at seed 20973 (the default):

| Property | Result |
|---|---|
| calls, stores, seed, result, one-sided faults — each of the eight runs (40 lines) | PASS, 77,208 original calls compared, 0 mismatches |
| calls in which the original read unmapped memory | 4, all at 0x112b68 (4.3); the model faulted on the same calls |
| shared-seed draws seen | 625 in `Creature_run` (burning player, and the scavenger through it), 632 in direct `Creature_spawnScavenger` calls; none anywhere else |

Calls compared per entry point: avoidanceOffset 465, avoidanceTarget 462, clearPath 122, filterState 957, findClearHeading 438, findNearestOnTeam 452, fleeFrom 611, fleeFromTarget 623, isAwayFromHome 640, isEnemy 1,196, isNearView 439, moveBy 613, moveTo 1,060, moveToAlly 805, moveToDest 2,071, moveToDirect 874, moveToTarget 1,541, pickTarget 9,803, pickWanderDest 85, probeThreeRays 253, processDamage 12,000, randomPointNearHome 484, requestPath 228, run 12,000, settle 690, slot31 212, slot35 253, slot36 253, slot6 264, slot7 515, spawnScavenger 2,197, stepAnim 9,803, stun 228, takeDamage 1,656, turnToward 915, updateActive 12,000.

Coverage of the original as executed in that run (from the interpreter's trace; a block
starts at the function entry, at a branch target and after a conditional branch's delay
slot):

| Function | Basic blocks | Instructions |
|---|---|---|
| `Creature_run` | 191 of 198 | 1191 of 1216 |
| `Creature_processDamage` | 234 of 234 | 1501 of 1515 |
| `Creature_updateActive` | 15 of 15 | 81 of 81 |
| `obj_updateActive` | 18 of 18 | 111 of 112 |
| `isNearView` | 17 of 17 | 67 of 68 |
| `Creature_takeDamage` | 15 of 15 | 82 of 82 |
| `Creature_pickTarget` | 52 of 52 | 250 of 251 |
| `Creature_isEnemy` | 11 of 11 | 53 of 53 |
| `Creature_turnToward` | 7 of 7 | 102 of 103 |
| `Creature_stepAnim` | 14 of 14 | 129 of 131 |
| `Creature_moveBy` | 55 of 56 | 482 of 488 |
| `Creature_moveTo` | 62 of 63 | 542 of 547 |
| `Creature_moveToDirect` | 23 of 23 | 203 of 204 |
| `Creature_fleeFrom` | 39 of 39 | 361 of 361 |
| `Creature_computeAvoidanceOffset` | 42 of 42 | 348 of 350 |
| `Creature_computeAvoidanceTarget` | 18 of 18 | 348 of 350 |
| `Creature_probeThreeMovementRays` | 10 of 10 | 170 of 170 |
| `creature_findClearHeading` | 18 of 18 | 268 of 268 |
| `Creature_randomPointNearHome` | 11 of 11 | 117 of 118 |
| `Creature_spawnScavenger` | 29 of 29 | 217 of 218 |
| `Creature_filterState` | 27 of 27 | 83 of 85 |
| the 20 small ones (`Creature_moveToTarget`, `Creature_moveToDest`, `Creature_settle`, `Creature_isAwayFromHome`, `Creature_getWaypoint`, `Creature_getNextWaypoint`, `Creature_advanceWaypoint`, `Creature_clearPath`, `Creature_slot7`, `Creature_requestPath`, `Creature_updateSpells`, `players_findNearestOnTeam`, `Creature_pickWanderDest`, `Creature_slot6`, `Creature_stun`, `Creature_slot31`, `Creature_slot35`, `Creature_slot36`, `Creature_fleeFromTarget`, `Creature_moveToAlly`) | 95 of 95 | 773 of 776 |
| **all 41** | **1003 of 1012 (99.1%)** | **7479 of 7547 (99.1%)** |

`Creature_moveBy`'s one missing block (0x11418c, a second object to stand on that is not
higher than the first) is entered with `--seed 777 --ticks 3000`, a run of 154,700 calls
that also passes; the other eight missing blocks are unreachable (below).

Floating point: every float is compared as a bit pattern under the interpreter's default
FPU model, and the whole run was repeated under its three other adder models (`--fpu
ps2g1`, `chop`, `nearest`, 600 ticks per run) with the same outcome. That shows the same
operations in the same order, not that a console produces the same last bit
(`docs/issues/dynamic-tests.md`). `powf` and `atan2f` run for real on the interpreter side
and through `tools/ref_core.py` on the model side.

Blocks never entered, and why:

- `Creature_run` 0x11347c, 0x113484, 0x113498, 0x1134a8 and 0x1134dc, 0x1134e4, 0x1134f8:
  the search for a free slot in the burn element record. The record is filled with −1 a
  few instructions earlier, so the first slot always matches; these are dead.
- `Creature_moveTo` 0x114a60: leaving the waypoint loop after sixteen successful advances.
  A sixteen-entry list allows at most fifteen, so this is dead too.

What stays scripted: everything in `EXTERNALS` of the model — animation, the damage
function, world rays, the box query, the slide, ground height, paths, effects, object
construction, handle lists, scripts, and (in the "hooks" runs) slots 2, 6, 7, 10, 11, 17,
20, 26, 27, 37. Their answers are random within plausible ranges, so combinations a real
callee cannot produce are tested and combinations only a real callee produces may be
missed. In particular the order of the box query's list is the script's, not a real
grid's.

The original read through a null pointer on a few calls (4.3, 0x112b68) when the script's
`pointList_getPoint` returned no next point; the model faults at the same place. On a
console address 0 is readable, so there the creature's destination would be filled from
low memory. Whether a path can end without a next point for a creature within 48 units of
its last point was not established (Unknown).

## 16. Where earlier documents turned out wrong or short when executed

1. `docs/monsters.md` 1.3, step 3: "a non-zero result [of `Creature_run`] ends the
   function". The caller does test it, but `Creature_run` returns 0 on every path
   (0x113c10).
2. `docs/creatures.md`, "How the pieces fit": the order given (`Creature_updateActive`,
   then `Creature_run`, `Creature_processDamage`) is not the order in the class read here;
   `docs/monsters.md` 1.3 has it right.
3. `docs/creatures.md`, slot 23 and the helper catalogue: "keeps the current target while
   it is alive and still an enemy … or when forced: box query". Executed: a scan starts
   from nothing and drops a target the query does not return; `force` with a current target
   takes any other candidate whatever its score (section 6). A dead target leads to
   set-state 0 and no clearing of the handle in the base class.
4. `docs/creatures.md`, "Pending damage": the knock-back speeds 100 / 150 / 200 / 312.5
   are the death table only; a surviving hit uses 100 / 150 / 225 / 375 and a tick without
   pending damage 50 / 75 / 100 / 156.25. Not stated there: a corpse's pending amount is
   cleared but its flags are kept; the burn test in the death branch is dead code.
5. `docs/creatures.md`, flag table and status section: the followPlayer bits act only
   while the charm timer is non-zero (4.5); "second timers −1/60 per `Creature_run`" does
   not hold for chill, which loses 1/15 per tick (and 1/30 more on a player).
6. `docs/creatures.md` C3 / FINDINGS E11: the boss-meter block also needs the active bit
   63, so it has two per-machine inputs.
7. `docs/spec/movement-camera.md` 6.3, `Creature_moveToDirect`: "a non-zero offset replaces
   the aim point". Executed: only when the offset's x and y are both non-zero; and the ray
   length is `min(distance, radius + 10)`.
8. `docs/spec/movement-camera.md` 6.4: `Creature_computeAvoidanceTarget` does not return "a
   point 1200 units along the straight line" but `pos + (p − pos) × 1200`; "more than two
   radii away" is the test `t × |D|² < (2 radius)²` with `t` unsquared. The side-selection
   rule and length of `Creature_computeAvoidanceOffset`, marked Unknown there, are in
   section 10 (the length is 2 radius).
9. `docs/spec/movement-camera.md` 6.3, `Creature_fleeFrom`: not stated there that the aim
   is written back as the flee point and that the avoidance offset is refreshed every 8th
   frame.
10. `docs/spec/movement-camera.md` 6.4 step 6: the last-resort teleport can happen only on
    the tick the clock equals the side-step deadline.
11. `docs/monsters.md` 1.3: `Creature_isAttackReady` 0x1195f0 is described as a test. It
    also zeroes the cooldown `c+0x318` of a creature without a target.
12. `docs/monsters.md` 1.4, `Creature_filterState`: the root redirect applies to requests
    other than 0, 5 and 6–15, gives 5 only with a target (0 without), and skips the stun
    and cooldown tests.
13. The brief for this work located slot 2 at 0x116740; that is the `handle_link` call
    inside `Creature_takeDamage` 0x116638 (FINDINGS ST3 cites the call site).

## 17. Notes for tools

`tools/ee_emu.py` was not changed. Besides the three gaps already known (no catch-all stub
hook, stub results not sign-extended, stack arguments not recorded) the test works around
a fourth: an unaligned `sdl` / `sdr` / `swl` / `swr` is logged as a store of the whole
aligned word, so the write log names bytes the instruction did not touch. The test hooks
those instructions in the functions under test and records their real effective address.

## 18. Not done

- `Creature_applyKnockback` 0x115eb8, `Creature_deadUpdate` 0x1108a0, `Creature_dropLoot`
  0x10f2c8, slot 28 (on death), slot 32 (revive), slot 24 / 21 (ally pick), slot 25 and the
  cone searches, the attack helpers 0x1196e8–0x119d10, `creature_bossRank` 0x10d940 (a
  callback: it compares the object's name with names in the executable).
- `Creature_setStats` and the damage function are modelled by `tools/ref_combat.py`,
  `anim_advance` by `tools/ref_anim.py`, the world queries by `tools/ref_world.py`; this
  model calls them as callbacks and does not wire the models together.
- The weapon-holder slots (12.4) and each class's own run and set-state.
- Nothing was run on a console; no net-game cutscene was recorded for the proposed row of
  section 14.
