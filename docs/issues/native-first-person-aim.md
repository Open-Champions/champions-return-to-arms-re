# Aiming by looking in first person and over the shoulder

Started 2026-10-20. In the views that look along the ground ([the camera](native-first-person.md),
[the controls](native-first-person-controls.md)) the player looks with the mouse or the right stick, but an
arrow or a spell bolt still goes where the game's own automatic aim sends it: at the nearest enemy near the
facing, or straight ahead and level. This adds an optional mode in which bows, thrown weapons and spell
bolts leave along the line the player looks along - heading and pitch - while the game stays deterministic
lockstep. Every statement says **Ran** (with what was seen), **Read** (with the address) or **Inferred**.
Scripts, logs and pictures are game output and stay under `local/aim/`; nothing of them is in the
repository.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-21 - in every version: Mac, Windows, Linux, the Godot library and its portal (3.5).** Ran: a Linux + Mac room
(4,381 ticks in step), a Windows (VM) + Mac room (2,254), two Godot portals (2,333); every pair equal in every shared
column, the aim block's own included. Still not: the emulator application (no pnach section).

**2026-10-20 - built, run offline and with two copies in one room; mode off byte-identical on the rig.**

- Program: `local/recomp-out/bin/rta_aim2` (the fix-set game with the mode), `rta_aim2_orig` (the game as on
  the disc with the mode's code linked in, for the rig). `rta_aim1` was the first build (same tick code; the
  sender only sent one needless "off" at the title screen). `bin/rta_app` and `rta_app_next` were not touched.
- Code: `tools/recomp/app/fpaim.{h,cpp}` (new); hunks in `fpcontrols.{h,cpp}` (`set_aim`), `app_main.cpp`,
  `build.py`, `build_win.py` (the Mac stand-in build that compiles `app_main.cpp`), `net2/hooks.h`,
  `net2/launch.cpp`, `net2/session.cpp`.
- **Ran**: offline, five arrows at five look pitches fly at exactly those pitches along the look; spell bolts
  likewise (3.1). Two copies in one room with the mode on, the host's choice taken up by the joiner, three
  launches through a level change, a fight, deaths and a reload: 5,499, 6,100 and 6,096 ticks in step, every
  column equal including the mode's own (3.2). A room whose copies differ in the mode is not started (3.2).
  The rig comparison with the mode off is byte for byte the reference in overhead and first person (3.3).
- **Not done**: the emulator application; homing bolts and the arrow skills, thrown weapons and Shock of Fire were
  not exercised (4); nobody has played it. (Windows, Linux and Godot: done 2026-10-21, 3.5.)

---

## 1. How the game aims projectiles (Read, then Ran)

The targeting itself was read for the controls work ([controls](native-first-person-controls.md) 1.4, FINDINGS
FP3). Read again here for what the launch does with it:

