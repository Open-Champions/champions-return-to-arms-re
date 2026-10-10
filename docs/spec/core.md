# The engine core: math, random numbers, object pool, handle lists

A specification for someone rebuilding these pieces so that the result stays in step with
original clients. Online play is lockstep: every machine must compute the same bits. This
document says what each function computes, in which order, with which constants.

- Model: `tools/ref_core.py` (Python, standard library, no game data).
- Differential test: `tools/difftest_core.py` runs the game's own instructions in
  `tools/ee_emu.py` and compares every output word with the model.
- Unit tests of the model that need no game file: `tools/test_ref_core.py` (55 tests).

**Evidence.** Everything below is *executed in isolation* unless marked otherwise: the
original function ran in the interpreter on inputs the test built, and the model produced
the same words (section 13 lists inputs and counts). That shows what the code does with
those inputs. It does not show that the interpreter's floating point equals a console's in
the last bit: where a result is a float, "bit for bit" means "under the interpreter's
floating-point model", and section 2 says how far that goes. Nothing here was run on a
console or in a console emulator.

Addresses are for `SLUS_209.73` (US 2.00). Names are those of `symbols/engine.tsv`,
`symbols/objects.tsv`, `symbols/player.tsv`, `symbols/fp.tsv` and `names.tsv`; a name in
*italics* is a suggestion for an address that has none (section 14).

## 1. Conventions

| Thing | Layout |
|---|---|
| float | IEEE single *format*; arithmetic is the console's (section 2) |
| angle | 16 bits, 0x10000 = one turn; every function reduces its argument to a signed 16-bit value first and ignores the bits above |
| vec3 | x, y, z |
| quat | x, y, z, w |
| mat3 | 9 floats, three rows of three; a vector is transformed as a row vector: `out[c] = v.x*m[0][c] + v.y*m[1][c] + v.z*m[2][c]` |
| mat34 | 12 floats: a mat3, then the translation row |
| mat4 | 16 floats, four rows of four |
| bbox | min x, y, z, max x, y, z |

Arguments: integers and pointers in `a0…a3, t0…`, floats in `f12…` in order, the two
counted separately (`mat34_setPosRotZScale(scale, m, pos, angle)` takes scale in `f12`, m
in `a0`, pos in `a1`, angle in `a2`). A float result is in `f0`.

Notation: `dot3(a0,b0, a1,b1, a2,b2)` means `(a0*b0 + a1*b1) + a2*b2`, evaluated exactly
in that grouping. Every sum of products in this library is grouped left to right like
this, and the grouping is part of the specification: a different association changes the
last bit (regrouping the model as `a0*b0 + (a1*b1 + a2*b2)` makes the test fail in 40–85 %
of the cases of every matrix and vector product).

## 2. Floating-point behaviours a rebuild must imitate

Context: `FINDINGS.md` L13 and `docs/issues/float-divergence.md`. This is the short list
for an implementer; items 1–3 are the ones a straightforward C++ port gets wrong on every
frame.

1. **Results are truncated toward zero**, not rounded to nearest: add, subtract, multiply,
   divide, square root, and integer-to-float conversion (`16777217` becomes `16777216.0`).
   `1.0 / 3.0` is 0x3eaaaaaa. On a PC that means round-toward-zero mode for single
   precision at the least; see item 9 for what that still leaves open.
2. **No NaN, no infinity, no denormal.** An exponent field of 0 is zero whatever the
   fraction; an exponent field of 255 is an ordinary number; overflow gives ±0x7fffffff;
   underflow gives a signed zero; anything divided by zero gives ±0x7fffffff (0/0
   included, sign = exclusive-or of the operand signs); `sqrt.s` takes the root of the
   magnitude. Compares order values by sign and magnitude of the raw pattern, with +0
   equal to −0.
3. **Decimal literals were truncated by the compiler.** `0.1f` is 0x3dcccccc, `0.3f` is
   0x3e999999, `0.9` (double) is 0x3feccccccccccccc. A modern compiler rounds them to
   nearest and gets a different constant for about half of all literals. Write constants
   as bit patterns. (Shown here for the C library: all 46 coefficient literals of `atanf`
   and `powf` in the executable equal the published decimal constant truncated to 24 bits,
   22 of them differ from the rounded value; and for 15 double literals of game code, 9 of
   which differ. `float-divergence.md` reports the same for game constants.)
4. **`double` is software, and that software truncates too.** The console has no
   double-precision hardware; the compiler's support library does it (section 9). Game
   code reaches it constantly, because `f * 1.5` with an unsuffixed literal means: widen
   to double, multiply, narrow. In this build the library truncates every result, has no
   denormals, and its double-to-float conversion truncates. Compiled for a PC, the same
   source line gives a different float in about half of all cases (difftest property
   `double.literal`: 3,193 of 6,000). `float-divergence.md` says double arithmetic
   "cannot differ between machines"; that is true between two copies of the original and
   false between an original and a rebuild that uses the host's `double`.
5. **Float to integer is `cvt.w.s`**: toward zero, saturating at 0x7fffffff and
   −0x80000000 (never the 0x80000000 "indefinite" value of x86). Float to *unsigned* is the
   compiler's two-branch idiom (section 3).
6. **Order of operations is part of the result.** No multiply-add instruction is used in
   these functions; each product and each sum is truncated separately. Do not let a
   compiler contract `a*b + c` into a fused multiply-add or reassociate.
7. **The sine and cosine are the engine's own polynomial** (section 4), not a library
   call, and they are not exact at the quarter turns: `sin16(0)` is 2⁻²² (0x34800000), not
   0. An object facing angle 0 has that value in its matrix.
8. **`atan2`, `pow`, `fmod`, `floor`, `ceil`, `sqrtf` are this build of newlib** running on
   the console's arithmetic (section 8): no NaN or infinity branches, results that differ
   from a PC libm in the last bits and in every special case. The library `sqrtf` rounds
   to nearest while the `sqrt.s` instruction truncates; the engine uses the instruction,
   `powf(x, 0.5)` uses the library.
9. **The last bit of the hardware adder and multiplier is not settled by this work.** The
   interpreter offers four models of the adder (they differ only when the operands are 25
   or more binary places apart) and a switch for the multiplier and for divide rounding.
   The model reproduces the original under all of them, which shows the *sequence of
   operations* is right; which variant a console implements is Unknown (see
   `docs/issues/dynamic-tests.md`). A rebuild should keep the primitive operations in one
   place so that this can be corrected once measured.
