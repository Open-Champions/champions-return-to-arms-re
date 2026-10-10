# Level queries — implementation specification

What the simulation asks of a level: how high the floor is, whether a place is blocked, how
far a circle can move, where a ray stops, and how to walk from one place to another. Every
movement, projectile and AI decision goes through these few functions, and in a net game
every machine must get the same bits out of them.

- `tools/ref_world.py` — the reference model (Python, raw float patterns).
- `tools/difftest_world.py` — runs the original functions of `SLUS_209.73` under
  `tools/ee_emu.py` on real level files and compares with the model.
- `docs/formats/world.md` — the file; `docs/spec/movement-camera.md` section 5 — the callers.

Every query in sections 3–10 was executed and compared; section 11 says on what, section 12
what earlier documents had wrong, section 13 proposes ledger rows and names, section 14 says
what was not done.

## 0. How this was established

Marks: **[X]** *executed in isolation* — the game's own instructions were run by the
interpreter on a real level and the model reproduces every output bit for the inputs listed
in section 11; **[O]** Observed — read at the address given, not run; **[I]** Inferred;
**[U]** Unknown. A statement without a mark in sections 3–10 is [X].

"Bit for bit" always means: under the interpreter's floating-point model
(`docs/issues/dynamic-tests.md`, "Floating point"). The comparison is repeated under all four
adder models and both rounding switches of the interpreter; agreement there shows the same
operations in the same order, not that a console produces the same last bit. Nothing here
was seen on a console or a console emulator.

## 1. Conventions

- A float is IEEE single precision as the R5900 does it: no NaN, infinity or denormal,
  results truncated toward zero, a division by zero gives ±0x7fffffff (the largest value).
- In pseudo-code every `+ − × /` is one single-precision operation, evaluated in the order
  written, parentheses first. `f32(i)` is integer → float, `int(x)` float → integer
  (truncation toward zero, saturating), `floorf`/`ceilf` are the C library routines
  0x3a57e8 / 0x3a5710 (they work on the bits and round to an integral float exactly).
  `min(a, b)` and `max(a, b)` are the hardware instructions: `a` unless `b` is smaller
  (larger).
- Constants are given as bit patterns where the decimal would mislead:

| Name | Pattern | Value |
|---|---|---|
| `Q` | 0x3e800000 | 0.25, world units → sample units |
| `K160` | 0x3bcccccc | 1/160 truncated, world units → terrain grid cells |
| `KROT` | 0x38000100 | s16 cosine/sine → float: 1/32767 truncated, so 32767 × `KROT` is below 1 |
| `K24` | 0x3d2aaaaa | 1/24 truncated, world units → path nodes |
| `K240` | 0x3b888888 | 1/240 truncated |
| 0.01 | 0x3c23d70a | |
| 0.001 | 0x3a83126e | truncated |
| 0.1 | 0x3dcccccc | truncated |
| 0.98 | 0x3f7ae147 | |
| `DT` | 0x3c888888 | frame time, 1/60 truncated |
| gravity step | 0x410fffff | 8.999999 per frame |

- A sample is an s16: `height = sample >> 4` (arithmetic), `flags = sample & 15`.
- Positions are (x, y, z) floats, z up. Sample units are world units × 0.25.

## 2. The level as the queries see it

After `world_fixup` 0x181d30 the offsets of the file are pointers and one thing has changed
in the data: for every moving piece (door, lift), in file order, the height field of its
terrain element is rewritten (0x181e2c–0x181ec0) — each sample with flag bit 0 becomes
`(sample & 15) + 0x7d00` (height 2000, flags kept), and the field's maximum (+0x12) becomes
2000. The field is shared, so every element that uses it sees the change.

Run-time state that the queries read or write:

| State | Where | Written by |
|---|---|---|
| visit stamp of each terrain element (+0x08) and the counter `g_terrainStamp` 0x44f08c | element; global | every height, flag, sweep and ray query |
| element flag 2 "ignored" (+0x10) | element | `world_setPieceCollision` 0x182b00: on → cleared, off → set; cleared for every piece by the level-restart routine 0x18b270 [O] |
| element height offset z (+0x1c) | element | `world_setPieceHeight` 0x182bb4: `z = int(height)` |
| path node bits 8–15 (search mark) | path grid | `path_service`, `path_search` |
| path node bits 16–31 (block counter) | path grid | 0x18b6c0 (+1, at most 16), 0x18b584 (−1, not below 0) |
| the search state (section 10.5) | globals | `path_service`, `path_search` |

## 3. Collecting terrain elements — `terrain_collectElements` 0x183248

`collect(minX, minY, maxX, maxY, limit)`:

```
col0 = int(floorf(minX × K160)) − gridOriginX      row0 = int(floorf(minY × K160)) − gridOriginY
col1 = int(floorf(maxX × K160)) − gridOriginX      row1 = int(floorf(maxY × K160)) − gridOriginY
row0 = max(row0, 0);  row1 = min(row1, gridH − 1);  col1 = min(col1, gridW − 1);  col0 = max(col0, 0)
for row = row0 .. row1:                              rows (y) outer
  for col = col0 .. col1:
    for each element index in the cell's list, in file order:
        skip if element.stamp == g_terrainStamp
        skip if element.flags & 2
        skip if maxX < f32(e.minX) or maxY < f32(e.minY) or f32(e.maxX) < minX or f32(e.maxY) < minY
        element.stamp = g_terrainStamp;  append
        if the list now holds limit − 1 elements: stop everything
```