| What | How | Where |
|---|---|---|
| bow, the release tick | `Player_findTarget(P, 300)` and one step of the turn toward it (within 60 degrees of the facing); shared draw A, the spread `% 500 - 250`; `world_collectObjectsInArc(pos, facing, 340, 20)`: the first creature the "is enemy" test accepts is the target | state 0, `docs/spec/player-tick.md` "State 0"; 0x1bb3c8, 0x1614f0 |
| without a target | heading `h = facing + spread`; velocity `(cos16(h) x 10 x 100, sin16(h) x 10 x 100, rand % 60 - 30)`: 1000 units a second along the facing, **level within 1.7 degrees** | 0x1a8cb0-0x1a8d60 (`math_cos16` 0x166630, `math_sin16` 0x1666e0, the constants 10.0 and 100.0) |
| with a target | the vector to the target's middle (its height x 0.5 added), normalised, x 1000; then the vertical part plus `rand % 60 - 30`, clamped to +-300: the **only aim in height is the automatic one toward the target** | 0x1a8d64-0x1a8ed8 |
| the arrow | `MissileWeapon_ctor` 0x150ee4 stores the velocity at object +0x1b0 and the heading argument (the heading - 0x4000) at +0x38; owner handle at +0x4c (`Projectile_ctor` 0x150e48, flag 0x80); linked to the every-frame run list | 0x1513a4-0x1513e0, 0x150e9c-0x150ec8 |
| its flight | `MissileWeapon_run` 0x15153c moves it by +0x1b0 (`obj_moveAndCollide` 0x1509f8: velocity x 1/60 a tick); nothing in the run rewrites +0x1b0 (no gravity, no homing). The model is drawn turned about the vertical only, by +0x38 | 0x151670-0x15168c; draw 0x15253c (0x15257c-0x152598 `mat34_setPosRotZScale`) |
| thrown weapons | `playerProjectile` (a `MissileWeapon`), its run takes 9.0 off the vertical speed every tick: a falling throw | 0x1ba940 (0x1bac58-0x1bac74) |
| spells | `Player_castSkill` 0x1a42b8: the bearing to the first enemy in the same arc (340, 10 degrees either side), else the facing; the skill builds its own object | FP3 |
| bolts that keep their velocity | the arrow skills (`Fire`/`Cold`/`Poison`/`ExplodeArrowProjectile`, velocity +0x54), `Sparks` (Shock of Fire, +0x58), `ShockOfFrost` (+0x9c): their runs move by the kept vector and do not write it | runs 0x2d66ac, 0x2d73c8, 0x2d8e80, 0x2db17c, 0x28fa3c, 0x2f77c0 (each run's `obj_moveAndCollide` call; no store to the vector in the run, searched for each) |
| homing bolts | `DiseaseBolt` turns its +0x38 toward its target by a bounded step and rebuilds the velocity `350 x (cos, sin, 0)` every tick; `HolyStrike` the same with 450; `HolyBolt` and `PoisonBolt` rewrite their vectors every tick | 0x2ca7c4-0x2ca850, 0x2ec390-0x2ec400, 0x2f5894-0x2f58f8, 0x30f8c8-0x30f8d4 |
| the move | `atan2_16` 0x166798 is `atan2f(f12, f13)` scaled to 16-bit units, f12 the y and f13 the x difference | 0x166798-0x1667d0, its use at 0x2ca7d0-0x2ca7ec |

So: **auto-target yes** (the nearest enemy within 10 degrees and 340, after a turn of the body toward the
nearest within 60 degrees and 300), **the facing otherwise**, and **pitch only the automatic one toward a
target** (or a random 1.7 degrees). The look's pitch never reaches the game.

**Ran** (offline, the program with the mode linked in but off, `local/aim/r5off`: a Wood Elf Ranger at the
start of valor, nothing near, the look's pitch set to 20, 0, 15, -8, 35 degrees before each shot): the
arrows climbed **+0.5, -1.2, +1.3, -1.7 degrees** (one was not tracked) whatever the look, at 16.7 units a
tick, along headings of 133.7, 132.4, 132.0, 132.2 degrees against a look of 132.5 (the spread). Next to a
monster (rim distance 11) the attack button with a bow gave a melee swing (state 1) instead of a shot,
in both modes (`local/aim/r2`, `r2off`).

## 2. Design

### 2.1 The rule

What changes the simulation is computed in the tick, on every machine, from what every machine has alike.

- **The heading** is the yaw word of the player's input record, the per-slot word every machine steers
  that player by (`net_getCamYaw` 0x13e0c8; FP2): `0x3e3d - yaw word` is where a pushed-up stick walks and
  where the first-person picture's middle looks (the controls' 2.1). Nothing new travels for it.
- **The pitch, and whether the player aims by looking at all,** travel by **game message 4, sub-type 3**:
  `{3, slot, flags (bit 0: aiming), pitch low byte, pitch high byte}`, the pitch in 16-bit angle units. Message 4
  is the game's "null" channel (FP4), carried with an input frame and executed in lockstep by every machine
  in the tick of that frame, the sender included; offline `net_sendGameMsg` calls the handler at once
  (0x13db5c-0x13db78). The strafe section of the fix set already uses sub-type 2 of it.
  Why not the input record: it has no free field. Its 16 buttons all have meanings, the yaw word is taken,
  and the right stick's bytes, which nothing in the simulation reads, go through the lossy stick codec
  (steps of 4 to 64 and a spring: a value settles over several ticks within a few counts, `docs/netcode.md`
  "The codec") - a pitch there would be late and a few degrees off. A message is exact.
- The handler stores the slot's flag and pitch in a block of guest memory, **0xE0A00** (the first megabyte,
  free: `tools/recomp/soak` uses 0xE0000-0xE004F, the souls mode 0xE0800-0xE09FF). The numbers in it are
  written only in the tick and are the same on every machine; they are tick-log columns in 3.2.
