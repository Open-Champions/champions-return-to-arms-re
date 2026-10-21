# Combat movement: the mover, the player's walk, and how they compose

US `SLUS_209.73` v2.00. Round 2 of the combat contract (`docs/combat-runtime.md`), target 1:
movement and collision for several live actors in one world. It is the prose of
`tools/ref_combat_move.py`; the bodies were run against the original by
`tools/difftest_combat_move.py`.

Evidence labels as in `docs/combat-runtime.md`: **Executed** = the original instructions ran
one function at a time in `tools/ee_emu.py` (an instruction interpreter, not a console) on
constructed state and agreed with the model (calls with arguments, every byte stored outside
the stack, the shared seed, the result); the entry point of the difftest is named.
**Observed** = read at the address given. **Inferred**. **Unknown**. **Authored** = a choice of
this contract (a fixture, a refusal), not a statement about the game. Nothing here was run on
a console, in PCSX2 or on the live rig.

## 1. What a rebuild needs, in brief

1. Players and plain objects move only through `obj_moveWithCollision` 0x14d4b8 (via
   `creature_moveSimple` 0x1186d8 for the player); monsters through `Creature_moveBy`
   0x113c48. An object only ever moves itself; the touch calls of a move run inside the
   mover's own run (`docs/combat-runtime.md` 4, 5). *Executed* (this document, 2;
   `docs/spec/creature-tick.md` 8 for `Creature_moveBy`).
2. **Touch order of `obj_moveWithCollision`**: for each object of one box query, in the
   query's order, with no early exit: the other object's slot 6 with the mover, then the
   mover's own slot 6 with the other. The other's call is skipped when the **mover** is the
   prediction copy (flag 0x20000, test at 0x14d9ac); the mover's own call never is.
   *Executed* (`moveWithCollision`, 3,000 cases).
3. A player moves **along its facing**, never along the stick; the facing turns toward the
   stick 40 % of the remaining angle per tick in mode 0. Speed 180 × s units per second,
   s = stick length × speed scale (at most the scale: 0.861945 offline, 0.75 in a net game,
   × record +0x4c20 × `g_runSpeed`, capped at 1.2). *Executed* (`playerMove`, 3,000 cases),
   agreeing with `docs/spec/movement-camera.md` 4.1.
4. Every `Player_move` call makes the call-outs `dialog_isOpen`, `net_getCamYaw` (once, plus
   two more when it turns and one more in mode 0) and, last, `net_getCamFlag`, whatever the
   mode; entering water draws the **shared seed** once. *Executed*.
5. The root motion of the player's animation (+0xbc, +0xc0) is overwritten by every
   `anim_advance` inside `Player_animStep`, rotated into world axes there, added to the
   velocity once as `root × 60` in `Player_move` and then zeroed. *Executed*
   (`playerAnimStep`, `playerMove`).

## 2. `obj_moveWithCollision(obj, vel, ignore, skipCreatures)` 0x14d4b8 → bits

*Executed* (`moveWithCollision`: 3,000 cases, 0 mismatches, 399 of 404 instructions; the five
not run are two `nop`s, a delay-slot-only path at 0x14d67c/0x14d6ac and the epilogue's
padding). Bits: 1 slid on terrain, 2 pushed out of an object, 4 landed.