The **caller** adds 1 to `g_terrainStamp` before the call. The height and flag queries pass
limit 64 (63 elements), the sweep and the ray 256 (255). The ray advances the stamp once and
then collects several times, so an element is handed to it only once per ray.

## 4. Floor height

### 4.1 The local position of a point in an element

Used by every query below, always with these operations in this order:

```
c = f32(e.cos) × KROT;   s = f32(e.sin) × KROT
ux = P.x − f32(e.x);     uy = P.y − f32(e.y)
mirrored (e.flags & 1):  ly = ux×s − uy×c;        lx = ux×c + uy×s
otherwise:               lx = ux×c + uy×s;        ly = (−ux)×s + uy×c
lx = lx × Q;  ly = ly × Q                          sample units
```

Sample (i, j) of the element is array entry `(j − hf.y0) × hf.w + (i − hf.x0)` when both
differences are inside the field; it sits at local position (i, j).

**A trap.** For an element that is not rotated the file holds cos = 32767, and
`f32(32767) × KROT` is 1 − 2⁻³⁰, which the truncating multiplier turns into 0x3f7fffff
(0.99999994), not 1.0. So a point exactly 12 units from the element's origin is at
2.9999998 samples and `floorf` gives 2, and a ray marched through such an element advances
0.99999994 samples per step and enters sample 10 on its 11th step. Do not special-case
unrotated elements, and do not let the multiply round to nearest: with rounding the product
is exactly 1.0 and other samples are chosen (section 13, proposed row W1).

### 4.2 `terrain_height(r, P)` 0x183820 and `terrain_heightBelow(r, P)` 0x1834a8

```
g_terrainStamp += 1
list = collect(P.x − r, P.y − r, P.x + r, P.y + r, 64)
r4 = r × Q;   reach = int(ceilf(r4));   r4sq = r4 × r4
best = −1000000                                              integer
for each element e in list order:
    top = hf.max(+0x12) + e.z
    if not (best < top): next element
    [heightBelow only]  if (P.z + 12.0) < f32(hf.min(+0x10) + e.z): next element
    (lx, ly) as in 4.1;   i0 = int(floorf(lx));   j0 = int(floorf(ly))
    for j = j0 − reach .. j0 + reach + 1:                    rows outer
      for i = i0 − reach .. i0 + reach + 1:
        skip samples outside the field
        h = (sample >> 4) + e.z                              integer
        if not (best < h): continue
        [heightBelow only]  if (P.z + 12.0) < f32(h): continue
        a = f32(i) − lx;   b = f32(j) − ly
        if not ((a×a + b×b) < r4sq): continue                strictly inside the disc
        best = h
        if not (best < top): next element                    the element's maximum is reached
return f32(best)
```

- The result is the **highest sample height under the disc**, with no interpolation; flags
  are not looked at; "no floor" samples (height −2000) are ordinary low samples.
- Nothing under the disc gives f32(−1000000) = 0xc9742400.
- A radius of 0 gives −1000000 everywhere (`r4sq` is 0 and the test is strict).
- The two early exits use the field's stored maximum. In a field whose +0x12 is lower than
  its real highest sample the answer can be lower than the real maximum, and it then
  depends on the scan order; the generated level of the test has such fields.
- `terrain_heightBelow` ignores what is more than 12 above `P.z` (both tests are float
  compares against `P.z + 12.0`), so a mover under a bridge stays under it.

### 4.3 `terrain_heightAtPoint(P)` 0x182f28

Only the terrain cell that contains the point: `col = int(floorf(P.x × K160)) − originX`,
likewise `row`; off the grid → 0.0. Of that cell's elements, those with flag 2 clear and
`f32(minX) ≤ P.x ≤ f32(maxX)`, `f32(minY) ≤ P.y ≤ f32(maxY)`: the one sample at
`(int(floorf(lx)), int(floorf(ly)))`, if inside the field. Result: the highest of these as a
float, or **0.0** when there is none or the best is below −100000. No stamp is used.

## 5. The blocked test — `terrain_testFlag1(r, P)` 0x183b48

The same walk as `terrain_height` (stamp, collect 64, `reach`, strict disc test), without
heights: returns **1.0** as soon as a sample inside the disc has flag bit 0, else **0.0**.
The result is a float in `$f0`; its two callers (`world_findFreeSpot` 0x14aee4,
0x20e07c) compare it with a float.

Who is stopped by which sample flag:

| Mask | Passed by | Stopped by |
|---|---|---|
| 1 | non-creature objects in `obj_moveWithCollision` 0x14d4b8; every push-out slide (0x14d8a0); `Prop_run`, `PhProp_run`, `PushPhysicsProp_run`, 0x15ea8c (direct sweeps); `Vehicle_collideObjects` | flag 1 |
| 3 | `Creature_moveBy` 0x113c48 (both slides): monsters, knocked-back players | flags 1, 2 |
| 5 | a player's own step in `obj_moveWithCollision` (object flag 0x40: `(mask | 4) & 5`) | flags 1, 4 |
| ray flags 3 | 12 of the 28 `terrain_raycast` call sites and 19 of the 26 `world_raycast` call sites (the creature movement probes in 0x108b00–0x119600, 0x27b308, 0x2b9f20) | flags 1, 2 raise the sample by 65536 × flag |
| ray flags 0 | 15 `terrain_raycast` and 7 `world_raycast` call sites, among them the three path goal tests; one site passes its caller's value | heights only |

[O] for the call sites: the constant loaded nearest before each call, found by a scan, not by
tracing each caller. No sample in the 119 shipped levels has flag 4 or 8; 37 samples in each
of 9 levels have flag 2 (counted with `tools/world_info.py`).

