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

`tools/recomp/app/fpcontrols.h` (the interface and the rule), `fpcontrols.cpp` (plain C++,
the same file for the Mac and the Windows program), `look_host.h` / `look_mac.mm` (the
pointer), and `tools/recomp/app/fpcontrols.patch` for the files other work owns - made
against the tree with the camera work's `fpview.patch` applied; its head has the merge
notes. Nothing in the simulation is changed and nothing is translated again: what the
game is given is an ordinary controller row and the game camera's yaw word.

"Look views" are chase, shoulder and first person. In overhead and action nothing of this
touches a row.

## 2.0 Why writing the yaw word is lockstep-safe (Read, then Ran)

The look is driven by writing the game camera's yaw word (camera +0x68) from the mouse and
the right stick. In a net game that word **is carried in every input record**: the sender's
`net_main` reads it from its own camera when it samples the pad (0x133464-0x133498: bit 0
cleared, the camera-mode flag put in its place) and stores it at record +0x0c; the packet
codec has a channel for it (deltas, or a whole 16-bit value when it jumps by more than
1000 units, so a flick goes through whole); every machine, the sender included, stores the
decoded word in `g_netCamYaw[slot]` (0x13ac8c-0x13ac9c) before the tick, and `Player_move`
reads that table. A remote player has no camera on this machine - only that word. The
camera stick's own bytes travel too, but nothing in the simulation reads them. So a word
written by this file is, to every machine, a player who turned the camera quickly; no
quantising to the game's stick turn rate is needed.

**Ran** (two copies in one game, section 2.7): the first-person copy's yaw word is the same
in both tick logs tick for tick (840 to 950 different values in a run) and nothing differs.

One thing follows from the codec: the word the simulation steers by wanders up to about a
degree round the true one, even while the camera stands still (the coder keeps a small
delta until its prediction is 200 units off). It is the same on every machine. The
picture uses the exact word; the character is turned to the delivered one.

## 2.1 Look and move (Ran)

- **Look.** Mouse (0.12 degrees a count) and right stick x (220 degrees a second at full
  push, a curve, a 70 ms ease) turn the yaw word; the view follows because every view
  looks along the game camera. The game's own camera-stick code is handed a stick at rest
  in these views (it would turn the same word at 82 degrees a second, and its y steps the
  hidden zoom): **`--opt view-zoom=off` is not needed** - the zoom cannot step, and what is
  withheld is input, not a change to the game. L3 is withheld as well (it would swing the
  word behind the character). Mouse y and right stick y (130 degrees a second) are pitch,
  the picture's only, handed to the view by `fpview::add_pitch` (a 12-line addition to the
  camera work's file, in the patch). Invert settings for both.
- **Move.** The left stick is passed on as it is: with the yaw word following the look,
  forward is where the player looks, left and right are relative to it. An analog stick
  gets a dead zone of its own (0.14) and is stretched over the game's range beyond the
  game's 0.32, so a light push walks instead of doing nothing for the first third.
- **Face** (first person and shoulder by default; `controls.face.<view>`): the turning
  push of 1.2, pointed where the player looks,
  - while the character stands and is off the look (half a degree; in a net game three
    degrees, because of the wandering word above);
  - **before a strike**: an attack or ability pressed while the character faces more than
    12 degrees away is held back while the push turns it - at most 6 ticks - and then let
    through (still held, or as a two-tick press when the button is up again);
  - in the states where the stick only turns (bow drawn, casting, blocking, the wind-up of
    a swing) the stick is pointed at the look, full where the rate depends on its length.
- In chase the character is left to face where it runs (the classic third-person way: the
  camera orbits freely, the stick runs relative to it). Nothing swings the camera but the
  player, so "left" never changes its meaning under the player's thumb.
- In first person the picture is turned by the 2.48 degrees of 1.2, so its middle is
  exactly where forward walks and where an arrow without a target flies.

**Ran offline** (`work/test1.py`, first level; a small test window driven through the
control socket - "app view", "app fpc mouse DX DY", key and stick commands; the machine's
own pointer and keyboard are never touched):

| What | Seen |
|---|---|
| mouse 500 counts to the right in ten blanks | the look turned 60.00 degrees; the character followed; moved 0.0000 |
| right stick full right for 30 blanks | 117 degrees; moved 0.0000 |
| W for 60 blanks | 162.8 units along heading -44.78 (the look: -44.80) |
| A for 40 blanks | ran to the left of the look, facing 90 degrees off it; on release the character was back on the look in 7 ticks without moving |
| S held (facing 180 degrees off), then attack | the press was held back 6 ticks while the character turned (180, 108, 65, 39, 23, 14, 8 degrees off), then the swing went toward the look |
| chase / shoulder | chase: the look turns, the character keeps its facing; shoulder: it follows |