10. **Uninitialised and per-machine inputs are not arithmetic.** The noise table depends
    on the CPU cycle counter and on three stale stack words (section 7); the cosmetic and
    C-library generators are per machine (section 10). Do not feed them into shared state.

## 3. Arithmetic primitives

All in `ref_core.Fpu`; the differential test checks each against the interpreter for
random and edge patterns under every setting.

| Operation | Rule |
|---|---|
| unpack | sign, exponent field e, 24-bit significand m (0 when e = 0); value m·2^(e−150) |
| add, sub | zero + zero = zero, negative only if both are; zero + x = x unchanged; otherwise the exact sum truncated to 24 bits (interpreter default: the smaller operand is first cut to six extra bits, and ignored altogether from 25 exponents apart) |
| mul | exact product truncated; a zero operand gives a zero with the product's sign |
| div | exact quotient truncated; x/0 = ±0x7fffffff; 0/x = signed zero |
| sqrt | root of the magnitude, truncated; a zero keeps its sign |
| rsqrt(a, b) | `a / sqrt(b)` as two truncating steps |
| neg, abs | flip, clear the sign bit; nothing else |
| int to float | truncated to 24 bits |
| float to int | toward zero, saturating |
| compare | by sign and magnitude of the pattern; +0 = −0 |
| max, min | the first operand unless the second compares greater (smaller) |

Inline conversions the compiler emitted (run as stretches of their functions):

| Idiom | Rule | Example site |
|---|---|---|
| float to unsigned | below 2³¹ (0x4f000000): `cvt.w.s`; otherwise `cvt.w.s(x − 2³¹)` with bit 31 set | 0x164f70; 77 sites compare with 0x4f000000 |
| round half away | `0 <= x ? x + 0.5 : x − 0.5`, then `cvt.w.s` | 0x16162c |
| degrees to angle | `(degrees * 0.5) * 182.04443` (0x43360b60, itself truncated), rounded half away, added to a base angle, minus 0x4000, 16 bits | 0x161610 |
| float to 16 bits | `cvt.w.s(x * 182.0)` (0x43360000 at this site), low 16 bits stored | 0x1985b0 |
| radians to angle | `cvt.w.s(x * 10430.378)` (0x4622f983), low 16 bits | end of `math_atan2_16` |
| 16-bit random to [0, 1) | `float(draw) * 2⁻¹⁶` (0x37800000) | 685 sites |

The conversion constant differs from site to site (182.04443 here, 182.0 there); copy each
site, do not share one helper.

## 4. Angles

### `math_cos16` 0x166630, `math_sin16` 0x1666e0

(The task brief had these two the other way round; the symbol file is right: 0x166630 is
the cosine. `mat3_rotateAxis` uses the first as cosine and the second as sine.)

```
cos16(angle):
    a = signed16(angle)
    sign = 1.0
    if bit 15 of a != bit 14 of a:          # second or third quadrant
        sign = -1.0
        a = low 15 bits of a, sign-extended from bit 14      # a - 0x8000 or a + 0x8000
    x  = float(a) * 0x38490fda              # pi/65536: HALF the angle in radians
    x2 = x * x
    x3 = x * x2
    s  = x - x3 * 0x3e2aaa57                # 0.16666542
    x5 = x3 * x2
    s  = s + x5 * 0x3c086b24                # 0.008326326
    x7 = x5 * x2
    s  = s - x7 * 0x39458017                # 0.00018835101
    return sign * (1.0 - (s + s) * s)       # cos 2x = 1 - 2 sin^2 x

sin16(angle) = cos16(angle - 0x4000)        # the same code after one subtraction
```

Properties (from the model, all 65,536 angles equal to the original): the largest error
against the true cosine is 7.1·10⁻⁷; no angle gives exactly 0; `cos16(0) = 1.0`,
`cos16(0x8000) = −1.0`, `sin16(0x4000) = 1.0`, but `sin16(0) = 0x34800000` (+2⁻²²),
`sin16(0x8000) = cos16(0x4000) = 0xb4800000`, `cos16(0xc000) = 0x34800000`;
`cos16(a) = cos16(−a)` fails for 1,190 angles. A rotation by angle 0 therefore does not
leave a matrix unchanged: `mat3_rotateAxis(identity, Z, 0)` has ±2⁻²² off the diagonal.

`mat3_setRotZ`, `mat34_setPosRotZ` and `mat34_setPosRotZScale` contain inlined copies of
both; the operations are the same.

### `math_atan2_16` 0x166798 (f12 = y, f13 = x)

`signed16(cvt.w.s(atan2f(y, x) * 0x4622f983))` with the C library's `atan2f` (section 8).
Because π is 0x40490fda (below the true value) and everything truncates, the cardinal
directions come out one short: (y, x) = (1, 1) → 8191, (1, 0) → 16383, (0, −1) → 32767,
(−0, −1) → −32767, (−1, 0) → −16383; (0, 0) → 0.

### `angle_turnDir` 0x166bc8 (a, b, out)

`d = signed16(signed16(a) − signed16(b))`. Returns −1 when d > 0, +1 otherwise (so +1 for
equal angles and for d = −0x8000). When `out` is not null it receives |d| as a 32-bit
word (0x8000 for a half turn).

### `angle_approach` 0x166c18 (f12 rate, f13 min, f14 max, a0 current, a1 target)

```
d    = signed16(signed16(current) - signed16(target))
step = float(|d|) * rate
if min != -1.0 and step < min: step = min
if max != -1.0 and max < step: step = max
return signed16(current + cvt.w.s(step) * (d > 0 ? -1 : 1))
```

The step is not limited to the remaining difference: `min` can carry the angle past the
target (rate 0.1, min 700, from 100 toward 0 gives −600).

## 5. Scalars, colours, vectors, boxes

`t2 = t*t`, `t3 = t2*t` throughout.

