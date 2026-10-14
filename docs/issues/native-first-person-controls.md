# Controls for the views that look along the ground: how the original moves and aims, and what the native build does about it

Started 2026-10-13. The native build (`docs/issues/native-app.md`) has views that look
along the ground - chase, over the shoulder, first person
(`docs/issues/native-first-person.md`, `tools/recomp/app/fpview.h`). This is the controls
side of them: how the left stick, the right stick and the buttons become movement, facing
and hits in the original (part 1), and the controls built for those views without changing
the simulation (part 2). Every statement says whether it was **Ran** (with what was seen)
or only **Read** (with the address). Scripts, logs and pictures are game output and stay
under `local/recomp-fp-controls/`.

2026-10-14 follow-up: [first-person hands](native-first-person-hands.md) implements
the body switch and records native/Godot swing, bow and spell captures plus the
unchanged section 13 comparison. The dated controls report below is preserved.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-13 15:25 - the strafe section is in its final form and proven as far as part 3
says; adopting it into the fix set is the coordinator's step.**

- Part 1 (how the original moves and aims): the movement facts **Ran**, targeting **Read**.
- Part 2 (controls with the stock simulation): built and **Ran** offline and in two-copy
  net games.
- **Part 3 (the strafe section)**: `tools/recomp/app/fp-proposed.pnach`, 84 words, final
  (sha256 of its `patch=` lines 3259b951fc619c0e). Interpreter test 15 of 15
  (`tools/recomp/app/fp_section_test.py`); a no-op with the mode byte clear (a machine with
  the section against one without, 4,805 and 4,824 ticks); the mode in use on two, three
  and four native copies and through the drop of a strafing player (5,253 to 5,431 ticks
  each); a native copy with an emulator-based copy through a fight. The application sends
  the mode by itself. The soak work runs its own arm with the section.
- **Built, not run**: pointer capture with a real mouse; everything on Windows (compiles
  and links). **Not done**: weapon and hands in view; bows and spells run; nobody has
  played it.
- Deliverables: `tools/recomp/app/fpcontrols.h`, `fpcontrols.cpp`, `look_host.h`,
  `look_mac.mm`, `fpcontrols.patch` (against the tree with the camera work's `fpview.patch`
  of 14:23), `fp-proposed.pnach`, `fp_section_test.py`.
- Sources and builds: `local/recomp-fp-controls/` (2.11; `root` = the fix set as released,
  `root2` = with the section). Nothing of this work is left running.

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

## 2.1a The model (one paragraph)

**The player's look leads, and the look is the game camera's yaw word.** Mouse and right
stick turn that word; the picture looks along it; forward on the stick walks along it;
the character is turned to it by the turning push (standing, before a strike, and through
the turn-only states). The one time the simulation turns the character by itself - it
picks a target for a swing or a shot inside 60 degrees of the facing and turns to it -
the look **comes round to that target** (`controls.swing_turn`, below), again by turning
the yaw word, so picture, steering and character stay one direction. The camera work's
`view.<mode>.follow` (the picture eased from the camera's heading to the character's
facing) therefore stays **0 in first person and shoulder**: with it on the picture would
leave the yaw word, forward would no longer be into the picture, and the 2.48-degree
centring would be wrong. In chase, where the character faces where it runs and the camera
orbits freely, `follow` may ease the picture behind the character if that is liked - but
a chase camera that follows *and* steers needs the yaw word to follow as well, which
would be a setting here (ease the yaw word toward the facing while running); not built.

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
cannot deliver the exact push (its steps are even and the nearest value it reaches is
44/128, a step of 0.079 a tick; no pair of even stick values gives the turn without the
step), so turning on the spot moves the character about 3.4 units for every second of
turning, along the way it faces - a small circle when the look sweeps round (4.8 units
from the start after 25 seconds of it). The proposal of 2.6 removes it. Figures in 2.7.

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

**The fight beside the picture, and the look coming round** (`controls.swing_turn`,
degrees a tick at most, default 5, 0 = off; `controls.swing_turn_within`, default 6). The
camera work found that in first person the character turns to the target the simulation
picked while the view keeps looking where it looked. While a swing or a shot holds a
target, the look now turns toward it - a quarter of what is left each tick, bounded, until
the target is within 6 degrees of the middle. It is the yaw word that turns: input, the
same on every machine. **Ran, the same strike before and after** (`work/test4.py off|on`,
`valor`, the look put 40 degrees beside the first monster, then the strike):

