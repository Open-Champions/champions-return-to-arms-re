# Soul_run, every state, and Creature_setCharm

US `SLUS_209.73` v2.00. Prose of `tools/ref_soul_run.py`; the comparison is
`tools/difftest_soul_run.py`, the synthetic tests `tools/test_ref_soul_run.py`. Written
2026-10-21.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
on a soul its own constructor built (game virtual table, creature base real underneath,
`Soul_setState`, `Soul_getModel`, `Soul_isDemonNear`, `Creature_setCharm`, the type-info
getters and the C library real), and the model agreed on the calls to everything outside
the models (in order, with arguments), every byte stored outside the stack, the shared seed
`0x404464` with its draw count, and the result. **Observed**: read at the address.
**Inferred** and **Unknown** as usual. Nothing here ran on a console, in PCSX2 or on the
live rig.

## 1. What was executed before this

- `docs/spec/combat-ctors.md`: the constructor, set-state and the run up to its switch,
  with the switch's range test patched out in the interpreter. `Creature_setCharm` was a
  recording stub there.
- `docs/spec/combat-round5.md` §1.3: only the demon check of states 0 and 0x18, and
  `Soul_isDemonNear` (58 of 58) with its type test as call-outs.
- `docs/spec/combat-ctors-2.md`: `Soul_takeDamage` and the destructor.
- `docs/spec/skills-35-68.md` §39: `Creature_setCharm` read, not run (*Observed*). The native
  client ported that prose.

This round removes the patch for the Soul: the original runs the whole function, every
state, with `Creature_setCharm` real inside the constructor.

## 2. How it was run, figures and coverage

The rig is `tools/difftest_combat_ctors2.py`'s world for the Soul class: the game's own
tables of Demon `0x514b40`, Player, Skelight, Skeleton, Soul and AntQueen, and synthetic
type descriptors. The other actors get these tables at random, live or dead (flag 8). Also
real here: the matrix helpers `mat34_setPosRotZScale` `0x163cb8`, `mat34_rotateAxis`
`0x163000`, `mat34_transformPoint` `0x1660a0`, `mat34_invert` `0x164288` (with
`mat4_invert` `0x163f98`) and `mat34_mul` `0x162808`. These are `tools/ref_core.py` bodies,
executed by `tools/difftest_core.py` and borrowed unchanged.

These are callbacks: recording stubs answered by the scripted world.

- `world_collectObjectsInBox`, `model_getSamplePointCount` (counts 0, 1, 2, 3, 5 and −2),
  `model_getSamplePoint`, `particle_spawn`, `terrain_height`;
- `damage_apply`, `obj_delete`, `obj_stopRunning`;
- `creature_getAttachMatrix0`, `model_getAttachMatrix` (each writes 12 floats through its
  out pointer);
- `handle_clear` and the anim calls.

The driver varies these between ticks:

- the state: all 35, plus out-of-range numbers;
- `+0xf4` near the clock;
- the frame, on and off the demon nibble;
- the owner handle `+0x3c8` and the thrown target `+0x3cc` (with its `+0x308`/`+0x30c`);
- clip flags 0x10 and 0x80, the inert byte `+0x231`, object flag 2;
- players placed at the thrown soul's contact point;
- `g_numPlayers` from 0 to 4;
- the wander destination and the scale `+0xdc`.

`Creature_setCharm` is also entered directly. Each time the driver sets object flags
(0x20, 0x40, 0x60, 0 …), `+0x312` (0, 7, −1, 0x8000) and the target handle, and passes
frames and teams of every width.

    python3 -u tools/difftest_soul_run.py -v              # seed 20973
    python3 -u tools/difftest_soul_run.py -v --seed 7
    python3 -m unittest tools.test_ref_soul_run

Each seed is four runs of 3,000 ticks (machines A and B, seed and seed + 1).

| | Seed 20973 | Seed 7 |
|---|---|---|
| `Soul_run` | 11,984 | 11,986 |
| `Soul_setState` | 3,080 | 3,022 |
| `Soul_ctor` | 410 | 388 |
| `Creature_setCharm` (direct) | 602 | 651 |
| All calls compared | 16,076 | 16,047 |
| Mismatches (calls, writes, seed, result, faults) | 0 | 0 |

Every state 0–0x22 was entered at least 31 times on each seed, and 0x1b, 0x1d, 0x14 and
0x22 several hundred times each.