**Ran in a net game** (`work/pair.py --look-only`, the first-person copy only turns where
it stands, 1,500 blanks): the character is within a degree of the look 0 to 4 ticks after
a turn ends. It does **creep** there: a net game's speed scale is 0.75 and its stick codec
cannot deliver the exact push (the nearest it reaches is 44/128, a step of 0.079 a tick),
so turning on the spot moves the character about 4.7 units a second in the direction it
faces - a circle of a few units when the look sweeps round. Figures in 2.7.

## 2.2 Aim and hit (Ran offline)

The game aims by itself (1.4), so there is nothing to free-aim: what matters is that the
player sees **whom the simulation will take**. `fpcontrols::hud()` gives, every blank, by
the simulation's own rules applied to the look:

- `melee`: the creature a swing would take now (inside 60 degrees, in reach, lowest
  score); `shot`: the creature an arrow or a cast would fly at (nearest inside 10 degrees
  either side within 340); `locked`: the target the simulation holds during a swing or
  shot (the player's own target handle); each with position, rim distance, bearing off
  the look and hit points. `reticle` is true only when a reticle means something: a look
  view, playing, a bow or thrown weapon in hand or a shot or cast in progress. With a
  melee weapon the right picture is a marker on `melee`, not a crosshair.
- No vertical aim is offered: the simulation's only aim in height is the automatic one
  toward a target (1.4). Pitch is for looking.

**Ran** (`work/test2.py valor`: to the first monsters by the pilot's route, then first
person): with the look turned onto the monster by its bearing, `shot` and `melee` both
named it; four swings: the simulation's `locked` target was the creature named each time,
its hit points fell 242.2 -> 237.6 (one of the four swings hurt; the rest is the damage
roll of a level-1 character), `hits_dealt` counted it. Looking 150 degrees away: no mark
(nothing ahead), the monster listed as behind. Turned back and struck in the same blank,
107 degrees off: the press was held 5 ticks (107, 64, 39, 23, 14 degrees), then the swing
took the monster as its target at once. Blocking with the look turning: the character
follows at the block state's 20 % a tick without moving.

## 2.3 Feel

- **Kick** (first person; half as much over the shoulder; `controls.kick`): a small dip
  when a swing or shot starts, a roll when a hit lands on the simulation's target, a
  larger kick away from the attacker when the player is hit - added to the view in the
  `fpview::on_view` call-out, decaying to a tenth in 12 blanks. Presentation only. Built;
  the numbers are a first guess and were not tuned by anybody playing.
- **Swing tilt** (`controls.swing_tilt`): what is struck in first person is often at the
  player's feet, under the picture (the first monster met, a low four-legged one in reach,
  showed only its back at the bottom edge: `work/test2-valor/t2-in-reach.png`). While a
  swing has a target the view tips until the target's middle is within 12 degrees of the
  picture's middle. Built, not judged by eye.
- **Events for a HUD and for sound or rumble**: counters in `hud()` that only grow -
  swings started, hits dealt, hits taken (with amount and the bearing it came from),
  deaths, respawns. **Ran**: swings 4 of 4, the hit that landed, the death.
- **Death and respawn**: the camera work falls back to the game's own camera when no local
  player is alive (and in cutscenes, dialogues, menus); this file then passes rows
  unchanged and takes the look up again from wherever the game left the yaw word. **Ran**:
  death in the fight; the level's opening cutscene after everybody died in the net game.
- **Using things you cannot see** (doors, chests, save points, talking, loot): the game
  already finds the nearest usable thing in a box of 48 round the player whatever way the
  player faces and makes the prompt (1.4). `hud()` passes it on: `usable`, the game's own
  prompt text and fade, the object and its position, and its bearing off the look - enough
  for "Talk to ... (behind you)" and an arrow. **Ran**: at the platform of the first level
  `usable=1 text="Talk to Firiona Vie"`, bearing 42 degrees right; looking the other way,
  the same prompt at 137 degrees left.