| | 14 ticks into the swing | 30 ticks | Picture |
|---|---|---|---|
| off | the monster 42 / 53 / 53 degrees right of the look (the character had turned 17 to 22 degrees toward it) | 44 / 53 / 53 | `work/test4-off/t4-off-1-swing.png`: forest, the weapon's trail at the right edge |
| on | 8 / 9 degrees | -1 / 9 | `work/test4-on/t4-on-1-swing.png`: the monster and the trail in the lower middle, the view tipped down to it |

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

## 2.6 What the stock simulation cannot do, and the proposal (the draft; the final section is part 3)

Running one way while facing another. In a look view with the stock simulation a player
who runs left faces left; the controls turn the character back before a strike, which
costs up to a tenth of a second, and in a net game turning on the spot creeps (2.1).
The body also runs turned away from the look, which matters as soon as hands and weapon
are drawn (2.3).

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
look (`controls.strafe`): no turning pushes, no hold-back, and the application sends the
mode itself (3.4). This section describes the first, 87-word draft and its first runs;
**part 3 has the final 84-word section and its proof.**

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
| `online/p5` | the same after the standing-turn rule for net games (turn from 3 degrees, until 1) | 1,819 ticks, nothing differs; 86.6 units of path in 1,542 ticks of which the look turned in 864: about 3.4 units for every second of turning, ending 4.8 units from the start |
| `online/p6` | rebased on the camera work's prediction-copy anchor; 1,500 blanks of play | 1,819 ticks, nothing differs. **First person no longer trails the visible world**: in 7 samples taken in mid-run the view's player point was within 0.1 units of the prediction copy (the eye 7.0 ahead of it, as set) while the simulated player was 0.8 to 14.8 units behind the copy |
| `online/s3` | **the proposal** (both copies built with `fp-proposed.pnach`): the first-person copy sends the mode by the section's sender, then plays; `drunare` fight | 4,887 ticks, **nothing differs**. The mode byte of slot 0 became 1 in tick 272 on both machines, was 0 again from the first tick of the new level on both (new character object), 1 again from tick 1,879 after the second send, 0 after the reload. With the mode on: 519 ticks of running, 263 of them more than 45 degrees off the facing - sideways and backwards in the simulation of both machines; the turning push was given 68 times (before the mode came on) and no press was held back, against 897 pushes and 5 held presses (28 ticks) in the same script's run without the mode (`s2`). (A first try, `s2`, stayed in step but never set the mode: the translator had run the sender in place of the handler - 2.6.) |

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
`swing_turn`, `swing_turn_within`, `strafe`. **Help**: the keys panel (F1) and the text printed at a start end with the
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
  from a sideways run waits up to a tenth of a second for the turn; the strafe section
  (part 3) removes both - measured: 0.0000 units moved in 1,592 ticks of turning (3.6,
  `p7`) - at the price of a fix-set section everybody must have.
- The weapon and hands in view (2.3): not done.
- Bows and spells were read, not run: the test character had no bow, and the cast that
  was pressed in the net runs was not looked at. `reticle` and `shot` are there for them.
- Enemy tells, ground effects and loot visibility from the ground (2.5): data for
  attackers only.