| Function | Address | Seed 20973 | Seed 7 |
|---|---|---|---|
| `Soul_run` | `0x2a9870` (to `0x2aa908`) | 1061 of 1062 | 1061 of 1062 |
| `Soul_isDemonNear` | `0x2ab2b4` | 58 of 58 | 58 of 58 |
| `Creature_setCharm` | `0x1189f0` | 25 of 25 | 25 of 25 |
| `Soul_setState` (underneath) | `0x2aac38` | 385 of 408 | 385 of 408 |

Two blocks are never entered:

- `Soul_run`: `0x2a98f4` is dead by reading. It is the delay slot of the branch taken when
  `Creature_run` returns non-zero, and `Creature_run` always returns 0
  (`tools/ref_creature.py`).
- `Soul_setState`: the remaining instructions are its owner branch of 0x21 (`0x2ab0d4`–) and
  two short paths. Those are `combat-ctors.md`'s business; an owned soul never reaches 0x21
  through this rig.

**Checks.** Each of these model changes was detected (`--quick`, 1,200 runs):

- the contact distance 36 → 40: 1 mismatching call;
- the thrown vertical limit −60 → −80: 42;
- the demon nibble `& 0xf` → `& 7`: 4;
- `Creature_setCharm` charming a player (object flag 0x40): 7 of 54.

## 3. The tick

Notation:

- `c` the soul; `clock` the creature clock `+0x300`.
- `expired(o)`: the signed word at `o` is strictly below the signed clock.
- `st(n)`: slot 27 (`Soul_setState`).
- `due`: `(g_simFrame 0x44fdcc XOR s8 +0x230) & 0xf == 0`. The byte is read signed and only
  its nibble counts.
- `demon`: `Soul_isDemonNear(c)`.
- `ev`: the event bits `Creature_stepAnim` returns.
- `n`: `s32 model_getSamplePointCount(slot 16)`. Slot 16 is `Soul_getModel` (class block
  `+0x1c` while owned, else `+0xc`).
- `SP(pos, facing, i)`: `model_getSamplePoint(slot-16 model, c+0x114, pos, facing, i, out,
  second out, 0; scale +0xdc)`. Slot 16 is called again before each one.
- `ball`: a unit-ball vector by **own** draws. Each try is three draws of
  `2·(d·2⁻¹⁶) − 1`, made again while `(x² + y²) + z² > 1`.
- `P(point, v)`: `particle_spawn(0x8e4600, point, (x·15, y·15, 0·15); 0.0)`. The copy's z word
  is zeroed before the multiply, so every Soul particle is flat.

**Prologue** (unchanged from `combat-ctors.md`):

1. `Creature_processDamage` and `Creature_run` with the slot-16 model. A non-zero
   `Creature_run` returns, but it never is non-zero.
2. `Creature_updateActive`; 0 returns.
3. `ev = Creature_stepAnim(c; 1.0)`.
4. `Creature_applyKnockback(c; 0.0)`, then slot 23.
5. When `+0x3c8` is 0 and the state is not 0x1b, `Creature_moveBy(c, (0, 0, 0))`.

The state is the s16 at `+0x232`, read again after that move. It is compared UNSIGNED with
0x23 (`0x2a997c`), so negative numbers and 0x23 and up return. The jump table is the 35 words
at `0x54c2c0`.

| State | Reads | Writes | Calls (in order) and draws |
|---|---|---|---|
| 0 | `+0x230`, `g_simFrame`, `+0xf4`, `+0x300`, home `+0x3b4`–`+0x3c0` (through the callee) | — | due → `demon` → `st(0x18)`; `expired(+0xf4)` → `st(1)`; else `Creature_isAwayFromHome(c)` → `st(1)` |
| 1 | as 0, `+0x104`–`+0x10c` | as `Creature_moveTo` | due → `demon` → `st(0x18)`; `Creature_moveTo(c, copy of +0x104)` arrived → `st(0)`; else `expired(+0xf4)` → `st(0)` |
| 3 | `+0x234` | — | no target → `st(0)` |
| 5 | `+0x314` | — | `Creature_isNotRooted` → `st(0)` |
| 0x12, 0x19 | `+0x11a` | — | clip flag 0x10 clear → `st(0x18)` |
| 0x14, 0x22 | `+0xc`, `+0x10`–`+0x18`, `+0x38`, `+0xdc`, `+0x231`, `+0xf4`, `+0x300`, `+0x11a`, `+0x232` | `+0xc`, `+0x44` | dissolve (§3.1) |
| 0x17 | `+0xf4`, `+0x300` | — | `expired(+0xf4)` → `st(1)` |
| 0x18 | `+0x230`, `g_simFrame` | — | due and not `demon` → `st(0)` (not due: nothing) |
| 0x1b | see §3.2 | `+0x10`–`+0x18`, `+0xb0`, `+0x44`, and slot 26's fields | thrown (§3.2) |
| 0x1d | `ev`, `+0x3c8`, `+0x24` → `+0x1c`, `+0xdc`, `+0xc` | `+0xc`, `+0x44` | owned burst (§3.3) |
| 2, 4, 6–0x11, 0x13, 0x15, 0x16, 0x1a, 0x1c, 0x1e–0x21 | — | — | nothing |