- **The weapon and hands in view.** Not done; what the controls need from the camera and
  model work: the player's own model drawn in first person with what is nearer than about
  14 units of the eye left out (a near plane does it: the head and shoulders go, forearms
  and weapon stay), the eye a little ahead of the neck. That is only right when the
  character faces the look - which it does here while standing, striking, shooting,
  casting and blocking; while it runs sideways or backwards in the stock simulation the
  body is turned that way and the arms would swing out of the picture (2.6 removes that).
  `hud().facing_error` is the angle between look and body for whoever draws it.

## 2.4 Third person

Chase: free look, the character runs relative to the camera and faces where it runs; the
strike hold-back is off there with the facing rule (a strike goes where the character
faces, as in the overhead game, and the game's own target turn does the rest). Shoulder:
the first-person rules (the character faces the look, strikes wait for the turn). The
character between the eye and the target is the camera work's side offset; relative
steering flipping under the thumb cannot happen because no code turns the camera but the
player (the game's own "camera behind the character" pull is withheld with L3 and the
rest of its stick code).

## 2.5 What the new view breaks, and the data to mend it

Found by the scripted fights, not by a person playing through:

| What the overhead view gave | In a look view | Supplied |
|---|---|---|
| enemies all round are seen | an attacker behind is invisible. **Ran**: with the back turned in `valor` the first monster killed the level-1 character in two hits from 100 degrees off the look | `hud().threats[]` (nearest 16: bearing, distance, targets the player, attacking, inside the view) and `behind`, the count of those targeting the player from outside the view - for an edge-of-screen indicator |
| the creature being struck is in the picture | it can be under the picture (2.3) | swing tilt; the `melee` / `locked` marks |
| things to use are seen at the feet | not seen | the prompt data of 2.3 |
| enemy wind-ups are seen from above | seen only if looked at | `threats[].attacking` (targets the player, in its reach, turned to the player) - a guess at a tell from outside the creature's own state; the per-monster attack states were not read |
| ground effects, loot on the floor, the map | not looked at here | nothing yet: the map (R3 / Tab) is the game's own 2-D overlay and works in every view |

## 2.6 What the stock simulation cannot do, and the proposal

Running one way while facing another. In a look view with the stock simulation a player
who runs left faces left; the controls turn the character back before a strike, which
costs up to a tenth of a second, and in a net game turning on the spot creeps (2.1).

`tools/recomp/app/fp-proposed.pnach` (**not in the fix set, not in the suggested
sections**; house style; written by `local/recomp-fp-controls/work/fpasm.py`, a small
assembler that checks each of its encoders against a word of the game) adds a **strafe
mode**:

- one byte per player object (+0x47e, which only the unreachable jump state used; the
  constructor now clears it, so every new character starts with the mode off on every
  machine). While it is 0, `Player_move` is the code it was.
- While it is not 0, in the neutral state: the character turns, at the game's own 40 % a
  tick, to **where its player's camera looks** (the heading a pushed-up stick asks for:
  0x3e3d minus the yaw word that already travels with every row) - also when the stick is
  at rest - and runs **along the stick's own direction** instead of along its facing, at
  the same speed.
- The mode travels as **game message 4, sub-type 2: {2, slot, mode}**. Message 4 exists,
  is carried and executed in lockstep by every machine and has an empty handler
  (0x1e01b0); the section gives it a handler that sets the byte, and a sender. So "face
  this heading" needs **no spare bits in the pad row at all**: the heading is the yaw word
  that is already there, and the mode is a message sent when the view changes.
- Size: 87 words - 2 in `Player_move` (the hook at 0x1b4210), 2 in `Player_ctor`, 2 at the
  empty handler, and three functions nothing refers to (no call, jump, branch or data word
  from outside; checked over the whole executable): 45 in 0x2128c8 (the move code, all of
  its room), 19 in 0x215c98 (the sender, at the function's entry so that it can be
  called), 17 in 0x215d28 (the handler, at an entry too: the native build's translator
  turns a jump into the *middle* of another function into a call of that function's
  entry unless the two are merged - found when the first try ran the sender in place of
  the handler - and a jump to an entry is a tail call for any translator). It is not "one
  word": the turn-in-place found in 1.2 is the one-word-sized answer (it needs no word at
  all); running against the facing does not exist in the original and has to be written.
- **Every player of a game would need the section** (a machine without it runs that
  character along its facing: out of step at the first sideways step). It belongs in the
  fix set or nowhere; the emulator-based build would take the same words.