Projectiles do not use flags at all: `obj_moveAndCollide` compares `terrain_height` with the
projectile's z (section 8.3).

## 6. The swept circle — `terrain_sweepCircle(r, P, S, mask, N)` 0x185a40

A circle of radius `r` at `P` tries to move by `S`. Returns the fraction of `S` it can go
and, when blocked and `N` is wanted, the contact normal.

```
g_terrainStamp += 1
E.x = P.x + S.x;   E.y = P.y + S.y
list = collect(min(P.x, E.x) − r, min(P.y, E.y) − r, max(P.x, E.x) + r, max(P.y, E.y) + r, 256)
sx = S.x × Q;   r4 = r × Q;   r4sq = r4 × r4;   sy = S.y × Q
len  = sqrt(sx×sx + sy×sy)
inv  = 1.0 / len
dir  = (sx × inv, sy × inv);   dz = S.z × inv                S.z is not scaled by Q
reach = int(ceilf(r4))
base  = int(floorf(min(P.z, P.z + S.z))) + 12                 integer
best  = len
for each element e in list order:
    if (e.flags & 4) == 0 and hf.max + e.z < base: next element
    (lx, ly) as in 4.1
    mirrored:   dlx = dir.x×c + dir.y×s;   dly = dir.x×s − dir.y×c
    otherwise:  dlx = dir.x×c + dir.y×s;   dly = (−dir.x)×s + dir.y×c
    i0 = int(floorf(lx));               j0 = int(floorf(ly))
    i1 = int(floorf(lx + dlx × len));   j1 = int(floorf(ly + dly × len))
    for j = min(j0, j1) − reach .. max(j0, j1) + reach + 1:   rows outer
      for i = min(i0, i1) − reach .. max(i0, i1) + reach + 1:
        skip samples outside the field
        h = 32000 if (sample & mask) != 0 else (sample >> 4) + e.z
        if h < base: continue
        a = f32(i) − lx;   b = f32(j) − ly
        perp = a×dly − b×dlx
        if (r4 + 0.01) < |perp|: continue
        along = a×dlx + b×dly
        if along < 0: continue
        if f32(h) < ((P.z + along×dz) + 12.0): continue
        q = r4sq − perp×perp
        t = along − sqrt(q)  if 0 < q  else  along − 0.0
        if not (t < best): continue                           ties keep the first sample
        best = t
        X = f32(i × 4);   Y = f32(j × 4)
        mirrored:   hit = ((X×c + Y×s) + f32(e.x),  (X×s − Y×c) + f32(e.y))
        otherwise:  hit = ((X×c − Y×s) + f32(e.x),  (X×s + Y×c) + f32(e.y))
if len ≤ best: return 1.0                                     N is not written
if N wanted:
    n = ((P.x + dir.x×best) − hit.x,  (P.y + dir.y×best) − hit.y)
    k = 1.0 / sqrt(n.x×n.x + n.y×n.y)                         the reciprocal-square-root instruction
    N = (n.x × k, n.y × k, 0.0)
return best × inv
```

Confirmed by execution, and easy to get wrong:

- **Time of impact** is `best × inv` with both in sample units; it is exactly 1.0 (the
  constant) when nothing blocks.
- **The normal is taken a quarter of the way.** The centre used is `P + dir × best` with
  `best` in sample units, i.e. after a quarter of the distance travelled. 0x186088–0x1860c4.
- **Step-up rule.** A sample blocks when one of its flags is in `mask`, or when its ground
  is 12 or more above the mover: once in integers against `floor` of the lower end of the
  step, once in floats against the height the mover would have at that point of the step.
  Lower samples never block.
- **Negative times.** A circle that already overlaps a blocking sample gets `t < 0` (it is
  pushed back along its direction). See the hazard in section 7.
- **A zero-length step** (`S.x = S.y = 0`): `len` is 0, `inv` is 0x7fffffff, `dir` is (0, 0),
  so `perp` and `along` are 0 for every sample. The result is 1.0 unless some blocking
  sample lies in the scanned square around the centre (`reach` samples each way and one
  more on the high side — inside the circle or not); then `best` is −`r4` and `best × inv`
  is −0x7fffffff.
- An element is skipped by height only when its flag 4 is clear; flag 4 does not otherwise
  change anything. An element with flagged samples and flag 4 clear (none in the shipped
  levels) is skipped when it is low, flags or not.

## 7. The slide — `world_slideMove(r, pos, delta, mask, normalOut)` 0x14d238

```
D = delta;  P = pos;  remain = 1.0;  hit = 0
repeat at most 11 times:
    step = (D.x × remain, D.y × remain, D.z × remain)
    t = terrain_sweepCircle(r, P, step, mask, &N)
    remain = remain − t
    P = (P.x + step.x×t,  P.y + step.y×t,  P.z + step.z×t)
    if not (0.001 < remain): stop
    hit = 1
    k = 0.001 − ((N.x×D.x + N.y×D.y) + N.z×D.z)
    if 0 < k:  D = (D.x + N.x×k,  D.y + N.y×k,  D.z + N.z×k)
pos = P;  normalOut = N if wanted;  return hit
```

`N` keeps the value of the last blocked sweep. When no sweep was blocked the function copies
an uninitialised stack slot to `normalOut` [O]. `Creature_moveBy` uses the normal only when
the slide reported a hit (`docs/spec/movement-camera.md` 5.6); the other callers were not
checked for this.

