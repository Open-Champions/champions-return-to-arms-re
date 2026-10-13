# Controls for the views that look along the ground: how the original moves and aims, and what the native build does about it

Started 2026-10-13. The native build (`docs/issues/native-app.md`) has views that look
along the ground - chase, over the shoulder, first person
(`docs/issues/native-first-person.md`, `tools/recomp/app/fpview.h`). This is the controls
side of them: how the left stick, the right stick and the buttons become movement, facing
and hits in the original (part 1), and the controls built for those views without changing
the simulation (part 2). Every statement says whether it was **Ran** (with what was seen)
or only **Read** (with the address). Scripts, logs and pictures are game output and stay
under `local/recomp-fp-controls/`.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-13 13:45.**

- Part 1 is written; the movement facts are **Ran** in the unmodified native build offline,
  the targeting rules are **Read** from the code.
- Built and **Ran** offline in the first level (`work/test1.py`): mouse and right-stick
  look, movement relative to the look, the character turned to the look while it stands
  and before a strike, in first person and over the shoulder; chase leaves the facing to
  the running direction. Not yet run: a fight (targets, bow, block), a net game, the
  two-copy lockstep check, anything on Windows (compile only), the pointer capture with a
  real mouse (must not be run on a machine somebody is using: the tests move the look
  through the control socket).
- Sources: `local/recomp-fp-controls/src` (= the shared tree of 13:30 with
  `app/fpview.patch` applied, in `base`, plus this work); the edits to files other work
  owns are made by `work/glue.py`; the program is
  `local/recomp-fp-controls/root/local/recomp-out/bin/rta_app_fpc`.
- New files (to go to `tools/recomp/app/`): `fpcontrols.h`, `fpcontrols.cpp`,
  `look_host.h`, `look_mac.mm`. The patch `fpcontrols.patch` is not written yet.

Next: the fight in a monster level; the two-copy game, one first person and one overhead;
Windows; the strafing proposal (section 2.6).

---

# Part 1. How the original does it

Sources: `docs/spec/movement-camera.md`, `docs/spec/player-tick.md`, `docs/netcode.md`
(read, and re-read in the disassembly where a number mattered), and two scripted sessions
in the unmodified native build, offline, first level (`work/facts1.py`, `work/facts2.py`;
logs beside them).

## 1.1 What a controller row is, and what of it the simulation sees

A row is 16 buttons, the left stick (two bytes), the right stick (two bytes) and - in a
net game - **the camera's yaw word** (16 bits; bit 0 says "my camera is not following").
Offline `Player_move` reads the camera's yaw live (`net_getCamYaw` 0x13e0c8 ->
`Camera_getYaw`, camera +0x68); in a net game `net_main` samples it with every input
record (0x133464) and every machine steers that player with the word that was sent
(`g_netCamYaw[slot]` 0x5d0bc0). **Read**; `docs/netcode.md`, "Input record".

So the simulation knows three things about where a player wants to go: the left stick,
the yaw word, and nothing else. It has no "look direction", no facing input, no strafe
button and no lock button. The camera itself (position, pitch, zoom) is per machine and
the simulation never reads it in a net game; offline two-player games also read the view
planes for the screen clamp.

In a net game both sticks go through a lossy codec before the simulation sees them (a
delta coder with steps of 4 to 64 and a spring, `docs/netcode.md` "The codec"): a full
push takes four ticks to pass the dead zone and settles within a few counts of what was
sent. Buttons are exact. The yaw word is approximated to within about a degree and jumps
of more than 1000 units are sent whole.

## 1.2 Moving

`Player_move` 0x1b4020, neutral state (mode 0). With `(lx, ly)` the left stick after
`pad_decodeStick` 0x174ce0 (radial dead zone 0.32 of the raw stick, then
`1.4705882 x (m - 0.32)`), `S` the speed scale (0.861945 offline, 0.75 in a net game,
times the record's multiplier and the level's `runSpeed`, at most 1.2) and
`s = S x |stick|`:

