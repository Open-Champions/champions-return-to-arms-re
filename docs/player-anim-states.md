# Player animation states and movement — client handoff (SLUS-20973 US v2.00)

2026-11-09, branch `t3/research-player-anim` from `cda95dc`. This note gathers what a
client needs to animate and move the player the way the original does. It adds one
executed probe, [`tools/difftest_player_anim_states.py`](../tools/difftest_player_anim_states.py)
(parts L, R, H, M), and its reference [`tools/ref_player_anim_states.py`](../tools/ref_player_anim_states.py).
Everything else is cited from earlier notes rather than repeated. Revised the same day
after the audit `research-player-anim-states` (verdict FIX): the probe now also checks
the ticks after an early press, a held attack, state 3, the Drowsy finder, the 7-track
block gate, the flinch fade, the next swing's hit and clip starts in modes 1–6; the
controls are a tracked script run on both seeds. Revised again after the re-audit
`research-player-anim-states-fix` (verdict FIX): fixed Drowsy cases where the
multiply/slow order changes the bits, a swap-order control, a baseline run in the control
script that replays the probe's own cases, the mode-5 step and fade call sites asserted,
and four wording fixes.

Labels: **Executed** = the original function ran in `tools/ee_emu.py` on constructed state
and a check of this probe compared it with the reference or a fixed expectation, on seeds
20973 and 7. Results of other tools are written "executed in `<tool>` (cited, not re-run
here)". **Observed** = read at the address, not run here. **Inferred** = a conclusion
from those. **Unknown** = open.
Nothing here ran on a console, loaded a real `.anm`, or rendered a frame.

Cross-references, not redone here:

- Clip slots, the 13-role weapon rows, `player_resetIdleAnim` and the equip→class
  handoff: [`docs/spec/player-animation-selection.md`](spec/player-animation-selection.md)
  sections 1–2 and 4.1 (this branch, `f6dfb13`..`cda95dc`). The created-character side
  (the inventory and creation clip installs, and that a reset keeps the current time) is
  `t3/research-char-appearance` `153d1c3`, `docs/spec/created-character-appearance.md`,
  "Pose, the body-mask frame, and the shell primitive".
- The per-tick order of `Player_run` and every state handler:
  [`docs/spec/player-tick.md`](spec/player-tick.md) section 6 (executed against
  `tools/ref_player.py` by `tools/difftest_player.py`, with animation answers scripted).
- Velocity, turning and modes of `Player_move`: [`docs/spec/movement-camera.md`](spec/movement-camera.md)
  section 4. The speeds there are executed by `tools/ee_tests.py` group m (m1–m6).
- Blocking damage, stagger and knock rolls, and the cast order: `t3/research-spells-r3`
  `6052213`, `docs/spec/combat-r6.md` sections 1, 2 and 5.
- Track fields and flags: [`docs/spec/animation.md`](spec/animation.md) section 1. Track
  cell: +0x00 clip, +0x08 weight, +0x0c weight rate, +0x10 life, +0x14 life rate,
  +0x18 time, +0x1c flags. The state's flag word `P+0x11a` is the union of the flags of
  the tracks visited by the last advance. Bits 0x8, 0x10, 0x20 and 0x8000 in clip flags
  are not engine flags. `Player_run` reads them as action markers.

## 1. What ran, and how