**Hazard [X for the arithmetic, I for the consequence].** `remain − t` grows when `t` is
negative, and the next step is `D × remain`. A mover that starts inside blocking samples can
therefore take steps many times longer than `delta` (156 times in one generated case). With
a zero-length horizontal step and a blocking sample in the scanned square (section 6 — for a
radius of 12 that is any flagged or 12-high sample within 12 to 16 units, i.e. any wall the
mover stands next to), `t` is −0x7fffffff, `remain` becomes 0x7fffffff, the delta picks up
`N × 0.001` and the following step is of the order of 10^35 units: the sweep then walks the
whole 32-bit range of sample indices in every element it collected, one comparison at a
time, which on a console is a hang. (The model, whose loops are cut down to the field,
finishes and puts the mover some 10^36 units away.)

`obj_moveWithCollision` reaches this with a velocity that is purely vertical and above
about 1.9 units/s (its threshold uses all three components); `Creature_moveBy` cannot (two
components). Executed once in the original: a player-flagged stand-in on the floor of a real
level, 12 units in radius, with a flag-1 sample within 14 units and velocity (0, 0, −3) —
the second call of `terrain_sweepCircle` was asked for a step of (−4.8 × 10^35,
4.8 × 10^35, −3.4 × 10^37) and the run was stopped there. Since the shipped game does not hang beside walls, its callers evidently never
pass such a velocity — vertical motion goes through the object's own vertical speed
(section 8.1) [I]. A rebuild must either keep that property or guard the case; nothing in
the function does.

## 8. Movers

### 8.1 Ground step — the end of `obj_moveWithCollision`, 0x14da20–0x14dac4

```
ground = terrain_heightBelow(r, pos);   if ground < stand: ground = stand      stand = −100000.0 with no object underfoot
vz = vz − 8.999999
z  = pos.z + vz × DT
if (z − 0.01) ≤ ground:
    z = ground
    if vz < 0:  vz = 0;  landed (result bit 4)
```

So a floor up to 12 above the feet is stepped onto in one frame, and anything further below
than gravity carries the mover this frame leaves it falling.

### 8.2 `obj_moveWithCollision` with no other object near — 0x14d4b8

```
d = (vel.x × DT, vel.y × DT, vel.z × DT)
if 0.001 < ((d.x×d.x + d.y×d.y) + d.z×d.z):
    mask = 1;  3 for a creature (object flag 0x20);  (mask | 4) & 5 for a player (flag 0x40)
    bits = world_slideMove(r, pos, d, mask, none) ? 1 : 0
ground step (8.1);  bits |= 4 when landed
```

The object loop between the two (push-out, touch calls, standing on objects) is specified in
`docs/spec/movement-camera.md` 5.5 and is not part of this model.

### 8.3 Projectiles — the terrain part of `obj_moveAndCollide`, 0x1509f8–0x150bc8

```
d = vel × DT;   pos = pos + d                               no sweep
if pos.z < terrain_height(r, pos):                          in the ground: result bit 1
    k = 0.1
    repeat:
        try = pos − d × k
        if terrain_height(r, try) ≤ try.z: stop
        k = k + 0.1
    while k < 2.0
    pos = try                                               also when no try was clear
```

With the truncated 0.1 the loop makes at most 20 tries (k = 0.1 … 1.9999989).

## 9. Rays

### 9.1 `terrain_raycast(maxT, O, D, flags)` 0x18a5c0

Returns the parameter `t` of the first hit, `O + D × t`, or −1.0.

```
dx = D.x × Q;  dy = D.y × Q;  len = sqrt(dx×dx + dy×dy)
if len < 0.01:                                              vertical
    if not (D.z < 0): return −1.0
    return O.z − terrain_heightAtPoint(O)                   a distance, not a parameter
limit = maxT × len;   inv = 1.0 / len
g_terrainStamp += 1                                         once for the whole ray
dx = dx × inv;  dy = dy × inv;  dz = D.z × inv              unit direction; rise per sample step
if not (0 < limit): return −1.0
marched = 0.0
repeat at most 1001 times:
    E = (O.x + dx×240.0,  O.y + dy×240.0,  O.z + dz×240.0)
    list = collect(min(O.x, E.x), min(O.y, E.y), max(O.x, E.x), max(O.y, E.y), 256)
    best = 1e11;   low = −1e7 if dz < 0 else O.z
    for each element e:
        unless (flags != 0 and e.flags & 4):  if f32(hf.max + e.z) < low: next element
        (lx, ly) as in 4.1 from O;   z = O.z − f32(e.z)
        (dlx, dly) as in section 6 from (dx, dy)
        t = 0
        clip to the field, one side after the other, in this order:
            lx < f32(x0):          if dlx ≤ 0.01: next element;   k = (f32(x0) − lx) / dlx
            f32(x0 + w) < lx:      if −0.01 ≤ dlx: next element;  k = (f32(x0 + w) − lx) / dlx
            ly < f32(y0):          if dly ≤ 0.01: next element;   k = (f32(y0) − ly) / dly
            f32(y0 + h) < ly:      if −0.01 ≤ dly: next element;  k = (f32(y0 + h) − ly) / dly
          each time:  t = t + k;  lx = lx + dlx×k;  ly = ly + dly×k;  z = z + dz×k
        col = int(lx) − x0;   row = int(ly) − y0             truncation, not floor
        outside = 0
        for step = 1 .. 1001:
            if (col, row) is outside the field:
                if outside ≥ 4: next element
                outside += 1
            else:
                height = (sample >> 4) + 65536 × (sample & flags)
                if z < f32(height):  best = min(best, t);  next element
            t = t + 1.0;  lx = lx + dlx;  ly = ly + dly;  z = z + dz
            col = int(lx) − x0;   row = int(ly) − y0
    if best < 1e10:
        total = best + marched × Q
        return total × inv if total < limit else −1.0
    marched = marched + 240.0;   O = E
    if not (marched × Q < limit): return −1.0
return −1.0
```