| | | |
|---|---|---|
| target facing | `T = atan2_16(lx, ly) - yaw word - 0x41c2` | **Ran**: stick up / right / down / left gave facing + yaw word = 0x3e3b / 0xfe3f / 0xbe40 / 0x7e41 at the game's own yaw; with the yaw word written by the test (0, 0x2000, 0x4000, -0x4000, 0x7000) the facing followed it within 2 units |
| turning | only when `s > 0.01`: 40 % of the remaining angle per tick | **Ran**: a quarter turn read 825, -414, -449 units from the goal after one, two, three reads |
| velocity | `180 x s` units a second **along the facing**, never along the stick; no acceleration | **Read** 0x1b4794-0x1b4b88; **Ran**: 0.0605 a tick at 43/128, 0.090 at 44, 0.150 at 46, 0.269 at 50 (five ticks between reads: 0.228 ... 1.343) |
| the move | `obj_moveWithCollision` 0x14d4b8 moves only when the square of the step (velocity / 60) is above 0.001, that is a step above 0.0316 | **Read**; **Ran** below |

Consequences:

- **Movement is relative to the camera's yaw word.** "Up" walks into the screen. The
  exact heading of a pushed-up stick is `0x3e3d - yaw word`: 0x1c3 units (2.48 degrees) to
  the right of the game camera's own heading `0x4000 - yaw word`.
- **The character faces where it runs.** There is no strafe and no back-pedal: left,
  right and back are turns followed by running that way. The facing lags the stick by the
  40 % rule; the path of a direction change is a short curve.
- **There is a turn in place, and it is exact.** A push just beyond the dead zone gives
  `0.01 < s` and a step under 0.0316: the character turns at the full 40 % a tick and does
  not move. Offline with the ordinary scale that push is exactly **42/128** on one axis
  (`s` = 0.0103, step 0.0309). **Ran**: 41/128 turns nothing; 42/128 turned a quarter turn
  in three reads and moved 0.0000 in 30 ticks, on all four axes; 43/128 moves 0.06 a tick;
  the yaw word turned through a full circle in 120 ticks with 42/128 held: the facing
  followed all the way round and the character moved 0.0000. The window is narrow (`s`
  from 0.0100 to 0.0105): with another scale the nearest push creeps by 0.03 to 0.06 a
  tick while it turns (arena games: scale 1.2; a net game: 0.75 and a stick codec that is
  only within about 4 counts of what was asked).
- Diagonals of a digital stick exceed 1 and are cut off by the clamp `s <= S`: no faster.
- Walk and run are one thing: the speed is the stick's length; the animation blends at
  0.43 and 0.7.
- No jump (action state 7 has code and no way in), no dodge. The "block move" (weapon
  swap pressed while blocking, state 0xb) is an animation with its own root motion.

Other states (`docs/spec/player-tick.md` section 6; **Read**): the stick does not move the
character at all - it only turns it, at these rates, toward the same target `T`:

| State | Turn per tick toward the stick | Ran |
|---|---|---|
| 1 melee, first 0.433 s of a swing (0.567 s heavy) | 5.1 % | |
| 1 melee, afterwards | none; a stick beyond 0.8 ends the swing once 39 ticks have passed | |
| 0 ranged (drawing a bow, throwing) | 20 % offline; `8 % x s` in a net game | |
| 5 casting | the same as ranged | |
| 8 blocking, 0xb | 20 % | R1 held with the stick up: state 8, the facing went 20 % a tick, moved 0.000 |
| 3 staggered, 4 dead, 10, 0xc | the stick is not read | |

## 1.3 The right stick, and the buttons

- **Right stick x** turns the game camera's yaw word (`Camera_followRotateInput`
  0x205db0): eased, at most 274 units a tick. **Ran**: held full right the word grew by
  about 250 a tick, 82 degrees a second, and ran on by 675 after release. **y** beyond 0.9
  steps the zoom (three distances), once per push. L3 with the left stick at rest swings
  the camera behind the character.
- Buttons (the per-slot tables at 0x41b980 on; **Ran**: read from memory, and each held
  with the stick up): Cross attack (state 1, or 0 with a bow), Circle and Triangle the two
  abilities (state 5), Square use / talk, R1 block (state 8), L1 the other weapon set, R2 /
  L2 health / mana potion, the direction pad the quick-spell selector, Select the bag,
  Start the pause menu, R3 the map.