| Function | Result |
|---|---|
| `math_hermite` 0x1658f0 (t, p0, p1, m0, m1) | `v = ((t3+t3) − t2*3.0) * p0 + p0`; `v = v + (t3*(−2.0) + t2*3.0) * p1`; `v = v + ((t3 − (t2+t2)) + t) * m0`; `v = v + (t3 − t2) * m1`. Note `h*p0 + p0`, not `(h + 1)*p0` as in the vector version |
| `vec3_hermite` 0x162310 (t, p0, p1, m0, m1, out) | per component `((p0*h00 + p1*h01) + m0*h10) + m1*h11` with `h00 = ((t3+t3) − t2*3.0) + 1.0`, `h01 = t3*(−2.0) + t2*3.0`, `h10 = (t3 − (t2+t2)) + t`, `h11 = t3 − t2` |
| *vec3_hermiteDerivative* 0x162440 | same shape, weights `t2*6 − t*6`, `t2*(−6) + t*6`, `(t2*3 − t*4) + 1`, `t2*3 − (t+t)`. No caller found |
| `math_log2Floor` 0x1665f0 | floor(log2 x) for x ≥ 1, 0 for x ≤ 1 including negative (64-bit test) |
| `color_scaleClamped` 0x165428 (f12 factor, a0 colour) | each byte: `cvt.w.s(float(byte) * factor)` limited to 0…255 |
| *color_fromHSV* 0x164f10 (h, s, v) | each clamped to [0, 1]; `s == 0` → grey v; else `h6 = h*6.0`, `i = cvt.w.s(h6)`, `f = h6 − float(i)`, `p = v*(1−s)`, `q = v*(1 − s*f)`, `t = v*(1 − s*(1−f))`; sectors 0…5 give (r,g,b) = (v,t,p) (q,v,p) (p,v,t) (p,q,v) (t,p,v) (v,p,q); sector 6 (h = 1.0) returns 0xff000000. Result `0xff000000 | b<<16 | g<<8 | r`, each `unsigned(x * 255.0)` |
| `vec3_dotDelta` 0x1667d8 (a, n, b) | `dot3(n0, b0−a0, n1, b1−a1, n2, b2−a2)` |
| `vec2_dotDelta` 0x166820 | `n0*(b0−a0) + n1*(b1−a1)` |
| `bbox_setEmpty` 0x166ec0 | min = 10,000,000.0 (0x4b189680), max = −10,000,000.0 |
| `bbox_union` 0x166cc0 (a, b) | `if b.min[i] < a.min[i]` copy; `if a.max[i] < b.max[i]` copy. Strict: an equal value (or −0 against +0) is not copied |
| *bbox_addPoint* 0x166d40, *bbox_containsPoint* 0x166dc0, *bbox_overlaps* 0x166e38 | the obvious ones; contains uses ≤ on both sides, overlaps is false only when one max < the other min. No caller found |

### *ray_planeDistance* 0x163658 (a0 point, a1 direction, a2 plane point, a3 normal)

```
facing = dot3(d0,n0, d1,n1, d2,n2)
h      = dot3(n0, p0-q0, n1, p1-q1, n2, p2-q2)
if 0 <= facing or h < 0: return -1.0
den = -dot3((n0*h), d0, (n1*h), d1, (n2*h), d2)
if 0x3a83126e < |den|: return h * (h / den)          # 0.001
return h * (h * 0x447a0001)                          # 1000.00006
```

### *segment_hitsPlaneNearEdge* 0x163790 (a0 a, a1 b, a2 normal, a3 p1, t0 p0, t1 out)

```
d = p1 - p0
if 0 <= dot3(d, n): return 0
den = dot3(d, n);  if -0.01 < den < 0: den = -0.01  (0xbc23d70a)   # and likewise +0.01
t = dot3(a - p0, n) / den
if t < 0 or 1 < t: return 0
out = p0 + d*t                                       # written from here on
e = a - b;  len = sqrt((e0*e0 + e1*e1) + e2*e2);  u = e * (1.0 / len)
along = dot3(u, out - b)
return 0 if along < -0.25 or len + 0.25 < along else 1
```

One caller each (0x204f28, 0x20b748).

## 6. Matrices and quaternions

"Buffered" means the result is built in a temporary (or the inputs are read before the
first store), so the output may be one of the inputs. Overlaps actually run against the
original: output = either factor for `mat3_mul`, `mat34_mul`, `mat4_mul`, `quat_mul`;
output = the second factor for `mat34_mulMat3`, `mat4_mulMat34`; output = input for
`mat4_invert`, `mat34_invert`, `mat3_transpose`; output = the vector (not the matrix) for
the seven vector transforms and `quat_rotateVec`; output = p0 or m1 for `vec3_hermite`.
No other overlap was tried, and no caller was checked for passing one.