Things a re-implementation would not guess:

- The march is per element, one sample per step, up to 1001 steps from the start of the
  240-unit segment in which the element was first collected. The first segment in which any
  element is hit decides, with the smallest `t` among that segment's elements — not
  necessarily the nearest hit along the ray.
- `E.z = O.z + dz × 240`: `dz` is the rise per sample step and a segment is 60 steps, so
  the ray's height at the start of every later segment is advanced four times too far.
  A horizontal ray is unaffected.
- Flags do not block as such: a flagged sample is 65536 units higher per flag bit value, so
  with flags 3 a flag-1 sample is a 65536-high wall and a flag-2 sample a 131072-high one.

### 9.2 `world_raycast` 0x18ad94

```
if maxT ≤ 0: return −1.0
tT = terrain_raycast(maxT, O, D, terrainFlags)
len = sqrt(D.x×D.x + D.y×D.y);   if len < 0.01: return −1.0     whatever tT was
best = maxT if tT < 0 else tT;   inv = 1.0 / len
unit = (D.x × inv, D.y × inv);   seg = D × (inv × 240.0)
for int((best × len) × K240) + 1 segments, cur starting at O:
    next = cur + seg
    objects = world_collectObjectsInBox((min(next.x, cur.x), min(next.y, cur.y), −10000),
                                        (max(next.x, cur.x), max(next.y, cur.y), 10000), 256)
    for each object o:
        skip if (o.flags & 5) and not (includeFlag40000 and o.flags & 0x40000)
        skip if o is the object to ignore
        rad = 60.0 if o.flags & 0x40000 else o.radius
        to = (o.x − O.x, o.y − O.y)
        perp = |unit.y×to.x − unit.x×to.y|;   skip if rad < perp
        t = (unit.x×to.x + unit.y×to.y) − sqrt(rad×rad − perp×perp)
        if o.flags & 0x40000 and t < 0: t = 0.01
        skip if t < 0
        t = t × inv;   if t < best: best = t, hit = o
    cur = next
return −1.0 if tT < 0 and nothing was hit, else best
```

## 10. Path finding

### 10.1 The grid

One u32 per node. Node (c, r) has index `r × W + c` and stands at world
`((c + originX) × 24, (r + originY) × 24)`. Bits 0–7: link k leads to the node at offset
(−1,−1), (0,−1), (+1,−1), (+1,0), (+1,+1), (0,+1), (−1,+1), (−1,0) for k = 0…7 (index
offsets −1−W, −W, 1−W, 1, W+1, W, W−1, −1). Bits 8–15: search mark, 0 = not reached,
k + 1 = entered through link k of its predecessor, 15 = the start node. Bits 16–31: block
counter; a node with a non-zero counter is never entered.

The block counter is raised by 0x18b6c0 and lowered by 0x18b584 over a rectangle:
columns from `int((x − (r + 5)) × K24 − 1) − originX` up to but not including
`int(((x + r) + 5) × K24 + 1) − originX`, rows likewise from y. Callers: `Torch_ctor`
0x2b1e80 and `StaticFire_initCommon` 0x2c5814 block, `StaticFire_dtor` 0x2c5770 unblocks
[O]. There is no bounds check.

### 10.2 Requests — 0x184e38, 0x184fc8, 0x185148, 0x1852c8

Queue `g_pathQueue` 0x7d43a8, 128 entries of 0x30 bytes, write index 0x44f09c, read index
0x44f0a0. A request with `((write + 1) & 127) == read` is answered at once with result 0.
Otherwise the entry gets world, start (x, y, z), goal (x, y, z), radius, output buffer,
capacity, a handle on the requester and the type (0–3). Type 0 raises a radius below 24.0
to 24.0; the others store it unchanged.

`Creature_requestPath` 0x1164c0 chooses [O]: mode 1 → type 2, mode 2 → type 3, otherwise
radius 0 → type 0, else type 1. The buffer is creature +0x23c with capacity 16.

### 10.3 `path_service(blocking)` 0x184798

While `g_pathEnabled` (0x44f090) is 0 the call is treated as blocking.

```
loop:
    if not blocking and T0 ≥ 9000: return                    hardware timer 0x10000000
    if g_pathBusy:
        r = path_search(entry.world, goalTest, entry.out, entry.capacity, blocking)
        if r == −1: continue                                  suspended: go round again
        if the requester still exists: requester.slot7(r)
        g_pathBusy = 0;  read = (read + 1) & 127;  continue
    if write == read: return
    if the requester no longer exists: read = (read + 1) & 127;  continue
    c = int((start.x × K24 − f32(originX)) + 0.5);   r = int((start.y × K24 − f32(originY)) + 0.5)
    if c < 0 or r < 0 or c ≥ W or r ≥ H: requester.slot7(0);  read += 1;  continue
    clear the marks of the previous search (below)
    counts[0..3] = 0;  rounds = 0;  round = 0
    start node = r × W + c;  ring 0 = [start node];  counts[0] = 1
    cell[start node] |= 0xf00;   previous start = start node;   g_pathBusy = 1
    set the goal test for the type (10.4)
```

The start is the node nearest the position (ties and negatives by truncation after adding
0.5). It is not checked for links or for a block counter.