```
d = vel × DT (each component; DT = 0x3c888888)
if 0.001 < (d.x² + d.y²) + d.z²:
    mask = 3 if flag 0x20 else 1;  if flag 0x40: mask = (mask | 4) & 5
    bits = world_slideMove(&pos, d, mask, no normal; radius) ? 1 : 0
    relink the grid node (inline copy of obj_updateGridCell, 0x14d5b8-0x14d6a8)
list = world_collectObjectsInBox(pos - (r, r, 1000), pos + (r, r, 1000), limit 0x40)
top = z + height;  stand = -100000
for o in list (no break):
    skip: o flag 1; o == obj; o == ignore; skipCreatures and o flag 0x20
    dx, dy = obj.xy - o.xy  (current positions, after earlier push-outs)
    skip unless sqrt(dx² + dy²) + 0.001 < r + o.r
    if (o.flags | obj.flags) & 0x10:
        skip if top < o.z + 3.0;  skip if o.z + o.height < obj.z
        if (o.z + o.height) - obj.z < 5.0:
            o 0x200 or mover 0x400: touch only (no push)
            else: stand = max(stand, o top); skip (no touch)
    unless touch only, o 0x200, mover 0x400 or |dist| <= 0.001:
        k = ((r + o.r) - dist) / dist
        world_slideMove(&pos, (dx × k, dy × k, 0), mask 1, no normal; r); relink; bits |= 2
    unless the MOVER has 0x20000: o.slot6(o, obj)
    obj.slot6(obj, o)
    r = obj.radius (re-read after the touches)
ground = max(terrain_heightBelow(g_world, pos; r), stand)
vz = obj+0x30 - 0x410fffff (8.999999);  z += vz × DT
if z - 0.01 <= ground:  z = ground;  if vz < 0: vz = 0, bits |= 4
```

- **The grid relink is inline** (twice: after the move and after each push-out). It is the
  same sequence of loads and stores as `obj_updateGridCell` 0x14f028 (*Observed*, the three
  bodies compared): the grid node is the partner (+8) of the first node of head +8; it is
  unlinked and pushed at the **front** of the list of the cell `(int(x) + 0x3c00) >> 8`,
  `(int(y) + 0x3c00) >> 8` (column tested unsigned, row signed, 120 × 120), in grid B
  0x5e95f0 for flag 0x800 else grid A 0x5db4f0, or the off-grid list 0x5f76f0. *Executed*
  on real list words: the difftest gives every object of its world a node in its cell.