| Function | Result |
|---|---|
| `mat3_setIdentity` 0x165650, `mat34_setIdentity` 0x165680, `mat34_setTranslation` 0x166850 (m, pos) | as named |
| `mat3_mul` 0x165710 (out, a, b) | `out[r][c] = dot3(a[r][0], b[0][c], a[r][1], b[1][c], a[r][2], b[2][c])`. Buffered |
| `mat34_mulMat3` 0x162580 (out, mat3 a, mat34 b) | rotation as `mat3_mul`, translation copied from b. Buffered |
| `mat34_mul` 0x162808 (out, a, b) | rotation as `mat3_mul`; translation `dot3(a[3][0], b[0][c], …) + b[3][c]` (b's translation added last). Buffered |
| `mat4_mulMat34` 0x162698 (out, mat34 a, mat4 b) | a taken as 4×4 with last column 0,0,0,1; last row `dot3(…) + b[3][c]`. Buffered |
| `mat4_mul` 0x1657e0 | `dot3(…) + a[r][3]*b[3][c]`. No caller found |
| `mat3_rotateAxis` 0x162960 = `mat34_rotateAxis` 0x163000 (m, axis, angle) | `c = cos16`, `s = sin16`. Axis 0: row1' = c*row1 + s*row2, row2' = (−s)*row1 + c*row2. Axis 1: row0' = c*row0 − s*row2, row2' = s*row0 + c*row2. Axis 2: row0' = c*row0 + s*row1, row1' = (−s)*row0 + c*row1. Any other axis: nothing. `(−s)` is the negated sine multiplied, not a subtraction. Only the first nine floats are touched |
| *mat3_rotateAxisPost* 0x162df0 | the same rotation applied to two columns: axis 0: col1' = c*col1 − s*col2, col2' = s*col1 + c*col2; axis 1: col0' = c*col0 + s*col2, col2' = (−s)*col0 + c*col2; axis 2: col0' = c*col0 − s*col1, col1' = s*col0 + c*col1. One caller (0x179030). 0x162b68 does it on all four rows of a mat34, 0x163208 is the row version for a mat4; neither has a caller |
| `mat3_setRotZ` 0x1639d8 (m, angle) | `[c, s, 0, −s, c, 0, 0, 0, 1]` |
| `mat34_setPosRotZ` 0x163b30 (m, pos, angle) | the same plus pos |
| `mat34_setPosRotZScale` 0x163cb8 (scale, m, pos, angle) | `[c*k, s*k, 0, −(s*k), c*k, 0, 0, 0, k]` plus pos |
| `mat34_setPosEulerScale` 0x163e48 (scale, m, pos, yaw, pitch, roll) | identity with pos; `rotateAxis(Z, yaw + 0x4000)`, `rotateAxis(Y, pitch)`, `rotateAxis(X, roll)`; then the nine rotation floats times scale |
| `mat4_invert` 0x163f98 (out, in) | see below. Buffered |
| `mat34_invert` 0x164288 (out, in) | widen to 4×4 (last column 0,0,0,1), `mat4_invert`, keep three columns. Buffered |
| `mat3_transpose` 0x166298 | buffered |
| `mat3_scale` 0x165cc0 (s, m), `mat3_scaleXYZ` 0x165d30 (sx, sy, sz, m), `mat4_scaleRotation` 0x165b98 (s, mat4) | element times scale; XYZ scales row 0, 1, 2 |
| `mat34_translateLocal` 0x165b10 (x, y, z, m) | `t[c] = t[c] + dot3(m[0][c], x, m[1][c], y, m[2][c], z)` |
| `mat4_translateLocal` 0x165c08 | the same on four columns of the last row |
| `mat3_mulVec` 0x165e40 = `mat34_rotateVec` 0x166158 (out, m, v) | `out[c] = dot3(m[0][c], v.x, m[1][c], v.y, m[2][c], v.z)`. Buffered |
| `mat3_mulVecTransposed` 0x165da0 = 0x1661f8 | `out[r] = dot3(m[r][0], v.x, m[r][1], v.y, m[r][2], v.z)`. Buffered |
| `mat34_transformPoint` 0x1660a0 | `mat3_mulVec` then `+ m[3][c]` as the last addition. Buffered |
| `mat4_transformPoint` 0x165ee0 → w in f0 | `dot3(…) + m[3][c]` for c = 0…3; the fourth is returned, the point is not divided. 0x165fc0 is the same with the matrix read by columns |
| `mat4_setProjection` 0x165950 (sx, sy, scale, zA, zB, near, far, out) | `[0] = scale*sx`, `[5] = scale*sy`, `[10] = zB − ((zB−zA)*far)/(far−near)`, `[11] = 1`, `[14] = (((zB−zA)*far)*near)/(far−near)`, rest 0. 0x1659d0 and 0x165a70 multiply [10] and [14] by 16.0 and then by 2⁴⁶ |
| `quat_fromAxisAngle` 0x1663c0 (x, y, z, out, angle) | `h = signed16(angle) >> 1`; `k = sin16(h) * rsqrt(1.0, (x*x + y*y) + z*z)`; `[k*x, k*y, k*z, cos16(h)]` |
| `quat_mul` 0x166480 (out, a, b) | `x = (aw*bx + bw*ax) + (ay*bz − az*by)`, y and z cyclically, `w = aw*bw − dot3(ax,bx, ay,by, az,bz)`. Buffered |
| `quat_normalize` 0x166550 | each component times `rsqrt(1.0, ((w*w + x*x) + y*y) + z*z)` |
| `quat_rotateVec` 0x163490 (out, q, v) | `tw = −dot3(x,vx, y,vy, z,vz)`; `tx = w*vx + (y*vz − z*vy)` and cyclically; `out.x = (tw*(−x) + w*tx) + (ty*(−z) − tz*(−y))` and cyclically. Not divided by the norm. Buffered |
| `mat3_fromQuat` 0x1668b8, `mat34_fromQuat` 0x166988 | `s = 2.0 / (((x*x + y*y) + z*z) + w*w)`; `xs, ys, zs = x*s, y*s, z*s`; `xx = x*xs, yy = y*ys, zz = z*zs, xy = x*ys, xz = x*zs, yz = y*zs, wx = w*xs, wy = w*ys, wz = w*zs`; rows `[1−(yy+zz), xy+wz, xz−wy]`, `[xy−wz, 1−(xx+zz), yz+wx]`, `[xz+wy, yz−wx, 1−(xx+yy)]` |
| `quat_fromMat3` 0x164330 | see below |

### `mat4_invert`

Works on a copy T of the input and builds the result R from the identity. For c = 0…3:

1. pivot = T[c][c]; for j = c+1…3: if |pivot so far| < |T[c][j]| take that one (strictly
   greater only; the search runs along **row** c).
2. If another column j was chosen, exchange columns c and j in both T and R.
3. If |pivot| ≤ 0x38d1b717 (0.0001): the result is the **identity**; stop.
4. `inv = 1.0 / pivot`; multiply column c of T and of R by inv.
5. For every other column j: `f = T[c][j]`; column j −= column c · f, in T and in R
   (each element `x − y*f`).

### `quat_fromMat3`

```
trace = (m[0] + m[4]) + m[8]
if 0 < trace:
    r = sqrt(trace + 1.0);  w = r * 0.5;  s = 0.5 / r
    x, y, z = (m[5]-m[7])*s, (m[6]-m[2])*s, (m[1]-m[3])*s
else:
    i = 1 if m[0] < m[4] else 0;   if m[4i] < m[8]: i = 2
    j, k = next of i, next of j           (0 -> 1 -> 2 -> 0)
    r = sqrt((m[i][i] - (m[j][j] + m[k][k])) + 1.0)
    q[i] = r * 0.5
    s = 0.5 / r     (left as r when r == 0)
    w = (m[j][k] - m[k][j]) * s;  q[j] = (m[i][j] + m[j][i]) * s;  q[k] = (m[i][k] + m[k][i]) * s
```

## 7. Noise

`math_noise` 0x166b48 (index) with the 256 signed 16-bit entries of `g_noiseTable`
0x6e0d90:

```
f = float(index & 15) * 0.0625
i = index >> 4                       # arithmetic
return (float(table[i & 255]) * (1.0 - f) + float(table[(i+1) & 255]) * f) * 2^-15
```

Period 4,096. 0x164578 (out, index, step) returns three such samples at index, index+step,
index+2·step; no caller found.

`math_buildNoiseTable` 0x1646c8 fills the table once at boot from `g_cosmeticSeed`
0x404460, which then holds the CPU cycle counter. Four accumulators; for entry n = 0…255
and octave k = 0…3: when n is a multiple of 2^k, draw `target = float(draw)*2⁻¹⁶ − 0.5`
from the cosmetic generator (0 instead for n ≥ 241, so the table closes), set
`slope[k] = (target − acc[k]) * (1.0 / float(2^k))`; then `acc[k] += slope[k]`. The entry
is the low 16 bits of `cvt.w.s(sum * 40000.0)`, where `sum` starts at 0 and adds
`acc[k] * w[k]` for k = 0…3 in turn, with weights `w[k] = powf(float(2^(3−k)), −1.0)` =
1/8, 1/4, 1/2, 1 (exact, as executed).

**Observed and executed:** only accumulator 0 (and slope 0) is cleared. Accumulators 1…3
start from the three stack words at sp+4, sp+8, sp+0xc of the function's own frame. The
test sets those words and the model reproduces the table for zero and non-zero values. The
table is per machine anyway (engine P-row "noise table"); this adds a second reason.

## 8. C-library routines (newlib, on the console's arithmetic)

Bit-pattern tests replace all classification; the NaN and infinity branches of the
published sources are absent. Coefficients are the published fdlibm decimals truncated
(section 2, item 3); the test compares every one with the executable.

| Routine | Behaviour |
|---|---|
| `libm_fabsf` 0x3aa7e8, *libm_copysignf* 0x3aa920 | on the bits |
| `libm_floorf` 0x3a57e8, `libm_ceilf` 0x3a5710 | integer bit code. For |x| < 1: floor gives +0 for any non-negative pattern and −1.0 for a negative non-zero value; ceil gives −0 for any negative pattern (`ceilf(−0.25)` is −0) and 1.0 for a positive non-zero value; a zero pattern of the other sign is returned as it is. From 2²³ up the argument is returned |
| `libm_atanf` 0x3aa558 | fdlibm `s_atanf.c`: |x| ≥ 2³⁴ → ±(atanhi[3] + atanlo[3]); |x| < 2⁻²⁹ → x; ranges split at bit patterns 0x3ee00000, 0x3f300000, 0x3f980000, 0x401c0000; the two polynomial halves are evaluated Horner-fashion in w = z·z and added as `s1 + s2`; result `atanhi[id] − ((x*(s1+s2) − atanlo[id]) − x)` |
| `libm_atan2f` 0x3a5a80 → 0x3a7328 (y, x) | x = 1.0 exactly → `atanf(y)`. y "zero" (bits ≤ 0x007fffff): returns y for x ≥ 0, +π for x < 0 and y ≥ +0, −π for both negative — exactly π, without the usual tiny addend. x "zero": ±π/2 (0x3fc90fda). Else with k = exponent difference: k > 60 → π/2; x < 0 and k < −60 → 0; otherwise `atanf(|y / x|)`; then by quadrant: z, −z, `π − (z − π_lo)`, `(z − π_lo) − π` with π = 0x40490fda, π_lo = 0x34222168 |
| `libm_powf` 0x3a5ac8 → 0x3a7930 (x, y) | fdlibm `e_powf.c`. Shortcuts in this order: y "zero" → 1; y = ±1 → x or 1/x; y = 2 → x·x; y = 0.5 and x ≥ +0 → library `sqrtf(x)`; x "zero" or |x| = 1 → |x| or 1/|x| (negated for negative x and odd y; `(z−z)/(z−z)` = 0x7fffffff for x = −1 and non-integer y); negative x with non-integer y → 0x7fffffff. |y| > 2²⁷: 0 or the folded constant "huge·huge" 0x7f7fffff unless x is within 8 units of 1.0. Otherwise the high/low split of the source, every "high part" being the pattern with its low 12 bits cleared. Overflow returns `(sign·1e30)·1e30` = ±0x7fffffff, underflow `(sign·1e−30)·1e−30` = ±0. `powf(10, 2)` is exactly 100 (shortcut); `powf(10, 3)` happens to be exactly 1000 too, but no general exactness holds |
| *libm_sqrtf* 0x3a84c0 | integer bit-by-bit root, **rounded to nearest**; zero returns itself; negative returns 0x7fffffff |
| `libm_scalbnf` 0x3aa810 (x, n) | exponent field + n; zero unchanged; field ≥ 256 → `copysign(1e30, x)·1e30`; field ≤ 0 → `copysign(1e−30, x)·1e−30` (a signed zero), or the overflow value when n > 50000 |
| `libm_fmodf` 0x3a5ab0 → 0x3a7760 | exact shift-and-subtract remainder with the sign of x; a "zero" divisor returns `(x·y)/(x·y)` = 0x7fffffff; equal magnitudes return ±0 |
| `libm_fmod` 0x3a5a38 → 0x3a6208 (doubles) | fdlibm `e_fmod.c` on the 32-bit halves, exact, denormals honoured (the only place they are); y = 0, x infinite or NaN, y NaN → `(x·y)/(x·y)` through the software double routines = NaN |

Not modelled: the other library routines game code calls — 0x3a51b0 and 0x3a53c0 (double
floor/ceil, *Inferred* from shape), 0x3a55d8 (double sine or cosine), 0x3a58c0, 0x3a59a8,
0x3a5a20, 0x3a5a50, 0x3a5a68, 0x3a5a98 (callers listed in section 15). They sit on the
same truncating arithmetic, so a PC libm will not reproduce them either.

## 9. Double precision in software (0x3ae688–0x3afc80)

GCC's `fp-bit.c`, built without rounding and without denormals. *Observed* in the code and
executed: the "pack" step shifts the guard bits out with no rounding step; "unpack" maps
exponent field 0 to zero whatever the fraction.

Call sites are counted with `tools/ps2elf.py xref`: all, and those below 0x323000 (the
game's own areas, as opposed to the libraries).

| Routine | Call sites: all / game | Rule |
|---|---|---|
| float → double 0x3aef58 | 97 / 94 | exact; field 0 → signed zero; field 255 is a number (0x7f800000 → 2¹²⁸) |
| double → float 0x3afb90 | 64 / 60 | truncated; below 2⁻¹²⁶ → signed zero; from 2¹²⁹ up, infinity and NaN → ±0x7f800000; [2¹²⁸, 2¹²⁹) → a float with field 255 |
| int → double 0x3afa08 | 42 / 21 | exact |
| double → int 0x3afac0 | 36 / 19 | toward zero, saturating (infinity too); NaN → 0 |
| add 0x3af410 | 122 / 28 | exact sum truncated toward zero, except that an operand 2⁶⁴ or more times smaller is dropped (so `a − tiny = a`, where exact truncation would give the next value down); x − x = +0; −0 + −0 = −0; ∞ − ∞ = NaN |
| subtract 0x3af468 | 138 / 53 | add with the second operand's sign flipped |
| multiply 0x3af4d0 | 170 / 48 | exact product truncated; ∞·0 = NaN |
| divide 0x3af758 | 15 / 1 | exact quotient truncated; x/0 = ±∞; 0/0 and ∞/∞ = NaN; x/∞ = ±0 |
| compare 0x3af9b8 | 110 / 56 | −1, 0, +1; +1 when either is NaN; +0 = −0 |

What follows a float → double conversion in the code (the next call after each of the 97
sites): a comparison 40 times, a multiply 19, an add 14, `libm_fmod` 6, `libc_sprintf` 5.
A comparison of a widened float with a double literal comes out the same whichever way the
literal was rounded (no float lies strictly between two neighbouring doubles); the
multiplies and adds do not.

The NaN an invalid operation returns is 0x7ff8000000000000. Double literals in game code
are the decimal value truncated to 53 bits. The idiom to copy is
`narrow(mul(widen(f), K))`, with K the truncated literal: e.g. the loot code multiplies by
1.5 (0x3ff8000000000000) and by 2.4 (0x4003333333333333, at 0x520048).

## 10. Random generators

One generator, several seeds:

```
state = state * 0x0019660D + 0x3C6EF35F      (mod 2^32)
draw  = state >> 16                           # the upper 16 bits of the NEW state
```

(This is the "quick and dirty" generator of Numerical Recipes; from state 0 the states are
3C6EF35F, 47502932, D1CCF6E9, …)

| Seed | Where | Notes |
|---|---|---|
| shared | `g_randSeed` 0x404464, updated by three inlined instructions at every use (as a function: script `getRand` 0x146570) | 0 in the executable, set to 0 by `net_startSync`; part of the sync hash |
| per object | object +0x44, `GameObject_rand` 0x1509d0 | `GameObject_ctor` (0x14cd50–0x14cd80) advances the shared seed once and stores the **draw** — a 16-bit number — as the object's state |
| per spell | spell +0x10, `Spell_rand` 0x16a964 | seeded the same way by every Spell constructor (out-of-line copy 0x3d0bc4) |
| cosmetic | `g_cosmeticSeed` 0x404460 | CPU cycle counter at boot; per machine |
| third | 0x404468 | per machine |

Float forms: `unit = float(draw) * 2⁻¹⁶` (*GameObject_randUnit* 0x3c7f30);
`signed = (unit + unit) − 1.0`; *GameObject_randInUnitSphere* 0x3c7f60 (obj, out) and
0x3c8030 (out, obj) draw three signed values and repeat while `1.0 < (x*x + y*y) + z*z`
— the number of draws consumed depends on the values, and the test checks it.

C library: `libc_rand` 0x3b70f0 keeps a 64-bit state (re-entrancy structure +0xa8, 1 in
the executable): `state = state * 6364136223846793005 + 1`, result
`(state >> 32) & 0x7fffffff`; `libc_srand` 0x3b70d8 stores the 32-bit seed zero-extended.
Per machine.

## 11. Object pool

`g_poolClasses` 0x403a10: four 16-byte records {block size, count, base, free head}:
(0x180, 512), (0x500, 512), (3000, 32) and a terminator of size 0x7fffffff. Memory:
0xe7700 bytes from 0x5f88c0, the classes back to back (bases 0x5f88c0, 0x6288c0, 0x6c88c0,
end 0x6dffc0). A free block's first word links to the next free block.

| Function | Behaviour |
|---|---|
| `pool_init` 0x14fcd8 | zero the memory; thread each class in ascending address order, last link 0; terminator base = end of pool, terminator head = start of pool (non-zero, which is what stops the search) |
| `pool_new` 0x14fdb8 (size) | walk the classes in order; take the first whose block size is ≥ size (signed compare) **and** whose head is not null. If that is the terminator: call `mem_dumpHeap` 0x150290 once and return 0. Otherwise unlink the head block, zero-fill it over the class's whole block size, record its address in 0x4d8a24, return it |
| `pool_free` 0x150470 (ptr) | class = first i with ptr < base of class i+1 (unsigned); push on that class's list (`*ptr = head; head = ptr`). No other check |
| `pool_countFree` 0x150410 | sum of the three list lengths |

Consequences an implementation must reproduce to hand out the same addresses:

- First use is ascending; after that each list is last-in-first-out.
- A full class spills into the next larger one; the spilled block returns to the list of
  the class its *address* lies in.
- Size 0 and negative sizes are served from class 0; 3000 is served, 3001 is not.
- A request fails only when every class that is large enough is empty, even if smaller
  classes have room.
- Freeing a pointer below the pool files it under class 0; at or beyond the end the search
  runs off the table (the model refuses). Freeing twice makes the list circular.

Object addresses matter to lockstep only through what depends on them (O8 in
`docs/objects.md`: identities); the free *count* feeds the simulation directly (O1).

## 12. Handle lists

Node pool: **6,096** nodes of 20 bytes at 0x847268 (the free-list head 0x864ea8 sits
directly behind the array): +0 next, +4 prev, +8 partner, +0xc object, +0x10 a 16-bit
field cleared whenever a node is taken. `prev` points at the previous node or at the list
head cell; both begin with the `next` pointer, and that is all the code touches through
it. `handle_initPool` 0x1a17d0 threads the nodes in ascending order; the free list is
last-in-first-out. Fields of a freed node other than `next` keep their old values.

Primitive steps: *take* (pop the free head, clear +0x10), *release* (push on the free
list), *push(head, n)* (`n.next = head.next`; fix the old first node's prev; `n.prev =
head`; `head.next = n`), *unlink(n)* (`if n.prev: n.prev.next = n.next`; `if n.next:
n.next.prev = n.prev`).

| Function | Behaviour |
|---|---|
| `handle_link` 0x1a1738 (head, back, obj) → A | take A, take B (in that order); push A on head, B on back; A.obj = obj, B.obj = 0; partners of each other |
| *handle_linkBoth* 0x1a18f0 (headA, objB, headB, objA) | the same, but B carries objB. Returns nothing. Callers 0x10b930, 0x11715c, 0x11a8a8 |
| `handle_addNode` 0x1a1980 (head, obj) → n | one node, partner 0, pushed on head |
| `handle_insertNode` 0x1a19d0 (head, after, obj) → n | one node; behind `after` when given, else at the front |
| `handle_removeNode` 0x1a1868 (n) → obj | unlink n; if it has a partner, unlink and release the partner; release n (so n is reused first) |
| `handle_clear` 0x1a1698 (head) | for each node front to back: remember its successor, unlink it, unlink and release its partner, release it |
| `iter_begin` 0x1a1a48 (it, head, mask) | it.mask (+0x14) = mask; find the first wanted node from the front; stand behind it (below); it.obj (+0xc) = 0. No wanted node: it.next = it.prev = 0 |
| `iter_next` 0x1a1b38 (it) | find the next wanted node starting at it.next; unlink the iterator; stand behind the found node, or set next = prev = 0 |
| `iter_end` 0x1a1ae8 (it, flags) | unlink the iterator; flags bit 0 also frees its memory |

An iterator is a 24-byte record with a node's layout that is **spliced into the list**
directly behind the node it is on ("stand behind n": `it.prev = n; it.next = n.next; fix
the next node's prev; n.next = it`). A node is *wanted* when its object pointer is not
null and `object.flags & mask == 0` (flags = the word at object +0xc). The caller's loop is

```
iter_begin(it, head, mask)
while it.prev != 0:
    obj = it.prev->object
    ...
    iter_next(it)
iter_end(it, 2)
```

What an iterator sees when the list changes under it (each case run against the original
with the loop body making the change):

| Change made by the loop body | Effect |
|---|---|
| remove the current node, or destroy the current object (clear its three heads) | the walk continues with the node that followed; nothing is skipped or repeated |
| remove or destroy the node after the iterator, or any other | that node is simply not visited |
| link at the front of the list | not visited (it is behind the iterator) |
| insert directly after the current node | not visited either: it lands between the current node and the iterator, and becomes `it.prev` |
| start or advance a second iterator in the same list | both walks are complete and independent; iterators and partner-side nodes (object 0) are skipped. But while the second one stands behind the same node, the first one's `prev` is the *second iterator*, whose object field is 0: re-reading `it.prev->object` then yields null |
| after the current node was removed | `it.prev` is the node before it or the list head cell; do not re-read the object through it |

Undefined in the original (the model raises; none of these was seen in a caller):
`handle_clear` on a list an iterator stands in (the iterator would be freed as a node),
`handle_clear` on a list holding both nodes of one link (the walk continues through a freed
node into the free list: executed on a fresh pool, `handle_link(L, L, obj)` then
`handle_clear(L)` returns after 97,561 instructions with the free list reversed and its
last node pointing at itself; in a random sequence the same call did not return), `iter_next` after the
end (stores to address 0), any link when the pool is empty (stores through a null node;
3,048 links exhaust it).

## 13. What the differential test covers

`python3 tools/difftest_core.py` (seed 20973; `--quick` runs a tenth of the random
samples). Last full run: **114 properties, 114 PASS, 0 FAIL**, about 1.4 million
compared cases, 6 minutes.

Inputs: values of the size the game uses, arbitrary 32-bit patterns (about one input in
six, which exercise overflow, underflow, zero patterns and exponent-255 values), a list of
edge patterns, and ties (equal or equal-magnitude elements forced into about a quarter of
the vector and matrix cases). Every float function is run under the interpreter's default
floating-point model with the full sample and under five other settings (two other adder
models, round-to-nearest, biased multiplier, divide-to-nearest) with a tenth of it, the
model switched the same way.

| Group | Properties | What is compared | Float results |
|---|---|---|---|
| `fpu.primitives` | 1 | the model's arithmetic against the interpreter's, operation by operation | identical by construction of the test |
| `angle.cos16`, `angle.sin16` | 2 | **all 65,536 angles** (default model and one other in full, four more on every 37th), plus junk above bit 15 | bit for bit |
| `angle.atan2_16`, `turnDir`, `approach` | 3 | integer offsets on a 97×97 grid, world- and unit-sized and arbitrary pairs through the real `atan2f`/`atanf`; turn direction with and without output pointer; approach with random rate and limits | bit for bit |
| `math.*` | 64 | every function of sections 5 and 6 and five of section 8: up to 6,000 random cases each (a few dozen for the functions without inputs) plus the aliasing runs named in section 6 | bit for bit under all six settings |
| `edge.*` | 14 | inputs built to sit on, and one unit either side of, each constant a function compares with (pivot limit, 0.001, 0.01, ±0.25, hue sectors, clamp ends, `atanf` range limits, whole numbers for floor/ceil, exponent gaps of ±59…62 for `atan2f`) | bit for bit |
| `convert.idioms` | 1 | three inline conversions run as stretches (section 3) | bit for bit |
| `libm.*`, `code.constants` | 8 | `powf` (26,000 cases: game-like, shortcuts, negative and zero bases, huge exponents, overflow and underflow limits, branch-limit patterns), `fmodf`, `sqrtf`, `scalbnf`, `copysignf`; 28 table words, 24 + 25 code constants read back from the executable | bit for bit |
| `double.*` | 9 | add, subtract, multiply, divide, `fmod` (all pairs of 27 edge patterns + 20,000 random pairs each), compare, the four conversions, the float×literal idiom, 15 literals | exact (integer code: no dependence on the FPU model) |
| `noise.*` | 2 | every index of a period, negative and huge indexes, against a random table; the table builder for 40 seeds with zero and non-zero stale stack words | bit for bit |
| `rand.*` | 6 | 3,000 draws from each of 12 seeds for the object, spell and shared generators (value and state); seeding of objects and spells; the float helpers including the number of draws consumed; `libc_rand`/`srand` | exact / bit for bit |
| `pool.sequence` | 1 | 11,017 steps of allocation and freeing in five regimes (empty, filling, hovering at full, small requests only, draining), then exhaustion, oversized and negative sizes (5,827 allocations, 544 of them spilled into a larger class, 637 refused): returned address, zero fill of the whole block, list heads and `pool_countFree` after **every** step, whole free lists every 64th | exact |
| `handles.*` | 3 | pool initialisation and exhaustion (whole node array); 30,000 random operations on 10 lists and 28 objects with up to four iterators standing in the lists: return values, every list, the free-list head and every iterator after **every** step, the whole node array every 1,000th; 1,500 walks with the loop body changing the list in seven ways | exact |

How sensitive the test is was measured by changing the model in one place at a time (71
changes: every `<` to `<=` and back in the float functions, every hex constant by one
unit, and a handful of changes to the generators, pool and lists). After the edge cases above
were added, the survivors are: comparisons where equality cannot change the result
(`step < min` then `step = min`, clamps at 0 and 1, the library's "huge + x > 0"), the
exact-tie branches at `powf`'s overflow and underflow limits, and constants too small to
move any float result — which is why those constants are also read back from the
instructions (`code.constants`, `libm.immediates`, `libm.tables`).

Limits. (1) "Bit for bit" is relative to the interpreter (section 2, item 9). (2) A
function was tested on the inputs described; state that the game never produces (wild
patterns) is covered more thinly than game-sized values, by design. (3) Callers were not
examined: argument order at each call site, and which sites pass aliased buffers, are not
part of this work. (4) `powf` at exact equality with its overflow and underflow limits,
and `quat_fromMat3`'s `r == 0` branch (unreachable for finite input as far as I can see),
were not reached.

## 14. Corrections, proposed ledger rows, suggested names

Corrections to earlier documents:

| Where | Says | Found |
|---|---|---|
| `symbols/player.tsv`, `handle_validatePool` and `handle_initPool` notes | "6095 handle nodes" | 6,096: the loops run from 0x17cf down to 0 inclusive, and 0x847268 + 6096·20 = 0x864ea8, the free-list head. Executed: the free list after `handle_initPool` has 6,096 nodes |
| `docs/issues/float-divergence.md`, "The machine" | double arithmetic is integer code "so it cannot differ between machines" | true between originals; but that code truncates and has no denormals, so a rebuild using the host's `double` differs in about half of all results (section 9) |
| `docs/runtime.md`, "Below the range" (marked Inferred there) | 0x3aef58 float→double: "58 callers, mostly float arguments to `libc_sprintf`" | 58 calling functions is right, the use is not: of its 97 call sites 5 feed `libc_sprintf`; 40 are followed by a double comparison, 19 by a multiply, 14 by an add, 6 by `libm_fmod` — game logic such as `loot_generateDrops` 0x100dec and `Creature_setStats` 0x10a7bc |
| `docs/engine.md`, Math table | `math_cos16` "polynomial on the half angle" | correct; add that `sin16(0)` and the other quarter-turn values are ±2⁻²², not 0 |
| `docs/objects.md`, handle recap | "An iterator is itself a node spliced into the list (object field 0)" | correct; add the two cases of section 12 where `it.prev` is not a node carrying an object |

Proposed ledger rows (for `FINDINGS.md`; not edited by me):

| Id | Finding | Kind | Evidence |
|---|---|---|---|
| new | Software double arithmetic truncates and has no denormals; game code uses it for every `float * literal` expression written without an `f` suffix. A rebuild that uses host doubles computes different floats in about half of such expressions | Executed in isolation (routines); Observed (call sites) | 0x3af018 (no rounding step), 0x3af0f0; `double.*` properties |
| new | Float and double decimal literals were truncated by the compiler, in game code and in the C library alike | Observed, checked against 46 + 15 constants | `libm.tables`, `libm.immediates`, `double.constants` |
| new | `sin16`/`cos16` never return 0; the quarter-turn values are ±2⁻²² and `cos16(a) ≠ cos16(−a)` for 1,190 angles | Executed, all 65,536 angles | 0x166630, 0x1666e0 |
| new | `math_buildNoiseTable` reads three uninitialised stack words | Executed | 0x1646c8 (stores to sp+0 and sp+0x10 only) |
| new | `handle_clear` on a list that an iterator stands in, or that holds both nodes of one link, corrupts the node pool; no caller was checked for either | Observed; second case executed (free list left circular) | 0x1a1698 |

No patch is proposed.

Suggested names for addresses nobody has named (not added to any symbol file):

| Address | Name | Basis |
|---|---|---|
| 0x162440 | `vec3_hermiteDerivative` | executed; no caller |
| 0x162df0, 0x162b68, 0x163208 | `mat3_rotateAxisPost`, `mat34_rotateAxisPost`, `mat4_rotateAxis` | executed |
| 0x163658, 0x163790 | `ray_planeDistance`, `segment_hitsPlaneNearEdge` | executed; the names describe the arithmetic, the callers were not read |
| 0x164578 | `math_noise3` | executed; no caller |
| 0x164f10 | `color_fromHSV` | executed |
| 0x1659d0, 0x165a70 | `mat4_setProjectionFixed` (two identical copies) | executed |
| 0x165fc0 | `mat4_transformPointTransposed` | executed |
| 0x166340, 0x166a68 | `mat4_fromMat3Pos`, `mat4_fromQuat` | executed; no caller |
| 0x166d40, 0x166dc0, 0x166e38 | `bbox_addPoint`, `bbox_containsPoint`, `bbox_overlaps` | executed; no caller |
| 0x1a18f0 | `handle_linkBoth` | executed |
| 0x3c7f30, 0x3c7f60, 0x3c8030 | `GameObject_randUnit`, `GameObject_randInUnitSphere` (two calling conventions) | executed |
| 0x3a84c0, 0x3aa920 | `libm_sqrtf`, `libm_copysignf` | executed |
| 0x3af410, 0x3af468, 0x3af4d0, 0x3af758, 0x3af9b8 | `softdouble_add`, `_sub`, `_mul`, `_div`, `_compare` | executed |
| 0x3aef58, 0x3afb90, 0x3afa08, 0x3afac0 | `softdouble_fromFloat`, `_toFloat`, `_fromInt`, `_toInt` | executed |
| 0x3af018, 0x3af0f0, 0x3af1b0 | `softdouble_pack`, `_unpack`, `_addParts` | Observed |

## 15. Not done

- The remaining C-library entry points game code calls: 0x3a51b0 (callers 0x168fdc,
  0x1cbd64, 0x1cc93c), 0x3a53c0 (0x168f74), 0x3a55d8 (0x1c395c, 0x1c7034, 0x1d23c4),
  0x3a58c0 (0x2256c0), 0x3a59a8 (0x1861f4), 0x3a5a20 and 0x3a5a50 (0x20cfcc, 0x20d060),
  0x3a5a68 (0x209d34, 0x20cd34), 0x3a5a98 (0x1d18c0). Not identified beyond their shape.
- 0x164898 and 0x164a48 (box transforms, no caller), 0x165410–0x165424 (two fragments),
  the unsigned double conversions (0x3afbe8 and neighbours) and the 64-bit integer
  helpers at 0x3aa960.
- The rigid-body block 0x167008–0x1685ef and the VU0 pose program: not part of this model.
- `max.s` / `min.s` are in the model as the interpreter implements them; no function
  modelled here uses them, so they were compared with the interpreter only.
- Which floating-point variant a console implements (section 2, item 9).