- **The launch**: `Player_run` (Player slot 4) is wrapped. Before the original runs, the first objects of the
  every-frame run list are noted; a new object is linked to the **front** of its list
  ([object system](../spec/object-system.md) 1, 2.2), so after it, whatever stands in front of them was linked
  during this player's run. Of those, an object of a known class (the kept-velocity classes of section 1) whose
  owner handle is this player gets its velocity turned onto the look, **its speed kept**:
  `v = |v| x (cos p cos h, cos p sin h, sin p)`, and its +0x38 turned by as much as its heading changed (the
  model). `cos16` / `sin16` / `atan2_16` are the game's own functions (called on the running context); the
  float operations are single IEEE operations of a build with `-ffp-contract=off`, `sqrt` correctly rounded.
  The prediction copy (flag 0x20000) is left alone (it creates no arrows: "real only", player-tick.md).
  The game's random draws are all still made (the spread, the rise): the shared seed advances as before.
- The run list and the owner handles are the same on every machine, so the same objects are chosen everywhere.
  If more than eight of the noted front objects were deleted in the same run (not seen) the walk would stop
  after 64 objects; that too would be the same on every machine.
- **The sender** (`fpaim::drawn`, from the draw pass in `fpview::on_drawn`, where the strafe sender is called
  from): aiming is on while this machine's view is first person or shoulder, that view has the frame, and the
  player is playing; the pitch is the view's `look_pitch` (degrees, clamped to +-78.75). A message goes when
  the flag changes, or the pitch moves a quarter of a degree from what was sent - at most one every two
  blanks - and again after a second when the simulation still holds something else. Not while another
  machine's rows are replayed (the controls' replay rule).
- In the mode, `fpcontrols` no longer turns the look toward the target the game picked during a shot
  (`controls.swing_turn` for state 0); a swing still does.

### 2.2 One switch for the whole game

Like the souls-style combat mode ([souls combat](native-souls-combat.md) 2.2):

- Offline: `combat.aim = look` (settings file) or `--aim look`; off by default. `app aim info | on | off`.
- Online, a room of our own (net2): a **room option**. A copy with the mode wanted sets bit **0x4000** of the
  word count in the description it gives the room and folds an FNV-1a figure of the mode's version into the
  fix-set figure; a joiner takes the host's choice and says so again; a room whose copies differ shows
  "Aiming by looking is on for A and off for B: every copy must have it. Do not start.", `net2_start` refuses,
  and a copy started anyway does not launch. At the launch every copy is told the room's choice
  (`net2hook::aim_room`); it holds for the game and ends with it.
- Online through the old lobby: off.
- With the mode off nothing is replaced: the program is the program without this file (3.3).

## 3. What was run

### 3.1 Offline (Ran)

`local/aim/t4.py` (`r5`, `r7`): a Wood Elf Ranger at the start of valor (no monster near), `--aim look`, the
look's pitch set before each shot, then the attack button; each arrow's position read every two ticks.