- A second local player: the look views fall back to the game's camera with two local
  players (the camera work's rule), so nothing here handles port 2.
- States the camera work asked about, as far as these runs reached them: death (the game's
  own camera takes the frame, rows pass unchanged, the look is taken up again on the new
  character: Ran offline and in the net fights), a cutscene (the level's opening cutscene
  after a reload in a net game: the same). Pause menu, bag, dialogue, shop, vehicle with
  these controls: not run here.
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
python3 -B test4.py off; python3 -B test4.py on     # the same strike without and with the look coming round to the target
(cd ../lobby && ./champions-server &)               # this work's own lobby instance, ports +4000 (config.ini there)
python3 -B pair.py online/p1 --views first,overhead --play 1500
python3 -B pair.py online/p2 --views first,overhead --play 900 --level drunare --play2 3600 --seed 7
python3 -B pair.py online/p4 --views first,overhead --play 1500 --look-only --seed 3
# the proposal
python3 fpasm.py                                    # writes tools/recomp/app/fp-proposed.pnach
python3 ../root2/tools/recomp/app/build.py --as rta_app_fps --extra-pnach $PWD/../../../tools/recomp/app/fp-proposed.pnach
python3 ../../../tools/recomp/app/fp_section_test.py # the section in the interpreter: 15 checks
python3 -B test3.py; python3 -B test5.py            # strafing offline; the application asking for the mode by itself
sh batch1.sh                                        # n1 n2 (no-op, cross-build), m2 m3 m4 (mode in use), d3 (drop): online/*.log, batch1.txt
python3 runstats.py n1 n2 m2 m3 m4 d3               # the mode bytes on every machine, strafing ticks
python3 -B mixed.py online/x2 --play 600 --play2 5400 --seed 42 --limit 1200; python3 mixedstats.py x2   # native + emulator copy
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

---

# Part 3. The strafe section, proposed for the fix set

The owner asked for the strafing of 2.6 to be added. This part is the section in its final
form and the proof asked for before it is adopted. The section is
`tools/recomp/app/fp-proposed.pnach`: `[Net test: strafe mode - a player can run one way
and face another]`, **84 words** (sha256 of its `patch=` lines: 3259b951fc619c0e...). It is
not in `patches/SLUS-20973_4028A55F.pnach` and not in the suggested sections; adopting it
is the coordinator's step at a release. Sections 2.6 and the `s3` row of 2.7 describe the
87-word draft; what changed is in 3.1.

## 3.1 What it is

- **A mode byte per player**: player object +0x47e. While it is 0 the game is, tick for
  tick, the game without the section (3.3, 3.5).
- **While it is not 0**, in the neutral moving state (`Player_move` mode 0) the character
  turns - `angle_approach` with the game's own 40 % - to **0x3e3d minus the yaw word of its
  player**, the heading a pushed-up stick asks for, also when the stick is at rest; and its
  velocity is `180 x s` along **the stick's own direction** instead of along the facing.
  Nothing else changes: the states where the stick only turns, skills, the rush, collision,
  animation rates.
- **How the mode travels**: game message 4, sub-type 2: `{2, slot, mode}`. Message 4 is the
  game's "null" channel: registered, carried in the input packets and executed in lockstep
  by every machine in the sender's slot order - with a handler that is an empty function
  (0x1e01b0). The section gives it a handler that stores `mode` in that slot's player
  object, and a sender (`0x215c98`, mode in a0) that builds the three bytes on the stack
  and calls `net_sendGameMsg` as the game's own sender of the channel does. Offline
  `net_sendGameMsg` runs the handler at once. **Nothing is added to the pad row**: the
  heading is the yaw word that is already in it.
- **Reset**: `Player_ctor` now clears +0x47e with +0x47c and +0x47d. A new character -
  level start, level change, respawn - therefore starts with the mode off on every
  machine, in lockstep; whoever wants it asks again. A player who never sends the message
  is in the original's mode for good; a remote player's mode is whatever that player's
  messages said. The prediction copy is a clone and carries the byte.
- **Joining and leaving**: nobody can join a game in progress in the original (the peer
  table is filled once, at the launch: `docs/netcode.md`), so there is no joiner to bring
  up to date. A player who leaves or is dropped stops sending; its character is killed by
  the game's own drop code and the byte goes with the object.
- Changed since the draft of 2.6: the sender keeps its bytes on the stack (the draft kept
  them in a word of the code area), and sender and handler each stand at the entry of a
  function of their own (a jump into the middle of a function is not a call for a
  translator).

## 3.2 Where the bytes go

| Words | Address | What stood there | Why it is free |
|---|---|---|---|
| 2 | 0x1b4210, 0x1b4214 in `Player_move` | `li v0,5`; `beq s5,v0,0x1b4408` | replaced by a jump and the `li` in its delay slot; the code jumped to does the `beq` (and the `li v0,2` of its delay slot, 0x1b4218, which stays where it is and is skipped). 0x1b4210 is a branch target (from 0x1b4204) and still starts the same sequence; nothing branches to 0x1b4214 or 0x1b4218 |
| 45 | 0x2128c8-0x212978 | an unreferenced function of 45 words (audio area; `docs/audio-save.md` lists it as unreferenced) | no jump, call, branch from outside or data word in the whole executable refers to it (W3); all 45 words are used |
| 16 | 0x215c98-0x215cd4 | an unreferenced function of 36 words | the same; 20 words of it are left as they were |
| 17 | 0x215d28-0x215d68 | an unreferenced function of 31 words | the same; 14 words left |
| 2 | 0x1e01b0, 0x1e01b4 | `jr ra`; `nop` - the empty handler of game message 4 | the whole function; referred to only by the registration at 0x1dc1ac |
| 2 | 0x1a22fc, 0x1a2300 in `Player_ctor` | `sb zero,0x47c(s5)`; `sb zero,0x47d(s5)` | become `sh zero,0x47c(s5)`; `sb zero,0x47e(s5)`: the same two bytes cleared, and the third |
| mode byte | player object +0x47e | read by `Player_move` (the 1.25 speed-up, only together with +0x47c) and by action state 7, written by state 7 | state 7 has no way in (`docs/player.md`); +0x47c is 0 outside it, so a set +0x47e alone changes nothing in the shipped code (M1, M2 of 3.3 run exactly that). The constructor did not initialise it: it held what the memory held |

Against the fix set: no address of the section, and none inside the three functions, is
patched by any section of `patches/SLUS-20973_4028A55F.pnach` or of
`tools/recomp/soak/proposed-sections.pnach` (W4). The fix set's own code lives in another
unreferenced function, 0x257ab4-0x257b4c.

**Other users of game message 4.** In the original: `nullmsg_sendShopClosed` 0x1e0134
(reached by the jump at 0x1d0b70 when a shop closes in a net game) sends `{1, slot}`;
`nullmsg_send0` 0x1e0108 (`{0}`) has no caller (W5). The handler takes sub-type 2 only, so
a closing shop is ignored as before (H2). The applications' own announcements - patch set,
arithmetic - are datagrams of their network layers, not game messages: neither
`tools/play-net/src` nor `tools/recomp/net` calls `net_sendGameMsg` or names the channel.

## 3.3 In the interpreter (Executed)

`python3 tools/recomp/app/fp_section_test.py` - the section in the function-level
interpreter (`tools/ee_emu.py`, the fake player of `tools/ee_tests.py`), in the style of
`tools/recomp/soak/sections_test.py`. 15 checks, 0 failed:

| Check | What |
|---|---|
| W1, W2 | 84 words in 6 blocks; every block stands on the words its `// was:` line quotes |
| W3, W4, W5 | the three functions are referred to by nothing; no clash with any other section; the channel's one sender in the game |
| C1 | the constructor's two words: +0x47c, +0x47d cleared as shipped, +0x47e as well, +0x47b and +0x47f untouched |
| S1 | the sender: one `net_sendGameMsg(channel id, {2, local slot, mode}, 3)`; stack and saved registers kept |
| H1-H4 | the handler: `{2, slot, mode}` changes that slot's byte and nothing else in any player object; `{0}`, `{1, slot}`, other sub-types, slots of 4 and more, a slot without an object: nothing; as shipped: nothing at all |
| **M1** | **mode byte 0**: `Player_move` in modes 0 to 6, 10 sticks x 4 yaw words x facings, offline and net: **1,200 of 1,200 calls leave the same player object (all 0x590 bytes), pad, move vector and return value with the section as without** |
| M2 | mode byte 1, modes 1 to 6: 240 of 240 the same bytes with the section as without |
| M3 | mode byte 1, mode 0: 240 of 240: the facing is `angle_approach(0.4, facing, 0x3e3d - yaw word)`, also at rest; the speed is the shipped one, along the stick |
| M4 | mode byte 1, mode 0: 32 of 32: velocity words and the vector handed to the move are bit for bit those of the shipped game for a character whose facing is exactly the stick's direction |

## 3.4 The application sends the mode by itself (Ran)

`fpcontrols` knows the section is in the game by the hook word at 0x1b4210. Each blank it
compares the mode it wants - on while a view that faces the look is steered (`controls.strafe
= auto`: first person and shoulder; `on`: chase as well; `off`: never), off in overhead and
action and whenever the game's own camera has the frame (cutscene, dialogue, menu, death) -
with the byte of the simulated player; when they differ, the application calls the section's
sender in that frame's draw pass (`fpview::on_drawn`, where the game's own HUD code sends its
messages from; `apprt::call_game`, new), and again every half second while the byte is still
not what is wanted. Offline and in a net game it is the same call. With the mode on, the
controls give no turning push and hold no strike back (2.6).