With the section in the game, `fpcontrols` uses it by itself in the views that face the
look (`controls.strafe`): no turning pushes, no hold-back; offline it sets the byte (what
the handler does), in a net game the mode has to be sent by the section's sender
(`fpcontrols::strafe_wanted()` says what to send; calling the sender from the application
is not wired - the test did it with the script's `call`).

**Ran offline** (`work/test3.py`, a program built with `app/build.py --extra-pnach
tools/recomp/app/fp-proposed.pnach` in a second stand-in root): overhead before and after:
A turns the character 90 degrees and runs it, as always (mode 0). First person: W, A, D, S
for 40 blanks each ran 144.8 / 144.8 / 140.5 / 143.2 units along the look, 90 degrees
left, 90 right and straight back, **the facing never more than 0.01 degrees off the
look**; an attack pressed while running left started in the next tick, no hold-back;
running right with the mouse turning (a circle strafe): 1.1 degrees behind the look at
the end; the turning push was given 0 times in 642 steered blanks.

The two-copy run is in 2.7.

## 2.7 Lockstep: two copies in one game (Ran)

`work/pair.py`: two copies of the window program in small test windows, through a lobby
server instance of this work's own (ports +4000, bound to this computer; throw-away
names), into one game; copy 1 (host, slot 0) in first person, played through its script
with mouse turns, stick look, walking, strafing, backing, strikes, blocks, casts and
potions; copy 2 (slot 1) overhead with `lobbypair.py`'s drawn input. Compared with
`tools/rig/compare.py ticks` over both tick logs: shared seed, each machine's sync hash of
the previous tick, both players' position, action state, hit points, gold, experience,
out-of-sync flags, plus both facing words and both entries of `g_netCamYaw`.

| Run | What | Result |
|---|---|---|
| `online/p1` | first level, 1,500 blanks of play | 1,819 ticks compared, **no shared column differs**; no checksum failure, no out-of-sync flag; 3 presses held back for the turn (18 ticks) |
| `online/p2` | 900 blanks, then `drunare`, 3,600 blanks: the arena fight | 5,433 ticks, nothing differs; both players hit (310 and 405 different hit-point values), both died, the level was loaded again |
| `online/p3`, `p4` | the first-person copy only turns where it stands | 1,819 ticks each, nothing differs; the creep and turn figures of 2.1 |

## 2.8 Keyboard, mouse, controller; settings; help

| | Keyboard and mouse | Controller |
|---|---|---|
| look | the mouse | right stick |
| move | W A S D | left stick |
| attack / shoot | left mouse button (also K) | Cross |
| block | right mouse button (also E, Shift) | R1 |
| use, talk, pick up | middle mouse button (also J, Space) | Square |
| abilities | L, I | Circle, Triangle |
| other weapon set | mouse wheel (also Q) | L1 |
| potions | 3, 1 | R2, L2 |
| map | Tab (also C) | R3 |
| quick-spell selector, bag, pause | arrows, Backspace, Return | direction pad, Select, Start |
| view | V | (not bound) |
| give the pointer back | Escape; a click in the window takes it again | |

The button masks are read from the game's own per-slot tables, so a remapped controller
layout in the game's options carries over to the mouse buttons. Space, Shift and Tab are
new second names for Square, R1 and R3 in every view.

**The pointer.** While a look view is played in the window that has the keyboard, the
pointer is hidden and held and the mouse's own motion is read (`look_mac.mm`: the pointer
is dissociated from the mouse, deltas come from the events; `win_main.cpp`: raw input, the
pointer clipped to the window). Never in a test window and never off screen. **Built, not
run**: it cannot be tried on a machine somebody is using without taking their pointer;
every test moved the look through `app fpc mouse DX DY`, which enters the same function
the pointer code calls (`fpcontrols::mouse_motion`). The first person to play it should
check: the pointer disappears on entering a look view, Escape gives it back, a click
takes it again, leaving the window gives it back.

**Settings** (`<data>/settings.txt`, written at a first start with every line and a
remark; also `app fpc set NAME VALUE` while running): `controls.mouse_sensitivity`,
`mouse_pitch_scale`, `mouse_smoothing`, `invert_y`, `invert_stick_y`, `stick_yaw`,
`stick_pitch`, `stick_deadzone`, `stick_curve`, `stick_ease`, `move_deadzone`,
`face.chase|shoulder|first`, `turn_before_strike`, `strike_wait`, `strike_within`,
`idle_within`, `mouse_buttons`, `capture_pointer`, `kick`, `centre`, `swing_tilt`,
`strafe`. **Help**: the keys panel (F1) and the text printed at a start end with the
look views' controls (`fpcontrols::help_text()`). The settings round trip through the
file and the panel were not run (a test window writes no settings file and shows no
panel); `app fpc set` was.