| View, look pitch | Pitch carried (16-bit units) | Arrow flight (positions) |
|---|---|---|
| shoulder, 20 | 3641 | climbs **+20.0** degrees, heading 132.52 (the look), 16.7 units a tick; seen climbing for 240 ticks, to 1,451 units up |
| shoulder, 0 | 0 | **0.0**, 132.52; stopped after 20 ticks (an obstacle) |
| first, 15 | 2731 | **+15.0**, 132.52; climbing for 240 ticks |
| first, -8 | -1456 | **-8.0**, 132.52; in the ground after 18 ticks |
| shoulder, 35 | 6372 | **+35.0**, 132.52 |

`rta_aim1` and `rta_aim2` gave the same flights. Against the game's own (`r5off`, 1): +0.5 to -1.7 degrees.

Spells (`w1`, `w2`: an Erudite Wizard next to the valor boar, the ability button): every cast is a
`ShockOfFrost` (speed 350 a second), turned onto the look; its positions climb **+25.0, -10.0, +45.0,
-40.0** degrees with the look at 25, -10, 45, -40. The boar was within reach at the launch and took 30 to
32 hit points from each of the five tracked casts, the upward ones too: these bolts live only a few ticks and hit what
they overlap.

### 3.2 Two copies in one room (Ran)

`local/aim/net/n2aim.py`: `tools/recomp/net2/n2party.py` unchanged, with the window program off-screen
(`as-app.py` of the souls work), **only the host given `--aim look`**, the host a Ranger and the joiner a
Wizard (presses right on the class page), the drawn input of `lobbypair.play_lines` with random mouse looks in
yaw and pitch woven in (and now and then a new base pitch), and the block's words as tick-log columns: mode,
messages, projectiles aimed, and per player the flag, pitch, messages, count aimed, heading, pitch and class of
the last, its speed, the facing word, the weapon class. A rendezvous service of the run's own on 127.0.0.1.
`tools/rig/compare.py ticks` over the two tick logs.

| Run | Views | Result | What happened |
|---|---|---|---|
| `two1` | first, first | **5,499 ticks in step**, no shared column differs | the joiner: "the host plays with aiming by looking on: so does this copy now"; mode on in every tick; hub > drunare, the fight, 2 deaths, the reload; 160 aim messages applied; Ranger **18 arrows** at **15 different pitches from -21.9 to +59.5** degrees, Wizard **9 Shock of Frost** at **9 pitches from -40.3 to +17.5** |
| `two2` | first, shoulder | **6,100 ticks in step** | the same course; 191 messages; 16 arrows at 12 pitches (-65.0 to +24.6), 8 casts at 8 pitches (-19.8 to +38.0) |
| `two3` | shoulder, first (final sources, `rta_aim2`) | **6,096 ticks in step** | 252 messages; 20 arrows at 17 pitches (-45.3 to +9.0), 9 casts at 8 pitches (-8.9 to +65.0) |
| `refuse1` | host with the mode, joiner the standard `rta_app` | **not started**, as it should be | the room's warning "Aiming by looking is off for J1 ... and on for Host ...: every copy must have it. Do not start."; 95 tries of the host's start, each refused ("Not every copy in the room aims by looking."); nobody launched |

In every run the two tick logs are equal in every shared column - the game's (seed, the previous tick's sync
hash, positions, states, hit points, gold, experience, out-of-step flags) and the mode's - and no out-of-step
flag was raised.

### 3.3 The rig comparison with the mode off (Ran)

`local/aim/rig/check.py` (the souls work's copy of the hands work's driver): the fight session against the
rig's log, controller rows replayed, the original game's translation **with this work's code linked in**
(`rta_aim2_orig`), no `--aim`.

| View | Result |
|---|---|
| overhead | `compare.txt` byte for byte `reference-compare.txt` |
| first person | `compare.txt` byte for byte `s13-first-compare.txt` |