Clearing the previous marks (0x184a04–0x184b88): nothing if the previous start node had
index 0. Otherwise its mark is cleared and a flood runs from it with two buffers taking
turns: for each node of the current buffer, for each link bit k set in that node, if the
neighbour has a mark, clear it and append the neighbour to the other buffer; after a node,
if the other buffer holds 497 or more, the rest of the current buffer is dropped. Marks the
flood does not reach stay in the grid and block later searches at those nodes.

### 10.4 Goal tests

Called with the node position as floats (px, py). `d2 = (px − gx)×(px − gx) + (py − gy)×(py − gy)`,
`r2 = radius × radius`; for types 1–3 a ray starts at `(px, py, start.z)` toward
`(gx − px, gy − py, 0)` with `maxT` = 1200.0 and terrain flags 0.

| Type | Function | Reached when |
|---|---|---|
| 0 | 0x1844a4 | `d2 < r2` |
| 1 | `path_goalTestClearLine` 0x1844f0 | not (`r2 < d2`), and `0.98 < world_raycast(...)` (requester ignored) |
| 2 | `path_goalTestRanged` 0x1845bc | `r2 < d2`; or, unless (`14400 < r2` and `d2 < 14400`), `terrain_raycast(...) < 0.98` |
| 3 | `path_goalTest3` 0x1846a4 | `r2 < d2`; or, unless (`14400 < r2` and `d2 < 14400`), `world_raycast(...) < 0.75` (requester ignored) |

A ray that hits nothing returns −1.0, so type 1 fails on a completely clear line and types
2 and 3 succeed on one.

### 10.5 `path_search` 0x183e40

State, all global: `round` 0x7d89c0, the count of rounds 0x44f094, four ring buffers of 512
node indices at 0x7d69b0 with their fill counts at 0x7d89b0, and the marks in the grid.

```
if g_pathEnabled == 0: return 0                              the output buffer is not written
found = 0;  empty = 0
loop:
    rounds += 1
    cur = ring[round % 4];  n = counts[round % 4] if rounds < 81 else 0;  counts[round % 4] = 0
    if n == 0:
        empty += 1;  if empty ≥ 5: fail
        round += 1;  continue
    empty = 0
    pass 1, into ring[(round + 2) % 4]:  for each node of cur, in order:
        m = cell >> 8;  skip if m is odd;  skip if link m − 1 of the node is not set
        nb = node + offset[m − 1]
        skip if nb has a mark or a block counter
        mark nb with m                                        also when the ring is full
        skip if the ring holds 512
        append nb;  if goalTest(nb): found = nb + 1, leave pass 1
    pass 2, into ring[(round + 3) % 4]:  for each node of cur, in order:
        for k = 0 .. 7:  skip if link k is not set
            nb = node + offset[k]
            skip if nb has a mark or a block counter
            mark nb with k + 1                                also when the ring is full
            skip if the ring holds 512
            append nb;  if goalTest(nb): found = nb + 1, go to the next node of cur
    round += 1
    if found: trace back
    if not blocking and T0 ≥ 7513: return −1
fail:  if capacity > 0: out[0] = (−1, −1);  return 0
trace back:
    node = found − 1
    repeat: note ((node % W + originX) × 24, (node / W + originY) × 24) as two s16
            d = (cell >> 8) − 1;  if d ≥ 8: stop;  node = node − offset[d]
    write the noted points in reverse (start node first) as pairs of s32, at most
    capacity − 1 of them, then (−1, −1);  return 1
```

- **Costs.** Going on in the same straight direction costs 2 rounds; every other move — a
  diagonal, a turn, the first step from the start, a straight step after a diagonal — costs
  3. (Mark 15 of the start is odd, so the start has no pass 1.)
- **Order and ties.** Nodes are expanded in the order they were appended to their ring; a
  node belongs to whoever marks it first; pass 1 of a round runs before pass 2. The goal is
  the **last** node of the round that passed the test, not the first.
- **Limits.** 80 rounds counted (empty ones included), 512 nodes per ring, five empty rounds
  in a row end the search. A node that finds its ring full is marked but lost.
- **Suspension.** −1 is returned only after a non-empty round without a hit. Everything the
  next call needs is in the globals and the grid, so calling again continues exactly; the
  two locals (`found`, `empty`) are 0 at that point in either case.
- **Result.** Node positions from the start node to the goal node. With capacity 16 the
  creature gets at most the first 15 nodes of the path, start node included.
  `Creature_onPathResult` 0x11a260 (slot 7) sets the waypoint index +0x2bc to 0 and, on
  failure, writes (−1, −1) to the first waypoint and counts the failure at +0x2c4 [O].

## 11. What the differential test covers

`python3 tools/difftest_world.py [SLUS_209.73] [LEVEL.world ...]` — see its docstring. The
level file is copied into the interpreter's memory, the game's own `world_fixup` is run on it
(disc read, texture, light, emitter and automap callees stubbed), `g_world` is pointed at it,
and each property calls the original function and the model with the same seeded random
inputs. Floats are compared as 32-bit patterns. A tenth of each sample is repeated under the
five other floating-point settings of the interpreter.