- The slot-6 calls go through the table's adjustment halfword (`this = o + s16(table[6])`).
- Stand-on never touches: an object one can stand on (flag 0x10, top within 5 of the
  mover's feet) is not reported to either side unless it has 0x200 or the mover 0x400.

`creature_moveSimple(obj, vel)` 0x1186d8 copies `vel` and calls
`obj_moveWithCollision(obj, copy, 0, 0)`. *Executed* (`moveSimple`: 3,000 cases with the mover
running for real, 15 of 16 instructions).

## 3. `Player_move(P, mode, pad, vec)` 0x1b4020 → event bits

*Executed* (`playerMove`: 3,000 cases with every mode 0..7, a moving and a still stick, in and
out of water, the swing window, slow, the screen clamp, landing; 0 mismatches, 1,204 of 1,220
instructions; the 16 not run are `nop`s and one dead delay slot, 0x1b4930, that executes only
when neither `0.6 <= s` nor `s < 0.6` holds). `playerMoveStill` (3,000 cases, 0 mismatches)
is the round-1 domain alone: a still stick, mode 0 in state 2 and modes 3/4 in state 1.
The steps, in the order the code runs them (`docs/spec/movement-camera.md` 4.1 has the same
letters; what is new or sharper here is marked **new**):

- (a) +0x481 non-zero: decrement it and zero the pad's stick (+0x14, +0x18). Then
  `dialog_isOpen()` **on every call**; open: zero the stick.
- (b) speed scale S (movement-camera 4.1(b); the level-name test is `strcmp` with the string
  at 0x537678; record +0x4c20 is skipped for slot −1); the Drowsy factor through
  `SpellDrowsy_typeinfo`, `creature_findSpellByType`, `SpellDrowsy_getStat3Fraction` when
  +0x31a > 0.
- (c) `s = S × sqrt(lx² + ly²)`, capped at S; `T = s16(atan2_16(lx, ly) − net_getCamYaw(slot)
  − 0x41c2)` — the yaw call is made **every time**, before any test (**new**).
- (d) mode ≠ 5 and 0.01 < s: turn by `angle_approach(rate, −1, −1, F, T)` with rate 0.2
  (mode 1; in action state 8 first track 5's time +0x1d4 advances by
  `min(f32(|T − F|) × 0x393ea672, 1) × 0x3f7fffff`), none (mode 3), 0x3d5266e5 (4),
  s × 0x3da3d70a (6), s × 0x3d0f5c28 when the word 0x4d8a28 is non-zero, else
  `SpellCharge_typeinfo` + `creature_findSpellByType` (**made in mode 0 too, every turning
  tick**, **new**) and `SpellCharge_getStat3Scaled(spell)` in mode 2 with a rush spell, else
  0.4. Modes 7 and above take the mode-0 rate. Then `cs = sin16(F + yaw + 0x4000) × s`,
  `cc = cos16(F + yaw + 0x4000) × s`, each with its own `net_getCamYaw` call and the new F.
- (e) mode 2 or action state 1: `s = 1.0` — so mode 0 in state 1 runs the locomotion blend at
  full rate (**new**: round 1 left it out).
- (f) water, creature flag bit 61 (+0xa8):
  - in water: level flag 0x1000 and `frame & 0xf == 0`: `damage_apply(P, P, 100000000, 0, 0,
    0x1000030, 0, 0; 1e8, 1e8)`; `water_disturb(g_world, (x, y, z − 12); 300, 12)` every
    tick while s ≥ 0.01, else on `frame & 0xf == 0`; the bit is cleared when it returns 0.
  - out of water, on `frame & 3 == 0`: `water_test(g_world, copy of pos, &height; 12)`; a hit:
    **one shared draw** (inline, 0x1b461c-0x1b4654), the bit set, the name
    `sprintf(<format at 0x537688>, 1)`, `res_find(<lump name at 0x535ef0>, name)`,
    `sound_playOnObject(entry, P; 1.0)` and `water_disturb(...; 3000, 24)` and the splash
    burst `fx_burst_1fbdf0((x, y, height); 1.0)` when airborne (+0x47c), else volume 0.4 and
    `water_disturb(...; 1000, 24)`. *Executed* (174 shared draws in the 3,000 cases).
- (g) mode 0: the locomotion blend (movement-camera 4.1(g); `docs/spec/player-animation-
  dispatch.md` 3.2 on t3/research-anim), with two details pinned by execution:
  - the track weights `float((double(w) × (double(s) − knee)) × 3.0)` keep the **sign of a
    zero**: with the blend weight w = 0 and s below the knee the stored pattern is
    0x80000000 (−0.0), not 0 (**new**; a standing player whose weight has decayed stores
    −0.0 in +0x164, +0x16c, +0x184, +0x18c every tick);
  - `V = A × (cc × −180) + B × (cs × 180)` with the camera yaw round trip, all three
    components (V.z = 0·p + 0·q), × 1.25 when +0x47e and +0x47c; +0x4bc, +0x4c0 = V.x, V.y.
- (h) modes 1, 4, 6: V = 0 and +0x46c, the six track fields zeroed; mode 2:
  `(cos16 F × 300, sin16 F × 300, 0)`; mode 5: `*vec`; mode 3 and 7+: 0. Modes 2, 3, 5 and 7+
  neither step the animation nor touch +0x46c or the cells (*Executed*; this settles the
  open row "modes 2/3/5 and cells 1-3" of `player-animation-dispatch.md` 6).
- (i) +0x44c ≠ 2: byte +0x490 = 0. Then **only in action state 1** (the test at 0x1b4c48
  skips both parts otherwise; **new**, movement-camera 4.1(i) reads as if the second part
  were general): the swing window by weapon class zeroes V.x, V.y; and a heavy attack
  (+0x44c = 2) with `+0x490 & 3` zeroes them too.
- (j) slow (1 ≤ +0x2fc ≤ 60): V × `f32(60 − slow) × DT`, all three components.
- (k) `g_aliveCount` 0x4f8420 ≥ 2 and offline: `Player_clampToScreen(P, &V, &mask)` (4). The
  original tests the alive count only (**new**: round 1 also required `g_numPlayers` ≥ 2).
- (l) `goal = (x + V.x × DT, y + V.y × DT, z)`; `W = (V.x + root.x × 60, V.y + root.y × 60,
  V.z)` is copied into the **static vector 0x8657a0** and `creature_moveSimple(P, 0x8657a0)`
  is called (**new**: the velocity passes through a global, not the stack); root = 0.
- (m) bookkeeping as movement-camera 4.1(m). Two details: the +0x482 countdown stores on
  every tick that does not land (decrement, then 0 if it went negative); on a landing in
  mode 2 with `bits & 3`, not the copy, `SpellCharge_onContact(spell, 0)` is called with
  whatever `creature_findSpellByType` returned, **0 included** (*Observed* and *Executed* as
  a call). The callee's first load is the spell's word +0x48 (0x2c962c; non-zero returns at
  once), so with a null spell it reads address 0x48; what a console holds there is
  *Unknown*.
- (n) `net_getCamFlag(slot)` **on every call** (**new**); with it 0 and the clamp condition of
  (k): unless the position equals `goal` in x and y, for each plane bit of `mask` with
  `(pos − old) · N < 0`, x and y go back to their values at entry.
- Return: the event bits of mode 0 (`& 4` from s = 0.6, else `& 1`), else 0.

## 4. `Player_animStep` 0x1b9520 and `Player_clampToScreen` 0x1b3d90

- **`Player_animStep(P; speed)`** — *Executed* (`playerAnimStep`: 3,000 cases, 77 of 78
  instructions). Drowsy factor (as 3(b)); slowed: `(speed × f32(60 − slow)) × DT`;
  `ev = anim_advance(P+0x114, P+0x10 or 0 when flag 0x200000, P+0xbc, 0; speed)`; with
  `c = cos16(F − 0x4000)`, `s = sin16(F − 0x4000)`, `(rx, ry)` the root just written:
  `root.y = (−rx) × s − ry × c`, `root.x = (−rx) × c + ry × s`. Returns `ev` (32 bits).
- **`Player_clampToScreen(P, &V, &mask)`** — *Executed* (`clampToScreen`: 3,000 cases with
  `vec3_dotDelta` 0x1667d8 running too, 162 of 164 instructions). mask = 0;
  `step = V × DT`; `game_buildScreenEdgePlanes(P+0x10)` 0x1e71b0 (a call-out here: it reads
  the camera frustum at 0x44f0a8, **per-machine view state**, offline only; its body uses
  `rsqrt.s` and was not executed); inside all four planes (`vec3_dotDelta(point_i, N_i, pos)
  ≥ 0`) → 0. Otherwise per plane the position is outside of: `mask |= 1 << i` (stored), and
  when `step · N_i < 0`: the first such plane removes that component (`step −= N_i × dot`),
  a second sets the step to 0 and ends the loop. A plane used: `V = step × 60`, result 1;
  else result 0 and V untouched.

## 5. Monsters: what is already executed, and where

The creature move helpers are executed in `tools/ref_creature.py` /
`tools/difftest_creature.py` (`docs/spec/creature-tick.md` 15: `Creature_moveBy` 482 of 488
instructions, `Creature_moveTo` 542 of 547, `Creature_moveToDirect`, `Creature_fleeFrom`,
`Creature_moveToTarget`, `Creature_moveToDest`, `Creature_moveToAlly`, `Creature_settle`,
the probes and avoidance, `Creature_turnToward`, `Creature_stepAnim`; 99.1 % of 7,547
instructions). They were not re-run here. What a fighting creature uses, by class, in the
executed class runs of `tools/ref_arena_monsters.py`: the chase states call
`Creature_moveToTarget` (path following to a point on the target's rim, the common ending
`Creature_moveBy` along the facing), the return states `Creature_moveToDest`, the retreat
`Creature_fleeFromTarget`, the attack and idle states `Creature_moveBy(c, 0)` (root motion
and gravity only) or `Creature_settle`. `Creature_applyKnockback` is the second
`Creature_moveBy` pass of a tick (`docs/combat-runtime.md` 5.4). In the composed runtime the
Skelight run of round 1 already runs these executed bodies.

Root motion, by mover (*Executed* in the documents named):

| Mover | Root written by | Root used | Then |
|---|---|---|---|
| creature | `anim_advance` inside `Creature_stepAnim` (+0xbc, +0xc0, yaw +0xc4), scaled and slowed there | `Creature_moveBy`: V = vel + root × 60, facing += yaw (all zeroed while the root timer +0x314 runs) | root and yaw zeroed by that move; the knock-back pass saves them, zeroes them for its own `Creature_moveBy` and restores them, so the class's later move still uses them |
| player | `anim_advance` inside `Player_animStep`, rotated into world axes (4) | `Player_move` (l): `root × 60` added to V | zeroed at once (0x1b5038-0x1b505c) |

## 6. Animation events and timing (ties to t3/research-anim)

From `docs/spec/creature-animation-dispatch.md` 4 and `docs/spec/player-animation-
dispatch.md` 4 on t3/research-anim (*Executed* / *Observed* there), joined to the bodies here:

- **Footsteps of a walking player** are clip events of the locomotion layers (walk
  {0.25 s, 0.75 s} mask 1, run layer 2 {0.45 s, 0.95 s} mask 4), returned by
  `Player_animStep` inside `Player_move` mode 0 and masked there by the speed: `& 4` from
  s = 0.6, `& 1` below (3(g)); `Player_run` state 2 calls `Player_footstep` on a non-zero
  result. A landing calls `Player_footstep` from `Player_move` itself (3(m)).
- **Monster footsteps** (masks 0x4/0x8 on walk and run clips) come out of
  `Creature_stepAnim` and are consumed in the class's run tail; some draw the object's own
  seed (Cyclops dust), so the tick on which a walk event fires is simulation state.
- **The strike** of a monster is mask 0x1 of its swing clip, consumed on the same tick as
  `Creature_stepAnim` after the knock-back pass and slot 23 (`docs/combat-runtime.md` 4.2).
- **The player's melee hit is not an event**: it lands on a frame count
  (`since == trunc(16.02 / speed)` offline; frame 1 with +0x55c = 0 in a net game). During a
  swing `Player_run` calls `Player_move` with mode 4 then 3: no stick velocity, only the
  swing's root motion moves the player (3(h), (i)).

## 7. Round-1 bodies that differ from the original

`tools/difftest_combat_move.py --round1` runs round 1's `CombatModel.move_with_collision` and
`.player_move` on the same cases. Round 1's methods are left unchanged (its API and vectors
stay stable); `ref_combat_move.MoveModel` has the executed bodies.