`Soul_isDemonNear` (*Executed*, now with the real type-info getters):

1. `world_collectObjectsInBox(position ± 300 on each axis, capacity 128)`.
2. For each entry: its slot 0 (the getter; `a0` is not the object) and `Demon_typeinfo`
   `0x3ca81c`, then `rtti_typeInfoEquals`.
3. The first exact Demon with flag 8 clear gives 1.

No draw.

### 3.1 Dissolve: states 0x14 (dead) and 0x22 (airhub), `0x2a9b34`–`0x2a9ed8`

1. Object flag 2 set (`0x2a9b38`): nothing at all.
2. When `n` ≠ 0 (this includes a negative `n`), make **three** particles (limit 3 at
   `0x2a9ce8`). Each one:
   - **one own draw** `d`;
   - the index `d % n`, a signed remainder (`div`/`mfhi` at `0x2a9b98`);
   - `SP(copy of +0x10, s16 facing +0x38, index)`;
   - `ball`;
   - `P` only while the byte `+0x231` is 0 (`0x2a9ca4`/`0x2a9cc4`). The draws are made
     either way.
3. Unless `expired(+0xf4)` or clip flag 0x80 (`0x2a9d0c`) is set, return.
4. For every `i < n` (none when `n` ≤ 0): `SP(copy of the position, s16 facing, i)`, then
   **two** particles, each `ball` and `P` under the same `+0x231` test (count down from 1 at
   `0x2a9e80`).
5. The ending depends on the state (compared with 0x14 at `0x2a9ea0`):
   - 0x14: `+0xc |= 2`, then `obj_delete(c)`.
   - 0x22: `+0xc` = (the word before) `| 0xb` (`0x2a9ec4`), then `obj_stopRunning(c)`
     `0x14f290`.

Own draws: 3 + 3·(tries) per frame, and 6·(tries) per sample point at the end. No shared
draw.

### 3.2 Thrown: state 0x1b, `0x2a9edc`–`0x2aa6a0`

1. The throw matrix
   `m = mat34_setPosRotZScale(+0xdc, copy of the position, s16(u16 facing + 0x5f40))`
   (`0x2a9f14`), then `mat34_rotateAxis(m, 0, 0x4fa0)` (X axis, `0x2a9f4c`/`0x2a9f54`).
2. When `n` ≠ 0, make **three** trail particles (`0x2aa0d8`). Each one:
   - **one own draw** `d`;
   - `SP((0, 0, 0), −0x4000, d % n)` (`0x2a9fb0`);
   - `mat34_transformPoint(m, point)`;
   - `ball` and `P`. There is **no** `+0x231` test here.
3. Velocity, with no handle `+0x3cc`: `(cos16 f · 400, sin16 f · 400, −80)`. Here `f` is the
   s16 facing; 400 is `0x43c80000` (`0x2aa284`), −80 is `0xc2a00000` (`0x2aa2a8`).
4. Velocity, with a handle (its object `T`):
   1. The aim point: `T`'s position, with x + `T+0x308`·0.2 and y + `T+0x30c`·0.2. z is
      unchanged. 0.2 is `0x3e4ccccc` (`0x2aa0f8`).
   2. `+0xb0` = 0.4 (`0x3ecccccc`, stored at `0x2aa164`).
   3. Slot 26 (`Creature_turnToward`) `(0, aim point)`.
   4. `T` is read again through the handle. `D = T.position − c.position` is scaled by
      `rsqrt.s(1.0, D·D)` (`0x2aa208`).
   5. The velocity is `(cos16 f' · 400, sin16 f' · 400, Dz · 400)`, with `f'` the facing
      after the turn. When −60 < z, z = −60 (`0xc2700000`, `0x2aa248`). The x and y of the
      normalised `D` are computed and then overwritten.