### 3.4 Pictures (Ran; local only)

| What | File (under `local/aim/`) |
|---|---|
| first person, look 8 degrees down: the arrow just loosed, on its way to the middle of the picture | `r6/first-8-1898.png` (1280 x 896) |
| side view of the tracked arrows of 3.1, height against distance: aim on (the five look pitches) and the game's own aim (level) | `r5/arrows-side.png` (drawn from the tick data) |

The arrow itself is small: at 640 x 448 it is not seen against the sky in shoulder view.

### 3.5 Windows, Linux, Godot (2026-10-21, Ran)

What `app_main.cpp` does, the others now do in the same places: `fpaim::blank` after the controls' `translate`,
`fpaim::drawn` in `fpview::on_drawn` (not while rows are replayed), `--aim look|off`, `combat.aim`, `app aim ...`, the
figures line. Files: `app/win_main.cpp`, `app/linux/linux_main.cpp`, `build_win.py` (the Windows program's list),
`build_linux.py`; Godot: `tools/godot/build.py` and `build_lib_linux.py` / `build_lib_win.py` compile `app/fpaim.cpp`
(`-DRTAG_HAVE_AIM`); `lib/rtag.cpp` calls `fpaim::blank` and `fpaim::drawn` as `app_main.cpp` (the sender only while the
library's controls are on), takes `rtag_set_option("combat.aim", ...)`, answers `rtag_has("aim")`, runs `app aim ...`,
and says `aim_want=`, `aim_on=` and, in `copy=`, the word count with bit 0x4000 and the figure folded in (as
`net2/launch.cpp` `souls_describe`); `main.gd --aim look|off`; the portal: `gameflow.gd` (`aim_available`, `set_aim`),
the room screen's choice **"Aim: The game's / Where you look"** (host only; a joiner's library follows the host by
itself), and the warning "The host aims where they look and NAME does not have it (yet)" for a copy without it.

| Run | Copies | Result |
|---|---|---|
| `lin1` | host the Linux `rta_app` (aarch64, container, `--aim look --view first`, Ranger), joiner the Mac `rta_app_next` (Wizard, no option: it took the host's choice) | **4,381 ticks in step** hub > drunare, a death; no shared column differs; 121 messages; 19 arrows at 17 pitches (-10.3 to +59.5), 6 Shock of Frost at 6 pitches (-33.4 to -6.0) |
| `win/w1` | host the Mac `rta_app_next` (`--aim look`, Ranger), joiner the VM's `rta_app.exe` (`--offscreen --plain`, Mesa llvmpipe, Wizard) | **2,254 ticks in step** hub > drunare; no shared column differs; 75 messages (34 from the Windows copy); 7 arrows at 7 pitches (-54.7 to +65.0), 4 casts at 4 pitches (-17.4 to +16.3) |
| `groom3` | two Godot portals in scene mode (`local/aim/r8/room8.py`: room6.py with n2aim.py's looks and classes, `app view first` once in the game, `RTA_SHOTS_AIM=look`): the host picks "Where you look" on the room screen, both copies then say `fix_words` 16573 (bit 0x4000 + 189) | "aiming by looking: on for this game" on both; **2,333 ticks in step** hub > drunare; no shared column differs; 76 messages (38 from each); 24 arrows at 19 pitches (-52.6 to -1.6), 2 Shock of Frost at +28.9 and +29.6. (`groom2` before it: in step too, 2,332 ticks, but the portal kept the overhead view - `--view` is not taken in the portal - so nothing was sent: the sender wants a look view) |

Logs under `local/aim/r8/`. The Windows run is short for the reason `native-windows.md` gives (llvmpipe under emulation).

## 4. Not done, and what to know

- **Not exercised**: thrown weapons (`playerProjectile`: they also fall by 9 a tick, so a throw will need a little
  more pitch than the line of sight, Inferred), the four arrow skills and Multi Fire, Shock of Fire (`Sparks`) - in the
  class list, built, never launched in a run. Homing bolts (Disease Bolt, Holy Bolt, Holy Strike, Poison Bolt)
  are left to the game: it steers them every tick.
- The game still picks its target and tells it (the creature's slot 12 with kind 2 at the release, 1): an
  aimed arrow may miss the creature that was "shot at". The body still turns toward the game's target for a
  shot (`Player_findTarget` + turn); the look does not follow it any more in the mode.
- Over the shoulder the line starts at the character, not at the eye: what is aimed at is along the look's
  direction, a little beside the picture's middle (parallax). Not measured.
- During a view transition the pitch sent is that of the picture being blended (`look_pitch` of the shown
  view): `w1`'s sixth cast left at -2.5 degrees with the shoulder view at 30 still easing in.
- A bow next to a monster swings instead of shooting (1): melee is not aimed.
- The emulator application does not have the mode; a room with it cannot start with it on. (Windows, Linux and
  Godot have it since 2026-10-21: 3.5.)

## 5. How to repeat

```sh
python3 tools/recomp/app/build.py --no-game --as rta_aim2
python3 tools/recomp/app/build.py --original --no-game --as rta_aim2_orig
python3 local/aim/rig/check.py off-over rta_aim2_orig overhead
python3 local/aim/rig/check.py off-first rta_aim2_orig first
# offline (RTA_DISC set by run.sh): cd local/aim; ADDRS="646dc0 647cc0 6481c0 6486c0 648bc0" python3 t4.py r5 4
#   PROG=rta_aim2 AIM_LOG=1 ./run.sh r5 r5/run.rig --aim look > r5/log.txt; python3 flight2.py r5/log.txt
# online: RTA_NET2_SERVICE=127.0.0.1:41994 N2_APP=.../rta_aim2 N2_HOST_EXTRA="--aim look --view first" N2_JOIN_EXTRA="--view first" \
#   python3 local/aim/net/n2aim.py OUT --port 41994 --players 2 --program local/aim/net/as-app.py --play 1500 --level drunare --play2 3600
#   python3 local/aim/net/summary.py OUT/run1/host.tick.tsv
```

`AIM_LOG=1` prints every projectile turned (tick, player, class, velocity before and after, heading, pitch).

## 6. Ledger rows (FINDINGS.md, "First person, strafing and the late save")

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| FP10 | A bow shot's velocity is 1000 units a second along `facing + spread` and level within 1.7 degrees without a target, or toward the target's middle (vertical part clamped to 0.3 of the forward) with one; `MissileWeapon` keeps it at +0x1b0 without gravity or homing and is drawn turned about the vertical only (+0x38) | Read, Ran | 0x1a8cb0-0x1a8ed8, 0x1513a4-0x1513b0, 0x15153c, 0x15257c; this document 1 |
| FP11 | Of the players' projectiles, the arrow skills, Multi Fire, Shock of Fire and Shock of Frost keep their launch velocity; Disease Bolt, Holy Strike, Holy Bolt and Poison Bolt rebuild theirs every tick (homing); thrown weapons lose 9 of vertical speed a tick | Read | the runs in this document 1 |
| FP12 | With the look-aim mode (the pitch by game message 4 sub-type 3 into guest memory at 0xE0A00, the heading from the yaw word, the new projectiles turned after `Player_run`), arrows and bolts leave at the look's pitch and heading to a tenth of a degree, and two native copies stay in step through a level change, a fight, deaths and a reload (5,499 to 6,100 ticks, three launches) with 16 to 20 arrows and 8 or 9 casts each at many pitches | Ran | this document 3.1, 3.2 |
| FP13 | The look-aim code linked in and the mode off leaves the rig comparison byte for byte the reference in overhead and first person | Ran | this document 3.3 |