| Round-1 body | Difference | Evidence | Effect |
|---|---|---|---|
| `move_with_collision`, `move_simple` | calls `obj_updateGridCell` where the original has an inline copy of it | Executed (calls differ in every moving case; the stores are those of the call) | none on state: the same relink |
| `player_move` | no `dialog_isOpen` call (0x1b40c0) and no `net_getCamFlag` call (0x1b51e8); both are made on every call | Executed (`playerMoveStill --round1`: all 2,748 cases differ in calls) | none offline with no dialog |
| `player_move` | no `net_getCamYaw` call for the target angle (0x1b41ec) | Executed | none (its value only matters with a moving stick) |
| `player_move` | W is not stored in the static vector 0x8657a0 | Executed | one global the original writes every call |
| `player_move` | the track weights of a zero blend weight are +0.0; the original stores −0.0 (0x80000000) | Executed (`track_weight`) | bit patterns of +0x164, +0x16c, +0x184, +0x18c of a standing player; both blend as 0 |
| `player_move` | the +0x482 countdown is stored only when non-zero | Executed | store set only |
| `player_move` | the `water_test` height pointer is passed as 0 | Executed | none |
| `player_move` | standing in water (bit 61 set) does nothing; the original calls `water_disturb` (and `damage_apply` on hurting levels) and may clear the bit | Executed | outside round 1's flat floor |
| `player_move` | mode 0 in action state 1 keeps s; the original sets s = 1.0 | Executed | not reached by `Player_run` (state 1 uses modes 3, 4) |
| `player_move` | refuses the screen clamp when `g_numPlayers` ≥ 2 and the alive count ≥ 2; the original tests the alive count only | Observed 0x1b4f6c | a refusal condition only |