**Ran offline** (`work/test5.py`, the program with the section):

| What | The simulated player's mode byte |
|---|---|
| view first / overhead / shoulder / chase / action / first | 1 / 0 / 1 / 0 / 0 / 1, each in the first blank after the view was asked for |
| `controls.strafe` off / on / (chase) / auto | 0 / 1 / 1 in chase / 0 in chase |
| pause menu opened and closed in first person | 1 throughout |
| level change | 0 on the new character while the level's own camera has the frame, 1 as soon as the view steers again |
| death | 0 (asked off when the game's camera took the frame); 1 again on the character of the restarted level |

12 messages in the whole session.

## 3.5 A no-op for everyone who does not use it (Executed, Ran)

- **In the interpreter**: M1 and M2 of 3.3 - with the byte clear, and in every mode but
  the neutral one with it set, `Player_move` leaves the same bytes with the section as
  without. The other changed words are the handler (reached only by a message of
  sub-type 2), the sender (called by nobody but an application that offers the mode) and
  the constructor's third cleared byte, which the shipped code reads only together with
  +0x47c in a state that cannot be entered.
- **Rows of a machine with the section against rows of a machine without it, on the same
  inputs** - two copies in one lockstep game, one built with the section and one without,
  the mode never set; the copy with the section played first person by the stock rules
  (`controls.strafe = off`), so `Player_move`'s hook ran on every tick of both players:

| Run | Copies | Result |
|---|---|---|
| `online/n1` | host WITH the section (first person, strafe off), joiner WITHOUT (overhead) | 4,805 ticks through the level change, the arena fight, 2 deaths and the reload: **no shared column differs** (seed, sync hashes, positions, facing words, yaw words, action state, hit points, gold, experience, the mode bytes - 0 throughout) |
| `online/n2` | host WITHOUT (overhead), joiner WITH (first person, strafe off) | 4,824 ticks, the same: nothing differs |

  (The single-machine form of this - one scripted session replayed in both builds and the
  two tick logs compared as files - was not run: the tick log of these builds is written by
  the network driver. The pair is the stronger form: each row of the machine without the
  section is that machine's own computation from the same rows of input.)

## 3.6 Lockstep with the mode in use (Ran)

`work/pair.py` (2.7) with the program built from the current sources and the final section
(`root2`, `rta_app_fps`); every copy has the section, the copies in first person and
shoulder ask for the mode by themselves (3.4), change view now and then in mid-game (the
mode goes off and on by message), overhead and chase copies never ask. Columns compared
between every two copies: those of 2.7 plus every player's facing word, yaw word and
**mode byte**. `work/runstats.py` counts the ticks.

| Run | Copies and views | Ticks in step | What happened |
|---|---|---|---|
| `m2` launch 1 | first, overhead | 5,424 | level change, arena fight, 2 deaths, reload; player 0: mode on in 2,668 ticks, switched 16 times, 272 of 554 running ticks sideways or backwards |
| `m2` launch 2 | first, overhead | 5,431 | the same course; mode on 2,456 ticks, 14 switches, 273 of 534 |
| `m3` | first, overhead, shoulder | 5,253 (all three pairs) | 3 deaths, reload; players 0 and 2 strafing (152 of 548 and 302 of 597 running ticks), 16 and 12 switches |
| `m4` | first, overhead, first, chase | 5,301 (all six pairs) | level change and fight; players 0 and 2 strafing (167 of 545, 423 of 804), 15 and 13 switches |
| `d3` | overhead, shoulder, first - **the first-person copy's process killed while strafing** | 1,854 with the killed copy, 2,752 between the two that stayed | the survivors dropped the player (dropped flag 1, no out-of-sync flag, no checksum failure) and played on in step; the shoulder player went on strafing |
| `s3` (2.7; the 87-word draft, mode sent by the script) | first, overhead | 4,887 | fight, deaths, reload |
| `p7` | first (turning its look where it stands, nothing else), overhead | 1,819 | **the turning creep of 2.1 is gone**: with the mode on the character followed the look for 1,592 ticks (the yaw word changing in 865 of them) and moved 0.0000 units - the simulation turns it itself, with the stick at rest; the turning push was given 5 times, all before the mode arrived |

In every run **the mode bytes of all players were the same on all machines in every tick**
(they are columns of the comparison; counted again by `runstats.py`: 0 ticks differing),
and no run fell out of step. A player joining in mid-game: does not exist in the original.

## 3.7 A native copy and an emulator-based copy (Ran)

`work/mixed.py`: one native copy (the window program with the section; host, first person,
asking for the mode by itself) and one copy of the emulator-based application
(`tools/play-net/play.sh`, the working build, a silent test window, its own data
directory, the suggested fix set **plus the section through `--rta-extra-patch`**;
overhead, drawn input; it never sends the mode). The emulator application has no port
shift, so this pair - unlike the others - went through the lobby server that already runs
on this computer on the usual ports (the way `lobbypair.py` always does; throw-away names;
nothing leaves this computer). The level change is made the game's own way: the native
copy's script calls `hudmsg_sendNewWorld` 0x1d9250 (game message 3 / 7), which both copies
execute in the same tick.

The emulator copy has no tick log; it leaves samples (tick, shared seed, level, both
players' positions as bits, hit points, gold, experience, the checksum verdict, **and the
native player's mode byte as the emulator copy's own simulation holds it**), each looked
up in the native copy's tick log (`work/mixedstats.py`).

| Run | Native log | Emulator samples inside it | Result |
|---|---|---|---|
| `online/x1` | 3,472 ticks; level change at tick 947; nobody was hit (the arena's own cutscene was still running at the end) | 45 | 43 equal in every compared column (seed, level, player count, the native player's position bits, both players' hit points, gold, experience, checksum verdict, **mode byte**), 26 of them with the mode byte 1; the 2 others were taken in the tick of the level load (no player object yet on the sampled copy: zeros) |
| `online/x2` | 4,821 ticks; level change at tick 724; **a fight**: the emulator copy's character was hit (684 different hit-point values) | 63 | 60 equal in every compared column, 41 of them with the mode byte 1 (the native player strafing: mode on in 3,042 ticks); the 3 others again in the tick of the level load |

In both runs the game's own checksum exchange agreed on both copies (expected = received:
bd96ab57, d5d4f60a; `g_checksumFailed` 0 on both; no out-of-sync flag), and both copies
named the same patch set to each other (073064bb, 99 words: `--rta-extra-patch` words and
the native build's `--extra-pnach` words are not counted in that figure - once the section
is in the fix set the figure will change for everybody at once). This comparison is
weaker than a row-for-row one - an emulator copy has no tick log - as
`docs/issues/native-online.md` says of all mixed pairs.

## 3.8 Two things ruled out by reading

**The tick in which the mode takes effect.** A game message is not applied when it
arrives. `net_sendGameMsg` appends it to the sender's message ring; `net_main` attaches
the bytes to one of the sender's future input frames (record +0x10 offset, +0x14 count);
they travel with that frame in every packet until it is acknowledged; and
`net_frameLoop`, on every machine, when it simulates that frame, applies that peer's pad
and yaw word (0x13ac84-0x13ac9c) and then reads the record's count and calls the handlers
(0x13ac90-0x13ad24) - peers in slot order, before the run tasks of the tick
(`docs/netcode.md`, "The tick", "Game messages"; re-read in the disassembly). So the mode
byte changes in the same tick on every machine, the sender included, and before any
`Player_move` of that tick. **Ran**: the mode bytes are columns of every comparison of 3.6
and never differed in a tick, with 9 to 16 switches per strafing player and run.

**The prediction copy.** Only the owner's machine has one, and only of its own player:
other machines do not predict a remote player at all, they simulate it in ticks
(`net_predictLocalPlayer` runs the copy through the local input frames not yet simulated).
The copy is a clone of the simulated player (`Player_clone` 0x11e870 copies +0x47e with the
rest), runs the same `Player_run` and so the same hooked `Player_move`, with its own byte:
it strafes exactly as the real one will. It is not part of any compared record (the sync
hash and the tick logs read the simulated objects of the player table). The section's move
code writes nothing but the facing of the object it is given and two float registers, and
reads nothing a machine could hold differently: the object's own byte, the stick of the
lockstep pad, the per-slot yaw word. The application, on the owner's machine, copies the
simulated player's byte to the copy each blank so that the picture does not wait for the
next re-clone - a write to an object no other machine has.

**Readers of "the way the player runs".** The velocity the game keeps for others to read
(+0x4bc, +0x4c0, and +0x308, +0x30c, which monsters use to lead a running player) is the
velocity `Player_move` actually computed - with the mode on, the true sideways velocity,
so a monster's lead is right. Rush, charge and bash skills move along the facing (mode 2,
or a vector of their own) and are untouched; in the mode the facing is the look, which is
what a player in first person expects of a charge. Knock-back does not exist for players
in a net game; staggered, dead, mounted and scripted players do not reach the neutral
move. None of these is a per-machine read, so none can break the step; they could only
feel different, and none was seen to.

## 3.9 Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| FP1 | The simulation has an exact turn in place: a left-stick push with `0.01 < S x stick` and a step under 0.0316 turns a player 40 % of the angle a tick and moves it by nothing (offline, ordinary scale: exactly 42/128 on one axis). A net game cannot deliver it (scale 0.75, even stick codec steps): the nearest push moves 0.079 a tick | Ran (native build), Read | 0x1b4228, 0x14d4b8 (the 0.001 test); docs/issues/native-first-person-controls.md 1.2, 2.1 |
| FP2 | The yaw word of the input record is the sender's own camera yaw, written by nothing else; a machine may write its camera's yaw directly (mouse look) and every machine steers that player by the delivered word. The delivered word wanders up to about a degree round the true one while the camera stands still | Read, Ran (two to four native copies; a native and an emulator copy) | 0x133464-0x133498, 0x13ac8c-0x13ac9c; same document 2.0, 2.7 |
| FP3 | A swing takes its target inside 60 degrees of the facing and in reach and hits that target whatever it does afterwards (line of sight only); arrows and casts fly at the nearest enemy inside 10 degrees either side within 340, with an automatic vertical part; there is no aim in height by the player | Read; the melee part Ran | 0x1a9678, 0x1b6a98, 0x1bb3c8, 0x1614f0, 0x1a8cb0, 0x1a42b8; same document 1.4, 2.2 |
| FP4 | Game message 4 (the "null" channel, id at 0x86aa60) has an empty handler 0x1e01b0 and one sender in the game, `nullmsg_sendShopClosed` 0x1e0134 (`{1, slot}`, a shop closing in a net game); `nullmsg_send0` 0x1e0108 has no caller | Observed | W5 of tools/recomp/app/fp_section_test.py; 0x1d0b70, 0x1dc1ac |
| FP5 | Player object +0x47e is read only by the unreachable jump state and by one test in `Player_move` that also needs +0x47c; `Player_ctor` does not initialise it | Observed | 0x1a22fc, 0x1b4020 (the 1.25 branch), state 7 of `Player_run` |
| FP6 | The section "strafe mode" (84 words) changes nothing for a player whose mode byte is 0: `Player_move` leaves the same bytes in 1,200 of 1,200 interpreter calls; a machine with the section and a machine without it stay in step for 4,805 and 4,824 ticks through a fight with the mode never set | Executed, Ran | same test, M1, M2; runs n1, n2 (3.5) |
| FP7 | With the mode in use, two, three and four native copies in mixed views stay in step through fights, a level change, deaths, reloads and the drop of a strafing player; the mode bytes are the same on all machines in every tick | Ran | runs m2 (two launches), m3, m4, d3 (3.6) |
| FP8 | An emulator-based copy given the section simulates a native player who strafes: samples equal to the native tick log in every compared column, the mode byte among them, and the game's checksum exchange agrees | Ran | runs x1, x2 (3.7) |