| Property | Original code run | Compared | Inputs |
|---|---|---|---|
| libm floorf/ceilf | 0x3a57e8, 0x3a5710 | result | random patterns, halves, edge patterns |
| terrain_collectElements | 0x183248 | the element list in order | boxes of 0–400 units, limits 2–256 |
| terrain_height, terrain_heightBelow | 0x183820, 0x1834a8 | result | points on and around elements, heights around the floor (0, ±1, ±11, ±12, ±13, random), radii 0–72 |
| terrain_heightAtPoint | 0x182f28 | result | the same points |
| terrain_testFlag1 | 0x183b48 | result | the same |
| terrain_sweepCircle | 0x185a40 | time, normal, inputs left alone | the same starts; steps of 0–300 units incl. zero and axis-aligned ones, vertical parts; masks 0, 1, 2, 3, 4, 5, 7, 8, 15; with and without a normal pointer |
| world_slideMove | 0x14d238 → 0x185a40 | hit flag, end position, normal | the same; inputs whose steps grow past 150 units are left out (section 7) |
| moving pieces | 0x182b00, 0x182bb4, 0x182b74, then 0x183820 and 0x185a40 | piece height, floor height, sweep time | each door switched off and on and moved in height |
| obj_moveWithCollision | 0x14d4b8 whole, on a stand-in object, the object box query returning nothing | result bits, position, vertical speed | object flags 0, 0x20, 0x40, 0x60 and others; velocities up to 18000 units/s |
| obj_moveAndCollide terrain part | 0x1509f8–0x150bc8 | hit flag, position | speeds 60–1500, falling and rising |
| terrain_raycast | 0x18a5c0 | result | rays of 0.3–1400 units, slopes to ±1.5, vertical and near-vertical, `maxT` ≤ 0, flags 0, 1, 2, 3, 4, 15 |
| world_raycast | 0x18ad94 → 0x18a5c0, the object box query returning 0–4 stand-in objects | result and hit object | object flags 0, 1, 4, 0x20, 0x40, 0x40000, 0x40001, 0x40004; ignore pointer; include flag |
| path block counters | 0x18b6c0, 0x18b584 | the whole node grid | rectangles inside the grid, released in another order, some twice |
| path queue | the four request functions, 0x184798 | queue entries, indexes, results delivered | 5, 140 (overflowing) and 3 requests; service with the path finder disabled |
| path search type 0 | 0x184798 → 0x183e40 → 0x1844a4, blocking | result delivered, path buffer, node marks, search globals | starts at linked nodes ±11 units, goals 3–45 nodes away, radii 0–100, capacities 1–40; 4 % starts off the grid, 3 % requesters deleted |
| path search suspended | the same with `blocking` 0 and T0 fed from a schedule | all of the above after every service call; and the model's one-call answer for the same request | T0 rising by 40–900 per reading from a random start |
| path search types 1–3 | → 0x1844f0, 0x1845bc, 0x1846a4 → the two ray functions | as type 0 | goals 2–8 nodes away, radii 36–600 |

<!-- COUNTS -->

What "tested" does **not** cover:

- The object loops of `obj_moveWithCollision` and all of `Creature_moveBy` (push-out, touch
  calls, standing on objects, root motion, water): not run. Their terrain calls are the
  functions above; their own arithmetic is as read in `docs/spec/movement-camera.md` 5.5–5.6.
- `world_collectObjectsInBox` 0x14a928 was replaced by a list, so the order in which real
  objects reach `world_raycast` is not tested.
- Slide inputs whose steps run away (section 7): the model computes them, the original was
  not waited for.
- Path start nodes at grid index 0, grids with links that leave the grid, node coordinates
  beyond ±32767, a requester deleted while its search is suspended: not generated.
- The handle list (0x1a1738, 0x1a1868) was replaced by a stub that stores a pointer.
- Levels: the 4 unpacked ones and 13 more from the disc; the other 102 were not run.

## 12. Where earlier documents turned out wrong or incomplete

`docs/spec/movement-camera.md` section 5 — **no error found.** 5.2 (collecting elements),
5.3 (the sweep, operand for operand, including the quarter-distance normal), 5.4 (the
slide), the ground and gravity lines of 5.5, 5.8 (`terrain_heightBelow`) and the terrain part
of 5.10 were executed and agree bit for bit. Additions:

| Where | Addition |
|---|---|
| 5.3, last bullet | the zero-length case is worse than a wrong result: with a blocking sample under the circle the time is −0x7fffffff, and the slide's next step is astronomically long (section 7 here) |
| 5.4 | when no sweep is blocked `normalOut` receives an uninitialised stack slot |
| 5.10 | the back-off makes at most 20 tries, and its bounds are now executed |
| 5.3–5.8 | for an unrotated element the cosine is 0x3f7fffff, not 1.0 (section 4.1 here) |

`docs/engine.md`:

| Statement | Executed |
|---|---|
| Pathfinding: "a breadth-first wave … stopping when a cell passes the request's goal test or after 80 rounds" | not breadth-first: continuing straight costs 2 rounds, any other move 3; a round is finished after a hit and the **last** hit of the round is taken; five empty rounds also end it; a node that finds its ring full is marked and lost |
| "bits 8–15 = search mark (direction it was reached from)" | direction + 1; the start node carries 15 |
| "upper 16 bits non-zero = blocked" | a counter, raised and lowered by two unnamed functions, 0x18b6c0 and 0x18b584, for torches and fires (section 10.1) |
| goal test 1: "within the radius and `world_raycast` to the goal is clear" | within the radius and the ray **returns more than 0.98**: a ray that hits nothing returns −1.0 and fails the test |
| goal test 2: "within the radius, at least 120 away when the radius is larger than that, and `terrain_raycast` clear (ranged attackers)" | every node **outside** the radius passes; inside, a node passes when the ray returns less than 0.98, which includes hitting nothing. Requested by `Creature_requestPath` mode 1, which `docs/spec/movement-camera.md` 6.3 describes as fleeing |
| goal test 3: "not read" | as test 2 with `world_raycast` (requester ignored) and the limit 0.75 |
| `terrain_testFlag1` … "-> 1" | the result is the float 1.0 or 0.0 in `$f0` |
| `terrain_raycast`: "first terrain hit along a ray, marching 240 units at a time" | elements are collected per 240-unit segment and marched one 4-unit sample at a time; the first segment with a hit decides; a vertical ray returns a distance; the height carried from one segment to the next is advanced four times too far (section 9.1) |
| World table: `world_movePiece` among the functions that "change the terrain element of a moving piece" | [O] 0x182c98 stores only into chunk records (+0x28, +0x2c, +0x30, +0x36, +0x38). The terrain element of a piece never moves or turns; only its flag 2 and its height offset change. Not executed |
| Open question 6: "Path request type 3 goal test (0x1846a4) and the two routines at 0x185448 and 0x1857e4" | the goal test: above. 0x1857e4 is a straight-line walk probe (height below, then a sweep, in steps of min(2 × radius, 24), with a 3-unit retry mode); 0x185448 walks the path grid calling `terrain_height` and a particle routine. Neither has a caller or a pointer to it in the executable [O: `ps2elf.py xref`/`ptrs` find none]; not modelled |