**Windows** (`app/win_main.cpp`, `app/build_win.py`): compiled and linked with
`build_win.py` (clang for x86_64-w64-mingw32; `rta_app.exe` 27.96 MB with
`fpcontrols.cpp` in it). Nothing of it was run. The Windows program does not have the
views yet (`fpview.patch`'s own merge note says how they get there); until it calls
`fpcontrols::set_view`, rows pass through unchanged, and the mouse code is in place for
that day.

## 2.9 What is not done, and what still feels wrong

- Nobody has played it. Every figure here is from scripts; sensitivity, the stick curve,
  the kick and the tilt are first guesses.
- In a net game the stock simulation creeps while turning on the spot (2.1) and a strike
  from a sideways run waits up to a tenth of a second for the turn; the proposal of 2.6
  removes both, at the price of a fix-set section everybody must have.
- In a net game the camera work's eye follows the simulated player, the picture shows the
  prediction copy (`g_ghost` 0x4027bc): asked of the camera work.
- The weapon and hands in view (2.3): not done.
- Bows and spells were read, not run: the test character had no bow, and the cast that
  was pressed in the net runs was not looked at. `reticle` and `shot` are there for them.
- Enemy tells, ground effects and loot visibility from the ground (2.5): data for
  attackers only.
- A second local player: the look views fall back to the game's camera with two local
  players (the camera work's rule), so nothing here handles port 2.
- With the proposal: the application does not send the mode in a net game by itself (the
  test called the section's sender from the script); mode off when leaving a look view is
  sent the same way.
- The pointer capture and everything on Windows: built, not run.

## 2.10 How to repeat

```
# sources: tools/recomp with app/fpview.patch and app/fpcontrols.patch applied (or the
# stand-in root of this work: local/recomp-fp-controls/root, whose tools/recomp is ../src)
python3 local/recomp-fp-controls/root/tools/recomp/app/build.py --no-game --as rta_app_fpc
cd local/recomp-fp-controls/work
python3 -B facts1.py; python3 -B facts2.py          # part 1 by running (the unmodified game's stick, yaw word, turn in place)
python3 -B test1.py                                 # look, move, face: first person, chase, shoulder
python3 -B test2.py valor                           # usable in reach; a fight: marks, strikes, block, attackers behind, death
(cd ../lobby && ./champions-server &)               # this work's own lobby instance, ports +4000 (config.ini there)
python3 -B pair.py online/p1 --views first,overhead --play 1500
python3 -B pair.py online/p2 --views first,overhead --play 900 --level drunare --play2 3600 --seed 7
python3 -B pair.py online/p4 --views first,overhead --play 1500 --look-only --seed 3
# the proposal
python3 fpasm.py                                    # writes tools/recomp/app/fp-proposed.pnach
python3 ../root2/tools/recomp/app/build.py --as rta_app_fps --extra-pnach $PWD/../../../tools/recomp/app/fp-proposed.pnach
python3 -B test3.py
python3 -B pair.py online/s3 --views first,overhead --play 900 --level drunare --play2 3000 --seed 11 --strafe \
    --app ../root2/local/recomp-out/bin/rta_app_fps
sh mkpatch.sh                                       # tools/recomp/app/fpcontrols.patch from base -> src, and the new files
```

In the running program: `--view first` (or V), then mouse and keys as in 2.8. Scripts and
the control socket: `app fpc mouse DX DY`, `app fpc button left|right|middle down|up`,
`app fpc wheel N`, `app fpc set NAME VALUE`, `app fpc hud` (one line of everything in
`hud()`), `app fpc figures`, `app fpc log on`.

## 2.11 Files

In the repository: `tools/recomp/app/fpcontrols.h`, `fpcontrols.cpp`, `look_host.h`,
`look_mac.mm` (new; compiled only once the patch is applied), `fpcontrols.patch`,
`fp-proposed.pnach` (a proposal; nothing reads it unless it is named to a build), this
document. Local (`local/recomp-fp-controls/`, game output and generated code): `base`,
`src`, `root`, `root2` (the proposal's build), `lobby` (the server instance), `work`
(`glue.py` - the edits to other work's files, `mkpatch.sh`, `fpasm.py`, `fpc.py`,
`facts*.py`, `test*.py`, `pair.py`, logs, pictures, `online/` run directories).