5. Four sub-steps (counter 3 down to 0, `0x2aa2b8`/`0x2aa494`). In each:
   1. Position += velocity · `0x3b888888` (1/240, `0x2aa2cc`), stored y, z, x.
   2. For each player slot `j` below `g_numPlayers` `0x4d8ae0` (read again every pass): the
      object is the word at `0x4dcec8 + 0x4c30·j`, skipped when 0 or when flag 8 is set
      (`0x2aa350`).
   3. The player's centre is its position with z + `+0x20`·0.5.
   4. The contact point is `(c.x + cos16 f · 36, c.y + sin16 f · 36, c.z)` (36 =
      `0x42100000` at `0x2aa384`).
   5. When `sqrt(dx² + dy² + dz²) ≤ c+0x1c + player+0x1c` (`sqrt.s` `0x2aa420`, `c.ole.s`
      `0x2aa424`): `damage_apply(player, c, 100000, 0, 0, 0x4000140, 0, 0; 10.0, 50.0)`
      (`0x2aa43c`–`0x2aa464`). That is a hit, and no further player is tested in this
      sub-step. The sub-steps go on.
6. After the four:
   - With no hit and `+0xf4` not expired: `h = terrain_height(g_world 0x44fdc8, copy of the
     position; 6.0)` (`0x40c00000`, `0x2aa4dc`). When the soul's z is not strictly below
     `h`, return (it flies on).
   - Otherwise (a hit, the timer expired, or below ground): `obj_delete(c)`. Then, for every
     `i < n`: `SP((0, 0, 0), −0x4000, i)` through the **old** `m` (built before the move),
     and **two** particles (`ball`, `P`, no `+0x231` test).

Reads: `+0x10`–`+0x1c`, `+0x38`, `+0xdc`, `+0x3cc` → `T+0x10`–`+0x18`, `T+0x308`,
`T+0x30c`, `+0xf4`, `+0x300`, `g_numPlayers` and the player records (`+0xc`, `+0x10`–`+0x20`,
`+0x1c`). Writes: the position, `+0xb0`, `+0x44`, and what slot 26 writes.

Draws: own draws only, 3 + 3·(tries) for the trail and 6·(tries) per sample point at the
end. Shared draws come only from `damage_apply` (round-1 contract).

### 3.3 The owned burst: state 0x1d, `0x2aa6a4`–`0x2aa8cc`

1. Only on `ev & 1` (`0x2aa6a4`).
2. For every `i < n`:
   1. `SP((0, 0, 0), −0x4000, i)`.
   2. While owned (`+0x3c8`), the point is carried to the owner:
      - `A = creature_getAttachMatrix0(owner object)` `0x287940`;
      - `B = model_getAttachMatrix(class block +0x1c model, c+0x114, 0; 1.0)` `0x1795f8`;
      - `B = mat34_invert(B)`, then `A = mat34_mul(B, A)`;
      - `point = mat34_transformPoint(A, point)`.
   3. Then **two** particles (no `+0x231` test).
3. `+0xc |= 2` and `obj_delete(c)`, even when `n` ≤ 0.

Own draws: 6·(tries) per sample point.

### Constants (Observed)

| Value | Use | Address |
|---|---|---|
| 0x23 | state count (unsigned) | `0x2a997c` |
| `0x54c2c0` | jump table, 35 words | `0x2a998c`/`0x2a9994` |
| 0x1b | no zero move in the thrown state | `0x2a9954` |
| 0xf | demon nibble | `0x2a99d0`, `0x2a9a2c`, `0x2a9a64` |
| 0x10, 0x80, 2 | clip flags of 0x12/0x19 and of the dissolve end; object flag 2 | `0x2a9b04`, `0x2a9d0c`, `0x2a9b38` |
| 3, 2 | particle counts | `0x2a9ce8`, `0x2aa0d8`; `0x2a9e80`, `0x2aa680`, `0x2aa8a0` |
| `0x8e4600` | particle definition | `0x2a9ccc`, `0x2a9e6c`, `0x2aa090`, `0x2aa63c`, `0x2aa85c` |
| 2⁻¹⁶ `0x37800000`, 15 `0x41700000` | ball draws, particle speed | `0x2a9be4`…, `0x2a9c7c`… |
| 0x5f40, 0x4fa0 | throw matrix roll and X pitch | `0x2a9f14`, `0x2a9f54` |
| −0x4000 | sample-point facing (0x1b, 0x1d) | `0x2a9fb0`, `0x2aa554`, `0x2aa718` |
| 0.2, 0.4 | aim lead, turn rate | `0x2aa0f8`, `0x2aa124` |
| 400, −60, −80 | thrown speed and vertical limits | `0x2aa23c`/`0x2aa284`, `0x2aa248`, `0x2aa2a8` |
| 1/240 `0x3b888888` | sub-step | `0x2aa2cc` |
| `0x4d8ae0`, `0x4dcec8`, 0x4c30 | `g_numPlayers`, player objects, stride | `0x2aa320`, `0x2aa338`+8, `0x2aa32c` |
| 0.5, 36 | player centre height, contact reach | `0x2aa360`, `0x2aa384` |
| 10.0, 50.0, 100000, 0x4000140 | `damage_apply` | `0x2aa43c`, `0x2aa448`, `0x2aa444`, `0x2aa450` |
| 6.0 | `terrain_height` radius | `0x2aa4dc` |
| 1.0 | `model_getAttachMatrix` scale | `0x2aa758` |