| Part | Original function | What is compared | Lines |
|---|---|---|---|
| L | `Player_move` 0x1b4020, mode 0 and modes 1–6 | rate passed to `Player_animStep`, blend `+0x46c`, held speed `+0x468`, weight and life of cells 1–3, idle time reset `+0x134`, returned footstep bits; no clip start in any mode 0–6; mode 1/4/6 clearing and mode 2/3/5 keeping (sentinels) | [141–196](../tools/difftest_player_anim_states.py#L141) |
| R | `Player_animStep` 0x1b9520; `Player_move` move stage | speed and arguments handed to `anim_advance`; the Drowsy gate (finder arguments, timer 0/−1, spell not found) with a planted fraction, and three fixed cases where the multiply/slow order changes the bits; root delta in world axes at `+0xbc/+0xc0`, return bits; `root × 60` added to the move vector and root cleared; in mode 0 the step overwrites a stale root before the move | [202–332](../tools/difftest_player_anim_states.py#L202) |
| H | `Player_processDamage` 0x1b2cc0 | name looked up (`res_find`) and clip, flags, blend times and call site of every animation start; the resisted knock's name; old-top-track fade for the knock-down, light knock and flinch; state stores | [342–463](../tools/difftest_player_anim_states.py#L342) |
| M | `Player_run` 0x1a5030, one call per tick | swing start clip and site, `Player_meleeHit` tick and arguments, combo start tick, the press tick one early plus three held ticks after it, attack held without a fresh press, the next swing's hit ticks, `Player_move` mode per tick, swing end tick; block entry, block clips, release gate (weight; 6 and 7 tracks); state 3 (no move call, root stored, position kept, exit on marker 8) | [469–687](../tools/difftest_player_anim_states.py#L469) |

Per seed: L 132 cases, R 33, H 315, M 187. **Stubs (disclosed).** Followed for real: the C
library and software-float range 0x3a5000–0x3c0000, the printf core 0x3c0170 (part H's
name building needs it), `math_cos16`/`sin16`/`atan2_16`, `angle_approach`,
`net_isSlotActive`, `GameObject_rand`, plus the camera-yaw/dialog/local-slot/cam-flag
helpers of `ee_tests.MoveRig` for L and R. Everything else is a recording stub that
returns 0 unless named:
`Player_animStep` returns a planted bit pattern (L; in M it is a stub returning 0, except
in the state-3 cases and R's last case, where it is followed); `anim_advance` writes a
planted root and returns planted bits (R, M state 3); for the Drowsy cases
`SpellDrowsy_typeinfo` 0x3d1234 returns a sentinel type-info word,
`creature_findSpellByType` 0x11a710 returns a constructed spell or 0 (per case), and
`SpellDrowsy_getStat3Fraction` 0x30ef08 puts a planted fraction (0.25, 0.333, 0.5 or 0.8)
in f0 (R); the skill-rank virtual slot returns 7, `0x30851c` 40, `res_find` a sentinel
clip, `Player_hasAnim` 0 or 1 (H); `player_canBlock` returns 1 (M).
Clip pointers are sentinels in a constructed definition table. The M target is a
pre-linked handle, because `world_collectObjectsInBox` and `handle_clear` are stubs.

**Controls.** [`tools/mutate_player_anim_states.py`](../tools/mutate_player_anim_states.py)
first runs the unmutated reference as a baseline: parts L, R, H, M in that order on one
`random.Random(seed)`, as the probe does, and all four must pass with 0 failing checks
(they did, with the probe's case counts). It saves the rng state each part starts from
and prints the same fingerprint the probe prints (`rng=…`), and each control reruns its
part from that state, so the controls run the logged probe's own cases. It then changes
the reference one item at a time. All 18 changes must make the probe fail, and all 18
did on both seeds 20973 and 7 (`local/anim-states/mutations-{20973,7}.log`): ramp
+1 ulp, run-event threshold, IEEE rounding instead of truncation, acceleration step,
root sign, slow ignored, Drowsy fraction ignored, slow before Drowsy, suffix boundary,
class-3 prefix, death models, reaction flags, fade rate, hit frame, combo window, swing
life, lunge time, stick end. The no-buffering, held-attack, 7-track and state-3 checks
compare the original with fixed expectations (nothing happens, the state stays), not
with a reference value, so no reference mutation targets them.

## 2. Action state machine (`P+0x58c`)

**Observed**, jump table 0x536260 read at 0x1a5e9c (`player-tick.md` section 6). Entry and
exit columns cite the store; **E** marks a transition this note executed in M or H.

| State | Meaning | Entered by | Leaves when | Move mode |
|---:|---|---|---|---|
| 2 | neutral: idle/walk/run layers | ctor; every exit below | — | 0 |
| 1 | melee swing / combo | attack pressed in 2, `P+0x48c×60 ≤ since` (0x1a7f7c start, **E**); heavy id 0x25 (0x1a7308) | `+0x470×60 ≤ since` (96 ticks, **E**), stick > 0.8 after 39.3 ticks (**E**), `+0x450` set → 2 | 4 then 3 (**E**) |
| 0 | bow shot / throw | attack with class 4 or 6 | marker 0x10 clear and interval passed → 2 (0x1a80e0) | 1 offline, 6 net |
| 5 | casting | ability start in 2 (0x1a6c30) | phase/marker rules, section 5 | 1 offline, 6 net |
| 8 | block | block held in 2 or during a swing, `player_canBlock` (**E**) | released, top-track weight ≥ 1.0 and fewer than 7 tracks (**E**: 0.5 stays, 1.0 leaves; 7 tracks stay, 6 leave) | 1 (**E**) |
| 0xb | block move (evade) | swap pressed while blocking (`Player_tryBlockMove` 0x1bf150) | marker 8 clear → 8 if block held, else 2 | 1 |
| 3 | hit reaction / knock-down | `Player_processDamage` 0x1b2ed8, 0x1b380c (**E**) | marker 8 clear → 2 (0x1ab1f0, **E**) | none (**E**: no `Player_move` call) |
| 4 | dead | lethal damage, 0x1b34fc (**E**) | never; `player_respawn` 0x1bd040 replaces the object | none |
| 6 | skill-driven (bash, cyclone) | skill code | skill code | 5 |
| 9 | rush | skill code | skill code | 2 (300 u/s) |
| 10, 0xc | ground pound, war cry | older skill ids 0xc, 0xe | marker 8 / 0x20 clear → 2 | none |
| 7 | airborne (jump) | **Unknown**: no writer of 7 is known | landing in `Player_move` (bits & 4 with `+0x47d`) → 2 | 0 |
| 0xd, 0xe | riding, scripted | vehicle / script code | — | none |

**Jump.** **Observed**: no pad mask among the per-slot button words (attack 0x41b980,
abilities 0x41b990/0x41b9a0, use 0x41b9c0, block 0x41b9d0, potions, swap 0x41ba30) starts a
jump. State 7's handler (0x1a5f98) is a jump arc, with vertical speed 360 after the top
track reaches 4.02 ticks, but **Inferred** unreachable from input. A client needs no jump.

**Turn.** There is no turn clip. **Executed (L):** `Player_move` starts no animation in any
mode 0–6 (in mode 0 with `Player_animStep` stubbed; modes 1–6 make no `Player_animStep`
call, asserted for each). The turn rates are **Observed** in `movement-camera.md` 4.1(d): the facing moves 40 % of the
remaining angle per tick in mode 0 (20 % in mode 1, 0.0514 in mode 4, `0.08 × s` in
mode 6), and the body moves along the facing, never along the stick. `tools/ee_tests.py`
m2 (lines 3777–3797) executes mode 0 only: the facing is still turning on call 1 and has
stopped by call 31; it asserts no rate (cited, not re-run here).

## 3. Locomotion (state 2, mode 0)

The base pose is four persistent cells: idle, walk, run 1 and run 2 (flags 0x1205),
installed by `player_resetIdleAnim` (selection note section 2). There is no discrete
walk/run state. One `Player_move(P, 0)` call per tick does this. **Executed (L)**,
reference [`locomotion_step` lines 106–132](../tools/ref_player_anim_states.py#L106):

1. `s = S × sqrt(lx² + ly²)`, capped at `S` ([32–35](../tools/ref_player_anim_states.py#L32)).
   **Observed** (`movement-camera.md` 4.1(b), 0x1b40d8–0x1b41bc): `S` = base × record
   `+0x4c20` × level `runSpeed`, capped at 1.2, then × the Drowsy fraction when s16
   `+0x31a > 0` and the player carries a SpellDrowsy. base = 0.861945 offline; 0.75 in a
   net game when PvP mode B is off or word 0x4f7124 ≠ 0; the level `watmedal` keeps
   0.861945. The record multiplier is stored as 1.0 by `player_importCharacter` and
   `player_initNewCharacter`, as 1.25 net / 1.75 offline by the arena set-up, and is
   also written by `SpellGiantGrowth` (0x3093c4, 0x30965c) and `SpellResurrect`
   (0x312a28, 0x312adc) (same section, lines 192–196). **Executed here** only with
   record and `runSpeed` 1.0 and no Drowsy, so `S` = 0.861945 / 0.75; the multipliers, the cap and the `watmedal`,
   PvP-mode-B and Drowsy branches were not executed here (`tools/ee_tests.py` m1/m3
   execute some of them; cited, not re-run here).
2. Playback rate `r` ([48–54](../tools/ref_player_anim_states.py#L48)):
   `s<0.43: s×2.3255813`; `s<0.7: (s−0.43)×3.7037034×0.3499999+1`;
   else `(s−0.7)×3.333333×0.15000009+1.35`. So r = 1.0 at 0.43, 1.35 at 0.7, about
   1.431 at offline top speed and 1.375 at the net cap.
3. Blend `B = +0x46c`: if `r > 0.01`, `B += 0.1`. Above 1.0 it becomes 1.0 **and idle cell
   time `+0x134` is set to 0**. On every tick at full blend, idle restarts from frame 0, so
   stopping always shows idle from its start. Else `B −= 0.1`, floored at 0.
4. If `r < 0.01` and `B < 0.05`: step the set at 1.0, no footstep. Else step at `r`. The
   footstep result is the returned byte, sign-extended, `& 4` when `s ≥ 0.6` (run) or
   `& 1` below (walk).
5. Held speed `h = +0x468`: `s` rises by at most 0.05 per tick (`h − s < −0.05 → s = h + 0.05`).
   Falls are immediate.
6. Weight **and** life: walk cell = `B`; run 1 = `narrow(B × (s − 0.45) × 3)`; run 2 =
   `narrow(B × (s − 0.7) × 3)`, in software doubles. **Executed: each operation truncates**
   (exact result cut to 53 bits, narrowed by cutting to 24). IEEE rounding fails the
   probe (control above). Negative values are stored; the engine clamps
   `min(weight, life)` to 0..1. Then `+0x468 = s`.

Modes 1, 4 and 6 zero `B` and the six weight/life words; modes 2, 3 and 5 leave them
(**Executed**, sentinels). The walk/run footstep events at 0.25/0.75 s (bit 1) and
0.45/0.95 s (bit 4) are constructor-written event slots (selection note section 2,
**Observed**). Idle fidget: selection note section 2 and `player-tick.md` 9.1.

**Speeds.** Velocity is `180 × s` units per second along the facing, with no
acceleration (executed in `tools/ee_tests.py` m1–m3, cited, not re-run here). Top speed is 155.15 offline, 135 net, and
216 at the 1.2 cap. Rush (state 9) moves at 300 per second. Slow `+0x2fc` 1..60
multiplies the velocity by `(60 − n)/60`. Carried load does not change speed
(movement-camera 4.3).

## 4. Root motion

**Executed (R)**, [`anim_step_speed`, `root_to_world` lines 139–158](../tools/ref_player_anim_states.py#L139):

- `Player_animStep(speed, P)`: when s16 `+0x31a > 0` it calls
  `creature_findSpellByType(P, SpellDrowsy_typeinfo())` (0x11a710, 0x3d1234), and when that
  returns a spell it multiplies speed by `SpellDrowsy_getStat3Fraction(spell)` (0x30ef08).
  **Executed with stubs** (section 1): the type-info getter returns a sentinel, the finder
  a constructed spell or 0, and the fraction is planted. Checked: the finder gets
  `(P, the getter's answer)`; timer 0 or −1 calls no finder; no spell found leaves the
  speed and calls no fraction; the multiply comes before the slow scaling. The order is
  **Observed** (movement-camera 4.1, 0x1b9520) and **Executed** in three fixed cases
  chosen so that the two orders give different bits: speed 1.0, fraction 0.8, slow 1
  gives 0x3f4962fa (slow first would give …fb); 1.25, 0.333, slow 2 gives 0x3ece0416
  (…17); 1.0, 0.75, slow 1 gives 0x3f3ccccc (…cb). The original gave the first value in
  each; the unit test pins both values, and the control "slow before Drowsy" fails. The
  random Drowsy cases alone need not separate the orders. What
  `SpellDrowsy_getStat3Fraction` returns is not executed here (it is a
  `difftest_skills_c.py` entry, scenario "88 drowsy"; cited, not re-run here).
- When slow byte `+0x2fc` is 1..60 it computes `(speed × float(60 − n)) × (1/60)`. 0, 61
  and 0xff leave it unchanged.
- It calls `anim_advance(speed, P+0x114, sound, P+0xbc, 0)`. `sound` is `P+0x10`, or 0 when
  object flag 0x200000 is set.
- The clip's local root delta `(rx, ry)` becomes, with `c = cos16(F−0x4000)` and
  `s = sin16(F−0x4000)`: `root.x = (−rx)c + ry·s`, `root.y = (−rx)s − ry·c`.
- `Player_move` adds `root × 60` to its velocity before the collision move and then clears
  `root` (**Executed**, offline and net). The player's root motion is not scaled by size or
  slow beyond the speed above (movement-camera 4.1).

Only clips with flag 0x800 (ROOT) give a delta: melee swings 0x802, knock-down 0x80a,
block 0x803/0x2801, block move 0x808. The delta reaches the body only through
`Player_move`'s move stage (movement-camera 4.1(l)). In states 1, 8 and 0xb `Player_run`
calls `Player_move` in modes 4/3, 1 and 1. That their own velocity is zero there, so the
body moves only by its clip, is **Inferred** (movement-camera 4.1(i), labelled [I] there
for state 1, lines 304–305, and 4.4); the mode per tick is **Executed** M for states 1
and 8.

State 3 is different. **Executed (M):** in state 3 `Player_animStep` runs at 1.0 and
stores the knock-down clip's root at `+0xbc/+0xc0`, but `Player_run` makes no
`Player_move` and no `obj_moveWithCollision` call and the position does not change; the
tick that returns to 2 makes none either. **Executed (R):** in mode 0, with `anim_advance`
stubbed to write the planted root (section 1), `Player_move` calls `Player_animStep`
before the move stage, `Player_animStep` stores the rotated root over the stale one
without adding, and the move uses it and clears it. That the real `anim_advance`
overwrites the root rather than adding to it is movement-camera 4.1 (line 347: "which
overwrites `root`, it does not add to it") and `docs/spec/animation.md` section 5
(`rootDelta = (0, 0)` on entry, lines 284–292; executed by `difftest_anim.py`, section 7.2
for `Player_animStep`; cited, not re-run here). So, **Inferred**: the knock-down
clip's root delta is computed but never applied (`movement-camera.md` 4.4 row "3
staggered": "`Player_run` does not move the object"). A client must not move a knocked
player by root motion; offline knock-back is a separate push (movement-camera 4.8).

## 5. Actions, their clips, and the frames that matter

### 5.1 Melee swing and combo (state 1)

**Executed (M)** for weapon classes 0, 1, 3, 5, 7, offline and net, with no haste and with
status counter `+0x374` (haste +0.25). Reference [`hit_frame`, `combo_window`,
`first_combo_frame`, `swing_end_frame`, `move_mode` lines 221–264](../tools/ref_player_anim_states.py#L221).
`e` = ticks since the swing started (`frame − P+0x448`).

`speed` is the swing speed of `player-tick.md` state 1 steps 3–4 (**Observed**): the
largest Ancestral Call / Battle Cry factor that affects the player (1.0 with none), ×
the Berserker Rage factor for record class 5, + haste. Haste = the larger item modifier
0x14 × 0.045 of the primary weapon and the slot-1 item (halved for class 7), + 0.25 when
status counter `+0x374` is set, + 0.1 when `+0x37c` is set. Slow `+0x2fc` 1..60 then
scales `speed` by `(60 − n)/60`, and every frame threshold below is divided by the
result (0x7fffffff at 60). **Executed here** only with speed 1.0 (no haste) and 1.25
(`+0x374`); the reference's `+0x37c` branch and the rest are not executed here.

| Event | Rule | Executed values (speed 1.0 / 1.25) |
|---|---|---|
| start | attack pressed in state 2 → `anim_startBlendInOut(row 0x74, 0x802; 0.1, 0.1)` at 0x1a7f7c, `+0x448 = frame`, `+0x470 = 1.6` | same tick |
| damage | offline: `e == trunc(16.02 / speed)` → `Player_meleeHit(P, target, 1, 0)`. Net: `e == 1` and `+0x55c == 0`, flag 0 | 16 / 12 offline; 1 net |
| move | mode 4 (slow turn, no velocity) while `e ≤ 0.433×60`, then mode 3 | mode 4 up to 25, mode 3 from 26 |
| combo | a **fresh press** (attack in pad `pressed` +0x0c) with `e > window/speed` starts the next swing: `Player_pickAttackAnim`, `anim_start(named clip, 0x802)` at 0x1aae5c, `+0x448 = frame`. `window = 22.02` (17.616 dual wield) − `min(haste×30, 17.4)`. A press one tick earlier does nothing on that tick, and with attack then held (pad +0x08, no fresh press) nothing on the next three ticks either; attack held from tick 1 without a fresh press starts no combo through `window + 3`: **there is no buffering or latch** | classes 0/1/3/5: 23 / 12; class 7: 18 / 9 |
| end | `+0x470×60 ≤ e` → state 2 (96 ticks for 1.6 s). Haste does not shorten it | 96 |
| stick end | stick length > 0.8 and `e ≥ 39.3` → state 2 | 40 |
| next hit | the new swing's own damage tick, counted from the combo tick. A hit frame of the old swing later than the combo tick never comes | press at 23 → hit at 39 (23 + 16); window + 12 with haste; window + 1 net. Class 7 with haste, offline: combo at 9 < hit 12, so only the new swing's hit at 21 lands (net: hits on ticks 1 and 10) |

Combo length (step cap) by class, **Observed** 0x1a9678 (`player-tick.md` state 1 step 2):
4 (class 2), 7 (1), 9 (3), 2 (5), 7 (others: classes 0, 4, 6 and 7); heavy attack 1.
Reference `COMBO_STEPS`, not executed. Which named variant comes next depends on model,
class, old variant and a frame hash (`Player_pickAttackAnim` 0x1bba88, executed in
`difftest_player.py`, cited, not re-run here; table in `t3/research-anim` `5694ae3`,
`docs/spec/player-animation-dispatch.md` §3.4).
Class 2 (`dha_`) hits by a sweep over a target list from `e ≥ trunc(127/speed)` instead
of one frame (**Observed**, `player-tick.md` state 1 step 7; not executed here). Bow and
throw: release on `since == trunc(22/speed)` (11 for a throw; halved in net play),
**Observed** `player-tick.md` state 0.

Net game: after any tick in state 8 or 0xb, `+0x55c = 16`. Each tick in state 1 counts it
down, and the frame-1 hit lands only at 0. **Executed (M):** a swing started with 16
makes no hit and leaves 15.

### 5.2 Block (states 8, 0xb)

**Executed (M):** block held in neutral → state 8. On the next tick it starts the block-idle
clip (row 0x9c, flags 0x2801) and the raise clip (row 0x84, flags 0x803), sets
`+0x55c = 16`, and moves in mode 1 (turn 20 % per tick, no velocity). With block released
it stays in 8 while the top track's weight is below 1.0 and returns to 2 once it is 1.0,
but only with fewer than 7 tracks: with 7 it stays in 8 at weight 1.0, with 6 it leaves.
**Observed** (`player-tick.md` state 8): block held also drains `R+0x4a5c` by 1/60 per
tick, and skill 0x3b adds particles with three shared draws per try.
Block move/evade: swap pressed while blocking → state 0xb, row 0xa4 with flags 0x808 and
blend 0.1/0.3, stick ignored 47 ticks, and the body moves by root motion only. It leaves
on marker 8 (`Player_tryBlockMove`, executed in `difftest_player.py`, cited, not re-run
here).
What a block does to damage is combat-r6 section 1 (front 0, half with 0x20000, back
full; state 8 draws once for the block clip choice at 0x1b548c–0x1b54b8). Knock levels drop by one from the
front (combat-r6 2.2).

### 5.3 Cast (state 5)

**Observed** (`player-tick.md` state 5); the cast order is executed in combat-r6 section 5
(cited, not re-run here):
a Skill-object cast starts `anim_start(row 0x6c, 0x8003)` in phase 0 (not for skill kind
6). The cast fires on the tick that clip's weight reaches **1.0 offline, 0.5 net** (phase
1 → 2). Then `Player_castSkill` runs aim (hand midpoint, arc query 340) → skill slot 2
cast → attach → recast store → mana debit, in that order. The state returns to 2 when
marker 0x8000 clears (phase 2), or when `Player_updateCast` sees the button released
(0x1a3f70). Kind 1 (channelled) pays `cost/60` per tick in phase 2. A hit in state 3
tears a running cast down.

### 5.4 Hit reaction, knock-down, get-up, death

**Executed (H)**, reference [`knockdown_name`, `reaction_offset`, `death_offset` lines
168–190](../tools/ref_player_anim_states.py#L168). `rel = s16(+0x2e0 − facing)`, and
`+0x2e0` points from attacker to victim (combat-r6 section 1). Knock levels and the
resist roll are combat-r6 2.2.

| Hit | Clip | Start | State |
|---|---|---|---|
| level ≥ 2, not resisted | `res_find(lump, "knockdown1_" or "knockdown2_" + a/b/c/d + ".anm")`. Prefix 2 for weapon classes 2 and 3. Suffix: `a` for rel ≤ −0x6000 or ≥ 0x6000 (hit from the front); `c` −0x5fff..−0x2000; `b` −0x1fff..0x2000 (from behind); `d` 0x2001..0x5fff | `anim_startBlendInOut(clip, 0x80a; 0.1, 0.1)` at 0x1b30bc | 3 |
| level ≥ 2, resisted | none. The same name and `int(speed)` go to the skill-0x3e reaction `0x308578` | — | stays |
| level ≤ 1 (light) | class row 0x7c | `(…, 0xa; 0.1, 0.1)` at 0x1b317c, skipped when the flag word has 0x400000 | 3 |
| surviving-hit flinch | class row 0x7c | `(…, 0xa; 0.1, 0.1)` at 0x1b38d0 | 3 |
| lethal | header `+0x14` for class 2 on models 0, 1, 4, 5, 8–11; header `+0xc` otherwise | `anim_start(clip, 0x206; 0.5)` at 0x1b34c0 / 0x1b34e0 | 4 |

When 5 or more tracks run, the knock-down, the light knock and the surviving-hit flinch
each first set the old top track's life rate to −1/12 and cap its life at 1.0
(**Executed** for all three, 5 and 6 tracks, each with its call site 0x1b30bc, 0x1b317c
or 0x1b38d0 asserted; 4 tracks untouched). A
knock-down whose name is already playing (`Player_hasAnim`) is not restarted.

**Get-up. Inferred:** there is no separate get-up clip or state. Flags 0x80a and 0xa
carry marker 8, and state 3 returns to 2 only when marker 8 is gone from `P+0x11a`
(0x1ab1f0; **Executed (M)**: it stays in 3 with marker 8 and returns to 2, with
`+0x448 = frame`, without it). That happens when the reaction track is removed at the
end of the clip. The stand-up is therefore the tail of each `knockdown*` clip. The eight
knock-down names match `creature_inKnockdownAnim` 0x10d390 (**Observed**,
`symbols/creatures.tsv` line 19: "one of the eight knockdown*.anm clips"). **Unknown:** clip
lengths, so the tick count of a knock-down, needs the `.anm` data.

**Death. Observed** (`player-tick.md` states 3 and 4): flags 0x206 (KEEP, REPORT_END,
PURGE_BELOW) hold the last frame. State 4 steps at 1.0 while
`g_playerDeadCountdown[slot] > 1`, and at `since == 180` it adds a decal with two shared
draws.

## 6. Client-implementable list

Each item names the evidence. Use bit-exact float operations where the probe compared
bit patterns.

1. **State variable** `P+0x58c` with the transitions of section 2. Do not invent states.
   No jump input, no turn clip (**Executed** L: no clip start from `Player_move` in modes
   0–6; **Observed** rest).
2. **Base cells**: idle/walk/run1/run2 from the class row, flags 0x1205, reset on spawn and
   weapon change. Keep the current time across a reset (selection note §2,
   `153d1c3`; executed there, cited).
3. **Locomotion tick**: steps 1–6 of section 3 in that order, including the idle-time
   reset at full blend, the 0.05 ramp of the held speed, the footstep byte mask, and
   truncating double arithmetic for run 1/run 2 (**Executed** L).
4. **Velocity**: `180 × s` along the facing, facing approach by mode, no acceleration
   (executed in `tools/ee_tests.py` m1–m3, cited, not re-run here; rates **Observed**).
5. **Root motion**: `anim_step_speed` (Drowsy gate, slow), world-axis rotation,
   `+ root × 60` in the move, clear after (**Executed** R; the Drowsy fraction itself
   planted).
6. **Melee**: start clip row 0x74 with 0x802, damage tick `trunc(16.02/speed)` offline or
   tick 1 net (with the `+0x55c` block lockout), mode 4 → 3 at 26, combo only on a fresh
   press after `window/speed` with no buffering, the new swing's hit counted from the
   combo tick (an old hit frame after it is lost), end at `+0x470 × 60` or stick > 0.8
   after 39.3 (**Executed** M, classes 0/1/3/5/7, speed 1.0 and 1.25; the full `speed`
   rule of 5.1 **Observed**). Variant choice: `Player_pickAttackAnim` (executed in
   `difftest_player.py`, cited).
7. **Block**: entry, the two block clips with their flags, `+0x55c = 16`, mode 1, release
   gate on the top track's weight and fewer than 7 tracks (**Executed** M); damage rule
   from combat-r6 §1 (executed there, cited).
8. **Cast**: row 0x6c with 0x8003, fire at weight 1.0 offline / 0.5 net, then aim → cast
   → attach → recast → debit (**Observed** here; order executed in combat-r6 §5, cited).
9. **Hit / knock-down / death**: the table of 5.4 with names, flags, blend times,
   fade of the old top track, and state stores (**Executed** H). State 3: no move call,
   exit on marker 8 (**Executed** M); do not apply the knock-down clip's root motion
   (**Inferred**, section 4). Get-up = end of the knock-down clip (**Inferred**).
10. **Refuse** what is not known: knock-down and swing durations from real clips, the
    class-2 sweep timing, bow/throw release (not executed here), the swing-speed and
    `S` branches not executed here (sections 3 and 5.1), state 7 entry, and rendered
    parity.

## 7. Unknown and not done

- No real `.anm` was loaded. Clip lengths, root-motion magnitudes, event times inside
  clips and when tracks are removed in a live run are **Unknown** here. `difftest_anim.py`
  needs local extracted clips, and none were present.
- The class-2 sweep, the bow/throw release, and heavy attack (id 0x25) timing were not
  executed by this probe. `difftest_player.py` covers them against `ref_player.py` with
  scripted animation answers.
- The M rig pre-links its target and stubs the world queries. It shows the timeline,
  not target selection. `player_canBlock` is a stub returning 1.
- `difftest_player.py`, `ee_tests.py` and `difftest_skills_c.py` were not re-run here.
  None of them changed. `SpellDrowsy_getStat3Fraction` is a stub here.
- Who stores state 7, and live reachability of states 6, 9, 0xd and 0xe from shipped
  skills.

## 8. Reproduction

From the worktree root on the mini, with the private executable at `local/SLUS_209.73`
(SHA-256 `292f6f48…d675`; the probe refuses any other):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["tools/difftest_player_anim_states.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0], run_name="__main__")'
# the controls: the same with tools/mutate_player_anim_states.py; both with --seed 7 too
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

Results after the final edit: each seed prints `PASS` for L (132), R (33), H (315) and
M (187), the control baseline passes with the same counts and fingerprints, and the
controls reject 18 of 18 on each seed. `difftest_player_anim_select.py`
passes 96/10/1 on both seeds. The unit suite runs 657 tests OK. The logs are ignored
files under `local/anim-states/`, each headed by the commit and the SHA-256 prefixes of
the probe, the reference, the control script and the unit test file.