## 8. The composed runtime

`MoveRuntime` (in `tools/ref_combat_move.py`) is `ref_combat_runtime.Runtime` with
`MoveModel` as its model, grid relinks through the shared world's grid (`inline_grid=False`;
the same operation, 2), and:

- `spawn_player(..., speed_mul=1.0)` also sets record +0x4c20, which
  `player_initNewCharacter` / `player_importCharacter` store as 1.0 (*Observed*,
  movement-camera 4.1(b)); without it the player's speed scale is 0 (*Authored* set-up).
- `stick(slot, x, y)` sets the slot's lockstep movement stick (pad +0x14, +0x18).
- `Player_animStep` is the executed body; `anim_advance` stays the authored timeline of round
  1, with an optional per-state root delta (`root_motion`, *Authored*).
- `game_buildScreenEdgePlanes` answers from authored planes (`screen_planes`) or refuses: the
  real planes come from the camera (per machine). Water, the rush spell's turn rate and
  contact, and the Drowsy fraction are refused; `SpellCharge_typeinfo` answers its address.

Tests (`tools/test_ref_combat_move.py`, 26, synthetic): a player walks 155.15 / 60 per tick
along a facing that settles 0x1c2 off the stick direction (the 0x41c2 constant) and the run
is deterministic; walking into a Skelight touches it (`Creature_onTouch` sets creature flag
bit 59 for a player toucher) and is held off by the push-out (+0x490 bit 2); two alive
players offline refuse without authored screen planes.