- Buttons are pressure sensitive on the console and one rule uses it: with a bow, attack
  held at a pressure below 0.13 only turns the character ("aim") and a full press shoots
  (0x1a7ca8). A net game sends no pressures (0 or 1), and neither does the native build
  (`rt/iop.cpp` gives 0xFF for a held button): that rule is not reachable here.

## 1.4 Attacking: who gets hit

**Melee** (`Player_run` state 1, 0x1a9678; **Read**).

- On the first tick of a swing - and on every later tick while there is no target - the
  simulation picks one: creatures in a box of 48 units round the player (58 with the two
  long weapon classes) and 72 up and down, inside **60 degrees either side of the
  facing**, rim nearer than the reach; the lowest `rim distance - 32 x cosine` wins. Then
  it turns the character toward the target for the first 29 ticks (the monsters' own turn
  rule, 8.4 degrees a tick at most).
- The hit lands on the hit tick (offline tick 16 / speed; **in a net game tick 1**, and
  only if the player has not blocked in the last 16 melee ticks) on **that target**,
  whatever it has done since: `Player_meleeHit` 0x1b6a98 tests the line of sight through
  the level and nothing else - no distance, no arc, no height. Whether it hurts is the
  damage function's roll (`docs/gameplay.md` 2).
- A swing without a target hits nothing. The two-hand class sweeps: everything in the
  front half is listed on the third combo step and hit as the blade passes its bearing.
- So melee is: **face within 60 degrees of something in reach, and the game does the
  rest.** There is no vertical part beyond the 72-unit box.

