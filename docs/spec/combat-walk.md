# Combat walk: walking after an attack, and a walker beside an armed creature

US `SLUS_209.73` v2.00. Two questions from the native client's lockstep fixture
(open-champions-godot `codex/netplay` round 2, "new limits"):

1. After a player's first attack swing the player never walks again, even with the stick
   held at full deflection.
2. A walking player next to an armed Skelight reaches `world_findFreeSpot`, which the
   composed runtime (`tools/ref_combat_full.py`) refuses.

The prose of `tools/ref_combat_walk.py`; the bodies were run against the original by
`tools/difftest_combat_walk.py` (seeds 20973 and 7). Evidence labels as in
`docs/combat-runtime.md`: **Executed** = the original instructions ran in `tools/ee_emu.py`
(an instruction interpreter, not a console) on constructed state and agreed with the model;
**Observed**, **Inferred**, **Unknown**, **Authored** (a fixture or refusal of this contract).
Nothing here was run on a console, in PCSX2 or on the live rig.

## 1. What a rebuild needs, in brief

1. `Player_run` 0x1a5030 action state 1 (melee) hands control back to walking by itself.
   It stores state 2 (neutral), and from the next tick on the neutral state calls
   `Player_move` 0x1b4020 with mode 0 (walking) and the pad. *Executed*
   (`walk.once`, `walk.mash.stop`, 36 runs per seed).
2. The end test of state 1 (`ref_player.Tick.state_melee`, tail):
   `elapsed = g_simFrame - player +0x448` (the start of the current swing). With the stick
   longer than 0.8 (`0x3f4ccccc`) and `elapsed >= 39.3` (`0x421d3332`), the swing ends.
   Otherwise it ends at `+0x470 x 60` (`+0x470` = 1.6, `0x3fcccccc`, for every class but
   4 and 6, so 96 ticks) or when `+0x450` is set. So with the stick held the player walks
   again **40 ticks** after the last swing started. Released, it walks again after **96**.
   *Executed* (`walk.once` 40, `walk.mash.stop` 40, `walk.release` 96, all six melee classes).
3. A press of the attack button while the swing is past its window
   (`elapsed > window / speed`, window = 22.02 `0x41b028f5` minus the haste trim) chains the
   next swing (`melee_next_swing` 0x1aac9c-0x1aafe0). That **restarts +0x448** and so the
   40-tick clock. A press every 12 ticks therefore keeps state 1 forever. Each press past the
   window (every 24 ticks at speed 1, every 12 with enough haste) starts a new swing, and
   `Player_move` is never called with mode 0. *Executed* (`walk.mash.12`, restart gaps 12
   and 24).
4. So (question 1) the netplay fixture's attack script, a press every 12 frames from frame
   24 to the end of the run, is the cause. Player_run does what the game does. A fixture that
   stops pressing walks on 40 ticks after its last swing.
5. `Creature_moveTo` 0x114510's stuck recovery: a creature that has made no progress of more
   than 4 units (`0x41800000` squared distance 16) for 300 of its clock ticks searches
   `world_findFreeSpot(position, 72, radius, 0)` when a side-step ends. If one is found, it
   jumps there and updates its grid cell (`ref_creature.py`, *Executed* by
   `difftest_creature.py`). A Skelight pressed against a walking player makes no progress, so
   a walking fight beside it reaches the search after a few hundred ticks (question 2).
6. `world_findFreeSpot` 0x14acf8 with those arguments, on the original object world and the
   composed runtime's flat floor, is `ref_objects.World.find_free_spot`. That covers the
   point, the ok byte, the terrain calls with their arguments, the shared seed and the whole
   object world. *Executed* (`free_spot`, 400 searches per seed, including retried and failed
   searches). The search was already executed by `difftest_objects.py` (`load.marker`, with
   Player1_ctor's arguments). That run passes on both seeds here too (896 and 907 searches
   under ps2, plus the three other adder models).
