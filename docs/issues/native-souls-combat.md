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

## 3. The numbers

All of them are one struct, `soulscombat::Tuning` (`soulscombat.h`); `combat.<name> = value`
in the settings file or `app souls set NAME VALUE` changes one offline; online the room's figure
holds them equal. Stamina in hundredths, ticks of 60 a second.

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
| SC4 | With the souls mode (L3 the dodge bit of the row; the mode's numbers in guest memory at 0xE0800, written in the tick by every machine), two and three native copies in one room stay in step through a level change, the arena fight, deaths and a reload, the mode's numbers equal in every tick; a room whose copies differ in the mode is not started | Ran | this document 4.3 |