**Bow** (state 0, release block 0x1a8cb0 on; **Read**). At the release tick (22 ticks
after the press offline, 11 in a net game, divided by the weapon's speed):

1. `Player_findTarget(300)` 0x1bb3c8: the creature with the lowest
   `rim distance - 32 x cosine` inside 60 degrees either side of the facing, within 300,
   with a clear line through the level; one step of the turn rule toward it.
2. `world_collectObjectsInArc(pos, facing, 340, 20 degrees)` 0x1614f0: creatures in a box
   of 340 round the player, in front, inside **10 degrees either side of the facing**,
   nearest first; the first one the player's "is enemy" test accepts is **the target**.
3. With a target the arrow flies at it: heading = the bearing to it plus 200 to 700 units
   of angle (1.1 to 3.8 degrees, random), **and a vertical speed toward the middle of its
   height**, random by +-30, limited to 300 against 1000 forward (16.7 degrees up or
   down). Without one it flies along the facing, +-250 units (1.4 degrees), level.
4. The arrow (`MissileWeapon`, radius 12) keeps that velocity: no gravity, no homing. It
   moves 1000 units a second without a sweep, stops in the ground, and hits the first
   object whose cylinder it overlaps **in three dimensions** (`obj_moveAndCollide`
   0x1509f8). So height is in the hit test, and the only aim in height is the automatic
   one of step 3.

**Thrown weapons**: the same `Player_findTarget(300)` and turn, with a lead by the
target's velocity when the passive is there; without a target a random spread and rise.

**Spells and skills** (`Player_castSkill` 0x1a42b8; **Read**): the cast direction is the
bearing to the first enemy in the same arc (340, 10 degrees either side of the facing),
else the facing. What the spell then does - a bolt that homes, a cone, a ring round the
caster, a leap - is the skill's own (`docs/skills.md`); none takes a point on the ground
from the player. Cones and channelled spells follow the facing while they run, and the
facing turns toward the stick at the casting rate of 1.2.

**Blocking**: state 8 while R1 is held and a weapon or shield allows it; the character
turns toward the stick, does not move; what a block stops is decided in the damage
function by the attacker's bearing against the facing. In a net game a melee hit cannot
land for 16 melee ticks after a block.

**Using things** (`Player_interact` 0x1b2640; **Read**): every tick the nearest object
with the "usable" flag in a box of 48 round the player (feet to 60 up), **whatever way
the player faces**, is asked for its prompt; the game shows it (fade counter 0x4d8ac0,
kind 0x4d8ad0, text 0x864f50 per slot) and a new press of the use button (kind 1) or
Triangle (kind 2) uses it. Nothing here depends on seeing it. (Menus on the front end
miss presses shorter than about ten frames, `docs/issues/live-rig.md`; in play the test
is the tick's "newly pressed" word.)

## 1.5 What is simulation and what is presentation

| | Lockstep simulation (every machine computes it from the rows) | Local |
|---|---|---|
| position, facing, action state | yes | |
| which creature a swing, an arrow or a cast goes for | yes - from position and **facing** only | |
| the yaw word | yes, as part of the row (the sender's camera decides it) | the camera that produced it |
| camera position, pitch, zoom, field of view, which view | | yes |
| the prompt for something usable | the use itself | the prompt |
| a "look direction" other than the yaw word | does not exist | |

So: **where the player looks can reach the simulation only as the yaw word and the
stick.** That is enough for "forward is where I look" (the yaw word is the look), and -
because of the turn in place of 1.2 - enough for "my character faces where I look" as
well. It is not enough for running one way while facing another: the simulation runs
along the facing.

---

# Part 2. The controls of the look views

`tools/recomp/app/fpcontrols.h` (the interface and the rule), `fpcontrols.cpp`,
`look_host.h` / `look_mac.mm` (the pointer). Nothing in the simulation is changed; what
is produced is an ordinary row and the game camera's yaw word.

## 2.1 Look and move (Ran offline)

- **Look.** Mouse (0.12 degrees a count; `controls.mouse_sensitivity`) and right stick x
  (220 degrees a second at full push, a curve and a short ease) turn the **game camera's
  yaw word** directly; the view follows because every view looks along the game camera
  (`native-first-person.md` section 4). The game's own camera-stick code is given a stick
  at rest in these views: it would turn the same word at 82 degrees a second, and its y
  would step the hidden zoom - so `--opt view-zoom=off` is not needed and the question of
  that option goes away. L3 is withheld too (it would swing the word behind the
  character). Mouse y and right stick y are pitch, handed to the view
  (`fpview::add_pitch`, a small addition to the camera work's file); invert settings for
  both.
- **Move.** The left stick is passed on as it is: with the yaw word following the look,
  forward is where the player looks. An analog stick gets a small dead zone of its own
  (0.14) and is stretched over the game's range past the game's 0.32, so a light push
  walks.
- **Face** (first person and shoulder; `controls.face.<view>`): the turning push of 1.2,
  pointed where the player looks,
  - while the character stands and is more than a degree off the look;
  - **before a strike**: an attack or ability pressed while the character faces more than
    12 degrees away is held back while the push turns it, at most 6 ticks, then let
    through (still held, or as a short press if the button is up again);
  - in the states where the stick only turns (bow drawn, casting, blocking, the wind-up
    of a swing) the stick is pointed at the look, at full length where the rate depends
    on it.
- The picture's centre in first person is turned by the 2.48 degrees of 1.2, so that the
  middle of the screen is exactly where forward walks and an arrow without a target flies.

**Ran** (`work/test1.py`, first level, small test window, driven through the control
socket; the pointer of the machine is never touched):

| What | Seen |
|---|---|
| mouse 500 counts to the right in ten blanks | the look turned 60.00 degrees; the character followed within a degree; moved 0.0000 |
| right stick full right, 30 blanks | 117 degrees; moved 0.0000 |
| W for 60 blanks | 162.8 units along heading -44.78 (the look: -44.80) |
| A for 40 blanks | ran to the left of the look, facing 90 degrees off it; on release the character turned back to the look in 7 ticks without moving |
| S held (facing 180 degrees off), then attack | the press was held back 6 ticks while the character turned (180, 108, 65, 39, 23, 14, 8 degrees off), then the swing started toward the look |
| chase | the look turns, the character keeps its facing (as set); shoulder: it follows |

Pictures: `local/recomp-fp-controls/work/test1/t1-*.png`.

## 2.2 to 2.5: aim, feel, third person, mechanics

Not run yet. What the code holds so far (`fpcontrols::hud()`, for the HUD work): the
creature the simulation would pick for a swing and for a shot or cast by its own rules
(1.4), the target it holds during a swing, whether a reticle means anything, the game's
own "usable in reach" prompt with the object and its bearing, the creatures round the
player with bearing, whether they target the player and whether they are outside the
view, and counters for swings, hits dealt and taken, deaths.

## 2.6 What the stock simulation cannot do: strafing

To be written with the proposal.