## 4. Creature_setCharm `0x1189f0` (creature, frames, team)

*Executed*, 25 of 25:

1. Nothing when `s16 +0x312` is −1 (`0x118a08`).
2. Nothing when object flag 0x20 (a monster) is clear (`0x118a1c`).
3. Nothing when object flag 0x40 (a player) is set (`0x118a24`).
4. Otherwise, in this order:
   - `+0x310` = the low byte of team (`sb`, `0x118a2c`);
   - `+0x312` = the low halfword of frames (`sh`, `0x118a34`);
   - `handle_clear(+0x234)`;
   - `+0x234` = 0 (`0x118a40`).

No draw. No other read.

Inside `Soul_ctor` (`frames` −1, team 0), `Creature_ctor` has just set flag 0x20 and zeroed
`+0x312`, so the charm always takes. In all 95 constructions of a 3,000-tick run, the soul
came out with `+0x312` = 0xffff, team 0 and no target. *Inferred*: a soul can never be
charmed again (step 1).

## 5. Corrections

- `docs/monsters-2.md`, Soul, states 0x14/0x22:
  - "up to 3 particles" is **exactly three** when the count is non-zero, a negative count
    included (`d % n` is signed).
  - The particles are suppressed, but the draws are not, while the byte `+0x231` is set.
  - The sample points are taken at the soul's position and s16 facing, with the scale
    `+0xdc`.
  - The whole arm does nothing once object flag 2 is set.
- `docs/monsters-2.md`, 0x1b:
  - "up to 3 trail particles" is **exactly three** when the count is non-zero.
  - Trail and end particles are moved by the throw matrix (`setPosRotZScale(+0xdc, position,
    facing + 0x5f40)`, then X by 0x4fa0). The end particles use the matrix of the position
    BEFORE the frame's move.
  - There is no `+0x231` test.
  - "not below `terrain_height`" is `terrain_height(…; 6.0)` not strictly above z.
- `docs/monsters-2.md`, 0x1d: "through the owner's attach matrix 0x287940" is through
  `inverse(model_getAttachMatrix(held model, anim, 0; 1.0)) · creature_getAttachMatrix0(owner)`.
  Without an owner the point is used as it is. Object flag 2 is set and the soul deleted
  even with no sample points.
- `docs/spec/skills-35-68.md` §39, `Creature_setCharm`: "lacks the creature flag" is object
  flag 0x20 at `+0xc`, and "is a player" is object flag 0x40. Team and frames are stored as
  a byte and a halfword. The target handle is `handle_clear`ed and then zeroed.
- `docs/spec/combat-ctors.md` §6 records `Creature_setCharm(−1, team 0)` as a call; it was a
  recording stub there and runs for real now, with the effect of §4. §8's "Soul's switch is
  not executed" is superseded by §3 here.
- `docs/spec/full-placement.md` §3.1: the Soul's stops at `Creature_setCharm` and at
  `Soul_run` states 0 and 1 are executed bodies now.

## 6. Still not executed

Callees `Soul_run` reaches that are recording stubs here and are not executed anywhere:

- `obj_stopRunning` `0x14f290`: state 0x22, airhub only.
- (`creature_getAttachMatrix0` `0x287940` and `model_getAttachMatrix` `0x1795f8`, state 0x1d
  while owned, are executed since 2026-10-21: `docs/spec/attach-matrix.md`.)
- `model_getSamplePointCount` `0x1799c8`, `model_getSamplePoint` `0x178e18`,
  `particle_spawn` `0x18f3f8`, `terrain_height` `0x183820`, `obj_delete` `0x14f200`: the
  probe treats these as services.

Executed elsewhere and stubbed here: `damage_apply` (`tools/difftest_combat.py`) and
`handle_clear` (`tools/ref_skills_b.py`).

Not established:

- What `Soul_setState`'s owner branch of 0x21 does on a real owned soul.
- Whether `+0x231` (inert) is ever set on a Soul in play: Unknown.
