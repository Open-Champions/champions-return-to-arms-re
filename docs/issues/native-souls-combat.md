# Souls-style combat for the native build

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

**2026-10-20 - built, run offline and online; the proof runs of part 4 passed. Not committed.**

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

### 2.6 The mechanics

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

## 3. The numbers

All of them are one struct, `soulscombat::Tuning` (`soulscombat.h`); `combat.<name> = value`
in the settings file or `app souls set NAME VALUE` changes one offline; online the room's figure
holds them equal. Stamina in hundredths, ticks of 60 a second.

### 3.1 Elden Ring reference -> our value

Sources, read as reference only (no file or value of them is in the repository; what was
fetched is under `local/souls-ref/`): **soulsmods/Paramdex** (`ER/Defs`: `BehaviorParam.stamina`,
`EquipParamWeapon.staminaGuardDef`, `guardCutRate`s, `NpcParam.superArmorRecoverCorrection`,
`GameSystemCommonParam.baseToughnessRecoverTime` - which fields model what);
**sovietspaceship/elden-ring-frame-data-explorer-data** (regulation 1.08: `data-bundle.json`
i-frame and cancel ranges of the roll animations, `weapon-attack-data.json` motion values and
poise damage); **vawser/Smithbox** and **JKAnderson/SoulsFormats** for what TAE time-acts are
(invulnerability and cancel windows by animation frame). The owner's own copy of the game was
not on this Mac; a later bench against its regulation changes only the struct.

| Elden Ring (reference, approximate) | Our value | Why it differs |
|---|---|---|
| roll: invulnerable from its first frame for about 13 frames at 30 fps (0.43 s); attack-cancel from 18-22, move from 22 (0.73 s) | `dodge_iframe_first` 1, `dodge_iframe_last` 24 (0.40 s) of a 45-tick hop | the game's hop is 45 ticks long, near the roll's recovery; the window ends a little before the reference's, the hop being a back-step and not a roll |
| a second dodge only after the recovery | `dodge_cooldown` 10 after the hop has ended (about 0.92 s between dodges) | |
| stamina refills at about 45 a second, after a short delay; slower while guarding | `regen_per_tick` 75 (45 a second), `regen_delay` 36 (0.6 s), `regen_block_percent` 35 | |
| base stamina about 80-100 at low Endurance | `stamina_max` 10000 (100) | one value for every character (no Endurance) |
| a straight-sword light attack costs about an eighth of a low-level bar, a heavy about twice that | `cost_light` 1300, `cost_heavy` 2600 | a light combo of 7 empties a full bar |
| a roll costs a little more than a light attack | `cost_dodge` 1500 | |
| sprinting drains slowly, no refill while sprinting | `cost_sprint_per_tick` 20 (12 a second), `sprint_speed_percent` 135 | the game has no sprint: its run speed is raised (record +0x4c20) |
| guard: stamina damage of a blocked hit, less the guard's "guard boost"; at 0 a guard break | `cost_block_base` 800 + `cost_block_per_hp_percent` 60 x damage % of maximum hp; `guard_break_ticks` 60 | the game's hits are not in the reference's units: the cost goes with the hit's share of the bar |
| hold for a heavy: separate button (R2); charged R2 by holding | `heavy_hold` 18 (0.3 s) | one button for both |
| motion value of R2 about 1.25 x R1 (longsword 100 / 125); poise damage of R2 about 2 x R1 (57.5 / 115) | `heavy_damage_percent` 130; `poise_light` 100, `poise_heavy` 220, `poise_ranged` 60 | |
| poise ("toughness"): a damage threshold per enemy; broken = stagger; recovers after some seconds without being hit | `poise_normal` 300 (3 light hits), `poise_miniboss` 650, `poise_boss` 1100; `poise_reset_ticks` 300 (5 s) | by the game's own boss rank |
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
python3 tools/recomp/app/build.py --no-game --as rta_app_combat
python3 tools/recomp/app/build.py --original --no-game --as rta_app_combat_orig
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
| SC4 | With the souls mode (L3 the dodge bit of the row; the mode's numbers in guest memory at 0xE0800, written in the tick by every machine), two and three native copies in one room stay in step through a level change, the arena fight, deaths and a reload, the mode's numbers equal in every tick; a room whose copies differ in the mode is not started | Ran | this document 4.3 |