## 9. What was run

- `python3 tools/difftest_combat_move.py <your SLUS_209.73>` (seed 20973, 3,000 cases per entry
  point): **18,000 cases compared, 0 mismatches**.

| Entry point | Compared | Instructions executed | Shared draws |
|---|---|---|---|
| `obj_moveWithCollision` | 3,000 | 399 of 404 | 0 |
| `creature_moveSimple` (+ the mover) | 3,000 | 15 of 16 | 0 |
| `Player_move` | 3,000 | 1,204 of 1,220 | 174 |
| `Player_move`, round-1 domain | 3,000 | 825 of 1,220 | 238 |
| `Player_animStep` | 3,000 | 77 of 78 | 0 |
| `Player_clampToScreen` (+ `vec3_dotDelta`) | 3,000 | 162 of 164 | 0 |

  Real in every run: the angle functions (`math_cos16`, `math_sin16`, `math_atan2_16`,
  `angle_approach`), `GameObject_rand` and the C library (soft doubles, `strcmp`, `sprintf`
  and its helpers; newlib's own first-print initialisation at 0x50c530 is done once before the
  cases). Everything else is a seeded stub, answered identically to the model.
- `python3 -m unittest tools/test_ref_combat_move.py`: 26 tests pass.
- Not run: anything on a console, PCSX2 or the live rig.

## 10. Not done, not known

- `game_buildScreenEdgePlanes` 0x1e71b0 (camera frustum, `rsqrt.s`): Observed in
  `symbols/movement.tsv`, not executed; the clamp's planes in the contract are authored.
- `world_slideMove`, `terrain_heightBelow`, `water_test`, `water_disturb` are call-outs here;
  the terrain kernels are `tools/ref_world.py`'s business and need a level file.
- `SpellCharge_onContact` 0x2c95f4 with a null spell after a rush landing (3(m)): it loads
  the word at address 0x48 first (0x2c962c) and returns when that is non-zero. The value on a
  console is Unknown; whether a rush can land without its spell attached is Unknown too
  (settle by reading who detaches the SpellCharge from the player).
- The word 0x4d8a28 (turn rate `s × 0x3d0f5c28`): no writer found (movement-camera 4.1(d)).
- A player under scripted control (+0x231) is walked by `Creature_moveToDest`
  (`docs/spec/player-tick.md` 1) — executed in ref_creature, not composed here.
- Net games and the prediction copy: `Player_move` is the same body for the copy (the
  ghost-rebase and SpellCharge tests are the only copy tests in it, 3(m)); the copy's
  re-simulation loop is not composed.

Proposed symbol line (for whoever edits `symbols/`):

```
008657a0	g_playerMoveVelocity	static Vec3: Player_move 0x1b4020 copies V + root x 60 into it and passes it to creature_moveSimple (0x1b4fa8); Executed (difftest_combat_move)
```