`docs/formats/world.md`:

| Statement | Executed |
|---|---|
| "*Ray* (`terrain_raycast` 0x18a5c0): marches 240 units at a time against the same samples" | as above; and flags do not block the ray, they add 65536 × (flag bits in the mask) to the sample's height |
| Path grid: "a position is snapped to the nearest node" | only the start of a search is; the goal is used as a point with a radius |
| Path grid bits 16–31: "non-zero blocks the node at run time" | a counter 0–16 (section 10.1) |
| Terrain element flag 4 | in the sweep it only disables the "all lower" skip; in the ray it does so only when the ray was given flags |

## 13. Proposed ledger rows, symbols, patches

Not edited into `FINDINGS.md`; for the maintainers to place. Kind for all: *executed in
isolation* (interpreter, real level data, constructed inputs) unless marked.

| Proposed | Claim | Evidence |
|---|---|---|
| W1 | Which terrain sample a position falls on depends on the multiplier truncating: an unrotated element's cosine is `f32(32767) × 0x38000100` = 0x3f7fffff truncated, 1.0 rounded to nearest. With rounding, a mover an exact multiple of 4 units from an element's origin reads a different sample, and every ray is marched one sample differently per element. Machines (or emulator settings) that differ in the EE's rounding mode would compute different floors, sweeps and paths. *Inferred* for the consequence; the arithmetic is executed under both rules | section 4.1; `tools/test_ref_world.py` `test_axis_aligned_cosine_is_not_one` |
| W2 | `world_slideMove` has no bound on its step: a sweep that starts inside blocking samples returns a negative time, which lengthens the next step; a zero-length horizontal step over a blocking sample makes the next step about 10^35 units and the sweep loop then covers the whole index range. `obj_moveWithCollision` can pass a zero horizontal step (purely vertical velocity). Reachability *Unknown* | section 7; 0x14d334, 0x185b84, 0x14d570 |
| D5 (add) | A search suspended on T0 and resumed gives the same result, path, marks and globals as the same search run in one call | "path search suspended", section 11 |
| engine P13 (add) | between T0 = 7513 and 9000 a non-blocking `path_service` keeps calling `path_search`, which does one round per call | 0x184830–0x184838, 0x184de4 |

Proposed names for addresses nobody has named (no symbol file was edited):

| Address | Name | Note |
|---|---|---|
| 0x18b6c0 | `path_blockNodes` | (radius, world, pos): block counter +1 (max 16) over a node rectangle |
| 0x18b584 | `path_unblockNodes` | the reverse |
| 0x1844a4 | `path_goalTestRadius` | goal test of request type 0 |
| 0x44f094 | `g_pathRounds` | rounds of the current search, limit 80 |
| 0x44f098 | `g_pathPrevStart` | start node of the last search; its marks are cleared from here |
| 0x7d89c0 | `g_pathRound` | ring index of the current round |
| 0x7d89b0 | `g_pathRingCounts` | int[4] |
| 0x7d69b0 | `g_pathRings` | 4 × 512 node indices |
| 0x7d35e0 | `g_pathGoalTest` | function pointer |
| 0x7d5ba8 / 0x7d89c4 | `g_pathGoalXY` / `g_pathGoalRadiusSq` | type 0 |
| 0x7d5bb0, 0x7d89c8, 0x7d89cc, 0x7d89d0, 0x7d89d4 | `g_pathGoalPos`, `g_pathGoalRequester`, `g_pathGoalStartZ`, `g_pathGoalWorld`, `g_pathGoalRadiusSq2` | types 1–3 |

No patch is proposed.

## 14. Not done, not known

- Nothing here was run on a console or a console emulator; the last bit of sums and
  products on real hardware is the open question of `docs/issues/dynamic-tests.md`.
- `Creature_moveBy`, the object part of `obj_moveWithCollision`, `world_collectObjectsInBox`,
  `world_findFreeSpot` and the creature probe-ray helpers were not run.
- `world_resetRuntime` 0x18b1b8 (queue indexes and `g_pathPrevStart` to 0, `g_pathEnabled`
  to 1) and the level-restart routine 0x18b270 (every path node reduced to its low byte, i.e.
  marks and block counters cleared; every piece's element flag 2 cleared) were read, not run
  [O]. 0x18b1b8 does not clear `g_pathBusy`.
- Whether any level or script makes a creature search from a start node whose links are all
  clear, or from node index 0, was not looked into.
- The meaning of request types 1–3 to the AI (which monster asks for which) is in the
  creature code and was not read beyond `Creature_requestPath`.
