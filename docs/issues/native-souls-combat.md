# Hardcore mode (souls-style combat) for the native build

**Name (2026-10-21):** the player-facing name is **Hardcore mode** (room screen "Combat: Classic / Hardcore", the
room's warnings, `--combat hardcore`, help texts). `--combat souls` and `combat.mode = souls` stay accepted as the
earlier name. Internal names are kept to avoid churn: `soulscombat.{h,cpp}`, `soulscombat::Tuning`, `hud/souls.gd`,
the `SOUL` block, `app souls ...` script commands, `rtag_has("souls")`, `souls_want=` / `souls_on=` in `rtag_info`,
the net2 hook names and the stderr prefix `souls:`.

Started 2026-10-19 (the owner: "what about elden ring style combat?"). An optional combat mode
on top of the views that look along the ground (chase, shoulder, first person:
[the camera](native-first-person.md), [the controls](native-first-person-controls.md)): lock-on,
a dodge with invulnerable ticks and a cooldown, stamina that attacks, dodges, blocks and sprinting
spend, light and heavy attacks (tap / hold), blocking that costs stamina instead of health, and
enemies that stagger when their poise breaks. Every statement says **Ran** (with what was seen)
or **Read** (with the address). Scripts, logs and pictures are game output and stay under
`local/souls-combat/` (and the Elden Ring reference data under `local/souls-ref/`); nothing of
either is in the repository.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-25, fourth round - attributes (Vigor, Mind, Endurance, Strength, Dexterity, Intelligence, Faith) and the spellbook
(the class's skills attuned to slots at save points, spell scaling by Intelligence and Faith), the character sheet in the
native overlay and in Godot (`hud/sheet.gd`); built, run offline, in Godot and in a room. Not committed.**

- Program: `local/recomp-out/bin/rta_app_next`, `rta_app_next_orig` (the rig). Design 2.9, numbers 3.4 (benched against the
  owner's copy: the stat curves and the catalysts), runs 4.9 / 4.10.
- **Ran**: mode off, the rig byte for byte in overhead and first person with the final sources (`off-over11`, `off-first11`);
  offline every piece with its numbers (4.9); Godot with the r26 library (`local/godot-r26/test/sheet1`); a two-copy room
  (`stats2c`, 5,630 ticks, 383 columns) through a level-up, points spent, a spell taken out of its slot, a level change,
  deaths and reloads.
- Built: Windows (`build_win.py --no-game`), Linux aarch64 in the container, the Godot library (`local/godot-r26`, snapshot
  `--refresh` + `lib`); `hud/sheet.gd`, `hud/souls.gd` parsed by Godot 4.5.2 `--check-only`.
- **Not done this round**: a three-copy room; a spell hit inside a room; a memory-card save and load with the spot; the
  game's own level-up screen extended (its rows are fixed in its code: the mode's points have the mode's own screen); a
  Windows or Linux run.

**2026-10-21, third round - weapons (equip load, weapon classes, stat scaling with grades, upgrades +1..+10 with the game's
own whetstones, weapon arts from the game's own skills, two-handing); built, run offline and in rooms. Not committed.**

- Program: `local/recomp-out/bin/rta_app_next` (fix set, the mode), `rta_app_next_orig` (for the rig). `bin/rta_app` was not
  touched.
- **Ran**: mode off, the rig byte for byte in overhead and first person with the final sources (`off-over9`, `off-first9`);
  offline every weapons mechanic with its numbers, several classes (4.7); a two-copy (`weap2b`, 5,734 ticks) and a
  three-copy room (`weap3a`, 5,703 ticks, all pairs) with Hardcore on through the drunare fight, upgrades at valor's save
  point, weapon arts, deaths and the level change valor > drunare, every pair of tick logs equal in every column (4.8).
- Built: Windows (`build_win.py --no-game`), Linux aarch64 in the container, the Godot library (snapshot `--refresh` +
  `lib`); `hud/souls.gd` parsed by Godot 4.5.2 `--check-only`.
- Design 2.8, numbers 3.3 (benched against the owner's copy), runs 4.7 / 4.8.
- **Not done this round**: the spear's chip (player against player only: no PvP run); in a room a two-handing toggle and a
  player's hit on a creature (scaled hit, material drop, interrupt: offline only); a weapon art or an upgrade seen by a
  person or in a running Godot build; the game's own shop / workshop screen (not hooked: the upgrade is the mode's own
  action at save points, 2.8); an upgraded save loaded by the unmodified program; a Windows or Linux run.

**2026-10-21, second round - Elden Ring mechanics added (parry and riposte, stance-break critical, guard counter,
backstab, flasks, the death drop), renamed Hardcore mode; built, run offline and in rooms. Not committed.**

- Program: `local/recomp-out/bin/rta_app_next` (fix set, the mode), `rta_app_next_orig` (the disc's game with the
  mode's code linked in, for the rig). `bin/rta_app` was not touched.
- **Ran**: mode off, the rig byte for byte in overhead and first person with the final sources (4.1, `off-over7`,
  `off-first7`); offline every new mechanic with its numbers (4.5); a two-copy room (`hard2c`, 5,730 ticks) and a
  three-copy room (`hard3a`, 5,702 ticks, all three pairs) with Hardcore on, through fights, deaths with a drop,
  recoveries, the reload after everybody died and save point refills, every pair of tick logs equal in every column
  (126 columns, the new ones included) (4.6).
- Built: Windows (`build_win.py --no-game`), Linux aarch64 in the container (`build_linux.py --docker arm64
  --no-game`), the Godot library (`tools/godot/build.py snapshot` + `lib`); `hud/souls.gd`, `room.gd`, `gameflow.gd`
  parsed by Godot 4.5.2 `--check-only`.
- **Not done this round**: a parry, riposte, backstab, stance-break critical or guard-counter hit inside a room (the
  drawn input of the room runs never landed a player hit on a creature: they are equal on every machine by
  construction, but only Ran offline); a Linux container room and a Windows run; the new HUD pieces seen in a running
  Godot build or by a person; "dying again loses it" Ran offline only.

**Earlier (2026-10-20/21, first round):** **2026-10-20 - built, run offline and online; the proof runs of part 4 passed. Not committed.**

- Program: `local/recomp-out/bin/rta_app_combat` (the fix-set game with the mode),
  `rta_app_combat_orig` (the game as on the disc with the mode's code linked in, for the rig).
  `bin/rta_app` was not touched.
- Code: `tools/recomp/app/soulscombat.{h,cpp}` (new), hunks in `fpcontrols.{h,cpp}`,
  `app_main.cpp`, `settings.h`, `build.py`, `rt/rt.h`, `rt/runtime.cpp`, `net2/hooks.h`,
  `net2/launch.cpp`, `net2/session.cpp`, `net2/session_net.cpp`; Godot: `hud/souls.gd` (new)
  and three lines in `hud/hud.gd` (part 6).
- **Ran**: the rig comparison with the mode off is byte for byte the reference in overhead and
  first person (4.1); offline every mechanic (4.2); two and three copies in one room with the
  mode on, the host's choice taken up by the joiners, through a level change and fights, every
  pair of tick logs equal in every column including the mode's own (4.3); the pictures (4.4).
- **2026-10-20**: wired into the Windows and Linux programs as in `app_main.cpp`; on Linux Ran
  (mode off: the rig byte for byte; a Linux + Mac room with the mode through the drunare fight,
  5,016 ticks in step: `docs/issues/native-linux.md`), on Windows Built only.
- **2026-10-20, later**: wired into the Godot library and the portal's room screen, Ran in a Godot room (part 6b).
- **2026-10-21**: benched against the owner's own copy of the reference game (3.1): `dodge_cooldown` 10 -> 0,
  `poise_miniboss` 650 -> 800, the rest kept; Ran after it: the rig with the mode off byte for byte, a two-copy room in step.
- **Not done**: Windows run (built, never started); the emulator application (the mode is native C++ only, no pnach
  section); an online game through the old lobby (the mode stays off there by design, 2.2);
  nobody has played it with hands; the Godot HUD part was parsed by Godot 4.5.2
  (`--check-only`) but not seen in a running Godot build (the library would need
  `soulscombat.cpp`; see part 6).

---

## 1. What the game has already (Read, then Ran)

| Wanted | What the game has | Where |
|---|---|---|
| a dodge animation | no roll or dive for players. The nearest is the **block move**: R1 held, L1 pressed while blocking -> action state 0xb, clip `anim(0xa4)` of the weapon class, the stick ignored for 47 ticks. **Ran**: it is a hop **backwards**, about 49 units in 45 ticks, then state 8 or 2 | `Player_tryBlockMove` 0x1bf150, state 0xb 0x1a6588 (`docs/spec/player-tick.md` 6, 9.3); `local/souls-combat/explore` |
| a heavy attack | the old ability id 0x25: state 1 with request 2 (`P+0x44c`), clip `anim(0x64)`, swing length 0.857 s, one combo step, turn rate 2.8 | state 2 A.4 (0x1a71f8-0x1a7310) |
| hyper-armour | `Player_processDamage` does not roll the 4 % stagger for a player whose request is 2 (the heavy attack), nor in states 3 / 7 | 0x1b3718-0x1b3750 |
| a forced stagger | pending-damage flag 0x4000000 makes `Player_processDamage` stagger (state 3) whatever the roll | 0x1b37c4-0x1b37e8 |
| blocking | states 8 / 0xb, in `Player_takeDamage`: a hit from the front (attacker not behind the facing) comes to 0 (half with flag 0x20000); not for flag 0x40 | 0x1b5440-0x1b5628 |
| a stun for creatures | virtual slot 30 `(frames, 1)` (the stun skill's effect), stun timer +0x31c | `docs/spec/combat.md` 3.2; `docs/creatures.md` |
| boss rank | `creature_bossRank` 0x10d940: 0 / 1 / 2 | `docs/spec/combat.md` 4.3 |
| sprint | none; the run speed has a per-player multiplier (record +0x4c20) | `docs/spec/movement-camera.md` 4.1(b) |
| stamina, poise, lock-on | none | |

Virtual tables: the object's table is at +0x48, slot k's function at table + 8k + 4 (**Ran**:
Player 0x511308: slot 1 0x1a1bb8, slot 2 0x1b5330, read from memory).

## 2. Design

### 2.1 The rule

Everything that changes the simulation is computed in the tick, on every machine, from what
every machine has alike: **each player's lockstep controller row** (`g_pads[slot]` 0x41bfd8 +
slot x 0x58, written by the tick from the input record) and the game's own state. Nothing reads
the local controller, the camera, the clock or the renderer when it decides. Integer arithmetic
for the mode's own numbers; the few float operations (a damage scale, a pending-damage add, the
sprint speed) are single IEEE operations of the same build with `-ffp-contract=off`.

### 2.2 One switch for the whole game

- Offline: the setting `combat.mode = souls` (settings file) or `--combat souls`.
- Online, a room of our own (net2): a **room option**. A copy says it has the mode in the
  description it gives the room ("copy" line): bit 0x8000 of its word count (no fix set has
  that many words) and, folded into the figure by XOR, an FNV-1a figure of the mode's numbers
  (so the numbers must be the same everywhere too). A joiner takes the host's choice and says
  so again (`net2_set(n, "copy", ...)`, new); a copy that cannot do it (any build without this
  file, the Godot library today) keeps the bit clear, the room shows "The souls-style combat
  mode is on for A and off for B: every copy must have it. Do not start.", **`net2_start`
  refuses**, and a copy that is started anyway does not launch ("its copies do not all have the
  souls-style combat mode: not launching"). At the launch every copy is told the room's mode
  (`net2hook::souls_room`); it holds for the whole game and ends with it.
- Online through the old lobby (netdrv's own path): there is no room to agree in; the mode is
  **off** there whatever the setting says.

### 2.3 Where the simulation is reached

`rt_replace_function(address, fn)` (new, `rt/runtime.cpp`) puts a native function in the
runtime's table of translations for calls through a pointer; the original runs inside it.
Three functions of the game are reached that way (virtual slots: **Ran**, the counters of 4.2
count them):

| Wrapped | Slot | What the mode does there |
|---|---|---|
| `Player_run` 0x1a5030 | Player 4 | before: the tap / hold of attack and of L3, the stamina gate, sprint, the heavy attack's start; after: the dodge's start, the stamina and timers |
| `Player_takeDamage` 0x1b5330 | Player 2 | the dodge's invulnerable ticks (the hit is not taken), the block's cost, the guard break |
| `Creature_takeDamage` 0x116638 | Creature 2 | a heavy attack's weight, poise, stagger |

They are put in place only when the mode becomes active; with the mode off the program is the
program without this file (4.1).

### 2.4 Inputs - nothing added to the input record

| Input | Bit of the row | Meaning in the mode |
|---|---|---|
| attack (the slot's own button, table 0x41b980) | as the game has it | held back while held: released before `heavy_hold` ticks = one press for the game (its swing, its combo step); held `heavy_hold` ticks = the game's heavy attack |
| **L3** | 0x200 | tap = dodge; hold `sprint_hold` ticks while moving = sprint. `Player_run` does not use it (the 16 buttons of the record are all given meanings by the game, L3 the camera's "behind the character", **Read**: `docs/spec/movement-camera.md`, 1.3 of the controls notes); whatever else reads it reads the same lockstep bit on every machine, so it is the bit taken. Not proven: that nothing else in the simulation reacts to it (no reaction was seen) |
| block (table 0x41b9d0) | as the game has it | the game's block; a blocked hit costs stamina |
| R3 | 0x400 | not sent: on this machine the lock-on toggle (and the map stays shut in a look view) |

Keys and buttons (`fpcontrols`): L3 = X key, mouse button 4, the stick click; lock-on = Tab
(the R3 key), mouse button 5, R3; light / heavy = K or the left mouse button, tapped or held;
block = E, Shift, the right mouse button.

### 2.5 State

A block of guest memory at **0xE0800** (the first megabyte, where the game has nothing;
`tools/recomp/soak` uses 0xE0000-0xE004F): "SOUL", version, mode, a count of player ticks,
poise breaks, the poise held, hits not landed, blocks paid; per player (0x40 bytes at +0x40 +
slot x 0x40): stamina, refill delay, flags, dodge tick, dodge cooldown, attack held, L3 held,
guard broken, last state, last combo step and six counters (`soulscombat.h` lists the words).
Every machine writes the same numbers in the same tick: they are columns of the tick logs of
4.3. The poise of creatures is kept in the program, keyed by the creature's object; object
addresses can differ between machines, but an entry is only ever used by its own creature,
never chosen between by address, cleared at a level change and when its creature dies; the
held sum goes to the block. The **lock-on is presentation**: it reaches the simulation only as
the yaw word, like the mouse (the controls' rule, FP2), and the strafe mode (fix set, FP7) turns
the character to it; its target and position are written to the block's local part (+0x180 on),
which differs between machines by design and is not compared.

The prediction copy (net games, own player only) runs the same wrapper with its own record of
presses, using the real player's stamina, so the dodge and the heavy attack show without waiting
for the copy's next re-clone; it changes no number of the block.

### 2.6 The mechanics (first round)

- **Stamina**: 0 to 100.0. Spent by a swing or combo step, a heavy attack, a shot, a dodge,
  sprinting and blocked hits; refills when nothing was spent for `regen_delay` ticks, slower
  while blocking. An attack, a heavy attack or a dodge is **refused while it is 0** (any stamina
  left lets the action start, as in the reference; it then ends at 0).
- **Dodge**: the block move, with the character first turned so that the backward hop goes where
  the move stick points (`atan2_16(stick) - yaw word - 0x41c2 + 0x8000`, the game's own target
  facing turned round); with the stick at rest it is a back-step. Ticks `dodge_iframe_first` to
  `dodge_iframe_last` no hit lands (except the 1,000,000 a dropped player's character is killed
  with); the rest of the hop is not a block (flag 0x40 is given to its hits). Then a cooldown.
- **Light / heavy**: the game's own swing and combo; the game's own heavy attack (its clip, its
  length, its hyper-armour) started as the game starts it, without the ability and its mana.
  Against creatures a heavy hit does `heavy_damage_percent` of its damage.
- **Blocking**: the game decides what is blocked (front / behind). A blocked hit costs
  `cost_block_base + cost_block_per_hp_percent x (damage as a percentage of maximum hit points)`;
  when that is more than what is left the **guard breaks**: stamina 0, the hit lands whole, the
  game's forced stagger, no block for `guard_break_ticks`.
- **Poise**: every hit by a player adds poise damage to the creature (light, heavy, shot); at the
  limit of its boss rank the creature is stunned by its own slot 30 for `stagger_ticks` and its
  poise starts again; poise damage is forgotten after `poise_reset_ticks` without a hit.
- **Lock-on** (`fpcontrols`): the enemy nearest the middle of the picture within `lock_range`;
  the look turns to it by itself (`lock_turn` of the bearing a blank, at most `lock_turn_max`
  degrees); a mouse flick of `lock_flick` degrees in one blank or the right stick past 0.85
  changes to the next enemy on that side; the lock lets go when the target dies, leaves range
  or the view stops steering. While locked the strafe mode is asked for in every look view.

### 2.7 The second round (2026-10-21): Elden Ring mechanics

Everything below is in the same three wrappers plus one more (`Savepoint_run` 0x28cdd0, SavePoint slot 4, optional:
without it no save point refill), only when the mode is in force, and every number is in `soulscombat::Tuning` (3.2).
The block's version is 2: a header extension (+0x20..+0x3c, +0x300..+0x31c) and a second per-player part at
+0x200 + slot x 0x40 that is **kept over a death, a respawn and a level change** (flasks, the drop) - `soulscombat.h`
lists the words. All of it is written in the tick by every machine alike and is a tick-log column of 4.6.

| Mechanic | Input (lockstep row) | Rule | The game's own pieces used |
|---|---|---|---|
| **Parry** | block held + L3 pressed (keys: hold E / Shift / right mouse, tap X / mouse 4). L3 is otherwise the dodge; with the block held its press is spent on the parry (neither a dodge nor a sprint) | costs `cost_parry`; ticks `parry_first`..`parry_last` after the press a hit from a **creature** (its slot 2 is `Creature_takeDamage`) within `parry_reach` units is parried: it does not land, the attacker is stunned `parry_stagger_ticks` and is open to a riposte for `riposte_window`; from `parry_last` to `parry_recovery` a missed parry leaves the guard open (hits get flag 0x40, not blocked). One parry per press | the guard is raised again by the game (block flag `P+0x47f` cleared: state 8 restarts its own `anim(0x84)`); the stun is the creature's own slot 30 |
| **Riposte** | any melee hit (light or heavy) on the parried creature inside the window | damage x `crit_riposte_percent`, then the creature stunned `crit_stun_ticks`; the window ends | slot 30 stun |
| **Stance-break critical** | a heavy hit within `stance_crit_window` ticks of the creature's poise break | damage x `crit_stance_percent` (one per break) | |
| **Backstab** | a light hit with the attacker inside `backstab_half_angle` of straight behind the creature's facing, within `backstab_reach` | damage x `crit_backstab_percent`; not again on that creature for `backstab_cooldown` ticks. The facing's direction is the game's own `math_cos16` / `math_sin16` (no host trigonometry in the decision) | |
| **Guard counter** | attack pressed within `guard_counter_window` ticks after a blocked hit was paid (not a guard break), in state 2 or 8 | the game's heavy attack at once (the press is spent), from the block too; costs `cost_heavy`; its hit does `guard_counter_damage_percent` and `poise_guard_counter` poise damage. The block's clips fill the tracks, so the track-count gate of the hold heavy is not applied (anim_start replaces the top track when full) | the heavy of 2.6 |
| **Flasks** | the health potion button (R2; the game's table 0x41ba10) | the game's own health potions are never used in the mode (the button is taken from the row); with a flask left, in state 2 on the ground: the drink, `flask_drink_ticks` long and committed (no move); at its `flask_heal_tick` the flask is spent and `flask_heal_percent` of the maximum hit points goes to the game's own pending-heal fields (`R+0xb4`, rate `R+0xb8` over `flask_heal_spread` ticks: `Player_regenHealth` delivers it). Full again (`flask_count`) at a new player object (level entry), after a death (respawn, reload after everybody died) and when alive within `flask_refill_radius` of a save point | the drink is the weapon class's cast clip `anim(0x6c)` played once in the game's hit-reaction state 3 (steps the clip, no move, back to state 2 at its end); in a net game the clip ends sooner, so the state is held until the drink's length |
| **Death drop** | - | at the death (state 4) `drop_percent` of the carried gold (`R+0xe4`) and the spot (`P+0x10`) and level (FNV-1a of the level name) are written; at the first tick alive again the share is taken from the gold *then* (a game that restores the record on everybody's death has done it by then; at most what is there) and left at the spot; alive within `drop_radius` of it on that level: the gold comes back; dying again before that loses it | gold and position of the record and the object |

Further fixes this round, mode on only: a heavy of the mode that is left before its hit (the block taken in its combo
window, a stagger) no longer leaves the attack request 2 behind (the game kept it in states 2 and 8 and started no
further swing); a heavy hold that reaches `heavy_hold` while a swing is still running starts the heavy as soon as the
swing has ended (it was lost before).

Presentation: the native overlay draws flask pips left of the stamina bar, a gold line over the bar in the parry
window, a red line under it while a riposte or guard counter is open, and a pale green upright diamond over this
player's drop on this level (local word +0x19c); `hud/souls.gd` draws the same in Godot (pips and a count, the lines,
the drop marker through `gs.project`).

Test aids (they change the simulation; never used outside tests): `app souls turn | pose front | pose back | go-drop`
(offline only, refused online), and the block word +0x31c: slot + 1 puts that player on its drop in its next tick -
written by every copy in one lockstep tick through n2party's `--tick-do`, so a room stays in step.

### 2.8 The third round (2026-10-21): weapons

Everything below is in the same wrappers, only with the mode in force; every number is in `soulscombat::Tuning` (3.3). The
block's version is 3: a weapons part per player at +0x400 + slot x 0x60, header words +0x320..+0x33c, the level's save
points at +0x380 (`soulscombat.h` lists the words). All of it is written in the tick by every machine alike and is a tick-log
column of 4.8. Nothing of the game's or Elden Ring's data is in the repository: the classes are decided at run time from the
game's own item records, and every figure is ours ("benched against the owner's copy", 3.3).

| Mechanic | Input (lockstep row) | Rule | The game's own pieces used |
|---|---|---|---|
| **Equip load** | - | the sum of the game's `item_getWeight` 0x103e08 of every equipped item (the 17 equipment pointers `R+0x43f0`, each item once, per unit for a stack, not the ammunition slot) against a capacity `load_base + load_per_stamina x stamina + load_per_strength x strength` (the effective statistics `R+0x90`, `R+0x9c`); below `load_light` % light, below `load_medium` % medium, up to 100 % heavy, above it overloaded. By tier: the dodge's movement (the hop's own steps of each tick lengthened or shortened by `tier_dodge_move`; overloaded: no dodge), its invulnerable ticks (`tier_iframes`), the stamina refill (`tier_regen`) and the sprint's extra speed (`tier_sprint`; overloaded: no sprint) | item_getWeight; the block move (2.6) |
| **Weapon classes** | - | from the definition row of the weapon in hand (the active set's primary `R+0x4434`, else equipment slot 0 or 2): animation class (`+0x1e`) 4 / 6 bow (thrown weapons too); 1 / 2 great weapon; 3 staff when blunt (damage bit 1), else spear / polearm; one-handed blunt mace; one-handed edged of weight 1 or less dagger; one-handed edged whose name has "axe", "pick", "cleaver" or "hatchet" axe; any other sword. Per class: stamina of light / heavy / shots (`wc_stamina`), poise damage (`wc_poise`), the recovery after a swing before the next swing starts (`wc_recovery`: a tap inside it is held and given when it ends, at most half a second), the tick of a swing from which a dodge cancels it (`wc_cancel`; never for great weapons and bows) - the attack speed is these windows, the animation's playback rate is not touched (sync) | the swing's own state 1 and combo |
| **Hyper-armour** | - | only a great weapon's heavy keeps the game's own hyper-armour (`Player_processDamage` skips the stagger for request 2); any other class's heavy hit by `heavy_interrupt_hp_percent` of the bar or more is staggered (the game's forced stagger, pending flag 0x4000000) | 0x1b3718 |
| **Spear chip** | - | a player's spear hit on a blocking player still lands `spear_chip_percent` of it (the game's creatures do not block, so this is the player-against-player case) | `Player_takeDamage` |
| **Dagger criticals** | - | ripostes and backstabs x `wc_crit` (daggers 110 %) | 2.7 |
| **Stat scaling** | - | every hit of the player on a creature x (100 + upgrade + scaling) %: scaling = sum over strength, dexterity, intelligence of the class's coefficient (`wc_str`, `wc_dex`, `wc_int`, +`upgrade_correct_percent` per upgrade level) x curve(statistic) / 100, the curve linear between `scale_stat` / `scale_value`. Grade letters from the coefficient: S 175, A 140, B 90, C 60, D 25, E above 0 | `R+0x90`, `+0x94`, `+0x98` |
| **Two-handing** | L3 held + swap (L1; keys hold X, press Q / the mouse wheel) | toggles; not for bows, thrown weapons and dual wielding. While on: strength x `twohand_strength_percent` for the scaling, poise damage x `twohand_poise_percent`, and the guard uses the weapon (below). The shield stays equipped (its weight counts) but is not used. The swap press is not given to the game | |
| **Guard with the weapon** | - | a blocked hit costs x `wc_guard` % when two-handing or with no shield in the shield slot | 2.6 |
| **Upgrades** | L3 held + use (Square; keys hold X, press J / Space) near a save point | +1..+`upgrade_max` for the weapon in hand: `upgrade_gold(n) = upgrade_gold_base x (100 + upgrade_gold_step x (n - 1)) / 100` gold and `1 + (n - 1) / upgrade_material_every` upgrade materials; each level +`upgrade_damage_tenths` / 10 % damage and +`upgrade_correct_percent` % to the scaling coefficients. "Near a save point": within `save_reach` of one of the level's save points, which `Savepoint_run` writes into the block (each machine alike). The use press is not given to the game. The game's own shop / workshop screens were not hooked: their input is per machine (menus) and reaches the simulation through messages (`docs/ui.md`), so the upgrade is the mode's own action at save points, made in the tick from the lockstep row | `Savepoint_run` 0x28cdd0 |
| **Upgrade material** | - | the game's own item: the lowest-level reagent (definition flag bit 35) of the game's table whose name has "whetstone" (found at run time). A creature killed by a player leaves one with `material_drop_normal` / `_miniboss` / `_boss` % by its boss rank; the roll is the game's shared generator state at the kill, **read, not drawn** (`(g_randSeed >> 16) mod 100`), the item made by the game's `loot_spawnNamedItem` 0x100ba0 (which draws as for any drop, on every machine alike); picked up like any item. Spent from the bags (stack count, or the game's `inventory_removeItem` for the last of a stack) | the game's item, loot and inventory |
| **Weapon arts** | L3 held + attack (keys hold X, press K / the left mouse button) | one per class (`wc_art`): **lunge** (daggers, spears: the game's skill 35 `charge`), **spin** (swords, axes: skill 41 `cyclone`), **slam** (maces, great weapons: skill 38 `groundpound`, its three shoves hit for `art_slam_percent` of the weapon's top damage), **bolt** (staves, bows: skill 37 `shock`, a projectile). Cast as `Player_castSkill` casts (the skill's slot 2 with the level 1 + upgrade, the player, a position and the facing; `creature_addSpell` 0x11a838 when a spell comes back) - not the player's rank and not its mana price: the mode's own cost, `art_mana_percent` of the maximum mana and `art_stamina_percent` of the heavy's stamina; `art_cooldown` after it. The lunge's and the bolt's damage is the skill's own fixed figure (made for higher levels), x `art_fixed_percent`. The spin and the slam play clips by name from the character's animation lump (`cyclone1.anm`, `dha_quake.anm`): a character without them (`res_find` 0x17365c asked first) gets the lunge. States 6, 9 and 10 of the skills are free of stagger by the game | skills 35, 37, 38, 41 |

**Where an upgrade is kept.** On the weapon's own item record, in two places the game never writes and no reader of it is
known (`docs/spec/items.md` 2: +0x06 and +0x44 are left as they lay in the parser's frame): +0x06 = 0x4800 | level, +0x44 =
0x4843 << 16 | level << 8 | a check (FNV-1a of the definition pointer and the level). Anything else there (the parser's
leftovers) reads as level 0; a check of 8 bits behind a 16-bit tag and the 16-bit word at +0x06 makes a false level from
leftovers about one in 2^40. So the upgrade **is on the memory card with the character** (the save holds the whole record,
`docs/audio-save.md`), **goes to every machine at a net game's launch** (`player_packRecord` sends the whole record,
`docs/player.md`), and follows the item when the game copies it whole (`inventory_giveItem` copies 0x48 bytes: a dropped
and picked-up weapon keeps it). It is lost where the game copies only the mutable fields (`item_copyMutableFields` leaves
+0x06 and +0x44 of the destination alone). The unmodified game ignores both places (Read: no reader; not run with an
upgraded save on the unmodified program). No sidecar file.

Test aid (changes the simulation; never used outside tests): the block word +0x33c = slot + 1 | count << 8 gives that player
`count` upgrade materials in its next tick through the game's own `inventory_giveItem` (a room's `--tick-do` writes it on
every copy in one lockstep tick; a poke offline).

Presentation (our own text): the native overlay writes the weapon card over the stamina bar with the overlay's own 5 x 7
letters (`testerkit::text`, new): the weapon's name, +level, class, the grade letters (STR, DEX, INT for staves), the damage
percent, "2H"; the equip load against the capacity and its tier (amber heavy, red overloaded), the whetstones carried, the
art's cooldown; near a save point the next upgrade's price. `hud/souls.gd` draws the same three lines in Godot from the
block (the weapon's name from the local words +0x1a0).

### 2.9 The fourth round (2026-10-25): attributes and the spellbook

Everything below is in the same wrapper of `Player_run` and in `Creature_takeDamage`, only with the mode in force; every
number is in `soulscombat::Tuning` (3.4). The block's version is 4: an attributes part per player at +0x600 + slot x 0x80,
mana costs and ranks per player at +0xa00 + slot x 0x40, header words +0x5e8..+0x5fc (`soulscombat.h` lists the words). All
of it is written in the tick by every machine alike and is a tick-log column of 4.10. Nothing of the game's or Elden Ring's
data is in the repository: the spells are the character's own ability records read at run time, their names the skills'
own internal names read from memory for the HUD, and every figure is ours ("benched against the owner's copy", 3.4).

| Attribute | Where it is | What it does in the mode |
|---|---|---|
| **Vigor** | the game's stamina statistic (record +0x84 base, +0x9c effective) | the game's own maximum hit points (`level x a + stamina x b - c`, `player_recalcStats`) |
| **Mind** | the mode's: the class's start + the points spent (the save spot) | the maximum mana: the game's own + `mana_per_mind_permille` of it per point spent; spell slots |
| **Endurance** | the mode's | the stamina bar `stamina_max + stamina_per_endurance` per point spent; the equip load's capacity (`load_per_endurance`; the weapons round had the game's stamina here) |
| **Strength** | the game's strength (+0x78 / +0x90) | the game's own (attack rating, load limit); the weapons' scaling; the capacity |
| **Dexterity** | the game's dexterity (+0x80 / +0x98) | the game's own; the weapons' scaling |
| **Intelligence** | the game's intelligence (+0x7c / +0x94) | the game's own maximum mana; the staves' scaling; spell scaling; spell slots |
| **Faith** | the mode's | spell scaling |

| Mechanic | Input (lockstep row) | Rule | The game's own pieces used |
|---|---|---|---|
| **Points** | - | every level the character has (record +0x59, the game's own experience and level-up) gives `points_per_level` of the mode's points: unspent = (level - 1) x `points_per_level` - the points spent. The game's own three points a level stay the game's: its level-up screen spends them on Vigor, Strength, Dexterity and Intelligence as before (the screen is per machine and reaches the simulation through inventory message 6, `docs/spec/levelup.md`; it was not extended: its rows are fixed in its code) | `player_giveExp` 0x1d3150 (the level), the level-up screen |
| **The character screen** | L3 held + potion B (L2; keys hold X, press 1) within `save_reach` of a save point, standing (state 2) | opens the mode's screen (a word of the block: simulation state); while open the character stands (the stick and every button are taken from the row before the game's run and put back after), up / down choose a row (Mind, Endurance, Faith, then one row per spell of the book), right spends a point (up to `stat_max`, at most 127 spent on one) or puts the chosen spell into a free slot, left takes it out of its slot; block, L3 + L2 again, leaving the save point, a hit that changes the state or a death close it | `Savepoint_run` (the save points, 2.8) |
| **Spellbook** | - | the character's ability records (15 at record +0x4440) with a skill id 1..101, not the older heavy attack (0x25, the mode's hold). Spell slots = `slot_base` + Mind / `slot_per_mind` + Intelligence / `slot_per_int`, 1..`slot_max` (at most 9); the attuned spells are the marked records, at most the slots (the first in record order). Until the screen is used the first spells of the book are attuned | the ability records |
| **Attunement** | ability A / B (the game's own skill buttons, tables 0x41b990 / 0x41b9a0) | a press of a skill button whose bound record (+0x4a84 / +0x4a85) is in the book and in no slot is taken from the row (not cast; counted as refused); a spell in a slot is cast by the game exactly as before (its state 5 or instant cast, its mana price, its recast) | `Player_run` state 2 A, instant abilities |
| **Cast cost** | - | the game's own: `manaCost(rank)` (the skill's virtual slot 5 at the character's rank of it; the older records' +0x2c), read in the tick for the sheet | the skill's slot 5 |
| **Spell scaling** | - | a cast is seen when the game's recast counter (object +0x4ae) starts from 0 in the run and the selected record is a spell (a skill that is not passive and not of kind 8 - the bow and axe skills fire through the shot -; of the older records not the arrows). For `spell_hit_ticks` after it (ended early by a shot or a death) every hit of the caster on a creature that is not a swing (state 1) or a weapon art is the spell's: x (100 + (`sc_int` x curve(Intelligence) + `sc_faith` x curve(Faith)) / 100) % by the class, in place of the weapon's percentage (the weapons round applied the weapon's to those hits too). Grade letters as the weapons' | `Creature_takeDamage` |

**Where it is kept.** Mind, Endurance, Faith (the points spent on each) and the attuned spells are kept in the last 6 bytes
of the player record, which the game never reads or writes: +0x4c2a..+0x4c2f, after the marker byte +0x4c29 that
`player_initNewCharacter` and `player_importCharacter` set. `tools/fieldxref.py 4c2a-4c2f --static 4d8af0,4c30,4` finds no
access in any function (+0x4c29 only the two marker stores); the whole-record copies take them along: `net_launchUpdate` (the
launch's copy of every record), `save_packLocalPlayer` / `save_unpackLocalPlayer` and the memory card's whole record
(`save_snapshotPlayer` rewrites only the item pointers, `docs/audio-save.md`). Layout, 48 bits, low first: Mind, Endurance,
Faith (7 bits each), the attuned ability records (15 bits, one per record), the tag 0xa (4 bits), a check (FNV-1a of the 40
bits below it, 8 bits). Anything else there reads as "nothing spent, the first spells attuned"; a fresh record has zeros
there. **Ran**: kept through a level change offline (`t6/lc`) and in a room through the level change, four deaths and two
reloads after everybody died (4.10). A first try used +0x43e0..+0x43ef (no access found there either), but **Ran**: a level
change clears them with the object pointer +0x43d8 (a block clear that the cross-reference does not see) - not used. So the
attributes are on the memory card with the character and go to every machine at a net game's launch, like the weapons'
upgrades (2.8). The unmodified game ignores the bytes (Read, as above; not run with such a save on the unmodified program).
No sidecar file. Attunement is by ability-record index: a skill learned later that makes the game rebuild its records in
another order can move a mark to another spell (the same on every machine; Read only - not seen). The game's own statistics
(Vigor, Strength, Dexterity, Intelligence) are not changed by the mode: a character played in Hardcore and then in Classic has
exactly the game's own statistics.

**The maximum mana.** The game rewrites record +0xc4 whenever it recalculates the character (a level gained, an item put on
or off, a new object; `player_recalcStats` 0x1b6458 for every player) and then puts the mana down to it. Each tick of a real
player, before and after its run: when +0xc4 is not the value the mode wrote last, it is the game's own new maximum (kept in
the block), and mana the game's recalculation cut is given back; then +0xc4 = the game's + the Mind bonus (single float
operations). At a new object the mode calls `player_recalcStats` once, so the game's own maximum is never mistaken for one
with a bonus saved in it.

Test aid (changes the simulation; never used outside tests): the block word +0x5e8 = slot + 1 | amount << 8 gives that
player `amount` experience through the game's own `player_giveExp` in its next tick (its levels, the game's points, the
refill) - a room's `--tick-do` writes it on every copy in one lockstep tick.

Presentation (our own text): the native overlay draws the **character sheet** - the class, level and points; the seven
attributes with the hit points, the mana, the stamina bar's length, the equip load and its tier; the weapon's grades and
percentage; the spells' grades, percentage and slots; every spell of the book with its rank and mana cost, the attuned ones marked;
on the open screen the chosen row marked and the keys - while the screen is open, and on this machine with
`app souls sheet`. Under the stamina bar: "LEVEL UP: N POINTS" while points are unspent, "CHARACTER: HOLD L3 + L2" near a
save point. Godot: `hud/sheet.gd` (new, added by `hud/souls.gd`) draws the same sheet from the block (P toggles it on this
machine), `hud/souls.gd` the level-up line and the stamina bar's length per player. The local words for them: +0x1c0 the
sheet asked for, +0x1d0..+0x1dc hit points and mana, +0x1e0 the book's records in order, +0xb00 the records' names.

## 3. The numbers

All of them are one struct, `soulscombat::Tuning` (`soulscombat.h`); `combat.<name> = value`
in the settings file or `app souls set NAME VALUE` changes one offline; online the room's figure
holds them equal. Stamina in hundredths, ticks of 60 a second.

### 3.4 The fourth round's numbers: attributes and spells (2026-10-25)

**Benched against the owner's copy** where its regulation has the figure: the stat correction graphs of hit points by Vigor,
mana (FP) by Mind, stamina by Endurance and equip load by Endurance, and the catalysts' scaling (staves, seals: median of the
base weapons' coefficients) - read by a local script beside the earlier ones (`bench_stats.py` under the local reference
folder; output under `local/stats-round/`), nothing of it in the repository. Our statistics are 2 x the reference's (3.3),
so one of the reference's levels (one point) is two of our points.

| What | Reference (the owner's copy) | Our value |
|---|---|---|
| points a level | one point a level | `points_per_level` 2 (our scale), on Mind, Endurance and Faith only (the game's own three a level stay on its four) |
| mana by Mind | 79 at 10, 121 at 20, 235 at 40, 350 at 60: about 5 % of a low-level bar per point | `mana_per_mind_permille` 25: +2.5 % of the game's own maximum per our point (5 % per reference point). Ran: a shaman of level 2, 42.2 -> 43.3 -> 44.3 with two points |
| stamina by Endurance | 96 at 10, 113 at 20, 130 at 30, 155 at 50: about 1.7 a point early | `stamina_per_endurance` 90 (0.9 of our 100 a point; 1.8 per reference point) |
| equip load by Endurance | 48 at 10, 64 at 20, 91 at 40, 120 at 60 | `load_per_endurance` 1.00 a point (the weapons round's value, now on Endurance) |
| hit points by Vigor | 415 at 10, 652 at 20, 1450 at 40 | the game's own (Vigor is its stamina statistic) |
| catalyst scaling | staves: strength 12, intelligence 90; seals: strength 15, faith 80 | `sc_int` / `sc_faith` by class: wizard 90 / 0 (a staff), cleric 0 / 80 (a seal), shaman 30 / 60, shadow knight 45 / 40, ranger 25 / 25, barbarian 0 / 20, berserker 0 / 20; the weapons' curve |
| not in the regulation (our own) | where the classes start, slots, the spell window | `start_mind` 20 / 36 / 28 / 26 / 44 / 20 / 38, `start_endurance` 40 / 30 / 36 / 34 / 24 / 42 / 28, `start_faith` 20 / 44 / 34 / 24 / 20 / 22 / 40 (barbarian, cleric, shadow knight, ranger, wizard, berserker, shaman); `stat_max` 198; `slot_base` 1, `slot_per_mind` 16, `slot_per_int` 40, `slot_max` 9 (a new wizard 4 slots, a new barbarian 2); `spell_hit_ticks` 240 |

Named for `combat.<name>` / `app souls set` as before; the class arrays as `<name>.<class>` with the labels barbarian, cleric,
shadowknight, ranger, wizard, berserker, shaman (e.g. `combat.sc_faith.cleric = 80`). `load_per_stamina` is still accepted
as the earlier name of `load_per_endurance`.

### 3.3 The third round's numbers: weapons (2026-10-21)

**Benched against the owner's copy** where its regulation has the figure: weapon rows by weapon type (median over the base
weapons of each type: weight, the four scaling coefficients, stamina guard, critical bonus), the player behaviour stamina of
each type's moveset (the first light and the first heavy), the equip-load curve of the stat correction graphs, the
reinforcement rows (the one-material-per-level kind: damage and scaling per level, price rate) and the weapon-art point costs
- read by local scripts beside the earlier ones (`bench_weapons*.py` under the local reference folder; output under
`local/weapons-round/`), nothing of it in the repository. The poise ratios come from the frame-data explorer's motion data
(the reference of 3.1) joined to the owner's weapon rows by name. Our values are our own, rounded near the ratios; the
statistics are mapped as our stat = 2 x the reference's (our characters start at 20-40 and gain 3 points a level to 80).

| What | Reference (the owner's copy unless said) | Our value |
|---|---|---|
| capacity | the equip-load curve: about 48 at endurance 10, 64 at 20, 91 at 40, 120 at 60, 160 at 99 | `load_base` 20.00 + 1.00 a stamina point + 0.25 a strength point: a new character 55-70, loads of the starting gear 17-31 (light or medium) |
| tiers | light below 30 %, medium below 70 %, heavy to 100 %, over it no roll (the game's fixed thresholds, not in the regulation: reference) | `load_light` 30, `load_medium` 70; dodge movement 115 / 100 / 75 / none, invulnerable ticks 100 / 100 / 75 %, refill 110 / 100 / 85 / 60 %, sprint 100 / 100 / 70 % / none (our own: the reference's rolls differ in distance and recovery) |
| light-attack stamina by type (straight sword = 100) | dagger 9, sword 12, axe 13, hammer 12, greatsword 15, greataxe 16, great hammer 16, colossal 15-20, spear 14, halberd 15, staff 12 | `wc_stamina` dagger 75, sword 100, axe 110, mace 100, great 135, spear 120, staff 100, bow 100 (of `cost_light` / `cost_heavy` / `cost_ranged`) |
| poise damage of the first one-handed light (straight sword 57.5 = 100) | dagger 40.5, axe 57.5, hammer 87.75, greatsword / greataxe 137, great hammer 175, colossal 194-243, spear 57.5, halberd 125, staff 40.5 (reference) | `wc_poise` dagger 70, sword 100, axe 100, mace 150, great 260, spear 200 (the game's long edged weapons are halberds, bardiches, voulges, poleaxes), staff 70, bow 100 |
| scaling coefficients (strength / dexterity / intelligence) | dagger 30 / 50, straight sword 34.5 / 31.5, axe 44 / 33, hammer 50.5 / 33, greatsword 35 / 34.5, greataxe 52.5 / 30.5, great hammer 55 / 26, colossal 45-47.5 / 28-36, spear 34 / 41.5, halberd 38 / 40.5, staff 12 / 0 / 90, bow 19 / 26 | `wc_str` / `wc_dex` / `wc_int`: dagger 30 / 50, sword 35 / 32, axe 44 / 33, mace 50 / 33, great 48 / 30, spear 36 / 41, staff 12 / 0 / 90, bow 19 / 26 |
| the statistic curve | the default correction graph: 11.7 % at 10, 27.8 at 20, 54.5 at 40, 75 at 60, 90 at 80, 95.4 at 99 | `scale_stat` 0 20 40 80 120 160 200 -> `scale_value` 0 12 28 54 75 90 95 (our stat = 2 x) |
| guard with the weapon | stamina guard: dagger 15, sword 30, axe 32, hammer 30, greatsword 44, great hammer 44, spear 33, halberd 45, staff 15; medium shield 53 | `wc_guard` (block cost, %, = 100 x 53 / the weapon's, at most 300): dagger 300, sword 175, axe 165, mace 175, great 120, spear 145, staff 300, bow 300, unarmed 300 |
| critical | the critical bonus: daggers +10 % (median), others 0 | `wc_crit` dagger 110, others 100 |
| upgrades | one-material-per-level reinforcement: +1..+10, damage x 2.45 at +10 (+14.5 % a level), scaling x 1.8 (+8 % a level), poise unchanged, price rate 1.0 .. 6.0; one material a level | `upgrade_max` 10, `upgrade_damage_tenths` 145, `upgrade_correct_percent` 8; gold 300 x (1 + 0.5 (n - 1)) (+1 300 .. +10 1650); materials 1 + (n - 1) / 3 (1, 1, 1, 2, 2, 2, 3, 3, 3, 4: more than one a level because every creature can leave one) |
| weapon art cost | median art point cost 15 (a starting character has about 60-80) | `art_mana_percent` 20 of the maximum mana; `art_stamina_percent` 100 of a heavy; `art_cooldown` 60 |
| not in the regulation (our own) | attack speed and cancels (animation time-acts), hyper-armour per class (time-acts), chip | `wc_recovery` 0 / 0 / 4 / 8 / 10 / 16 / 6 / 8 / 0, `wc_cancel` 18 / 16 / 20 / 24 / 26 / never / 22 / 24 / never (unarmed, dagger, sword, axe, mace, great, spear, staff, bow; every cancel after the offline hit tick 16), `heavy_interrupt_hp_percent` 6, `spear_chip_percent` 20, `twohand_strength_percent` 150 (the reference's two-handing rule), `twohand_poise_percent` 125, `art_slam_percent` 160, `art_fixed_percent` 30, `art_bolt_ticks` 90, material drops 8 / 50 / 100 % by boss rank, `save_reach` 120 (the flasks' save-point radius) |

Named for `combat.<name>` / `app souls set`: the plain numbers by their names; the arrays as `<name>.<label>` with the
labels light / medium / heavy / over (tiers), none / dagger / sword / axe / mace / great / spear / staff / bow (classes), 0-6
(curve points), e.g. `combat.wc_poise.great = 260`. (`parry_first` was missing from the names and is there now.)

### 3.2 The second round's numbers (2026-10-21)

Benched against the owner's copy where the regulation has the figure (attack corrections of the straight-sword moveset
the first bench used - critical, parry-critical and guard-counter rows - read with the same local scripts; nothing of
it in the repository). Our values are our own, chosen near the ratios:

| What | Reference (ratio to that moveset's first light attack) | Our value |
|---|---|---|
| riposte / stance-break critical | the parry critical about 4 x a light (the front critical is the one a stance break opens) | `crit_riposte_percent` 400, `crit_stance_percent` 400 (x the hit's own damage) |
| backstab | the back critical about 3 x a light | `crit_backstab_percent` 300 |
| guard counter | damage about 1.4 x a light (a little over the uncharged heavy), poise damage about 6 x | `guard_counter_damage_percent` 150 (our heavy is 130), `poise_guard_counter` 550 (light 100) |
| flasks | a new character starts with 4 | `flask_count` 4 |
| parry window | small-shield parry active for about a quarter of a second | `parry_first` 3 - `parry_last` 18 (0.27 s), recovery to 45 (0.75 s) |
| flask heal / drink | heals about half of a starting character's bar; the drink about a second | `flask_heal_percent` 50, `flask_drink_ticks` 66 (1.1 s), spent at 36 |
| runes lost on death | all, recoverable at the spot | `drop_percent` 50 (gold also buys the shops here), `drop_radius` 60 |
| not in the regulation (animation time-acts) | stagger after a parry, riposte window, backstab angle | `parry_stagger_ticks` / `riposte_window` 100, `crit_stun_ticks` 45, `stance_crit_window` 90 (the stun of the break is 50: the window covers the get-up), `backstab_half_angle` 40, reaches 90, `backstab_cooldown` 120, `guard_counter_window` 36, `flask_heal_spread` 30, `flask_refill_radius` 120 (the game's own save-point radius) |

`soulscombat::Tuning` is plain `int32_t` fields in one struct: the room figure (FNV-1a of the struct) covers every
new field, and the next round's weapon numbers (equip load, scaling, upgrades, weapon arts, two-handing) go into the
same struct, named in `NAMES[]` for `combat.<name>` / `app souls set`.

### 3.1 Elden Ring reference -> our value

Sources, read as reference only (no file or value of them is in the repository; what was
fetched is under `local/souls-ref/`): **soulsmods/Paramdex** (`ER/Defs`: `BehaviorParam.stamina`,
`EquipParamWeapon.staminaGuardDef`, `guardCutRate`s, `NpcParam.superArmorRecoverCorrection`,
`GameSystemCommonParam.baseToughnessRecoverTime` - which fields model what);
**sovietspaceship/elden-ring-frame-data-explorer-data** (regulation 1.08: `data-bundle.json`
i-frame and cancel ranges of the roll animations, `weapon-attack-data.json` motion values and
poise damage); **vawser/Smithbox** and **JKAnderson/SoulsFormats** for what TAE time-acts are
(invulnerability and cancel windows by animation frame).

**2026-10-21: benched against the owner's copy.** The owner's own regulation file was read on
this Mac (decrypted and decoded with the public Paramdex definitions, by scripts kept under
`local/souls-ref/`; nothing of it is in the repository): the player behaviour stamina of the
straight-sword moveset, the weapon's stamina and guard figures, the attack corrections (motion
value and stance damage of light, heavy and charged heavy), the stance threshold of the enemies
by kind, and the base toughness recovery time. The roll's and back-step's frames are not in the
regulation (they are in the animation time-acts, not on this Mac); for them the frame-data
explorer stays the reference. Outcome, in our units:

| What | Bench (the owner's copy) | Our value | Changed |
|---|---|---|---|
| light attack cost | an eighth of a low-level bar | `cost_light` 1300 (13 %) | no - matches |
| heavy attack cost | between an uncharged heavy (about a fifth of the bar) and a charged one (about a third) | `cost_heavy` 2600 (26 %) | no - inside the range |
| heavy damage | motion value 1.25 x light uncharged, 1.6 x charged | `heavy_damage_percent` 130 | no |
| heavy poise damage | 2 x light uncharged (6 x charged) | `poise_heavy` / `poise_light` = 2.2 | no |
| poise thresholds by kind | ordinary : mini-boss : boss = 1 : 2.7 : about 4 (the bosses spread 2.7 to 6.7); every field mini-boss looked at has the same threshold | `poise_normal` 300, **`poise_miniboss` 650 -> 800**, `poise_boss` 1100 | **yes**: 650 was 2.2 x the ordinary threshold, the bench is 2.7 x |
| dodge to dodge | roll: the next dodge may start 0.70 s after the first (back-step 0.57 s) | **`dodge_cooldown` 10 -> 0**: the next dodge as soon as the 45-tick hop ends (0.75 s) | **yes**: with 10 it was 0.92 s, a third slower than the reference |
| dodge invulnerability | roll about 0.43 s from the start | `dodge_iframe_*` 1-24 (0.40 s) | no |
| hyper-armour on heavies | only some weapon classes' heavies have it (mostly the large weapons) | the game's own heavy keeps it (not a figure of the struct) | no - the game's rule stays |
| stamina refill, its delay, guarding refill, roll cost | not figures of the regulation for the player | as before | no |
| poise forgetting | the player's toughness recovers after a long base time; the enemies' stance recovery scales with their threshold | `poise_reset_ticks` 300 (5 s) | no - kept short for the game's short fights |

After the change: the mode-off rig comparison again byte for byte in both views
(`local/souls-combat/rig/off-over3`, `off-first3`), and a two-copy room with the mode
(`local/souls-combat/net/two4`: hub > drunare, the arena fight, 2 deaths and the reload)
**5,733 ticks in step, no shared column differs** (4 / 6 dodges, 36 / 30 light, 0 / 2 heavy,
0 / 5 presses refused, 3 hits not landed, 1 blocked hit paid).

The table below is the first reference pass (2026-10-20); the two rows the bench changed say so.

| Elden Ring (reference, approximate) | Our value | Why it differs |
|---|---|---|
| roll: invulnerable from its first frame for about 13 frames at 30 fps (0.43 s); attack-cancel from 18-22, move from 22 (0.73 s) | `dodge_iframe_first` 1, `dodge_iframe_last` 24 (0.40 s) of a 45-tick hop | the game's hop is 45 ticks long, near the roll's recovery; the window ends a little before the reference's, the hop being a back-step and not a roll |
| a second dodge only after the recovery | `dodge_cooldown` 0 after the hop has ended (0.75 s between dodges; was 10, 0.92 s, before the bench) | |
| stamina refills at about 45 a second, after a short delay; slower while guarding | `regen_per_tick` 75 (45 a second), `regen_delay` 36 (0.6 s), `regen_block_percent` 35 | |
| base stamina about 80-100 at low Endurance | `stamina_max` 10000 (100) | one value for every character (no Endurance) |
| a straight-sword light attack costs about an eighth of a low-level bar, a heavy about twice that | `cost_light` 1300, `cost_heavy` 2600 | a light combo of 7 empties a full bar |
| a roll costs a little more than a light attack | `cost_dodge` 1500 | |
| sprinting drains slowly, no refill while sprinting | `cost_sprint_per_tick` 20 (12 a second), `sprint_speed_percent` 135 | the game has no sprint: its run speed is raised (record +0x4c20) |
| guard: stamina damage of a blocked hit, less the guard's "guard boost"; at 0 a guard break | `cost_block_base` 800 + `cost_block_per_hp_percent` 60 x damage % of maximum hp; `guard_break_ticks` 60 | the game's hits are not in the reference's units: the cost goes with the hit's share of the bar |
| hold for a heavy: separate button (R2); charged R2 by holding | `heavy_hold` 18 (0.3 s) | one button for both |
| motion value of R2 about 1.25 x R1 (longsword 100 / 125); poise damage of R2 about 2 x R1 (57.5 / 115) | `heavy_damage_percent` 130; `poise_light` 100, `poise_heavy` 220, `poise_ranged` 60 | |
| poise ("toughness"): a damage threshold per enemy; broken = stagger; recovers after some seconds without being hit | `poise_normal` 300 (3 light hits), `poise_miniboss` 800 (650 before the bench), `poise_boss` 1100; `poise_reset_ticks` 300 (5 s) | by the game's own boss rank |
| a stagger lasts about a second | `stagger_ticks` 50 (0.83 s), the creature's own stun | |
| heavy attacks have hyper-armour | the game's own heavy attack already has it (1) | |
| lock-on: nearest to the middle of the view, switch with the stick | `lock_range` 600, `lock_turn` 0.30, `lock_turn_max` 9, `lock_flick` 7 (controls settings) | |

## 4. What was run

### 4.1 The rig comparison with the mode off (Ran)

`local/souls-combat/rig/check.py` (the hands work's `local/fp-ready/rig/check_rig.py`, results
beside it): the fight session against the rig's log, controller rows replayed, the original
game's translation **with this work's code linked in** (`rta_app_combat_orig`), sound on the
machine's clock.

| View | Result |
|---|---|
| overhead | `compare.txt` byte for byte `reference-compare.txt` |
| first person | `compare.txt` byte for byte `s13-first-compare.txt` |

Run twice: with the first build (`off-over`, `off-first`) and again with the final sources
(`off-over2`, `off-first2`): byte for byte both times. (The section 12/13 contract of
`native-app.md`: the reports are the gate, not whole memory.)

### 4.2 Offline, every mechanic (Ran)

`local/souls-combat/t1`, `t2o` (the hands work's route to the valor boar, Barbarian, hit points
held up, `--combat souls`; the block's words shown every few ticks):

| What | Seen |
|---|---|
| dodge (L3 tapped with the stick up-left) | state 0xb from the tick after the release, facing turned (-27538 -> -29809), 55 units moved in 40 ticks, stamina 100 -> 85, refill from 0.6 s later |
| heavy (cross held) | at 18 ticks held: state 1, request 2 (the game's heavy), stamina 100 -> 74 |
| lights (cross tapped every 12 ticks) | each swing and combo step 13 off: 82.75 -> 4.75 in seven; the swings go on to 0 |
| block (R1 held against the boar) | three blocked hits paid (27.6 -> 0 ...); a **guard break**: stamina 0, state 3 (the forced stagger), flags "broken, empty", red bar; block again after 1 s |
| poise | the boar's poise broke once (rank 0, three hits within 5 s): its slot 30 (0x118a58) was called and its stun timer (+0x31c) read 50 right after (`t1b`, `SOULS_LOG=1`) |
| invulnerable ticks | `t2o`, overhead, L3 tapped every 46 ticks beside the boar: 29 hits on the player, **9 of them not landed** (the counter `savoid`), each while the dodge tick read 13 to 25 in the samples of every second tick |
| lock-on | `app souls lock`: the boar locked, the look turned to it, the marker on it; let go when it died |
| refusal | offline the taps of `t1` never found the bar at 0; online (4.3) 2 to 7 presses per player were refused with an empty bar |

Offline runs are repeatable: the same script gave the same ticks for every change of the
counters twice (`t2`, `t2o`), and `t1` gave the same figures with two builds (`t1`, `t1b`).

### 4.3 Online: two and three copies in one room (Ran)

`local/souls-combat/net/n2souls.py`: `tools/recomp/net2/n2party.py` unchanged, with (a) the
window program off-screen in place of the headless one (`as-app.py`, after the s13 helper), (b)
**only the host given `--combat souls`** - the joiners take it from the room - , (c) drawn
input with the mode's presses added (dodge taps and sprint holds of L3, heavy holds of cross,
long blocks), (d) the block's words as tick-log columns: mode, player-tick count, breaks,
poise held, hits not landed, blocks paid, and per player stamina, flags, dodge tick, attack
held, L3 held, the four counters, facing word and attack request. A rendezvous service of the
run's own on 127.0.0.1:41987. `tools/rig/compare.py ticks` over every pair of tick logs.

| Run | Copies | Result | What happened (from the tick logs and the programs' figures) |
|---|---|---|---|
| `two1` | 2 | **3,961 ticks in step**, no column differs | hub > drunare (the level change in one lockstep tick); the joiner: "the host plays with the souls-style combat mode on: so does this copy now"; mode on in every row on both; player 0: 7 dodges, 3 heavy attacks, 31 light; player 1: 8 dodges, 36 light, 2 presses refused with an empty bar. No monster reached |
| `two2` | 2 | **6,346 ticks in step** | hub > valor (an attempt to walk both to the boar: no fight) |
| `three1` | 3 | **5,697 ticks in step, all three pairs** | hub > drunare, the arena fight there: 54 hits on players (1 not landed: a dodge), 2 creature hits by players, 1 blocked hit paid, **3 deaths and the reload after everybody died**; per player 4 / 8 / 9 dodges, 1 / 2 / 1 heavy, 39 / 47 / 34 light, 0 / 7 / 3 refused, stamina at 0 in 0 / 222 / 37 ticks, 96 / 192 / 216 invulnerable ticks, 16 / 43 / 35 sprinting, 1,818 / 529 / 630 blocking |
| `two3` | 2 | **5,731 ticks in step** | hub > drunare, the arena fight: 18 hits on players (2 not landed), 2 deaths and the reload; 9 / 6 dodges, 47 / 46 light, 1 / 0 heavy, 3 / 2 refused, stamina at 0 in 148 / 74 ticks |
| `refuse1` | host with the mode, joiner the standard `rta_app` (no mode) | **not started**, as it should be | the room's warning "The souls-style combat mode is off for J1 ... and on for Host ...: every copy must have it. Do not start."; 80 tries of the host's start, each refused ("Not every copy in the room plays with the souls-style combat mode."); nobody launched |

In every run every pair of tick logs is equal in every column - the game's (seed, the previous
tick's sync hash, positions, states, hit points, gold, experience, out-of-step flags) and the
mode's (stamina, flags, dodge tick, held counts, counters of every player, facing words, attack
requests, the hits not landed, blocks, breaks, poise held, player-tick count) - and no
out-of-step flag was raised. Not reached online: a guard break and a poise break (both Ran
offline, 4.2); a run of four copies.

### 4.4 Pictures (Ran; local only)

| What | File (under `local/souls-combat/`) |
|---|---|
| lock-on: the marker and the target's health on the boar, the stamina bar | `t1/sheet-block.png` (frames 2780-3060) |
| stamina running out: the bar empty and red after the guard break | `t1/sheet-block.png` (2840, 2960) |
| a dodge through an attack: the white frame of the invulnerable ticks round the bar while the boar's hit at tick 3273 does not land | `t2o/sheet-iframe.png` (ticks 3250-3282, overhead) |
| the dodge itself | `t1/sheet-dodge.png` |

### 4.5 Offline, the second round (Ran)

`local/souls-combat/t3.py` (the valor route, the boar; `SOULS_LOG=1`, `--combat hardcore`; maximum hit points and
stamina topped up by pokes so the fight lasts; `app souls pose` keeps the boar in reach). Final run `t3/out.log`:

| What | Seen |
|---|---|
| flasks | three drinks: state 3 for 66 ticks, at drink tick 36 "500.0 of 1000.0 hit points to come", 4 -> 3 -> 2 -> 1; hit points 300 -> 807 within the spread |
| parry | 3 parried boar hits ("a hit of 37.1 (parry tick 13)", 35.1, 44.1 at tick 18), the boar stunned 100 ticks each |
| riposte | tick 3112: 5.9 x 400 % (hit points 201.2 -> 177.6) |
| guard counter | 5 started from the block; tick 3617: 11.6 x 150 % (177.6 -> 160.1) and the poise broken by it |
| backstab | tick 3982: 5.6 x 300 % (160.1 -> 143.1) with the boar turned away |
| stance-break critical | tick 5006: a heavy 65 ticks after a break, 11.3 x 400 % (63.0 -> 17.4); with `poise_normal` set to 100 for that part. Many of the game's heavy hits on the boar come with 0 damage (its own roll), which is why several tries were needed |
| death drop | died with 1000 gold: 500 at the spot; offline the level restarts from the save (gold 500 again), 500 taken then (0 left), `go-drop`: picked up, 500; died again with 500 (250 left), after the reload died again before picking it up: "died again: 250 gold lost", 125 left the second time |
| save point refill | after the reload at valor's start: "at a save point: flasks full (4)" |

### 4.6 Rooms with Hardcore mode (Ran)

`local/souls-combat/net/hardroom.sh OUT N PORT` (n2party through `n2hard.py`: the drawn input of 4.3 plus parry
presses inside blocks, attack presses inside blocks, R2 drinks; 126 tick-log columns with the block's new words; only
the host given `--combat hardcore`; a rendezvous service of its own on 127.0.0.1; `--tick-do` pokes in one lockstep
tick on every copy: pending damage on every player at 2600 and 3400, the test-aid word at 3150 and 3900).

| Run | Copies | Result | What happened |
|---|---|---|---|
| `hard2a`, `hard2b` | 2 | 5,731 / 5,732 ticks in step | earlier builds: found the drink ending early in a net game and the respawn without a new object (both fixed, above) |
| `hard2c` | 2 | **5,730 ticks in step**, no column differs | hub > drunare; "Hardcore mode: on for this game" on both; 3 flasks drunk, 3 refills, both died (drop 250 each), reload after everybody died, both drops picked up (one by the test aid, one by walking: 500 gold back) |
| `hard3a` | 3 | **5,702 ticks in step, all three pairs** | `--level-option valor` > drunare; 11 flasks drunk, 11 refills (save point refills at valor's start: "p0 at a save point: flasks full (4)" at ticks 272, 812, p1 at 1052, 1083, 1211, p2 at 332), 38 hits on players (2 dodged), 5 deaths, 3 drops left and picked up (750 gold back), the reload after everybody died |

Not reached in a room: a parry, riposte, backstab, stance-break critical or guard-counter hit (no player hit landed
on a creature in the drawn input), "dying again loses it".

### 4.7 Offline, the weapons (Ran)

`local/souls-combat/t4.py RIGHTS` (the valor route; at valor's start, by its save point: the material test aid gives 6,
gold poked to 5000, four upgrade presses, two-handing on and off; at the boar: light taps, weapon arts with mana topped up,
swings cancelled by a dodge, a dodge in each equip-load tier with the statistics poked, heavies under the boar's hits with a
300-point bar, then the record's definition set to a great weapon's row (a test only) and the heavies again; drops set to
100 %) and `t5.py` (the weapon record's definition set in turn to eleven rows of the game's table, a test only: the class,
grades and scaling of each and its weapon art cast). `SOULS_LOG=1`, `--combat hardcore`. Final runs with the final sources:
`t4/g2` (character 2, an axe), `t4/g0` (character 0, a mace), `t5/out.log`; earlier runs `t4/r0`-`r6` (every character:
maces, axes, bows), `t4/f0`, `f2`, `b`.

| What | Seen |
|---|---|
| classes from the game's records | characters: mace (0, 6), axe (1, 2, 3), bow (4, 5); `t5`: the rows of a dagger, a longsword, an axe, a mace, a greatsword and a two-handed hammer (great weapon), a halberd and a trident (spear), a staff, a bow and a throwing axe (bow) came out as those classes, the grades (strength / dexterity / intelligence) D D -, D D -, D D -, D D -, D D -, D D -, D D -, D D -, E - B, E D -, E D - |
| equip load | from the game's own weights: the axe character 20.84 of 68.75 (30 %, medium), the mace character 18.84 of 59.50; the same character with a dagger 16.84, a longsword 19.84, a greatsword 30.84, a halberd 31.53 |
| tiers (axe, statistics poked) | a dodge of 44 ticks moved 67.3 units light, 55.2 medium, 43.7 heavy; overloaded: no dodge (refused) |
| scaling and upgrades | the axe character: scaling +21 %, damage 121 %; the upgrades at the save point +1 300 gold 1 whetstone -> 136 %, +2 450 -> 153 %, +3 600 -> 169 %, +4 750 gold 2 whetstones -> 186 % (1 left); two-handed +38 % scaling -> 196 %; statistics poked to 400: scaling +61 % (219 %) |
| light hits with it | the boar: 6.8 -> 12.7, 6.6 -> 12.2, 5.6 -> 10.5 (axe +4, 186 %); the mace +4: 4.1 -> 7.5 (184 %) |
| grades with upgrades | the mace's strength C at +3 and above (50 x 1.24 = 62), D before |
| weapon arts | the axe: the spin (cyclone, state 6) at level 5, 3.2 mana, hits of 2.9 -> 5.5 on the boar and the creature beside it, the boar's poise broken; the mace character (its lump has no ground-pound clip): the lunge (charge, state 9), 7.3 mana, 185.1 x 30 % x 184 % = 102.2; `t5`: lunge for the dagger and the spears, spin for the sword and the axe, slam (state 10) for the mace and the great weapons with the barbarian, bolt (shock) for the staff and the bows |
| dodge cancel | the axe's swing cancelled by a dodge 27 ticks in (state 1 -> 0xb), 1 / 2 per run |
| hyper-armour | the axe's heavy staggered by the boar's hits of 37.1, 42.1, 22.1 ... (6 of the heavies); the same character with the great weapon's row: 6 heavies hit the boar, none staggered |
| material drops | the boar killed by a light hit: "rank 0, roll 96 of 100" (drops set to 100 %), a whetstone left; the mace character: roll 23 |

### 4.8 Rooms with the weapons (Ran)

`local/souls-combat/net/weaproom.sh OUT N PORT` (`n2weap.py`: the drawn input of 4.6 plus weapon-art presses (L3 held,
cross), two-handing presses (L3 held, L1) and three upgrade presses (L3 held, Square) at the start of every phase; the
weapons part of the block, the save-point count, every player's mana and the upgrade tag of its weapon record as tick-log
columns - 222 columns with two copies, 231 with three; only the host given `--combat hardcore`; `--level-option valor`, so
the game starts by valor's save point; `--tick-do`: 5000 gold and the material test aid (3) for every player at ticks
140-175, the kills and the drop aid of 4.6).

| Run | Copies | Result | What happened |
|---|---|---|---|
| `weap2a` | 2 | 5,734 ticks in step | an earlier build (found the test aid's item record overlapping the save-point list: moved) |
| `weap2b` | 2 | **5,734 ticks in step**, no column differs | valor > drunare; p0 upgraded its mace to +1 at valor's save point (300 gold, 1 whetstone; the record's tag word 0x484301da on both machines; damage 120 % -> 135 %), p1 refused (not near enough: 3 refusals); 8 weapon arts (lunges, state 9), arts refused in a swing and while dead; 19 hits on players in the drunare fight, both died (drops, the reload after everybody died, a drop picked up) |
| `weap3a` | 3 | **5,703 ticks in step, all three pairs** | valor > drunare; p0 and p2 upgraded to +1 at the save point (tag 0x484301da on all three), 12 weapon arts, 2 swings cancelled by a dodge, 13 hits on players, 3 deaths, the reload |

Not reached in a room: a two-handing toggle (none drawn through), a player hit landing on a creature (so no scaled hit, no
material drop and no interrupt online: they are computed from words every machine has - the tick's own columns - and were
Ran offline, 4.7), the spear's chip (player against player).

### 4.9 Offline, the attributes and the spellbook (Ran)

`local/souls-combat/t6.py RIGHTS OUT.rig XP SEQ` (the valor route; at valor's start, by its save point: XP experience by the
test aid, the character screen opened with L3 + L2, the presses SEQ, closed with block; at the boar the skill buttons pressed
every 100 ticks with the boar held in front and the mana full; the screen asked for again away from a save point).
`SOULS_LOG=1`, `--combat hardcore`, program `rta_app_next`. Runs `t6/a0`, `a1`, `b4`, `c0`, `d0`, `lc`:

| What | Seen |
|---|---|
| level-ups and points | 3,000 experience: level 1 -> 2, 2 points (character 0, a shaman); 20,000: level 6, 10 points (character 4, a ranger) |
| the screen | open at tick 324 (L3 + L2 by valor's save point), points on Mind 38 -> 40, Endurance, Faith; a press with no points left refused; closed by block; at the boar "refused" (no save point) |
| Mind -> mana | the shaman's maximum mana, the game's own 42.2 at level 2: 43.25 with one point, 44.31 with two (+2.5 % each); the game's own maximum kept apart and the bonus added again after its recalculations |
| Endurance -> stamina, load | 2 points: the bar 100 -> 101.8 (`b4`), 1 point 100.9 (`c0`); the capacity follows Endurance |
| Faith / Intelligence -> spells | the shaman's poison bolt (skill 89) hits the boar 26.0 -> 32.2, 29.0 -> 35.9 ... (x 124 %: INT D, FTH C); the ranger (no spells) 108 % shown after one Faith point |
| spellbook | the shaman's book one spell, 3 slots; taken out of its slot on the screen: 5 casts refused at the boar (`c0`, `a1`), "spell is in no spell slot"; out and into its slot again: cast and scaled (`d0`) |
| kept with the character | the save spot (+0x4c2a) written at the first change; through a level change valor > drunare with its object made anew (`lc`): the same bytes, Mind still 39 |
| pictures | `t6/a0/sheet-open.png`, `sheet-spent.png`, `t6/a1/sheet-spent.png` (the native sheet on the open screen) |

Godot (`local/godot-r26/test/sheet1`, the r26 library with this round's code in the r25 project with `hud/sheet.gd` and
`hud/souls.gd` of this round, `--mode scene --combat hardcore`, the same script as `t6/a0`): the same log line for line
(level 2, the screen, Mind 40, the slot changes, the casts x 124 %); `boar-cast.png`: the sheet drawn by `hud/sheet.gd` over
the scene at the boar (asked for with `app souls sheet`), the level-up line and stamina bar of `hud/souls.gd`. At valor's
start the Godot HUD is hidden by the game's own intro (phase 0xa42), so the pictures of the open screen there show no HUD.

### 4.10 Rooms with the attributes and the spellbook (Ran)

`local/souls-combat/net/statsroom.sh OUT N PORT` (`n2stats.py`: the drawn input of 4.8, and at valor's save point the
character screen - L3 + L2, then right, right, down, right, down, right, down, right, right, left, down, right, up x3, block -
with the drawn play's own presses and stick left out from frame 300 to 600 so that nothing else closes it; the skill buttons
at 620, 720, 820, 920; 20,000 experience for every player by the test aid at 200 + 10 x slot; 383 tick-log columns with two
copies: the attributes part, the save spot's bytes, the maximum mana, level and base stamina of every player, the header
counters).

| Run | Copies | Result | What happened |
|---|---|---|---|
| `stats2a` | 2 | 5,617 ticks in step | the drawn play's own presses closed the screen at once (found: they are left out in the window since) |
| `stats2b` | 2 | 5,632 ticks in step | the save spot at +0x43e0 cleared by the level change (found: moved to +0x4c2a) |
| `stats2c` | 2 | **5,630 ticks in step**, no shared column differs | both players level 6 (10 points); p0's screen at valor's save point: Mind 38 -> 41, Endurance 28 -> 29, Faith 40 -> 41, the poison bolt taken out of its slot (stamina bar 100.9, maximum mana 64.2 -> 69.0); p1's screen refused (not near enough); p0's skill presses refused (21), p1's casts scaled x 124 %; valor > drunare, four deaths, two reloads after everybody died: p0's attributes the same after all of it |

Not reached: a three-copy room this round; a spell hit on a creature inside a room (the casts were made, no hit landed in
the drawn input); a save on the memory card and a load of it (the record is saved whole: Read).

## 5. Files

| File | What |
|---|---|
| `tools/recomp/app/soulscombat.h`, `.cpp` | new: the mode, its numbers, the block, the overlay, the commands |
| `tools/recomp/app/fpcontrols.h`, `.cpp` | hunks: `set_souls`, `lock_toggle`, the lock-on (Hud `lock`, `foes`), L3 passed and R3 taken in the mode, four `controls.lock_*` settings |
| `tools/recomp/app/app_main.cpp` | hunks: `soulscombat::blank` after `fpcontrols::translate`; `overlay` before `backend->execute`; the camera in `on_drawn`; `--combat`; `app souls ...`; settings; figures |
| `tools/recomp/app/settings.h` | `combat.*` lines go to the modules |
| `tools/recomp/app/build.py` | `soulscombat.cpp` compiled; a build `--as NAME` keeps its own object folder (it shared `obj-app` before) |
| `tools/recomp/rt/rt.h`, `runtime.cpp` | `rt_replace_function` (a separate hunk from the shelf work's) |
| `tools/recomp/net2/hooks.h`, `launch.cpp`, `session.cpp`, `session_net.cpp` | the room option: four hook pointers, the copy's description, the joiner following the host, the refusal, `net2_set("copy")` |
| `tools/godot/project/hud/souls.gd`, `hud/hud.gd` | new file; three lines in `_ready` |
| `docs/issues/native-souls-combat.md` | this |
| second round (2026-10-21) | `soulscombat.{h,cpp}` (the mechanics of 2.7, the Tuning fields of 3.2, the block's version 2, the test aids, Hardcore names), `hud/souls.gd` (flasks, parry / riposte lines, drop marker); the name in `app_main.cpp`, `win_main.cpp`, `linux_main.cpp` (`--combat hardcore`), `testerkit_app.h`, `net2/session.cpp`, `net2/launch.cpp`, `godot/lib/rtag.cpp`, `godot/project/main.gd`, `portal/screens/room.gd`, `portal/gameflow.gd` |

| fourth round (2026-10-25) | `soulscombat.{h,cpp}` (the attributes and the spellbook of 2.9, the Tuning fields of 3.4, `load_per_stamina` renamed `load_per_endurance`, the block's version 4, the experience test aid, the character sheet in the overlay, `app souls sheet`), `hud/sheet.gd` (new), `hud/souls.gd` (the sheet added, the level-up line, the stamina bar's length per player) |

| third round (2026-10-21) | `soulscombat.{h,cpp}` (the weapons of 2.8, the Tuning fields and arrays of 3.3, `parry_first` named, the block's version 3, the material test aid, the weapon card in the overlay), `testerkit.{h,cpp}` (`testerkit::text`: the overlay's letters for another overlay), `hud/souls.gd` (the weapon card) |

## 6b. In the Godot library (2026-10-20, Ran)

- `tools/godot/build.py lib` compiles `app/soulscombat.cpp` when the snapshot has it (`-DRTAG_HAVE_SOULS`);
  `lib/rtag.cpp` calls `soulscombat::blank` right after `fpcontrols::translate` / `take_pitch` (as `app_main.cpp`),
  `rtag_set_option("combat.mode" | "combat.<number>")`, `rtag_has("souls")`, script lines `app souls ...`, and adds
  `souls_want=`, `souls_on=` and `copy=fix=XXXXXXXX,words=N` (what the copy says of itself in a room, worked out as
  `net2/launch.cpp` `souls_describe` does) to `rtag_info`. The native overlay is not called: Godot draws the HUD.
- `main.gd --combat souls|off`. The portal: `gameflow.gd` says the copy's description to the room
  (`net2_set "copy"`) once the game runs and whenever it changes; the **room screen** has a third choice "Combat:
  Classic / Souls-style" (host only; guests see the host's); a joiner's library takes the host's choice by itself
  (`follow_souls`). A copy without the mode makes the room show "The host plays with souls-style combat and NAME does
  not have it (yet)" - now also when that copy says nothing of itself (an older Godot copy: the service's own check
  leaves such a copy out, `net2_start` refuses all the same).
- **Ran** (`local/godot-r6/test/`): offline `souls1` (old directory, overwritten; the figures are in the log): the
  valor route, 1 dodge, 1 heavy, 7 light, a poise break (stagger), 3 blocks paid. Room `souls2` (two Godot portals,
  `room6.py`, own rendezvous service on 127.0.0.1): host picks Souls-style on the room screen, the joiner says
  `fix=170c4f08 words=32957` within a second; game launched with "souls-style combat: on for this game" on both;
  hub > drunare, **5,931 ticks in step, no shared column differs** (`compare.py ticks`, the mode's columns included);
  dodges 6 / 6, heavy 0 / 3, light 50 / 43, refused 0 / 10, stamina at 0 in 0 / 222 ticks, 1 hit not landed (a
  dodge), 18 hits on players, both died in the arena. `refuse1`: the same host, joiner the fifth round's Godot build
  (no mode): the warning on the room screen, `session.start()` -> -7 "refused", nothing launched.
- HUD (`hud/souls.gd`): the stamina bar is the theme's own bar (`Style.bar`), on the player's frame (overhead, third
  person) or under the two slim bars (first person), so it covers none of the middle of the picture.

## 6. The Godot HUD

`hud/souls.gd` draws the stamina bar (with the frame of the invulnerable ticks, red when the
guard is broken) and the lock-on marker with the target's health, reading only the block at
0xE0800 through `machine.peek_u32` / `peek_f32` and placing the marker with `gs.project`. The
hook is three lines in `hud.gd`'s `_ready`. For the Godot program to have the mode, the library
build (`tools/godot/build.py`, the other agent's) has to compile `tools/recomp/app/soulscombat.cpp`
and call `soulscombat::blank` where it calls `fpcontrols::translate`; until then the block is
not there and the piece draws nothing.

## 7. How to repeat

```sh
python3 tools/recomp/app/build.py --no-game --as rta_app_next
python3 tools/recomp/app/build.py --original --no-game --as rta_app_next_orig
python3 local/souls-combat/rig/check.py off-over7 rta_app_next_orig overhead
python3 local/souls-combat/rig/check.py off-first7 rta_app_next_orig first
# second round offline: cd local/souls-combat && python3 t3.py && SOULS_LOG=1 PROG=rta_app_next ./run.sh t3 t3/t3.rig --combat hardcore
# second round rooms:   cd local/souls-combat/net && ./hardroom.sh hard2c 2 41987; EXTRA="--level-option valor" ./hardroom.sh hard3a 3 41988
# third round offline: cd local/souls-combat && python3 t4.py 2 t4/g2.rig && SOULS_LOG=1 PROG=rta_app_next ./run.sh t4/g2 t4/g2.rig --combat hardcore
#                      python3 t5.py t5.rig && SOULS_LOG=1 PROG=rta_app_next ./run.sh t5 t5.rig --combat hardcore
# third round rooms:   cd local/souls-combat/net && EXTRA="--level-option valor" ./weaproom.sh weap2b 2 41991   (and 3 copies)
# fourth round offline: cd local/souls-combat && python3 t6.py 0 t6/d0.rig 3000 d && sed -i '' 's#OUTDIR#t6/d0#g' t6/d0.rig && SOULS_LOG=1 PROG=rta_app_next ./run.sh t6/d0 t6/d0.rig --combat hardcore
# fourth round rooms:   cd local/souls-combat/net && EXTRA="--level-option valor" ./statsroom.sh stats2c 2 41995
python3 local/souls-combat/rig/check.py off-over rta_app_combat_orig overhead
python3 local/souls-combat/rig/check.py off-first rta_app_combat_orig first
# offline: local/souls-combat/t1.py, t2.py (scripts from the valor route), run.sh DIR RIG --combat souls
# online:  N2_APP=.../rta_app_combat N2_HOST_EXTRA="--combat souls" RTA_NET2_SERVICE=127.0.0.1:41987 \
#          python3 local/souls-combat/net/n2souls.py OUT --port 41987 --players 3 --program local/souls-combat/net/as-app.py \
#                  --play 1200 --level drunare --play2 3600
```

## 8. Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| SC1 | The game has no roll; its block move (state 0xb, `anim(0xa4)`) is a backward hop of about 49 units in 45 ticks | Read, Ran | 0x1bf150, 0x1a6588; this document 1 |
| SC2 | `Player_processDamage` skips the stagger roll for a player whose attack request is 2 (the heavy attack) and staggers on pending flag 0x4000000 | Read | 0x1b3718-0x1b37e8 |
| SC3 | `Player_takeDamage` blocks a hit from the front in states 8 and 0xb unless flag 0x40; the blocked hit still ORs its flags into the pending ones | Read | 0x1b5440-0x1b5698 |
| SC5 | Hardcore mode's parry, riposte, guard counter, backstab, stance-break critical, flasks and death drop work offline with the numbers of 3.2; two and three copies in a room stay in step with them on through deaths, drops, recoveries, the reload and save point refills | Ran | this document 4.5, 4.6 |
| SC6 | Hardcore mode's weapons (equip load from the game's item weights, classes from its item records, scaling with grades, upgrades kept in the item record's unused bytes +0x06 / +0x44, the game's whetstones as the material, weapon arts from skills 35 / 37 / 38 / 41, two-handing) work offline with the numbers of 3.3; copies in a room stay in step with them through fights, an upgrade and a level change | Ran | this document 4.7, 4.8 |
| SC7 | Hardcore mode's attributes (Vigor, Strength, Dexterity, Intelligence the game's own; Mind, Endurance, Faith the mode's, kept in the player record's last 6 bytes +0x4c2a..+0x4c2f), points from the game's level-ups spent at a save point, the spellbook (attunement of the game's ability records, slots from Mind and Intelligence, spell hits scaled by Intelligence and Faith) work offline and in Godot with the numbers of 3.4; two copies in a room stay in step through a level-up, a point spend, a spell taken out of its slot, a level change, deaths and reloads | Ran | this document 4.9, 4.10 |
| SC4 | With the souls mode (L3 the dodge bit of the row; the mode's numbers in guest memory at 0xE0800, written in the tick by every machine), two and three native copies in one room stay in step through a level change, the arena fight, deaths and a reload, the mode's numbers equal in every tick; a room whose copies differ in the mode is not started | Ran | this document 4.3 |