7. `WalkRuntime` (`tools/ref_combat_walk.py`) answers the call-out with that body on the
   runtime's own world and shared seed. Its two terrain tests, `terrain_testFlag1` 0x183b48
   and `terrain_height` 0x183820, come from the terrain fixture. *Authored*: `FlatTerrain` has
   no walls, so blocked is 0.0 and the height is the floor; a level-backed host uses
   `tools/ref_world.py`'s `terrain_test_flag1` / `terrain_height`. Everything else is
   `FullRuntime` unchanged.

## 2. Part 1: Player_run, walking after a swing

`difftest_combat_walk.py` part 1 drives difftest_player's rig. The original Player_run and
the helpers difftest_player runs for real are in the interpreter, and `tools/ref_player.py`
runs each tick first on a copy-on-write view. The comparison is difftest_player's, unchanged:
calls in order with arguments, the bytes stored outside the stack and their values, the
shared seed and the number of draws, and the exit. Only the world's answers are calmer.
`CalmWorld` gives no damage, no stray animation events, no frozen game, dialog, camera switch
or spell, and `Player_move` lands the player and moves nothing. The movement itself is
`docs/spec/combat-movement.md`. The pad holds the stick at full deflection in a seeded
direction.

| Property | Script | What the original did (both seeds) |
|---|---|---|
| `walk.once` | one press, stick held | state 1, then state 2 on the 40th tick after the press; every later tick `Player_move` mode 0 |
| `walk.mash.stop` | presses every k = 6..29 ticks, 2..6 of them, then none | state 2 40 ticks after the last swing start, then mode 0 |
| `walk.mash.12` | a press every 12 ticks for 240 ticks | state 1 throughout, a new swing at every press past the window (gaps 12 and 24), never mode 0 |
| `walk.release` | one press, stick released | state 2 on the 96th tick after the press |

There are three runs per weapon class (sword 0, two-handed sword 1, axe 2, spear 3, fist 5,
dual 7) and seed. On seed 20973, 13,633 Player_run ticks were compared, and 13,488 on seed 7.
The model equals the original on every tick.

## 3. Part 2: world_findFreeSpot beside a walker

This part uses difftest_objects' rig and driver, unchanged. The original object system is
built by its own constructors and `ref_objects.World` holds the same world. On top of that,
fights are placed: 1 to 5 objects within 80 units, with radius 16 (players) or 12
(creatures), some without the solid bit. In 15 % of the steps a crowd of 6, 12 or 30 solid
objects stands within 72 units of the centre, with radius 16, 24 or 40. The search is made
from near an object on the flat floor (z 0, -40 or 200) with spread 72, radius 12 or 16
and anyHeight 0. difftest_objects' full check runs after the search, which includes every
list, every object's words, the allocators, the shared seed and the name table.

| Seed | Searches | More than one try | No spot | Mismatches |
|---|---|---|---|---|
| 20973 | 400 | 296 | 92 | 0 |
| 7 | 400 | 221 | 61 | 0 |

## 4. The composed runtime

`tests`: `tools/test_ref_combat_walk.py` (CI, synthetic) pins the following:

- One swing with the stick held: state 1 from the press (tick 30), state 2 at tick 70, and
  the player walks on. It stands still during the swing (`AttackThenWalk`).
- A press every 12 ticks: state 1 from the first press to the end, no step.
- Six presses, then none: back to walking.
- `FullRuntime` refuses `world_findFreeSpot` in a walking fight beside a Skelight.
  `WalkRuntime` answers it. Every search has Creature_moveTo's arguments (72, 12, 0), finds
  a spot within the spread on the floor, and draws the shared seed. A spot found beside a
  creature is clear of it (`FreeSpotBesideAWalker`).

## 5. What stays open

- The terrain tests on a real level are `tools/ref_world.py`'s kernels. They are not
  re-executed here. A native host that feeds its level copy into the search relies on its
  own port of those two kernels.
- The netplay fixture's attack cadence is authored. Which button rhythm a human uses is not
  a property of the game.
