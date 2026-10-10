# Monsters and level objects, second pass (0x232000–0x2c3cd4)

This document finishes what `docs/monsters.md` started. The first pass catalogued every
class in the range and read the Drundar arena set, Cazic, Savepoint, JumpGate, Chest and
Container by hand; 66 creature classes were summarised by script only and several object
families were not read. Here every remaining class was read by hand from the decompile, with
the disassembly used wherever the decompile dropped arguments or looked wrong. Nothing was run
on a game.

Read `docs/monsters.md` sections 1–2 and `docs/creatures.md` first; their conventions are
used without repeating them. New symbols are in `symbols/monsters2.tsv` (147 addresses that
no other file named when it was written). Renames of existing names are proposed in section 8; they were not
applied.

Every statement is **Observed** (read at the address given) unless it is marked **Inferred**
or **Unknown**. "No caller" always means: no `jal`, no jump and no data word holding the
address was found by `tools/ps2elf.py xref` / `ptrs`.

## How this was made, and how far to trust it

- The area was split into eleven groups. Each group was read by one reader working only from
  the decompile, the disassembly and the existing documents; the group notes were then merged
  here. The merging reader read Zek, Innoruuk, Marr, MummyKing, Natasla and the door, switch,
  light, bomb and anchor objects, and re-checked a sample of the other groups' findings in
  the disassembly or decompile: CloudGiant 0x250930, Scorpion 0x2a5328–0x2a53b0, BlackWidow
  0x2ac22c, the Mummy save and load sizes, the Wraith list store 0x2bf474, and which class
  uses each static initialiser's data. The rest of the group sections were **not** verified a
  second time; they are as their readers wrote them, so wording and depth vary a little.
- A scan was run over every run, setState, takeDamage, touch, trigger and draw function of
  every class for reads of the camera globals (0x44f038–0x44f168), the cosmetic generators
  (0x404460, 0x404468), the render counters (0x44fdd0, 0x506048), the local-slot calls
  (0x13e1f0, 0x13e150), audio status calls and the hardware timer, and — for draw functions —
  for object creation, generator draws, run-list changes, script runs, world queries and
  stores into the object. It covers the function body and its direct callees inside the
  area; hits were then read by hand. Section 7 gives the results.
- **Two tool traps** found on the way, both affecting earlier work: `tools/ps2elf.py`'s
  function table treats every text address stored in data as a function start, and switch
  jump tables are data. `func_of` therefore ends a function at its first `case` label, and
  `tools/localstate.py`, which uses it, scans only the part of a run function **before the
  state switch** and resets its `lui` tracking at every case label. Its "nothing found" for a
  monster run function says nothing about the states. The scan used here takes function sizes
  from `decomp/all/index.tsv` instead. The same cause makes the address 0x293228 look like a
  function (it is inside `LostSoul_ctor`, which starts at 0x2931bc) and makes 0x281194 look
  like a `LavaBomb` constructor (it is a case label of `LavaMonster_run`).

Shorthand used in the sections written in list form (the first boss group and the level
objects of section 6.2): "event bit 0 / 1 / 2" are the bits of the mask `Creature_stepAnim`
returns for the frame (bit 0 is the hit frame of every attack clip); "own draw" is one value
from `GameObject_rand(this)`; "V23", "V27" … are virtual slots; "→ 5" means "requests AI state
5 through slot 27"; `hit(min..max, arc, dmg, flags)` is one of the arc helpers of
`docs/creatures.md` ending in `damage_apply`, with `+0xd0..+0xd2` the creature's level-scaled
damage range and `+0xd4` the attack rating passed with it; "tr" and "r" are the target's and
the creature's own radius; "clock" is the creature clock +0x300.

## 1. What this pass established

The short version; every line is backed by a section below.

**Online play (section 7 has the details).**

- A new per-machine input to AI: the CloudGiant king chooses "conjure a new bolt" by testing
  a `beam_create` handle (+0x530, read at 0x250930). The beam and trail tables are also used
  by camera-gated effect code, so whether the create succeeded is per-machine. Patch P-M2
  (section 10) makes the test use the class's own "bolt in flight" flag instead.
- `FireBomb_run` (type `kelethinBomb`) draws the shared seed and creates objects only when
  `isNearView(960)` is true (0x261fd0); `Catapult_run`, `LightningRod_run` and `AutoProp_run`
  gate script calls, object creation and damage on `obj_updateActive`. All four inherit the
  camera dependence of FINDINGS D6. Patch P-M1 removes the FireBomb gate.
- The `exclamation` script run from four draw functions is conditioned on **camera mode == 1**
  (the word at 0x4f8450 is the camera object pointer, not a structure) and, for NPC only, on
  being more than 240 units from the camera. Three interact prompts in this area run `key`
  scripts (AutoChest 0x23b6e8, AutoProp 0x23d068, SpiritAnchor 0x296ba0); prompts are evaluated
  from both run and draw code (`docs/script.md` P1).
- Lights: a light joining the run list from its draw function cannot change shared state
  through its run function, its generator or the list order (the link is pushed at the head).
  It does take two nodes from the global handle-node pool per light, and `handle_link` has no
  empty-pool test.
- Animation phases seeded from the cosmetic generator reach game state in two places: a
  `path` Critter's position (root motion, state 0x16) and the damage windows of a plain
  `pipepistona` AutoProp. For NPC, Ghoul, Vampire and the others listed in `docs/engine.md` P4
  no gameplay reader of the idle phase was found.
- Every draw function that the first pass listed as storing into its object was read: AntQueen
  (facing), FireBeetle, FireFly, Mosquito and Critter (position) save and restore; Creep sets
  and clears a creature flag only `Creature_draw` reads; `AutoObject_draw` clears flag 0x100
  and the three LP stores behind `g_drawFrame` are dead code.
- No boss run, setState or takeDamage function reads the camera, the local slot, audio state,
  a hardware timer or a cosmetic generator for a decision. Innoruuk, MummyKing and Minion do
  not even gate their AI on `Creature_updateActive`.

**Bosses (section 3).** Zek's "state 0xe handle" is a travelling shock wave that homes on an
enemy; Innoruuk fights in two phases switched by a 6 % chance per hit reaction to drop his
weapon, not by hit points, and his `invulnerable` property is never cleared by code in this
area; Marr builds a power counter that unlocks a double-damage swing, PlanarWind and a guard
with SpiritShield; MummyKing summons one soldier per player plus a shaman, of a type chosen by
thirds of his hit points; SpiderQueen's states 8–9 are a web strand that drags its victim, not
a jump; VampireLord has a bat form and a second form; RedDragon's breath damage is a 15-frame
tick in run; Hag has two forms carried by animation flags; the CloudGiant king conjures,
throws or slams a bolt; IronGuardian builds Droids; LavaMonster throws rocks only above half
hit points and with the standing-in-water flag set.

**Level objects (section 6).** The Auto classes are chosen by properties, not type names, and
"LP" means "has a ParticleEmitter, DynamicLight or Halo key". For AutoProp slot 17 is "next
state", slot 18 "set state silently" (script `autoPropSetState`) and slot 19 "set passable".
Slot 3 is the entry of the script built-in `trigger`. A WorldPart owns one movable piece of
level geometry. The Teleporter contains no teleport code: the only level code it can run is
the `dialogScript` of the Creature base. `WeaponRack_interact` is empty. FallPlatform,
FireTrail / FireTrailMaker, PointSourceSound and SnowballSpell have no creator in this build.

**Rules of play that depend on the game mode.** BlackWidow's web shot is requested only
offline (0x2ac22c). "A comrade was hurt nearby" (slot 12, kind 0) reaches Bubo, Goblin, Ghoul
and Orc only when there is one player (sender `Creature_processDamage` 0x110d90). Slot 36 is
the level a monster uses for the Dodge skill against missiles (`MissileWeapon_onTouch`
0x152eec).

**Bugs found on the way (not desync risks; each is in its class section).** Scorpion's sting
permanently divides its stored damage on the two highest difficulty indexes (0x2a5328–0x2a53b0);
the 61st Wraith or WarWraith of a level overwrites its own list counter (0x2bf474, 0x2c0b18);
Ulthork's variant test is inverted so its caster state is unreachable (0x2b56f0); Minotaur's
charge test has min and max swapped (0x289b48); `Mummy_saveState` writes 9 bytes and
`Mummy_loadState` consumes 12; `Demon_loadState` passes its holder arguments swapped
(0x25ef90); RedDragon state 0xf reads `g_players[-1]` when it finds nobody (0x260888);
CloudGiant's quake and the FireBomblet's burn hit everything in range without an enemy test;
`SpiritAnchor_interactPrompt` looks up the `key` text where it means `lockMessage`. States
with no requester in their own class: MummyKing 0x17 and 0x18, Mummy 0x17, Innoruuk 8 and 0xd,
Tormentor 8, Kobold 9, AntQueen 0x19 (the only creator of AntWave), Arenabeast 0x17 and 0x18,
Agony 0x11, Badger 7.

**Names (section 8).** Of the 151 functions that had no name, 146 are named in
`symbols/monsters2.tsv`, two were named by other files while this was written and three are
described but left unnamed. 77 of the 79 `Class_vslotN` names have a proposed replacement;
the two left are empty functions.

## 2. Conventions settled in this pass

### 2.1 Virtual slots

Additions to the table in `docs/monsters.md` 1.2 (slot numbers as `tools/vtab.py` prints them).

| Slot | Meaning | Evidence |
|---|---|---|
| 3 | **trigger(value)**: the entry the script built-in `trigger(name, arg)` (0x142264) calls on up to 99 objects with that name. Base for creatures is `Creature_trigger` (runs `dialogScript`). Overrides in this area: Innoruuk (start arming), MummyKing (1 = turn hostile, 0 = toggle weapon), DoorSwing / DoorSecret / RollDoor (open), Timer (start), Counter (count up or down), Catapult (restart the animation), FallPlatform (fall), AutoProp (next state when `Triggerable`), AutoChest (open), AutoContainer (ignite), Generator (spawn one when `triggerable`), WoodElfSoldier (shoot an arrow), NPC and Rondo (cutscene hide bits), CloudGiant (base, except the king). Empty overrides: AntQueen, Arenabeast, RedDragon, SpiderQueen, Minion, Soul, UndeadKnight | each class section |
| 10 | hit terrain (from `Creature_moveBy`): Nightmare ends its charge, Goblin starts its knock-into clip | 0x27142c, 0x26d690 |
| 11 | list of touched objects (from `Creature_moveBy`): contact damage for Cazic's charge, Marr's lunge, Nightmare's charge, Arenabeast, the flying FireBeetle, Goblin; Gnome pairing. Empty: Badger, CastBadger, SeaMonster, WarBoar | 0x24c04c, 0x2845e4, 0x271484, 0x23a028, 0x246fe8, 0x26d6fc, 0x269ab8 |
| 12 | nearby event (kind, position, source). Kind 0 "a creature was hurt here" is sent by `Creature_processDamage` (0x110d90) **only when there is one player**; Bubo, Goblin, Ghoul and Orc walk to the spot when the source is of their own class. Kind 2 makes shield carriers guard when the source is in front: Marr, FemaleDarkElf, MaleDarkElf, Goblin, Orc, Skeleton (who sends kind 2 is **Inferred**: `Player_run`, for the creature a shot is aimed at). Empty: Cazic, Creep | 0x249404, 0x26c9f4, 0x266bac, 0x2a2ec8, 0x28453c, 0x25aa30, 0x25cfc0, 0x2a7688 |
| 16 / 38 | get model / second model. Overrides switch the model by form: Hag (variant byte), VampireLord (bat), LavaMonster, Soul (held), Bubo (slot 38 only) | 0x27090c, 0x2b9d10, 0x282868, 0x2ab298, 0x249a30 |
| 17 | creatures: update attached spells (override: Mummy 0x29aeb8). **AutoProp family: advance to the next state.** AddParticle: recompute light and halo — called from the owners' draw functions. The door classes add their own slot 17, an empty function | section 6.1; 0x28ae34, 0x28dee0 |
| 18 | **AutoProp family: set state n silently** — the entry of script `autoPropSetState`. AddParticle: emit particles, called from run | section 6.1 |
| 19 | **AutoProp family: set passable (on)**; creatures: get display name | section 6.1 |
| 20 | is-enemy overrides: Demon (a Soul is an enemy), Skeleton (red against blue), Wraith and WarWraith (one wraith per victim; has a side effect, see 7.3) | 0x25f378, 0x2a7e04, 0x2c061c, 0x2c1bc0 |
| 21 | is-ally override: Kobold (base result and the other's type name is `koboldshaman`) | 0x280434 |
| 35 | level handed to skills; Zek's override only calls the base | 0x2c3c54 |
| 36 | **level used for the Dodge skill against missiles**: `MissileWeapon_onTouch` asks a non-player creature for slot 36 and, when non-zero, passes it to the skill 2 (Dodge) value query. Base: 0, 4 or 10 by boss rank. Marr: 20 while guarding, else 5. IronGuardian: 11 | 0x152eec–0x152f50; 0x284b50; 0x3cb50c |

### 2.2 The weapon holder (object at creature +0x50, table at its +0)

Slots read while following boss code (Weapon2 bodies at the addresses in section 8; Weapon1 and
WeaponShield have the same layout with fewer hands). The first argument selects the hand
(0 both, 1, 2).

| Slot (table offset) | Meaning |
|---|---|
| 1 (+0x0c) | put model entry n in a hand; 0 empties it |
| 2–8 (+0x14…+0x44) | build the hand's elemental damage descriptor (2 fire, 6 lightning, 8 by element code) |
| 9 (+0x4c), 10 (+0x54) | hand glow colour, four 8-bit values |
| 11 (+0x5c) | drop the held part as a physics prop |
| 14 (+0x74), 15 (+0x7c) | is the hand full; which model entry it holds |
| 16 (+0x84), 17 (+0x8c) | element code of the hand's descriptor; pointer to the descriptor (what monsters pass as the last argument of a hit) |
| 18 (+0x94) | draw the held parts |
| 21 (+0xac) | per-frame update; gated by `isNearView(480)` it only feeds `fx_modelStatusEffects` |

### 2.3 Other conventions

- Animation events: `creature_setDefEntryParams` (0x118378), called in every constructor,
  stores up to four (time, mask) pairs per animation entry of the class definition; the masks
  are the bits `Creature_stepAnim` returns. That these are the same events is **Inferred**
  (the masks match every use read); the time unit was not verified.
- Several constructors call `GameObject_rand(this)` **before** the base constructor has seeded
  the object's generator (SpiderQueen, Critter, Cyclops, Goblin, Ghoul, WoodElfSoldier, Wraith,
  WarWraith). `pool_new` zero-fills, so the value is a constant and the same on every machine;
  the hit-point argument computed from it is later replaced by `Creature_setStats`.
- A static initialiser is a pair: a body taking (1, 0xffff) and a 32-byte stub in the
  constructor table. In this area the pair sits at the **end** of its translation unit, so the
  pair found just before a constructor belongs to the class before it. The first pass
  attributed several to the wrong class; section 8 has the corrected owners.
- State 0x17 is "rise / appear" only for Skeleton and Skelight. Elsewhere it is whatever the
  class needs (Innoruuk arming, MummyKing teleport, Marr guard, CloudGiant conjure, Ghoul walk
  to a comrade, …).

## 3. Bosses

Per boss: constructor, fields, every AI state with its tests and transitions, attacks and their damage, what is summoned or cast, phases, script hooks, and the per-machine answer.

### Zek, Innoruuk, Marr, MummyKing, Natasla

#### Zek  (factory `raloszek`; vtable 0x5180c8; size 0x480)

Functions: ctor 0x2c1f94, draw 0x2c2378, run 0x2c2440, takeDamage 0x2c34e4, setState 0x2c382c,
slot 35 0x2c3c54 (only calls the base 0x118c50).

Constructor: `Creature_ctor` with max-hp argument 10 and class definition 0x503688. The 10 is
a placeholder here and for the next three bosses: `Creature_ctor` itself calls
`Creature_setStats` with the factors it looks up by type name (0x10a1a8–0x10a200). A Weapon1 holder is embedded at +0x3c8 and
installed at +0x50; hand 1 gets model entry 0x15. Radius 30, turn rate 1.2, speed +0xb8 = 0,
creature kind +0xb4 = 0xb, +0x28 = 0x32, creature flags |= 0x2000040000, the five resistances
+0x5c…+0x6c all 0.5, +0xec = frame, +0xf4 = frame + 300. Start state 0, `obj_runEvery60`,
`Creature_init`. No property is read by the class.

| Offset | Type | Meaning | Where |
|---|---|---|---|
| +0x460 | handle | enemy the ground wave steers toward | state 0xe, tail of run |
| +0x464 | s32 | a ground wave is travelling | state 0xe, tail |
| +0x468 | s16 | heading of the wave | tail |
| +0x46c | Vec3 | position of the wave | tail |
| +0x478 | s32 | clock value before which neither special is used | states 3, 5, 0xd, 0xe |
| +0x47c | s32 | last attack state entered (6…0xe) | setState, state 5 |

Run, before the switch: `Creature_processDamage`, `Creature_run`, `Creature_updateActive`
(returns when inactive), weapon-holder update, `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.2)`, slot 23 pickTarget(0). All ranges below are in world units and
all arcs in 16-bit angle units.

- **0** idle: slot 25 (can see target) → 3; otherwise away from home → 1.
- **1** walk home: can see target → 3; otherwise `Creature_moveToDest`.
- **3** chase: no target → 0. Target within 84 in an arc of 32000: → 7 if the target is
  charging (`Creature_isTargetCharging`), else → 5. Otherwise, in this order: if clock >
  +0x478 + 180 and an enemy is 120–800 away within arc 5000 → 0xe; if clock > +0x478 and an
  enemy is within 260 in any direction → 0xd; if the target is within 84 in any direction
  turn toward it; else `Creature_moveToTarget`.
- **5** between attacks: target within 84 and arc 8000 in front: charging → 7; otherwise one
  own-generator draw picks 6, 7 or 8 (only 6 or 7 when the last attack was 8). Not in front:
  target on the +16000 side (arc 8000) → 9, on the −16000 side → 10; any enemy on the +16000
  side → 0xb, on the −16000 side → 0xc; then the same two special tests as state 3; then turn
  toward a target within 84; else, when not rooted, → 3.
- **6, 7** swing: on event bit 0 `Creature_hitTargetInArc(0–84, facing, arc 8000, damage
  +0xd0…+0xd2, rating +0xd4, flags 0x80008, the hand-1 descriptor from holder slot 17)`. → 5
  when the clip ends.
- **8** double hit, turning toward the target: event bit 0 `Creature_hitAllEnemiesInArc(0–84,
  arc 8000, half damage, flags 0x440001)`; event bit 1 the same with flags 0x80001. → 5.
- **9, 10, 0xb, 0xc** sweeps: event bit 0 `Creature_hitAllEnemiesInArc(0–84, arc 8000, full
  damage, flags 0x80008, weapon descriptor)` centred on the facing (9), facing − 16000 (10 and
  0xc) or facing + 16000 (0xb). → 5.
- **0xd** ground pound: on event bit 0 a `GroundPoundEffect` (`pool_new(0x9c)`, constructor
  0x2c74ac) is created 84 units ahead with the skill 38 (GroundPound) object, the slot-35 level
  and Zek as owner; +0x478 = clock + 600. → 5.
- **0xe** ground wave: on event bit 0 `creature_findEnemyInCone(120–800, arc 10000)` is linked
  at +0x460 (may be empty), +0x464 = 1, the wave starts 120 units ahead with Zek's facing as
  heading, +0x478 = clock + 600. → 5.
- **0x10** → 0 when the attack cooldown has run out, else `Creature_fleeFromTarget`.
  **0x12** → 5 when animation flag 0x10 clears. **0x13** → 3 when no longer stunned.
  **0x14** dead: zero `Creature_moveBy`, `Creature_deadUpdate(20)`.

Tail of run, every frame while +0x464 is set (it runs in any state, including while Zek does
something else): the wave moves 5 units along its heading; its height is the terrain height
+ 1, and a step of more than 12 units ends it at the previous position. With an enemy linked,
the heading turns toward it at up to about 140 angle units per frame (**Inferred** from the
arithmetic: 0.43 % of the angle to the reverse bearing is subtracted each frame) and the wave
ends within 36 units of it. It also
ends more than 800 units from Zek. At the end: `fx_ringBurst`, an explosion sound,
`combat_applyAreaDamage(40, 180, Zek, position, half of +0xd0, half of +0xd2, flags 0x80840)`,
a scorch decal whose rotation is one own-generator draw, a `LightEffect`, and the handle is
cleared. Every frame of travel calls `fx_spawn(7, position)`.

setState 0x2c382c (after the common filter): 6…0xe store the state in +0x47c; 6 picks one of
two clips with an own draw; 0x10 sets the attack cooldown +0x318 to 60; 0x12 picks one of four
hit clips with an own draw; 0x14 sets creature flag 0x20000000000, calls
`Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, …)`, and then — unless the level name is
`drunarm` — drops the weapon as a physics prop (holder slot 11) and plays the other death
clip; slot 28 (on death).

takeDamage 0x2c34e4: when the flags carry 0x2000 and the attacker is a creature, a metal
"clang" sound and 50 particles are produced, the particle directions coming from Zek's own
generator (a rejection loop, three draws per try); then `Creature_takeDamage`. Damage is never
refused.

Phases: none by hit points. The ground pound can recur every 600 frames, the wave only 780
frames after the last special. Script-driven: nothing class-specific.

Per-machine: (a) none found: run calls `fx_spawn`, `fx_ringBurst`, `decal_add` and sounds,
all sinks; every decision uses the own generator, the clock and world queries. (b) draw is
`Creature_draw` plus the holder's draw; no store. (c) none.

Neighbours that are not Zek code: 0x2c1d4c (with stubs 0x2c1f54, 0x2c1f74) is the static
initialiser and destroyer of the Wraith and WarWraith instance lists; 0x2c3c68 constructs the
static `SkillShock` object.

#### Innoruuk  (factory `Innoruuk`; vtable 0x515a28; size 0x4d0)

Functions: ctor 0x2735dc, draw 0x273b20, run 0x273bd0 (11,760 bytes), trigger 0x2769c0,
takeDamage 0x276a58, setState 0x276a80, death particles 0x277110; static initialiser 0x279c58
with stub 0x279fec.

Constructor: `Creature_ctor` with max-hp argument 10 and class definition 0x500878; a light at
+0x400; radius 30, turn rate 1.2, scale 2.0, speed 0, activity radius +0x3c4 = 44000, creature
flags |= 0x1020040400; resistances +0x5c 0.4, +0x60 0.35, +0x64 0.4, +0x68 0.4, +0x6c 0.35.
Property read: `invulnerable` (int) → +0x3e0 = 1. (A comparison of the level name with
`hatecut` only stores a 0 that is already there.) `obj_runEvery60`, `Creature_init`; the state
stays 0 without a setState call.

| Offset | Type | Meaning | Where |
|---|---|---|---|
| +0x3c8 | s32 | **armed**: 1 = weapon in hand (melee phase), 0 = unarmed (beam phase) | state 3, 0x12, 0x17, draw |
| +0x3cc | s32 | "drop the weapon on the next hit-reaction event" | setState 0x12, state 0x12 |
| +0x3d0, +0x3d8 | s32 | slam particles running; light-flash latch | states 0xb, 0xc, 0xe |
| +0x3e0 | s32 | invulnerable; only writer is the constructor; also tested by `damage_apply` (0x1e83cc) | takeDamage |
| +0x3e4 | handle | the dropped weapon prop | states 0x12, 0x17 |
| +0x3e8 | s32 | clock before which the ball attack is not repeated | states 3, 10 |
| +0x3ec | s32 | clock until which he stays unarmed and uses the beam | state 3, setState 0x12 |
| +0x3f0, +0x3f4, +0x3f8 | s32, s32, handle | clock at death; ring radius; trail handle of the death sequence | state 0x14 |
| +0x43c | float | light radius, decays 1.8 per frame | run head |
| +0x4c8 | handle | beam sound | state 9 |

Run, before the switch: `fx_modelStatusEffects` (effects), light update, `Creature_processDamage`,
`Creature_run`, `Creature_updateActive` — **its result is not used**, so his AI runs whether or
not he is "active" — `Creature_stepAnim(1.0)`, `Creature_applyKnockback(0.2)`, slot 23.
"hit(R, arc, flags)" below is `Creature_hitTargetOrPlayerInArc(0, target radius + own radius +
R, facing, arc, +0xd0…+0xd2, rating +0xd4, flags, no descriptor)`, which hits the target if it
is in the arc and otherwise whatever player is.

- **0** idle: can see target → 3; else once clock > +0xf4 → 1. **1** wander: can see target →
  3; while clock ≤ +0xf4 `Creature_moveToDest`, afterwards → 0.
- **3** chase, armed. No target → 0. The following tests are made first on the target
  (`Creature_canSeeTargetEdge`, lead 0.4) and then, if none matched, on any player
  (`creature_findPlayerInCone`); the first match decides:
  within radius + 75, arc 12000 → 0xc with probability 50 % (own draw), else 6;
  75 to radius + 125, arc 2000 → 0xe with 70 %, else 6;
  within radius + 100, arc 20000 → 6;
  within radius + 135, arc 7000 → 10 when clock > +0x3e8, otherwise keep chasing;
  behind him (facing − 0x7fff, arc 4000) within radius + 100 → 0xb.
  No match → `Creature_moveToTarget`.
- **3** chase, unarmed. No target → 0x17. While clock ≤ +0x3ec: target or any player within
  radius + 100, arc 20000 → 0x17 with probability 40 %, else 9; nobody in range → move to the
  target. Once clock > +0x3ec → 0x17.
- **5** → 3 when not rooted.
- **6** swipe: on event bit 0 the light flashes and `hit(100, arc 20000, flags)` with flags
  0x40001 in 30 % of cases (own draw) and 1 otherwise. Turns toward the target while the clip
  plays. → 3.
- **9** hate beam (unarmed): glows at model attach points 0 and 1 every frame; on event bit 0
  a `HateBeam` object is created (`pool_new(0xb0)`, constructor 0x277468) with the two points,
  Innoruuk as owner and the skill 27 object, and a looping sound starts. Turns toward the
  target. When the clip ends the sound stops and → 3.
- **10** ball of hate (armed): on event bit 0 the aim angle is computed by
  `creature_aimAngleAt(350, …)` from attach point 1 (his own position is replaced by that
  point for the call and restored), +0x3e8 = clock + 120, and **three** `HateProjectile`
  objects (`pool_new(400)`, constructor 0x278158) are created at aim − 5500, aim and aim + 5500
  with the skill 28 object and the integer monster level (0x4f714c). → 3.
- **0xb** rear slam: on event bit 0 `camera_shake(22)`, a `LightEffect` 100 units ahead, 60
  particles (60 own draws) and `hit(100, arc 5000, 0x80001)`. → 3.
- **0xc** slam: on event bit 0 a `LightEffect`, 60 particles, then an own draw: half the time
  shake 22 and `hit(75, arc 12000, 0x80001)`, otherwise shake 14 and the same hit with flags
  0x40001. When the clip ends: if the target (or a player) is 75 to radius + 125 away within
  arc 2000 → 0xe with probability 80 %, else 3.
- **0xe** lunge: on event bit 0 shake 22, `LightEffect`, 60 particles, `hit(125, arc 3000,
  0x80001)`. → 3.
- **8** waits until clock > +0xf4 (set to clock + 300 on entry), **0xd** waits for its clip;
  both → 3. No request for either exists in the class.
- **0x10** → 0 when the attack cooldown is over, else flee.
- **0x12** hit reaction: if +0x3cc is set, on event bit 0 he becomes unarmed (+0x3c8 = 0) and
  a `PhProp` (0x248 bytes, `PhProp_ctor3` 0x155394) of his weapon is created at a model point
  and linked at +0x3e4. → 0 when animation flag 0x10 clears.
- **0x17** re-arm: 80 particles a frame converge on the two attach points (400 own draws per
  frame) and the dropped prop glows; on event bit 0 the prop is deleted and +0x3c8 = 1. → 3.
  This is also the state he enters first: he is created unarmed.
- **0x14** death, timed from +0x3f0 (t = clock − +0x3f0): camera shake growing until t = 3060;
  a sound chosen by own draws every 45th simulation frame until 2880; from 1981 to 2339 a
  `HateSoul` (`pool_new(0xac)`, constructor 0x279640) every 47 and every 37 clock frames, from
  2341 to 2699 every 17 and every 37, each in a direction drawn from his generator; from 2881
  ten particles a frame; at 3061 the body bursts into particles (0x277110), object flags |= 3
  and creature flag 0x20000000000 are set and an expanding ring runs for 64 frames; at 4500
  `obj_delete`. Screen flashes come from `gfx_setColorOffset`.

setState 0x276a80: 0 and 1 set +0xf4 = clock + own draw % 120 (+ 300 for state 1). A request
for **0x12** is honoured only with probability 31 % and only while armed; otherwise the state
is left unchanged. When honoured: from state 0xd, with 50 % the disarm clip is started and
+0x3cc = 1; from any state but 0x17, with 20 % the disarm clip, +0x3cc = 1 and +0x3ec = clock +
3600; else the ordinary hit clip. State 0x17 cannot be interrupted by a hit reaction. 0x14:
object flag 0x4000, +0x3f0 = clock, activity radius 44000, `Creature_dropLoot(36, 1, 10, 1, 6,
1, …)`, slot 28. Leaving state 9 stops the beam sound.

trigger (slot 3) 0x2769c0: a non-zero value stores state 0x17 directly (no filter) and starts
the arming sound and clips. takeDamage 0x276a58: nothing while +0x3e0 is set, otherwise
`Creature_takeDamage`.

Phases: not by hit points. He alternates between armed and unarmed: about 6 % of hit-reaction
requests while armed (31 % × 20 %) disarm him for up to 3600 frames, during which he uses the
beam and, with 40 % per decision, re-arms early.

Script-driven: the `invulnerable` property; the script built-in `trigger`. `NITBON2` creates
him with `generateMonster('bossGen', 'Innoruuk')`.

Per-machine: (a) none found by scan and reading: seven `camera_shake` calls,
`gfx_setColorOffset`, glows and particles are sinks; decisions use the own generator, the
clock, `g_simFrame` and the monster level. `fx_modelStatusEffects` (gameplay area) was not
followed. (b) draw is `Creature_draw` and, when armed, the weapon model; no store. (c) none.

#### HateBeam, SpellHateEffect, HateProjectile, HateSoul

**HateBeam** (vtable 0x515908; 0xb0 bytes): ctor 0x277468, run 0x2775e8, destructor 0x2780e0.
Lives 180 frames or until its owner (handle +0x4c) is gone. Each frame
`world_collectObjectsInArc(200, 120, 0, owner position, owner facing)` is searched and the last
object the owner's slot 20 calls an enemy is the victim. Without a victim six beams are drawn
to random ground points within ±11000 of the facing, up to 200 away (24 own draws a frame).
With one, the beams end on it and, if it carries no `SpellHateEffect` (type info 0x3cb0d8),
one is created (`pool_new(0x30)`, 3 seconds, integer monster level, skill 30) and attached
with `creature_addSpell`. The level and skill pointer passed to the constructor are stored but
not read by run. The beam handles are tested only for "already created"; both branches make
the same four draws.

**SpellHateEffect** (Spell table 0x515b70; 0x30 bytes): ctor 0x27930c, slot 2 0x279420. The
constructor draws `g_randSeed` once for the spell's own generator; expiry = frame + seconds ×
60. Slot 2 is the per-frame update that `Creature_updateSpells` calls (the existing name
`SpellHateEffect_takeDamage` was wrong; it is now `SpellHateEffect_update`): until expiry it tints the victim and, on every 30th
simulation frame, takes v = the skill 30 value query (skill table offset 0x5c) at the stored
level, one draw from the spell's generator, and calls `damage_apply(v × 0.5, (v + 20 % × draw)
× 0.5, victim, attacker 0, rating 100000, flags 0x40)`. After expiry it deletes itself.

**HateProjectile** (vtable 0x515878; 0x190 bytes): ctor 0x278158, run 0x2783e8, draw 0x279048,
chain picker 0x279188, membership test 0x2792cc. Fields: +0x4c skill pointer, +0x50 candidate
list, +0x54 chosen list, +0x58 birth frame, +0x5c speed (350 per second), +0x180 level,
+0x181 mode (0 flying, 1 hit, 2 fizzled), +0x182 chain length 4, +0x184 chain radius squared
(3600), +0x188 owner handle. It flies along its facing, sinking one unit a frame, for at most
180 frames. Every 8th simulation frame a ±20 box is searched: terrain above it or a
non-creature object ends it (30 frames of fade); an enemy of the owner within its radius + 20
is hit. On a hit all the owner's enemies in a ±600 box become candidates and up to four more
are chained, each the nearest unchosen one within 60 units of the previous pick; one own draw
picks the knock-back flag (0x40000 or 0x80000); v = the skill 28 query at table offset 0x6c;
every chosen object takes `damage_apply(v, v + 20 % × one own draw, object, attacker 0, 100000,
flags | 0x40)` and a 3-second SpellHateEffect if it has none. Several hundred own draws a
frame place particles. Draw: a glow only.

**HateSoul** (vtable 0x515998; 0xac bytes, Projectile-derived): ctor 0x279640, run 0x279850. A
visual of the death sequence: flags 0x4003, 600 frames, wanders by its own generator through
`obj_moveAndCollide`.

#### Marr  (factory `MattMarr`; vtable 0x5160d0; size 0x4a8)

Functions: ctor 0x2835a0, draw 0x2838ec, run 0x283afc, slot 12 0x28453c, slot 11 0x2845e4,
setState 0x28468c, slot 36 0x284b50, death effects 0x284b68; static initialiser 0x2858ac with
stub 0x285b10.

Constructor: `Creature_ctor` (max-hp argument 10); Weapon1 holder at +0x3c8 with model entry
0x11 in hand 1; radius 20, turn rate 1.2, kind +0xb4 = 9, +0x28 = 0x28, +0xf4 = frame + 300,
creature flags |= 0x22000040000, the five resistances 0.5. setState(0), `obj_runEvery60`,
`Creature_init`.

| Offset | Type | Meaning |
|---|---|---|
| +0x460 | s8 | **power counter**: +1 for every melee hit that lands while it is below 5, and +1 on every 90th clock frame on which the target is charging him |
| +0x464, +0x494 | light, Vec3 | light of the death sequence and its position |
| +0x4a0, +0x4a4 | s32, float | death stage 0–3 and seconds spent in it |

Run, before the switch: weapon-holder update, `Creature_processDamage`, `Creature_run`,
`Creature_updateActive` (returns when inactive), `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.3)`, slot 23; the weapon glow colour is set from the counter
(holder slot 9); while the state is not 0 and the scale +0xdc is below 1.25 he grows by 0.002
a frame with tint preset 6.

- **0** / **1**: as Zek.
- **3** chase: no target → 0; an enemy within 36, arc 10000 → 5; counter 1–4 and target 120–360
  away within arc 2000 → 0xb; counter ≥ 5 and target within 700 → 9; enemy within 36 in any
  direction → turn; else move to the target.
- **5** between attacks: counter ≥ 5, target within 60 / arc 12000 and
  `Creature_isTargetAttackingMe` → 0x17. An enemy within 60 / arc 12000: counter below 5 → 6, 7
  or 8 by an own draw; counter ≥ 5 → 8. Otherwise the 0xb and 9 tests of state 3; then an enemy
  within 60 in any direction → 10; else, when not rooted, → 3.
- **6, 7, 8, 10** swings (10 turns toward the target): on event bit 0, with the counter below
  5, `Creature_hitAllEnemiesInArc(0–60, arc 12000, +0xd0…+0xd2, rating +0xd4, flags 8, weapon
  descriptor)` and counter + 1 if anything was hit; with the counter at 5 or more the same
  arc with **double damage** and flags 0x100008, and the counter returns to 0. State 6 leaves
  for 5 as soon as no enemy is in the arc. → 5.
- **9**: weapon glow, turn toward the target; on event bit 0 skill 66 (PlanarWind) is cast
  (skill table offset 0x14, level from slot 35, own position and facing) and the spell is
  attached; counter = 0. → 5.
- **0xb** lunge: turns at rate 0.4; on event bit 0 `Creature_hitAllEnemiesInArc(0–60, arc
  12000, normal damage, flags 0x100008, weapon descriptor)`; a hit resets the counter. → 5.
- **0x17** guard: leaves for 3 if the target is no longer within 60 / arc 12000, and for 5 once
  clock > +0xf4. **0x18** guard: → 3 once clock > +0xf4.
- **0x10** → 0 or flee; **0x12** → 3; **0x13** → 3; **0x14** `Creature_deadUpdate(30)` and the
  death effects.

setState 0x28468c clears creature flag 0x200 (blocking) on every call. 0x10 sets the cooldown
to 60. A request for 0x12 is honoured only from state 0x17 (a flinch clip); from any other
state it is dropped, so Marr has no ordinary hit reaction. 0x17 and 0x18 set creature flag
0x200, and if no `SpellSpiritShield` (type info 0x3d19f0) is attached they cast skill 94
(SpiritShield, table offset 0x14, level from slot 35) on himself; +0xf4 = clock + 60 + own
draw % 60. 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, …)`, `Creature_clearStatus`,
`camera_shake(20)`, death stage 0, slot 28.

Slot 12 (nearby event) 0x28453c: kind 2 with a source object within ±10000 of his facing,
while in state 3 or 5, requests state 0x18. Slot 11 (touched objects) 0x2845e4: during the
lunge 0xb every touched player that is not already in a knock-down clip takes
`damage_apply(0, 0, player, Marr, 100000, flags 0x100041)` — no damage, a knock-down. Slot 36
0x284b50: returns 20 in state 0x18 and 5 otherwise (the Dodge level against missiles, 2.1).

Death effects 0x284b68, called every frame of state 0x14: the screen is darkened; animation
event 0x40 starts stage 1 (6.02 seconds: a light, camera shake growing with t², particles
whose number and direction come from generator 0x404468); then the body is hidden (object
flag 2), shake 25, stage 2 (one second of a white full-screen rectangle fading, drawn from run
code); stage 3 deletes the object after 0.09 seconds. Stage timing depends only on +0x4a4,
which grows by 1/60 per run call.

Phases: none by hit points; the counter is the phase. Script-driven: nothing class-specific.

Per-machine: (a) none in run, setState, slot 11 or slot 12. The death effects use generator
0x404468 for particle count and scatter only. (b) draw (`Creature_draw`, holder draw, glows at
the model's sample points in death stage 1) reads `g_simFrame`, +0x4a0 and +0x4a4 and stores
nothing. (c) none.

#### MummyKing  (factory `MummyKing`; vtable 0x516b50; size 0x4a0)

Functions: ctor 0x29afb4, draw 0x29b2c4, run 0x29b360, trigger 0x29c3b0, takeDamage 0x29c544,
setState 0x29c574, helpers 0x29c9f8 and 0x29ca5c; static initialiser 0x29d668 with stub
0x29d6ec (the MummySnake particle definition).

Constructor: `Creature_ctor` (max-hp argument 10); Weapon1 holder with model entry 0xe in hand
1; radius 25, turn rate 1.2, scale 1, creature flags |= 0x820010000; resistances +0x5c −0.2,
+0x64 0.6, +0x68 0.7, +0x6c 0.3. `obj_runEvery60`. Unlike the other bosses the constructor
calls neither `Creature_init` nor setState.

| Offset | Type | Meaning |
|---|---|---|
| +0x460 | s32 | clock before which no new summon starts |
| +0x464 | handle[4] | one `SpawnMummy` per player slot |
| +0x474 | handle | the shaman `SpawnMummy` |
| +0x478 | s32 | step of the running summon |
| +0x47c | s32 | clock before which no snakes |
| +0x480 | handle[4] | one `MummySnake` per player slot |
| +0x490 | s32 | written (clock + 600) on entering state 0x17; no reader found |
| +0x494 | s32 | step of the dust teleport |
| +0x498 | u8 | 0 = disease, 1 = poison for the next state-7 hit |

Run, before the switch: while creature flag 0x4000000 (friendly) is set the `ShowName` text
pointer +0x368 is reloaded from the property, otherwise cleared — he can be talked to only
while friendly. Then weapon-holder update, `Creature_processDamage`, `Creature_run`,
`Creature_updateActive` (result not used), `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.2)`, slot 23.

- **0** → 3 when he can see the target. **1** → 3 likewise; → 0 once clock > +0xf4; else
  `Creature_moveToDest`.
- **3** and **5** share one chooser (state 3 without a target → 0): if clock > +0x460 and a
  mummy slot is free (0x29ca5c: one of the first `g_numPlayers` handles at +0x464 is empty, or
  all are used and +0x474 is empty) → 9. Target within 50 / arc 4000, or any enemy within 50 /
  arc 6000 → 6 or 7 by one own draw. Else, if snakes are allowed (0x29c9f8: clock > +0x47c and
  one of the first `g_numPlayers` handles at +0x480 is empty) → 8. Else a free mummy slot → 9.
  Then state 3 turns toward a target within 50 or moves to it; state 5 goes to 3 when not
  rooted.
- **6** swing: on event bit 0 `Creature_hitTargetOrPlayerInArc(0, radius + 50, arc 6000,
  +0xd0…+0xd2, rating +0xd4, flags)` with flags 0x80001 one time in four (own draw), else
  0x40001. → 3.
- **7** enchanted swing: on event bit 0 a descriptor with one effect is built — type 0x26
  (disease) from the skill 25 (DiseaseWeapons) value query, or type 0x17 (poison) from skill
  26 (PoisonWeapons), by +0x498; the query is made through skill table offset 0x5c at the
  integer monster level and the second value adds up to 20 % by an own draw — and the same
  arc is hit with flags 1 and that descriptor. → 3.
- **8** snakes: on event bit 0, for every player slot below `g_numPlayers` whose handle at
  +0x480 is empty and whose player is alive, a `MummySnake` (`pool_new(100)`, constructor
  0x29cfe4) aimed at that player is created. → 3.
- **9** summon: step i (0 … `g_numPlayers` − 1) happens 60 × i frames after entry: if handle
  +0x464[i] is empty a `SpawnMummy` (`pool_new(0x68)`, constructor 0x29ce20) is created at
  `world_findFreeSpot(position, 200, 15)` — a shared-generator routine — or 50 units ahead if
  none is found. The type depends on his hit points: above two thirds `mummydesertsoldier`,
  above one third `mummytemplesoldier`, else `mummyelitesoldier`. The step after the last
  player does the same for +0x474 with `mummydesertshaman` / `mummytempleshaman` /
  `mummyeliteshaman`. → 3 one second after the last step.
- **0x17** dust teleport: 48 frames after entry he is hidden (object flags |= 3, creature flags
  |= 0x20000000800) and moved — home if he is farther than HomeRange from it, otherwise by
  `Creature_relocateAlongClearRay(400, …)` toward the target — and a `DustDevil` is created at
  the new place; 48 frames later he is visible again; after 120 → 3. **0x18** waits until clock
  > +0xf4 → 3. **No request for 0x17 or 0x18 exists in the class** (run, setState and trigger
  were searched for the constants): who enters them is Unknown.
- **0x10**, **0x12**, **0x13** → 0 when their condition ends. **0x14** `Creature_deadUpdate(20)`.

setState 0x29c574 clears creature flag 0x200 on every call. 0 and 1 set +0xf4 = clock + own
draw % 120 (+ 300); 7 draws +0x498; 8 sets +0x47c = clock + 300; 9 sets +0xf4 = clock, +0x460 =
clock + 600, creature flag 0x200 and the step to 0; a request for 0x12 is ignored during a
state-6 swing and in 0x13 and 0x17; 0x13 is ignored in 0x17; 0x14 calls
`Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, …)` and slot 28; 0x17 sets +0x490, creates a
`DustDevil` at his position and sets creature flag 0x200; 0x18 sets +0xf4 = clock + 120 and
the same flag.

trigger (slot 3) 0x29c3b0: value 1 clears creature flag 0x4000000 and object flag 0x1000000 —
he turns hostile; value 0 puts the weapon into, or takes it out of, hand 1 with a particle
effect. takeDamage 0x29c544: nothing while creature flag 0x4000000 is set.

Phases: the hit-point thirds choose which mummies are summoned; nothing else changes.
Script-driven: the built-in `trigger`; `NITBON2` creates him with
`generateMonster('bossGen', 'MummyKing')`.

Per-machine: (a) none found: run reads `g_numPlayers`, the player table, the monster level
and `g_simFrame`; `world_findFreeSpot` draws the shared generator from run code. (b) draw is
`Creature_draw` plus the holder's draw; no store. (c) none.

**DustDevil** (table 0x516db8; 0x58 bytes): ctor 0x29caa8, run 0x29cb98. Object flags |= 9;
for 60 frames it emits particles into its own particle group with own-generator positions,
its radius growing 2 a frame to 96. Its run never deletes it; what does is Unknown.

**SpawnMummy** (table 0x516d28; 0x68 bytes; derives from DustDevil): ctor 0x29ce20, run
0x29cea8. After the 60 frames it creates a `Mummy` (`pool_new(0x480)`, `Mummy_ctor` 0x298418
with a facing from its own generator and the type name) with creature flag 0x1000000 (the
corpse is removed), linked at +0x60. When its owner (handle +0x64) is gone or dead it sends
the mummy to state 0x14. It deletes itself once the mummy handle is empty — so a slot of the
king is free again only when the previous mummy's corpse has gone.

**MummySnake** (table 0x516c98; 0x64 bytes): ctor 0x29cfe4, run 0x29d0c0. Lives 360 frames.
Target handle +0x50, re-picked with `players_findNearestOnTeam(1000, position, −1)` when
missing or dead. It turns 500 a frame toward the target, climbs one unit a frame toward its
mid-height and moves 2.17 units a frame. Within the target's radius + 5:
`damage_apply(50, 50, target, the king, rating 10000, flags 0x10000)` with a poison effect
(type 0x17) sized by the skill 26 value query at the integer monster level. It ends on the
hit, when its owner is gone or dead, or at the end of its life (`fx_spawn` 0xe six times and
3, `obj_delete`).

#### Natasla  (factory `Natasla`; vtable 0x516f90; size 0x3c8)

Functions: ctor 0x29d70c, draw 0x29d844, run 0x29dbf0, setState 0x29dc3c.

Not a fighter. The constructor sets object flags 0x1000008 (the "dead" bit, so nothing targets
it), creature flags 0x200040000, hit points 1000, all five resistances 1.0 and radius 15, and
calls `Creature_init`. run is `Creature_run`, `Creature_updateActive` and
`Creature_stepAnim` only — no damage processing and no AI. setState plays the idle clip for
state 0, ignores requests for 1, 3, 5, 6, 0x10, 0x12, 0x13 and 0x14, and stores any other
number. draw calls `Creature_draw` and then draws five sub-models at attach points 0–4, each
spun by the creature clock; it stores nothing. Per-machine: none.

### SpiderQueen, WebTrap, VampireLord, RedDragon, Nightmare, Hag

*Reader's notes for this group.* Method: every function listed was read in full from the decompile; disassembly was
used where the decompile dropped stack arguments. "own draw" = GameObject_rand on the object.
Animation entry n = class-definition word at +4+8n (so the handle at classDef+0x24 is entry 4).
Event masks come from `creature_setDefEntryParams` (0x118378) calls in each constructor: four
(time, mask) pairs per animation entry; the time unit was not verified (Inferred seconds).

#### SpiderQueen  (factory `SpiderQueen`; vtable 0x50fbf8; size 0x430)

Functions: ctor 0x2ad1c0, run 0x2ad630, draw 0x2ad5e4, takeDamage 0x2aed60, setState 0x2aeec4,
trigger (slot 3) 0x2ad1b8 = empty. Helpers: 0x2af4c0 (may-grab test), web strand sub-object
0x2afc04 / 0x2afc1c / 0x2afc28 / 0x2afda4 / 0x2afe38 / 0x2b0080 / 0x2b04ac / 0x2b04ec, strand
line drawer 0x2af510 (shared with WebTrap_draw and BlackWidow). Slots 1 (0x3c4818) and 15
(0x1271c0) are also unique to the class (not read). 0x2acfd8, 0x2ad158, 0x2ad180, 0x2ad1a8 lie
in the range but belong to BlackWidow (see end of this section).

Constructor 0x2ad1c0: two own draws BEFORE the base constructor runs (0x2ad21c, 0x2ad228; the
generator word +0x44 is not yet seeded and pool_new 0x14fdb8 zero-fills the block, so both
draws start from 0 and are the same on every machine) give the max-hp argument (d&7)+(d&7)+32;
Creature_ctor(…, class def 0x5029d0, props) stores it and then, when a type name is supplied,
its own Creature_setStats call replaces hit points (0x10a1d4/0x10a204). Radius +0x1c = 70, turn rate +0xb0 = 0.7,
speed +0xb8 = 120, creature kind +0xb4 = 0x13, +0x28 = 100, +0x64 = 1.0 (poison resistance
slot per gameplay.md), +0xe0 = -50, scale +0xdc = 1.0, activity radius +0x3c4 = 1200, creature
flags |= 0x8020002000, +0x3cc = 0, eight words +0x40c..+0x428 cleared, web sub-object at +0x3d0
initialised with (0x29, 0xf0). Idle animation (entry 0xb, +0x5c) pushed with randomised time.
Start state 0. Run list: obj_runEvery60. No property is read by the class itself.
Event tables set here (entry: time->mask): 0x10 (spit): 0.3->1, 0.5->1, 0.7->1; 0x11 (state
0x17): 1.3->1, 2.5->1, 2.6->1; 0xc (turn, state 0x18): 0.2->1, 0.9->2, 1.1->1; 0x15 (web
shot): 0.4->1; 0xd, 0xe, 0xf (states 10/0xb): 0.5->1, 1.5->2; 4 (bite): 0.2->1; 6 (grab bite):
0.3->1, 1.3->2, 2.0->4; 5 (death): 6.0->0x80.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | "pull active" latch in states 7, 10, 0xb; "turning" latch in state 0x18 | run |
| +0x3cc | s32 | last attack state entered (6, 7, 8, 10, 0xb, 0xc); 10 or 0xb blocks the grab family | setState, 0x2af4c0 |
| +0x3d0 | 0x3c bytes | web strand sub-object (below) | run, helpers |
| +0x40c | s32[8] | per-leg clock stamp, indices 2..7 used (= model attach points 2..7): 0 = leg intact, else clock+20 at the moment it was shot off | takeDamage, tail of run |
| +0xf4 | s32 | idle: clock after which state 0 goes to 1; cleared by setState 8 | run, setState |
Web strand sub-object (offsets inside it): +0x00 strand count (1 flying, 5 when it catches,
counts down as the victim struggles); +0x04 float fan width (1.0 at catch, +0.5 per frame up
to the victim radius); +0x08 line alpha (40 at launch, -3 per frame when idle); +0x0c caught
flag; +0x10 Vec3 tip; +0x1c handle victim; +0x20 Vec3 tip velocity; +0x2c expiry clock (1 =
armed but not launched, 0 = idle); +0x30 flight frames (0x29 = 41); +0x34 hold frames (0xf0 =
240); +0x38 clock of the next struggle test.

Web strand update 0x2b0080(sub, source, clock), every frame from run:
- clock < expiry, not caught: three sub-steps per frame of tip += velocity/60 (15 units per
  frame, about 615 over the 41 frames). Per sub-step: tip z <= terrain_height(5, tip) -> make a
  WebTrap (pool_new(0xa0) + WebTrap_ctor2 0x2b07c0(source, tip)) and release; no victim handle
  -> release; victim not a creature -> WebTrap at the tip and release; victim has knockback
  speed > 0 or is a dead creature (flags 0x28) -> release; else if horizontal distance tip to
  victim < victim radius: caught = 1, expiry = clock + 240, strands = 5, fan width 1.0.
- caught: victim gone or not a creature -> release. Otherwise every frame the victim's
  knockback speed +0x2e8 = 160 and knockback angle = toward the source (the queen); tip =
  victim position, z + half its height. Struggle: when clock > +0x38 and the victim is a Player
  (object flag 0x40) with action state +0x58c == 1 (melee swing): strands - 1, at 0 release;
  +0x38 = clock + 5.
- clock == expiry -> release. clock > expiry: expiry kept only if it is the "armed" value 1,
  caught cleared, alpha -3 per frame to 0, victim handle dropped.
Release 0x2b04ac: if caught and the victim is a creature its knockback speed is zeroed;
expiry = 0. 0x2b04ec = "expiry != 0" (busy). No damage anywhere in the strand code.

Run 0x2ad630, every frame before the state switch: Creature_processDamage, Creature_run,
Creature_updateActive, events = Creature_stepAnim(1.0), Creature_applyKnockback, V23
pickTarget(0), web update 0x2b0080(sub, position with z+10, clock), web line queue
0x2afe38(sub, same position). (No weapon holder.) "sees(min,max,arc)" below =
Creature_canSeeTargetIn(min, max, 0, this, facing, arc, 0).

States:
- 0 idle: V25(0) true -> 3; else when clock > +0xf4 -> 1.
- 1 wander: V25(0) true -> 3; else Creature_moveToDest.
- 3 chase and 5 between attacks use the same ordered chooser:
  1. sees(0,600,0x7fff) and not sees(0,600,0x4000) -> 0x18 (turn round).
  2. sees(0,30,2000) -> 6.
  3. G and sees(0,450,3000) -> 8 (web shot).
  4. G and sees(0,250,5000) -> 7.
  5. G and sees(0,250,5000) -> 10 (same test as line 4, so not reachable from here unless the
     two calls differ; Observed as written).
  6. G and sees(0,250,6000) -> 0xb.
  7. sees(0,450,3000) -> 0xc (spit).
  8. state 3: not sees(0,30,0x7fff) -> Creature_moveToTarget, else Creature_turnToTarget.
     state 5: Creature_isNotRooted -> 3, else stay. State 3 with no target -> 0.
  G = 0x2af4c0: +0x3cc is neither 10 nor 0xb, there is a target, it has object flag 0x20
  (creature) and its knockback speed +0x2e8 is exactly 0.
- 6 bite: on event bit 0 with a target: Creature_hitTargetAtReach(radius + 24, this, +0xd0,
  +0xd2, +0xd4, flags 0x90004, descriptor) = damage_apply on the current target only, if it is
  alive and within 60 units (3-D) of the point radius+24 ahead. Descriptor: one slot type 0x17
  (poison) with v1 = q, v2 = q + trunc(q x 0.2 x d/65536), v3 = 0, where q = PoisonWeapons (26)
  value query (skill table offset +0x5c) called with (0, (int) monster level 0x4f714c, 0) and
  d = one own draw. When animation flag 8 clears -> 3.
- 7 grab bite: bit 0 sets +0x3c8; mask 4 clears it and zeroes the target's knockback speed if
  it is a creature. While +0x3c8 is set, every frame: P = model attach point 0 (fallback
  position + facing x (radius + target radius + 30)); if the target is a creature its
  knockback speed +0x2e8 = 15 x horizontal distance to P and its knockback angle +0x2e0 =
  direction target->P (written as angle(target - P) - 0x7fff): the target is dragged to P
  (Inferred from Creature_takeDamage's use of +0x2e0). Mask 2: same hit call and poison rider
  as state 6 but flags 0x10004. Flag 8 clear -> 3.
- 8 web shot: setState arms the strand (+0x2c = 1). On bit 0, if the target is a creature:
  0x2afc28(300, sub, position z+10, target, clock): links the victim handle, velocity = unit
  vector to (target position, z + 0.25 x target height) x 300, tip = start, alpha 40, strand
  count 1, expiry = clock + 41. Then: strand no longer busy -> 3; caught flag set -> 9; else
  stay. If the target is not a creature or is gone when bit 0 fires the strand stays armed
  and nothing in this state leaves it (Inferred: only a hit reaction, stun or death does).
- 9 reel in: strand busy: if a target exists and sees(0,50,2000) -> release (0x2b04ac) and
  state 7; then Creature_turnToTarget. Strand not busy -> 3.
- 10 / 0xb swipe-and-pull: bit 0 sets +0x3c8 if the target is a creature with knockback speed
  0. While sees(0,250,5000) and +0x3c8: same drag as state 7 but speed = 6 x distance. Mask 2
  and sees(0,30,2000): hit call and rider as state 7 (flags 0x10004). Flag 8 clear -> 3 and
  the target's knockback speed is zeroed. setState 0xb picks animation entry 0xf or 0xe by the
  sign of (angle to target - facing).
- 0xc spit: flag 8 clear -> 3. On each bit 0 (three per animation by the table): aim = lead
  point from Creature_leadTargetPoint(this, position + facing x 300); muzzle = attach point 0
  (fallback position + facing x 85, z + 36). Twice: heading = direction to aim clamped to
  facing +/- 4000, plus (own draw % 2000) - 1000; velocity = 300 horizontal, vertical = ((own
  draw % 50) + 75) x 3-D distance(this, aim) / 300; pool_new(0xa8) + PoisonProjectile_ctor
  0x2b153c(scale = own draw/65536 x 0.5 + 0.5, classDef, 0x16, 0x17, 0x18, 0x1a, muzzle,
  velocity, angle = facing - 0x4000, owner = this) (last two from the stack, 0x2ae774-0x2ae798).
  Three own draws per projectile (the third is skipped if the pool is full). The projectile's
  damage is in PoisonProjectile_run 0x2b176c (outside this group's range, read only lines 0x2b19f8 on):
  on impact combat_applyAreaDamage(12, 36, owner, position, q, q + 20% x draw, flags 0x10000,
  poison rider built the same way) with q = PoisonWeapons query at level_getMonsterLevel().
- 0x10: Creature_isAttackReady -> 0, else Creature_fleeFromTarget.
- 0x12: until animation flag 0x10 clears, then 3.  0x13: Creature_isNotStunned -> 0.
- 0x14 dead: Creature_deadUpdate(100, this, events, zero vector, 0); on mask 8 and not hidden:
  camera_shake(8, 0).
- 0x17: camera_shake(4, 0) on bit 0; flag 8 clear -> 3. Nothing in the class enters 0x17
  (Inferred: script / generator entrance).
- 0x18 turn round: bit 0 toggles +0x3c8; mask 2 camera_shake(5, 0); while +0x3c8 is set and a
  target exists Creature_turnToTarget; flag 8 clear -> 3.
- 2, 4, 0xd-0xf, 0x11, 0x15, 0x16: no code.
After the switch, every frame: for legs i = 2..7 with stamp s = +0x40c[i]: if clock < s a
strong blood jet (strength (s - clock)/20 x 36) from attach point i, else if s != 0 a weak one
(16) on a 1-in-10 own draw. Each jet: own draws in threes until the vector is inside the unit
sphere, particle_spawn(0, def 0x8e4650); during the strong phase a 1-in-20 own draw adds a
decal (three more own draws). All own-generator draws, made in run. The particle definition is
built once behind the guard word 0x502ab0.

setState 0x2aeec4 (after Creature_filterState): speed reset to 120 for every state. 0: +0xf4 =
clock + (own draw % 300) + 120. 6/7/8/10/0xb/0xc record themselves in +0x3cc; 7, 10, 0xb, 0x18
clear +0x3c8; 8 arms the strand and clears +0xf4. 0x12: refused (state kept) when the current
state is 0x13 or 0x18, or is 6 or 0xc with the attack animation still playing; otherwise the
target's knockback speed is zeroed (drops a dragged victim) and one of four hit animations is
chosen from the hit angle +0x2e0. 0x14: radius 65, Creature_dropLoot(36,1,6,1,6,1, this,
position + facing x 60, facing, item name `venomsac`), object flag 1 CLEARED (the corpse stays solid),
death animation (jumped to its end if hidden), V28(0).

takeDamage 0x2aed60: Creature_takeDamage (which subtracts the amount from +0x228 at once),
then for legs i = 2..7: if hit points <= 180 - 20 x i (140, 120, 100, 80, 60, 40: absolute
values, not fractions of the maximum) and +0x40c[i] is 0: stamp = clock + 20, fx_spawn(3) at
attach point i, and OR a per-leg constant into the hidden-part mask +0xe8 (0x8021041, 0x42082,
0x184104, 0x10208208, 0x3810410, 0x1400820); finally +0x220 = model_buildHideMask. No state
change, no damage change.

Phases: none in the AI. Leg loss is visual only (mask + blood); nothing in run or setState
reads the leg stamps except the blood loop. Whether the scaled maximum is above 140 is Unknown
(set by Creature_setStats from the stat row).

Script-driven: no property or script use inside the class. scripts/NITBON2.txt `start` makes
it with generateMonster('bossGen', 'SpiderQueen') when variable nit2bonboss is 0, then applies
setCFlag('bossGen', 0, 1) and setMonsterVal('bossGen', 4, 2000) / (…, 1, 2000) to whichever
boss was generated. No other script names the class.

Per-machine:
(a) run / setState / takeDamage and the helpers: no camera, local-slot, audio, cosmetic-seed or
timer read (scan and reading). camera_shake x3 in run and fx_spawn(3) in takeDamage are
effects only. All decisions use the own generator. The web line queue 0x2afe38 is called from
RUN and appends to the global line buffer 0x7e0b00 (count 0x82cc98, cap 128) through
0x18fd18; 0x2af510 picks strand end points with a local generator seeded from the victim's
object ADDRESS (0x2af510 line with model_getSamplePoint) - line end points only, nothing reads
them back.
(b) draw 0x2ad5e4: sets global 0x41c14c = 4.0 (0x1797c8), Creature_draw(model, second model,
0), model_resetDrawState. No store into the object.
(c) draw: none of the listed actions.
Open: gameplay meaning of flags 0x10000 / 0x80000 at the take-damage end; who enters 0x17;
time unit of the event tables; slots 1 and 15 not read.

BlackWidow helpers that sit in this address range (called only from BlackWidow_run 0x2abdd8;
BlackWidow +0x414 is its variant word, 1 = the large one set in its ctor 0x2ab958):
0x2acfd8 (this, n): unless variant 1, sets hidden-part bit n (0..0xb) in +0xe8, rebuilds
+0x220, and for n <= 7 creates a 0x268-byte GutChunk (GutChunk_ctorFromProp 0x201ad0);
0x2ad158 returns 36 (variant 1) or 24; 0x2ad180 returns 120 or 60; 0x2ad1a8 returns 500. They
are used as (min, max) ranges in BlackWidow's canSee tests (0x2abdd8 state 3 / 5).

#### WebTrap  (factory `WebTrap`; vtable 0x50e348; size 0xa0; plain GameObject)

Functions: ctor (factory) 0x2b04f8, ctor2 (from the queen's / widow's strand) 0x2b07c0, run
0x2b0c74, draw 0x2b0954; unique slots 1 (0x3c66b8) and 15 (0x12e1e0) not read; all others base.
Constructors: both set object flag 1 (not solid), alpha +0x84 = 50, strand count +0x98 = 1,
fan width +0x9c = 0, +0x28/+0x29 = 0xff, glow resource +0x8c = res_find(`fx.lmp`, `spiderweb.tex`),
+0x90 = 0, obj_runEveryFrame. 0x2b04f8(this, pos, angle): end A = pos; casts terrain_raycast
(1200, from pos z+24, direction (sin, cos, 0) x 500); no hit in (0, 1] -> obj_delete(this);
else end B (+0x54) += hit point (Inferred: +0x54 starts at 0) and expiry +0x50 = -1 (waits
for ever). 0x2b07c0(this, A, B): end B given, expiry = g_simFrame + 600. No properties read.
Fields: +0x10 end A; +0x54 Vec3 end B; +0x4c s32 sprung flag (this class reuses the owner
word); +0x50 s32 expiry frame (-1 none); +0x60 Vec3 catch point; +0x6c / +0x78 Vec3 inner ends
of the two half strands; +0x84 s8 alpha / life (50); +0x88 handle victim; +0x8c, +0x90 glow
resource and glow level (0..70, +/-2 per frame); +0x94 s32 frame of the next struggle test;
+0x98 s32 strands left (4 when sprung); +0x9c float fan width.
Run 0x2b0c74 each frame:
- Not sprung: world_raycast(1200, from A with z+24, toward B, ignoring the previous hit) up to
  20 times along the strand; a hit object with object flag 0x20 or 0x40 whose exact class is
  not BlackWidow, SpiderQueen, Minotaur, Gremlin or SmallSpider (typeid compares) springs it:
  +0x4c = 1, catch point = hit point, strands = 4, victim handle linked. A sprung trap with
  expiry -1 gets expiry = frame + 600. A sprung trap whose victim handle is empty gets expiry 0.
- With a victim: fan width +0.5 per frame up to the victim radius. While alpha is exactly 50
  (trap not expired) and the victim is a creature: victim knockback speed +0x2e8 = 3 x
  horizontal distance to the catch point, knockback angle toward the catch point (held in
  place; no damage anywhere in this class). At alpha 49 (first frame after expiry) the
  victim's knockback speed is zeroed. Struggle: when frame > +0x94 and the victim is a Player
  (flag 0x40) whose action state +0x58c is 1 (melee swing): strands - 1, or expiry = 0 when
  only one is left; +0x94 = frame + 17. So four counted swings free a player; other creatures
  stay for the 600 frames.
- Before expiry: inner ends = midpoint of A and B, or the victim position; alpha forced to 50;
  glow +2. After expiry: inner ends retract toward A and B at 900 units/s, alpha -1 per frame,
  glow -2; at alpha < 1 the object destroys itself (V1(3)).
Triggers: none (slot 3 / touch / interact are base). Not named in any script; nothing saved
beyond the base record (slots 8/9 base).
The queen's strand makes one (0x2b0080) when the flying tip reaches the ground (tip z <=
terrain_height) or when the victim is not a creature.
Per-machine: (a) run reads g_simFrame and the world only - none found. (b) draw stores
nothing. (c) draw 0x2b0954 queues strand lines through 0x2af510 (local generator seeded with
the victim's address) and two glow_add calls whose rotation argument is the low 16 bits of the
object's own ADDRESS (and that + 0x4000): cosmetic, but address-dependent. No creation, no
shared or own generator, no script, no world query.
Open: clone (slot 15) and destructor not read; who else constructs it besides 0x2b0080 (one
caller each per the decompile headers).

#### VampireLord  (factory `VampireLord`; vtable 0x517ba8; size 0x480)

Functions: ctor 0x2b76e4, run 0x2b7be0, draw 0x2b7af0, takeDamage 0x2b93d8, setState 0x2b944c,
get model (slot 16) 0x2b9d10, second model (slot 38) 0x2b9d50, enter bat form 0x2b9be8, leave
bat form 0x2b9c54, own range/arc/line-of-sight test 0x2b9d90. Unique slots 1 (0x3cca38) and 15
(0x128ee0) not read.

Constructor 0x2b76e4: Creature_ctor(max hp argument 10, …, class def 0x502ea8, props). Radius
18, turn rate 1.3, move speed +0xb8 = 0 (movement is animation root motion through
Creature_settle / the move helpers - Inferred; only states 0x17/0x18 set 150 around their move
call), kind +0xb4 = 0x10, resistances: fire +0x5c = -0.2, poison +0x64 = 1, disease +0x68 = 1,
lightning +0x6c = 0.3; creature flags |= 0x20420000000; +0x3dc = clock + 300; +0x3cc, +0x3d0,
+0x3d8, +0x3ec, +0x3c8 = 0; an empty damage descriptor is laid out at +0x430 (slots at +0x454
= -1, colour quads +0x440 and +0x448 = 0). Loads `bat.lmp`. Property `wings` (int): when 0,
hidden-part bit 1 is set in +0xe8. Idle animation entry 5 pushed; state 0; obj_runEvery60.
+0x478 is not written by the constructor (first store is in setState 7 / 0x10 / 0x17) but
state 3 reads it; pool_new zero-fills the block, so it starts at 0.
Event tables (entry: time->mask): 0x12 (+0x94, used by 0x10, 0x14, 0x19): 0.3->1, 1.5->2; 0xd
(+0x6c, state 8): 0.3->1, 0.5->2; 0xe (+0x74, state 9): 0.2->1, 0.6->2; 0xf (+0x7c, state
10): 0.7->1, 1.2->2; 0xc (+0x64, state 0xb): 0.9->1, 1.2->2; 9 (+0x4c, state 0x18): 0.3->4,
0.4->8, 0.5->1, 2.0->2; 8 (+0x44, state 7): 1.2->1, 1.8->2; 4 (+0x24, state 0x17): 0.7->1,
1.0->2; 0x14: 2.0->0x40, 2.1->0x80.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | form: 0 = first form, 1 = second form (after state 0x19) | run 3, 0x19; setState; draw |
| +0x3cc | s32 | 1 while in bat form (model and textures from bat.lmp) | slots 16/38, setState tail |
| +0x3d0 | s32 | 1 = emit the 16-particles-per-frame cloud | run head |
| +0x3d4 | s32 | "victim held" latch of the bite (states 7, 0x18) | run |
| +0x3d8 | s32 | second form: attacks left in the current flurry (4..7); non-zero also means animation speed 1.5 and a red light quad | run, setState 8-0xb, 0x11 |
| +0x3dc | s32 | clock after which a new flurry may start | run 3, setState |
| +0x3e0 | Vec3 | copy of the position, with a z offset animated in 0x17/0x18; no reader inside the class range (Unknown user) | run |
| +0x3ec | s32 | 1 once takeDamage has asked for state 0x19 | takeDamage |
| +0x3f0 | 0x40 bytes | state block handed to fx_modelStatusEffects | run head |
| +0x430 | descriptor | passed to fx_modelStatusEffects; +0x440 / +0x448 colour quads (0x448 is the draw-time ambient light) | run, draw |
| +0x478 | s32 | last special state entered (7, 0x10, 0x17) | run 3 |
| +0xf4 | s32 | per-state timer (see setState) | run |
T(min,max,arc) below = 0x2b9d90(min, max, this, facing, arc): target exists, |angle to target
- facing| < arc, centre distance minus both radii < max, distance + target radius - own radius
>= min, and world_raycast(1.1, from own position at half height, toward the target, ignoring
self, mode 3) hits nothing before the target.

Run 0x2b7be0 head: in the second form fx_modelStatusEffects(0.5, 1.0, +0x430, classDef+0xac,
+0x3f0, position, facing, model, animation, state in 8..0xb) is called before anything else.
Then Creature_processDamage, Creature_run, Creature_updateActive, Creature_stepAnim at speed
2.0 in state 3, 1.5 while +0x3d8 != 0, else 1.0; Creature_applyKnockback(0.5); V23(0). If
+0x3d8 != 0 the quad +0x448 = (190, 0, 0, 0). If +0x3d0: 16 x (one own draw for a model sample
point, own draws in threes for a direction, particle_spawn(0, 0x8e4a60)).

States:
- 0: V25(0) -> 3; Creature_isAwayFromHome -> 1; clock > +0xf4 -> 1.   1: V25(0) -> 3 else
  Creature_moveToDest.   5: Creature_isNotRooted -> 3.
- 3, first form (+0x3c8 == 0): T(0,36,28000): if clock < +0xf4 -> 0x10 (bats, retreat) else ->
  0x17 (vanish and pounce). Otherwise, unless +0x478 == 7, T(0,240,0xdac) -> 7. Otherwise
  Creature_moveToTarget. No target -> 0.
- 3, second form: every frame, if clock > +0x3dc then +0x3d8 = (own draw & 3) + 4 (a draw per
  frame spent in state 3), else +0x3d8 = 0. T(0,36,28000) -> 0x11; T(0,48,7000) -> 10;
  T(0,120,0xdac) -> 0xb; else T(0,36,0x7fff) -> Creature_turnToTarget, else moveToTarget.
- 6: bit 0: Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags 8, no descriptor);
  flag 8 clear -> 3. No code in the class requests state 6.
- 7 lunge bite (first form): Creature_settle; turn to target. Bit 0: Creature_hitTargetInArc
  (0, 12, this, facing, 0x4000, +0xd0, +0xd2, +0xd4, flags 8, no descriptor); if T(0,12,0x4000)
  the latch +0x3d4 = 1. While latched the target is dragged in front: its knockback speed
  +0x2e8 = 15 x horizontal distance to (own position + facing x (both radii)), angle toward
  that point. Mask 2: latch cleared, then the same hit call with a descriptor holding one
  type-0x16 (cold) slot v1 = 2q, v2 = 2q + trunc(2q x 0.2 x d/65536), q = ColdWeapons (14)
  value query (+0x5c) with (0, (int) monster level, 0), d = one own draw. The target's hit
  points (creature targets only) are read before and after; if the integer difference is
  non-zero the lord's own hit points += 8% of his maximum, capped at the maximum. Flag 8
  clear: latched target's knockback speed zeroed, -> 3.
- 8 / 9 (second form): settle; bit 0: Creature_hitAllEnemiesInArc(0, 36, this, facing, 28000,
  +0xd0, +0xd2, +0xd4, flags 8, none); turn to target. During a flurry (+0x3d8 != 0), on mask 2
  the next attack starts at once: T(0,36,28000): own draw % 100 < 50 -> the other of 8/9, else
  10; else T(0,48,7000) -> 10; else T(0,120,0xdac) -> 0xb; else 3. Flag 8 clear -> 3.
- 10: settle; bit 0: Creature_hitTargetInArc(0, 48, …, arc 7000, flags 0x40008, none); flurry
  chain on mask 2: T(0,36,28000): own draw % 100 < 50 -> 8 else 9; T(0,48,7000) -> 10;
  T(0,120,0xdac) -> 0xb; else 3. Flag 8 clear -> 3.
- 0xb: settle; bit 0: Creature_hitTargetInArc(0, 36, …, arc 28000, flags 0x80008, none). When
  flag 8 clears: no flurry -> 3; flurry: same chooser as state 10.
- 0x10 bats and retreat (first form): bit 0 particle cloud on; mask 2: cloud off, bat form
  (0x2b9be8: +0x3cc = 1, bat_move animation, object flag 1 = not solid, creature flag 0x100000
  set), then six times: own draws in threes for an offset (radius 12, z + 24), pool_new(0x448)
  + Critter_ctor 0x2547fc(obj, name `bat`, position, facing + own draw, property list 0x502f78
  = {`oneshot=1`}). While clock < +0xf4 (setState: clock + 240) and a target exists:
  Creature_fleeFrom(this, target, 0). Otherwise leave bat form (0x2b9c54: fx_ringBurst(4),
  sound, object flags 1 and 2 cleared, creature flag 0x100000 cleared) and -> 3.
- 0x11 guard (second form): setState sets creature flag 0x200 (the "blocking" bit of
  damage_apply; every later setState call clears it) and +0xf4 = clock + 60 x +0x3d8. Run:
  quad +0x440 = (190, 0, 0, 30); turn to target; once clock > +0xf4: T(0,36,28000): own draw %
  100 < 50 -> 8 else 9; T(0,48,7000): own draw % 100 < 65 -> 10 else 9; else 3. No target -> 0.
- 0x12, 0x13: setState replaces both requests with the current state, so the lord has no hit
  reaction and never enters the stun state (run case 0x13 is an empty return).
- 0x14 death: setState: sound, Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, position,
  facing, `vampirefang`), animation entry 0x12, +0xf4 = clock + (own draw % 180) + 180, V28(0).
  Run: bit 0 cloud on; mask 2: +0x3c8 = 0, cloud off, bat form, six `bat` Critters as in 0x10.
  Then while clock < +0xf4 and a target exists Creature_fleeFrom; otherwise obj_delete(this).
  Creature_deadUpdate is never called: the body turns into a bat, flies off and is deleted.
- 0x17 vanish (first form): +0xf4 = clock + (own draw % 120) + 180. With a target: +0x3e0 x/y
  follow the position and +0x3e8 rises 6 per frame; bit 0: cloud on, object flags |= 5 (not
  solid + bit 4), +0x3e8 = z + 50.02; mask 2: cloud off, object flag 2 (not drawn) set; speed
  150, Creature_moveToTarget, speed 0. clock > +0xf4 -> 0x18.
- 0x18 pounce: +0xf4 = clock + (own draw % 120) + 300 (this later decides 0x10 versus 0x17 in
  state 3). With a target: +0x3e8 falls 7.929 per frame; mask 4: cloud on, +0x3e8 = z +
  210.28; mask 8: flag 2 cleared (visible); bit 0: cloud off, latch = 1, object flags 5
  cleared, hit as state 7 bit 0; mask 2: latch off, cold-rider hit and the 8% heal exactly as
  state 7. Unlatched: facing snapped to the target, speed 150, moveToTarget, speed 0. Latched:
  the same drag as state 7. When animation flag 0x20 clears: latched target's knockback speed
  zeroed, -> 3.
- 0x19 form change: +0xf4 = clock + 90, animation entry 0x12; bit 0 cloud on; when clock >
  +0xf4: cloud off; first form -> 0x2b9c54 (ring burst, sound, flags restored), +0x3c8 = 1,
  +0xe8 = 3; second form -> +0xe8 = 0, +0x3c8 = 0 (the code can toggle back, but takeDamage
  asks only once); rebuild +0x220; -> 3.
- 2, 4, 0xc-0xf, 0x15, 0x16: empty.

setState 0x2b944c: after the filter, creature flag 0x200 is cleared on every call. 0: +0xf4 =
clock + (own draw % 90) + 90. 6: +0xf4 = 20 (an absolute value, Observed). 7 / 0x10 / 0x17
store themselves in +0x478. 8, 9, 10, 0xb: if +0x3d8 == 1 the next flurry time +0x3dc = clock +
240 + 60 x (own draw % 3) (0xb: own draw & 3); then +0x3d8 is decremented if non-zero. Tail:
if in bat form and the new state is neither 0x10 nor 0x14, 0x2b9c54 is called (bat form ends).

takeDamage 0x2b93d8: Creature_takeDamage; then if hit points < 0.5 x maximum and +0x3ec == 0:
V27(0x19) and +0x3ec = 1. The request goes through Creature_filterState (0x10a9c0), which
turns it into 5/0 while rooted, 0x13 while stunned (which this class maps to "keep current
state") or 0x10 while the attack cooldown +0x318 runs; +0x3ec is set regardless, so in those
cases the second form is never entered (Inferred from the two functions; not seen in play).

Phases: first form (lunge bite 7, bats 0x10, vanish/pounce 0x17-0x18); second form from the
first hit that leaves him under 50% (state 0x19: +0x3c8 = 1, model parts 0 and 1 hidden, an
extra mesh classDef+0xac/+0xb4 drawn): melee flurries 8/9/10/0xb with the guard 0x11.
Only the two bites (7 and 0x18, second event) carry the cold rider and the heal; 8-0xb have no
descriptor.

What is spawned: `Critter` (0x448 bytes, vtable 0x510ca0) named `bat` with `oneshot=1`: its
constructor (read 0x2547fc) calls Creature_ctor with no type name and max hp (draw % 14) + 4,
sets object flag 8 (the "dead" bit), kind 0x12, and with `oneshot`
starts in Critter state 0x17; Critter_run states 0x17/0x18 (read) wait for a player inside its
radius or a timer, then move with the animation and obj_delete themselves when inactive. No
damage call in what was read (rest of Critter not read).

Script-driven: property `wings` only. No script in scripts/*.txt names the class.

Per-machine:
(a) run/setState/takeDamage/helpers: no camera, local-slot, audio, timer or cosmetic-seed read
in the class code (scan and reading). Effects called from run: fx_modelStatusEffects (0x1f6ac8;
given the block +0x3f0, which nothing else in the class reads) and fx_ringBurst (0x1f3d00);
both are outside the area and were not read - their symbol notes say cosmetic seed. All
choices in the class use the own generator.
(b) draw 0x2b7af0 stores nothing in the object. (c) draw: V38/V16 (res_find lookups while in
bat form), Creature_draw, and in the second form light_addObjectAmbient(+0x448) plus the
extra mesh; no creation, generator, run-list, script or world call.
Open: who reads +0x3e0 (the clone 0x128ee0 copies it; no other use found in the class);
take-damage meaning of flags 0x40000 / 0x80000 beyond the knockback table; destructor not
read.

#### RedDragon  (factory `RedDragon`; vtable 0x514c88; size 0x418)

Functions: ctor 0x25f470, run 0x25f988, draw 0x25f93c, takeDamage 0x260d58 (only forwards to
Creature_takeDamage), trigger (slot 3) 0x260d50 = empty, setState 0x260d74, breath effect
0x261328. Unique slot 1 (0x3ca86c) not read. 0x25f3fc lies in the range but is a Demon helper
(callers 0x25e448 and 0x25eb0c inside Demon_run): returns 1 when the target's exact class is
`Soul`.

Constructor 0x25f470: Creature_ctor(max hp argument 10, …, class def 0x4ffd38, props). Radius
72, turn rate 1.2, move speed +0xb8 = 0 (root-motion movement, Inferred), kind +0xb4 = 5,
+0x28 = 100, +0xe0 = -48, creature flags |= 0x200040000, resistances fire +0x5c = 1.0, poison
+0x64 = 0.5, disease +0x68 = 0.5, lightning +0x6c = 0.5, +0xf4 = g_simFrame + 300 (never read
by this class). A light record is embedded at +0x3dc (position +0x40c, colours +0x3e6..+0x3f4,
radii +0x3f8..+0x404, +0x408 = 0.6); it is linked and unlinked again inside the constructor.
RedDragon_setState(0); obj_runEvery60. No property read by the class.
Event tables (entry: time->mask): 3 (+0x1c, state 0x1c) 0.2->1; 4 (+0x24, state 0x1d) 0.2->1;
5 (+0x2c, state 6) 0.3->1; 6 (+0x34, state 7) 0.3->1; 7 (+0x3c, state 8) 0.3->1; 9 (+0x4c,
state 0xb) and 10 (+0x54, state 0xd): 0.1->1, 0.5->2, 1.7->1, 1.9->2; 0xb (+0x5c, state 0xc)
and 0xc (+0x64, state 0xe): 0.3->1, 0.7->2, 1.7->1, 1.9->2; 0x12 (+0x94, state 0xf): 1.0->1,
1.5->1, 1.7->2; 0x14 (+0xa4, state 9) and 0x15 (+0xac, state 10): 0.4->1; 0x13 (+0x9c, walk):
0.126->8, 0.152->1, 0.44->4, 0.445->2.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | last attack state entered (6-0xf, 0x1a, 0x1c, 0x1d); steers the choosers | run 5, 0x1b |
| +0x3cc | s32 | turn states 0x17/0x18: 1 once the target has been inside the 2000 arc (stops turning) | run |
| +0x3d4 | s32 | flame particles on (toggled by bit-0 events) | run 0xb-0xf |
| +0x3d8 | s32 | ground impact + damage window on (toggled by mask-2 events) | run 0xb-0xe |
| +0x3dc | light | breath impact light | 0x261328, run |
The first-pass table gave size 0x418; fields up to +0x414 are used.

Run 0x25f988: Creature_processDamage, Creature_run, Creature_updateActive (0 -> return),
events = Creature_stepAnim(1.0), Creature_applyKnockback(0), V23(0), switch. C(...) =
Creature_canSeeTargetIn(min, max, lead, this, facing, arc, 0); E(min,max,facing,arc) =
creature_findEnemyInCone (any enemy, nearest wins, needs a clear terrain ray).
- 0: target -> 3; else Creature_isAwayFromHome -> 1.   1: target -> 3; else moveToDest.
- 2, 4, 0x11, 0x15, 0x16 and unknown values -> 0.
- 3 chase: no target -> 0. C(0,300,0, facing-0x7fff, 0x4000) (target behind) -> 5. Else if the
  target is not charging (Creature_isTargetCharging) and C(0,84,0.3,facing,12000) -> 5. Else
  C(0,36,0.3,facing,12000) -> 5. Else Creature_moveToDirect(target position) (no path finder).
- 5 attack chooser, in order (L = +0x3c8):
  1. E(0,144, facing+0x6c79, 5000) -> 9; E(0,144, facing-0x6c77, 5000) -> 10 (tail, either side).
  2. C(0,84,0.5,facing,4000) (target in front): L == 6 -> 0x1b; L == 0xb -> 0x1c; L == 0x1c ->
     0x1d; otherwise -> 6. (When 0x1b then picks the close breath 0xb the front sequence
     is 6, 0x1b, 0xb, 0x1c, 0x1d, 6, …; after any other breath it returns to 6.)
  3. L not 7 or 8 and C(0,84,0.2,facing,12000): Creature_angleToTarget < 0 -> 8 else 7.
  4. L != 0xf and E(84,264,facing,4000) -> 0x1b.
  5. L not in {0xc, 0xe, 0xf}: E(84,264,facing+6000,6000) -> 0x1b; then E(84,264,facing-6000,
     6000) -> 0x1b.
  6. Rooted: angle < 0 -> 0x18 else 0x17. Not rooted: if the target is neither behind
     (C(0,300,0,facing-0x7fff,0x4000)) nor C(0,84,0,facing,12000) -> 3; otherwise 0x18 / 0x17 by
     the sign of the angle.
- 6, 7, 8, 0x1c, 0x1d melee: Creature_settle; on bit 0 with a target, Creature_hitTargetInArc
  (0, 84, this, F, A, +0xd0, +0xd2, +0xd4, flags, no descriptor): 6: F = facing, A = 4000,
  flags 0x40008, then Creature_knockbackTarget(200) (sets the target's knockback speed 200,
  direction away, whether or not the hit landed); 0x1c: facing, 4000, 0x40008; 0x1d: facing,
  4000, 0x80008; 7: facing + 6000, 6000, 0x80008; 8: facing - 6000, 6000, 0x80008. Flag 8
  clear -> 5.
- 9 / 10 tail: zero Creature_moveBy; bit 0 with a target: Creature_hitAllEnemiesInArc(0, 144,
  this, facing + 0x6c79 (9) or facing - 0x6c77 (10), 8000, +0xd0, +0xd2, +0xd4, 0x80008,
  none). Flag 8 clear -> 5.
- 0xb-0xe breath: mouth = attach point 0 moved by facing x +0xe0 and z - 12. Bit 0 toggles
  +0x3d4, mask 2 toggles +0x3d8 (by the tables: flame on 0.1/0.3 to 1.7, damage window
  0.5/0.7 to 1.9). 0x261328(this, mouth, direction, +0x3d4, +0x3d8, -1 in state 0xb else 0)
  every frame. While +0x3d8 is set, on every frame with creature clock % 15 == 0:
  Creature_hitAllEnemiesInArc(min, max, this, F, A, +0xd0 / 4, +0xd2 / 4, +0xd4, flags 0,
  descriptor) with one fire slot (type 0x15, v1 = +0xd0 / 4, v2 = +0xd2 / 4) (descriptor
  pointer checked in the disassembly: register t3 = sp+0x60 at 0x260380). Areas: 0xb: 0-84,
  facing, arc 4000; 0xd: 84-264, facing, 4000; 0xc: 84-264, facing + 6000, 6000; 0xe: 84-264,
  facing - 6000, 6000. The damage cone is fixed by the state, not by where the particles go.
  Flag 8 clear -> 5 and light_unlink(+0x3dc).
- 0xf fire storm: bit 0 toggles +0x3d4; while set 0x261328(this, mouth + facing x 12,
  direction, 1, 0, +1) (flame only, forced upward). On mask 2: i = players_findFarthestWithin
  (own position, 600) (0x119d60: farthest living player within 600, 2-D); p = player table
  0x4dcec8[i]; if p: pool_new(0xb4) + FireStorm_ctor2 0x2d4048(0.501, obj, owner = this,
  position of p, 0x82, +0xd0, 0xb4, 5) (stored by that constructor at +0xa4, +0x9c, +0x8c,
  +0x94, +0xa8; the skill table is not used). The helper returns -1 when nobody qualifies
  (sign-extended byte, 0x119e28) and the caller does not test for it: it multiplies by 0x4c30
  and reads the word at 0x4dcec8 - 0x4c30 = 0x4d8298 as if it were a player pointer
  (0x260888-0x260898) - Observed missing check; what is stored there is Unknown. Animation
  flag 0x10 clear -> 3.
- 0x10: Creature_isAttackReady -> 0 else Creature_fleeFromTarget (setState 0x10 sets the
  cooldown +0x318 = 60).   0x12, 0x19: zero moveBy until flag 0x10 clears -> 3.   0x13:
  Creature_isNotStunned -> 3.   0x14: Creature_deadUpdate(40, this, events, zero, 0) + zero
  moveBy.   0x1a: creature_moveSimple(zero) only; no exit in run.
- 0x17 / 0x18 turn left / right: until the target is inside C(0,5000,0,facing,2000) (or there
  is no target) the facing is stepped by 0x10bca8 / 0x10bdb0 (angular velocity +0x110 +/-
  0x199 per frame, damped, limited by the turn rate); after that +0x3cc = 1 and it only waits.
  Animation flag 0x20 clear -> 5.
- 0x1b breath choice (after its animation, entry 0xf, ends): E(0,84,facing,4000) -> 0xb;
  E(84,264,facing,4000) -> 0xd; else with L = +0x3c8: L == 0xe -> 0xf; L not 0xc/0xf and
  E(84,264,facing+6000,6000) -> 0xc; L not 0xc/0xe/0xf and E(84,264,facing-6000,6000) -> 0xe;
  otherwise 0xf.
After the switch, in state 3 only: event masks 1, 2, 4, 8 each fx_spawn(0x15) at attach
points 2, 3, 4, 5 (footfalls).

Breath effect 0x261328(this, mouth, dir, flameOn, impactOn, mode): flameOn: 20 particles (def
0x8e34b8), each from two own-generator unit-sphere samples (three draws per try), velocity =
dir x 101.5 + sample x 40, vertical part forced >= 0 (mode > 0) or <= 0 (mode < 0). impactOn:
steps 12 units along dir (up to 60 steps) until below terrain_height, then 16 + 5 ground
particles (two own draws each), and the light at +0x3dc is placed there with a radius that
flickers with g_simFrame, light_link + light_link2. No damage, no object creation.

setState 0x260d74: 0: +0xf4 = clock + own draw % 120; 5: +0xf4 = clock + own draw % 120 + 60
(two draws that feed a field the class never reads). 6-0xf, 0x1a, 0x1c, 0x1d store themselves
in +0x3c8; 0xb-0xf clear +0x3d4 and +0x3d8; 0x17/0x18 clear +0x3cc. 0x12 is refused (state
kept) while the current state is 6..0xf. 0x14: Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25,
this, position + facing x 84, facing, no item name), death animation, V28(0), object flag 1
cleared (solid corpse). No code in the class requests 0x19 or 0x1a.

Phases: none (takeDamage is the base one; no hit-point test anywhere in the class).

Script-driven: scripts/FIRE5.txt `setminiboss` (run after the `dragon` cut scene / checkpoint)
does setCFlag('reddragon', 0, 1) and setMonsterVal('reddragon', 1 / 4 / 5, 4000)
(pointblankrange, HomeRange through slot 34, activity radius). The class reads no property.

Per-machine:
(a) none found in run / setState / takeDamage / 0x261328 (scan and reading): the four
fx_spawn(0x15) calls and the light are effects; players_findFarthestWithin walks the global
player table (all players, not local ones); all draws are own-generator draws made in run.
One unclassified read: the index -1 case of state 0xf (word 0x4d8298, 0x858 bytes below
g_players 0x4d8af0); whether that word is the same on every machine was not determined.
(b) draw 0x25f93c: global 0x41c14c = 5.0, Creature_draw, model_resetDrawState; no store into
the object. (c) none.
Open: what lies at 0x4d8298 (the index -1 slot); which state values a script or the base
class may request for 0x19/0x1a; time unit of the event tables.

#### Nightmare  (factory `Nightmare`; also built by Horsemen_ctor at 0x27217c; vtable 0x5155e8; size 0x3d8)

Functions: ctor 0x270968, run 0x270bbc, draw 0x270b4c, hit terrain (slot 10) 0x27142c, touched
list (slot 11) 0x271484, setState 0x27155c, Horsemen_mountSeatTransform 0x2719d4 (model
attach point 10 of the mount at position + facing x +0xe0, via 0x175330; called by the
rider). takeDamage is the base one. Unique slot 1 (0x3cae50) not read. Callee just outside
the range: 0x271a6c (charge-target picker, read).

Constructor 0x270968: Creature_ctor(max hp argument 10, …, class def 0x500680, props). Radius
30, turn rate 0.6, move speed 0 (root motion), +0x28 = 50, kind +0xb4 = 10, fire resistance
+0x5c = 1.0, +0xe0 = -20, scale +0xdc = 1.2, HomeRange +0x3c0 = 2400, visualrange +0x3ae =
2400, creature flags |= 0x20200040000, +0x3c8 = 0, +0x3cc = 0, +0xf4 = 0. Nightmare_setState
(0); obj_runEvery60. No property read. Event tables: entries 4 (+0x24) and 8 (+0x44): 0.5->1,
0.8->2, 1.2->2, 1.5->4 (only entry 8 is started by this class).
Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | handle | rider (a Horsemen); linked both ways by Horsemen_ctor 0x271c70 (lines at 0x27217c on) | setState, run 8 |
| +0x3cc | s16 | fade counter: counts up 0..100 while "dead", down from 120 after a reappear; draw passes it to 0x1797b8 (global byte 0x41c149) and skips the model at >= 98 | run 0x14, 0x1a; draw |
| +0x3d0 | s32 | clock until which the mount stays non-solid after trampling a player | run head, slot 11 |
| +0x3d4 | s32 | "keep turning to the target" latch of the kick states | run |
| +0xf4 | s32 | wander / hidden timer | run 1 |

Run 0x270bbc: Creature_processDamage, Creature_run, Creature_updateActive, Creature_stepAnim
(0.9 in state 7 while animation flag 0x20 is set, else 1.0), Creature_applyKnockback(0.2),
V23(0). If the state is not 0x14 and clock > +0x3d0: object flag 1 cleared (solid again).
- 0: V25(0) -> 3; Creature_isAwayFromHome -> 1.   1: V25(0) -> 3; clock <= +0xf4 ->
  Creature_moveToDest, else -> 0.
- 3 chase: no target -> 0. creature_findEnemyInCone(0,36,this,facing,4000) -> 5.
  Creature_canSeeTargetIn(0,36,…,arc 0x7fff) -> 5. Else, if 0x271a6c(this) and
  creature_findEnemyInCone(0,240,this,facing,2000) -> 7 (charge). Else: target not within 120
  (any direction) -> Creature_moveToTarget; within 120 and inside arc 6000 -> moveToTarget;
  within 120 but outside arc 6000 -> 0x17.
  0x271a6c: for each living player in slot order, eight terrain_raycast(480) probes of 360
  units (45-degree steps, from the player's position z+24); the first player with no terrain
  hit in any direction becomes the TARGET (+0x234 relinked) and the function returns 1. So
  the charge is only started when some player stands in open ground, and it retargets to the
  first such player.
- 5: no target -> 0. findEnemyInCone(0,36,facing,4000) -> 6. Target within 36 (any direction):
  |angle to target| < 4000 -> 6; |angle + 0x4000| < 6000 -> 8; |angle + 20000| < 6000 -> 0x18;
  else 0x17. Target farther: within 120 but outside arc 6000 -> 0x17; else
  Creature_isNotRooted -> 3.
- 6 / 0x17 / 0x18 kicks (all three start animation entry 8): Creature_settle. On masks 1 or
  2: Creature_hitAllEnemiesInArc(0, 42, this, facing, 0x1194, 2 x +0xd0, 2 x +0xd2, +0xd4,
  flags 1, no descriptor); on mask 4: the same with flags 0x100041. Bit 0 sets the latch
  +0x3d4, mask 4 clears it; while latched Creature_turnToTarget. Flag 8 clear -> 3. The three
  states differ only in the state they push onto the rider (below).
- 7 charge: turn to target during the wind-up (animation flag 0x20) and afterwards only while
  Creature_canSeeTargetIn(0,2400,…,arc 6000); zero Creature_moveBy (root motion). While
  running (flag 8 set, 0x10 clear): terrain_raycast(480, from position z+24, facing x 360);
  a hit in (0,1) starts the braking animation (entry 6, flag 0x810). Flags 8 and 0x10 both
  clear -> 3. Damage comes through the two overrides:
  slot 11 0x271484 (list of objects touched by the move, state 7 only): for every Player
  (object flag 0x40) not in a knock-down animation (0x10d390): damage_apply(2 x +0xd0, 2 x
  +0xd2, victim, this, rating 100000 = always hits, flags 0x100041, no descriptor), then the
  mount sets its own object flag 1 (not solid) and +0x3d0 = clock + 120.
  slot 10 0x27142c (hit terrain): in state 7 -> setState(3).
- 8: no rider -> 0; otherwise wait until the RIDER's animation flag 8 clears -> 5 (the rider's
  own attack; see setState).
- 0x10: Creature_isAttackReady -> 3 else Creature_fleeFromTarget.   0x13: not stunned -> 0.
- 0x14: every frame the position is advanced directly by facing x 11.667 (no collision test),
  obj_updateGridCell, +0x3cc += 1, Creature_deadUpdate(30, this, events, zero, 1); at +0x3cc >
  99: object flags |= 0x4002 and obj_delete. The dead mount gallops away and fades.
- 0x19: nothing in run (setState hid it). 0x1a: +0x3cc counts down to 0, then -> 0.
- 2, 4, 9-0xf, 0x11, 0x12, 0x15, 0x16: empty.

setState 0x27155c (after the filter). Every case also sets a state on the rider through the
rider's slot 27 when +0x3c8 is linked: 0, 5, 0x13 -> rider 0x1b; 1, 3 -> 0x1c; 7, 0x10 ->
0x1d; 6, 0x17 -> 0x1e; 0x18 -> 0x1f; 8 -> 0x20 + (own draw % 3); 0x19 -> 0x19; 0x1a -> 0x1a;
0x14 -> 0x23, then the rider handle is dropped. 0: +0xf4 = clock + own draw % 120. 1: +0xf4 =
clock + own draw % 120 + 300. 0x10: cooldown +0x318 = 60. 0x12: the request is replaced by the
current state (no hit reaction) and the rider is sent 0x1b. 0x14: object flag 0x4000, V28(0),
animation entry 5 (no Creature_dropLoot call). 0x19: object flags |= 0xb (not solid, not
drawn, dead bit), +0xf4 = clock + 300. 0x1a: those flags cleared, +0x3cc = 120. 8 without a
rider does nothing but store the state. Nothing in this class requests 0x19 / 0x1a (Inferred:
the rider or a script).

Phases: none. Script-driven: none found (no script names the class; it is built by the
factory, call at 0x15b1e4, and directly by Horsemen_ctor, call at 0x27217c).
Per-machine: (a) none found (scan and reading): the charge-target picker walks the global
player table and the terrain; draws are own-generator. (b) draw 0x270b4c writes only the
global byte 0x41c149 (fade) and calls Creature_draw / model_resetDrawState; no store into the
object. (c) none.
Open: which caller requests 0x19 / 0x1a; rider-side meaning of 0x19-0x23 (Horsemen, not
re-read); slot 1.

#### Hag  (factory: any type name with the prefix `Hag`, test at 0x15ad9c; vtable 0x5154a0; size 0x3d8)

Functions: ctor 0x26f120, run 0x26f504, draw 0x26f494, setState 0x270264, get model (slot 16)
0x27090c, second model (slot 38) 0x27092c, form tests 0x27094c (animation flag 0x20 in
+0x11a) and 0x27095c (animation flag 0x8000), both called only from Hag_run / Hag_setState.
takeDamage is the base one. Unique slot 1 (0x3cada0) not read.

Constructor 0x26f120: Creature_ctor(max hp argument 10, …, class def 0x5005a8, props). Radius
18, turn rate 1.2, move speed 0 (root motion), kind +0xb4 = 0x10, creature flags |=
0x200010000, resistances poison +0x64 = 0.5, disease +0x68 = 0.4, lightning +0x6c = 1.0, +0xf4
= g_simFrame + 300, +0x3cc = 1 (never read in the class), +0x3d0 = 0. +0x3c8 (u8) = 1 when the
type name equals `hagred` (case-insensitive), else 0: slots 16 / 38 then return the class
definition's model/texture at +0x1c / +0x24 instead of +0xc / +0x14. Hidden-part mask +0xe8 =
1 << (own draw % 9) (one own draw; the look variant), +0x220 rebuilt. Hag_setState(0);
obj_runEvery60. No property read.
Event tables (entry: time->mask): 6 (+0x34, melee) 0.2->1; 0x10 (+0x84, grown melee) 0.2->1;
0xc (+0x64, state 7) 0.1->1; 0xb (+0x5c, state 8) 0.4->1; 0x15 (+0xac, state 9) and 0x18
(+0xc4, state 10): 0.3->1, 1.2->2; 7, 8, 9 (+0x3c/+0x44/+0x4c, the three death animations):
0.2->0x80.
Fields: +0x3c8 u8 variant (above); +0x3d0 s32 clock before which no Shock / LightningStrike
is started (set to clock + 300 by every cast); +0xf4 s32 state timer (7: 180 frames, 0x11:
120 frames); scale +0xdc is animated by the grown form.
Two forms are carried by animation-track mode bits, not by fields (Observed: the run head and
every setState case test them through 0x27094c / 0x27095c):
- F (flag 0x20, set by the tracks started in state 0x17, dropped by the one in 0x18): while
  set the run head ORs creature flags 0x100050 every frame (0x10 / 0x40 immune to damage
  classes 8 and 1, 0x100000 "absolute"), and clears them when it is not set.
- G (flag 0x8000, tracks started in state 0x19; state 0x1a starts a plain loop): while set
  the scale +0xdc grows 0.01 per frame up to 1.4; when clear it shrinks 0.01 per frame to 1.0.

Run 0x26f504: Creature_processDamage / Creature_run with the slot-16 model,
Creature_updateActive (0 -> return), Creature_stepAnim(1.0), Creature_applyKnockback(1.0),
V23(0), scale step, immunity flags, switch. C(max, arc) = Creature_canSeeTargetIn(0, max, 0,
this, facing, arc, 0). R = 12 x ConeOfShock (101) value query (skill offset +0x5c) called with
(1, V35(), 0x19); "cone free" = no SpellConeOfShock attached (creature_findSpellByType).
- 0: V25(0) -> 3; Creature_isAwayFromHome -> 1.   1: V25(0) -> 3; else Creature_moveToDest.
- 3: no target -> 0. F and C(400,4000) -> 0x18. C(24,4000) -> 5. Not G and C(400,4000) -> 5.
  Then: (G or not C(400,0x7fff)) and not C(24,0x7fff) -> Creature_moveToTarget; otherwise
  Creature_turnToTarget.
- 5, target not in C(24,4000): (a) not F, not G, cone free and C(R,4000) -> 7. (b) not F, not
  G and C(400,4000): wait while clock <= +0x3d0; then own draw & 1: 0 -> 10, 1 -> 8. (c)
  otherwise, if not rooted: own draw % 50 == 0 -> 3; else G -> 3, not G ->
  Creature_turnToTarget.
- 5, target in C(24,4000): F -> 0x18. Otherwise, each step only if not G and the previous one
  did not fire, one own draw each: draw % 3 == 0 -> 0x19 (grow); draw % 3 == 0 -> 0x17 (form
  F); Creature_isTargetAttackingMe and draw % 3 == 0 -> 0x11 (guard); draw % 3 == 0 and cone
  free and C(R,4000) -> 7. Fallback -> 6.
- 6 melee: Creature_settle, turn to target; bit 0: Creature_hitTargetInArc(0, 24, this,
  facing, 4000, +0xd0, +0xd2, +0xd4, flags 8, or 0x80008 when G, no descriptor). Flag 8
  clear: Creature_isTargetKnockedDown -> 0x10; else G and (own draw & 3) == 0 -> 0x1a; else 5.
- 7 cone: settle, turn; on bit 0 (the animation loops, so about every cycle) if cone free:
  spell = ConeOfShock cast (skill offset +0x14)(V35(), this, position with z + half height,
  facing); creature_addSpell(this, spell); +0x3d0 = clock + 300. clock > +0xf4 (180 frames
  after entry) -> 5. Every setState call removes the attached SpellConeOfShock
  (creature_removeSpellByType 0x11a6d0), so the cone lives only while the state lasts.
- 8 Shock: settle, turn; bit 0: Shock (37) cast (+0x14)(V35(), this, position z + half
  height, facing), result not attached; +0x3d0 = clock + 300. Flag 8 clear -> 5.
- 10 LightningStrike: bit 0: pool_new(0x60) + LightningBolt_ctor 0x295360(obj, own position z
  + half height, 60 frames, no light) (a visual bolt 240 units straight up from the hag). Mask
  2 with a target: +0x3d0 = clock + 300; LightningStrike (100) cast (+0x14)(V35(), this,
  TARGET position at that frame, facing). Flag 8 clear -> 5.
- 9: animation only (entry 0x15); empty in run and nothing requests it.
- 0x10: Creature_isAttackReady: no -> Creature_fleeFromTarget; yes -> F: 0x18; G: 0x1a; else
  0. (setState 0x10 sets the cooldown +0x318 = 120.)
- 0x11 guard: setState sets creature flag 0x200 (blocking; cleared by the next setState) and
  +0xf4 = clock + 120; run waits for it -> 5.
- 0x12: flag 0x10 clear -> 5 (setState starts no hit animation in form F).   0x13: not
  stunned -> 3.   0x14: Creature_deadUpdate(20, this, events, zero, 0).
- 0x17 (enter F): flag 8 clear: C(24,0x7fff) -> 0x10 else 3.   0x18 (leave F): flag 0x20
  clear -> 5.   0x19 (enter G): flag 8 clear -> 5.   0x1a (leave G): once flag 0x8000 is
  clear and scale <= 1.01 -> 0.
- 2, 4, 0xb-0xf, 0x15, 0x16 and unknown values -> 0.

setState 0x270264: after the filter, clears creature flag 0x200 and removes SpellConeOfShock.
Locomotion / idle cases pick one of three animations by form (F, G, neither). 6: G and own
draw & 1 -> the grown swing (entry 0x10) else entry 6. 7: +0xf4 = clock + 180. 0x14:
Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, position, facing, no item name), death
animation entry 7 + (own draw % 3) (after a landing animation when in form F), V28(0).

Phases: no hit-point threshold. The forms are chosen by own-generator rolls in state 5 when
the target is in melee range.
Skill use summary: ConeOfShock (101): +0x5c range query and +0x14 cast, attached to the hag;
Shock (37): +0x14 cast from the hag; LightningStrike (100): +0x14 cast at the target's
position. All three get V35() as level. No "can use" (+0x0c) call.
Script-driven: none (no property read; no script names a Hag).
Per-machine: (a) none found in run / setState (scan and reading); all rolls are own-generator.
(b) draw 0x26f494 = Creature_draw(slot 16 model, slot 38 texture); no store. (c) none.
Open: which `Hag…` names the level files actually use besides `hagred`; what +0x3cc is
for; skill-side meaning of the +0x5c arguments (1, level, 0x19); slot 1.

### IronGuardian, CloudGiant, Demon, SeaMonster, LavaMonster, Minion, GnawSpawn

*Reader's notes for this group.* Method for every class below: each function in the range was read in full in the Ghidra
decompile, doubtful spots were settled in the disassembly (`tools/dis.py`), the
class-definition name tables were dumped from the executable to tie animation slots to file
names, the scan was run on run / setState / takeDamage / draw. Unmarked statements are
Observed at the address given. "clock" = creature clock +0x300; "events" = the bit mask
returned by `Creature_stepAnim`; "own generator" = `GameObject_rand(this)`.

Shared facts used below (outside this group's ranges, read to interpret the classes):
- `Creature_ctor` 0x109d68 itself calls `Creature_setStats` (0x10a1a8–0x10a200): with the five
  factors returned by the type-name lookup 0x223a4c when the name is found, else (1,1,1,1,1).
  The float handed to `Creature_ctor` is therefore only a placeholder for hit points.
- `creature_bossRank` 0x10d940 returns 2 by type name for (among others) `IronGuardian`,
  `CloudGiantKing`, `Minion`. `Creature_setStats` 0x10a620: rank 2 gets no per-player damage
  factor; a creature whose type name is `droid` gets none either (string test at 0x10a730).
- `g_alivePlayerCount` 0x4f8420 is the count of ALL alive players (filled for every slot by
  `game_rebuildAlivePlayers` 0x1e72f8); the local-only count is the different word 0x4f8424.

---

#### IronGuardian  (factory name `IronGuardian`, call at 0x15ae54; vtable 0x515c60; size 0x3e8)

Functions: ctor 0x27a00c, run 0x27a390, draw 0x27a30c, setState 0x27b550. Outside the range:
destructor 0x3cb414 (clears the four handles +0x3d8..+0x3e4), slot 36 0x3cb50c (returns the
constant 11). takeDamage, save/load, slots 20-26 are the creature base versions (vtab.py).

Constructor (0x27a00c): `Creature_ctor(10, this, name, pos, angle, classDef 0x500960, props)`;
radius +0x1c = 35; draw half-width +0x28 = 0x48; turn rate +0xb0 = 0.3; +0xb4 = 4; speed +0xb8 = 0;
+0x5c/+0x64/+0x68 = 1, +0x6c = 0.75; HomeRange +0x3c0 = 3000; activity radius +0x3c4 = 3000;
cflags |= 0x22000020000; +0xec = g_simFrame, +0xf4 = g_simFrame + 300; +0x3cc = 0, +0x3d4 = 0,
four handles +0x3d8.. = 0. +0x3c8 and +0x3d0 are not written by the constructor; they start
at 0 because `pool_new` (0x14fdb8) zero-fills every block. State 0 via
IronGuardian_setState; `obj_runEvery60`; seven `creature_setDefEntryParams` calls (entries
3,4,5,6,0xd,7,8); `Creature_init`; `lump_load("droid.lmp")`. No property is read here; no
Creature_setStats / scaleStats call of its own.

Class-definition entries (0x500960, entry i handle at classDef + 4 + 8*i): 3 attack_01, 4
attack_02, 5 attack_03, 6 attack_04, 7 catapault, 8 death, 9 hit_reaction_01, 10
hit_reaction_02, 11 idle_01, 12 idle_02, 13 shoot, 14 walk; entries 15..34 are ten
(junk_NN model, junk_NN texture) pairs used by JunkProjectile.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | state 9 "firing" toggle; cleared by setState 9 and 10; set to 1 after the state-10 burst (0x27b0ac) | 0x27a860–0x27a86c (state 9) |
| +0x3cc | s32 | two uses: in state 0 a count of frames the target was visible (leave at > 120); in states 3/5 a clock value — the junk burst (state 10) is allowed only when +0x3cc < clock; set to clock + 600 after a burst | run cases 0, 3, 5, 10 |
| +0x3d0 | s32 | earliest time of the next Droid; compared with `g_simFrame` (0x27b1c0) but written as clock + 480 (0x27b4e0) | tail of run |
| +0x3d4 | s32 | Droids created so far; no more after 50 | tail of run |
| +0x3d8..+0x3e4 | handle[4] | the Droids this guardian made that still exist | tail of run, destructor |

States (run 0x27a390; head: processDamage, Creature_run, updateActive (0 → return),
stepAnim(1.0), applyKnockback(0), V23(0)):
- 0: V25(0) (can see target) false → if `Creature_isAwayFromHome` → 1, else stay. True →
  +0x3cc += 1 and when it exceeds 120 → 3. (The counter is never reset on losing sight.)
- 1: V25(0) true → 0; else `Creature_moveToDest`.
- 3: no target handle → 0. `creature_findEnemyInCone(84, 400, facing, arc 2000)` → 9. Else, if
  +0x3cc < clock and findEnemyInCone(240, 400, facing, arc 10000) → 10. Else
  findEnemyInCone(0, 84, facing, arc 0x7fff) → 5. Else `Creature_moveToTarget`.
- 5: tests in this order, all `creature_findEnemyInCone`: (0, 84, facing, 10000) → 6;
  (0, 84, facing + 0x4000, 0x4000) → 7; (0, 84, facing − 0x4000, 0x4000) → 8;
  (84, 400, facing, 2000) → 9; +0x3cc < clock and (240, 400, facing, 10000) → 10; otherwise →
  3 when `Creature_isNotRooted`, else stay.
- 6 (attack_01 or attack_02, chosen in setState by own generator & 1): on events bit 0
  `Creature_hitAllEnemiesInArc(0, 84, this, facing, 10000, +0xd0, +0xd2, +0xd4, flags 8, 0)`.
  → 5 when animation flag 8 (+0x11a) has cleared.
- 7 (attack_03) / 8 (attack_04): while `g_alivePlayerCount` (0x4f8420) == 1 it calls
  `Creature_turnToTarget` every frame (0x27a750, 0x27a7d0); on events bit 0
  hitAllEnemiesInArc(0, 84, facing + 0x4000 for state 7 / facing − 0x4000 for state 8, arc
  0x4000, +0xd0, +0xd2, +0xd4, flags 0x80008, 0). → 5 when animation flag 8 clears.
- 9 (shoot): `Creature_turnToTarget` every frame. Each events bit 0 flips +0x3c8. While
  +0x3c8 != 0 and clock % 6 == 0: one missile. Position and direction from
  `model_getAttachPoint(scale +0xdc, model, pos, facing, anim, index 1, &pos, &dir)` (the
  buffers are preloaded with pos + facing×48 + z 86 and facing×70, z −12); velocity = −dir
  normalised × 400, z − 2, plus a random point in the unit ball × 20 (own generator, three
  draws per rejection round). One more own-generator draw (& 3) picks one of four sounds.
  `pool_new(0x1c8)` + `MissileWeapon_ctor`(obj, kind 0, two words from the static block
  0x3e9ce0 (+8, +0xc), pos, velocity, atan2(vy, vx) − 0x4000, owner this; stack arguments
  read in the disassembly 0x27ab84–0x27ac08: 0, 0, (s16 +0xd0)/2, (s16 +0xd2)/2, 0, 0, +0xd4,
  4, descriptor 0) — they land in missile +0xd4 / +0xd8 (the two halved damage values),
  +0xe4 (+0xd4 of the guardian) and +0xe8 (4). MissileWeapon's use of them was not read here.
  → 5 when animation flag 8 clears.
- 10 (catapault): `Creature_settle`, `Creature_turnToTarget`. On events bit 0: ten
  JunkProjectile objects (`pool_new(0x74)` + ctor 0x27c2c8) with model index 15, 17, … 33,
  scale 1.0, all starting at `model_getAttachPoint(1.0, model, pos, facing, anim, index 2)`,
  facing = the guardian's. Velocity of each: facing × 400 horizontally, z = (60 + own
  generator % 40) × 300 × 0.0025 (the 300 is the length of a facing × 300 offset computed in
  place), plus a random unit-ball point × 140 (own generator, three draws per rejection
  round). One extra own-generator draw is made before the loop for a value that is not used
  (0x27ae80, result overwritten by the first loop pass). Then +0x3c8 = 1, +0x3cc = clock +
  600 (0x27b0ac, 0x27b0b4). → 3 when animation flag 8 clears.
- 0x10: `Creature_isAttackReady` → 0, else `Creature_fleeFromTarget(this, 0)`.
- 0x12: wait for animation flag 0x10 to clear → 5. 0x13: `Creature_isNotStunned` → 5.
- 0x14: `Creature_deadUpdate(30, this, events, zero vector, 0)`.
- 2, 4, 0xb–0xf, 0x11 and any other number → setState(0).

Tail of run, after the state switch on every frame the switch was reached (0x27b1a4–0x27b500):
if not inert (+0x231 == 0), state != 0x14, +0x3d0 < g_simFrame, +0x3d4 < 50 and one of the
four handles is empty: one own-generator draw gives a base angle; up to 32 horizontal rays of
length 2000 (float at 0x500a80) from pos + (0,0,36), at base ± (k/2) × 0x800 for k = 0..31,
through `terrain_raycast(1.1, world, origin, dir, 3)`; the first ray with 0 < t ≤ 1 whose
point "hit point − 72 along the ray" (at the guardian's own height) has no player object
within 450 (`players_anyWithinRadius`, all player slots) gets a Droid: `pool_new(0x3d0)` +
`Droid_ctor(obj, "droid", point, facing = own generator, 0)`, V34(3000) (HomeRange), +0x3c4 =
3000, +0x3ac = 3000, cflags |= 0xc000000000000000, `obj_runEveryFrame`, +0x3d4 += 1, +0x3d0 =
clock + 480, handle stored. So at most four live Droids and fifty in total. The spawn timer
mixes two time bases (written from the creature clock at 0x27b4d0–0x27b4f0, tested against
the simulation frame at 0x27b1bc–0x27b1c4). The clock starts at 0 (`Creature_ctor`) and gains
at most 1 per frame, so the test can only be easier to pass than "480 frames since the last
Droid" — Inferred consequence: whenever g_simFrame is more than 480 ahead of the guardian's
clock a Droid is attempted on every frame a handle is free, so the four handles can fill in
four consecutive frames. That lag is the normal case, not a corner: g_simFrame is zeroed at
session/level start (docs/mainloop.md) and an inactive creature sits on a 60-frame run list
(docs/objects.md), so its clock gains 1 per 60 frames until the players arrive. The first
attempt comes at once (+0x3d0 starts at 0). While waiting for a usable ray the base-angle
draw is made every frame.

setState (0x27b550; `Creature_filterState` first): 0 and 0x13 idle_01; 1 clearPath +
pickWanderDest + walk; 3 clearPath + walk; 5 idle_02; 6 attack_01/02 (own generator & 1);
7 attack_03; 8 attack_04; 9 shoot, 10 catapault (both clear +0x3c8); 0x10 sets +0x318 = 60 then
as 3; 0x12 picks entry 9 + (own generator & 3), i.e. hit_reaction_01, hit_reaction_02, idle_01
or idle_02, started with flag 0x10; 0x14 `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this,
pos, facing, 0)`, death animation, V28(0). Other numbers are stored as 0.

takeDamage / touch / trigger / save-load: base creature versions (vtab.py); the Droid handles,
+0x3cc, +0x3d0 and +0x3d4 are therefore not in the save record (Inferred from the shared slots 8/9).
Phases: none by hit points. Counters: the 600-tick junk cooldown and the Droid budget above.
Script-driven: no property read by the class; no level script in scripts/*.txt names
`IronGuardian`, `droid` or the junk objects (grep).
Per-machine: (a) none found (scan and reading): run reads g_simFrame and the all-players count
0x4f8420, makes sounds, and uses only its own generator. (b) draw sets the global draw
parameter 0x41c14c to 3.0 (0x1797c8), calls `Creature_draw`, then `model_resetDrawState`; no
store into the object. (c) none.
Open: what MissileWeapon does with kind 0 and flags 4; whether g_simFrame restarts per level
(decides how often the mixed-base Droid timer misbehaves); meaning of cflags 0x22000020000
beyond the documented body-material bit 0x20000.

#### Droid  (factory name `droid`, call at 0x15a928; also made by IronGuardian_run 0x27b47c; vtable 0x515da8; size 0x3d0)

Functions: ctor 0x27b840, run 0x27ba78, draw 0x27ba08, setState 0x27c0a0. Destructor 0x3cb364
(outside). Everything else is the creature base.

Constructor: `Creature_ctor(10, this, name, pos, angle, classDef 0x500a88, props)`; radius 15;
turn rate 1.4; +0xb4 = 4; speed 0; cflags |= 0x22000020400; **clock +0x300 = g_simFrame** (so
this class's clock is on the simulation-frame base); +0xec = g_simFrame; +0xf4 = g_simFrame +
300; **+0x3cc = g_simFrame + 3600** (self-destruct time); state 0; `obj_runEvery60` (the
guardian then moves its Droids to the every-frame list); setDefEntryParams for entries 3, 9,
10; `Creature_init`. No property read.
Class-definition entries (0x500a88): 3 explode, 4 hit_reaction, 5 idle_aggressive, 6
idle_passive, 7 run, 8 walk, 9 death_01, 10 death_02.

Fields: +0x3c8 s32 = handle returned by `sound_playOnObject` for the fuse sound (setState
0x17), passed to `sound_stop` at 0x27bda0; +0x3cc s32 = clock value after which it self-destructs.

States (run 0x27ba78; usual head with applyKnockback(1.0); then, before the switch: if
+0x3cc < clock and the state is neither 0x14 nor 0x17 → setState(0x17)):
- 0: V25(0) true → 3; else away from home → 1.
- 1: V25(0) true → 3; else `Creature_moveToDest`.
- 3: no target → 0; `Creature_canSeeTargetIn(0, 24, 0, this, facing, 0x7fff, 0)` → 0x17; else
  `Creature_moveToTarget`.
- 5: same test → 0x17; else → 3 when not rooted.
- 0x10 / 0x12 / 0x13: as IronGuardian (→ 0 / → 5 / → 5).
- 0x14 (killed): nothing until events bit 0x40; then ten `PhProp` (`pool_new(0x248)` +
  `PhProp_ctor2` 0x1556c0 with the creature's pose, part mask 1 << i, launch flags 0x4107,
  from the disassembly 0x27bfc8–0x27c030), object flag |= 2, `obj_delete`. `Creature_deadUpdate`
  is not called by this class.
- 0x17 (explode animation): every frame `fx_spawn(0x16, pos + (0,0,36))`. When the clip has
  finished (animation flag 0x80): `sound_stop(+0x3c8)`, `fx_ringBurst(2.0, pos + z 24)`, a
  sound, **`world_damageInRadius(inner 60, outer 144, attacker this, pos, max damage = s16
  +0xd2, type 0x40840, min 0, 0)`**, `decal_add(48, pos + z 1, angle = own generator, 9, 0)`,
  a `LightEffect` (`pool_new(0xbc)` + 0x201bd8), object flags |= 0xa, `obj_delete`, then ten
  `PhProp` (`PhProp_ctor` 0x155a0c, lump "droid.lmp", part mask 1 << i, launch flags 0x112).
- every other number → setState(0).

setState (0x27c0a0): 0/0x13 idle_passive; 1 walk (+ pickWanderDest); 3 run; 5
idle_aggressive; 0x10 +0x318 = 60 then run; 0x12 hit_reaction; 0x14 object flag |= 0x4000,
death_01/02 by own generator & 1, V28(0) (no `Creature_dropLoot`); 0x17 starts the fuse sound
and stores its handle in +0x3c8, object flag |= 0x4000, explode animation, V28(0).
Phases: none; the only counter is the 3600-tick life.
Script-driven: none found (no property read, no script mention).
Per-machine: (a) run: `fx_spawn(0x16)` (camera-gated cosmetic) at 0x27bd80; the stored sound
handle +0x3c8 comes from audio code and is only ever handed back to `sound_stop` — it is
object state that may differ between machines but no decision reads it. `decal_add` depends on
a local option (see symbols/engine.tsv) but its angle is drawn from the own generator before
the call, unconditionally. Nothing else found (scan and reading). (b) draw is only
`Creature_draw(this, V16, V38, 0)`: no stores. (c) none.
Open: PhProp_ctor2 argument meanings (named "body not read" in the symbols).

#### JunkProjectile  (no factory name; made only by IronGuardian_run 0x27b090; vtable 0x515bd0; size 0x74)

Functions: ctor 0x27c2c8, run 0x27c4c0, draw 0x27c3b8, onTouch (slot 6) 0x27c5e8. Destructor
0x3cb514 (outside). Clone is the shared Projectile clone 0x11c7f8.
Constructor(scale, this, owner, modelIndex, pos, velocity, facing): `Projectile_ctor(this, pos,
owner, 0)`; +0x68 = scale; +0x70 = model index; +0x6c = start height (pos z); +0x54..+0x5c =
velocity; +0x38 = facing; +0x60 = 0; object flag |= 1; +0x64 = g_simFrame + 300;
`obj_runEveryFrame`.
Fields: +0x54 Vec3 velocity; +0x60 s32 "damaged something" flag (set by onTouch); +0x64 s32
frame at which it deletes itself; +0x68 float scale; +0x6c float start height (never read in
these four functions); +0x70 s32 index into the IronGuardian class-definition name table.
Run (every frame): velocity z −= 4.95; `obj_moveAndCollide(this, velocity)`; on a non-zero
result: +0x64 = 0, and when the result is 1 and +0x60 == 0 the height is raised to
`terrain_height(5, world, pos)` if below it; `fx_spawn(2, pos)`. Then if +0x64 ≤ g_simFrame the
object destroys itself through slot 1 with argument 3. So it lives until its first collision
or 300 frames.
onTouch(this, other): only when the owner handle +0x4c is live and owner->V20(other) is
non-zero: `damage_apply(d, d, victim other, attacker owner, attack rating owner +0xd4, 0, 0,
flags 0x80001, descriptor 0, 0)` with d = owner (s16 +0xd0) / 4 (integer, toward zero); a
non-zero result sets +0x60 = 1.
Draw: builds a matrix (scale +0x68, position, facing + 0x4000) and draws the model/texture
named by entries [index] and [index + 1] of the table 0x500960 (two `res_find` look-ups in
lump "iron.lmp" per draw call).
Per-machine: (a) run: `fx_spawn(2)` only (cosmetic). (b) draw stores nothing in the object.
(c) draw does two resource look-ups by name and nothing else (the draw scan: no hits).
Open: return codes of `obj_moveAndCollide` (1 is treated as "not an object hit").

---

#### CloudGiant  (factory prefix `CloudGiant*`, call at 0x15a6f8; vtable 0x514448; size 0x538)

Functions: ctor 0x2500b0, run 0x250714, draw 0x250678, saveState 0x252320, loadState
0x252390, trigger (slot 3) 0x252444, takeDamage 0x25246c, setState 0x252488. Destructor
0x3ca44c and the RTTI getter 0x3ca4ac are outside the range.

Constructor(this, pos, angle, props, typeName): `Creature_ctor(10, this, typeName, pos, angle,
classDef 0x4ff348, props)`; a `Weapon2` holder is embedded at +0x3e0 and +0x50 points at it;
+0x28 = 0x4b, +0x29 = 0x32; turn rate 1.2; radius 35; speed 0; activity radius 1200; cflags |=
0x200040000; +0x6c = 0.3; +0xec = g_simFrame; +0xf4 = 0; +0x530 = 0; +0x534 = −1; scale +0xdc
= 2.0; state word +0x232 = 0 stored directly (setState is not called); idle1 pushed;
`obj_runEvery60`; eleven setDefEntryParams calls; `Creature_init`.
- holder slot 1 (hand 1, entry 0x18 = hammer model) — the hammer is always in hand 1.
- Type name starting with `cloudgiantking` (0x159c20 prefix test): +0x3d8 = 1; hand 2 emptied;
  holder slot 6 for hand 1 and for hand 2 (slot 6 is the `ShockWeapons` setter of
  `Creature_init`; each call is `creature_buildElementDamage(…, element 4)`, which writes a
  type-0x18 rider sized by SKILL[12 LightningWeapons] offset 0x5c and **draws g_randSeed
  once**); cflags |= 0x20000000.
- Any other name: +0xe8 = 1 << (own generator % 3) (model variant). +0x3d8 is not written
  and stays 0 (`pool_new` zero-fills).
- Then for every giant: `model_buildHideMask` → +0x220, and one own-generator draw; below 0.1
  → holder slot 6 on hand 1 (one g_randSeed draw). So about one ordinary giant in ten has a
  lightning rider on the hammer.
Class-definition entries (0x4ff348): 3 180atak, 4 atakwind1, 5 atakwind2, 6 boltconjure, 7
bolthrow, 8 boltsalm, 9 boltwalk, 10/11 death_a/b, 12/13 hamtak1/2, 14/15 hitleft/right, 16/17
idle1/2, 18 kick, 19 quake, 20 throw, 21 walk, 22/23 bolt model/texture, 24/25 hammer, 26/27
rock, 28–32 five sounds (bolt_conjure, bolt_hit, bolt_slam, throw, wind).

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | clock value until which no special attack is rolled (clock + 360 from state 3, + 480 from state 5) | 0x250974, 0x250b74 |
| +0x3cc | u8 | wind is blowing (set on events bit 0 in state 7, cleared by setState 7) | 0x250fd8 |
| +0x3d0 | s32 | wind end, clock base (setState 7: clock + 240; zeroed by a damage pass that reached nobody) | 0x251270, 0x2514cc |
| +0x3d4 | s32 | clock + 240, written when a BoltGoRound is made (0x250ea8); no reader in the class | - |
| +0x3d8 | s32 | 1 = king | 0x25076c, 0x2508ec, trigger |
| +0x3e0 | Weapon2 | holder; hand-1 damage descriptor at +0x430, hand-2 at +0x4c0 | |
| +0x508 | s32 | a thrown bolt is in flight | 0x251f84 |
| +0x50c, +0x518 | Vec3 ×2 | bolt head and tail (in flight), or the two ends of the held bolt | tail of run |
| +0x524 | Vec3 | bolt step per frame (length 12) | tail of run |
| +0x530 | u32 | handle returned by `beam_create` for the bolt; 0 = none | 0x250930 (a state decision), tail |
| +0x534 | s32 | handle of the wind loop sound, −1 none | setState head, state 7 |

Weapon2 slots as used here (bodies read: 0x11b5f0, 0x3c2168, 0x11b668, 0x11b858, 0x11b920,
0x11b8c8, 0x3c2238, 0x11b708): 1 = set a hand's model entry (0 empties it); 6 = lightning
rider on a hand; 8 = build a rider of a given element; 9 = hand colour; 11 = drop the held
part as a PhProp; 14 = "is this hand holding something"; 16 = element code of a hand's
descriptor; 17 = pointer to a hand's descriptor.

States (run 0x250714; head: processDamage, Creature_run, `Creature_updateActive` (called twice
for the king, once otherwise; 0 → return), weapon-holder update slot 21 with 0.5,
stepAnim(1.0), applyKnockback(0), V23(0)):
- 0: V25(0) → 3; away from home → 1; clock > +0xf4 → 1; else stay.
- 1: V25(0) → 3; clock ≤ +0xf4 → `Creature_moveToDest`; else → 0.
- 3: no target → 0. King only: hand 2 empty (slot 14) **and +0x530 == 0** → 0x17. Otherwise:
  `Creature_canSeeTargetIn(0, 30, 0, facing, arc 3000, 0)` → own generator & 3: 0 → 10, else 6.
  Not in reach and clock ≤ +0x3c8: canSeeTargetIn(0, 30, 0, facing argument 0, arc 0x7fff, 0) →
  `Creature_turnToTarget`, else `Creature_moveToTarget`. Not in reach and clock > +0x3c8: r =
  own generator % 3 (one draw every frame until something is chosen):
  r 0 and canSeeTargetIn(0, 250, …, 3000, 0) → 7;
  r 1 and NOT canSeeTargetIn(0, 200, …, 3000, 0) and canSeeTargetIn(0, 500, …, 3000, rayMode 1) → 9;
  r 2 → 0xb when hand 2 holds the bolt, else 8.
  A choice sets +0x3c8 = clock + 360.
- 5: canSeeTargetIn(0, 30, 0, facing, 3000, 0) → own generator % 5: 0 → 10, else 6. Otherwise
  clock ≤ +0x3c8 → 3 when not rooted; clock > +0x3c8 → the same three-way roll as state 3
  (the 500 test uses rayMode 0 here), +0x3c8 = clock + 480.
- 6 (hamtak1/2): zero `Creature_moveBy`. With a target, on events bit 0:
  `Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags 8, descriptor = hand-1
  descriptor (slot 17))` — so the lightning rider applies only when hand 1 carries one. Turns
  to the target while animation flag 8 is set; → 3 when it clears.
- 7 (wind; atakwind2 looping under atakwind1): zero moveBy. Events bit 0: starts the wind
  sound (handle → +0x534) and sets +0x3cc. While +0x3cc: 16 particles per frame from attach
  point 2 (positions and velocities from the own generator, ≥ 6 draws each); and on every
  32nd clock tick a box query (±250 in x/y, ± height +0x20 in z, up to 0x80 objects): each
  object with this->V20(obj) != 0 and `creature_canSeePoint(0, 250, this, obj pos, facing,
  3000)` takes `damage_apply((s16 +0xd0)/10, (s16 +0xd2)/10, obj, this, rating 100000, 0, 0,
  flags 0x40440, descriptor, 0)` where the descriptor has one effect: type 0x16 (cold), v1 =
  v2 = Q/5, v3 = 0, Q = SKILL[14 ColdWeapons] table offset 0x5c called with (0, (int) level
  value 0x4f714c, 0). A pass that reached nobody sets +0x3d0 = 0. When clock > +0x3d0:
  `sound_stop(+0x534)`, +0x534 = −1, → 3.
- 8 (quake): zero moveBy. Events bit 0: `camera_shake(6, 0)`; box ±256 on all three axes; every
  object with object flag 0x20 (creature) and without 0x8 whose RTTI type is not exactly
  CloudGiant (type-info compare 0x2515f4–0x251600) takes `damage_apply((s16 +0xd0)/2, (s16
  +0xd2)/2, obj, this, 100000, 0xff, 0, flags 0x4000000, 0, 0)` and then obj->V30(60, 0)
  (stun 60 frames). No V20 enemy test is made: other monster classes in the box are hit too.
  → 3 when animation flag 8 clears.
- 9 (throw / bolthrow): zero moveBy; with a target, turn to it every frame; on events bit 0:
  - hand 2 empty → a rock: aim = pos + facing × 300 passed through
    `Creature_leadTargetPoint(400, this, &aim)`; start = attach point 0; heading clamped to
    facing ± 4000; velocity = unit(aim + z 36 − start) × 400; `pool_new(0x1c8)` +
    `MissileWeapon_ctor`(obj, kind 0, rock model, rock texture, start, velocity, heading −
    0x4000, owner this; stack arguments at 0x251c48–0x251cac: 0, 0, s16 +0xd0, (s16 +0xd2)/2,
    0, 0, +0xd4, 4, descriptor 0).
  - hand 2 holds the bolt → the bolt is thrown: aim as above (lead call made with 300 in the
    speed register, 0x25180c–0x251850); +0x524 = unit(aim + z 36 − start) × 12; +0x50c = +0x518
    = start; `beam_create(8, 16.5, …, 200, 10, 0x5e808080)` → +0x530; +0x508 = 1; hand 2
    emptied; sound.
  → 3 when animation flag 8 clears.
- 10 (kick): zero moveBy; with a target, on events bit 0 `Creature_hitTargetAtReach(36, this,
  +0xd0, +0xd2, +0xd4, flags 0x100041, 0)`; turns while flag 8; → 3.
- 0xb (boltsalm): on events bit 0 a **BoltGoRound** (`pool_new(0x9c)` + ctor 0x252a6c) at pos +
  50 × direction(facing − 5000), z = `terrain_height(6, world, pos)`, duration 240, with the
  slam sound; +0x3d4 = clock + 240; hand 2 emptied; +0x530 = 0. → 3 when flag 8 clears.
- 0x10: attack ready → 0 else flee. 0x12: zero moveBy; animation flag 0x10 clear → 0.
  0x13: not stunned → 0.
- 0x14: `Creature_deadUpdate(50, this, events, facing × 50, 0)`; on events bit 1, if not
  hidden, object flag |= 1 (not solid).
- 0x17 (boltconjure, king only): on events bit 0 hand-2 colour (150, 150, 200, 30), hand 2 =
  entry 0x16 (bolt model), sound. → 3 when flag 8 clears.
- 2, 4, 0xc–0xf, 0x11, 0x15, 0x16 and unknown numbers: nothing (no setState call).

Tail of run (every frame the switch was reached, 0x251dd8 on):
- hand 2 holding the bolt: the two bolt ends are recomputed from the hand attach matrix into
  +0x50c / +0x518, `beam_create(4, 4.5, …)` is called if +0x530 == 0 and its result stored,
  then `beam_update`.
- hand 2 empty and +0x508 set (bolt in flight): `world_raycast(96, world, head, tail − head,
  ignore this, &hit, 0, 0)`; a hit object with (flags & 0x48) == 0x40 (a living player) takes
  `damage_apply(0, 0, hit, attacker 0, rating +0xd4, 0, 0, flags 0x40, descriptor, 0)` with
  one effect: type 0x18 (lightning), v1 = +0xd0, v2 = +0xd2. There is no "already hit" latch:
  the test repeats every frame of the flight. Then head += step; tail follows once it is
  more than 96 behind; `beam_update`. The flight ends (+0x508 = 0, +0x530 = 0) when the head
  is more than 1000 from the giant or the tail is below `terrain_height(6, …)`.

setState (0x252488): always first `sound_stop(+0x534)`, +0x534 = −1, then the common filter.
0: +0xf4 = clock + own generator % 120, idle1. 1: clearPath, pickWanderDest, +0xf4 = clock +
300 + own generator % 120, walk (boltwalk when hand 2 is full). 3 and 0x10: clearPath; the
walk animation is restarted only when the old state is none of 3, 6, 8, 9 (0x10 does NOT set
+0x318). 5 idle2. 6 hamtak1/2 by own generator & 1. 7: atakwind2 + atakwind1, one
own-generator draw → +0xf4 = draw % 20, +0x3cc = 0, +0x3d0 = clock + 240. 8 quake. 9 throw or
bolthrow by hand 2. 10 kick. 0xb boltsalm. 0x12 hitleft/right by own generator & 1. 0x13 no
animation change. 0x14: death_a/b by own generator & 1, `Creature_dropLoot(36, 2, 2.4, 0.6,
4, 0.75, this, pos, facing, 0)`, hand 2 emptied, +0x530 = 0, and when not hidden: object flag
bit 1 cleared and holder slot 11 for hand 1 (the hammer becomes a PhProp); V28(0). 0x17
boltconjure.

takeDamage 0x25246c: a bare tail call of `Creature_takeDamage`. Trigger (slot 3) 0x252444:
`Creature_trigger` only when +0x3d8 == 0 (the king ignores the signal). saveState 0x252320:
`Creature_saveState` + 4 bytes = element code of the hand-1 descriptor (holder slot 16).
loadState 0x252390: `Creature_loadState`, then holder slot 8 (hand 1, saved byte) rebuilds the
hammer rider (a g_randSeed draw when the element is non-zero), and a giant loaded in state
0x14 gets hand 1 emptied; consumes 4 bytes.
Phases: none by hit points. The king cycle is conjure (0x17) → throw (9) or slam (0xb) →
conjure again; the slam and the death case zero +0x530, the flight zeroes it on landing.
Script-driven: no class-specific property; no script in scripts/*.txt names the class (grep
"cloud" has no hit). Weapon element properties are the generic `Creature_init` ones.
Per-machine:
(a) **+0x530 is the return value of `beam_create`** (0x193088: 0 when none of the 20 beam
    slots at 0x7e30d0 is free or `trail_create` fails; otherwise slot | counter 0x44fca4 << 8)
    and the king's state 3 reads "+0x530 == 0" to choose state 0x17 (0x250930). The beam
    table is shared with effect code that is gated per machine: `beam_create` is also called
    at 0x1f6478 inside `fx_modelParticlesNearCamera_1f61c0` (after its `isNearCameraFocus480`
    test at 0x1f6244) and at 0x1f826c inside `fx_modelStatusEffects` (cosmetic seed, hardware
    timer reads) — Observed by xref and the scan, bodies not read further. So the table's
    occupancy, and the counter inside every handle, are per-machine values. Consequence
    (Inferred): if the 20 beam slots or the 64 trails are exhausted on one machine when the
    bolt is thrown (0x2519e8), +0x530 stays 0 there and that machine's king starts state 0x17
    while the bolt is still flying; the others wait for it to land. The stored handle word
    can also differ between machines in normal play (different counter), which matters only
    if object memory is compared. Otherwise: `camera_shake` (cosmetic + rumble) at 0x251530; the wind particles use
    the own generator from run code (same on all machines); sound handle +0x534 is only
    handed to `sound_stop`. The holder update slot 21 (0x118058, creatures area) gates
    `fx_modelStatusEffects` on `isNearView(480, pos)` and passes holder state at +0xc / +0x9c
    to it; that routine was not read.
(b) draw 0x250678: `Creature_draw` then holder slot 18 (0x11b948, draws the two held parts);
    no store into the object. (c) none (the draw scan on both).
Open: what `MissileWeapon` does with kind 0 / flags 4; whether beams made with +0x530 zeroed
(slam, death) are freed by timeout only (`beam_update` keeps one alive for 2 frames);
`fx_modelStatusEffects`.

#### BoltGoRound  (no factory name; made only by CloudGiant_run 0x250e90; vtable 0x514590; size 0x9c)

Functions: ctor 0x252a6c, run 0x252cb4. Destructor 0x3ca39c (outside). Draw, touch and the
rest are the empty GameObject versions (vtab.py).
Constructor(this, pos, facing (unused), duration, sound): `GameObject_ctor(this, pos, 0, 0)`;
object flags |= 0xb; z += 24; +0x50 = g_simFrame + duration; +0x54 = 0; +0x98 = sound handle or
−1; `obj_runEveryFrame`; then for every alive player in `g_alivePlayers` order (all players,
count 0x4f8420) closer than 500: the player's position is stored as target point n (+0x68 +
12n), a beam is made (`beam_create(8, 16.5, pos, point, 200, 10, 0x5e808080)`, handle at +0x58
+ 4n) and the count +0x4c is raised. (The end point given to `beam_create` at 0x252c64 is
read from the slot of the loop index, not of the count — it differs from the stored point
when an earlier player was out of range; only the beam's initial end point is affected,
`beam_update` overwrites it from run.)
Fields: +0x4c s16 beam count (≤ 4); +0x50 s32 end frame; +0x54 float current beam length;
+0x58 u32[4] beam handles; +0x68 Vec3[4] fixed target points; +0x98 sound handle.
Run (every frame): length +0x54 grows 15 per frame up to 500 while g_simFrame < +0x50, then
shrinks 15 per frame to 0. Each frame it serves only the beams whose index has the parity of
g_simFrame (index = frame & 1, step 2). For each: end = pos + unit(point − pos) × min(length,
500); while not expired `world_raycast(1.1, world, pos, that vector, ignore this, &hit, 0,
0)`; a hit object with flag 0x40 (a player; no dead test) at t < 1 takes `damage_apply(0, 0,
hit, attacker 0, rating 100000, 0, 0, flags 0x40, descriptor, 0)` with one effect: type 0x18
(lightning), v1 = v2 = (int)(`level_getMonsterLevel()` × 0.3); the beam end snaps to the
victim. `beam_update` for that beam. When g_simFrame > +0x50 and the length is 0:
`sound_stop(+0x98)` and self-destruct through slot 1 (3).
The target points are never changed after construction: the beams do not track or rotate.
The damage has no attacker and no link to the giant (it continues if the giant dies).
Per-machine: (a) run reads only g_simFrame and its own fields; the beam handles are used only
as arguments of `beam_update` (a failed `beam_create` gives handle 0, which `beam_update`
ignores, while the ray and the damage still happen) — none found. (b)(c) no draw function.
Open: none.

---

#### Demon  (factory prefix `Demon*`, call at 0x15a89c; vtable 0x514b40; size 0x468)

Functions: ctor 0x25dc6c, run 0x25e17c, draw 0x25e118, saveState 0x25eef8, loadState
0x25ef68, setState 0x25efd0, isEnemy (slot 20) 0x25f378. A further helper lies just past the
range: 0x25f3fc "is my target a Soul" (exact RTTI compare with the Soul type info 0x3cc7a0;
callers 0x25e448 and 0x25eb0c, both in Demon_run). Destructor 0x3ca7bc (outside).

Constructor: `Creature_ctor(10, this, typeName, pos, angle, classDef 0x4ffc90, props)`; a
`Weapon1` holder embedded at +0x3c8 (+0x50 points at it; its damage descriptor is at +0x418);
turn rate 0.8; radius 20; +0x28 = 0x30; speed 0; +0xec = g_simFrame; +0xf4 = 0; +0x464 = 0;
state word 0 stored directly; scale 1.0; hand 1 = entry 0x12 (the `mgrabber` model);
guard animation pushed; `obj_runEvery60`; six setDefEntryParams; `Creature_init`.
Variant byte +0x460 from the type-name prefix:
- 1 `demonshaman`: +0x5c = 1, +0x60 = −0.25, cflags |= 0x200040000, tint preset +0xa0 = 6.
- 2 `demonwater`: cflags |= 0x200040000 only.
- 3 `demonfire`: +0x5c = 1, +0x60 = −0.25, cflags |= 0x200000000, holder slot 2 (the
  `FireWeapons` setter: fire rider type 0x15 sized by SKILL[13 FireWeapons] offset 0x5c, one
  g_randSeed draw), **object flag |= 2** (not drawn by the grid walk).
- 0 anything else: +0x5c = 1, +0x60 = −0.25, cflags |= 0x200040000; one own-generator draw;
  below 0.5 a second draw: even → holder slot 2 (fire rider as above); odd → cflags |=
  0x800000000000 and tint preset 8.
Class-definition entries: 3–5 attack1..3, 6 block, 7 blockhit, 8 guard, 9 hit, 10/11 idle1/2,
12 run, 13 walk, 14 death1, 15–17 torturea/b/c, 18/19 mgrabber model/texture.

Fields: +0x3c8 Weapon1 holder; +0x460 u8 variant; +0x464 s32 zeroed in the constructor and
not used by any function of the range; +0xf4 is used as the end clock of states 10 and 0x11
and as the death clock.

States (run 0x25e17c; head: processDamage, Creature_run, updateActive, holder update slot 21
(0.5), stepAnim(1.0), applyKnockback(0.2), V23(0)):
- 0: V25(0) → 3; away from home → 1. 1: V25(0) → 3; else moveToDest.
- 3: no target → 0. `Creature_canSeeTargetIn(0, 24, 0, facing, 5000, 0)` → 5. Variants 1 and
  3: canSeeTargetIn(0, 400, 0, facing, 5000, rayMode 1) → 5. canSeeTargetIn(0, 120, …, 5000,
  0) and `Creature_countAlliesNearTarget(24, this)` > 1 → 5 (waits when two allies are
  already on the target). canSeeTargetIn(0, 24, …, arc 0x7fff, 0) → turn to target. Else
  `Creature_moveToTarget`.
- 5: in reach (0, 24, arc 5000): target is a Soul → 9; otherwise own generator % 5: 0 → 0x11,
  else 6. Not in reach: within 24 at any angle → turn. Variants 1 and 3 with
  canSeeTargetIn(0, 400, …, 5000, 1) → 10. Rooted → stay. Otherwise one own-generator draw per
  frame; only when draw % 60 == 0 → 3 (and, if the target is within 156 in the arc, only when
  fewer than two allies are near it).
- 6 / 7 / 8 (attack1 / attack2 / attack3): with a target, on events bit 0: (min, max) = (+0xd0,
  +0xd2); if cflag 0x800000000000 is set (the "odd" plain variant) one own-generator draw,
  and below 0.5 both are doubled and `Creature_emitLinkParticles(this, target)` runs (more
  own-generator draws). `Creature_hitTargetAtReach(36, this, min, max, +0xd4, flags 8 (state
  8: 0x80008), descriptor = hand-1 descriptor)` — the fire rider when the holder has one.
  Turns to the target every frame. On events bit 1 while the clip plays: own generator & 1 ==
  0 and canSeeTargetIn(0, 40, …, 5000, 0) → 6 → 7, 7 → 8 (combo). → 3 when animation flag 8
  clears.
- 9 (torturea): while the target is a Soul within (0, 40, arc 5000): on events bit 0 the
  Soul's slot 2 is called directly with (amount = (float) s16 +0xd2, attacker this, flags 0)
  — no `damage_apply`, no roll; turn to it; when its hit points +0x228 are ≤ 0 → 3. If the
  target stops being a Soul or leaves reach: setState(3) and the torturec clip is started
  with flag 0x20.
- 10 (cast; reached only by variants 1 and 3): aim = pos + facing × 300 passed through
  `Creature_leadTargetPoint(400, this, &aim)`. On events bit 0: hand colours (holder slots 10
  and 9), then own generator & 1:
  - 0 → `pool_new(0xb4)` + `FireStorm_ctor(obj, (int) level value 0x4f714c, this, (aim.x,
    aim.y, own z + 6), SKILL[7 FireStorm])` — the spell object is built directly; the skill's
    cast entry (offset 0x14) is not called and the result is not linked to the creature.
  - 1 → SKILL[57 ShockOfFire] table offset 0x64 is called four times with index 0, 1, 2, 3
    (level value, this, last argument 0, 0, 10, 10); D = result 0, speed = result 3 (results 1
    and 2 unused); one own-generator draw r between them; angle =
    `creature_aimAngleAt(speed, this, target)`; `pool_new(0xb8)` + `Sparks_ctor(obj, pos + z
    height/2, (cos, sin)(angle) × speed, this, 0, 0, D, D + (int)(D × 0.2 × r/65536))`.
  Every frame with a target: V26(0, &aim). → 3 when clock > +0xf4.
- 0x10: attack ready → 0 else flee. 0x11 (block): cflags |= 0x200 every frame; → 3 when clock
  > +0xf4. 0x12: animation flag 0x10 clear → 0. 0x13: not stunned → 3.
- 0x14: variant 2: `Creature_deadUpdate(0, this, events, 0-vector, 0)` only. Other variants:
  `Creature_deadUpdate(…, 1)`, `fx_modelParticlesNearCamera_1f5210` every frame; clock > +0xf4
  + 60 → object flag |= 2 and cflags |= 0x20000000000; clock > +0xf4 + 75 → `obj_delete`. For
  all variants: once clock > +0xf4 + 60 and hand 1 still holds its part → holder slot 11
  (drops it as a PhProp).
- Tail, variant 3 only: `fx_modelParticlesNearCamera_1f5210` every frame.
- 2, 4, 0xb–0xf and unknown numbers: nothing.

setState (0x25efd0): after the filter it clears cflag 0x200. 0 guard; 1 walk + wander point;
3 and 0x10 run (0x10 does not set +0x318); 5 idle1; 6/7/8 attack1/2/3; 9 torturea; 10
attack1 clip and +0xf4 = clock + 240 + (int)(own generator / 65536 × 180); 0x11 block clip,
cflags |= 0x200, +0xf4 = clock + 60 + own generator % 60; 0x12 blockhit clip (flag 0x10); 0x13
idle2; 0x14 object flag |= 0x4000, +0xf4 = clock, `Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25,
this, pos, facing, 0)`, clip death1 for variant 2 and **idle1 for every other variant**
(those burn away standing), V28(0).

isEnemy (slot 20, 0x25f378): `Creature_isEnemy`; when that says 0 and the other object is
exactly a Soul (RTTI) and not dead (flag 8) the answer is 3. With the state-5 test this is
the whole "demons attack Souls" rule.
saveState 0x25eef8: creature record + 4 bytes = element code of the hand-1 descriptor (holder
slot 16: 1 fire, 2 cold, 3 poison, 4 lightning, 6 type 0x1f). loadState 0x25ef68: holder slot
8 is called with (saved word, 0) — register order read at 0x25ef90–0x25efb4 — whereas
CloudGiant_loadState calls the same slot with (1, saved byte). `Weapon1` slot 8 takes (hand,
element), so for a saved code of 0 or 1 this rebuilds the descriptor with element 0, which
clears its four effect slots: **a Demon restored from a level record loses its fire rider**;
codes ≥ 2 do nothing. Observed; that the arguments are swapped by mistake is Inferred.
Phases: none.
Script-driven: no class-specific property; no script names the class (grep, excluding
`hideMonster` false hits).
Per-machine: (a) none found by the scan. By reading: run calls
`fx_modelParticlesNearCamera_1f5210` (camera-gated, cosmetic seed per its symbol note) with the
creature's effect block +0x320 — the routine `Creature_run` already uses for burn visuals
(creatures C7); what it writes into +0x320 was not read. The holder update slot 21 (Weapon1:
0x11b2a8) was not read. All decisions use the own generator. (b) draw 0x25e118: `Creature_draw`
+ holder draw slot; no store. (c) none.
Open: FireStorm_ctor / Sparks_ctor parameter meanings beyond what is passed; the meaning of
ShockOfFire's offset-0x64 indices 1 and 2; why variant 3 is constructed with object flag 2.

---

#### SeaMonster  (factory name `SeaMonster`, call at 0x15b4a0; vtable 0x517368; size 0x3d0; model lump `crusher`)

Functions: ctor 0x2a428c, run 0x2a44a8, draw 0x2a445c, slot 11 0x2a4a9c (empty), setState
0x2a4aa4. Destructor 0x3cc508 (outside). takeDamage and the rest are base versions.
Constructor: `Creature_ctor(10, this, name, pos, angle, classDef 0x5021b0, props)`; radius 35;
turn rate 1.2; +0x28 = 0x41, +0x29 = 0x32; speed 0; scale 1.0; +0xe0 = 10; cflags |=
0x8000040000; +0xec = g_simFrame; +0xf4 = 0; state word 0 stored directly; csh_idle1 pushed;
`obj_runEvery60`; setDefEntryParams 4, 5, 6; `Creature_init`. No property read.
Class-definition entries: 3 block, 4 crush, 5 csh_atak1, 6 csh_atak2, 7 csh_idle1, 8
csh_idle2, 9 death, 10 hitreact, 11 run, 12 spawn, 13 stepleft, 14 stepright, 15 walk.
Entries 3 (block) and 12 (spawn) are not used by setState.
Fields: +0x3cc s32 is read in state 5 (compared with 7 and 9) and never written by any
function of the class; `pool_new` zero-fills, so it is always 0 and both comparisons always
pass. (+0x3c8 is not touched at all.)

States (run 0x2a44a8; head: processDamage, Creature_run, updateActive, stepAnim(1.0),
applyKnockback(0.2), V23(0)):
- 0: V25(0) → 3; away from home → 1. 1: V25(0) → 3; else moveToDest.
- 3: no target → 0. `Creature_canSeeTargetIn(0, 36, 0, facing, 5000, 0)` → 5; within 36 at any
  angle (arc 0x7fff) → turn to target; else `Creature_moveToTarget`.
- 5: not in (0, 36, arc 5000): → 3 when not rooted. In reach: own generator & 1 == 0 → 7;
  otherwise a second draw, % 3 == 0 → 9, else 6. (Net odds 1/2, 1/6, 1/3.)
- 6 (csh_atak1 or csh_atak2 by own generator & 1 in setState), 7 (csh_atak1), 8 (csh_atak2):
  `Creature_settle`; with a target, on events bit 0 `Creature_hitTargetInArc(0, 36, this,
  facing, 5000, +0xd0, +0xd2, +0xd4, flags 8, 0)`. In 7 and 8 only: on events bit 1, own
  generator & 1 == 0 and the target still in (0, 36, 5000) → setState(8) from 7, setState(7)
  from 8 (the chain can repeat). → 5 when animation flag 8 clears.
- 9 (crush): zero `Creature_moveBy`; on events bit 0 the same hit with flags 0x80008. → 5.
- 0x10: attack ready → 0 else flee. 0x12: flag 0x10 clear → 5. 0x13: not stunned → 5.
- 0x14: `Creature_deadUpdate(30, this, events, 0-vector, 0)`.
- 0x17 (stepleft) / 0x18 (stepright): zero moveBy; → 3 when animation flag 8 clears. Nothing
  in this class requests 0x17 or 0x18; `ScriptGenerator_spawn` requests 0x17 only for
  Skeleton (0x265fc4). Who else could: Unknown.
- 2, 4, 10–0xf, 0x11, 0x15, 0x16, unknown numbers: nothing.
setState (0x2a4aa4): 0/0x13 csh_idle1; 1 walk + wander point; 3 and 0x10 run (0x10 does not
set +0x318); 5 csh_idle2; 6/7/8/9 as above; 0x12 hitreact; 0x14 `Creature_dropLoot(36, 2, 1.8,
0.6, 2, 0.25, this, pos, facing, 0)`, death, V28(0); 0x17 / 0x18 the step clips (flags 0x808).
Slot 11 (list of touched objects) is overridden with an empty function.
Phases: none. No attack has a rider, a cast or a created object.
Script-driven: `generateMonster('<generator>', 'SeaMonster')` in scripts/ISLGNOME.txt (six
call sites) creates them through `ScriptGenerator_spawn`; no class-specific property.
Per-machine: (a) none found (scan and reading; own generator only). (b) draw sets the global
draw parameter 0x41c14c to 2.0, `Creature_draw`, `model_resetDrawState`; no store into the
object. (c) none.
Open: who enters states 0x17/0x18; cflag 0x8000000000 meaning.

---

#### LavaMonster  (factory names `LavaMonster` → variant 0, call 0x15aef8; `EarthElemental` → variant 1, call 0x15a970; vtable 0x510118; size 0x430)

Functions: ctor 0x28048c, run 0x280b44, draw 0x280a60, saveState 0x282260, loadState
0x2822e8, setState 0x282460, getModel (slot 16) 0x282868, getSecondModel (slot 38) 0x282888.
Clone 0x124b78 and destructor 0x3c4538 are outside. takeDamage is the base version.

Constructor(this, name, pos, angle, props, variant): `Creature_ctor(10, this, name, pos, angle,
classDef 0x500bb0 + variant × 0x108, props)` (the two class definitions have the same 30
entries; only lump, model and texture differ: `lavabst`/`lavabeast` vs `element`/
`earth_elemantal`). A damage descriptor is embedded at +0x3d8 (no weapon holder; +0x50 is not
set). Turn rate 1.2; radius 30; +0x28 = 0x3c; +0xb4 = 0xb; speed 0; +0xec = g_simFrame;
+0x420 = variant; +0x3c8 = +0x424 = +0x42c = 0; scale +0xdc = 0.9 + own generator × 0.2.
- variant 0: +0xe8 = own generator % 15 (model-variant bits); +0x5c = +0x64 = +0x68 = +0x6c =
  1, +0x60 = −0.2; cflags |= 0x4000020800; then one own-generator draw compared with
  1.0999999 (always below, so unconditional): fire rider in the descriptor — effect type
  0x15, v1 = Q, v2 = Q + (int)(Q × 0.2 × own generator / 65536), Q = SKILL[13 FireWeapons]
  offset 0x5c with (0, (int) level value, 0). The spread comes from the OWN generator here
  (the generic `creature_buildElementDamage` uses g_randSeed).
- variant 1: cflags |= 0x4000010800; +0x5c = 0.5, +0x60 = −0.2, +0x64 = +0x68 = +0x6c = 1;
  +0xe8 = 0; no rider.
Both carry cflag 0x800 ("nobody's enemy or ally") from construction. +0x220 from
`model_buildHideMask`; state word 0x17 stored directly with the `underground` clip pushed
(the "+0x424 == 1 → state 0 with the block clip" branch cannot be taken: +0x424 was just
zeroed); `obj_runEvery60`; nine setDefEntryParams; `obj_updateGridCell`; +0x3d0 = 1.0;
**+0x3cc = (int) hit points / 2** (after `Creature_ctor` has set the stats); `Creature_init`.
Class-definition entries: 3 death2, 4 death1, 5–7 hit1..3, 8 idle1, 9 lava_launch, 10 pivot,
11 rise, 12 roar, 13 run, 14 slam, 15/16 slap_left/right, 17 swipe_combo, 18/19
swipe_left/right, 20 taunt, 21 throw, 22 throw2, 23 underground, 24 walk, 25 block, 26/27
lavarock model/texture, 28 throw sound, 29 throw-hit sound.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | a rock is in the hand (state 8, events bit 0 … bit 1) | draw, tail of run |
| +0x3cc | s32 | half of the hit points at construction | states 3, 5; setState 3 |
| +0x3d0 | float | light scale used by draw; 1.0, fades to 0.3 in the fade death | draw, state 0x14 |
| +0x3d8 | descriptor | melee rider (effect slots from +0x3fc) | states 6, 7; save/load |
| +0x420 | s32 | variant: 0 LavaMonster, 1 EarthElemental | everywhere |
| +0x424 | s32 | zeroed by the constructor, no writer in the class; non-zero would make slots 16/38 return 0 and freeze state 0 | 0x282868, 0x282888, state 0 |
| +0x428 | s32 | death kind, own generator & 1 at death: 0 fade, 1 shatter (matters for variant 0) | state 0x14 |
| +0x42c | s32 | variant 1: effect toggle in state 8 (events bit 2) | state 8 |

States (run 0x280b44; head: `Creature_processDamage` only while cflag 0x800 is clear —
so pending damage is not processed while underground; Creature_run; updateActive;
stepAnim(1.0); applyKnockback(0.2); V23(0)):
- 0x17 (underground, the start state): `Creature_turnToTarget`; V25(0) true → 0.
- 0: clears cflag 0x800 every frame. While the rise clip is still playing (animation flag
  0x20): turn to target; variant 1 also `fx_spawn(0x14, pos + random offset < 36)` (two
  own-generator draws) every frame. Afterwards: V25 → 3; away from home → 1.
- 1: V25(0) true → 0; else moveToDest.
- 3: no target → 0. `Creature_canSeeTargetIn(0, 150, 0, facing, 6000, 0)` → 5. Ranged gate →
  5: variant 0 needs hit points > +0x3cc AND cflag 0x2000000000000000 (the "standing in
  water" bit of `Creature_moveBy`) AND canSeeTargetIn(0, 400, …, 6000, 0); variant 1 needs
  only the 400 test. Else within 20 at any angle → turn; else `Creature_moveToTarget`.
- 5: canSeeTargetIn(0, 48, …, 6000, 0) → 6; (0, 150, …) → 7; the same ranged gate → 8; else →
  3 when not rooted.
- 6 (swipe_combo / swipe_left / swipe_right by own generator % 3) and 7 (slap_left /
  slap_right by own generator & 1): `Creature_settle`, turn to target; with a target, on
  events bit 0: state 6 `Creature_hitTargetInArc(0, 48, this, facing, 6000, +0xd0, +0xd2,
  +0xd4, flags 1, descriptor +0x3d8)`; state 7 the same with flags 0x40001, or 0x80001 when
  own generator % 3 == 0. The descriptor carries the fire rider for variant 0 only. → 3 when
  animation flag 8 clears.
- 8 (throw2): settle, turn to target. Events bit 0: +0x3c8 = 1. Events bit 1 (without bit 0):
  +0x3c8 = 0 and a **LavaBomb** is made (see below): aim = pos + facing × 300 through
  `Creature_leadTargetPoint(400, this, &aim)`; start = attach point 0; velocity = 400 along
  the heading start → aim, z = (80 + own generator % 40) × |pos − aim| × 0.0025; sound.
  Variant 1 only: events bit 2 flips +0x42c, and while it is set `fx_spawn(0x14)` at attach
  point 0 (ground height) every frame. → 3 when animation flag 8 clears.
- 0x10: attack ready → 0 else flee. 0x12: animation flag 0x10 clear → 3. 0x13: not stunned →
  0.
- 0x14: +0x28 = 0x50. Variant 1: `Creature_deadUpdate(40, this, events, 0-vector, 0)`.
  Variant 0, +0x428 == 0 (fade): deadUpdate(20, …, 0); +0x3d0 −= 0.005 per frame, particles
  from random model sample points every 4th clock tick (own generator); at +0x3d0 ≤ 0.3
  `obj_stopRunning`. Variant 0, +0x428 == 1 (shatter): deadUpdate(20, …, 1); on events bit 2:
  sound, one particle per model sample point (own generator), 15 `PhProp` (`PhProp_ctor2`,
  part masks 1 << 5 … 1 << 19, launch flags 0x100, 0x281854–0x2818bc), object flags |=
  0x4002, cflags |= 0x20000000000, `obj_stopRunning`.
- 2, 4, 9–0xf, 0x11, 0x15, 0x16, unknown → setState(0).
Tail (variant 0 only, every frame): unless dead, two particles from random model sample
points; while +0x3c8 is set, eight more around attach point 0. All positions and velocities
come from the own generator (rejection sampling, ≥ 4 draws per particle), i.e. a living
LavaMonster consumes its own generator every active frame.

setState (0x282460): 0: idle1, and when coming from 0x17 also the rise clip with flag 0x20;
+0xf4 = clock + own generator % 120. 1: walk + wander point. 3: clearPath; idle1 (mode 3) when
hit points > +0x3cc and the water bit is set, otherwise walk — both variants. 5, 0x13 idle1.
6, 7, 8 as above (8 also clears +0x42c). 0x10 walk (no +0x318 write). 0x12: **ignored while
in state 8** (the state stays 8, no clip change); otherwise hit1 with flag 0x10. 0x14:
`Creature_dropLoot(36, 2, 2.8, 0, 3, 0.25, this, pos, facing, 0)`, +0x428 = own generator & 1,
clip death2 (0) or death1 (1), V28(0). Finally, any state other than 0 and 0x17 clears cflag
0x800.
Slots 16 / 38 return the class definition's model / texture unless +0x424 != 0.
saveState 0x282260: creature record + 4 bytes = 1 when the descriptor has a type-0x15 effect
with non-zero v1. loadState 0x2822e8: clears the four effect types, and when the saved word
is non-zero rebuilds the fire rider (same expression as the constructor, one own-generator
draw).
Phases: the half-health threshold +0x3cc: above it (and standing in liquid) variant 0 stays
planted with the idle clip and throws at up to 400; at or below it, or out of liquid, it only
walks into melee. Variant 1 throws regardless of health.
Script-driven: no class-specific property; no script names either type (grep).
Per-machine: (a) `fx_spawn(0x14)` at 0x280dac and 0x281594 (cosmetic, variant 1). Particles
are spawned from run code with the own generator (same on every machine; `particle_spawn`
itself silently drops when its pool is empty, after the draws). Nothing else found (the scan +
reading). (b) draw 0x280a60: sets the global draw parameter 0x41c14c to 2.0, scales the
per-object light by +0x3d0 (`light_scaleObjectLight`), `Creature_draw`, draws the rock model
when +0x3c8 is set, `model_resetDrawState`; no store into the object. (c) none.
Open: what sets the "standing in water" bit in the lava levels (the bit is written by
`Creature_moveBy`, not read here); cflags 0x4000000000, 0x10000, 0x20000 meanings.

#### LavaBomb  (no factory name, no constructor function; vtable 0x516038; size 0x1d8)

Functions: draw 0x2828a8, run 0x282954, onTouch (slot 6) 0x283214. Destructor 0x3cb680
(outside); clone and slot 17 are MissileWeapon's.
docs/monsters.md lists "ctor 0x281194": that address is the case label of state 8 inside
LavaMonster_run, not a function. The object is built inline at 0x2813c8–0x28149c:
`pool_new(0x1d8)`, `MissileWeapon_ctor`(obj, kind 0, lavarock model, lavarock texture, start,
velocity, facing − 0x4000, owner; stack arguments 0, 0, (s16 +0xd0) × 2, (s16 +0xd2) × 2, 0,
0, +0xd4, 1, descriptor 0), then the virtual table is replaced by 0x516038 and three fields
are added: +0x1cc = hit sound (class-definition entry 29), +0x1d0 = the lump handle,
+0x1d4 = 1 for variant 0 (lava) / 0 for variant 1 (earth).
Fields used (MissileWeapon layout): +0x4c owner handle; +0xcc u8 hit latch (0 none, 1
damaged something, 2 touched without effect); +0xd4 / +0xd8 the doubled damage pair; +0xdc,
+0xe0 = 0; +0xe4 attack rating; +0xec frame at which it deletes itself; +0x1b0 Vec3
velocity; +0x1c0 / +0x1c4 model / texture; +0x1c8 s16 spin angle.
Run (every frame): spin −= 2000; velocity z −= 9.0; lava bombs emit 8 particles (own
generator of the bomb); `obj_moveAndCollide(this, velocity)`. On a non-zero result: +0xec =
0; hit sound; lava bombs burst 250 particles (own generator, ≥ 6 draws each); `fx_spawn(2)`
for results 1 (at terrain height + 5) and 2; then six `PhProp` chunks (`PhProp_ctor`, lump
+0x1d0, lavarock model, part mask 1 << 1 … 1 << 6, launch flags 0x112) whose horizontal
velocity is replaced by 0.3 × own + 0.3 × the bomb's and whose +0x30 is scaled by 0.6,
followed by `PhProp_initPhysics`. Then +0xec ≤ g_simFrame → self-destruct via slot 1 (3).
onTouch(this, other): nothing once +0xcc != 0. If the owner still exists and `other` has
exactly the owner's RTTI type (another LavaMonster/EarthElemental) → no damage, latch = 2.
Otherwise earth bombs: `damage_apply((float) +0xd4, (float) +0xd8, other, attacker = the
bomb, rating +0xe4, +0xdc, +0xe0, flags 1, descriptor 0, 0)`; lava bombs:
`damage_apply(0, 0, other, the bomb, +0xe4, +0xdc, +0xe0, flags 1, descriptor, 0)` with one
effect type 0x15 (fire), v1 = +0xd4, v2 = +0xd8 — all of a lava bomb's damage is fire.
Latch = 1 when `damage_apply` returned 1, else 2.
Per-machine: (a) run: `fx_spawn(2)` at 0x28302c / 0x28305c / 0x2830d4 (cosmetic); particles
from run code with the bomb's own generator; expiry against g_simFrame. None found
otherwise. (b) draw 0x2828a8 builds a matrix from position, facing and spin and calls
`model_draw`; no store. (c) none (the draw scan: no hits).
Open: meaning of `obj_moveAndCollide` results 1 and 2 (the code treats 1 as terrain).

---

#### Minion  (factory name `Minion`; vtable 0x5164a8; size 0x3e8; model `beezabub` in lump `minion`)

Functions: ctor 0x285f10, run 0x2862c0, draw 0x28625c, trigger (slot 3) 0x287430 (empty),
takeDamage 0x287438 (bare tail call of `Creature_takeDamage`), setState 0x287454. Destructor
0x3cb9b0 (outside). Boss rank 2 by type name (`creature_bossRank`).
Constructor: `Creature_ctor(10, this, name, pos, angle, classDef 0x500ee0, props)`; radius 45;
turn rate 1.2; +0x28 = 100, +0x29 = 0x32; speed 0; scale 1.3; cflags |= 0x220040000; the five
resistances +0x5c..+0x6c = 0.5; +0xec = g_simFrame; +0xf4 = 0; +0x3c8 = 0, +0x3cc = 1, +0x3d0 =
0, +0x3dc = 0, +0x3e0 = 0; state word 0 stored directly; idle1 pushed; `obj_runEvery60`; ten
setDefEntryParams; `Creature_init`. No property read.
Class-definition entries: 3 atak_bk, 4 atak_f1, 5 atak_f2, 6 atak_lf, 7 atak_rt, 8 dethbreth,
9–12 four hit clips (unused: see setState 0x12), 13 idle1, 14 roar, 15 so_catch, 16 so_club,
17 so_shoot, 18 death, 19 torment, 20 walk, 21/22 bow model/texture, 23 a sound
(spel_minion_rain).

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | handle | the Soul it is holding | head of run, states 3/5/7/8, setState |
| +0x3cc | s32 | "draw the bow model"; 1 from the constructor, no other writer | draw |
| +0x3d0 | handle | the victim the current attack turns toward | states 3, 5, 6–9 |
| +0x3d4 | s32 | last attack state (set by setState 6–0xc); stops 10, 0xb, 0xc repeating | states 3, 5 |
| +0x3d8 | s32 | the hit event of the current attack has happened (stops the turning) | states 6–9 |
| +0x3dc | s32 | clock before which state 9 is not chosen (clock + 600 + own generator % 300) | states 3, 5 |
| +0x3e0 | s32 | clock before which state 8 is not chosen; zeroed by the constructor and never written again, so the gate is always open after the first tick | states 3, 5 |

States (run 0x2862c0; head: processDamage, Creature_run, `Creature_updateActive` **with the
result ignored** (the AI also runs while "inactive"), stepAnim(1.0), applyKnockback(0.2),
V23(0); then, when a Soul is held, the Soul's position is set to model attach point 0, its
facing to the Minion's, and `obj_updateGridCell` is called for it):
- 0: V25(0) → 3; away from home → 1; clock > +0xf4 → 1. 1: V25(0) → 3; clock ≤ +0xf4 →
  moveToDest; else → 0.
- 3 and 5 (same tree; where 3 moves, 5 goes to 3 when not rooted): no target → 0 (5: → 3).
  The victim handle is cleared, then:
  - no Soul held: victim = the target if `Creature_canSeeTargetIn(0, 120, lead 0.3, facing,
    0x7fff, 0)`, else `creature_findEnemyInCone(0, 120, facing, 0x7fff)`.
    - no victim: +0x3dc < clock and findEnemyInCone(120, 350, facing, 3000) → 9; otherwise →
      **0x17** (catch a Soul).
    - victim: canSeeTargetIn(0, 120, 0.3, facing, 4000, 0) → 6; last attack != 10 and
      canSeeTargetIn(0, 120, 0.3, facing + 11000, 7000, 0) → 10; last != 0xb and the same at
      facing − 11000 → 0xb; last != 0xc and the same at facing − 24000 with arc 6000 → 0xc;
      else turn to target.
  - Soul held: victim = the target if canSeeTargetIn(0, 170, 0.3, facing, 18000, 0), else
    findEnemyInCone(0, 170, facing, 18000) → 7. No victim and clock > +0x3e0: victim = the
    target if canSeeTargetIn(275, 500, 0.3, facing, 2000, 0), else findEnemyInCone(275, 500,
    facing, 2000) → 8. Otherwise `Creature_moveToTarget`.
- 6 (atak_f1/f2), 10 (atak_lf), 0xb (atak_rt), 0xc (atak_bk): zero moveBy. Events bit 0:
  `Creature_hitTargetOrPlayerInArc(0, 120, this, F, A, +0xd0, +0xd2, +0xd4, flags, 0)` with
  (F, A, flags) = (facing, 4000, 1) for 6; (facing + 11000, 7000, 0x80001) for 10; (facing −
  11000, 7000, 0x80001) for 0xb; (facing − 24000, 6000, 0x80001) for 0xc; +0x3d8 = 1. Before
  the hit, state 6 turns toward the victim (V26); after it, state 6 turns to the target while
  it is in (0, 120, arc 4000). → 3 when animation flag 8 clears.
- 7 (so_club): zero moveBy. Events bit 0: hitTargetOrPlayerInArc(0, 170, this, facing, 18000,
  +0xd0, +0xd2, +0xd4, flags 1, 0), +0x3d8 = 1, and the Soul handle is dropped (the Soul is
  not deleted here). Turns toward the victim before the hit. → 3.
- 8 (so_shoot): zero moveBy. Events bit 0: +0x3d8 = 1; if a Soul is held: v =
  findEnemyInCone(275, 500, facing, 2000); when found it is linked into the Soul's handle at
  Soul +0x3cc; the Soul is put in its state 0x1b; the Minion's handle is dropped. → 3.
- 9 (dethbreth): events bit 0: SKILL[58 FrostStorm] table offset 0x64 is called four times
  (index 0..3, (int) level value, this, 10) → p0..p3; `pool_new(0xb0)` + the spell
  constructor 0x1ff860 (`RainOfFireSpell_ctor` in the gameplay symbols) with ((float)(int)(p1
  × 12 × 1.5), obj, pos + facing × 100, p2 × 60, p0, this, velocity = facing × 2 × p3, sound =
  class-definition entry 23). Events bit 1: +0x3d8 = 1. → 3 when animation flag 8 clears.
- 0x10: attack ready → 0 else flee. 0x12: animation flag 0x10 clear → 0 (not reachable, see
  setState). 0x13: not stunned → 0.
- 0x14: when the death clip has finished (animation flag 0x80) → `obj_stopRunning`.
  `Creature_deadUpdate` is not called.
- 0x17 (so_catch, clip flags 0x810): zero moveBy; when animation flag 0x10 has cleared →
  setState(3). Events bit 0: `pool_new(0x3e0)` + `Soul_ctor(obj, "soul", attach point 0,
  facing, 0, this)`; the Soul is linked into +0x3c8 and put in its state 0x1a.
- 2, 4, 0xd–0xf, 0x11, 0x15, 0x16, unknown: nothing in run.

setState (0x287454): 0 (and every unlisted number, stored as 0): +0xf4 = clock + own generator
% 120, idle1, held Soul → Soul state 0x1e. 1: wander point, +0xf4 = clock + 300 + own generator
% 120, walk, Soul → 0x1f. 3: walk restarted only when the old state is none of 3, 6, 10, 0xb,
0xc; Soul → 0x1f. 5: idle1, Soul → 0x1e. 6: atak_f1/f2 by own generator & 1. 7: so_club, Soul →
0x1d. 8: so_shoot, Soul → 0x1c. 9: dethbreth, +0x3dc = clock + 600 + own generator % 300. 10 /
0xb / 0xc: the side and back clips. 6–0xc all clear +0x3d8 and store the state in +0x3d4.
0x10: walk, Soul → 0x1f (no +0x318 write). **0x12 is refused: the state stays what it was**
(no hit reaction). 0x13 idle1. 0x14: death clip, held Soul → Soul state 0x21, V28(0); **no
`Creature_dropLoot` call**. 0x17 so_catch.
Phases: none by hit points. The cycle is: nobody within 120 → conjure a Soul (0x17), then
club with it (7, range 170) or fire it (8, at an enemy 275–500 ahead); the breath spell (9)
every 600–900 ticks when someone is 120–350 ahead; four melee arcs otherwise.
Script-driven: no property; no script names the class (grep "minion", "beezabub": no hit).
Related classes: Soul (not in my task) receives states 0x1a–0x1f and 0x21 from here; Demon
treats Souls as enemies (see Demon).
Per-machine: (a) none found (scan and reading). Note the ignored `Creature_updateActive`
result: this boss's AI is not gated by the activity test. (b) draw 0x28625c: `Creature_draw`,
then the bow model when +0x3cc != 0; no store. (c) none.
Open: Soul states; parameter meanings of the spell constructor 0x1ff860 (its symbol note says
it also creates a LightEffect and starts a looping sound — that is where the first pass's
"makes a LightEffect" comes from; Minion_run itself creates none).

---

#### GnawSpawn  (factory name `GnawSpawner`, string ref 0x15ac00; vtable 0x514ef0; size 0x3e0)

Functions: ctor 0x267cf4, run 0x268070, draw 0x268000, takeDamage 0x268c40 (bare tail call of
`Creature_takeDamage`), setState 0x268c5c. Two helpers lie just past the range: 0x268f38
(count of empty child handles, 0 once all three pods are gone; callers in run and setState)
and 0x268f80 (store an object in the first empty child handle; caller in run). Destructor
0x3caa8c (outside).
Constructor: `Creature_ctor(10, this, name, pos, angle, classDef 0x5000e8, props)`; six child
handles +0x3c8..+0x3dc zeroed; radius 30; +0x28 = 0x30; turn rate 0.1; +0xb4 = 1; speed 0;
scale 0.75; cflags |= 0x200001000; +0xec = g_simFrame; +0xf4 = 0; +0xe8 = 0 and +0x220 =
`model_buildHideMask(model, 0)`; state 0 through setState; `obj_runEvery60`; nine
setDefEntryParams; `Creature_init`. No property read.
Class-definition entries: 3 attack_spit (unused by setState), 4–6 death_01..03, 7
death_final, 8/9 hit_reaction_01/02, 10 idle_01, 11–13 spawn_01..03, 14 spawn_321, 15 walk.
Fields: +0x3c8 handle[6] = the creatures it has spawned that still exist; +0xe8 (the model-
variant word) doubles as the "pods lost" mask, bits 0–2; +0xf4 = clock before which it does
not spawn again.

States (run 0x268070; usual head, applyKnockback(0.1)):
- 0: V25(0) → 5; away from home → 1. 1: V25(0) → 5; else moveToDest.
- 3 and 5 share one decision list (no target → 0):
  1. free child slots > 0 (helper 0x268f38) and clock > +0xf4 and
     `Creature_canSeeTargetIn(0, 360, 0, facing, 0x7fff, 0)` → 6;
  2. hit points < 0.8 × max and bit 0 of +0xe8 clear → 0x17;
  3. hit points < 0.6 × max and bit 1 clear → 0x18;
  4. hit points < 0.4 × max and bit 2 clear → 0x19;
  5. otherwise state 3 calls `Creature_fleeFromTarget(this, 0)` every frame (it walks away
     from its target), and state 5 goes to 3 when not rooted.
- 6 (spawn clip): while free slots > 0, each of events bits 0, 1, 2 triggers one spawn at
  model attach point 1, 2, 3 respectively: the point is pushed 24 further out from the
  spawner's centre; three `GutChunk` objects (`pool_new(0x268)` + ctor 0x201958 with (1.0,
  obj, point, 2, 3)); three `fx_spawn(9, point)`; then **`world_createObject("gnaw", point at
  the spawner's height, heading away from the centre, 0)`**; the new creature is stored in
  the first empty child handle, and when the spawner is charmed (+0x312 != 0) it gets
  `Creature_setCharm(child, −1, team of the spawner (V37))`. When animation flag 8 clears:
  +0xf4 = clock + 60 + own generator % 300 and → 3.
- 0x17 / 0x18 / 0x19 (clips death_01 / death_02 / death_03): `Creature_settle`; events bit 0:
  three GutChunk objects and three `fx_spawn(9)` at attach point 1 / 2 / 3; events bit 1:
  +0xe8 |= 1 / 2 / 4 and +0x220 is rebuilt (`model_buildHideMask`) so that pod disappears. →
  3 when animation flag 8 clears.
- 0x10: attack ready → 0; else flee. 0x12: animation flag 0x10 clear → 5 (setState starts the
  hit clip with flag 8, not 0x10, so this passes on the next frame). 0x13: not stunned → 3.
- 0x14: `Creature_deadUpdate(20, this, events, 0-vector, 0)`.
- 2, 4, 7–0xf, 0x11, 0x15, 0x16, unknown → setState(0).
setState (0x268c5c): 0, 5, 0x13 idle_01; 1 walk + wander point; 3 walk; 6: spawn_321 when no
pod is lost (+0xe8 == 0) and more than two child slots are free, otherwise one of the single
clips — spawn_03 when bit 0 is clear, spawn_02 when bit 0 is set and bit 1 clear, spawn_01
when both are set; 0x10 +0x318 = 60 then walk; 0x12: refused while the state is 0x17–0x19,
otherwise hit_reaction_01/02 by own generator & 1 (clip flag 8); 0x14 death_final and V28(0)
— **no `Creature_dropLoot` call**; 0x17–0x19 the three pod clips (flags 0x808).
Phases: three hit-point thresholds, 80 %, 60 %, 40 % of the maximum, each used once (mask in
+0xe8); with all three pods gone the helper reports no free slot and spawning stops for good.
At most six live children; 60–359 clock ticks between spawn clips.
Script-driven: no property; no script names the class (grep). The spawned type is the fixed
name `gnaw` through the factory.
Per-machine: (a) twelve `fx_spawn(9)` calls (cosmetic, camera-gated) in run; `GutChunk_ctor`
reads the local gore option 0x44fdc0 for one flag bit of the chunk (symbol note; the chunk is
created regardless — see the objects document for that option). Nothing else found (the scan +
reading). (b) draw 0x268000 is `Creature_draw(this, V16, V38, 0)` only. (c) none.
Open: which animation events each spawn clip raises (data, not code): the single clips are
chosen by the pod mask but the spawn point follows the event bit, so the pairing was not
verified. docs/monsters.md says "three Prop objects per spawn state": they are three
`GutChunk` objects (0x268 bytes), and the spawn state also creates the `gnaw` creature.

## 4. Ordinary monsters, by family

### Ants, Arenabeast, beetles, badgers, Agony, Amphian

*Reader's notes for this group.* Conventions: every statement is Observed at the address given unless marked Inferred / Unknown.
"own rand" = GameObject_rand(this) (object generator +0x44). "def+N" = handle in the class
definition block (+0x24), i.e. entry (N-4)/8 of the file list. "events" = bit mask returned by
Creature_stepAnim for this frame. Angles are 16-bit as written in the code.
"Event markers" are what the constructor passes to creature_setDefEntryParams (0x118378):
up to four (time, mask) pairs per clip, stored in the clip's event slots; the times are seconds
into the clip according to docs/engine.md (event slots), which is why values above 1.0 occur.
Whether the animation files add markers of their own was not checked for any class.
"No requester" means: no code in the class's own functions passes that state number to slot
27; it does not rule out a caller elsewhere unless the section says what was searched.
Soft-float helpers identified while reading (Observed from their bodies): 0x3af410 double add,
0x3af468 double subtract (flips the sign of operand 2, then the same add), 0x3af4d0 double
multiply; 0x3aef58 / 0x3afb90 are used as float->double / double->float around them (Inferred).

### Family: ants (Ant, AntQueen, AntWave)

#### Ant  (factory `AntTough`, `AntBlocker` exact -> "sant" model; `Ant*` prefix -> "ant" model; vtable 0x5111c0; size 0x3e8)

Functions: ctor 0x235418, draw 0x2359b0, run 0x2359fc, saveState 0x236648 (slot 9), loadState
0x236690 (slot 8), setState 0x236708, helper 0x236b0c (lose a body part + gib). takeDamage,
slot 3, slot 11 are the Creature base versions (vtab.py). Slot 15 (clone) is a class-specific
function outside this range (0x11f188), not read.

Constructor (0x235418; args this, pos, angle, arg4, typeName, sant flag):
- The first own-rand draw (0x235470) is taken BEFORE Creature_ctor runs, i.e. on the zero-filled
  pool block (pool_new memsets), so it is the same number every time; it only feeds the
  Creature_ctor hit-point argument `(rand % 14) + 4`, and Creature_ctor overwrites hit points
  through Creature_setStats whenever a type name is passed (0x10a1e8-0x10a208). No effect seen.
- Class definition: 0x4fe9c0 (`ant.lmp`) or 0x4fea68 (`sant.lmp`) when the sant flag is set. Same
  entry layout in both: 4/5 attack1/2, 6-8 death1-3, 9 hit_reaction, 10-12 idle_a/b/c, 13 walk,
  14 spit, 15-17 projectile vif/tex/anm, 18 spel_ant_spit, 19 spel_ant_spit_hit.
- speed +0xb8 = 140, turn rate +0xb0 = 1.2, radius +0x1c = 18, +0x28 = 0x14, +0xb4 = 0x12,
  state 0, cflags |= 0x8000001000, +0xec = g_simFrame.
- Properties: `Color` (int) -> +0x3c8; `Type` (int) -> +0x3d0. Then type-name prefixes override
  both: `antblack` -> colour 1; `antdroneblack` -> colour 1, type 1; `antdrone` -> colour 0,
  type 1; `antblocker` -> colour 0, type 2 (0x235560-0x2355ec).
- sant model: scale +0xdc 1.47, radius 20, colour forced 0, own rand & 1 sets model-variant bit 1
  (+0xe8); type 2: radius 25, scale 1.6.
- ant model: type 1 -> scale 1.1 and variant bit 1; otherwise scale = 0.75 + (own rand % 6) x 0.05.
  +0x5c (first resistance slot) = 0.2 for colour 0, 0.3 for colour 1.
- Elemental variant +0x3e0 (only type 0): own rand / 65536 < 0.15 -> +0x3e0 = (own rand & 1) + 1.
  1 -> tint preset +0xa0 = 2, 2 -> tint preset 4 (0x2357a0-0x235800).
- radius x= scale; +0x220 = model_buildHideMask(model, +0xe8); idle_a pushed; obj_runEvery60.
- Animation event markers (creature_setDefEntryParams): attack1 event 1 at 0.3, attack2 event 1
  at 0.7, spit event 1 at 0.3, death1-3 event 0x80 at 0.5. Then Creature_init.
- No Creature_setStats / Creature_scaleStats call of its own (base ctor only).

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | u8 | colour (1 = black texture def+0x1c, else def+0x14) | draw 0x2359b0, 0x236b0c |
| +0x3cc | s32 | "this bite already hit" (cleared on entering 6, set on the hit event) | run state 6, setState 6 |
| +0x3d0 | u8 | type: 0 worker, 1 drone (spits, two attack animations), 2 blocker (never leaves its spot) | run, setState |
| +0x3d4 | float | corpse sink depth; added to z at the top of run and subtracted at the end while cflag 0x1000000 is set | run 0x235a28, 0x236600 |
| +0x3d8 | s32 | death animation has ended (sinking phase started) | run state 0x14 |
| +0x3dc | s32 | creature-clock value after which the drone may spit again | run state 3, setState 7 |
| +0x3e0 | s32 | elemental bite: 0 none, 1 fire, 2 poison (the only class field saved) | run state 6, save/load |
| +0xf4 | s32 | state 0: clock value at which it starts wandering; state 6: frames to wait after the bite animation; state 0x14: clock when the death animation ended | run |

States (run 0x2359fc; order: processDamage, Creature_run, updateActive (inactive returns),
stepAnim(1.0), applyKnockback(0.5; 0 for type 2), V23 pickTarget(0), switch):
- 0 idle: V25(0) sees target -> 3; else Creature_isAwayFromHome -> 1; else when clock > +0xf4 -> 1.
- 1 wander: V25(0) -> 0; else Creature_moveToDest.
- 3 chase: no target -> 0. Target within 0-20 in arc 6000 of facing -> 6. Type 1 and clock >
  +0x3dc and target within 0-270 in arc 6000 -> 7. Otherwise: target within 20 in any direction
  (facing 0, arc 0x7fff) -> Creature_turnToTarget, else Creature_moveToTarget.
- 5: target within 0-20, arc 6000 -> 6; type 2 otherwise stays; others -> 3 once not rooted.
- 6 bite: with a target, on events bit 0: Creature_hitTargetAtReach(36, this, +0xd0, +0xd2,
  +0xd4, flags 8, descriptor) (hits the target if it is within 60 of the point 36 ahead).
  Descriptor: none for +0x3e0 == 0; +0x3e0 == 1 adds effect type 0x15 with v1 = N, v2 = N +
  (s16)(N x 0.2 x own rand / 65536), v3 = 0 where N = SKILL[13 FireWeapons] table offset 0x5c
  called with (0, (int)level global 0x4f714c, 0); +0x3e0 == 2 the same with SKILL[26
  PoisonWeapons] and type 0x17. Sets +0x3cc. Until the hit, types 0/1 keep turning to the
  target. Then +0xf4 counts down on frames where animation flag 8 is clear; at <= 0 -> 3.
  The <= 0 test runs every frame, also while the clip is still playing, and setState 6 seeds
  +0xf4 with own rand % 15: when that draw is 0 the ant requests state 3 on its first frame in
  6, before the hit marker (0x236008-0x236034; FireBeetle's copy of this logic seeds
  20-39 and cannot do this).
- 7 spit (drone): Creature_moveBy with a zero vector every frame. On events bit 0 with a target:
  one PoisonProjectile (pool 0xa8, ctor 0x2b153c) from 10 ahead, z+12; direction = bearing to the
  target clamped to facing +-4000, plus (own rand % 2000) - 1000; velocity 300 horizontal,
  vertical (own rand % 15) + 80; ctor float = 0.5 + 0.5 x own rand / 65536 (stored at projectile
  +0xa0); def entries 0xf, 0x10, 0x11, 0x13; stack args facing - 0x4000 and owner = this
  (0x236240-0x23624c). Plays sequence `spel_ant_spit.anm` on itself. The loop around it runs once.
  While animation flag 8: turn to target; afterwards -> 3.
- 0x10: Creature_isAttackReady -> 0, else Creature_fleeFromTarget.
- 0x12: wait for animation flag 0x10 to clear -> 3. 0x13: Creature_isNotStunned -> 0.
- 0x14 dead: cflag 0x1000000 clear: Creature_deadUpdate(15, this, events, zero, 0) only. Set
  (Generator-spawned ants, see Generator in docs/monsters.md): deadUpdate(.., 1); when animation
  flag 0x80 appears +0x3d8 = 1 and +0xf4 = clock; from 80 frames later, every frame: 3 particles
  (definition 0x8e2f18, positions/velocities by rejection sampling with own rand), +0x3d4 += 0.15,
  +0x3c = z - +0x3d4; 240 frames after the animation ended obj_delete.
- States 2, 4, 8-0xf, 0x11 are case labels that do nothing.

setState (0x236708), non-routine:
- Type 2: any request other than 0, 5, 6, 0x12, 0x14 becomes 5 (so a blocker never walks,
  chases, spits or backs off).
- 0: +0xf4 = clock + own rand % 120. 1/3/0x10: speed reset to 140, walk animation.
- 6: type 1 picks attack1 or attack2 with own rand & 1, others attack1; +0x3cc = 0;
  +0xf4 = own rand % 15.
- 7: +0x3dc = clock + 180 + own rand % 60.
- 0x12 requested while in 6 with the attack animation still playing (flag 8): stays in 6.
- 0x14: type 2 clears object flag bit 0 (+0xc); +0x3d8 = 0; own rand % 3 == 0 -> 0x236b0c(this,
  own rand & 7); Creature_dropLoot(36, 2, 1, 0.1, 1.2, 0.25, this, pos, facing, 0); death
  animation death1-3 by own rand % 3; V28(0).
- 0x236b0c (proposed Ant_loseBodyPart): sets model-variant bit (2 << n) in +0xe8, rebuilds
  +0x220, creates one GutChunk (pool 0x268, GutChunk_ctorFromProp 0x201ad0, scale 1.0, texture
  name by colour) and adds 2.0 to its +0x1c4.

Save/load: Creature_saveState / Creature_loadState, then 4 bytes: +0x3e0. Load also recomputes
the tint preset from it (0x236690).

Per-machine: (a) none found (the scan on 0x2359fc, 0x236708, 0x235418, 0x236b0c: no hits; body
read: every random decision uses own rand). (b) Ant_draw stores nothing (two Creature_draw
calls chosen by +0x3c8). (c) no.
Observed oddity (not a per-machine issue): the two early exits of run (Creature_run non-zero at
0x235a64, inactive at 0x235a74) jump past the "z -= +0x3d4" at 0x236610, so on such a frame a
sinking corpse (cflag 0x1000000, +0x3d4 > 0) keeps the z that was raised at 0x235a38. Whether
that is ever visible depends on Creature_run / Creature_updateActive for corpses (not read).
Open: object flag bit 0 cleared for dead blockers — meaning of the bit not read here.

#### AntQueen  (factory `AntQueen`; vtable 0x511078; size 0x3e8)

Functions: ctor 0x236c70, draw 0x236f10, run 0x236f78, slot 3 0x2378f4 (empty), takeDamage
0x2378fc (plain jump to Creature_takeDamage), setState 0x237918, helpers 0x238150 (pick fly
destination), 0x238448 (update banking), 0x2385dc (fade banking tracks out), 0x238360 (gib
spawner, no caller). Save/load are the Creature base versions.

Constructor (0x236c70): class definition 0x4feb10 (`antqueen.lmp`: 3 attack1, 4-6
attack2_center/left/right, 7-9 fly/fly_left/fly_right, 10-13 hit_back/front/left/right,
14 hover, 15-17 idle_a/b/c, 18 landing, 19 sting, 20 takeoff, 21-23 walk/walk_left/walk_right,
24 death). Hit-point argument: same pre-constructor own-rand draw as Ant (overwritten by the
base). Turn rate 1.2, radius 45, speed 140, +0x28 = 0x37, +0xb4 = 0x13, +0x5c = 0.4, cflags |=
0x8020001000, +0x3d4 = 180, +0x3d8 = clock + 180 + own rand % 180, variant bits 0, idle_a,
obj_runEvery60. Event markers: attack1 event 1 at 0.2; attack2 x3 event 1 at 0.3; sting event 1
at 0.2. Creature_init. No property read by the class itself.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3cc | s32 | bite/sting has hit (cleared by setState 6, 9, 10) | run state 6 |
| +0x3d4 | s32 | flight timer (creature-clock value): on the ground, take-off allowed after it; in 8, flying chase lasts until it; in 0x17, moving to the fly destination lasts until it | run 3, 8, 0x17; setState 8, 0x17, 0x18 |
| +0x3d8 | s32 | written by the ctor and setState 0x19 only; never read in 0x236c70-0x238654 | field search by disassembly |
| +0x3dc, +0x3e0 | float | banking spring: velocity and value | 0x238448 |
| +0x3e4 | s16 | banking angle = (s16)(2 x +0x3e0 x 2177); subtracted from the facing while drawing | 0x238448, draw |
| +0xf4 | s32 | state 0: wander time; state 0x19: end time | run |

States (run 0x236f78: processDamage, Creature_run, updateActive (result NOT tested), stepAnim
(1.0), applyKnockback(0.5), V23(0), switch). "queue < 4" = animation count +0x118 below 4.
- 0 idle (calls 0x2385dc): V25(0) and queue < 4 -> 3; otherwise when clock > +0xf4 -> 1.
- 1 wander (0x238448): V25(0) -> 3; else Creature_moveToDest.
- 3 ground chase (0x238448): no target -> 0. One own-rand draw per frame: (rand & 3) == 0 ->
  creature_findEnemyInCone(0, 40, this, facing - 0x7fff, 6000) non-null -> 7 (rear attack);
  otherwise Creature_canSeeTargetIn(0, 20, 0, this, facing, 6000, 0) -> 6 (bite). If neither:
  Creature_moveToTarget, and when clock > +0x3d4 and queue < 4 -> 8 (take off).
- 5: one own-rand draw: same two tests as 3 (rear cone when (rand & 3) == 0, else front bite);
  otherwise -> 3 once not rooted.
- 6 bite (0x2385dc): on events bit 0 with a target: Creature_hitTargetAtReach(36, this, +0xd0,
  +0xd2, +0xd4, flags 0x40008, no descriptor); sets +0x3cc; turns to the target until the hit;
  animation flag 8 clear -> 3.
- 7 rear attack (0x2385dc): on events bit 0 (no target test): descriptor with effect type 0x17,
  v1 = v2 = SKILL[26 PoisonWeapons] offset 0x5c (0, (int)level global, 0), v3 = 0;
  Creature_hitTargetOrPlayerInArc(0, 40, this, facing + 0x7fff, 3000, +0xd0, +0xd2, +0xd4,
  0x40008, descriptor). Flag 8 clear -> 3.
- 8 flying chase (0x238448): no target -> 0. While clock <= +0x3d4: after the take-off animation
  (flag 8 clear): target within 0-20 in arc 6000 -> V27(9) and, with own rand % 3 == 0, +0x3d4 = 0;
  else within 20 any direction -> turn, else Creature_moveToTarget. Clock > +0x3d4 -> 0x17.
- 9 / 10 sting (0x2385dc): with a target, on events bit 0: the same poison descriptor, then
  Creature_hitTargetAtReach(40, this, +0xd0, +0xd2, +0xd4, flags 0x10004, descriptor); turns to
  the target every frame. Flag 8 clear: 9 -> 8, 10 -> 0x17.
- 0x12 (0x2385dc): animation flag 0x10 clear and queue < 4 -> 3. 0x13: not stunned -> 0.
- 0x14 (0x2385dc): Creature_deadUpdate(30, this, events, zero, 0).
- 0x17 fly to a point (0x238448): no target -> 0. While clock <= +0x3d4 (after flag 8 clears):
  Creature_moveTo(this, +0x104); arrival, or failed-search count +0x2c4 >= 31, sets +0x3d4 = 0.
  After that: turn to target; Creature_canSeeTargetIn(0, 500, 0, this, facing, 3000, 0) -> 0x18.
- 0x18 landing (0x2385dc): flag 8 clear and queue < 4 -> 3.
- 0x19 (0x2385dc): with a target, on the single frame where clock == +0xf4 - 120: creates an
  AntWave (pool 0x3d8, ctor 0x238654) with (target object, position = own position + (radius +
  10) ahead, facing, lifetime 600). Clock > +0xf4 and queue < 4 -> 3.
- 2, 4, 0xb-0x11, 0x15, 0x16: run returns without doing anything. Note 0x10 is among them: an
  AntQueen that the common filter redirects to 0x10 (attack cooldown +0x318 running) has no
  handler for it. What takes it out again was not traced (Open).

**State 0x19 and state 10 have no requester.** Observed: no instruction in 0x236c70-0x238654
passes 0x19 or 10 as the slot-27 argument (the run function requests only 0, 1, 3, 6, 7, 8, 9,
0x17, 0x18); +0x3d8, which setState 0x19 re-arms, is never read. A text search of every
decompiled function for a slot-27 call with literal 0x19 finds two, both on their own object
(0x256024 and VampireLord_takeDamage 0x2b93d8). docs/script.md lists no built-in that sets an
arbitrary AI state. Inferred: the AntWave attack is unreachable in this build (slot-27 calls
with a variable argument in other classes were not all traced). This matters for
docs/monsters.md 7.5: AntWave_ctor's only caller is this state (xref 0x2376a8).

setState (0x237918), non-routine:
- 0: +0xf4 = clock + own rand % 120. 1: speed 140.
- 3: unless coming from 0x12, 6 or 7: speed 140 and the three walk tracks (walk, walk_left,
  walk_right). Always: activity radius +0x3c4 = 44000.
- 7: only with a target: looks for the enemy in the rear cone again and picks attack2_center,
  _left (bearing from the tail < -2000) or _right (> 2000). Without a target no animation
  starts but the state is still stored.
- 8: speed 240. From 0x17 or 9: nothing else. Otherwise +0x3d4 = clock + 300 + own rand % 180,
  the three fly tracks and the takeoff animation.
- 9 / 10: sting animation, +0x3cc = 0. 6: attack1, +0x3cc = 0.
- 0x12: ignored (state unchanged) while in 8, 0x17 or 9; ignored while a bite animation is still
  playing in 6; otherwise one of four hit animations chosen by the hit angle +0x2e0.
- 0x14: Creature_dropLoot(36, 2, 5, 1, 5, 1, this, pos, facing, 0); death animation; when no fly
  track is active the takeoff animation is blended in as well; V28(0).
- 0x17: +0x3d4 = clock + 180 + own rand % 120; speed 240; +0x104 = result of 0x238150; unless
  coming from 8 or 9, the fly tracks and takeoff animation.
- 0x18: +0x3d4 = clock + 180 + own rand % 180; idle_b + landing animation.
- 0x19: +0x3d8 = clock + 180 + own rand % 180; idle_b + idle_c; +0xf4 = clock + 120 + own rand % 60.

Helpers:
- 0x238150 (proposed AntQueen_pickFlyDest): up to 10 tries: own-rand angle, point at 300-600
  (two separate own-rand draws for x and y distance) from the target; accepts it when
  terrain_height(radius) at the point 150 behind it (along facing - 0x7fff) is within 12 of the
  queen's z. Falls back to the queen's own position; also when there is no target.
- 0x238448 (AntQueen_updateBank): target = angular velocity +0x110 / 512 clamped to +-1; spring
  +0x3dc += (target - +0x3e0) x 0.09, +0x3e0 += +0x3dc, +0x3dc x= 0.04; +0x3e4 from +0x3e0; sets
  the weight of the left (walk_left / fly_left) or right track to |2 x +0x3e0| and the other to 0.
- 0x2385dc (AntQueen_fadeBankTracks): gives those four tracks a weight change of -1/30 per frame.
- 0x238360: rebuilds the hide mask and creates one GutChunk like Ant's 0x236b0c, without
  setting a part bit. No call and no data pointer to it found (xref, ptrs): dead code.

Phases: none by hit points. The ground/air cycle is driven by +0x3d4 only.
Script-driven: nothing found in scripts/*.txt for this type name.
Per-machine: (a) none found (the scan on run, setState, ctor and the three helpers: no hits; all
random decisions use own rand). (b) **First-pass open question answered:** AntQueen_draw
subtracts +0x3e4 from the facing +0x38 at 0x236f50, calls Creature_draw, then adds +0x3e4 back
at 0x236f64 (16-bit wrap-around arithmetic, both operands re-read from the object). It is
undone before return, provided Creature_draw changes neither field. It also sets the draw
parameter 0x41c14c to 2.0 (0x1797c8) and restores draw state (model_resetDrawState). +0x3e4
itself is written only by run code (0x238448). (c) no.

#### AntWave — constructor only (run 0x238938 / draw 0x2387d0 documented in the first pass)

ctor 0x238654 (this, target object, pos, facing, lifetime): Creature_ctor with hit-point
argument 10000, no type name and no class definition; turn rate 0.6, speed 100, radius = target
radius + 10; vtable 0x50d298; +0x3c8 = clock at birth, +0x3cc = clock + lifetime; +0x3d0 = handle
to the target (handle_link); object flag |= 1; obj_runEveryFrame. Size 0x3d8 (pool_new argument
at 0x237668). dtor 0x238750 (already named). Slot 27 is the bare Creature version (vtab.py).
Only caller: AntQueen_run state 0x19 (see above: no requester found for that state).

Static initialiser of the ant translation unit: stub 0x238b98 (pointer in the constructor
table at 0x3e99f8) calls 0x238a8c(1, 0xffff), which constructs two particle definitions:
0x8e2f18 (used by Ant_run's corpse-sink particles at 0x236524) and 0x4febe0 (used by
AntWave_draw at 0x2388c8).

#### Arenabeast  (factory `Arenabeast`; vtable 0x512ee8; size 0x3d8)

Functions: ctor 0x238bb8, draw 0x238f18, run 0x238f5c, slot 3 0x239b9c (empty), takeDamage
0x239ba4 (plain jump to Creature_takeDamage), setState 0x239bc0, slot 11 touch list 0x23a028.

Constructor (0x238bb8): Creature_ctor hit-point argument 10; class definition 0x4fec30
(`a_beast.lmp`: 3 atak_left, 4 atak_ryt, 5 atakclo1, 6 atakclo2, 7 atakclo22, 8 atakclo3,
9 atakkill, 10-12 ataklng1-3, 13 death, 14-16 hitreact1-3, 17 idle1, 18 roar, 19 taunt, 20
walk). Radius 50, +0x29 = 0x50, +0x28 = 0x55, turn rate 0.6, **speed +0xb8 = 0 and never
written again by the class**, scale 1.0, +0x64 = 0.2, +0x6c = 0.3 (resistance slots 2 and 4),
cflags |= 0x220040000, +0xf4 = 0, +0xe0 = 0, idle1, obj_runEvery60. Event markers: entries
5-8 event 1 at 0.6; 10 event 1 at 0.5; 11 at 0.4; 12 at 0.5; 9 (atakkill) event 0x11 at 0.6;
3 and 4 (atak_left / atak_ryt) event 0x10 at 0.6 — no bit-0 marker; 13 (death) event 0x80 at
2.0. +0x3cc = clock + 300 + own rand % 300. Creature_init. No property read by the class.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | state number of the last attack started; several attacks are not chosen twice in a row | run states 3, 5; setState |
| +0x3cc | s32 | written by the ctor, setState 0x18 and run state 0x18; never read in 0x238bb8-0x23a100 | disassembly search |
| +0x3d0 | s32 | set on event bit 0x10 in states 0xd-0xf (cleared on entering them); closes the contact-damage window of state 0xd | run, slot 11 |
| +0x3d4 | s32 | "contact damage has landed" (cleared on entering 0xd-0xf) | slot 11 |
| +0xf4 | s32 | states 0/1: wander timing (clock value). Attack setStates store own rand % 20 there; not read by the attack states | run 0, 1 |

States (run 0x238f5c: processDamage, Creature_run, updateActive (result not tested), stepAnim
(1.0), applyKnockback(0), V23(0), then **Creature_moveBy(this, zero vector) every frame** before
the switch — this is what delivers the slot-11 touch list):
- 0: V25(0) -> 3; else away from home -> 1; else clock > +0xf4 -> 1.
- 1: V25(0) -> 3; else clock > +0xf4 -> 0; else Creature_moveToDest.
- 3 chase / choose (no target -> 0). First match wins; T = Creature_canSeeTargetIn on the
  target with lead 0.6, E = creature_findEnemyInCone (any enemy); "last" = +0x3c8:
  1. last != 0xd, T(0-20, facing, arc 4000) -> 0xd
  2. last != 0xe, T(0-20, facing + 0x4000, arc 0x2000) -> 0xe
  3. last != 0xf, T(0-20, facing - 0x4000, arc 0x2000) -> 0xf
  4. T(0-50, facing, 4000) -> 6;  5. T(0-150, facing, 2000) -> 0xc;  6. T(0-200, facing, 1000) -> 7
  7. last != 10, T(150-200, facing + 0x2000, 2000) -> 10;  8. last != 0xb, same at facing - 0x2000 -> 0xb
  9-11. the three tests of 1-3 again with E instead of T -> 0xd / 0xe / 0xf
  12. E(50-150, facing, 2000) -> 0xc;  13. E(150-200, facing, 1000) -> 7
  14. last != 8, E(0-150, facing + 0x60bf, 2000) -> 8;  15. last != 9, E(0-150, facing - 0x60c1, 2000) -> 9
  16. last != 10, E(150-200, facing + 0x2000, 4000) -> 10;  17. last != 0xb, E(150-200, facing - 0x2000, 4000) -> 0xb
  18. otherwise: target within 300 in any direction -> Creature_turnToTarget, else Creature_moveToTarget.
- 5 (with a target; without one -> 3 once not rooted): T(0-50, facing, 4000) -> 6; T(0-150,
  facing, 4000) -> 0xc; T(0-200, facing, 1000) -> 7; T(150-200, facing +- 0x2000, 4000) -> 10 /
  0xb; E(50-150, facing, 4000) -> 0xc; E(150-200, facing, 1000) -> 7; last != 8, E(0-150,
  facing + 0x60bf, 4000) -> 8; last != 9, E(0-150, facing - 0x60c1, 4000) -> 9; E(150-200,
  facing +- 0x2000, 4000) -> 10 / 0xb; else -> 3 once not rooted.
- 6, 0xc, 7 (front attacks): on events bit 0 Creature_hitTargetAtReach(reach, this, +0xd0, +0xd2,
  +0xd4, flags 8, no descriptor) with reach 36 / 150 / 200 (0x23988c, 0x2398b0, 0x2398d4).
- 8, 9, 10, 0xb (side / rear sweeps): on events bit 0 Creature_hitTargetOrPlayerInArc(minR, maxR,
  this, facing + offset, arc 4000, +0xd0, +0xd2, +0xd4, flags 8, none): 8: 0-150 at +0x60bf;
  9: 0-150 at -0x60c1; 10: 150-200 at +0x2000; 0xb: 150-200 at -0x2000.
- 0xd, 0xe, 0xf: on events bit 0 Creature_hitTargetAtReach(150, ..., flags 8, none); on events
  bit 0x10 +0x3d0 = 1. (By the ctor's markers only atakkill, state 0xd, raises bit 0.)
- All attack states: animation flag 8 clear -> 3.
- 0x10: attack ready -> 0, else Creature_fleeFromTarget. 0x12: flag 0x10 clear -> 0. 0x13: not
  stunned -> 0. 0x14: Creature_deadUpdate(40, this, events, zero, 0).
- 0x17: flag 0x10 clear -> 3. 0x18: flag 0x10 clear -> V27(3) and +0x3cc = clock + 600 + own rand % 300.

setState (0x239bc0), non-routine:
- 0: +0xf4 = clock + own rand % 120. 1: +0xf4 = clock + 300 + own rand % 120, walk animation.
- 3 / 0x10: walk animation restarted unless coming from 3, 6, 0xc, 8 or 9.
- Attack animations: 6 atakclo22, 8 atakclo3, 9 atakclo1, 0xc atakclo2, 7 ataklng2, 10 ataklng3,
  0xb ataklng1, 0xd atakkill, 0xe atak_left, 0xf atak_ryt. Each stores the state in +0x3c8 and
  draws own rand % 20 into +0xf4; 0xd-0xf also clear +0x3d0 and +0x3d4.
- **0x12 is refused**: the request is replaced by the current state, so the beast has no hit
  reaction (the three hitreact animations are not referenced).
- 0x14: Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25, this, pos, facing, 0), death animation, V28(0).
- 0x17: roar animation. 0x18: taunt animation, +0x3cc = clock + 300 + own rand % 300.
- States 0x17 and 0x18 have no requester in the class (run requests 0, 1, 3, 6-0xf only;
  ScriptGenerator_spawn 0x265fc4 sends 0x17 only to Skeleton objects), and +0x3cc is never read:
  roar and taunt look unused. Inferred from those searches; variable-argument slot-27 calls in
  other classes not traced.

Slot 11, touch list (0x23a028, proposed Arenabeast_onTouchList): acts in state 0xd while
+0x3d4 == 0 and +0x3d0 == 0 (i.e. until the first contact hit or the 0x10 marker), and in
states 0xe / 0xf on every call with no once-only test. For each touched object with object flag
0x20: damage_apply(+0xd0, +0xd2, victim, this, attack rating 100000, 0, 0, flags 0x100041, no
descriptor, 0); sets +0x3d4.

Slot 3 (0x239b9c) is empty: the Creature trigger behaviour (dialog script) is switched off.
Script-driven: scripts/NITBON2.txt creates it with generateMonster('bossGen', 'ArenaBeast').
Phases: none.
Per-machine: (a) none found (the scan on run, setState, slot 11, ctor: no hits; all random draws
are own rand). (b) Arenabeast_draw stores nothing into the object; it sets the draw parameter
0x41c14c to 5.0 and calls Creature_draw (no model_resetDrawState call here). (c) no.
Open: what cflag 0x200000000 means; whether the animation files add markers of their own.

Three functions after Arenabeast (0x23a100, 0x23a200, 0x23a2b4) are not Arenabeast code. They
work on a raw property list (zero-terminated array of `key=value` strings):
- 0x23a100 (list, key, nth): lower-cases the key in place, finds the nth entry whose text
  starts with the key followed by '=', returns libc_atoi of the value, else 0. Same job as
  obj_getPropInt but on the list pointer. Callers: 0x23a200, 0x23a2b4, AutoEmitter_ctor
  0x240dc8, AutoPropLP_ctor 0x2416c4.
- 0x23a200 (list, n): true when `ParticleEmitter<n>`, `DynamicLight<n>` or `Halo<n>` is non-zero.
- 0x23a2b4 (list): true when `ParticleEmitter`, `DynamicLight`, `Halo` or any indexed form for
  n = 0..3 is non-zero. Called three times by the object factory (0x15d6e4, 0x15d76c, 0x15d7f4)
  to choose between a plain prop class and its light/particle variant (different pool sizes
  and constructors on the two branches).

### Family: beetles (FireBeetle, FireFly, beetleProjectile)

#### FireBeetle  (factory `BBeetle` -> variant 2, `LBeetle` -> variant 1, `FireBeetle*` prefix -> variant 0; vtable 0x510a10; size 0x430)

Functions: ctor 0x24587c, draw 0x245c8c, run 0x245f54, setState 0x2469d0, slot 11 touch list
0x246fe8, helper 0x247130 (lose a body part + gib). takeDamage, slot 3, save/load: Creature base.

Constructor (0x24587c; last argument = variant): class definition 0x4fee80 + variant x 0x98
(`beetle.lmp` / `lbeetle.lmp` / `bbeetle.lmp`, same entries: 3 attack1, 4-7 death1-4, 8 fly,
9 hitreact, 10 idle1a, 11 idle1b, 12 idle2, 13 landing, 14 takeoff, 15 walk, 16
spel_beetle_spit, 17 spel_beetle_spit_hit). Hit-point argument (pre-constructor own rand % 6)
+ 8, overwritten by the base as for Ant. Embedded damage descriptor at +0x3e8 initialised empty
(effect slots at +0x40c). Speed 180, turn rate 20, radius 12 x scale, +0xb4 = 0x12, +0x5c = 1.0,
+0x60 = -0.25 (resistance slots 0, 1), cflags |= 0x8000001000, +0x3cc = 0. Scale +0xdc = 0.8 +
(own rand % 6) x 0.05. idle1a pushed, then anim_randomizeTopTime (start phase from the cosmetic
seed; already listed as docs/engine.md P4). Own rand / 65536 < 0.1 -> the embedded descriptor
gets effect type 0x15: v1 = N, v2 = N + (s16)(N x 0.2 x own rand / 65536), v3 = 0, N =
SKILL[13 FireWeapons] offset 0x5c (0, (int)level global, 0). obj_runEvery60. Event markers:
attack1 event 1 at 0.3; death1-3 event 0x80 at 0.5 (death4 none). Variant bit 1 set in +0xe8,
hide mask rebuilt, Creature_init. No property read by the class itself.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | clock value at which the flight (state 0x17) ends | run 0x17; setState 0x17 |
| +0x3cc | s32 | clock value after which it may spit again | run 3, 5; setState 7 |
| +0x3d0 | s32 | zig-zag phase: 1 = heading for the side point, 0 = direct | run head, run 3 |
| +0x3d4 | s32 | clock value of the next phase toggle | run head |
| +0x3d8 | Vec3 | side point (100 units at facing +-0x2000) | run 3 |
| +0x3e8 | 0x44 bytes | damage descriptor passed with the bite (optional fire effect) | run 6 |
| +0xec | s32 | re-stamped with g_simFrame when a spit starts; the draw function times the glow from it | run 3, 5; draw |
| +0xf4 | s32 | state 0: clock value to start wandering; states 6, 7: frames to wait after the animation | run |

States (run 0x245f54: processDamage, Creature_run, updateActive (inactive returns), stepAnim
(1.0), applyKnockback(0.4), V23(0)). Before the switch, in every state: when clock > +0x3d4 the
phase +0x3d0 toggles; entering phase 1 takes one own-rand bit for the side (facing + 0x2000 or
- 0x2000), stores the side point and lasts 10 frames; phase 0 lasts 15.
- 0: V25(0) -> 3; away from home -> 1; clock > +0xf4 -> 1.
- 1: V25(0) -> 3; else Creature_moveToDest.
- 3 chase: no target -> 0. Target within 0-20, arc 4000 -> 6. Spit: clock > +0x3cc, target NOT
  within 100 (arc 0x7fff) and within 0-400 in arc 3000 -> V27(7), +0xec = g_simFrame, and a
  LightEffect (pool 0xbc, ctor 0x201bd8; colour 255,155,0,-96 fading to 0; first stack float 180,
  last 1.5; at z + 36; owner this). Take off: target not within 200 (any direction) and within
  0-400 in arc 8000 -> 0x17. Otherwise: within 20 any direction -> turn; else phase 1 ->
  Creature_moveTo(side point), phase 0 -> Creature_moveToTarget.
- 5: bite test and spit test as in 3; else -> 3 once not rooted.
- 6 bite: on events bit 0 with a target: Creature_hitTargetAtReach(50, this, +0xd0, +0xd2, +0xd4,
  flags 8, descriptor this + 0x3e8). Turns to the target while animation flag 8 is set; then
  +0xf4 counts down; <= 0 -> 3.
- 7 spit: on events bit 0 with a target: aim point from Creature_leadTargetPoint (float argument
  300 still in the register, 0x2466a4-0x2466d0); bearing to it clamped to facing +-4000, plus
  (own rand % 1000) - 500; velocity 300 horizontal, vertical = ((own rand % 50) + 200) x distance
  to the aim point / 300. Creates a beetleProjectile (pool 0x1d0, ctor 0x247884) from 10 ahead,
  z + 5, with facing - 0x4000, owner this, damage +0xd0 / +0xd2, and on the stack 0, +0xd4 and
  the sound handle def+0x8c (0x246868-0x24689c). Plays def+0x84 on itself. Turn / countdown /
  -> 3 as in 6.
- 0x10: attack ready -> 0 else flee. 0x12: animation flag 8 (not 0x10) clear -> 3. 0x13 -> 0.
- 0x14: Creature_deadUpdate(30, this, events, zero, 0).
- 0x17 flying: no target -> 1; clock < +0x3c8 -> Creature_moveToTarget; else -> 3.
- 2, 4, 8-0xf, 0x11, 0x15, 0x16: nothing.

setState (0x2469d0), non-routine:
- 0: +0xf4 = clock + 120 + own rand % 60. 1 / 3 / 0x10: speed 160; when coming from 0x17, cflag
  0x100000 is cleared and the landing animation plays over walk.
- 6: +0xf4 = 20 + own rand % 20. 7: same animation as the bite (attack1 over idle2); +0x3cc =
  clock + 300; +0xf4 = 20 + own rand % 20.
- 0x12: ignored while stunned (0x13) and while a bite animation is playing in 6. Requested in
  0x17 (hit in the air): idle1a + landing animation, +0xf4 = clock + 120 + own rand % 60, and
  the state becomes 0 — cflag 0x100000 is not cleared on this path (0x246dac-0x246e5c has no
  access to +0xa8; the clears of cases 1 / 3 / 0x10 are at 0x246ab0, 0x246b54, 0x246d48). Otherwise hitreact with animation flag 0x10 (the run state waits
  on flag 8).
- 0x14: own rand % 3 == 0 -> part = own rand % 6 + 2 with 5 -> 4 and 7 -> 6, 0x247130(this,
  part) (sets variant bit 1 << (part - 1), creates a GutChunk as Ant's helper does);
  Creature_dropLoot(36, 2, 2.8, 0, 1, 0.25, this, pos, facing, `fire_beetle_eye`); death1-4 by
  own rand & 3; when object flag 2 is set the animation is jumped to its end; V28(0).
- 0x17: cflag |= 0x100000, speed 180, +0x3c8 = clock + 120, fly + takeoff animation.

Slot 11, touch list (0x246fe8, proposed FireBeetle_onTouchList): only in state 0x17 (else the
empty Creature version). For each touched object whose dynamic class differs from this
object's own class (type-info compare, 0x3b1250): calls the object's slot 2 directly —
takeDamage(amount (own rand & 7) + 4, attacker this, flags 0x40001), i.e. without damage_apply
— and notes whether it lacked object flag 4. With a target and at least one such object
lacking flag 4: V27(3) (lands). One own-rand draw per touched object.

Per-machine: (a) run / setState / slot 11 / helper: none found (the scan, body read). The
constructor's anim_randomizeTopTime uses the cosmetic seed (0x16d0b8; known, engine.md P4). (b)
**First-pass open question answered:** FireBeetle_draw copies the 12-byte position to the stack
at 0x245cbc-0x245ccc, in state 0x17 adds a wobble (3 x cos, 3 x sin, 5 x cos of clock x 1500)
to +0x10/+0x14/+0x18, draws, and copies the saved position back at 0x245f1c-0x245f34 on its only
exit path. Undone. In state 7 it also draws a camera-gated glow (0x1f5890, strength by
g_simFrame - +0xec: 0.25 below 16 frames, 1.0 below 41, then 0.25) and adds the colour bias
+0x70 to the object ambient; neither stores into the object. (c) no.
Open: stack floats 2 and 3 of the LightEffect call; meaning of object flag 4 on touched objects.

#### FireFly  (factory `FireFly`; vtable 0x5108c8; size 0x470; derived from FireBeetle)

Functions: ctor 0x24726c, draw 0x24742c, run 0x247670, setState 0x24787c (empty). Slot 11 is
its own empty function in the runtime area (0x3c4178), so the beetle touch damage does not apply.

Constructor (0x24726c): calls FireBeetle_ctor with variant 0 (all of the beetle's own-rand
draws and its Creature_init happen), then: vtable; a light node at +0x430 (position +0x460,
linked with light_link); turn rate 20, radius 12, speed 160, state 1 stored directly, +0xf4 =
360, scale 0.5, cflags |= 0x101000; fly animation + anim_randomizeTopTime (cosmetic seed, as
above); obj_runEvery60 and Creature_init a second time (so an `initScript` property would run
twice — Observed call structure; no level use checked).

run (0x247670): processDamage, Creature_run (non-zero returns), updateActive (result ignored),
stepAnim(1.0) (result ignored), applyKnockback(1.0). No target picking and no state switch.
Zig-zag as the beetle but with periods 20 (side) / 30 (direct). Phase 0: Creature_moveTo(wander
destination +0x104); phase 1: Creature_moveTo(side point). On arrival or when clock > +0xf4:
Creature_clearPath, Creature_pickWanderDest, +0xf4 = clock + 300 + own rand % 3. Finally copies
the position to the light node (+0x460).
setState is an empty function: every request, including 0x14 from Creature_processDamage, is
discarded and +0x232 stays 1. The class has no attack and no death handling of its own. What
a FireFly at zero hit points does was not traced (Open).

Per-machine: (a) none found in run (the scan, body read); ctor as FireBeetle. (b) **Answered:**
FireFly_draw saves the position on entry, adds a wobble (10 x cos, 10 x sin, 10 x cos + 20 of
clock x 1000), temporarily offsets it again for one glow_add call and takes that offset back,
calls FireBeetle_draw, then restores the saved position at 0x247634-0x24764c. Undone. It reads
g_simFrame for the glow size; no other store. (c) no.

### Family: badgers (Badger, CastBadger)

Shared shape: speed +0xb8 = 0 (never written by either class; walking uses clips started with
flags 0x803), turn rate 1.0, +0xb4 = 3, cflags |= 0x200000000, attacks call Creature_settle
every frame, +0x3c8 = "this attack has hit", hit reaction refused while a front attack (state
6) is still playing, death clears object flag 1 (unless flag 2 is set) and sets it again on
animation event bit 2 (the 0x84 marker at the end of the death clip), slot 11 overridden by an
empty function.

The two functions before Badger_ctor are not badger code: stub 0x243ff8 (constructor table
0x3e9a00) calls 0x243ef8(1, 0xffff), which constructs particle definitions 0x8e3058 and
0x8e30a8; their only other references are in HateInto_run 0x242cd0 and HateGate_run 0x242edc.

#### Badger  (factory `SnoBadge` exact -> variant 1, `Badger*` prefix -> variant 0; vtable 0x510f30; size 0x3d0)

Functions: ctor 0x244018, draw 0x244320, run 0x244380, slot 11 0x244a9c (empty), setState
0x244aa4. takeDamage, slot 3, save/load: Creature base.

Constructor: Creature_ctor hit-point argument 10; class definition 0x4fecf8 + variant x 0xa0
(`badger.lmp` / `snobadge.lmp`: 2 gobdog.tex, 3 gobdog_b.tex, 4 atak_front, 5 atak_left, 6
atak_mid, 7 atak_right, 8 backup, 9 charge, 10 chargetak, 11-12 death1-2, 13-14 hit2left/right,
15 idle1, 16 roar, 17 walk). Variant 0: radius 35, +0x28 = 0x2d, +0xe0 = -15. Variant 1:
radius 25, +0x28 = 0x28, scale 0.8, +0xe0 = -10, +0x5c = -0.3, +0x60 = 1.0 (resistance slots 0,
1). +0x3cc (u8) = variant. idle1, obj_runEvery60. Event markers: entries 4-7 event 1 at 0.3 and
event 2 at 0.8; entry 10 event 1 at 0.5 and event 2 at 0.9; death1-2 event 0x84 at 1.0.
Creature_init. No property read by the class.

States (run 0x244380: processDamage, Creature_run, updateActive (inactive returns), stepAnim
(1.0), applyKnockback(0.2), V23(0)). T = Creature_canSeeTargetIn (lead 0), E =
creature_findEnemyInCone:
- 0: V25(0) -> 3; away from home -> 1; otherwise stays (no wander timer; the +0xf4 that setState
  0 writes is not read).
- 1: V25(0) -> 0; else Creature_moveToDest.
- 3 (no target -> 0), first match:
  1. T(0-60, facing, arc 7000) -> own rand % 5: 0 -> 8, 1 -> 9, else 6
  2. T(25-100, facing, 7000) -> 10
  3. T(0-60, facing + 8000, 3000) -> 8;  4. T(0-60, facing - 8000, 3000) -> 9
  5. E(0-25, facing, 7000) -> own rand % 5: 0 -> 8, 1 -> 9, else 6
  6. E(0-25, facing + 8000, 3000) -> 8;  7. E(0-25, facing - 8000, 3000) -> 9
  8. target within 20 any direction -> turn; else Creature_moveToTarget.
- 5: with a target: T(0-25, facing, 7000) or E(0-25, facing, 7000) -> 6; else -> 3 once not rooted.
- 6-10 attacks: on events bit 0: Creature_hitAllEnemiesInArc(0, radius + 25, this, facing, 7000,
  +0xd0, +0xd2, +0xd4, flags, none), +0x3c8 = 1. Flags: variant 1 always 8; variant 0 in states
  6, 7, 10: 0x80008 when own rand % 3 == 0 else 0x40008; variant 0 in 8, 9: 8. While the clip
  plays (flag 8) and the target is within 0-10 in arc 7000: turn to it (6 only before the hit;
  7 and 10 throughout). On events bit 1, in any state but 6, T(0-60, facing, 7000) -> V27(6)
  (chains into a front attack). Flag 8 clear -> 3.
- 0x10: attack ready -> 0 else flee. 0x12: flag 0x10 clear -> 3. 0x13 -> 0.
- 0x14: Creature_deadUpdate(35, this, events, zero, 0); events bit 2 -> object flag |= 1.

setState (0x244aa4), non-routine: 1: walk clip, or the charge clip while the charm timer +0x312
is non-zero. 3: charge clip unless coming from 3 or an attack. Clips: 6 atak_front, 7
chargetak, 8 atak_left, 9 atak_right, 10 atak_mid (8 and 9 with flags 0x4808, others 0x808);
all clear +0x3c8. 0x10: backup clip. 0x12: hit2left / hit2right by own rand & 1. 0x14:
Creature_dropLoot(36, 2, 2.8, 3, 3, 0.25, this, pos, facing, 0), death1 / death2 by own rand &
1, V28(0). State 7 (chargetak) has no requester in the run function. The roar clip is not
referenced.

Phases: draw only — below 25 % of maximum hit points Badger_draw uses the second texture
(def+0x1c instead of def+0x14).
Per-machine: (a) none found (the scan on run, setState, ctor; body read). (b) Badger_draw stores
nothing; it reads +0x228 / +0x22c. (c) no.

#### CastBadger  (factory `castbadger` with level 1; also created by SkillSummonBadger_cast 0x3106f4; vtable 0x513e08; size 0x3d0)

Functions: ctor 0x244e4c, draw 0x2450b0, run 0x2450d8, slot 11 0x245518 (empty), saveState
0x245520, loadState 0x245568, setState 0x245660.

Constructor (this, name, pos, angle, arg5, level): Creature_ctor hit-point argument 10; class
definition 0x4fee38 (`gooddog.lmp`: 3 atak_front, 4 charge, 5 hit2left, 6 death1, 7 idle1).
Radius 12, scale 0.5, +0xe0 = -7, idle1. +0x3cc = level. Then it swaps the global monster
level 0x4f714c for (float)level, looks up `castbadger` in the balance table (0x223a4c) and
calls Creature_setStats(..., rollHp = 1) again (a second hit-point roll: one more own-rand
draw), and restores the global. **obj_runEveryFrame** (not the staggered list). Event markers:
atak_front event 1 at 0.3 and event 2 at 0.8; death1 event 0x84 at 1.0. Creature_init; cflags
|= 0x8000000000000000. No property read by the class.
Context, read in the skills area only as far as the call: SkillSummonBadger_cast passes the
skill's value as level and afterwards sets object flags 0x4002 and cflag 0x1000000; for a
player caster also the followed slot +0x5a, cflag 0x400000, Creature_setCharm(-1, caster's
team), +0x3ac = 400 and HomeRange 500 (0x310940-0x3109c0).

States (run 0x2450d8; when Creature_updateActive says inactive: in state 0x14 the object gets
flags 0x4002 and obj_delete, otherwise just returns; then stepAnim(1.0), applyKnockback(0.2),
V23(0)):
- 0: V25(0) -> 3; away from home -> 1; else stays. 1: V25(0) -> 3; else Creature_moveToDest.
- 3: no target -> 0. T(0-12, facing, arc 9000) -> 5. Within 12 any direction -> turn. Else
  Creature_moveToTarget, and when the failed-search count +0x2c4 reaches 4 -> 1.
- 5: T(0-12, facing, 9000) or E(0-12, facing, 9000) -> 6; else -> 3 once not rooted.
- 6 bite: Creature_settle; on events bit 0: Creature_hitTargetInArc(0, 12, this, facing, 9000,
  +0xd0, +0xd2, +0xd4, flags, none) with flags 0x40008 when own rand % 3 == 0, else 8; +0x3c8 =
  1. Before the hit, while the clip plays and the target is in that arc: turn. Flag 8 clear -> 5.
- 0x10 / 0x12 / 0x13 / 0x14 as Badger (deadUpdate height 35; no loot call in setState 0x14).
setState (0x245660): 1, 3 and 0x10 all restart the charge clip; 6 atak_front; 0x12 hit2left
unless a bite is playing; 0x14 death1 and V28(0) — no Creature_dropLoot.
Save/load: Creature record + 4 bytes (+0x3cc). Load swaps the global level the same way and
calls Creature_setStats with rollHp = 0 (stats rescaled, hit points not re-rolled).
Per-machine: (a) none found (the scan on run, setState, ctor, loadState). The global 0x4f714c is
swapped and restored inside one call in run-side code. (b) draw is a plain Creature_draw. (c) no.

### Family: Agony and Amphian (same skeleton: hub state 5, three melee clips picked by own rand % 3, a block state that sets cflag 0x200)

Shared, Observed in both: speed +0xb8 = 0 and never written; +0x64 = 1.0; cflag 0x200000000;
+0xf4 = g_simFrame + 300 in the ctor (the frame counter, not the creature clock); the ctor
calls its own setState(0) directly, then obj_runEvery60; every setState call first clears
cflag 0x200; setState 0x10 stores 60 in the attack-cooldown timer +0x318 and plays the run
clip; any state number without a case becomes 0; the run function answers unknown states with
V27(0); loot call Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos, facing, 0); death
clip one of two by own rand & 1; no property read by the class.

#### Agony  (factory `AvatarAgony`; vtable 0x512c58; size 0x3d0)

Functions: ctor 0x23396c, draw 0x233b90, run 0x233bdc, setState 0x234168. Everything else base.
Constructor: hit-point argument 10; class definition 0x4fe888 (`A_Agony.lmp`: 3-5
aoa_attack1-3, 6 aoa_block, 7-8 aoa_death_02/03, 9-10 aoa_hit_reaction/2, 11
aoa_idle_aggressive, 12 aoa_idle_passive, 13 aoa_knockback, 14 aoa_run, 15 aoa_walk). Radius
30, +0x28 = 0x3c, +0xb4 = 1, turn rate 0.4, cflags |= 0x200001000. Event markers: attack1 event 1 at 0.6 and again at 1.1;
attack2 event 4 at 0.4; attack3 event 2 at 0.2, event 1 at 0.4 and at 1.1; deaths 0x80 at 0.5.
Field: +0x3c8 s32 = last action (6, 7, 8, 0x11 or 0x17), read in state 5.
States (run 0x233bdc: processDamage, Creature_run, updateActive (inactive returns), stepAnim
(1.0), applyKnockback(1.0), V23(0)); T = Creature_canSeeTargetIn, lead 0:
- 0: V25(0) -> 3; away from home -> 1; else stays. 1: V25(0) -> 3; else Creature_moveToDest.
- 3: no target -> 0. T(0-48, facing, arc 12000) -> 5. Else, if Creature_isTargetCharging and
  T(240-500, facing, 0x7fff) -> 0x17. Else T(0-48, any direction) -> turn; else Creature_moveToTarget.
- 5: T(0-48, facing, 12000): last action 0x17 -> 8; last action 0x11 -> 6; otherwise V27(6 + own
  rand % 3). Not in the arc: within 48 any direction -> turn; else -> 3 once not rooted.
- 6 / 7 / 8: turns to the target every frame. Creature_hitTargetInArc(0, 48, this, facing, 12000,
  +0xd0, +0xd2, +0xd4, flags, none) on events bit 0 with flags 8, on bit 1 with flags 1, on
  bit 2 with flags 0x40001. Animation flag 8 clear -> 3.
- 0x10: attack ready -> 0 else flee. 0x11 (block): clock > +0xf4 -> 3. 0x12: zero-vector
  Creature_moveBy; flag 0x10 clear -> 3. 0x13: not stunned -> 3. 0x14: zero-vector
  Creature_moveBy, Creature_deadUpdate(30, this, events, zero, 0).
- 0x17 (run-in): no target -> 0. T(0-12, facing, 12000) -> 5. If not within 0-48 in that arc
  but within 48 in any direction -> turn; else Creature_moveToTarget.
setState (0x234168): also resets the turn rate to 0.4 on every call. 0: +0xf4 = clock + own
rand % 120. 5: +0xf4 = clock + own rand % 360 (not read in state 5). 6-8: clip, +0x3c8 = state.
0x11: +0x3c8 = 0x11, cflag |= 0x200, block clip, +0xf4 = clock + 60 + own rand % 60. 0x12: clip
by the pending damage flags +0x2dc: any of 0x380000 -> aoa_knockback; else 0x40000 ->
aoa_hit_reaction; else aoa_hit_reaction2. 0x17: +0x3c8 = 0x17, turn rate 1.2, run clip.
State 0x11 (block) has no requester in the run function (it requests 0, 1, 3, 5, 6-8, 0x17).
Per-machine: (a) none found (the scan on run, setState, ctor; body read). (b) Agony_draw sets the
draw parameter 0x41c14c to 3.0, calls Creature_draw and model_resetDrawState; stores nothing
in the object. (c) no.

#### Amphian  (factory `Amphian`; vtable 0x512da0; size 0x3c8 — no class fields)

Functions: ctor 0x234584, draw 0x2347cc, run 0x23483c, setState 0x2350d0.
Constructor: hit-point argument 10; class definition 0x4fe910 (`amphian.lmp`: 3-5 attack_01-03,
6 block, 7-8 death_01/02, 9-10 hit_reaction_01/02, 11 idle_aggressive, 12 idle_passive, 13 run,
14 spit, 15 walk, 16-18 projectile vif/tex/anm, 19 spel_cyclops_spit, 20
spel_cyclops_spit_hit). Radius 25, +0xb4 = 9, +0xe0 = -12, turn rate 1.2, cflags |=
0x200040000. Event markers: attack_01 event 1 at 0.2; attack_02 event 1 at 0.6; attack_03
event 1 at 0.7 and event 2 at 1.2; spit event 1 at 0.45; deaths 0x80 at 0.2.
States (run 0x23483c; same head, applyKnockback(0.5); the model comes from slot 16):
- 0 / 1 as Agony.
- 3: no target -> 0. T(0-12, facing, arc 8000) -> 5. Target not charging and T(0-36, facing,
  8000) -> 5. Target not charging and within 36 in any direction -> turn. T(120-360, facing,
  2000) -> 9 (spit). Else Creature_moveToTarget.
- 5: T(0-36, facing, 8000): when hit points < 50 % of maximum, one own-rand draw and (rand & 3)
  == 0 -> 0x17 (block); otherwise V27(6 + own rand % 3). Not in the arc: within 36 any
  direction -> turn; T(120-360, facing, 2000) -> 9; else -> 3 once not rooted.
- 6 / 7 / 8: Creature_settle, turn to target; Creature_hitTargetInArc(0, 36, this, facing, 8000,
  +0xd0, +0xd2, +0xd4, flags, none): events bit 0 flags 8, bit 1 flags 0x40001. Flag 8 clear -> 5.
- 9 spit: Creature_settle, turn; on events bit 0: two PoisonProjectile objects (pool 0xa8, ctor
  0x2b153c) from model attach point 1 (fallback 10 ahead, z + 36); velocity = 300 x unit vector
  of (120 cos facing, 120 sin facing, 48) plus 48 x an own-rand point in the unit ball
  (rejection loop); ctor float 0.5 + 0.5 x own rand / 65536; def entries 0x10, 0x11, 0x12, 0x14;
  stack args facing - 0x4000 and owner this (0x234f54-0x234f58). Plays def+0x9c on itself.
  Flag 8 clear -> 5.
- 0x10: attack ready -> 0 else flee. 0x12: flag 0x10 clear -> 3. 0x13 -> 3. 0x14: zero-vector
  Creature_moveBy, Creature_deadUpdate(20, ...). 0x17 (block): clock > +0xf4 -> 5.
setState (0x2350d0): 3 and 0x10 use the run clip; 0x12 one of two hit clips by own rand & 1;
0x17: cflag |= 0x200, block clip, +0xf4 = clock + 60 + own rand % 120.
Phases: below half hit points each melee decision has a 1-in-4 chance of a block instead.
Per-machine: (a) none found (the scan on run, setState, ctor; body read). (b) Amphian_draw is
Creature_draw(this, slot 16 model, slot 38 second resource, 0); no store. (c) no.

### Bubo, FemaleDarkElf, Critter, Creep, Cyclops family, Clockwork

*Reader's notes for this group.* Method: every function listed was read in the Ghidra decompile; where the
decompile was doubtful the instructions were checked with `tools/dis.py` (said where). Arc
constants are quoted as the code writes them: `8000` and `4000` are DECIMAL (0x1f40, 0xfa0),
`0x7fff` is hex. "Event 0xNN" = that mask bit of the `Creature_stepAnim` result for this frame (0x1 is the
hit frame, "bit 0" in the conventions).
"Anim flag" = the word at +0x11a. Animation slots are quoted as class-definition offsets
(`def+0x..`). Weapon-holder calls are quoted by table offset; the Weapon1 bodies behind the
offsets used here were read: 0x0c = slot 1 (hand, part id: hand 1 on with that held part),
0x4c = slot 9 (hand, four colour bytes -> holder +0x60..+0x66), 0x5c = slot 11 (drop the held
part as a prop, `creature_dropHeldPartAsProp`), 0x84 = slot 16 (hand 1: `damageDesc_getElement`
of the holder descriptor, i.e. non-zero when the weapon already carries an element),
0x8c = slot 17 (hand 1: pointer to the damage descriptor at holder+0x50), 0x94 draw, 0xac update.

Event marks (applies to every class below). `creature_setDefEntryParams(t0..t3, this, n,
m0..m3)` (0x118378, body read) writes four (float, byte) pairs into class-definition
resource n, i.e. the resource whose pointer is at `def + 4 + 8n` (entry 4 = def+0x24, the
first clip). In every class read here the bytes are exactly the event bits the run function
tests while that clip plays (0x1 = hit frame, 0x2/0x4/0x8 = further marks, 0x80 = the mark the death
and combo code waits for), and the floats are the times at which they fire. So these calls
define the animation events per clip: Observed for the store, Inferred for "time -> event
bit" (`Creature_stepAnim` was not read). The pairs are stored in the shared clip resource,
not in the object. Unit of the time values not checked.

---

#### Bubo  (factory names `Bubonian*`; vtable 0x513fe0; size 0x470)

Functions: ctor 0x247fb0, run 0x248598, draw 0x2484c8, setState 0x2494c0, slot 12 0x249404,
slot 38 0x249a30. takeDamage, save/load, touch are the Creature base bodies (vtab.py).

Constructor (0x247fb0):
- `Creature_ctor(maxHp 10.0, this, typeName, pos, angle, classDef 0x4ff048 (lump
  `bubonian.lmp`), props)`. Radius +0x1c = 18, turn rate +0xb0 = 1.2, speed +0xb8 = 0,
  kind byte +0xb4 = 9, +0xec = g_simFrame, +0xf4 = g_simFrame + 300 (not read again in this
  class), cflags |= 0x200040000, +0x68 = 1.0 (the disease entry of the resistance array per
  docs/gameplay.md; Inferred meaning), state 0, `obj_runEvery60`. No `Creature_setStats` /
  `Creature_scaleStats` call in this constructor. No property is read here.
- The embedded Weapon1 holder is at +0x3c8 (pointer stored at +0x50); its damage descriptor
  is therefore at +0x418 (effect slots initialised to "none").
- The exact type name selects a sub-kind stored at +0x460 (case-insensitive compares):
  `bubonianshaman` -> 1, `bubonianarcher` -> 2, `buboniantough` -> 3, anything else -> 0.
  - shaman: holder slot 1 (hand 1, part 0x24); variant bits +0xe8 = 0x40; tint preset +0xa0 = 6.
  - archer: holder slot 1 (hand 1, part 0x1e); one `GameObject_rand`, odd -> variant bit 1.
  - tough: scale +0xdc = 1.4, radius 19; then as kind 0.
  - kind 0 and 3: `GameObject_rand` & 1 picks held part 0x20 or 0x22; a second draw sets the
    variant bits to `1 << (rand % 6)`.
- One more `GameObject_rand` & 1 -> +0x468 (texture/second-model choice, see slot 38).
  So the constructor consumes 1 (shaman), 2 (archer) or 3 (others) own-generator values.
- Event marks: entries 4-7 (melee clips def+0x24..+0x3c) 0x1 at 0.2, entry 5 also 0x1
  at 0.8 and 1.4 (three hits in that clip); 0x18 and 0x19 (cast clip def+0xc4, def+0xcc)
  0x1 at 0.2; 0x16 (archer clip def+0xb4) 0x1 at 0.6; death clips: entry 8 (def+0x44)
  0x80 at 1.9, entries 0xd and 0xe (def+0x6c, +0x74) 0x80 at 0.8. Then `Creature_init`.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | Weapon1 (up to +0x45f) | embedded weapon holder; descriptor at +0x418 | ctor, run states 6-9 |
| +0x460 | s8 | sub-kind 0 plain / 1 shaman / 2 archer / 3 tough | ctor; run states 3, 5; setState animation choice |
| +0x464 | s32 | creature-clock value (+0x300) after which the shaman may cast again; set to clock + 180 after every cast event | run states 3, 5, 0xb/0xc |
| +0x468 | u8 | 0/1 from the constructor's generator draw | slot 38 only |

Run head (0x248598): slot 16 model -> `Creature_processDamage`; `Creature_run`; returns when
`Creature_updateActive` is 0; holder update (0xac) with 0.5; `Creature_stepAnim(1.0)`;
`Creature_applyKnockback(1.0)`; slot 23 (0); the shaman also calls slot 24 (pick ally) every
frame.

States:
- 0 idle: if `g_levelName` equals `storm2` the creature does nothing while g_simFrame < 180
  (0x248618-0x24863c). Otherwise slot 25 (0): seen -> state 1; not seen and
  `Creature_isAwayFromHome(this,1)` -> state 1; else stay.
- 1: no target seen (slot 25) -> `Creature_moveToDest`. Seen: turn to target; when the target
  is within visualrange (+0x3ae) inside arc 8000 -> 3.
- 2, 4, 0xd, 0xe, 0xf, 0x11 and any unlisted state -> 0.
- 3 chase: no target -> 0.
  - kinds 0/3 (melee): target charging and within 6 (arc 8000) -> 9; not charging and within
    24 (arc 8000) -> 5; not charging and within 24 at any angle -> turn only; else
    `Creature_moveToTarget`.
  - kinds 1/2: target within 60 at any angle (facing 0, arc 0x7fff): shaman whose clock is
    past +0x464 and who has no DiseaseShield spell attached (`creature_findSpellByType` with
    the SpellDiseaseShield type-info) -> 0xc; otherwise -> 0x10. Target not within 60: within
    360 inside arc 4000 -> 5; within 360 at any angle -> turn only; else move to target.
- 5 choose:
  - kinds 0/3: within 24 inside arc 8000 -> state 6 + (`GameObject_rand` & 3), i.e. 6..9
    equally; within 24 at any angle -> turn; else when not rooted -> 3.
  - kinds 1/2: if the target is within 60 at any angle the code calls setState at once with
    0xc (shaman, clock past +0x464, no shield) or 0x10, AND THEN FALLS THROUGH (checked in the
    instructions, 0x248ac8/0x248ae8 -> 0x248af0) to the ranged test: target within 360 inside
    arc 4000 -> archer: 10; shaman: 0xb if the clock is past +0x464 (else nothing); not in
    that cone -> 3 when not rooted. Consequences (Inferred from the filter body 0x10a9c0,
    which turns every request into 0x10 while the cooldown +0x318 runs): after the 0x10 call
    the second request is redirected to 0x10 again; after the 0xc call the second request
    replaces it — by 0xb when the target is in the front cone, by 3 when it is not and the
    creature is not rooted. So from state 5 the shield state survives only for a rooted
    shaman whose target is outside the front cone; the normal route to 0xc is state 3.
- 6, 7, 8, 9 melee (animations def+0x24/+0x2c/+0x34/+0x3c): `Creature_settle`, turn to
  target; on event 0x1: `Creature_hitTargetInArc(0, 24, this, facing, 8000, +0xd0, +0xd2,
  +0xd4, flags 8, descriptor = holder slot 17 (hand 1))`. -> 5 when anim flag 8 clears.
- 10 archer shot (animation def+0xb4): on event 0x1: aim point = own position + 300 along
  the facing, replaced by `Creature_leadTargetPoint(400, this, &aim)`; muzzle = attach point 0
  of the model (start value position + 12 along facing, z + 48); heading =
  atan2 from muzzle to aim; velocity = 400 along the heading, vertical component =
  `(GameObject_rand % 40 + 80) * distance(own position, aim) * 0.0025`. `pool_new(0x98)` +
  `DiseaseProjectile_ctor(1.0, obj, muzzle, velocity, heading, this)`. -> 5 when anim flag 8
  clears.
- 0xb shaman cast / 0xc shaman shield (same animation def+0xc4): every frame holder slot 9
  (hand 1, 0xff, 0xff, 0, 0x19). On event 0x1, with `corpse = creature_findCorpseOfClass(360)`
  and `wounded = creature_findWoundedAlly(360)` both evaluated first:
  1. state 0xc: DiseaseShield (skill 5), table offset 0x14 (cast) with (slot 35 value, this,
     own position, facing); result linked with `creature_addSpell(this, ...)`.
  2. else if a corpse was found: the corpse's slot 32 (revive) is called with no skill.
  3. else if the ally handle +0x238 is set, the ally has no DiseaseBlade spell, the ally's
     weapon-holder slot 16 (hand 1) returns 0 and `Creature_canSeeAllyIn(0, 360, 0, this,
     facing, 0x7fff, 0)`: DiseaseBlade (skill 97), offset 0x14 with (slot 35 value, the ALLY as
     caster, ally position, own facing); linked to the ally with `creature_addSpell`.
  4. else if a wounded ally was found and it has no Healing spell attached: Healing (skill 55),
     offset 0x14 with (slot 35 value, the wounded ally as caster argument, the shaman's own
     position, facing); linked to the wounded ally.
  5. else DiseaseBolt (skill 4), offset 0x14 with (slot 35 value, this, own position raised by
     half of +0x20, facing + `Creature_angleToTarget`); the result is not linked.
  In all five cases +0x464 = clock + 180. -> 5 when anim flag 8 clears.
  No skill-table offset 0x0c (can-cast) is called anywhere in this class.
- 0x10: attack ready -> 0; else `Creature_fleeFromTarget(this, 0)`. setState 0x10 sets the
  cooldown +0x318 = 60.
- 0x12 hit reaction: while anim flag 0x10 is set and the clip has finished (flag 0x80): if the
  track def+0x6c is present and def+0x7c is not, push def+0x7c (flags 0x10) and chain def+0x4c
  (flags 3); else if def+0x74 is present and def+0x84 is not, push def+0x84 and chain def+0x4c.
  (Knock-down clip followed by a get-up clip: Inferred.) Flag 0x10 clear -> 5.
- 0x13: stun timer zero -> 3.
- 0x14 dead: when object flag 2 (+0xc) is clear and event 0x80 (clip ended) is set:
  `pool_new(0x1b0)` + `SpellDiseaseEffect_ctor(obj, 5, slot 35 value, this, this,
  skill-table entry 29 DiseaseEffect)`, then `creature_addSpell(this, obj)` — called even if
  the allocation returned 0 (0x249320-0x249360). Then `Creature_deadUpdate(20, this, events,
  zero vector, 0)`. The 0x80 bit is the mark the constructor puts at 1.9 / 0.8 in the three
  death clips; that a mark fires once per pass of a non-looping clip (hence one cloud per
  corpse) is Inferred.

setState (0x2494c0), non-routine cases: 0x10 sets +0x318 = 60. 0x12 draws two own-generator
values (which of two clip pairs; flags 0x14 = knock-down pair def+0x6c/+0x74, or blended
flinch def+0x5c/+0x64). 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos,
facing, 0)`, holder slot 11 (drops the held weapon as a prop), death clip by
`GameObject_rand % 3` (def+0x44, +0x74 or +0x6c), then slot 28 (0). Idle/walk/flee clips are
chosen per sub-kind. Requests 2, 4, 0xd-0xf, 0x11 and unknown numbers store state 0.

Slot 12 (0x249404) `(this, kind, Vec3 *pos, source)`: when kind == 0, the source's type-info
equals Bubo's and own state < 2: setState(1) and the wander destination +0x104 = pos. The
only kind-0 sender found is `Creature_processDamage` (0x110d30 head): while a creature has
pending damage and `g_numPlayers == 1` it calls `world_notifyObjectsNear(600, 0, own pos,
this)`. So in a one-player game an idle Bubo walks to a Bubo that is being hit within a
600-unit box; with more players the call is not made. (`Player_run` sends kinds 2 and 3,
which this body ignores.)

Slot 38 (0x249a30): returns class-definition resource +0x1c when +0x468 == 1, else +0x14
(passed by Bubo_draw as the second model/texture argument of `Creature_draw`).

Phases: none. No hit-point threshold is read.
Script-driven: no property or built-in specific to the class. scripts/STORM2.txt (the level
named in state 0) shows a "remaining" counter with `bust_bubonian.tex` (line 248); how that
count is kept was not read.

Per-machine:
(a) the scan on run/setState/slot 12/ctor: no hits. By hand: run reads g_simFrame (tick counter)
    and g_levelName in state 0 only; all random decisions use `GameObject_rand`.
(b) Bubo_draw (0x2484c8) stores nothing into the object: slot 38, slot 16, `Creature_draw`,
    then the holder draw (0x94).
(c) None found (the draw scan and by hand).

Open: meaning of cflag 0x200000000; `Creature_stepAnim`'s handling of the marks.

#### FemaleDarkElf  (factory names `FemaleDarkElf*`; vtable 0x5149f8; size 0x478)

Functions: ctor 0x25947c, run 0x259a98, draw 0x259a34, setState 0x25ab14, saveState (slot 9)
0x25a84c, loadState (slot 8) 0x25a950, slot 12 0x25aa30. takeDamage is the base body. Slot 15
(clone) is a unique body at 0x121a98 (outside this range, not read).

Constructor (0x25947c; argument order here is this, pos, angle, props, typeName):
- `Creature_ctor(maxHp 10.0, this, typeName, pos, angle, classDef 0x4ff920 (`dark_fem.lmp`),
  props)`. Radius 15, turn rate 1.2, speed 0, kind byte +0xb4 = 9, draw half-width +0x28 =
  0x19, +0xec = g_simFrame, state 0 (stored directly, setState is not called), idle clip
  def+0xd4 pushed, cflags |= 0x800000000, `obj_runEvery60`. No stats call, no property read.
- Embedded holder at +0x3d0, final table WeaponShield 0x50cda0 (two hands; descriptor at
  +0x420).
- Sub-kind +0x3c8 by name prefix (`str_prefixDiffers`): `femaledarkelfsoldier` -> 0,
  `femaledarkelfnecro` -> 1, anything else stays 0.
  - necro (1): one `GameObject_rand`: variant bits = `1 << (r & 3)`; tint preset 6;
    `lump_load("skele_b.lmp")`. No hand is switched on.
  - soldier (0): four own-generator draws: variant bits `1 << (r % 14 + 4)`; hand-1 part
    `(r & 2) + 0x1d`; hand-2 (shield) part `(r % 3) * 2 + 0x21`; then `r / 65536 < 0.1`
    (one in ten) draws a fifth value `r % 3` and calls a holder element slot with hand 1:
    0 -> table offset 0x2c (the entry `Creature_init` uses for the `PoisonWeapons` property),
    1 -> 0x24 (`ColdWeapons` entry), 2 -> 0x3c (`DiseaseWeapons` entry). Those WeaponShield
    bodies (0x3c2470, 0x3c2440, 0x3c24d0) call `creature_buildElementDamage(…, 3 / 2 / 5)`,
    which queries the matching skill through table offset 0x5c and draws the SHARED seed
    once to size the rider.
- Event marks: entries 0x12-0x15 (melee clips def+0x94..+0xac) 0x1 at 0.3; entries 0xd,
  0xe (cast clips def+0x6c, +0x74) 0x1 at 0.2; entries 4, 6, 8, 10 (death clips
  def+0x24, +0x34, +0x44, +0x54) 0x80 at 1.0. Then `Creature_init`.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s8 | sub-kind: 0 soldier, 1 necro | ctor, run, setState, save/load |
| +0x3d0 | WeaponShield | embedded holder (hand-2 part id is its +0x98 = object +0x468) | ctor, run, save/load |
| +0x470 | s32 | necro: clock value after which she may cast again (clock + 180 after each cast event) | run states 3, 5, 7/8 |
| +0xf4 | s32 | base "free class timer": idle-to-wander time (clock + 180, set by setState 0) and end of the block state (clock + 60, set by setState 0x11) | run states 0, 0x11 |

Run head (0x259a98): `Creature_processDamage`, `Creature_run`, `Creature_updateActive` (0 ->
return), holder update 0.5, `Creature_stepAnim(1.0)`, `Creature_applyKnockback` with 0.3
(necro) or 0.5 (soldier), slot 23 (0); the necro also calls slot 24 (pick ally).

States:
- 0: slot 25 sees the target -> 3; else `Creature_isAwayFromHome(this, 3)` -> 1; else when
  the clock has passed +0xf4 -> 1.
- 1: target seen -> 0; else `Creature_moveToDest`.
- 2, 4, 9-0xf, unlisted -> 0.
- 3: no target -> 0.
  - soldier: within 24 inside arc 6000 -> 5; else within 200 inside arc 6000 AND
    `Creature_countAlliesNearTarget(24)` >= 2 -> 5; else within 24 at any angle -> turn
    only; else move to target.
  - necro: target within 100 at any angle -> 8 if the clock has passed +0x470, else 0x10;
    else within 400 inside arc 2000 with rayMode 1 -> 5; else within 400 at any angle ->
    turn only; else move to target.
- 5:
  - soldier, target within 24 inside arc 6000: if holder slot 14 (hand 2: "shield hand on")
    is non-zero and `Creature_isTargetAttackingMe` and `GameObject_rand & 3 == 0` -> 0x11
    (block); otherwise -> 6. (The generator is drawn only when the first two tests pass.)
  - soldier, otherwise (and not rooted): if the target is NOT within 200 inside arc 6000,
    draw the own generator and go to 3 when `r % 60 == 0`; if still here and at least two
    allies are near the target, draw again and go to 3 when `r % 60 == 0`; else stay.
  - necro: target within 100 at any angle -> 8 (clock past +0x470) or 0x10. Else, clock past
    +0x470 and target within 400 inside arc 2000 (rayMode 1) -> 7. Else when not rooted and
    the target is not in that cone -> 3; in the cone but not ready -> stay.
- 6 soldier melee (one of four clips def+0x94..+0xac by `GameObject_rand & 3` in setState):
  settle, turn; event 0x1: `Creature_hitTargetInArc(0, 24, this, facing, 6000, +0xd0,
  +0xd2, +0xd4, flags 8, descriptor = holder slot 17 hand 1)`. Anim flag 8 clear -> 3.
- 7 necro cast / 8 necro close-range cast (clip def+0x6c or +0x74 by `GameObject_rand & 1`):
  with no target handle the state only waits for the clip. Otherwise each frame: aim point =
  position + 300 along the facing, replaced by `Creature_leadTargetPoint(400)`; turn to
  target. On event 0x1, `corpse = creature_findCorpseOfClass(300)` and `wounded =
  creature_findWoundedAlly(300)` are both evaluated, then:
  - state 8: SummonSkeleton (skill 11) table offset 0x0c (can-cast) with this. Non-zero ->
    SummonSkeleton offset 0x14 (cast) with (slot 35 value, this, own position, facing),
    result not linked. Zero -> SpiritShield (skill 94) offset 0x14 with the same arguments,
    result linked with `creature_addSpell(this)`.
  - state 7, corpse found: the corpse's slot 32 (revive) is called with argument 1.
  - state 7, no corpse, wounded ally found that has no Healing spell: Healing (55) offset
    0x14 with (slot 35 value, the wounded ally, own position, facing); linked to that ally.
  - state 7, otherwise, ally handle +0x238 set and the ally's holder slot 16 (hand 1)
    returns 0 (weapon has no element): PoisonWeapons (26) offset 0x14 with (slot 35 value,
    the ally, ally position, own facing); linked to the ally.
  - state 7, otherwise: `angle = creature_aimAngleAt(350, this, target)` (own-generator
    spread inside), then `GameObject_rand % 3`:
    0 -> SummonSkeleton offset 0x0c; non-zero -> SummonSkeleton offset 0x14 (as above);
         zero -> Shock (37) offset 0x14 with (slot 35 value, this, position raised by half
         of +0x20, angle);
    1 -> PoisonRain (24) offset 0x14 with (slot 35 value, this, the led aim point, angle);
    2 -> PusStorm (80) offset 0x14 with (slot 35 value, this, the led aim point, facing).
  Every branch writes the flash colour quads +0x90..+0x9e (cosmetic) except the SpiritShield
  and PoisonWeapons branches, and every branch ends with +0x470 = clock + 180. Anim flag 8
  clear -> 3.
- 0x10: attack ready -> 0; else `Creature_fleeFromTarget(this, 0)`. setState sets +0x318 = 60.
- 0x11 block: stays until the clock passes +0xf4 (60 ticks), then 3. setState 0x11 sets
  cflag 0x200 (blocking); every later setState that passes the filter clears it.
- 0x12: leaves to 3 when anim flags 0x10 and 0x20 are both clear, or when flag 0x20 is set,
  0x10 clear and 0x80 (clip finished) set; otherwise waits.
- 0x13: stun over -> 0.  0x14: `Creature_deadUpdate(20, this, events, zero vector, 0)`.

setState (0x25ab14), non-routine: clears cflag 0x200 first (after the filter). 0x12: if the
pending damage flags +0x2dc have none of 0x380000 -> a flinch clip (necro def+0x7c, soldier
def+0xcc); the third choice def+0xbc is taken only when cflag 0x200 is set, which the clear
just above makes impossible on this path (dead branch, Observed in the decompile order).
With a 0x380000 bit: `GameObject_rand & 3` picks a knock-down clip, chained to its get-up
clip and the idle clip. 0x14: death clip by `GameObject_rand & 3`; `Creature_dropLoot(36, 2,
1.8, 0.6, 2, 0.25, this, pos, facing, 0)` unless cflag 0x100000000; holder slot 11 for hand
1 and hand 2 (weapon and shield dropped as props); slot 28 (0).

Slot 12 (0x25aa30): kind 2 only. If holder slot 14 for hand 2 is non-zero (argument register
checked at 0x25aa60-0x25aa7c: it still holds the kind value 2), own state is 3 or 5, a source
object is given and the direction to the source is within +-9999 angle units of the facing:
setState(0x11). Kind 2 is sent by `Player_run` to the creature a player's shot is aimed at
(call at decompile line 1111 of 0x1a5030, inside the block that searches a cone ahead of the
player; that this is the ranged-attack code is Inferred, the block was not read in full).

saveState: base record, then 16 bytes: sub-kind, holder slot 15 hand 1 (held part id),
slot 15 hand 2 (shield part id), slot 16 hand 1 (weapon element). loadState: base, sub-kind,
holder slot 1 for both hands with the saved part ids, holder slot 8 (hand 1, saved element)
= `creature_buildElementDamage` again (for a non-zero element that is one shared-seed draw
at load time: the rider size is re-rolled, not saved; element 0 draws nothing).

Phases: none.  Script-driven: nothing class-specific.

Per-machine: (a) the scan: no hits on run/setState/slot 12/ctor/save/load; by hand nothing
per-machine is read; decisions use `GameObject_rand`, the ctor/load element rider uses the
shared seed. (b) FemaleDarkElf_draw (0x259a34) stores nothing: `Creature_draw`, holder draw.
(c) none found.

Doc correction: docs/monsters.md lists SummonSkeleton for this class as "can-cast test"
only; the run function also CASTS it (offset 0x14) on two paths (0x25a574 block, reached from
state 8 and from the `% 3 == 0` branch of state 7).

Open: meaning of `Creature_isAwayFromHome`'s second argument (3 here, 1 in Bubo); cflag
0x800000000; whether kind 2 of slot 12 is only sent for ranged shots.

---

#### Critter  (ambient animals; vtable 0x510ca0; size 0x448)

How it is created (corrects the first pass, which lists only `Orca`):
- factory 0x159c94: the exact type name `Orca` jumps straight to the allocation (0x159ecc ->
  0x15d8f0); in addition, in the factory's fall-through tail ANY otherwise unmatched type
  name whose record has a non-zero `Critter` property creates one (0x15d8d8-0x15d910). The
  type name itself is then used as the species (see below).
- `Creature_spawnScavenger` 0x1125e0: `raven` (props `oneshot=1`, `movename=fly1`) or `rat`
  (props `oneshot=1`, `fleename=rat_move`), static property lists at 0x402770 / 0x402780.
- VampireLord code at 0x2b8104 and 0x2b9358: type `bat`, static property list 0x502f78
  (`oneshot=1`), angle = vampire facing + one draw of the VAMPIRE's generator.

Functions: ctor 0x2547fc, species setup 0x256024 (unnamed, called once by the ctor), run
0x255008, draw 0x254f24, setState 0x255c5c (its switch bodies run to 0x255f7c; the decompile
loses them, they were read in the instructions with the jump table 0x5442c0), onTouch (slot 6)
0x255f7c, takeDamage 0x255c54 (empty: a Critter ignores slot 2), saveState / loadState
0x255c4c / 0x255c44 (8-byte stubs; return value not checked). Slots 15 and 16 are unique
bodies outside this range (0x120df8, 0x3c3ef8; not read).

Constructor (0x2547fc) `(this, typeName, pos, angle, props)`:
- Calls `GameObject_rand(this)` BEFORE the base constructor (0x25484c; a0 is still the raw
  block) and passes `r % 14 + 4` as the max-hp argument. The generator word +0x44 has not
  been seeded yet; with a zero-filled block (what `pool_new` is documented to return) the
  draw is the constant 0x3c6e and the argument is always 4.0 (Inferred from that). The value
  is then overwritten by `Creature_setStats(1, 1, 1, 1, 1, this, rollHp 1)`.
- `Creature_ctor(maxHp, this, typeName 0, pos, angle, classDef 0, props)`: no class
  definition; the model and clips are looked up by name instead.
- Radius 10, draw half-width 10, turn rate 1.2, speed 0, kind byte +0xb4 = 0x12, +0xec =
  g_simFrame, cflags |= 0x40000000000, OBJECT flags |= 8 (the "dead" bit: every Critter
  carries it from birth), +0x444 = (int)HomeRange, +0x43c = 2, +0x440 = 0, +0x404 = 180,
  +0x408 = 60, +0x40c = 180.
- The type-name string is lower-cased IN PLACE and used as the default stem. Properties
  (value replaces the stem): `lumpname` -> lump `<x>.lmp`; `wakname` -> model `<x>.vif`
  (+0x414); `rawname` -> texture `<x>.tex` (+0x418); `idlename` -> `<v>.anm`, default
  `<type>_idle.anm` (+0x41c); `movename` (+0x428, default `_move`); `followname` (+0x42c,
  `_follow`); `fleename` (+0x430, `_flee`); `osidlename` (+0x434, `_osidle`, falls back to
  the idle clip); `osfleename` (+0x438, `_osflee`, falls back to the flee clip); `turnSpeed`
  (float, default 1.0, +0x400); `path` -> `pathFollower_init(this+0x3c8, name, &pos)`;
  `oneshot` (int).
- Start state: with a `path`: object flags |= 5, move clip pushed with flags 0x801,
  `anim_randomizeTopTime` (draws g_cosmeticSeed, see Per-machine), setState(0x16),
  `obj_runEveryFrame`. Without: `oneshot` -> 0x17; else idle clip present -> 0; else move
  clip present -> 1; `obj_runEvery60`.
- Then the species setup 0x256024(this, lower-cased type, lump name), hide mask,
  `Creature_init`.

Species setup (0x256024), by lower-cased type name (exact unless marked prefix):
| name | effect |
|---|---|
| bat | object flag 1; cflag 0x100000 |
| kitten (prefix) | +0x408 180, +0x40c 120, +0x404 180; class flag 2 cleared; `name` property starting `kitten0`..`kitten3` sets variant bit n; fidget clip A `jump_xy.anm` |
| pengo | +0x408 360, +0x40c 120, +0x404 480; fidget clips `pengo_cluck.anm`, `pengo_flap.anm` |
| shark | draw half-width 0x28 |
| crab | +0x408 180, +0x404 180; object flag 1; scale = 1.5 + own-generator fraction |
| raven | cflag 0x100000; +0x444 200; +0x40c 240; class flag 1; clips `hop.anm`, `flutter.anm`; if the level name starts with `intro`: cflag 0x2000000 |
| fish (prefix) | object flag 1; +0x440 += own-generator fraction x 60 |
| seagull | cflag 0x100000; setState 0x19 (0x18 when `oneshot`); +0x444 200; object flag 1; +0x40c 360; class flag 1; clips `stretch.anm`, `preen.anm` |
| rat | +0x444 96; object flag 1; scale 1.2 |
| bullfrog | class flag 0x20; object flag 1; cflag 0x2000; in level `dismedal` also cflag 0x80000000000; +0x408 360, +0x404 360; scale 0.75 |
| catfish | class flag 4; turn rate 0.2; object flag 1 |
| bottomfish | +0x440 = 12; object flag 1 |
| fishdead | class flag 4, +0x440 = 8, turn rate 0.2 — UNREACHABLE: the `fish` prefix test comes first (0x256024 order) |
| drake, adrake | only without a `path` property: cflag 0x100000; setState 0x19; +0x444 200; class flag 1; +0x40c 360; object flag 1; clips `idlea.anm`, `idleb.anm` |
| bflya, bflyb | object flag 1 |
| orca | draw half-width 0x78 |
| dblob | class flag 8; +0x404 = length word of `dblob_move.anm` when found; +0x408 360 |
| hangman | class flag 0x10 |

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | 0x38 bytes | path follower (pos pointer, direction, name at +0x3dc, target angle s16 at +0x3f0, "snap" byte +0x3d9) | run state 0x16 |
| +0x400 | float | `turnSpeed` | run state 0x16 |
| +0x404 / +0x408 / +0x40c | s32 | wander time base / idle time base / fidget interval base (frames) | setState, run |
| +0x410 | s32 | clock value of the next fidget clip | run 0, 0x17, 0x19 |
| +0x414, +0x418 | ptr | model, texture | draw, run |
| +0x41c | ptr | idle clip | run, setState 0 |
| +0x420, +0x424 | ptr | fidget clips A, B | run |
| +0x428, +0x42c, +0x430 | ptr | move, follow, flee clips | setState |
| +0x434, +0x438 | ptr | one-shot idle, one-shot flee clips | setState 0x17-0x1a |
| +0x43c | u32 | class flags: 1 rises while fleeing; 2 walk without the path finder; 4 "return home when high above the ground at home"; 8 on arrival before the timer: new point and timer restarted in multiples of +0x404; 0x10 never moves; 0x20 can be squashed | run |
| +0x440 | float | height offset added to z for drawing (and to the smoothed height +0x3c) | draw, run 0x18/0x1a |
| +0x444 | s32 | player-proximity radius of the one-shot states (HomeRange by default) | run 0x17, 0x19 |
| +0xf4 | s32 | state timer (clock value) | run |

Run (0x255008). Head: state 0x16 skips `Creature_run` and `Creature_updateActive`
altogether: it sets cflag bit 63 itself, steps the path follower (0x210128) and, when that
returns non-zero, turns toward the follower's target angle (`angle_approach` with turnSpeed
x 0.25, or a snap when byte +0x3d9 is set). Other states: `Creature_run` (non-zero ->
return), `Creature_updateActive`; inactive -> return, except in state 0x18 where the object
is deleted. Then `Creature_stepAnim(1.0)`. There is no `Creature_processDamage`, no target
picking and no knockback in this class.
- 0 idle: zero-velocity `Creature_moveBy` unless class flag 0x10. If fidget clip A exists
  and the clock passed +0x410: start A (or B when present and `GameObject_rand & 1 == 0`),
  +0x410 = clock + (+0x40c) + `GameObject_rand % 60`. Otherwise, once anim flag 8 is clear
  and a move clip exists: clock past +0xf4, or `Creature_isAwayFromHome` -> 1.
- 1 wander: `Creature_moveToDirect` (class flag 2) or `Creature_moveTo` to +0x104, neither
  with flag 0x10. On arrival or when the clock passed +0xf4: with an idle clip -> 0 (flag 8:
  only once the timer has ALSO passed); without one (or flag 8 before the timer): new
  wander point, +0xf4 = clock + (+0x404) + `rand % 120` (flag 8: clock + (+0x404) x
  (`rand % 3` + 1)). Class flag 4: if z is more than 11 above `terrain_height` at the home
  position, the destination becomes the home position.
- 0x10 flee: no target -> 0 (or 1 without an idle clip). Else `Creature_fleeFrom(this,
  target, 0)` (not with flag 0x10) until the clock passes +0xf4, then the target handle is
  cleared and the state returns to 0 / 1.
- 0x14: `obj_stopRunning`, then slot 28 (0). setState never stores 0x14 (below), so this
  needs a direct write of +0x232 (not searched).
- 0x16 path: when the follower step succeeded: x, y += the animation root motion of this
  frame (+0xbc, +0xc0); z += follower direction z (+0x3d4) x |root motion per second| / 60;
  `obj_updateGridCell`; smoothed height +0x3c = z.
- 0x17 one-shot waiting: every 16th frame (g_simFrame xor serial +0x230): for player slots
  0..g_numPlayers-1 in order, a player object within +0x444 (3-D) -> setState 0x18. Fidget
  clips as in state 0. A second exit (cflag bit 63 clear and the clock past +0xf4, 300 after
  entry -> 0x18) is written but see the note below.
- 0x18 one-shot fleeing: class flag 1 adds 2.0 per frame to +0x440; +0x3c = z + offset;
  x, y += root motion; grid update. Deletion happens in the run head (inactive + state
  0x18 -> `obj_delete`); the switch body has its own "bit 63 clear -> delete" branch too.
- 0x19 repeating wait: as 0x17's proximity test (-> 0x1a) but only while object flag 2 is
  clear. Written but see the note: "bit 63 clear and flag 2 set -> clear flag 2".
- 0x1a repeating flee: as 0x18. Written but see the note: "bit 63 clear -> object flag 2
  set, position = home, grid update, setState 0x19 (which zeroes +0x440 for class flag 1)".
- Note on the bit-63 branches (Inferred, from two Observed bodies): the run head returns
  whenever `Creature_updateActive` returns 0 (except the 0x18 delete), and
  `Creature_updateActive` (0x10c0f0) sets cflag bit 63 exactly when it returns non-zero. So
  inside the switch bit 63 is always set for states other than 0x16, and the four
  "bit 63 clear" branches above cannot run. Consequence as the code stands: a seagull /
  drake that reaches 0x1a keeps rising while a player is near (drawn until its offset
  reaches 196), freezes when it goes inactive, and never returns home or to 0x19.
- 2-0xf, 0x11-0x13, 0x15: nothing.
- Tail, every state that did not return (class flag 0x20 only = bullfrog): every 4th frame
  (g_simFrame xor serial), for players in slot order: 2-D distance below 2 x radius and
  player speed (+0x308, +0x30c) above 20 -> run the script named by the `deathScript`
  property with the script-self global set to this object, `fx_spawn` 3 / 0 / 9 by cflag
  0x2000 / 0x40000 / 0x1000, a sound, one `GameObject_rand` for the decal angle,
  `decal_add(24, ..., type 4 / 1 / 7)`, `obj_delete`.

setState (0x255c5c): no `Creature_filterState`. A request other than 0x16 becomes 0x16 when
the object has a `path` property. Current 0x17 accepts only 0x17/0x18; current 0x18 is
final; current 0x19 and 0x1a accept only 0x19/0x1a. Bodies: 0 (timers +0xf4 = clock +
(+0x408) + `rand % 120`, +0x410; idle clip), 1 (timer as in run; wander point; follow clip
when cflags 0xc00000 and one exists, else move clip), 0x10 (only with a flee clip: +0xf4 =
clock + 60 + `rand % 120`), 0x16 (move clip), 0x17 and 0x19 (+0xf4 = clock + 300, fidget
timer, one-shot idle clip; 0x19 with class flag 1 zeroes +0x440), 0x18 and 0x1a (object
flag 1, +0xf4 = clock, one-shot flee clip). Every other request, INCLUDING 0x14, leaves the
state unchanged.

onTouch(other): state 0x16 ignores; 0x17 -> setState 0x18; states 0/1 with a flee clip:
target handle linked to the toucher (registers checked at 0x255f90-0x255ff4), setState 0x10.

Critter_draw (answers the first-pass open question): it saves x, y, z, adds +0x440 to z,
calls `Creature_draw` (in states 0x18/0x1a only while (int)(+0x440 x 0.5) < 0x62, after
writing that value to the draw parameter byte 0x41c149 through 0x1797b8, then
`model_resetDrawState`), and writes x, y, z back on every path before returning
(0x254f24: both branches join at the restore). Only z is changed in between; no facing
field is touched. So the store IS undone; run code never sees it. Code called from
`Creature_draw` during the call (attached-spell draw) sees the raised z.

Per-machine:
(a) Found by hand (the scan does not descend outside the area): a `path` Critter's clip time is
    set by `anim_randomizeTopTime` (g_cosmeticSeed, 0x16d0b8) in the constructor, and state
    0x16 integrates the clip's root motion into the object position and grid cell every
    frame and feeds that position to the path follower. Unless the move clip's root motion
    is uniform over the clip (clip data, not checked) the position of every path Critter
    differs between machines. What reads that position: the squash test in the run tail
    (class flag 0x20, bullfrog only: runs `deathScript`, draws the own generator, deletes
    the object) and any box query that returns the object (Critters carry object flags 8,
    and path ones also 1 and 4; consumers not traced). Whether any level gives a bullfrog a
    `path` was not checked. Everything else in run reads g_simFrame, g_numPlayers and the
    player table in slot order only; `fx_spawn` x3 and the sound are cosmetic.
(b) Draw stores z and restores x, y, z (above). Nothing else is stored in the object.
(c) None: no generator draw, creation, run-list change, script or world query in draw.

Script-driven: `initScript` (base, in `Creature_init`) and `deathScript` (squash tail).
scripts/DISMEDAL.txt has `frogInit` (counter var[0] + 1) and `frogDie` (counter - 1), called
through two `callScript` wrapper entries, and `showOnMap('frog', 1)`; that the wrappers are
the `initScript` / `deathScript` values of that level's bullfrog records is Inferred (level
records not read). It shows the squash is a counted game event there, so its timing matters
for lockstep.

Open: who sets state 0x14 on a Critter; return values of the save/load stubs; layout of the
follower beyond the fields used.

---

#### Creep  (factory name `Creep`; vtable 0x514620; size 0x500)

Functions: ctor 0x253148, run 0x2535c8, draw 0x253514, setState 0x2542c4, saveState 0x2540e0,
loadState 0x254198, slot 12 0x2542a0 (EMPTY: copies its position argument to the stack and
returns; instructions read). takeDamage is the base body.

Constructor (0x253148): `Creature_ctor(maxHp 10.0, this, typeName, pos, angle, classDef
0x4ff458 (`creep.lmp`), props)`. Embedded holder at +0x3c8 with final table Weapon2 0x50ce70
(two descriptors: hand 1 at +0x418, hand 2 at +0x4a8). Radius 15, draw half-width 0x1e, turn
rate 1.2, speed 0, kind byte 0x10, +0xec = g_simFrame, +0xf4 = g_simFrame + 300, cflags |=
0x400040000, resistance array entries +0x64 = 1.0, +0x68 = 1.0, +0x6c = 0.5 (poison,
disease, lightning by the docs/gameplay.md naming; Inferred), fade counter +0x4fe = 0x78.
Two own-generator draws: hand-1 part `(r % 3) * 4 + 0x13`, hand-2 part `(r % 3) * 4 + 0x15`.
setState(0x17), `obj_runEvery60`. Event marks: entry 5 (def+0x2c, state 6) 0x1 at 0.2 and
0x80 at 0.4; entry 6 (def+0x34, state 7) 0x2 at 0.2 and 0x80 at 0.4; entry 7 (def+0x3c,
state 8) 0x4 at 0.7 and 1.3, 0x8 at 1.7; entry 8 (def+0x44, state 9) 0x1 at 0.1 and
0x2 at 0.3; entry 0xb (def+0x5c, death) 0x80 at 0.5. `Creature_init`. No property read,
no stats call.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | Weapon2 | embedded two-hand holder | run, save/load, draw |
| +0x4f0 | Vec3 | target position of the previous frame | run state 0x1a |
| +0x4fc | u8 | last action state stored by setState (6-9, 0x11, 0x19) | no reader found in this class |
| +0x4fd | u8 | count of 0x4 events in state 8; non-zero sets tint preset +0xa0 = count + 9; zeroed by every setState | run states 6-9 |
| +0x4fe | s8 | fade counter: 120 at birth, held while in state 0x17, otherwise -1 per frame down to 0 (-2 per frame in state 0) | run head; DRAW |

Run head (0x2535c8): `Creature_processDamage`, `Creature_run`, `Creature_updateActive` (0 ->
return), holder update 0.5, `Creature_stepAnim(1.0)`, `Creature_applyKnockback(0.3)`, slot 23
(0), then the fade-counter step.

States:
- 0x17 ambush (start state; the counter stays at 120 so the model is not drawn): turn to
  target; when the target is within 200 at any angle: if it is also within 60 inside arc
  0x4000, `Creature_knockbackTarget(100, this)`; -> 0x18.
- 0x18 appear (clip def+0x24 or +0x1c by `GameObject_rand & 1`): zero-velocity
  `Creature_moveBy`, turn; anim flag 8 clear -> 3.
- 0: slot 25 sees the target -> 3; else `Creature_isAwayFromHome(this, 3)` -> 1.
- 1: target seen -> 0; else `Creature_moveToDest`.
- 3 chase: no target -> 0.
  - Target within 60 inside arc 6000: if `Creature_isTargetAttackingMe` and `GameObject_rand
    % 3 == 0`, a second draw `% 3` picks 0 -> 0x11 (block), 1 -> 0x19 (evade clip), 2 -> 8.
    Otherwise, if `Creature_isBlockedByTarget`: -> 0x19 (the alternative 0x11 needs the same
    60 / 6000 test to fail a second time in the same frame). Otherwise `GameObject_rand & 1`:
    0 -> 6, 1 -> 7.
  - Not within: if `Creature_countAlliesNearTarget(60)` > 0: +0xf4 = clock + 240 + `rand %
    240`, setState 5 (case 5 of setState then overwrites +0xf4, see below). Else target
    within 60 at any angle -> turn only. Else one `GameObject_rand % 30` draw and
    `Creature_moveToTarget`; the written alternative (draw == 0, allies near the target, and
    this creature standing within +-0x3fff of the direction the TARGET faces -> 0x1a)
    requires `Creature_countAlliesNearTarget(60)` to be > 0 after it was <= 0 a few
    instructions earlier with identical arguments (0x253978 vs 0x253a20), so state 0x1a is
    not reachable from here (Inferred).
- 5 hold back: no target -> 0. Turn; target within 60 inside arc 6000 -> 6. Else (not
  rooted): clock past +0xf4 -> 3; no ally near the target (60) -> 3; target farther than 110
  -> 0x1b; else stay.
- 0x1b close in: target within 110 at any angle, or clock past +0xf4 -> 5; else
  `Creature_moveToTarget`.
- 6, 7, 8, 9 attacks (clips def+0x2c, +0x34, +0x3c, +0x44): zero-velocity `Creature_moveBy`;
  with a target, all through `Creature_hitTargetInArcEdge(0, 60, this, facing, 6000, +0xd0,
  +0xd2, +0xd4, flags, descriptor)`:
  event 0x1 -> hand-1 descriptor, flags 8; else 0x2 -> hand-2 descriptor, flags 8; else 0x4
  -> hand 1 then hand 2, flags 8 (in state 8 it also increments +0x4fd); else 0x8 -> hand 1
  then hand 2, flags 0x80008. Then turn to target and apply the tint. Combo: state 6 on event 0x80:
  `GameObject_rand % 3 == 0` -> 7; state 7 on event 0x80: `% 3 == 0` -> 9. Otherwise anim
  flag 8 clear -> 3.
- 0x10: attack ready -> 0; else `Creature_fleeFromTarget(this, 0)`. (This setState does NOT
  set +0x318, unlike Bubo and FemaleDarkElf.)
- 0x11 block (cflag 0x200, +0xf4 = clock + 60): leaves to 3 once the clock passed +0xf4 and
  `Creature_isBlockedByTarget` is 0.
- 0x12: zero-velocity move; anim flag 0x10 clear -> 3.
- 0x19 (clip def+0x64): zero-velocity move; anim flag 0x10 clear -> 0x11.
- 0x1a (see state 3): no target -> 0; target within 60 inside arc 6000 -> 6; else when
  `GameObject_rand % 30 == 0` and the target moved less than 1.3333 (2-D) since the previous
  frame -> 3; else move to target. Target position stored at +0x4f0 every frame.
- 0x13: stun over -> 0.  0x14: zero-velocity move; `Creature_deadUpdate(30, this, events,
  zero vector, 0)`.
- 2, 4, 10-0xf, 0x15, 0x16: the run function returns without a transition.

setState (0x2542c4): after the filter, always +0x4fd = 0, cflag 0x200 cleared, tint preset
+0xa0 = 0. Non-routine: 0 sets +0xf4 = clock + `rand % 120`; 5 and 0x1b set +0xf4 = clock +
60 + `rand % 120`; 0x11 sets +0xf4 = clock + 60 and cflag 0x200; 0x12 is REFUSED (state kept)
when the current state is 6-9 with anim flag 8 still set, or 0x13 — otherwise one of two
clips by `GameObject_rand & 1`; 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this,
pos, facing, 0)`, death clip def+0x5c, holder slot 11 for both hands, slot 28 (0). Numbers
without a case are stored unchanged.

saveState: base record + 8 bytes (holder slot 15 for hand 1 and hand 2 = held part ids).
loadState: base, holder slot 1 for both hands with the saved ids; if the loaded state is
0x14 both hands are switched off (part 0).

Creep_draw (answers the first-pass open question): it writes the fade counter +0x4fe to the
draw parameter byte 0x41c149 (through 0x1797b8). When the counter is above 100 it SETS
creature flag 0x200000 ("model not drawn by `Creature_draw`", docs/creatures.md) before
calling `Creature_draw`; the holder (weapons) is drawn only when the counter is below 100;
then it CLEARS 0x200000 unconditionally and calls `model_resetDrawState`. So the bit is
0x200000 and it is a temporary for the duration of the draw call. Readers of that bit: only
`Creature_draw` 0x10b048 was found (text search of the whole decompile for a 0x200000 test
on +0xa8, directly or through a local; the other 0x200000 tests in creature code are on the
damage-flag word +0x2dc). Other writers: `SpellShadowStep_run` / `_dtor` (0x311e3c /
0x311da0) and `BlackWidow_run` (clear). Creep_run and Creep_setState neither read nor write
it. One side effect to keep in mind: because the clear is unconditional, a Creep that had
the bit set by run code (only a ShadowStep spell could) would lose it at the next draw.

Per-machine:
(a) the scan: no hits on run/setState/ctor/save/load. By hand: all decisions use
    `GameObject_rand`; nothing camera- or local-player-dependent is read. The fade counter
    +0x4fe is written only by run code and the constructor.
(b) Draw sets and clears cflag 0x200000 (above); no run-side reader found. Nothing else
    stored.
(c) None found.

Open: reader of +0x4fc; what sets the attack cooldown that leads into state 0x10 for this
class; cflag 0x400000000.

---

### Cyclops family (Cyclops, FatCyclops)

Shared behaviour (each Observed in both run functions): three special attacks built from the
same gameplay-area objects —
- "stomp": `pool_new(0x6c)` + `dustCloud_ctor(obj, pos, life 0x78, radius 0x28, 0, 1)` at 80
  units ahead, z + 36; no damage call in the monster code;
- "spit": `pool_new(0xa8)` + `PoisonProjectile_ctor(scale, obj, classDef, four resource
  indices, origin, velocity, angle = facing - 0x4000, owner = this)` (the last two are stack
  arguments, read in the instructions at 0x2572c0 / 0x258af8); scale = 0.5 + own-generator
  fraction x 0.5;
- "rear gas": an enemy BEHIND (`creature_findEnemyInCone` with facing - 0x7fff) triggers
  `pool_new(0x70)` + `poisonGasSpell_ctor(obj, pos, life 300, radius 0x28, 1, owner this,
  damage 5)` placed behind the creature.
Melee hits pass descriptor 0 (no elemental rider) and damage +0xd0/+0xd2 with rating +0xd4.
Footstep marks: walk clip entry 0x10 (def+0x84) carries 0x4 at 0.2 and 0x8 at 0.8; both
classes turn them into ground effects at attach points 3 and 2 unless cflag
0x2000000000000000 (standing in water) is set. Both death handlers call
`Creature_deadUpdate(40, ...)`. Both draw functions set the draw parameter 0x41c14c to 3.0
(through 0x1797c8) around `Creature_draw`. They are separate classes with separate tables
and separate run/setState bodies; the static initialiser after FatCyclops (0x2593d0) builds the
dust particle definition 0x8e3468 that only Cyclops code (0x257ba0) uses, so the two share a
translation unit (Inferred).

#### Cyclops  (factory names `CyclopsNew` -> variant 2, `CyclopsGrey` -> 1, `Cyclops` -> 0; vtable 0x510b58; size 0x458)

Functions: ctor 0x2566d4, run 0x256b18, draw 0x256acc, setState 0x257668, loadState (slot 8)
0x257618, dust burst 0x257ba0 (unnamed), club drop 0x257ab4 (unnamed, NO caller or reference
found by xref). takeDamage and saveState are base. Slot 15 unique at 0x121460 (not read).

Constructor `(this, typeName, pos, angle, props, variant)`: like Critter it calls
`GameObject_rand(this)` before the base constructor (0x256728) for the max-hp argument
`r % 14 + 4` (unseeded generator word; 4.0 for a zero-filled block, Inferred).
`Creature_ctor(..., classDef = 0x4ff558 + variant x 0xf8, props)`: variant 0 `cyclops.lmp`,
1 `sickcyc.lmp`, 2 `cyclops2.lmp`. No holder (+0x50 stays as the base left it). Radius 35,
draw half-width 0x37, turn rate 1.2, speed 0, +0xec = g_simFrame, +0x3c8 = 0, cflags |=
0x220040000, state 0 stored directly with idle clip def+0x6c, `obj_runEvery60`. One
own-generator draw r: variant bits 1, 2, 4, 8 copied from r; bit 0x10 of r set -> variant
bit 0x10 and +0x3cc = 0x18, clear -> variant bit 0x20 and +0x3cc = 0x16. Event marks: entry
3 (def+0x1c) 0x1 at 0.6; entry 4 (def+0x24) 0x1 / 0x2 / 0x4 at 0.5 / 1.5 / 2.5; entries 5,
6 (def+0x2c, +0x34) 0x1 at 0.6; entry 8 (def+0x44) 0x1 at 0.3; entry 9 (def+0x4c) 0x1
at 0.5; entry 0x10 (walk) 0x4, 0x8; entry 0x12 (def+0x94 death) 0x80 at 3.5.
`Creature_init`. No property read, no stats call.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | clock value after which the rear-gas state 10 may be chosen again (clock + 600, set by setState 10) | run state 3 |
| +0x3cc | s8 | class-definition resource index (0x16 or 0x18) of the club variant | run head |
| +0x3d0 | block | effect state handed to `fx_modelStatusEffects` | run head only |
| +0x410 | descriptor | damage descriptor with empty effect slots; only passed to `fx_modelStatusEffects` | run head |

Run (0x256b18). Head: when +0x3cc != 0, `fx_modelStatusEffects(0.5, 1.0, &+0x410,
resource[+0x3cc], &+0x3d0, pos, facing, model, anim, state in 6..15)` — the same call the
weapon-holder update (Weapon1 slot 21, 0x11b2a8) makes for other monsters; that function is
outside this area and was not read. Then `Creature_processDamage`, `Creature_run`,
`Creature_updateActive` (0 -> return), `Creature_stepAnim(1.0)`. Footsteps: outside states
6..15 and out of water, event 0x4 -> dust burst at attach point 3, else 0x8 -> at attach
point 2. `Creature_applyKnockback(0.2)`, slot 23 (0).
- 0: target seen (slot 25) -> 3; away from home -> 1; clock past +0xf4 (clock + 120 +
  `rand % 60`, set by setState 0) -> 1.
- 1: seen -> 0; else `Creature_moveToDest`.
- 2: seen -> 0; else `Creature_moveToDest`; when that returns 0 -> 0. (Nothing in this class
  requests state 2.)
- 3: no target -> 0. If the clock passed +0x3c8 and `creature_findEnemyInCone(0, 72, this,
  facing - 0x7fff, 5000)` finds someone -> 10. Else target within 72 inside arc 3000:
  `GameObject_rand % 6`: 0 -> 8, 1 -> 9, else 6. Else within 72 inside arc 6000 -> 7. Else
  within 72 at any angle -> turn only. Else `Creature_moveToTarget`.
- 5: target within 72 inside arc 3000 -> setState 8 / 9 / 6 by `GameObject_rand % 6` as
  above; THEN, in the same call, if not rooted -> setState 3 (0x257030). So the attack
  chosen here only stands for a rooted creature; an unrooted one draws the generator, starts
  the attack clip and is put back to 3 at once (setState 3 keeps the running clip when the
  current state is 3 or 6-10).
- 6 swing (clip def+0x1c): event 0x1: dust burst at attach point 4 (variant bit 0x10) or
  5; `GameObject_rand % 3`: 0 -> flags 0x80001, else 0x40001;
  `Creature_hitAllEnemiesInArc(0, 78, this, facing, 3000, +0xd0, +0xd2, +0xd4, flags, 0)`.
- 7 side swing (clip def+0x2c when the target is on the positive-angle side at setState
  time, else def+0x34): event 0x1: dust burst; `Creature_hitAllEnemiesInArc(0, 72, this,
  facing + 3000 (def+0x2c playing) or facing - 3000, 3000, +0xd0, +0xd2, +0xd4, flags
  0x100001, 0)`.
- 8 stomp (clip def+0x44): event 0x1: dustCloud as above, sound.
- 9 spit (clip def+0x4c): event 0x1: ONE projectile from (10 ahead, z + 120). Heading =
  direction to the target clamped to facing +-4000, plus `GameObject_rand % 2000 - 1000`;
  velocity = 260 along it, vertical `GameObject_rand % 15 - 150`; resource indices 0x13,
  0x14, 0x15, 0x1b. Sound.
- 10 rear gas (clip def+0x24): event 0x1: gas at 80 behind, z + 36. Sound. setState 10
  sets +0x3c8 = clock + 600.
- 6-10 without a target do nothing; all leave to 3 when anim flag 8 clears.
- 0x10: attack ready -> 0; else flee.  0x12: anim flag 0x10 clear -> 3.  0x13: -> 0.
- 0x14: `Creature_deadUpdate(40, this, events, vector of 100 along the facing, 0)`; on
  event 0x2 with object flag 2 clear: object flags |= 1 (not solid). setState 0x14 also
  sets the draw half-width +0x28 to 0x78, as does loadState for a creature loaded dead.

setState (0x257668), non-routine: 1, 2 and 0x10 zero the speed +0xb8 (0x10 does not set
+0x318); 3 keeps the current clip when coming from 3 or 6-10; 0x12 is refused (state kept)
when the current state is 0x13, or 6 with anim flag 8 still set; 0x14: clip def+0x94,
`Creature_dropLoot(36, 2, 1.6, 0.6, 1.6, 0.25, this, pos, facing, 0)`, slot 28 (0). 4,
0xb-0xf, 0x11 are stored as given (the run switch has no case for them: nothing happens).

Dust burst 0x257ba0 `(this, Vec3 *pos)`: 50 particles of definition 0x8e3468; per particle a
rejection-sampled own-generator triple plus four more `GameObject_rand` draws. It runs from
run code only (footsteps and swings), so each footstep consumes at least 350 own-generator
values; identical on every machine as long as the animation is.

Club drop 0x257ab4 `(this, flag)`: with flag 1 it clears variant bits 0x30, and when that
changes the hide mask creates a 0x248-byte prop with `PhProp_ctor2` from the class model,
then refreshes +0x220. No call or data reference to it exists (xref), so it is dead code as
shipped.

Per-machine: (a) the scan: no hits on run/setState/ctor/helpers; `fx_modelStatusEffects` in
the run head is documented as a cosmetic-seed user (not read here; shared with every
weapon-holder update, so not class-specific). All decisions use `GameObject_rand`.
(b) Cyclops_draw stores nothing in the object. (c) none.

Open: what requests state 2; whether event 0x2 can occur in the death clip (the
constructor marks only 0x80 there); contents of the +0x3d0 block.

#### FatCyclops  (factory name `FatCyclops`; vtable 0x514768; size 0x468)

Functions: ctor 0x257de8, run 0x258200, draw 0x258134, setState 0x258f8c. Everything else is
base.

Constructor: `Creature_ctor(maxHp 10.0, this, typeName, pos, angle, classDef 0x4ff840
(`cyclops3.lmp`), props)`. Weapon1 holder at +0x3d0, hand 1 on with part 0x12. Radius 30,
draw half-width 0x37, turn rate 1.2, speed 0, kind byte 0xb, +0xec = g_simFrame, +0xf4 =
g_simFrame + 300, cflags |= 0x200040000, setState(0), `obj_runEvery60`. No generator draw,
no property, no stats call. Event marks: entry 3 (def+0x1c) 0x1 at 0.3; entry 4
(def+0x24) 0x1 at 0.8; entries 5, 6 (def+0x2c, +0x34) 0x1 at 0.4; entry 8 (def+0x44)
0x1 at 0.3; entry 9 (def+0x4c) 0x1 at 0.6; entry 0x10 (walk) 0x4, 0x8; entry 0xc
(def+0x64 death) 0x80 at 3.5.

Fields: +0x3c8 s32 last attack state (6-0xb, written by setState); +0x3cc s32 "keep turning
toward the target" flag of state 6 (1 at setState 6, 0 after the hit); +0x3d0 Weapon1.

Run (0x258200). Head: slot 16 model, `Creature_processDamage`, `Creature_run`,
`Creature_updateActive` (0 -> return), holder update 0.5, `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.2)`, slot 23 (0).
- 0: seen -> 3; `Creature_isAwayFromHome(this, 3)` -> 1.   1: seen -> 3; else move to dest.
- 3: no target -> 0. Target charging and within 12 inside arc 9000 -> 6. Not charging and
  within 60 inside arc 7000 -> 5; within 60 at any angle -> turn only. Otherwise: if the
  target is not within 180 (any angle) and the clip def+0x8c is not playing -> setState 3
  again (which picks def+0x8c beyond 180, def+0x84 inside); else `Creature_moveToTarget`.
- 5 choose: unless the last attack (+0x3c8) was 0xb, an enemy behind
  (`creature_findEnemyInCone(0, 60, this, facing - 0x7fff, 9000)`) -> 0xb. Target within 60
  inside arc 9000 ahead: state = 6 + `GameObject_rand % 3`, replaced by 6 when equal to the
  last attack. Target within 60 in the cone centred at facing - 18000 -> 10; at facing +
  18000 -> 9. Otherwise -> 3 (when rooted and the target is not within 60: stay).
- 6 swing (clip def+0x1c): settle; turn to target while +0x3cc is set; event 0x1:
  `GameObject_rand % 3` == 0 -> flags 0x80001 else 0x40001; `Creature_hitTargetInArc(0, 60,
  this, facing, 9000, +0xd0, +0xd2, +0xd4, flags, 0)`.
- 7 stomp (def+0x44): event 0x1: dustCloud, sound.
- 8 spit (def+0x4c): event 0x1: THREE projectiles from attach point 1 toward the point
  108 ahead at ground height: velocity = unit direction x 200 + a rejection-sampled
  own-generator unit-ball vector x 48; resource indices 0x14, 0x15, 0x16, 0x18. Sound.
- 9, 10 side swipes (def+0x2c, def+0x34, clip flags 0x4808): settle; event 0x1:
  `Creature_hitTargetInArc(0, 60, this, facing, 9000, +0xd0, +0xd2, +0xd4, flags 1, 0)`.
- 0xb rear gas (def+0x24): event 0x1: gas at attach point 0 moved 36 backwards. Sound.
- 6-0xb leave to 5 when anim flag 8 clears.
- 0x10: attack ready -> 0; else flee (setState sets +0x318 = 60).  0x12: flag 0x10 clear ->
  5.  0x13: -> 3.  0x14: settle, `Creature_deadUpdate(40, this, events, zero vector, 0)`.
- 0x17: stays until the clock passes +0xf4 (clock + 120, set by setState 0x17 together with
  cflag 0x200 and clip def+0x54), then 5. Nothing in this class requests 0x17.
- 2, 4, 0xc-0xf, 0x11, 0x15, 0x16, unlisted -> 0.
- Tail of every frame: footstep events -> `fx_spawn(2, attach point 3 or 2)`.

setState (0x258f8c), non-routine: clears cflag 0x200 first; 6-0xb store the state in
+0x3c8; 0x12 uses clip def+0x5c when the current state is 0x17, else def+0x6c; 0x14:
`Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos, facing, 0)`, holder slot 11 (club
dropped as a prop), death clip def+0x64, slot 28 (0); unknown numbers store state 0.

Per-machine: (a) the scan: only the two footstep `fx_spawn` calls (cosmetic, camera-gated);
nothing else; decisions use `GameObject_rand`. (b) FatCyclops_draw stores nothing (slot 16,
`Creature_draw`, holder draw between the 0x41c14c set and reset). (c) none.

Difference worth keeping: Cyclops footsteps and swings draw the creature's own generator
(dust burst), FatCyclops footsteps do not (`fx_spawn`). Both are run-side, so neither is a
per-machine problem by itself.

Script-driven: scripts/ISLSM1.txt creates one with `generateMonster('broon', 'FatCyclops')`
(line 64); nothing class-specific in the code.

Open: who sets state 0x17 on a FatCyclops.

---

#### Clockwork  (factory names `Clockwork*`; vtable 0x514300; size 0x500)

Functions: ctor 0x24e124, run 0x24e758, draw 0x24e6dc, setState 0x24f90c. Slot 36 is a
unique 8-byte body at 0x3ca394 (outside this range; constant return, value not read).
Everything else is base. Callee just past this range: 0x24fd8c `(this, n, exploded)`, which
selects mesh group n (0..7, different masks per sub-kind) and creates a prop for it
(`pool_new` + `PhProp_ctor2`); only its head was read.

Constructor: `Creature_ctor(maxHp 10.0, this, typeName, pos, angle, classDef 0x4ff260
(`clokwork.lmp`), props)`. Weapon2 holder at +0x3d0 (descriptors +0x420, +0x4b0); hand 1 part
0x17, hand 2 part 0x19. Kind byte +0xb4 = 4, turn rate 0.6, radius 28, +0xec = g_simFrame,
+0xf4 = g_simFrame + 300, cflags |= 0x22000020000, resistance entries +0x5c = 1.0, +0x64 =
1.0, +0x68 = 1.0, +0x6c = 0.75. Sub-kind +0x3c8: 1 by default and for the prefix
`clockworkhammer`; 0 for the prefix `clockworkcutter`, which also gets variant bits 8, scale
0.9 and radius 22. setState(0), `obj_runEvery60`. No generator draw, no property, no stats
call.
All clips are indexed `def + subkind x 0x50 + offset`, i.e. the hammer uses the entries ten
places after the cutter's. Event marks (cutter entry / hammer entry): state 6 clip (3 / 0xd)
0x1 at 0.3; state 7 clip (4 / 0xe) 0x1 at 0.3; state 8 clip (5 / 0xf) 0x1 at 0.2 and
0.4; charge clip (0xc / 0x16) 0x1 at 0.2, 0.4 (hammer also 0.6); death clips: cutter 6, 7,
8 0x2 at 2.75 / 2.25 / 2.5; hammer 0x10, 0x11 0x2 at 2.7 / 2.2 and hammer 0x12 0x4 (not 0x2) at
2.5.

Fields: +0x3c8 s8 sub-kind (1 hammer, 0 cutter); +0x3cc s32 last attack state (6, 7 or 8);
+0x3d0 Weapon2; +0x4f8 s32 cutter: start of the current missile window (clock value); +0xf4
state timer (end of state 8; next missile time in state 9).

Run (0x24e758). Head: `Creature_processDamage`, `Creature_run`, `Creature_updateActive` (0 ->
return), holder update 0.5, `Creature_stepAnim(1.0)`, `Creature_applyKnockback(0.4)`, slot 23
(0).
- 0: seen or away from home (`Creature_isAwayFromHome(this, 1)`) -> 1.
- 1: not seen -> `Creature_moveToDest`; seen: turn, and when the target is within
  visualrange inside arc 8000 -> 3.
- 3: no target -> 0; within 36 inside arc 8000 -> 5; within 280 inside arc 16000 -> 9; else
  `Creature_moveToTarget`.
- 5: target within 36 inside arc 8000: if the last attack +0x3cc was not 6 -> 6; else
  `GameObject_rand & 3`: 0 -> 8, else 7. Not in range: within 36 at any angle -> turn; else
  when not rooted -> 3.
- 6: turn; event 0x1: `Creature_hitTargetInArc(0, 36, this, facing, 8000, +0xd0, +0xd2,
  +0xd4, flags, 0)` with flags 1 (hammer) or 0x40008 (cutter). Anim flag 8 clear -> 5.
- 7: zero-velocity `Creature_moveBy`, turn; event 0x1: same call with flags 0x40001
  (hammer) or 8 (cutter). -> 5.
- 8 sustained (looping clip, +0xf4 = clock + 120): no target -> 0. Turn; event 0x1:
  hammer `Creature_hitAllEnemiesInArc(0, 36, this, 0, 0x7fff, +0xd0, +0xd2, +0xd4, 1, 0)`
  (everything around it), cutter `Creature_hitTargetInArc(0, 36, ..., 8000, ..., 8, 0)`.
  Target no longer within 36 / arc 8000 -> 3; else when the clock passed +0xf4 -> 5.
- 9 charge: no target -> 0. `Creature_moveToTarget`; event 0x1: `Creature_hitTargetInArc(0,
  36, this, facing, 8000, +0xd0, +0xd2, +0xd4, flags 1 (hammer) / 8 (cutter), 0)`.
  Cutter only — missiles: setState 9 sets +0xf4 = +0x4f8 = clock. While the clock is in the
  60 ticks after +0x4f8 and past +0xf4, fire and set +0xf4 = clock + 9 (one shot every 10th
  tick); once 60 ticks have passed, +0x4f8 = clock + 120 (pause), then the next window. A
  shot: muzzle = attach point 2 or 3 (`GameObject_rand & 1`); velocity = 400 toward the point
  300 ahead (horizontal) + a rejection-sampled own-generator unit-ball vector x 60; one more
  own draw picks the sound variant; `pool_new(0x1c8)` + `MissileWeapon_ctor(obj, 0, two
  words from the table g_itemModels (+0x148, +0x14c), muzzle, velocity, heading - 0x4000, owner this,
  stack: 0, 0, (+0xd0) / 7, (+0xd2) / 7, 0, 0, +0xd4, 4, 0)` (instructions at 0x24f010-0x24f080;
  meaning of the stack slots not read).
  Exit: target not charging and within 12 inside arc 8000 -> 5; target no longer within 280
  inside arc 16000 -> 3.
- 0x10: attack ready -> 0; else flee (setState sets +0x318 = 60).  0x12: zero-velocity move;
  anim flag 0x10 clear -> 3.  0x13: -> 3.
- 0x14: zero-velocity move. When object flag 2 is clear and event 0x2 or 0x4 fires:
  - 0x4 (only the hammer's third death clip): `fx_ringBurst(4.0, pos + 36 up)`, sound,
    `world_damageInRadius(40, 180, this, pos, maxDamage = +0xd2, type 0x40840, 0, 0)`, one
    `GameObject_rand` + `decal_add(48, ..., type 9)`, `pool_new(0xbc)` + `LightEffect_ctor`;
  - then the eight body-part props through 0x24fd8c(this, 0..7, exploded) and object flags
    |= 0x4003.
  Then `Creature_deadUpdate(20, this, events, zero vector, noBlood 1)`.
- 2, 4, 10-0xf, 0x11, unlisted -> 0.
- Tail of every frame that reaches the end (all states, including dead): a particle
  definition at 0x8e3328 is constructed on first use, guarded by the global flag 0x4ff340
  (a function-local static, built from RUN code). Hammer only: two steam puffs, each behind
  a `GameObject_rand & 1` draw and object flag 2 clear, at attach points 0 and 1, with
  rejection-sampled own-generator velocities. So a hammer Clockwork consumes at least two
  own-generator values per run call for a cosmetic effect.

setState (0x24f90c), non-routine: 6, 7, 8 record themselves in +0x3cc; 8 sets +0xf4 = clock
+ 120; 9 sets +0xf4 and +0x4f8 to the clock; 0x10 sets +0x318 = 60; 0x12 starts its flinch
clip only when `GameObject_rand & 1 == 0`; 2, 4, 10-0xf, 0x11 and unknown numbers store 0.
0x14: object flags |= 0x4000 (never saved). If object flag 2 was clear, `GameObject_rand % 3
== 0` throws the eight parts at once (0x24fd8c(this, n, 0)) and sets flags 0x4002 — no
corpse, and the run-side explosion test then never passes; otherwise object flag 1 is
CLEARED (the wreck stays solid until it falls apart). Then `Creature_dropLoot(36, 2, 1.6,
0.6, 1.4, 0.25, this, pos, facing, 0)`, a second draw `% 3` picks the death clip (entry 6 +
subkind x 10 + r), slot 28 (0). Net effect for a hammer that keeps its corpse: one death
clip in three carries the 0x4 mark and ends in the radius-damage explosion.

Phases: none.  Script-driven: nothing class-specific in the code; scripts/INNMEDAL.txt keeps
a Clockwork counter (var[0xb0], `bust_clockwork.tex`), not traced.

Per-machine: (a) the scan: no hits. By hand: `fx_ringBurst` (cosmetic seed, per its symbol
note), sounds, particles and the decal are effects; the damage, the props, the light and
all decisions use the own generator and run-side state. The lazily built particle
definition and its guard flag are written from run code only. (b) Clockwork_draw stores
nothing (sets the draw parameter 0x41c14c = 2.0, `Creature_draw`, holder draw, reset).
(c) none.

Open: stack arguments of `MissileWeapon_ctor`; value returned by slot 36; cflag bits
0x2000000000 and 0x20000000000.

---

### Goblin, MaleDarkElf, Froglock, the talking creatures, Ghoul, Gnaw

*Reader's notes for this group.* All statements are Observed at the address given unless marked Inferred / Unknown.
Method for every function: the decompile read in full; disassembly (tools/dis.py) read where
the decompile dropped an argument or the control flow was unclear (those places are named).

### Family: goblins

#### Goblin  (factory prefixes `fgoblin`, `Goblin`; vtable 0x510260; size 0x498)

Functions: ctor 0x26a624, draw 0x26b1d0, run 0x26b27c, slot 12 0x26c9f4, saveState 0x26cb44,
loadState 0x26cc10, setState 0x26ccfc, slot 10 0x26d690, slot 11 0x26d6fc, helper 0x26d7e4
(has-shield test). takeDamage, trigger, touch are the base creature versions.

How the variant is chosen (two independent things):
- Model family, byte +0x490 = last constructor argument: the factory (0x15acc4–0x15ad44)
  passes 1 for a type name starting with `fgoblin` and 0 for one starting with `Goblin`. It
  selects the class definition (0x500298 + family×0xd8: goblin.lmp / fgoblin.lmp with model
  `firegoblin`) and the weapon-part table (0x500448 + family×0x80: goblin_z.lmp / fgob_z.lmp;
  part 1 arrow, 3 staff, 5 bow, 7 shield, 9 axe, 11 sword1, 13 sword2).
- Role, s32 +0x3d4, from twelve prefix tests on the type name in the constructor (calls at
  0x26a8ac–0x26a9d0; the test function ignores case): `goblinrecruit`/`fgoblinrecruit` 0, `…soldier` 1,
  `…leader1` 3 (tested before `…leader`), `…leader` 2, `…archer` 4, `…shaman` 5. Any other
  name leaves 0 (recruit).

Constructor (0x26a624):
- Calls GameObject_rand(this) BEFORE the base constructor (0x26a68c) and passes
  (value mod 14) + 4 as Creature_ctor's max-hp float. At that point the generator word +0x44 has
  not been seeded (GameObject_ctor seeds it later); the block comes zero-filled from pool_new
  (0x15acd8 / 0x15ad20), so the draw is the same constant every time: the first output of the
  generator from state 0 is 0x3c6e = 15470, 15470 mod 14 = 0, argument = 4.0 (Inferred from the
  constants; the arithmetic is mine). The value does not survive anyway: Creature_ctor calls
  Creature_setStats(…, rollHp=1) at 0x10a1d4/0x10a204 whenever a type name is given, which
  rewrites +0x228/+0x22c from the stat table.
- Base call: Creature_ctor(hp, this, typeName, pos, angle, classDef = 0x500298 + family×0xd8,
  props). No Creature_setStats / Creature_scaleStats call of its own.
- +0x28 = 0x28, speed +0xb8 = 60, turn rate +0xb0 = 1.2, radius +0x1c = 18, state 0,
  +0xec = g_simFrame, cflags |= 0x40000 (ordinary blood). Embedded WeaponShield holder at
  +0x3e8 (table 0x50cda0), pointer stored at +0x50.
- Per role (all draws GameObject_rand, in this order: one draw `r` first, then as listed):
  - 0 recruit: r bit 0 → hide-mask bit (draw mod 3)+5; r bit 1 → mask |= 2; hand 1 = part
    (draw mod 3)×2+9 (axe / sword1 / sword2); cflags |= 0x200000000.
  - 1 soldier: r bit 0 → hand 2 = part 7 (shield); mask |= bit (draw mod 3)+5 and 2; r bit 1 →
    mask |= 4; r bit 2 → mask |= 8; draw/65536 < 0.1 → weapon element = (draw & 1)+1; hand 1 as
    recruit; cflags |= 0x200000000.
  - 2 leader: shield always; mask |= 0x1f and bit 8 or 9 (draw & 1); draw/65536 < 0.1 →
    element = (draw & 3)+1; hand 1 as recruit; cflags |= 0x2000000000; float +0x68 = 0.2
    (element [3] of the resistance array +0x5c; meaning of the index Unknown).
  - 3 leader1: as leader, plus scale +0xdc = 1.4, speed 80, radius 25.
  - 4 archer: mask |= 0x4000; draw/65536 < 0.1 → element = (draw mod 3)+1; hand 1 = part 5
    (bow); cflags |= 0x200000000.
  - 5 shaman: mask |= 0x10002; hand 1 = part 3 (staff); cflags |= 0x400000000; tint preset
    +0xa0 = 6; float +0x6c = 0.2 (resistance [4]).
- Weapon element (0x26af0c–0x26affc): for the fire-goblin family any non-zero element becomes
  1. Element 1 → holder slot 2 (builds a fire descriptor, kind 1), 2 → slot 4 (cold, kind 2),
  3 → archer: slot 3 (kind 6, the one that makes ExplodeArrow below), others: slot 6 (shock,
  kind 4), 4 → slot 5 (poison, kind 3). The holder functions (0x3c23e0…0x3c24a0, read) call
  creature_buildElementDamage, which per docs/creatures.md draws the shared seed once
  (constructor = run code, so shared).
- Hide mask → +0x220 through model_buildHideMask; animation `idleb` pushed; obj_runEvery60.
- Animation event markers written with creature_setDefEntryParams(time…, this, entry, bit…)
  (0x118378 read: four (float time, byte event bit) pairs into the animation resource of class
  entry `index`): attack1 (entry 3): 0.3→bit 1. attack2 (entry 4): 0.3→2, 0.6→2, 1.0→1.
  bowattak (entry 6): goblin 0.6→1, 1.1→2; fire goblin 0.9→1, 1.6→2. shmnspell (entry 0x10):
  1.5→1. death (entry 8): 1.0→0x80 and 1.0→2. Then Creature_init.
- Properties read by this class: `dead`, `noloot` (both in setState 0x14). Base constructor and
  Creature_init read the usual creature keys.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | Vec3 | target position stored at the end of states 3 and 4 | state 4 (0x26b8c4) |
| +0x3d4 | s32 | role 0–5 (saved) | everywhere |
| +0x3d8 | s32 | shaman: clock value before which state 0x17 will not leave for another cast (clock + 180) | run 0x26b9c8 |
| +0x3e8 | object | embedded WeaponShield holder | +0x50 |
| +0x488 | s32 | corpse is to sink and be deleted | run state 0x14 |
| +0x48c | float | sink depth so far (+0.35 per frame) | run state 0x14 |
| +0x490 | s8 | model family 0 goblin / 1 fire goblin | ctor, run, draw, setState |
| +0xf4 | s32 | class timer: end of block (state 0x11), end of hold (state 0x17, non-shaman); also written on entering 0 and 4 but not read there | run 0x26bb60, 0x26b990 |

Run head (0x26b27c): Creature_processDamage, Creature_run (non-zero returns), Creature_updateActive
(inactive returns), holder update (holder table offset 0xac, with 0.5 and the part table),
Creature_stepAnim(1.0), Creature_applyKnockback(0.5), V23(0); shaman only: V24 (pick ally).
`ev` below is the stepAnim event mask. Arc/facing arguments are written as in the code.

States:
- 0 idle: archer: V25(1) true → 3. Any role: V25(0) true → 3. Else Creature_isAwayFromHome → 1.
- 1 wander: archer: V25(1) true → 0. V25(0) true → 3. Else Creature_moveToDest (result ignored;
  no other exit).
- 2 run to a point (entered only from slot 12, destination +0x104 = the damaged goblin's
  position): archer V25(1) true → 0; V25(0) true → 0; else Creature_moveToDest, and when it
  returns 0 → 0.
- 3 chase (0x26b530; disassembly read). No target → 0.
  - Archer first: canSee(0, 80, arc 0x7fff, ray 0) → V27(0x10); else canSee(0, 400, arc 6000,
    ray 1) → V27(7); else Creature_moveToTarget. The archer then ALSO runs the melee block below
    in the same frame (0x26b5dc falls into 0x26b668 for every role except 5), so a second V27
    or a move call can follow the first.
  - Shaman only: canSee(0, 60, arc 0x7fff, 0) → 0x10; else canSee(0, 400, arc 6000, ray 1) → 8;
    else Creature_moveToTarget. Returns.
  - Melee block (roles 0–4): (A) canSee(0, 30, arc 6000, 0): if the goblin has its shield out
    (0x26d7e4) and Creature_isTargetAttackingMe and GameObject_rand mod 3 == 0 → 0x11 (block),
    otherwise → 6 (attack). (B) else canSee(0, 30, arc 0x7fff, 0) → Creature_turnToTarget only.
    (C) else, role > 0 and creature_allyInLineOfFire(400, radius×3, this, target, 0) → 0x17.
    (D) else GameObject_rand mod 30 == 0 and
    world_countLivingNonplayerCreaturesInBox(target radius × 1.75, target position) < 3: let a =
    atan2 angle from the goblin to the target; if (a − target facing + 0x3fff) as unsigned
    < 0x7fff → 4, else Creature_moveToTarget. (E) else Creature_moveToTarget.
    Always ends by copying the target position to +0x3c8.
- 4 (run in; entered from 3-D — Inferred geometry: the goblin is then in the half-plane behind
  the target):
  no target → 0. canSee(0, 30, arc 6000, 0) → 6. Else GameObject_rand mod 30 == 0 and the
  target's 2-D distance from the stored position +0x3c8 is < 1.0 (target stood still since the
  last frame) → 3. Else Creature_moveToTarget. Stores the target position.
- 5 between attacks: no target → 3. Archer: canSee(0, 400, arc 6000, ray 1) → 7. Shaman: same
  test → 8. Roles 0–3: canSee(0, 30, arc 6000, 0) → 6. Else when Creature_isNotRooted → 3.
- 6 melee (0x26bb7c): with a target, on ev & 3 (either marker):
  Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags, descriptor) where descriptor
  = holder slot 17 (hand 1) = the holder's element descriptor (holder+0x50) and flags = 0x8
  when the target has object flag 0x40, 0x40008 otherwise. If ev bit 0 is also set:
  GameObject_rand mod 5 == 0 → V27(3). While animation flag 8 is set: Creature_turnToTarget;
  when it clears → 3. attack2 therefore tests three times (markers at 0.3, 0.6, 1.0).
  Animation: recruit always attack1; other roles attack1 or attack2 by GameObject_rand & 1
  (setState 6).
- 7 bow shot (0x26bcc4): aim point = 300 ahead, replaced by Creature_leadTargetPoint(400).
  On ev bit 0: hand 2 emptied; muzzle = model_getAttachPoint (start (x, y, z + height×0.5 + 12));
  velocity = unit(aim − muzzle) × 400 + (random point in the unit sphere, rejection-sampled with
  3 GameObject_rand draws per try) × 40; one more GameObject_rand & 3 picks the sound
  `swsh_arrow%d`. Projectile by the holder's element (slot 16, hand 1):
  2 → ColdArrowProjectile (pool 0xb0, ctor 0x2d718c, args pos, velocity, owner,
  (int)float 0x4f714c, SKILL[44 ColdArrow] pointer); 1 → FireArrowProjectile (0xb0, 0x2d6440,
  SKILL[43 FireArrow]); 6 → ExplodeArrowProjectile (0x74, 0x2dafe0, SKILL[47 ExplodeArrow]);
  anything else → MissileWeapon (pool 0x1c8, ctor 0x150ee4) with kind 0, the two words at
  0x3e9ce8/0x3e9cec (both 0 in the file), pos, velocity, angle atan2(vy, vx) − 0x4000, owner,
  and stack arguments (disassembly 0x26c154–0x26c1a8) damage +0xd0 / +0xd2, the third stat
  +0xd4, the constant 4 and a null descriptor. The skill pointers are only handed to the
  constructors; no skill-table call is made here.
  On ev bit 1: hand 2 = part 1 (arrow back in the hand). While the animation plays: V26(0, aim).
  When it ends → 3.
- 8 shaman cast (0x26c224): every frame holder slot 9 sets a colour (0, 0x80, 0xff, 0x96) on
  hand 1; aim point as in 7. On ev bit 0, with a target:
  action = GameObject_rand mod 3; corpse = creature_findCorpseOfClass(300, this);
  if a corpse exists and GameObject_rand/65536 < 0.5 → action 3; otherwise, if the ally handle
  +0x238 holds a Goblin (RTTI test) whose hand-1 part is not 3 (not a staff) and whose holder
  element (slot 16) is 0 → action 4. aimAngle = creature_aimAngleAt(350, this, target).
  - 0: skill cast (offset 0x14) of SKILL[7 FireStorm] (fire goblin) or SKILL[58 FrostStorm],
    args (V35(), this, aim point, aimAngle).
  - 1: cast SKILL[57 ShockOfFire] (fire goblin) or SKILL[23 ShockOfFrost] from
    (x, y, z + height×0.5), aimAngle.
  - 2: cast SKILL[37 Shock], same origin.
  - 3: corpse->V32(1) (revive).
  - 4: cast SKILL[13 FireWeapons] (fire goblin) or SKILL[14 ColdWeapons] with level V35() of
    the shaman, CASTER argument = the ally, position = the ally's, facing = the shaman's; the
    returned spell is linked with creature_addSpell(ally, spell).
  No offset-0x0c "can cast" test and no 0x44/0x5c/0x64 query anywhere in this class.
  Then +0x3d8 = clock + 180. Every frame V26(0, aim); when the animation ends → 0x17.
- 9–0xf, 0x15, 0x16: return (unused).
- 0x10: Creature_isAttackReady → 0, else Creature_fleeFromTarget(this, 0). setState 0x10 sets
  +0x318 = 60 and run speed.
- 0x11 block: when clock > +0xf4 → 3. setState 0x11: block animation, +0xf4 = clock + 120,
  cflags |= 0x200 (blocking).
- 0x12 hit reaction: clears +0x2e8 when the knockdown track is present; waits while animation
  flags 0x30 are set; then → 3.
- 0x13: Creature_isNotStunned → 0.
- 0x14 dead: Creature_deadUpdate(20, this, ev, zero vector, 0); ev bit 1 and not hidden →
  object flag |= 1. If +0x488 and the animation has ended (flag 0x80): +0x48c += 0.35,
  +0x3c = z − +0x48c, and past 24 → object flags |= 0x4002, obj_delete.
- 0x17 hold: no target → 0. Shaman: canSee(0, 60, facing argument 0, arc 0x7fff, 0) → 0x10;
  else clock > +0x3d8 → 3. Others: clock > +0xf4 → 3; else
  creature_allyInLineOfFire(400, radius×3, this, target, 1) == 0 → 3. Always
  Creature_turnToTarget. setState 0x17: +0xf4 = clock + 240 + (GameObject_rand mod 240).

setState (0x26ccfc), non-routine:
- Every accepted change clears cflag 0x200 before the switch (0x26cd30). Consequence
  (Inferred): the `blockhit` branch of case 0x12, which re-reads that flag at 0x26d284, cannot
  be taken.
- 0: +0xf4 = clock + 120 + (GameObject_rand mod 60). 1: speed 60 (leader1 80), walk.
  2, 4, 0x10: speed 150 (leader1 200), run. 4 entered from 3 also sets
  +0xf4 = clock + 40 + (GameObject_rand mod 120) (never read in state 4).
- 3: strcmp(g_levelName 0x41b721, `firmedal`) == 0 → speed 150/200 and the run animation;
  any other level → speed 60/80 and the WALK animation (0x26cee4–0x26cf7c). So outside that one
  level goblins close in at walking speed. Whether the stored level name has that exact case:
  not checked.
- 0x12: request ignored (state kept) when the goblin is stunned (0x13) or in state 6 with the
  attack animation still playing. With knockback bits (+0x2dc & 0x3c0000): only if the hit
  direction +0x2e0 minus facing is outside −0x688f…0x688f does it start the knockdown animation;
  otherwise one of hit1–hit3 by GameObject_rand mod 3.
- 0x14: unless property `dead` is set, counts objects with (flags & 0x68) == 0x28 in a ±96
  box; 3 or more → +0x488 = 1 (this corpse will sink). If not hidden: object flag 1 cleared and
  holder slot 11 for both hands (drops the held parts as props). `dead` → object flag |= 1.
  Death animation. If cflag 0x100000000 is clear: Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25,
  this, pos, facing, 0); archer: GameObject_rand() < 6000 (of 65536) and `noloot` unset →
  loot_spawnNamedItem(pos, `arrows`). Then V28(0).

Other overrides:
- Slot 12 (0x26c9f4), arguments (radius, kind, position, source):
  kind 0 with a Goblin source while this goblin is in state 0 or 1 → V27(2) and destination
  +0x104 = position. Kind 0 is sent by Creature_processDamage (0x110d90–0x110dc8) around any
  creature that has pending damage, radius 600, ONLY WHEN g_numPlayers == 1. So goblins run to
  a hurt goblin in one-player games only (Observed condition; the gameplay reading is Inferred).
  world_notifyObjectsNear 0x11a2b8 (read) has no test that skips the source, so the hurt
  goblin presumably receives the call too (Inferred).
  kind 2 with a source, shield out, state 3 or 5, and the source within ±9999 angle units of
  the facing → V27(0x11) (block). Kind 2 is sent from Player_run (call set up at 0x1a8f08–0x1a8f20,
  under an object-flag-0x20000-clear test) to the creature a player's missile is aimed at
  (Inferred from the surrounding code; Player_run not read). A second site (0x1aa57c) sends
  kind 3, which no class in this note handles.
- Slot 10 (0x26d690, hit terrain): in state 0x12 with animation flag 0x20 clear, starts the
  `knokinto` animation (flag 0x20).
- Slot 11 (0x26d6fc, touched list): same animation rule; then for every touched object that
  is a Container (RTTI) calls its slot 2 with (1.0, this, 1): a goblin knocked into a barrel
  damages it.
- 0x26d7e4: true when hand 2 holds part 7 and the hand-2 bit of the holder is on.
- saveState 0x26cb44: creature record + 12 bytes (role, hand-1 part, hand-2 part).
  loadState 0x26cc10: restores them; a goblin loaded in state 0x14 has hand 2 emptied.
  Not saved by this class: hide mask, weapon element, +0x490.

Phases: none (no hit-point test). Script-driven: nothing class-specific found (no grep done
for goblin type names in scripts beyond what the factory needs).

Per-machine:
(a) None found (the scan on run, setState, slots 10/11/12, 0x26d7e4, save/load: no hits; by
    reading: every decision uses GameObject_rand; setState reads only g_levelName). The holder
    update called from run (0x11b2a8, creatures area, read) is gated by isNearView(480) and only
    calls fx_modelStatusEffects (not read).
(b) No. Goblin_draw calls Creature_draw and the holder draw (offset 0x94) and stores nothing.
(c) No.
Holder slot argument: slots 2–8 take a hand selector (0 both, 1 hand 1, 2 hand 2; read in
Weapon2 0x3c1fc8 ff. and WeaponShield 0x3c23e0 ff. — WeaponShield only has a hand-1
descriptor).
Open: meaning of cflags 0x200000000 / 0x400000000 / 0x1000000000 / 0x2000000000 (one of the
four is set per variant here and in MaleDarkElf 0x25bab4; not traced) and of +0x68/+0x6c; what
creature_allyInLineOfFire's last argument does on the frames when it does not sweep.

Corrections to docs/monsters.md for this class: FireStorm (7) and FrostStorm (58) are CAST
(offset 0x14, through a pointer variable at 0x26c4cc ff.), not "passed to a constructor"; only
FireArrow / ColdArrow / ExplodeArrow pointers go to constructors.

### Family: dark elves (male)

#### MaleDarkElf  (factory prefix `maledarkelf…`; vtable 0x5148b0; size 0x4f8)

Functions: ctor 0x25afd8, variant-flag helper 0x25bab4, draw 0x25bb80, run 0x25bbe4,
saveState 0x25cdd0, loadState 0x25ced4, slot 12 0x25cfc0, setState 0x25d084. The shield test
0x25dc00 used by slot 12 lies just past this range (read: true when the hand-2 part is 0x2e,
0x30 or 0x32, the three shields). takeDamage / trigger / touch / slots 10, 11: base versions.

Constructor: Creature_ctor(10, this, typeName, pos, angle, classDef 0x4ffa68, props); embedded
Weapon2 holder at +0x3d0 (table 0x50ce70) → +0x50; turn rate 1.2, radius 15, +0x28 = 0x14,
+0xb4 = 9, **speed +0xb8 = 0** (the walk/run tracks are started with flag 0x800; that the
movement is animation root motion is Inferred), +0xec = g_simFrame.
Role byte +0x3c8 = GameObject_rand mod 6, then overridden by a type-name prefix (case ignored):
`maledarkelfarcher` 0, `…spear` 1, `…soldier` 2, `…knight` 3, `…star` 4, `…assassin` 5. A name
matching none keeps the random role.
Per role (GameObject_rand draws in this order; parts are class-definition entry numbers):
- 0 archer: hide mask = bit (draw & 3) | 0x8000000; hand 1 = 0x40 (bow); draw/65536 < 0.1 →
  element = (draw & 3) + 1.
- 1 spear: mask = bit (draw mod 6) + 4; hand 1 = 0x34 (spear); 10 % → element (draw & 3) + 1.
- 2 soldier: mask = bit (draw mod 5) + 16; hand 1 = 0x3e (one-hand sword); hand 2 = shield
  0x2e + 2×(draw mod 3); 10 % → element (draw & 3) + 1.
- 3 knight: mask = bit (draw mod 6) + 10; hand 1 = 0x3a (two-hand sword); 10 % → element
  (draw mod 5) + 1.
- 4 star: mask = bit (draw mod 6) + 21; hands = 0x36 / 0x38 (two throwing stars); no element.
- 5 assassin: mask as star; hands = 0x3e / 0x3c; 10 % → element (draw mod 6) + 1.
Then 0x25bab4(this): tint +0xa0 = 0; assassin gets float +0x64 = 0.2 (resistance [2]); clears
cflags 0x3600000000 and sets exactly one of 0x1000000000 (mask & 0x4112e6b), 0x2000000000
(mask & 0xd100), 0x400000000 (mask & 0x1a00014), 0x200000000 (otherwise).
Element switch (jump table 0x545140, disassembly 0x25b658–0x25b718), holder called with hand
selector 0 (both hands): 1 → slot 2 (fire, kind 1); 2 → slot 4 (cold, 2); 3 → slot 5 (poison,
3); 4 → archer: slot 3 (kind 6), others: slot 6 (shock, 4); 5 → cflags |= 0x200000000000 and
tint +0xa0 = 8; 6 → cflags |= 0x800000000000 and tint 8 (no descriptor for 5 and 6).
Then hide mask, setState(0), obj_runEvery60, animation event markers
(creature_setDefEntryParams, (time→event bit)): one-hand attacks (entries 0x13–0x15), two-hand
attacks (0xd–0xf), spear attacks (0x1c, 0x1d), asas_atak2 (4): 0.1→1. asas_atak1 (3): 0.1→1,
0.2→1, 0.4→1 (three hit tests). bow_atak1 (0x22): 0.2→1, 1.1→2. asas_throw1 (0xb): 0.5→2,
0.6→4, 1.0→1. asas_throw2 (0xc): 0.2→2, 0.6→1. knokdown1–4 (0x26, 0x28, 0x2a, 0x2c): 1.0→0x80.
Creature_init last. Properties read by the class itself: none.

Fields: +0x3c8 s8 role (saved); +0x3d0 embedded Weapon2 holder; +0xf4: in state 0 the clock
value after which the elf starts wandering; in 5 the end of the hold; in 6–9 a countdown of
frames after the animation; in 0x11 the end of the block.

Run head: processDamage, Creature_run, updateActive (inactive returns), holder update (offset
0xac; 0.5, classDef), stepAnim(1.0), applyKnockback(0.8), V23(0).
States (disassembly read for 0, 1, 3 and the tails of 6–9):
- 0: V25(0) → 3; else Creature_isAwayFromHome → 1; else clock > +0xf4 → 1.
- 1: V25(0) → 0; else Creature_moveToDest.
- 2, 4, 0xa–0xf: return.
- 3: no target → 0.
  - Roles 1, 2, 3, 5: canSee(0, 36, arc 6000, 0) → 6. Else
    creature_allyInLineOfFire(400, radius×3, this, target, 0) → +0xf4 = clock + 240 +
    (GameObject_rand mod 240), V27(5). Else canSee(0, 30, arc 0x7fff, 0) → turnToTarget. Else
    moveToTarget.
  - Role 4: canSee(0, 30, arc 6000, 0) → 6; canSee(0, 30, arc 0x7fff, 0) → turnToTarget;
    canSee(0, 400, arc 2000, ray 1) → GameObject_rand & 1 ? 7 : 8; else moveToTarget.
  - Role 0: creature_findEnemyInCone(0, 80, this, facing 0, arc 0x7fff) → 0x10;
    canSee(0, 400, arc 2000, ray 1) → 9; else moveToTarget.
- 5 (hold; also the filter's redirect while the root timer runs): roles 1, 2, 3, 5 and 4:
  canSee(0, 30, arc 6000, 0) → 6. Role 0: canSee(0, 400, arc 2000, ray 1) → 9. Else, once
  Creature_isNotRooted: clock > +0xf4 → 3; otherwise with a target and
  creature_allyInLineOfFire(…, 1) == 0 → 3.
- 6 melee: Creature_moveBy(this, zero vector) every frame. With a target, on ev bit 0:
  min/max = +0xd0/+0xd2; if cflag 0x800000000000 (element roll 6) and GameObject_rand/65536
  < 0.5 both are DOUBLED and Creature_emitLinkParticles(this, target) runs (100 particles,
  GameObject_rand). Creature_hitTargetInArcEdge(0, 36, this, facing, arc 6000, min, max, +0xd4,
  flags 8, descriptor = holder slot 17 hand 1). While the animation plays: turnToTarget. Once it
  has ended, roles 2, 3, 4, 5 set cflag 0x200 (blocking) and +0xf4 counts down one per frame.
  Exit to 3 when +0xf4 ≤ 0 — tested every frame, also while the animation is playing
  (0x25c2d8–0x25c300), and setState 6 sets +0xf4 = GameObject_rand mod 20: a draw of 0 sends
  the elf back to 3 on the first frame of the attack (consequence Inferred).
- 7 / 8 (star throw, role 4) and 9 (bow, role 0), common code 0x25c304. No target → V27(0).
  Aim = 300 ahead, replaced by Creature_leadTargetPoint(400).
  ev bit 0: archer: hand 2 = part 0x42 (arrow); star: hands restored (0x36, 0x38).
  ev bit 1 or 2 (mask 6) = release. Velocity = unit(aim − muzzle) × 400 + random unit-sphere
  point × 40 (GameObject_rand, rejection), one GameObject_rand & 3 for the sound.
  - Star: muzzle = model_getAttachPoint with facing − 0x4000 and attach index (ev>>1)&1;
    hand 1 emptied when ev bit 1 is set (hand 2 when bit 0 is set in the same frame);
    MissileWeapon (pool 0x1c8, ctor 0x150ee4) kind 0, model words classDef+0x1b4 / +0x1bc
    (star_1), angle atan2(vy, vx) − 0x4000, owner, stack arguments (0x25cbf4–0x25cc60) min =
    +0xd0, max = +0xd2 / 2, stat +0xd4, constant 4, null descriptor; then missile byte +0xfe = 2
    and word +0xfa = 3000.
  - Archer: muzzle (x, y, z + 60); hand 2 emptied; by holder element (slot 16, hand 1), elemental
    projectiles start at (x, y, z + height×0.5 + 12):
    2 → ColdArrowProjectile (0xb0, ctor 0x2d718c, level (int)float 0x4f714c, SKILL[44 ColdArrow]);
    1 → FireArrowProjectile (0xb0, 0x2d6440, SKILL[43 FireArrow]);
    3 → PoisonArrowProjectile (0xb0, 0x2d8c40, SKILL[45 PoisonArrow]);
    6 → MultiFire: n = SKILL[46 MultiFire] table offset 0x5c called with (2, level, 10) at
    0x25c984;
    heading toward the aim point clamped to facing ± 1000; n MultiFireProjectile objects (pool
    0x78, ctor 0x2da164, args pos, angle, owner, level, skill) at angles heading − n×250 +
    1000×k;
    other → MissileWeapon kind 0 (words 0x3e9ce8/0x3e9cec), min +0xd0, max +0xd2 / 2, +0xd4, 4.
    Skill pointers go to constructors only; the single skill-table call is MultiFire's 0x5c.
  While the animation plays V26(0, aim). After it: archer with
  creature_findEnemyInCone(0, 80, facing 0, arc 0x7fff) → V27(0x10); +0xf4 −= 1; ≤ 0 → 3.
  Same first-frame exit as state 6 (setState sets +0xf4 = GameObject_rand mod 15).
  Animations: 7 = asas_throw2 (one star), 8 = asas_throw1 (two stars), 9 = bow_atak1.
- 0x10: Creature_isAttackReady → 0, else fleeFromTarget. setState: +0x318 = 60.
- 0x11 block: clock > +0xf4 → 3. setState: cflags |= 0x200, +0xf4 = clock + 120.
- 0x12: waits for animation flag 0x10 to clear → 3. 0x13: not stunned → 0.
- 0x14: Creature_deadUpdate(20, this, ev, zero, 0) only.
setState non-routine: cflag 0x200 cleared on every accepted change (so the block-hit branch of
case 0x12 is unreachable, as in Goblin — Inferred); 3 clears cflag 0x8000000; 0x12 is ignored
while stunned or while a state-6 animation plays; 0x14: death animation = knokdown1–4 by
GameObject_rand & 3, Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25, this, pos, facing, 0) with no
test of cflag 0x100000000, holder slot 11 for both hands when not hidden, V28(0).
Slot 12 (0x25cfc0): kind 2 only: has a shield (0x25dc00), state 3 or 5, source within ±9999 of
the facing → V27(0x11). (Only role 2 carries a shield.) Kind 0 is ignored.
saveState: creature record + 16 bytes (role, hand-1 part, hand-2 part, hand-1 element kind).
loadState: restores them (element through holder slot 8, hand 1, which calls
creature_buildElementDamage) and re-runs 0x25bab4. Not saved: hide mask, the tint-8 variants'
cflags.
Phases: none. Script-driven: nothing class-specific found.
Per-machine: (a) none found (the scan on run, setState, slot 12, 0x25bab4, save/load: no hits;
all draws are GameObject_rand). (b) draw (0x25bb80) = Creature_draw + holder draw, stores
nothing. (c) no.
Open: what cflags 0x200000000000 / 0x800000000000 do outside this class (the second doubles
melee damage half the time here); MissileWeapon fields +0xfa/+0xfe.

### Froglock

#### Froglock  (factory prefix `Froglock`; vtable 0x510780; size 0x468)

Functions: ctor 0x263e1c, draw 0x264278, run 0x264314, saveState 0x264fb8, loadState 0x265070,
setState 0x265150; helper 0x265754 (just past this range, read). takeDamage, trigger, touch,
slots 10–12: base versions.
The two functions at the start of the range, 0x263d70 and 0x263dfc, are NOT Froglock code:
they are the static-initialiser pair of the preceding FireBomblet file (0x263dfc calls
0x263d70(1, 0xffff), which constructs the particle definition 0x8e35a8 with
particleDef_ctor(4, 6, −3.3, …); the only other reference to 0x8e35a8 is FireBomblet_run at
0x262c64).

Constructor: Creature_ctor(10, this, typeName, pos, angle, classDef 0x4ffe28, props); embedded
Weapon1 holder at +0x3c8 (table 0x50cf40) → +0x50; +0x28 = 0x23, turn rate 1.2, radius 22,
speed +0xb8 = 0, +0xb4 = 9, forward draw offset +0xe0 = −6, cflags |= 0x200000000,
float +0x68 = 0.15, +0xec = g_simFrame, state 0, animation idle1, obj_runEvery60.
Variant = the weapon part in hand 1 (there is no role field; the code asks the holder, slot 15):
- default: part 0x12 (trident); GameObject_rand/65536 < 0.1 → element = (draw & 1) + 1; next
  draw & 1 → hide mask = bit (draw mod 3), else mask 0.
- type name starting `froglockblowgun`: part 0x10 (blowgun); 10 % → element (draw & 1) + 1;
  hide mask 8.
Element 1 → holder slot 5 (poison, kind 3), element 2 → slot 4 (cold, kind 2), hand 1.
Animation markers: pokeatak (entry 0xc), blowatak (3), sniper (0xd): 0.3→bit 1; death1, death2
(4, 5): 1.0→0x80. Properties read by the class: none.

Fields: +0x3c8 embedded Weapon1 holder; +0x460 u8 "was standing in water at the end of the
last run call" (copy of cflag 0x2000000000000000); +0x461 u8 "water 130 units ahead" (sampled
every 8th frame, staggered by the serial +0x230, with water_test(12, world, point, 0));
+0x462 u8 previous value of +0x461; +0xf4: state 0 wander time, states 7/8 countdown.
Helper 0x265754: returns 1 when the froglock has just entered water (+0x460 == 0 and the
cflag set), or when +0x462 != 0 and +0x461 == 0 (water ahead has just ended); the callers
then call V27 with the CURRENT state so that setState re-picks walk1 / swim.

Run head: processDamage, Creature_run, updateActive (inactive returns), holder update,
stepAnim(1.0), applyKnockback(0.5), V23(0), the water sample above. Every path through the
switch ends by updating +0x462 and +0x460 (0x264f70).
States:
- 0: V25(0) → 3; Creature_isAwayFromHome → 1; clock > +0xf4 → 1.
- 1: V25(0) → 0; else Creature_moveToDest, then 0x265754 true → V27(1) (which also picks a
  new wander destination).
- 3: no target → 0.
  - Trident: canSee(0, 40, arc 6000, 0) → 6. Else if NOT canSee(0, 300, arc 0x7fff, 0) and
    canSee(0, 450, arc 1000, 0) → 0x17 (jump; i.e. target 300–450 away and nearly dead ahead).
    Else canSee(0, 40, arc 0x7fff, 0) → turnToTarget; else moveToTarget and 0x265754 → V27(3).
  - Blowgun: canSee(0, 100, arc 0x7fff, 0) → 0x10. canSee(0, 400, arc 6000, 0) → 7 when the
    standing-in-water cflag is clear, 8 when set. Else canSee(0, 400, facing 0, arc 0x7fff, 0)
    → turnToTarget; else moveToTarget and 0x265754 → V27(3).
- 5: blowgun: canSee(0, 400, arc 6000, 0) → 7; trident: canSee(0, 40, arc 6000, 0) → 6; else
  Creature_isNotRooted → 3.
- 6 poke: Creature_settle every frame; with a target on ev bit 0:
  Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags 8, holder descriptor hand 1).
  Animation ended → 5.
- 7 (blowatak over idle3) / 8 (sniper over idle4): no target → V27(0). Aim 300 ahead /
  Creature_leadTargetPoint(400). On ev bit 0: muzzle (x, y, z + 48), velocity =
  unit(aim − muzzle) × 400 + random unit-sphere point × 40 (GameObject_rand, rejection), one
  GameObject_rand & 3 for the sound. By holder element (slot 16): 2 → ColdArrowProjectile
  (pool 0xb0, ctor 0x2d718c, from (x, y, z + height×0.5 + 12), level (int)float 0x4f714c,
  SKILL[44 ColdArrow]); 3 → PoisonArrowProjectile (0xb0, 0x2d8c40, SKILL[45 PoisonArrow]);
  other → MissileWeapon (0x1c8, 0x150ee4) kind 0 from the muzzle with stack arguments
  (0x264db0–0x264e18) min +0xd0, max +0xd2 / 2, +0xd4, 4, null descriptor. Skill pointers go to
  constructors only; no skill-table call. V26(0, aim) every frame. After the animation:
  blowgun and canSee(0, 100, arc 0x7fff, 0) → V27(0x10); +0xf4 −= 1. Exit to 3 when
  +0xf4 ≤ 0, tested every frame (setState: +0xf4 = GameObject_rand mod 15, so a draw of 0 ends
  the state on its first frame — consequence Inferred, same pattern as MaleDarkElf).
- 0x10: 0x265754 true → V27(0x10) again (setState 0x10 re-arms +0x318 = 60); else
  Creature_isAttackReady → 0; else fleeFromTarget.
- 0x12: wait for animation flag 0x10 → 3. 0x13: not stunned → 0.
- 0x14: Creature_deadUpdate(25, this, ev, zero, 0).
- 0x17 jump: Creature_settle; wait for animation flag 0x10 → 3. setState 0x17 starts the jump
  track with flags 0x810. No hit helper is called in this state: the jump itself does no
  damage (Observed absence in 0x264ef0–0x264f1c).
- 2, 4, 9–0xf, 0x11, 0x15, 0x16: nothing.
setState non-routine: no cflag change. Walk/chase/back-off animation is swim only when the
standing-in-water cflag is set AND +0x461 is set, walk1 otherwise; idle is idle4 in water.
Case 3 calls canSee(0, 400, arc 6000, 0) itself to choose a standing or moving animation for
the blowgun variant. 0x12 is ignored in states 0x13, 0x17 and in 6 while its animation plays.
0x14: death1/death2 by GameObject_rand & 1, Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25, this,
pos, facing, 0) without a cflag test, holder slot 11 hand 1 (drop the weapon), V28(0).
saveState: creature record + 5 bytes (hand-1 part u32, element kind u8). loadState: restores
both (element through holder slot 8); a froglock loaded dead has hand 1 emptied.
Phases: none. Script-driven: nothing class-specific found.
Per-machine: (a) none found (the scan on run, setState, save/load, 0x265754: no hits; the water
sample uses g_simFrame, the serial and the world; all draws GameObject_rand). (b) draw
(0x264278) = Creature_draw + holder draw; stores nothing. (c) no.
Open: +0x460–+0x462 are not in the save record and are zero after load (not traced further).

### Family: talking / friendly creatures (NPC, Rondo, Gnome, GnomeNavigator)

#### The `exclamation` script run from draw code — what was established

1. **0x4f8450 is a pointer, not a structure.** All four draw functions load the word at
   0x4f8450 and read +0x34 of the object it points to (NPC_draw 0x29e5ac–0x29e5b8). The
   pointer is the one world camera object: its only writer is game_initCamera (gxref:
   0x1e6bb0 W). So the test is **camera mode (+0x34) == 1**, "follow", the normal gameplay
   mode (docs/gameplay.md section 5 has the mode list).
2. **Writers of camera +0x34** (method: every store with displacement 0x34 in the camera code
   0x203000–0x207800 from disasm/text.asm, plus a scan of the whole text for a store to +0x34
   through a register loaded from 0x4f8450 within 60 instructions — none of the second kind):
   - Camera_setMode 0x2072e8 (the store is at 0x207304). Its ten call sites pass only 0 or 1:
     cut_start 0x19b5b0 → 0; cut_runFrame 0x199f5c → 1 (after cut_end);
     menu_openInventory 0x1c1728 → 0; inventory_close 0x1c5154 → 1;
     shop_openOrStock 0x1c880c → 0; frontend_stop 0x1e21a0 → 1; 0x22f728 (in 0x22f6a8, clears
     the dialog data and the menu mutex) → 1; Camera_init 0x2071e8 → 1;
     Camera_pushState 0x207264 → 0 (callers shop_openOrStock 0x1c87f4 and the dialog camera
     setup 0x22ef4c); Camera_popState 0x207290 → 1 (callers shop_openOrStock 0x1c8750,
     shop_close 0x1d0b44).
   - Camera_updateFree 0x20440c stores 1 (leaving a free-fly mode on a pad-0 button pair).
   No code that stores 2–5 was found by this method (Unknown how modes 2–5 are entered).
   Consequence (Inferred): the flag is 0 on a machine while ITS inventory or shop screen, a
   conversation camera or a cutscene is up, and 1 otherwise — it is per-machine state, on top of
   draw functions already running a per-machine number of times.
3. **Extra conditions differ by class.** Gnome_draw 0x2691f0, GnomeNavigator_draw 0x26a000 and
   Rondo_draw 0x29f28c are the same code (decompiles identical apart from string addresses):
   Creature_draw, then — camera mode 1 and an `exclamation` property — script_runByName(value)
   on every drawn frame; result 1 draws the icon (`exclaim.tex` from icons.lmp) at the object
   position + 72 up (48 with property `exclamationShort`), alpha pulsing with g_simFrame.
   NPC_draw 0x29e3ec adds two camera tests first: the plane test
   (pos − 0x44f038)·(0x44f148, 0x44f158, 0x44f168) ≤ 0 must hold or nothing at all is drawn
   (branch 0x29e4ac), and the script runs only when the NPC is MORE than 240 units from the
   camera position (300 while g_cutsceneActive; compare 0x29e530, call 0x29e5f4). Within that
   distance no marker is drawn and no script runs.
4. **Can the script change shared state?** script_runByName 0x1ed694 (read) looks the name up
   and calls scr_interpret on the level's machine with no restriction; nothing marks the call as
   read-only (docs/script.md P1 says the same of the interpreter). So any built-in with side
   effects in such a script would run a different number of times per machine.
5. **Which scripts are used as `exclamation` values.** Not determinable from disk: objects.ob
   exists for four levels only (DRUNARE, DRUNARM, DRUNDAR, PVPARENA) and none of them contains
   the string `exclam`, nor an NPC, Gnome or Rondo. Fallback, every script whose name contains
   "Exclam" (case-insensitive grep of scripts/*.txt for label lines): exactly two, both in
   INNOVAT1:
   - `check1Exclam`: getEvil, getv('finishedMission'), playerHasItem('coppersprocket'),
     getv('talkedToGnome'); returns 0/1. Reads only.
   - `check2Exclam`: same four calls with the getEvil test inverted. Reads only.
   Their only callers are two auto-named snippets, `return67c` and `return288c`, each a single
   callScript — these are the likely property values (Inferred). No setv, getRand or object
   creation in any of the four. (docs/script.md notes that getv on an unknown name appends it
   to the variable table; both names here are set elsewhere in the same file.)

#### NPC  (factory name `NPC`; vtable 0x50f590; size 0x480)

Functions: 0x29dcb8 (stores 0 to global 0x501b78), ctor2 0x29dcc4, ctor 0x29df04, saveState
0x29e214, loadState 0x29e2a4, draw 0x29e3ec, run 0x29ea40, takeDamage 0x29eeb8, slot 3
0x29eed0, setState 0x29efcc. Slot 16 (model) is 0x3c4c80 = the word at +0x428. Interact
(slot 14) and prompt (slot 13) are the base creature versions 0x116bd8 / 0x116d50.

Constructor 0x29df04 (the factory's, call 0x15d31c): Creature_ctor(8, this, typeName 0, pos,
angle, classDef 0, props) — no type name, so no Creature_setStats; object flags |= 0x1100008
(dead 0x8, interactable 0x100000, friendly 0x1000000); +0x28 = 0x24, radius 20, turn rate 0.5,
speed 60, state 0, +0x478 = 0. Properties:
- `name` → +0x434 (copied; default the 4 bytes "npc").
- `lumpname` → +0x3c8 = "<value>.lmp", else "<name>.lmp". If the result is exactly `npc.lmp`
  the object calls obj_delete on itself and the constructor stops there.
- `wakname` → +0x3e8 = "<value>.vif" (else from `name`); model handle +0x428 = res_find.
- `rawname` → +0x408 = "<value>.tex" (else from `name`); texture handle +0x42c.
- idle animation = obj_findRoleAnim(this, "idle"), pushed and then given a random start time by
  anim_randomizeTopTime (0x16d0b8, read: it draws **g_cosmeticSeed**).
- `showName` absent → object flag 0x100000 cleared again (not interactable). (The base
  constructor reads `ShowName` into +0x368; whether property lookup is case-sensitive was not
  checked.)
- obj_runEveryFrame; cflags |= 0x8000000000000000; Creature_init (`dead`, `change%d`, weapon
  keys, `initScript`).
- Read elsewhere: `exclamation`, `exclamationShort` (draw); `dialogScript`, `shop`, `talkCone`
  (base interact/prompt); `name` again by the player-select helpers.
Constructor 0x29dcc4 (speed, this, pos, angle, lump, vif, tex, anim name, s16 → +0x432, props):
same setup from explicit strings. **No caller found** (ps2elf xref: none; decompile header
callers = 0), so +0x432 is never set non-zero by code that runs (Inferred).

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | char[0x20] | lump file name | draw, run (string compares), save |
| +0x3e8 | char[0x20] | model file name | draw, save |
| +0x408 | char[0x20] | texture file name | draw, save |
| +0x428 / +0x42c | handle | model / texture | run, draw, slot 16 |
| +0x432 | s16 | negative: use the "low…" model beyond 240 units (draw); saved | draw 0x29e53c |
| +0x434 | char[0x40] | `name` | slot 3, setState, draw |
| +0x474 | ptr | vehicle this NPC is seated in (written by Vehicle_attachNpcDriver 0x208af0, script putNPCInVehicle — unused by the shipped scripts per docs/script.md) | run |
| +0x478 | s32 | set by slot 3 for `firlow` in level `hate3` | setState 0 |

Run (0x29ea40), every frame: Creature_run(this, model) with the RESULT IGNORED; no
Creature_processDamage, no target picking. If seated (+0x474) or Creature_updateActive says
active: Creature_stepAnim(1.0); then
- seated: vehicle->V18(&position, &facing) (Vehicle_getSeat0Pose) and obj_updateGridCell;
- state 1: speed is zeroed for the Creature_moveToDest call when either root-motion component
  (+0xbc, +0xc0) of the last animation step exceeds 0.5 in magnitude, then restored as
  (float)(int)speed (truncated to a whole number each frame);
- state 0 with cflag 0x8000000 (following a path): V27(1).
- lump `we_king.lmp` only: GameObject_rand & 3 == 0 → one particle (descriptor 0x8e4470) near
  the model attach point, 6+ GameObject_rand draws.
There is no other state logic: an NPC is in 0 (idle), 1 (walking) or 0x17.
setState (0x29efcc): 0 → idle animation (`idle1.anm` instead when +0x478 and name `firlow`);
1 → Creature_pickWanderDest, and `walk.anm` (flags 0x803, synced to the frame) if not already
in 1; 0x17 accepted with no animation; every other request (2–0x16, including 0x12 hit, 0x13
stun, 0x14 death) is refused — the state is kept.
takeDamage (0x29eeb8): does not call the creature version; it only zeroes the five effect
timers +0x340…+0x350 (burn, chill, effect, two damage-over-time). NPCs cannot be hurt.
Slot 3, trigger(value) (0x29eed0):
- cutscene active and name `sylea`: hide bits +0xe8 = 0 (value 0) or 2 (otherwise), +0x220
  rebuilt — a mesh swap used by cutscenes;
- else name `firlow` in level `hate3` (g_levelName, case-insensitive): +0x478 = 1 and
  `idle1.anm` started;
- else Creature_trigger 0x11a5f0: with a display name (+0x368) and a `dialogScript` property,
  and menuMutex_tryAcquire() == 0, runs that script.
Interact (base 0x116bd8, playerSlot): needs +0x368 and a living player object. With property
`shop` and net_anyAlivePlayerFlag800000: shop_openOrStock(slot, 0, 1) only if net_isLocalSlot
(slot). Otherwise, if the player stands in front of the NPC (dot of facing with the offset > 0)
and the menu mutex is free: g_scriptActivePlayer = slot, script_runByName(`dialogScript`).
saveState: 0x18 bytes of its own and NOT the creature record: three interned strings (lump,
model, texture), +0x432, hide bits +0xe8, speed +0xb8. loadState: restores them, re-finds the
resources, restarts the idle animation with anim_randomizeTopTime (cosmetic seed again),
rebuilds +0x220.
Per-machine:
(a) Run / setState / slot 3 / takeDamage: no camera, local-slot or cosmetic-seed read
    (the scan: only g_cutsceneActive in slot 3). But the CONSTRUCTOR and loadState set the idle
    animation phase from g_cosmeticSeed (calls to 0x16d0b8 at 0x29e194 in the constructor, 0x29e3a0 in loadState, 0x29de74 in the uncalled constructor), so the animation state +0x114
    of an idle NPC differs between machines from the start. What reads it: Creature_stepAnim's
    root motion +0xbc/+0xc0 (used only in state 1, whose track is synced to g_simFrame by
    setState) and the we_king attach point (particle position only; the number of generator
    draws does not depend on it). No gameplay read of the idle phase found (Inferred harmless).
    Base interact opens the shop only on the owner's machine (net_isLocalSlot, 0x116bd8).
(b) Yes: NPC_draw stores the hide-mask handle +0x220 on every drawn frame (lines for the
    near model, the `firlow` low model, the "low" model when +0x432 < 0, and the player-select
    mask when the lump name contains `select`); not restored. Field search (fieldxref 0x220):
    readers are Creature_draw, creature_drawHeldPart, Creature_refreshVariant and the clone
    functions — no run-code reader found.
(c) Runs a script (0x29e5f4) under the conditions in the section above; reads the camera
    position, the camera matrix and playerSel state; no generator draw, no object creation, no
    run-list change, no world query. The we_king glow uses math_noise seeded with the object
    ADDRESS and g_simFrame (cosmetic).
Open: who sends slot 3 to NPCs; property-key case sensitivity; what 0x501b78 was for (0x29dcb8
is its only reference).

#### Rondo  (factory name `Rondo`, exact; vtable 0x5170d8; size 0x3d0)

Functions: ctor 0x29f10c, draw 0x29f28c, run 0x29f46c, slot 3 0x29f720, setState 0x29f768.
Save/load, takeDamage, touch: base creature versions.
Constructor: Creature_ctor(10, this, typeName 0, pos, angle, classDef 0x501b80 (rondo.lmp),
props) — the type-name argument is not forwarded, so no Creature_setStats and the damage range
+0xd0/+0xd2 stays 0 (Inferred from the zero-filled block). Turn rate 1.2, radius 20, speed 0,
object flag |= 0x1000000 (friendly), cflags |= 0x400040000 and the active bit,
Creature_setCharm(this, −1, 0) (permanent, team 0), +0x3c8 handle empty, +0x3cc = 0, hide bits
+0xe8 = 1, animation idle1, obj_runEveryFrame, attack marker (entry 3) 0.3→bit 1,
Creature_init. Class properties: `exclamation`, `exclamationShort` (draw).
Fields: +0x3c8 handle = the enemy fled from (state 0x10); +0x3cc s32 = 1 after slot 3 (idle2
instead of idle1); +0xf4 state timer.
Run: processDamage, Creature_run (non-zero returns), updateActive (result ignored),
stepAnim(1.0), applyKnockback(0.3), V23(0).
- 0: Creature_isAwayFromHome → 1; else creature_findEnemyInCone(0, 20, this, facing, 0x7fff)
  → 6; else clock > +0xf4 → 1.
- 1: enemy in cone (0, 20) → 6; else Creature_moveTo(+0x104): arrived → 0; else clock > +0xf4
  → 0.
- 5: Creature_isNotRooted → 0.
- 6: with a target, ev bit 0: Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags 1,
  no descriptor); turnToTarget; animation ended → 0.
- 0x10: clock > +0xf4 → 0; else Creature_fleeFrom(this, object of +0x3c8, 0); empty handle → 0.
- 0x12: wait for animation flag 0x10 → 0. 0x13: not stunned → 0.
- 0x14: when the animation has ended (0x80) obj_stopRunning(this); no Creature_deadUpdate.
- others: V27(0).
setState: 0: +0xf4 = clock + 120 + GameObject_rand mod 120. 1: clearPath, pickWanderDest,
+0xf4 = clock + 300 + rand mod 120, run animation when cflags & 0xc00000 (following a player)
else walk. 0x10: creature_findEnemyInCone(0, 100, this, facing, 0x7fff) — none: request
dropped; found: +0x3c8 = it, run animation, +0xf4 = clock + 120 (timer +0x318 not touched).
0x12: hitreaction unless stunned. 0x14: V28(0) and idle1 with flags 6 (there is no death
animation). 2–4, 7–0xf, 0x11: accepted without animation.
Slot 3, trigger(value) (0x29f720): value 0 → hide bits +0xe8 = 2, +0x3cc = 1, +0x220 rebuilt.
Other values: nothing.
Script-driven: no script in scripts/*.txt names `rondo` (grep).
Per-machine: (a) none found (the scan on ctor, run, slot 3, setState: no hits; GameObject_rand
only). (b) draw stores nothing. (c) runs the `exclamation` script, see above; nothing else.

#### Gnome  (factory prefix `Gnome`; vtable 0x5103a8; size 0x3d8)

Functions: ctor 0x268fd4, draw 0x2691f0, run 0x2693d0, onTouch 0x26998c, slot 11 0x269ab8,
setState 0x269bb4. The two functions before the constructor, 0x268f38 and 0x268f80, belong to
GnawSpawn (callers 0x2681f4, 0x26830c, 0x268424 region and 0x268d24, all in GnawSpawn_run /
GnawSpawn_setState): they treat +0x3c8…+0x3dc as six handles — 0x268f38 counts the empty ones
(0 when +0xe8 == 7), 0x268f80 links an object into the first empty one (used right after
world_createObject("gnaw")).
Constructor: Creature_ctor(10, this, typeName, pos, angle, classDef 0x500170 (g_gneric.lmp),
props); turn rate 1.2, radius 15, +0x28 = 0xf, speed 0, +0xb4 = 9, cflags |= 0x400040000,
object flag |= 0x1000000, Creature_setCharm(this, −1, 0), +0x3d0 = 0, +0x3d4 = 0.
Role +0x3cc = GameObject_rand mod 3, overridden by prefix: `gnomesoldier` 0, `gnomeworker` 1,
`gnomepeasant` 2. Hide bits: role 0 → bit 14 + (draw mod 9); role 1 → bit 12 or 13; role 2 →
bit (draw mod 12). Animation idle1, obj_runEvery60, Creature_init. No animation event markers
are written by the constructor (so whether state 6 ever sees ev bit 0 depends on the
animation files — Unknown).
Fields: +0x3cc s32 role; +0x3d0 handle = gnome being talked to; +0x3d4 s32 = clock value
before which no new chat starts / at which the current one ends; +0xf4 idle/wander timer.
Run: processDamage, Creature_run, updateActive (inactive returns), stepAnim(1.0),
applyKnockback(1.0); V23(0) is called with HomeRange +0x3c0 temporarily replaced by 1000
(saved 0x269440, replaced 0x26945c, restored 0x26946c).
- 0: soldier: V25(0) → 3. Worker/peasant: creature_findEnemyInCone(0, 72, this, facing,
  0x7fff) → 0x10. Otherwise Creature_isAwayFromHome → 1; else, unless
  strcmp(level name 0x44fe18, `firmedal`) == 0 (then stays idle), clock > +0xf4 → 1.
- 1: soldier: V25(0) → 3; others: enemy in cone (0, 72) → 0x10; else Creature_moveToDest.
- 3: no target → 0; canSee(0, 20, arc 6000, 0) → 6; canSee(0, 20, arc 0x7fff, 0) →
  turnToTarget; else moveToTarget.
- 5: canSee(0, 20, arc 6000, 0) → 6; else Creature_isNotRooted → 3.
- 6: with a target, ev bit 0: Creature_hitTargetInArc(0, 20, this, facing, 6000, +0xd0, +0xd2,
  +0xd4, flags 8, no descriptor); turnToTarget; animation ended → 3.
- 0x10 flee: Creature_isAttackReady → 0. Else a new flee point is chosen when none is set
  (+0xf8/+0xfc == −1), when within the radius of it, or when clock mod 60 == 0: angle =
  GameObject_rand (16 bits), point = position + 360 × (cos, sin). Creature_moveTo(point).
  setState 0x10 sets +0x318 = 60.
- 0x12: wait for flag 0x10 → 0. 0x13: not stunned → 0. 0x14: Creature_deadUpdate(20, …).
- 0x17 chat: empty handle → 0; else V26(0, partner position); clock > +0x3d4 →
  +0x3d4 = clock + 720 and V27(0).
onTouch (0x26998c): not dead, level (0x41b721) not `firmedal`, no cutscene, clock > +0x3d4,
and the other object is a Gnome (RTTI) whose own clock > its +0x3d4 → +0x3d0 = other,
V27(0x17), +0x3d4 = clock + 180 + GameObject_rand mod 180. Then Creature_onTouch.
Slot 11 (0x269ab8, touched list; only the FIRST entry is looked at): not dead, clock > +0x3d4,
entry is a Gnome in state 0x17 → +0x3d0 = it, V27(0x17), +0x3d4 = that gnome's +0x3d4 + 60.
setState: 1: walk, or run in level `firmedal`; +0xf4 = clock + 120 + rand mod 120.
6: one of three attack animations (GameObject_rand mod 3). 0x14: death1–4 (rand & 3) and V28(0)
— no Creature_dropLoot. 0x17: talk3.
Per-machine: (a) none found (the scan: only g_cutsceneActive in onTouch; level-name compares are
shared). (b) draw stores nothing. (c) `exclamation` script as above.

#### GnomeNavigator  (factory name `GnomeNavigator`; vtable 0x515180; size 0x3c8)

Functions: ctor 0x269eb8, draw 0x26a000, run 0x26a1e0, setState 0x26a3f4.
Constructor: Creature_ctor(10, this, typeName, pos, angle, classDef 0x500238 (g_naviga.lmp),
props); turn rate 1.2, radius 15, speed 0, +0xb4 = 9, object flag |= 0x1000000,
cflags |= 0x404040000 (includes 0x4000000 "friendly") and the active bit,
Creature_setCharm(this, −1, 0), hide bits 0, idle1, obj_runEveryFrame, Creature_init.
Run: **Creature_processDamage is skipped when g_levelName is `beachhub` or `island2`**
(case-insensitive compares at 0x26a208 and 0x26a21c, call at 0x26a230): there pending damage is never applied. Then Creature_run,
updateActive (inactive returns), stepAnim, applyKnockback(1.0), V23(0).
- 0: only when cflags & 0xc00000 (following a player): clock > +0xf4 → 1, else
  Creature_isAwayFromHome → 1.
- 1: Creature_moveTo(+0x104): arrived → 0; else clock > +0xf4 → 0.
- 3: no target → 0 (with a target nothing happens). 5: not rooted → 3. 0x13: not stunned → 0.
- 0x14: Creature_deadUpdate(20, …). Others: nothing.
setState: a request for 1 is refused unless cflags & 0xc00000; 6 and 0x12 are refused (no
attack, no hit reaction); 0x14 plays idle1 with flags 6 and calls V28(0).
Per-machine: (a) none found (the scan clean). (b) draw stores nothing. (c) `exclamation` script.

### Ghoul and Gnaw

#### Ghoul  (factory prefixes `Ghoul` → ghoul.lmp, `GhulBlue` → ghoulblu.lmp; vtable 0x5104f0; size 0x3d8)

Functions: ctor 0x266088, draw 0x2663f8, run 0x266420, slot 12 0x266bac, setState 0x266c68.
takeDamage, save/load, touch: base versions.
Constructor (this, typeName, pos, angle, blue flag, props): three GameObject_rand(this) calls
BEFORE the base constructor (0x2660ec, 0x2660f8, 0x266104; Creature_ctor is called at
0x266158), max-hp argument = (r1 & 7) + (r2 & 7) + (r3 & 7)
+ 18. As in Goblin the generator is still the zero-filled word (pool_new at 0x15ab38 /
0x15ab80), so the three outputs are always 0x3c6e, 0x4750, 0xd1cc and the argument is 28
(Inferred; arithmetic mine), and Creature_setStats overwrites the hit points anyway.
Creature_ctor(hp, this, typeName, pos, angle, classDef 0x4ffed0 or 0x4fffb8, props); turn rate
0.7, speed 170, radius 18, floats +0x64 = 1.0, +0x68 = 1.0, +0x6c = 0.3 (resistance [2], [3],
[4]), +0xb4 = 0x10, cflags |= 0x200000000, +0xec = g_simFrame, state 0. Animation idle1a
pushed, then **anim_randomizeTopTime (0x26620c) — start time from g_cosmeticSeed**.
obj_runEvery60. Markers: attack1, attack2 (entries 3, 4): 0.2→bit 2. attack3 (entry 5):
0.2→2 and 0.4→2 (the second call replaces the first). Hops (entries 0x11–0x14): 0.1→1,
0.4→2, 0.425→4. Creature_init. Class properties: none.
Fields: +0x3c8 s32 timer of the death twitches and of the "played dead" state 0x19;
+0x3cc s16 hop heading; +0x3d0 s32 "hop is moving"; +0xf4 state timer.

Run: processDamage, Creature_run, updateActive (inactive returns), stepAnim(1.0),
applyKnockback(0.5), V23(0).
- 0: V25(0) → 3; Creature_isAwayFromHome → 1; clock > +0xf4 → 1.
- 1: V25(0) → 3; else Creature_moveToDest.
- 3: no target → 0. canSee(0, 20, arc 5000, 0) → 6. canSee(0, 90, arc 3000, 0) →
  GameObject_rand & 1 ? 0x1a : 7. Else creature_allyInLineOfFire(radius×6, radius×3, this,
  target, 0) → 0x18. Else canSee(0, 20, arc 0x7fff, 0) → turnToTarget; else moveToTarget.
- 5: canSee(0, 20, arc 5000, 0) → 6; else Creature_isNotRooted → 3.
- 6 (attack1/attack2 by GameObject_rand & 1): with a target on ev bit 1 (mask 2):
  Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags 1, no descriptor). While the
  animation plays turnToTarget; when it ends → 0x1a (hop).
- 7 (attack3, the long-reach one): on ev mask 2 (twice per animation):
  Creature_hitTargetAtReach(80, …, flags 1, 0). After the animation +0xf4 (set to 20 by
  setState) counts down; at 0 → 3.
- 0x10: Creature_isAttackReady → 0, else fleeFromTarget. (setState 0x10 does NOT set +0x318
  in this class; it only picks speed 170 and the crawl animation.)
- 0x12: wait for flag 0x10 → 3. 0x13: not stunned → 0.
- 0x14 dead (0x266a18, disassembly read), a three-stage corpse:
  (1) death animation finished (animation flags 0x80 and 0x08 both set): object flag |= 1,
  +0x3c8 = clock + GameObject_rand mod 120, `twitch` started with flags 0x13;
  (2) flag 0x10 set and clock > +0x3c8: new timer, `spasm` with flags 0x23;
  (3) flag 0x20 set and clock > +0x3c8: one of the seven `dead…` poses (GameObject_rand mod 7,
  flags 6), object flag |= 1, and only now is event 0x80 passed on.
  Every frame Creature_deadUpdate(25, this, events (0 or 0x80), (20·cos facing, 20·sin facing,
  0), 0).
- 0x17 (called to a hurt ghoul): V25(0) → 3; else Creature_moveToDest.
- 0x18 hold: no target → 0; clock > +0xf4 → 3; else allyInLineOfFire(…, 1) == 0 → 3;
  turnToTarget. setState: +0xf4 = clock + 240 + GameObject_rand mod 240.
- 0x19 lying as if dead: when clock > +0x3c8 starts hop_fwd (blend out 2.0) and → 3.
- 0x1a hop: ev bit 0 → +0x3d0 = 1; ev bit 1 → +0x3d0 = 0; ev bit 2 → V27(3). While +0x3d0:
  Creature_moveBy(speed × (cos, sin) of heading +0x3cc), speed = +0xb8 scaled by
  (60 − slow amount +0x2fc)/60 when that amount is 1–60. Animation ended → 3.
  setState 0x1a: speed 200; heading = creature_findClearHeading(3.0, this, pos, facing,
  GameObject_rand & 1) (0x10eaa8, read: first heading, stepping 0x800 from the facing in the
  chosen direction, whose three parallel world rays of length 3×radius are clear). Animation by
  d = heading − facing (s16), disassembly 0x266e54–0x266e88: −0x2000 ≤ d < 0x2000 → hop_bk;
  0x2000 ≤ d < 0x6000 → hop_lft; d ≥ 0x6000 → hop_fwd AND speed 250; −0x5fff ≤ d < −0x2000 →
  hop_ryt; d < −0x5fff → hop_bk. (The names are the file names of class entries 0x12, 0x13,
  0x11, 0x14; the mapping is as coded, including its asymmetry.)
setState non-routine:
- 0x12 (hit): ignored in 0x13, in 0x19, and in 6 or 7 while the attack animation plays.
  Otherwise GameObject_rand mod 3: non-zero → hitreact; zero → the ghoul DROPS: twitch plus the
  death animation (flags 0x14), state becomes 0x19, +0x3c8 = clock + 120 + GameObject_rand mod
  180.
- Tail (0x267298–0x2672d0): entering 0x19 sets object flag 1 (not solid); leaving 0x19 for
  any other state clears it.
- 0x14: if not hidden, object flag 1 cleared; +0x28 = 0x3c;
  Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos, facing, `ghoulflesh`); death
  animation with flags 0xe (hidden: the `dead` pose with flags 6, which skips the three
  stages); V28(0).
- 0: +0xf4 = clock + 90 + GameObject_rand mod 90. 3: the crawl animation is restarted only when
  coming from another state. 7: +0xf4 = 20.
Slot 12 (0x266bac): kind 0 with a Ghoul source while in state 0 or 1 → V27(0x17),
destination +0x104 = position. Sent by Creature_processDamage only when g_numPlayers == 1
(see Goblin).
Phases: none by hit points; the 1-in-3 "drop and get up" on any hit reaction is the special
behaviour.
Per-machine: (a) run / setState / slot 12: none found (the scan clean; GameObject_rand only).
The constructor's anim_randomizeTopTime uses g_cosmeticSeed for the phase of the first idle
track (flags 1, no root-motion flag 0x800). No reader of that phase in the state code: state 0
tests no animation flag and the track is replaced by the first setState (Inferred harmless).
(b) draw = Creature_draw only. (c) no.
Open: which objects the three rays of creature_findClearHeading stop on (its world_raycast
arguments 0, 3, 0 were not decoded).

Unreferenced function 0x2672f4 (between Ghoul_setState and Gnaw_ctor; no jal, no pointer, no
decompile reference): (object, part 0–4) ORs hide bit 2 / 4 / 8 / 0x10 / 1 into +0xe8, creates
a GutChunk copy of the object's model (pool 0x268, GutChunk_ctorFromProp 0x201ad0, +0x1c4 of
the chunk raised by 2.0) and rebuilds +0x220. Dead code; which of the two classes it was
written for cannot be told from the binary.

#### Gnaw  (factory name `Gnaw`, exact; created by GnawSpawn through world_createObject("gnaw"); vtable 0x515038; size 0x3c8)

Functions: ctor 0x26741c, draw 0x267604, run 0x267654, setState 0x267a0c. Everything else base.
Constructor: Creature_ctor(10, this, typeName, pos, angle, classDef 0x5000a0 (gnawer.lmp),
props); +0xb4 = 1, turn rate 1.2, radius 6, speed 0, cflags |= 0x200001000,
+0xf4 = g_simFrame + 300 (not read by this class), scale +0xdc = (GameObject_rand/65536) × 0.3
+ 0.45 (double arithmetic through the soft-float routines; which routine is add and which
multiply is taken from docs/runtime.md — Inferred), setState(0), obj_runEveryFrame, markers
bite / bite_02 / bite_03 (entries 3–5): 0.2→bit 1, Creature_init. No class fields, no class
properties.
Run: processDamage and Creature_run with the model from V16(); updateActive (inactive
returns); stepAnim(1.0); applyKnockback(1.0); V23(0).
- 0: V25(0) → 3; Creature_isAwayFromHome → 1. 1: V25(0) → 3; else moveToDest.
- 3: no target → 0; canSee(0, 6, arc 8000, 0) → 5; canSee(0, 6, arc 0x7fff, 0) → turnToTarget;
  else moveToTarget.
- 5: canSee(0, 6, arc 8000, 0) → 6; canSee(0, 6, arc 0x7fff, 0) → turnToTarget; else
  Creature_isNotRooted → 3.
- 6: turnToTarget; ev bit 0: Creature_hitTargetInArc(0, 6, this, facing, 8000, +0xd0, +0xd2,
  +0xd4, flags 8, no descriptor); animation ended → 5.
- 0x10: Creature_isAttackReady → 0, else fleeFromTarget (setState: +0x318 = 60).
- 0x12: wait flag 0x10 → 5. 0x13: not stunned → 3.
- 0x14: Creature_deadUpdate(20, this, ev, zero, 1) and obj_delete(this) in the same frame —
  no corpse.
- others: V27(0).
setState: 0x12 is refused (no hit reaction); 5 and 6 pick one of the three bite animations
with GameObject_rand mod 3; 0x14: six fx_spawn(9) at (x, y, z + 24) and, for the first two
loop passes, a GutChunk (pool 0x268, ctor 0x201958, kind GameObject_rand mod 3, bits 2,
PhProp_initPhysics(…, 0x12)); V28(0); no Creature_dropLoot. Unused state numbers are stored as
0.
Per-machine: (a) none found (the scan: only the camera-gated fx_spawn(9)). (b) (c) draw =
Creature_draw only.

### Mummy, Tormentor, Minotaur, Kobold, Gremlin, Mosquito, Ogre, Mermaid

*Reader's notes for this group.* Method: every function listed was read from the Ghidra decompile; where the
decompile was ambiguous (missing call arguments, merged labels) the disassembly was read with
`tools/dis.py` and the address range is quoted. "own generator" = `GameObject_rand`,
"shared seed" = `g_randSeed` 0x404464. Skill-table offsets are quoted as called
(0x0c can-use, 0x14 cast, 0x5c = slot 11 tier-2 statistic (stat, level, cap), 0x64 = slot 12
statistic for a caster (stat, level, caster, cap) — slot meanings from docs/skills.md).
`ML` below = `(int)` of the float global 0x4f714c ("monster level").
`Creature_isAwayFromHome` and `Creature_moveToDest` take one argument (this); the second
"argument" the decompile shows at their call sites is the leftover next-state constant.
`Creature_moveToDest` itself calls slot 27 with 0 when the wander point is reached (0x119f38,
read), which is how state 1 ends in every class below unless stated otherwise.

---

#### Mummy  (factory names `Mummy*`; vtable 0x516e48; size 0x480)

Functions: ctor 0x298418, run 0x298d18, draw 0x298c7c, setState 0x29a6f4, saveState 0x29a53c
(slot 9), loadState 0x29a608 (slot 8), slot 17 0x29aeb8, dtor 0x3cbf34 (not read).
takeDamage, trigger, touch, onDeath, revive are the base Creature functions (vtable read).
NOTE: 0x2982cc, listed with this class in the first pass, is NOT Mummy code: its only two callers
(0x29812c, 0x298250) are inside Mosquito_setState. See Mosquito.

Constructor 0x298418 (type name, position, angle, props):
- `Creature_ctor(10.0, this, typeName, pos, angle, classDef 0x501838, props)`.
- radius +0x1c = 15; turn rate +0xb0 = 1.2; speed +0xb8 = 0; +0x28 = 0x1e; +0xb4 = 0x10;
  +0xec = g_simFrame; creature flags |= 0x400010000; state word +0x232 = 0.
- Embedded weapon holder at +0x3d0 (table 0x50cf40 = Weapon1), pointer stored at +0x50.
- +0x468, +0x46c, +0x470 = 0.
- **Variant +0x3c8 is chosen from the type-name prefix** (`str_prefixDiffers`, tested in this
  order): `mummytemplesoldier` / `mummytso` → 2; `mummydesertshaman` / `mummydsh` → 1;
  `mummytempleshaman` / `mummytsh` → 3; `mummyelitesoldier` / `mummyeso` → 4;
  `mummyeliteshaman` / `mummyesh` → 5; anything else → 0. Odd = shaman (caster), even =
  soldier (melee). No level-file property is read by the constructor.
- Per variant (all draws from the own generator, in this order):
  | variant | hidden-part word +0xe8 | holder slot 1 (hand 1, part id) | rare modifier roll |
  |---|---|---|---|
  | 0 | `1 << (rand % 3)` | 0x2c | if rand/65536 < 0.1: modifier = (rand & 1) + 1 |
  | 2 | `1 << ((rand & 3) + 4)` | 0x2c | same, (rand & 1) + 1 |
  | 4 | `1 << ((rand & 1) + 9)` | 0x2e | if rand/65536 < 0.1: modifier = (rand & 3) + 1 |
  | 1 | 8 | 0x30 | none |
  | 3 | 0x100 | 0x30 | none |
  | 5 | 0x800 | 0x32 | none |
  All variants: resistances +0x5c = −0.2, +0x64 = 0.3, +0x68 = 0.5. Shamans (1, 3, 5) also
  +0x6c = 0.2 and tint preset +0xa0 = 6. +0x220 = `model_buildHideMask(model, +0xe8)`.
- Rare modifier (soldiers only, 10 % of them): 1 → holder table offset 0x3c (Weapon1 slot 7:
  `creature_buildElementDamage(…, 5)` = DiseaseWeapons rider, descriptor type 0x26, one
  shared-seed draw inside that helper); 2 → holder offset 0x24 (slot 4: element 2 =
  ColdWeapons rider, type 0x16, one shared-seed draw); 3 → creature flag 0x800000000000 and
  tint +0xa0 = 8; 4 (variant 4 only) → creature flag 0x200000000000 and tint 8.
  Flag 0x800000000000 is read by Mummy_run states 6/8 (below). Flag 0x200000000000 is read by
  `damage_apply` (decompile of 0x1e8230 near 0x1ea5c8): a non-player victim carrying it answers
  a damage-class hit by calling 0x2ddccc with skill-table entry 9 (Riposte) and level ML —
  Observed there, not in Mummy code.
- `anim_clear`; `Mummy_setState(0)`; `obj_runEvery60`; twelve `creature_setDefEntryParams`
  calls (entries 3, 4, 0x20, 0x21, 0x22, 0xe, 0xf, 0x10, 0x11, 0x12, 0x13, 0x2b);
  `Creature_init`.
- Second caller of the constructor: SpawnMummy_run 0x29cf2c (the MummyKing's summon): it
  passes its own stored type name, a random angle, links the new mummy and sets creature flag
  0x1000000 on it.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | variant 0–5 (saved) | ctor, run, setState, save/load |
| +0x3d0 | object | Weapon1 holder; holder+0x60…+0x6e (= creature +0x430…+0x43e) eight s16 colour words written before each cast, never read by Mummy code | ctor, run state 7 |
| +0x468 | s32 | 1 while the ConeOfFire spell is attached; while set `Creature_stepAnim` is NOT called (animation frozen) | run 0x298dac, state 7; cleared by every setState |
| +0x46c | s32 | creature age at which the cone ends (age + 120) | run state 7 |
| +0x470 | s32 | written only (ctor 0, setState 0x17: age + 600); no reader found with fieldxref | — |
| +0x474 | Vec3 | target position of the previous frame (state 0x18) | run 0x2991e0, 0x299264 |
| +0xf4 | s32 | states 0/3/5: creature age until which it idles/waits; state 7: frame countdown | run, setState |

Run 0x298d18: processDamage; Creature_run; updateActive (return if inactive); weapon-holder
update (holder offset 0xac, 0.5); `events = +0x468 ? 0 : Creature_stepAnim(1.0)`;
applyKnockback(0.5); V23(0); switch on state. Shaman = variant 1, 3 or 5.

States:
- 0 idle: V25(0) true → 3. Shamans try V25(1) as well → 3. Else away from home
  (`Creature_isAwayFromHome`) → 1; else when age > +0xf4 → 1. setState 0 sets
  +0xf4 = age + ownrand % 120.
- 1 wander: V25(0) true → 0, else `Creature_moveToDest`.
- 3 chase: no target → 0.
  - Shaman: `Creature_canSeeTargetIn(0, 400, 0, facing, arc 6000, rayMode 1)` → 7, else
    `Creature_moveToTarget`.
  - Soldier: canSeeTargetIn(0, 40, arc 6000, ray 0) → 6. Variant 4 only: (0, 100, arc 4000)
    → 8. Else `creature_allyInLineOfFire(500, radius × 3, this, target, 0)` non-zero →
    +0xf4 = age + 240 + ownrand % 240 and state 5. Else target within 40 in arc 0x7fff →
    only `Creature_turnToTarget`. Else one own draw per frame: 29 times in 30 →
    `Creature_moveToTarget`; otherwise, when
    `world_countLivingNonplayerCreaturesInBox(target radius × 1.75, target pos) <= 2` and
    `(u32)(atan2(target − me) − target facing + 0x3fff) < 0x7fff` (as written at
    0x29911c–0x299124; Inferred meaning: the direction from the mummy to the target is within
    a quarter turn of the target's facing, i.e. the mummy is behind it) → state 0x18; else
    moveToTarget.
- 5 between attacks (setState: +0xf4 = age + 60 + ownrand % 120): shaman with target in
  (0, 400, arc 6000, ray 1) → 7; soldier with target in (0, 40, arc 6000) → 6; nothing more
  while rooted (+0x314). Shaman: until age > +0xf4 turns to the target, then → 3. Soldier:
  age > +0xf4 → 3; before that → 3 as soon as `creature_allyInLineOfFire(500, radius × 3,
  this, target, 1)` reports nothing (stays when it reports something or there is no target).
- 6 melee and 8 (variant 4's long attack; same code, other animation set): zero move; on
  event bit 0 with a target: `Creature_hitTargetAtReach(36, this, min, max, +0xd4, flags 8,
  descriptor)` (per its symbol note: hits the target when it is within 60 of the point 36
  ahead; body not re-read) with min/max = +0xd0/+0xd2 and descriptor = holder slot 17(hand 1) =
  holder+0x50 (carries the cold/disease rider if the modifier gave one). With creature flag
  0x800000000000: one own draw, below 0.5 → min and max doubled and
  `Creature_emitLinkParticles(this, target)`. Turns to the target every frame. Animation
  finished (flag 8 clear) → 3.
- 7 cast (shamans). setState 7: idle animation plus one of three cast animations
  (ownrand % 3), +0xf4 = 240 + (int)(ownrand/65536 × 120). Every frame with a target: aim
  point = `Creature_leadTargetPoint(400, this, &p)` (p starts 300 ahead of the facing), then
  `V26(0, &aim)`. On event bit 0:
  1. `creature_findCorpseOfClass(300, this)` (0x10f008, read: only when the caller's s16 at
     +0x312 is 0; a creature in the box with object flags & 0x2a == 0x28 — dead and not
     hidden —, animation flag 0x80 set, and exactly the caller's C++ class, so any Mummy
     variant qualifies). If a corpse exists and one own draw < 0.5: **revives it** — sets
     the corpse's flash colour words +0x90…+0x9e, calls the corpse's slot 32 (revive) with 1,
     plays `spel_he_heal.anm` from `fx.lmp`. No spell that frame. The own draw is made only
     when a corpse was found.
  2. otherwise a spell by variant (level argument ML unless noted; origin "chest" = own
     position raised by half of +0x20):
     - Variant 1 (desert shaman). Choice = ownrand % 3 when the target is within 144 but not
       within 48 (arc 0x7fff), else ownrand & 1.
       0 → **ShockOfFire (57)**: skill offset 0x64 queried for stat 0 (damage d), stats 1 and
       2 (results discarded) and stat 3 (speed s, cap 10); one own draw: dMax = d +
       (int)(d × 0.2 × rand/65536); angle = `creature_aimAngleAt(s, this, target)`; creates a
       `Sparks` object (size 0xb8, ctor 0x28f880) at chest with velocity (cos, sin) × s,
       owner this, damage (d, dMax); plays the class sound at classDef+0x1ac.
       1 → **FireStorm (7)**: object 0xb4 bytes, ctor 0x2d41f8, at the aim point raised 6.
       2 → **ConeOfFire (18)**: `SpellConeOfFire` 0x58 bytes, ctor 0x2f00ac, linked with
       `creature_addSpell`; +0x468 = 1, +0x46c = age + 120.
     - Variant 3 (temple shaman). r = DiseaseShield (5) offset 0x64 (stat 1, ML, this, cap
       0x14). Choice = ownrand % 3 when the target is within r × 12 (arc 0x7fff), else
       ownrand & 1.
       0 → **DiseaseBolt (4)**: object 0x7c, ctor 0x2c9eb0, from chest at
       `creature_aimAngleAt(350, …)`.
       1 → **PoisonRain (24)**: object 0x6c, ctor 0x2f8f48, at the aim point (extra argument
       classDef+0x1c4).
       2 → **DiseaseShield (5)**: `SpellDiseaseShield` 0x1b0 bytes, ctor 0x2ccfc8, linked with
       `creature_addSpell` (on itself).
     - Variant 5 (elite shaman). Choice = ownrand & 3:
       0 → **ShockOfFrost (23)**: object 0xd0, ctor 0x2f7404, from chest at aimAngleAt(350).
       1 → **FrostStorm (58)**: the only one cast through the skill table (offset 0x14) with
       level = V35(), position = aim point, facing = own facing.
       2 → ShockOfFire `Sparks` exactly as variant 1 choice 0.
       3 → FireStorm at the aim point raised 6.
     None of the eight skills is asked "can use" (offset 0x0c is never called).
  After the switch: when age >= +0x46c the cone flag is cleared and the ConeOfFire spell
  removed by type. While +0xf4 > 0 it stays in 7, and +0xf4 counts down by one only on
  frames where the cast animation is no longer playing (flag 8 clear) — i.e. one cast per
  visit, then 240–359 frames of standing and turning. +0xf4 <= 0 → cone removed, state 3.
- 0x10: `Creature_fleeFromTarget(this, 0)` until `Creature_isAttackReady` → 0.
- 0x12: zero move until animation flag 0x10 clears → 3. 0x13: until not stunned → 0.
- 0x14 dead: +0x28 = 0x4b; zero move; `Creature_deadUpdate(20, this, events, zero, 0)`.
- 0x17 (teleport in dust): event bit 0 → `DustDevil` (0x58 bytes, ctor 0x29caa8) at own
  position. Event bit 1 → creature flags |= 0x20000000800, object flags |= 3, class sound
  classDef+0x1bc; if farther from home (+0x3b4) than the leash radius +0x3c0 the position is
  set to home and `obj_updateGridCell` called, otherwise
  `Creature_relocateAlongClearRay(400, this, target position or 0)` (one shared-seed draw);
  then a second DustDevil at the new position. When the animation is over: object flags
  &= ~3, creature flags &= ~0x20000000800, state 3.
  **No requester of state 0x17 exists in Mummy code** (run never passes 0x17 to V27; a1
  constants of the whole run function checked in the disassembly); who asks for it is
  Unknown (see "Not done" for what was searched).
- 0x18 approach from behind (soldiers): no target → 0. Target in (0, 40, arc 6000) → 6;
  variant 4 in (0, 100, arc 4000) → 8; otherwise one own draw per frame: when rand % 30 == 0
  and the target moved less than 1.3333 units (2-D) since the previous frame → 3 (argument
  read at 0x299234), else `Creature_moveToTarget`. The target position is stored in +0x474
  every frame.
- 2, 4, 9–0xf, 0x11, 0x15, 0x16: run returns immediately; setState stores the number
  unchanged (no animation).

setState 0x29a6f4: after `Creature_filterState`, EVERY state change clears +0x468 and removes
an attached ConeOfFire spell. Animation sets differ by variant group (0/2, 4, shamans).
Case 0x12 keeps state 6/8 while its attack animation is still playing, and keeps 0x13.
Case 0x14: with creature flag 0x1000000 (set by SpawnMummy_run on its mummy; docs/monsters.md
says the Generator classes set the same flag on what they spawn): `fx_spawnOnModelVerts`,
object flags |= 0x4002, creature flag 0x20000000000, `obj_delete(this)` — no loot, no corpse.
Otherwise `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos, facing, "mummytongue")`
unless creature flag 0x100000000 (revived), and one of two death animations (own draw).
Both paths: holder offset 0x5c (slot 11: drop the held part as a prop) and V28(0).
Case 0x17: +0x470 = age + 600.

Slot 17 (0x29aeb8): replaces `Creature_updateSpells`: calls slot 2 (run) of every attached
spell with the world position of model attach point 0 (`model_getAttachPoint(1.0, model,
pos, facing, anim, 0, out, 0)`) instead of the position it was given, plus the facing. So
the cone (and the shield) run from that attach point.

Save/load: saveState appends variant (u32), holder slot 15 (weapon part id, as u32) and
holder slot 16 (element code, u8) = 9 bytes after the Creature block. loadState reads the
same three values, re-applies holder slot 1 (part id) and slot 8 (element →
`creature_buildElementDamage`, which first empties the descriptor and, for a non-zero code,
rebuilds the rider with one shared-seed draw), clears the weapon part when the loaded state
is 0x14, and returns Creature size + **12** (save returned + 9; 0x29a5e4 vs
0x29a644–0x29a658). Whether the caller uses the returned length was not checked (records
carry their own size per docs/objects.md).
Detail (Observed in 0x117e88 and 0x1176e0): the element code comes from
`damageDesc_getElement`, which maps descriptor types 0x15/0x16/0x17/0x18/0x1f to 1/2/3/4/6
and has no case for 0x26 (disease). A mummy with the disease modifier is therefore saved
with code 0 and comes back from a load with an empty descriptor; the cold one is rebuilt
(with a newly drawn maximum).

Phases: none (no hit-point threshold). Script-driven: nothing read from properties.

Per-machine: (a) none found — the scan on run, setState, slot 17, ctor reports nothing; by
hand, all decisions use the own generator; the only shared-seed draws are inside
`Creature_relocateAlongClearRay` (state 0x17) and `creature_buildElementDamage` (ctor
modifier, loadState), both run-side. (b) Mummy_draw 0x298c7c stores nothing: Creature_draw,
V16, holder draw (offset 0x94). (c) none.

Open: requester of state 0x17; meaning of holder part ids 0x2c/0x2e/0x30/0x32 and of the
colour words; creature flag 0x400000000 (set by the ctor, not traced).

---

#### Tormentor  (factory: prefix `Tormentor` → class block 0, exact `SnowBeast` → 1, exact `SnowBoss` → 2; vtable 0x516360; size 0x3d8)

Functions: ctor 0x287998, run 0x287db0, draw 0x287d78, setState 0x288b70, dtor 0x3cba74 (not
read). takeDamage, save/load and everything else are base Creature (vtable read).
0x287940 (88 bytes, just before the ctor) is not Tormentor code: see "Stray helpers" below.

Constructor (this, typeName, pos, angle, props, classIndex): `Creature_ctor(10.0, …, classDef
0x500fa8 + classIndex × 200, props)`; turn rate 1.2; radius 25; +0x28 = 0x30; speed 0; +0xb4
= 9; creature flags |= 0x200040000; scale +0xdc = 0.7; +0xf4 = 0; state word 0 (setState is
not called); idle animation pushed; `obj_runEvery60`; eleven `creature_setDefEntryParams`
(entries 9, 10, 0xb, 0xd, 8, 0xc, 0x13, 0x15, 0x16, 0xe, 0xf); `Creature_init`. No property
is read. Variant byte +0x3d4 from the type-name prefix: `tormentorgreen` 1, `tormentororange`
2, `tormentorwhite` 3, `snowbeast` 4, `snowboss` 5, otherwise 0.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s32 | number of the last attack state entered (6–0xc); used so the same swing is not repeated | setState 0x288b70, run states 3/5/attacks |
| +0x3d0 | s32 | age after which the ranged attack 0xe may be used again (set by setState 0xe: age + 300, by setState 8: age + 600) | run states 3, 0x17 |
| +0x3d4 | u8 | variant 0–5; draw uses classDef +0x14 + 8 × variant as the second model argument; 5 (snowboss) unlocks the cold rider and state 0xe | ctor, draw, run |

Run 0x287db0: processDamage; Creature_run; `Creature_updateActive` is called but its result is
ignored (AI runs when inactive too); stepAnim(1.0); applyKnockback(0.2); V23(0).
All melee tests use range 0–24.

States:
- 0: V25(0) → 3; else age > +0xf4 → 1 (setState 0: +0xf4 = age + ownrand % 120).
- 1: V25(0) → 3; else `Creature_moveToDest` while age <= +0xf4, then → 0
  (setState 1: +0xf4 = age + 300 + ownrand % 120).
- 3 chase: no target → 0. Target in (0, 24, facing, arc 4000): last attack was 7 → one own
  draw, % 3 == 0 → 0xc else → 6; otherwise → 7. Else, with lead 0.3: last != 9 and target in
  (facing + 11000, arc 7000) → 9; last != 10 and (facing − 11000, arc 7000) → 10; last != 0xb
  and (facing − 24000, arc 6000) → 0xb. Else target within 24 at any angle (arc 0x7fff) →
  only `Creature_turnToTarget`. Else, variant 5 with age > +0x3d0 and
  `creature_findEnemyInCone(24, 400, this, facing, 6000)` → 0xe. Else
  `Creature_isTargetCharging` → 0x17; else `Creature_moveToTarget`.
- 5: same choice as 3 for the front (last == 7 → 6, else 7; no random 0xc) and the three
  side/back tests; none and not rooted → 3.
- 6, 7, 9, 10, 0xb, 0xc melee (`Creature_settle` each frame). Event bit 0: an empty damage
  descriptor is built on the stack; variant 5 only: one own draw, `& 3 == 0` → cold entry
  (type 0x16, v1 = +0xd0, v2 = +0xd2, v3 = 0). Then, all with (min, max, type) = +0xd0/+0xd2/
  +0xd4 and that descriptor:
  | state | helper | facing used | arc | flags |
  |---|---|---|---|---|
  | 6, 7 | Creature_hitTargetInArc | facing | 4000 | 0x1 |
  | 0xc | Creature_hitAllEnemiesInArc | facing | 4000 | 0x40001 |
  | 9 | Creature_hitAllEnemiesInArc | facing + 11000 | 7000 | 0x80001 |
  | 10 | Creature_hitAllEnemiesInArc | facing − 11000 | 7000 | 0x80001 |
  | 0xb | Creature_hitAllEnemiesInArc | facing − 24000 | 6000 | 0x80001 |
  6, 7, 0xc turn to the target while it is in (0, 24, arc 4000). Event bit 2 (mask 4) with the
  target in (0, 24, lead 0.3, arc 4000) chains straight into the next front attack: last != 7
  → 7, else own draw % 3 == 0 → 0xc else 6. Animation over → 5.
- 8: event bit 0 → casts **ConeOfFrost (56)** through skill-table offset 0x14 (level V35(),
  this, own position, facing) and links it with `creature_addSpell`; event bit 1 → removes the
  ConeOfFrost spell by type; turns to the target; animation over → 3. setState 8 sets +0x3d0
  = age + 600. **Nothing in Tormentor_run or setState ever requests state 8** (all a1 constants
  of the run function listed from the disassembly: 1, 3, 5, 6, 7, 9, 0xa, 0xb, 0xc, 0xd, 0xe,
  0x17), so this cast is reachable only if something outside the class calls slot 27 with 8.
  Not found; Unknown.
- 0xd (answer to a charge, entered from 0x17): event bit 0 → `Creature_hitTargetInArc(0, 24,
  facing, arc 10000, min, max, +0xd4, flags 0x80001, no descriptor)`; event bit 1 and target
  no longer in that arc → 3; animation over → 3.
- 0xe (snowboss ranged, setState: +0x3d0 = age + 300): event bit 0 → enemy =
  `creature_findEnemyInCone(24, 400, this, facing, 6000)`; origin = position + 24 × (cos, sin)
  (facing − 8000), raised by +0x20; aim = 360 ahead, replaced by `creature_leadPoint(400, this,
  enemy)` when the enemy is a creature; creates a **ShockOfFrost (23)** object (0xd0 bytes,
  ctor 0x2f7404, angle atan2 of the aim direction, level V35()) and overwrites its velocity
  (+0x9c..+0xa4) with the 3-D aim direction × 400. Animation over → 3.
- 0x10: flee until `Creature_isAttackReady` → 0. 0x12: until animation flag 0x10 clears → 0.
  0x13: until not stunned → 3. 0x14: `Creature_deadUpdate(30, …)`.
- 0x17 (target is charging; looped animation classDef+0xa4): no target → 0; target in (0, 24,
  facing, arc 10000) → 0xd; target within 24 with facing argument literally 0 and arc 0x7fff
  → 3; else variant 5 with age > +0x3d0 and an enemy in the cone → 0xe; else moveToTarget.
- 2, 4, 0xf, 0x11, 0x15, 0x16 and unknown numbers: setState turns the request into state 0.

setState 0x288b70: 0x12 is ignored while the current state is 6–0xf (attacks are not
interrupted by the hit reaction). 0x14: one of two death animations (own draw), V28(0),
`Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25, this, pos, facing, 0)`.

Phases: none. Script-driven: nothing found in the class.
Per-machine: (a) none found (the scan on run, setState, ctor; body read: own generator only).
(b) Tormentor_draw 0x287d78 is one `Creature_draw` call; stores nothing. (c) none.
Open: who requests state 8.

---

#### Minotaur  (factory names `Minotaur*`; vtable 0x5165f0; size 0x470)

Functions: ctor 0x288fdc, run 0x2894b8, draw 0x289400, setState 0x28a16c, dtor 0x3cbb24 (not
read). Everything else base Creature (vtable read).

Constructor: `Creature_ctor(10.0, …, classDef 0x501200, props)`; embedded two-hand holder at
+0x3c8 (final table 0x50cda0 = WeaponShield), pointer at +0x50; turn rate 1.2; radius 25;
speed 0; +0xb4 = 0xb; +0xf4 = g_simFrame + 300; creature flags |= 0x200040000; +0x46c = 0.
Exact type name `minotaurboss` (strcasecmp): hand 1 part 0x15, hand 2 part 0x17, hidden-part
word +0xe8 = 4. Any other name: hand 1 part 0x15, hand 2 part 0x19, +0xe8 = `1 << (ownrand &
1)`. `Minotaur_setState(0)`; `obj_runEvery60`; eight `creature_setDefEntryParams` (entries 5,
6, 7, 8, 9, 0xd, 3, 4); `Creature_init`. No property read.

Fields:
| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | object | WeaponShield holder; slot 14 (offset 0x74)(hand) answers "is this hand still holding its part" (hand 1 = weapon bit 0, hand 2 = shield bit 1) | run states 3, 5; setState |
| +0x468 | s32 | age before which the charge (0xc) is not used again; never initialised by the ctor (0) | run states 3, 5, 0xc |
| +0x46c | s32 | 1 once the extra animation of the first charge has been played | setState 0xc |
| +0xf4 | s32 | state 0x17: age at which the block ends | run, setState |

Run 0x2894b8: processDamage and Creature_run with the model from V16(); returns when
`Creature_updateActive` is 0; holder update (offset 0xac, 0.5); stepAnim(1.0);
applyKnockback(0.7); V23(0). Range note (from `creature_canSeeObj` 0x10c810, read): the range
test is `gap < max` and `min <= centre distance + target radius − own radius`, gap = centre
distance minus both radii.

States:
- 0: V25(0) true → 1; else away from home (`Creature_isAwayFromHome`) → 1; else stays
  (next-state constant 1 on both paths, read at 0x2895f0 and 0x289608).
- 1: no visible target → `Creature_moveToDest`. Otherwise turns to the target and goes to 3
  only when it is within the creature's `visualrange` word +0x3ae in arc 8000.
- 3 chase: no target → 0. Target in (0, 12, arc 8000) → 5. Target not charging and in (0, 36,
  arc 8000) → 5. Target not charging and within 36 at any angle → turn only. Otherwise: if
  hand 1 still holds the weapon, or age <= +0x468 → `Creature_moveToTarget`; with the weapon
  gone and the cooldown over, target in (min 60, max 300, arc 8000) → 0xc, else moveToTarget.
- 5 choose attack. Tested in this order:
  1. only while 33 % < hp < 66 % of max and the target is in (0, 36, arc 8000): if
     `Creature_isTargetAttackingMe` and one own draw % 3 != 0 and hand 2 still holds the
     shield → 0x17 (block); otherwise → 6.
  2. weapon gone: target in (0, 36, arc 8000) → 6.
  3. weapon held: target in (0, 36, arc 8000) → 7 or 8 (own draw & 1); in (0, 36, facing +
     0x4000, arc 8000) → 9; (facing − 0x4000) → 10; (facing − 0x7fff) → 0xb.
  4. weapon gone and age > +0x468: the charge test here is called with **min 300, max 60**
     (0x289b48–0x289b64; the same test in state 3 has min 60, max 300). With the range rule
     above that can only hold for a target whose radius exceeds 120 — Inferred: never in
     practice, so the charge starts from state 3 only.
  5. target within 36 at any angle → turn only; else not rooted → 3.
- 6 (unarmed strike): settle, turn; event bit 0 → `Creature_hitTargetInArc(0, 36, facing, arc
  8000, +0xd0, +0xd2, +0xd4, flags 0x440001, no descriptor)`; animation over → 5.
- 7, 8 (weapon swings): same but flags 0x440008 and descriptor = holder slot 17(hand 1) =
  holder+0x50; → 5.
- 9, 10, 0xb (side / back swings): zero `Creature_moveBy`, no turning; event bit 0 → the same
  hitTargetInArc with the UNMODIFIED facing, arc 8000, flags 8, weapon descriptor; → 5.
- 0xc charge (weapon lost): setState starts the looping animation classDef+0x8c and, the
  first time only (+0x46c), blends classDef+0x9c in. While only the run track is playing and
  the target comes into (0, 36, arc 8000) it starts classDef+0x84 and blends the strike
  animation classDef+0x6c (flags 0x818). With a target: turn, settle; event bit 0 →
  hitTargetInArc(0, 36, facing, arc 8000, min, max, +0xd4, flags **0x100041**, no descriptor).
  Leaves when the animation is over, or when animation flag 0x10 is clear and the target is no
  longer in (0, 300, arc 8000): +0x468 = age + 300 + ownrand % 180, state 3.
- 0x17 block: setState sets creature flag 0x200 (blocking) and +0xf4 = age + 60 + ownrand %
  120; run waits for age > +0xf4 → 3. Every setState call first clears flag 0x200.
- 0x10 (setState: +0x318 = 60): flee until attack ready → 0. 0x12: until animation flag 0x10
  clears → 3. 0x13: until not stunned → 3. 0x14: zero move, `Creature_deadUpdate(20, …)`.
- 2, 4, 0xd, 0xe, 0xf, 0x11, 0x15, 0x16, others: run calls V27(0); setState maps them to 0.

setState 0x28a16c, non-routine: case 3 picks the chase animation by hit points (>= 66 % and
<= 33 %: classDef+0x8c; between: classDef+0xa4, the wander animation). Case 0x12: **when hp <
33 % of max it first drops both held parts** (holder offset 0x5c, hand 1 then hand 2 →
`creature_dropHeldPartAsProp`), then plays the hit animation. Case 0x14:
`Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos, facing, 0)`, both held parts
dropped, one of two death animations (own draw), V28(0).

Phases (hit-point thresholds, all Observed above; "unarmed strike" is my label for state 6):
- hp >= 66 % of max: weapon swings 7/8 in front, 9/10/0xb to the sides and back.
- 33 % < hp < 66 %: with the target in the front arc it uses 6 or the shield block 0x17
  instead of 7/8 (the side/back swings are unchanged); the chase animation changes.
- hp < 33 %: the next hit reaction (setState 0x12) drops weapon and shield. Until that
  happens it still swings the weapon; afterwards only 6 and the charge 0xc remain.

Per-machine: (a) none found (the scan on run, setState, ctor; own generator only). (b)
Minotaur_draw 0x289400 stores nothing (V16, Creature_draw, holder draw offset 0x94). (c) none.
Open: meaning of the held-part ids 0x15/0x17/0x19.

---

#### Kobold  (factory names `Kobold*`; vtable 0x515ef0; size 0x3d0 per the catalogue, not re-read)

Functions: ctor 0x27f0c0, run 0x27f52c, draw 0x27f504, setState 0x27ff6c, isAlly override
0x280434 (slot 21), dtor 0x3cb5d0 (not read). Everything else base Creature.
0x27ef4c / 0x27f0a0 (just before the ctor) are not Kobold code: see "Stray helpers".

Constructor: `Creature_ctor(10.0, …, classDef 0x500af0, props)`; +0x28 = 0x1e; +0xb4 = 9; turn
rate 1.2; speed 0; +0xf4 = g_simFrame + 300; creature flags |= 0x200040000; +0xe0 = −10;
resistance +0x5c = −0.2. Variant byte +0x3cc from the type-name prefix: `koboldtough` → 1
(scale +0xdc 1.5, radius 20, +0xe8 = 1); `koboldshaman` → 2 (scale 1.2, radius 18, +0xe8 = 2);
otherwise 0 (radius 12, creature flag 0x400, +0xe8 = 0). Hide mask; idle animation;
`Kobold_setState(0)`; `obj_runEvery60`; eleven `creature_setDefEntryParams` (3, 4, 5, 6, 7,
0x15, 0x11, 8, 9, 10, 0xb); `Creature_init`. No property read.

Fields: +0x3c8 s32 = last attack state entered (6, 7, 8, 9, 0x17; written by setState, not read
by the class); +0x3cc u8 variant.

Slot 21 override 0x280434 (isAlly(other)): base `Creature_isAlly` AND the other object's type
name (+0x34) equals `koboldshaman` exactly (strcasecmp). So for every kobold the only "ally"
is a kobold shaman; this is what slot 24 (pickAlly, called every frame by run),
`creature_findWoundedAlly` and the guard logic below see.

Run 0x27f52c: processDamage; Creature_run; returns when `Creature_updateActive` is 0;
stepAnim(1.0); applyKnockback(1.0); V23(0); **V24()** (ally handle +0x238).

States:
- 0: V25(0) → 3; away from home (`Creature_isAwayFromHome`) → 1; age > +0xf4 → 1.
- 1 (setState: +0xf4 = age + 120 + ownrand % 120): V25(0) → 3; else walks
  (`Creature_moveToDest`) until age > +0xf4 → 0.
- 3 chase: no target → 0. Never attacks directly: in range it goes to 5.
  - variant 1 (tough): `Creature_countAlliesNearTarget(24, this) > 2` → 5; target charging and
    in (0, 24, arc 6000) → 7; in (0, 24, arc 6000) → 5; within 24 at any angle → turn; else
    moveToTarget.
  - variant 2 (shaman): in (0, 24, arc 6000) → 5; in (0, 164, arc 5000) → 5; within 164 at any
    angle → turn; else moveToTarget.
  - variant 0: in (0, 24, arc 6000) → 5; within 24 at any angle → turn. Else guard logic with
    the ally (shaman) handle: 0x119180 = `creature_canSeeObj(viewer = ally, object = this, 0,
    24, facing = Creature_angleAllyToTarget, arc 6000)` true (I stand within 24 of the shaman
    on the target's side) → 5; else 0x119128 = `creature_canSeeObj(viewer = ally, object =
    target, 0, 500, arc 0x7fff)` true → walks to `creature_getGuardPoint(24)` (24 from the
    shaman toward the target) with `Creature_moveTo`; else moveToTarget. Without an ally both
    helpers return 0 → plain chase.
- 5: no target → 0. Turns to the target, then
  - variant 1: in (0, 24, arc 6000) → 6; else stays while rooted or while more than 2 allies
    are near the target, otherwise → 3.
  - variant 2: in (0, 24, arc 6000) → 6; else `creature_findCorpseOfClass(200, this)` → 8;
    else stays while rooted or while the target is in (0, 200, arc 5000); otherwise → 3.
  - variant 0: in (0, 24, arc 6000) → 6; rooted → stays; no ally → 3; not in the guard spot
    (0x119180 test as above false) → 3; in the guard spot → stays.
- 6 melee: settle; with a target, event bit 0 → `Creature_hitTargetInArc(0, 24, facing, arc
  6000, +0xd0, +0xd2, +0xd4, flags, no descriptor)` with flags 0x440008 for variant 1 and 8
  for the others; turns; animation over → 5.
- 7 (tough, against a charging target): event bit 0 → the same hit with flags 0x80001; event
  bit 1 → a second hit with flags 1; → 5.
- 8 and 9 (shaman cast animation classDef+0xac). Event bit 0: corpse =
  `creature_findCorpseOfClass(200, this)`, wounded = `creature_findWoundedAlly(200, this)`
  (a live creature below half hit points accepted by slot 21, i.e. a kobold shaman).
  State 9 only: casts **FrostArmor (96)** through skill offset 0x14 (V35(), this, own
  position, facing) and links it to itself. Then: corpse → corpse's slot 32 (revive) with 1
  (0x27fd28); else wounded ally that has no `SpellHealing` attached → **Healing (55)** through
  skill offset 0x14 with (V35(), caster argument = the wounded ally, position = the shaman's
  own position, facing) and `creature_addSpell(ally, spell)`. Animation over → 5.
  Neither skill is asked "can use" (offset 0x0c).
  Reachability: state 8 is entered only from state 5 when a same-class corpse is within 200;
  **state 9 is never requested by Kobold_run** (its a1 constants are 1, 3, 5, 6, 7, 8), so the
  FrostArmor cast needs an outside slot-27 call — not found, Unknown. Healing is reached only
  when state 8 was entered for a corpse that is gone by the hit frame.
- 0x10 (setState: +0x318 = 60): `Creature_fleeFromTarget(this, 1)` until attack ready → 0.
- 0x12: zero move; event bit 3 (mask 8) → knockback speed +0x2e8 = 0; animation flag 0x10
  clear → 3. 0x13: until not stunned → 3. 0x14: zero move, `Creature_deadUpdate(20, …)`.
- 0x17: zero move until animation flag 0x10 clears → 3 (three animations, own draw % 3). Not
  requested by Kobold_run.
- 2, 4, 10–0xf, 0x11, 0x15, 0x16, others: → 0.

setState 0x27ff6c, non-routine: case 0x12 for variant 0 plays the knock-down animation
classDef+0x8c when the pending damage flags +0x2dc contain any of 0x3c0000 (the knockback
strength bits), otherwise one of two hit animations. Case 0x14: `Creature_dropLoot(36, 2,
1.6, 0.3, 1.4, 0.12, this, pos, facing, 0)`, one of four death animations (own draw & 3),
V28(0). Case 3 picks the walk animation by variant / crowding.

Phases: none. Script-driven: nothing in the class.
Per-machine: (a) none found (the scan on run, setState, ctor, slot 21). (b) Kobold_draw 0x27f504
is one `Creature_draw` call. (c) none.
Open: requesters of states 9 and 0x17; whether `creature_findWoundedAlly` can return the
shaman itself.

---

#### Gremlin  (factory name `Gremlin`; vtable 0x515358; size 0x460) — archer

Functions: ctor 0x26e08c, run 0x26e4c4, draw 0x26e40c, setState 0x26ee98, dtor 0x3cacf0 (not
read). Everything else base Creature. 0x26dfec / 0x26e06c before the ctor: see "Stray helpers".

Constructor: `Creature_ctor(10.0, …, classDef 0x500548, props)`; Weapon1 holder embedded at
+0x3c8 (pointer +0x50); +0xb4 = 9; turn rate 1.2; radius 18; speed 0; +0xf4 = g_simFrame +
300; creature flags |= 0x200040000; **`pointblankrange` word +0x3ac = 700 and leash radius
+0x3c0 = 1500** are overwritten here; holder slot 1 (hand 1, part 9 = the arrow shown in the
hand). Arrow type roll, own generator: one draw; below 0.1 a second draw % 3 picks a holder
call: 0 → offset 0x24 (slot 4: `creature_buildElementDamage` element 2, ColdWeapons, type
0x16); 1 → offset 0x14 (slot 2: element 1, FireWeapons, type 0x15); 2 → offset 0x1c (slot 3:
element 6, FireWeapons statistic, type 0x1f). Each of those helpers draws once from the
shared seed. `Gremlin_setState(0)`; `obj_runEvery60`; four `creature_setDefEntryParams`
(8, 3, 4, 5); `Creature_init`. No property read.

Fields: only the holder (+0x3c8…); the arrow type lives in the holder's damage descriptor
(holder+0x50) and is read back with holder slot 16 (`damageDesc_getElement`: 1 fire, 2 cold,
6 for type 0x1f).

Run 0x26e4c4: processDamage / Creature_run with V16(); returns when inactive; holder update;
stepAnim(1.0); applyKnockback(1.0); V23(0).

States:
- 0: V25(1) → 3; away from home (`Creature_isAwayFromHome`) → 1; else stays.
- 1: V25(1) → 3; else `Creature_moveToDest`.
- 3 chase: no target → 0. Target within 120 at any angle (facing argument 0, arc 0x7fff, ray
  mode 0) → 0x10 (back off). Target in (0, `visualrange` +0x3ae, own facing, arc =
  `visualarc` +0x3b0, ray mode 1) → 5. Target within visualrange at any angle (ray mode 1) →
  turn only. Else `Creature_moveToTarget`.
- 5: same three tests; the second one leads to 6 (shoot). None true and not rooted → 3.
- 6 shoot: turns to the target every frame. Event bit 0: holder slot 1 (hand 1, 0) hides the
  arrow; aim = `Creature_leadTargetPoint(400, this, &p)` (p starts 300 ahead); origin =
  `model_getAttachPoint(scale +0xdc, V16(), pos, facing, anim, 0)` (pre-set to position +
  half height + 12); velocity = unit(aim − origin) × 400 + (point in the unit sphere by
  rejection, 3 own draws per try) × 40; one more own draw picks one of four `swsh_arrow%d.anm`
  sounds. Projectile by holder slot 16:
  | element | object | size | constructor | skill pointer passed |
  |---|---|---|---|---|
  | 1 | FireArrowProjectile | 0xb0 | 0x2d6440 (obj, origin, velocity, this, ML, skill) | FireArrow (43) |
  | 2 | ColdArrowProjectile | 0xb0 | 0x2d718c | ColdArrow (44) |
  | 6 | ExplodeArrowProjectile | 0x74 | 0x2dafe0 | ExplodeArrow (47) |
  | other | MissileWeapon | 0x1c8 | 0x150ee4 (obj, 0, g_itemModels[2], g_itemModels[3], origin, velocity, atan2(velocity) − 0x4000, this, 0, 0, +0xd0, +0xd2, 0, 0, +0xd4, 4, 0) | none |
  The skills are only handed over as pointers; no skill-table offset is called by Gremlin
  code. Stack arguments of the plain arrow read at 0x26ec90–0x26ece4: the creature's +0xd0 /
  +0xd2 / +0xd4 and the constant 4 land in the missile at +0xd4 / +0xd8 / +0xe4 / +0xe8
  (their use inside MissileWeapon was not read).
  Event bit 1: holder slot 1 (hand 1, 9) shows the arrow again. Then, when the hand holds a
  part (holder slot 14) and the target is within 120 at any angle → 0x10. Animation over → 5.
- 0x10 (setState: +0x318 = 120): `Creature_fleeFromTarget(this, 0)` until attack ready → 0.
- 0x12: until animation flag 0x10 clears → 5. 0x13: until not stunned → 3.
  0x14: `Creature_deadUpdate(20, …)`.
- 2, 4, 7–0xf, 0x11, others: → 0.

setState 0x26ee98: case 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos,
facing, 0)`, holder offset 0x5c (drop the held part), one of three death animations (own draw
% 3), V28(0).

Save/load: slots 8/9 are the base Creature functions (vtable), unlike Mummy, which adds the
holder's part id and element code itself. Inferred, not checked in the base functions: the
gremlin's arrow element is not part of its save record.

Phases: none. Per-machine: (a) none found (the scan on run, setState, ctor); the sound choice
uses the own generator, in run code. (b) Gremlin_draw 0x26e40c stores nothing (V16,
Creature_draw, holder draw). (c) none.

---

#### Mosquito  (factory names `Mosquito*`; vtable 0x516a08; size 0x3c8 — no class fields)

Functions: ctor 0x297788, run 0x297b30, draw 0x297a14, setState 0x297f54, **losePart
0x2982cc** (unnamed until now; its only callers are 0x29812c and 0x298250 in setState), dtor
0x3cbe84 (not read). Everything else base Creature. 0x297768 before the ctor: "Stray helpers".

Constructor: `Creature_ctor(10.0, …, classDef 0x5017a0, props)`; +0x28 = 0x1e; +0xb4 = 0x12;
turn rate 1.2; radius 10; speed 0; +0xf4 = g_simFrame + 300; creature flags |= 0x8000001000;
resistances +0x5c = −0.2, +0x64 = 1.0, +0x68 = 1.0; scale +0xdc = 0.7 unless the type name
starts with `mosquitolarge`; `Mosquito_setState(0)`; `obj_runEvery60`; six
`creature_setDefEntryParams` (3–8); `Creature_init`. No property read.

Run 0x297b30: processDamage; Creature_run; returns when inactive; stepAnim(1.0);
applyKnockback(1.5); V23(0).
States:
- 0: V25(0) → 3; away from home (`Creature_isAwayFromHome`) → 1; else stays.
- 1: V25(0) → 0; else `Creature_moveToDest` unless animation flag 0x20 is set.
- 3: no target → 0; nothing while animation flag 0x10 is set; target in (0, 40, arc 6000) →
  6; within 40 at any angle → turn; else `Creature_moveToTarget`.
- 5: no target → 0; turn; in (0, 40, arc 6000) → 6; else not rooted → 3.
- 6 bite: zero move; with a target, event bit 0 → `Creature_hitTargetInArcEdge(0, 40, facing,
  arc 6000, +0xd0, +0xd2, +0xd4, flags 4, no descriptor)`; turn; animation over → 3.
- 0x10 (setState: +0x318 = 60): flee until attack ready → 0. 0x12 and 0x17: zero move until
  animation flag 0x10 clears → 3. 0x13: until not stunned → 3. 0x14: zero move,
  `Creature_deadUpdate(15, …)`. Others → 0.
  The run function itself only ever requests 0, 1, 3 and 6 (a1 constants read from the
  disassembly); 0x17 has no requester in the class.

setState 0x297f54: case 0x12: one of two hit animations (own draw & 1) **and
`Mosquito_losePart(this, ownrand % 3 + 1)`**. Case 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6,
1.4, 0.25, this, pos, facing, 0)`, one of four death animations (own draw & 3),
`Mosquito_losePart(this, (ownrand & 3) + 4)`, V28(0). After every case: creature flag
0x100000 (no water/dust ground effects) is cleared when the new state is 0 or 0x14 and set
otherwise.

Mosquito_losePart 0x2982cc (this, part): ORs a bit into the hidden-part word +0xe8 — part 1
and 2 → 0x10, 3 → 0x40, 4 → 2, 5 → 1, 6 → 4, 7 → 8 — recomputes +0x220 with
`model_buildHideMask`, then ALWAYS creates a `GutChunk` (0x268 bytes,
`GutChunk_ctorFromProp(1.0, obj, pos, facing, classDef[3], anim, classDef[0], classDef[2],
classDef[4])`) and adds 2.0 to the chunk's +0x1c4. So every hit reaction sheds a piece (a new
object each time, even when the part bit was already set).

Per-machine: (a) none found (the scan on run, setState, ctor, losePart).
(b) **Answer to the first-pass open question**: Mosquito_draw 0x297a14 copies the 12 bytes of
position (+0x10..+0x1b) to its stack at entry (0x297a3c–0x297a54). In states 3 and 5, and in
state 6 once the attack animation is no longer playing, it adds (3 cos a, 3 sin a, 5 cos a),
a = creature age +0x300 × 0x5dc, to the position, calls `Creature_draw`, and then restores the
saved 12 bytes on the single exit path (0x297afc–0x297b14). Facing is not touched. So nothing
it stores survives the call; the offset is only visible to code running inside
`Creature_draw`. (c) none: no generator draw, no object creation, no run-list change.

---

#### Ogre  (factory name `Ogre`; vtable 0x517220; size 0x468)

Functions: ctor 0x29fad0, run 0x29fe50, draw 0x29fdb4, setState 0x2a060c, dtor 0x3cc458 (not
read). Everything else base Creature. 0x29fa24 / 0x29fab0 before the ctor: "Stray helpers".

Constructor: `Creature_ctor(10.0, …, classDef 0x501bf8, props)`; Weapon1 holder embedded at
+0x3c8 (pointer +0x50); +0xb4 = 0xb; turn rate 1.2; radius 25; speed 0; +0xf4 = g_simFrame +
300; creature flags |= 0x800040000; own draws: holder slot 1 (hand 1, part 0xc or 0xe by
`rand & 1`), hidden-part word +0xe8 = `1 << (rand % 5)`; hide mask; idle animation;
`Ogre_setState(0)`; `obj_runEvery60`; four `creature_setDefEntryParams` (3, 4, 5, 6);
`Creature_init`. No property read; no elemental rider is ever built.

Fields: +0x460 s32 = last attack state entered (6–9; setState), read by run states 3 and 5.

Run 0x29fe50: processDamage; Creature_run; returns when inactive; holder update;
stepAnim(1.0); applyKnockback(0.1); V23(0). All hits are `Creature_hitAllEnemiesInArc(0, 60,
facing, arc 6000, …, descriptor = holder slot 17(hand 1))`.

States:
- 0: V25(0) true → 1; away from home → 1; else stays (constant 1 on both paths, 0x29ff60 /
  0x29ff78). 1: V25(0) → 3; else `Creature_moveToDest`.
- 3 chase: no target → 0. Target in (0, 60, arc 2000) → 5. Else, unless the last attack was 8
  or 9: target within 60 at any angle → 9. Else target not charging and within 60 at any angle
  → turn only. Else target in (0, 120, arc 2000) and `Creature_countAlliesNearTarget(60) > 0`
  → 5. Else `Creature_moveToTarget`.
- 5: target in (0, 60, arc 2000): unless the last attack was 8 or 9, one own draw % 3 == 0 →
  8. Otherwise, if the last attack was not 7 and `Creature_isBlockedByTarget`, one own draw %
  3 == 0 → 7. Otherwise → 6.
  Target not there: nothing while rooted; if it is also outside (0, 156, arc 2000), one own
  draw % 60 == 0 → 3; then one more own draw: % 60 == 0 and no ally near the target → 3;
  otherwise stays.
- 6: event bit 0 → hit with (+0xd0, +0xd2, +0xd4), flags 0x40001; animation over → 3.
- 7 (used against a blocking target): event bit 0 → hit with LITERAL damage 1–5, +0xd4, flags
  0x100001; → 3.
- 8: event bit 0 → hit with (+0xd0, +0xd2, +0xd4), flags 1; event bit 2 (mask 4, only when bit
  0 is not set in the same frame) → a second hit with flags 0x80001; → 3.
- 9 (target close but not in front): turns to the target every frame; on event bit 0 or bit 2
  (mask 5) → hit with flags 1; → 3.
- 0x10 (setState: +0x318 = 60): flee until attack ready → 0. 0x12: until animation flag 0x10
  clears → 3. 0x13: until not stunned → 3. 0x14: zero move, `Creature_deadUpdate(30, …)`.
  2, 4, 10–0xf, 0x11, others → 0.

setState 0x2a060c: case 0x12 is ignored while the current state is 6–0xf (attacks are not
interrupted). Case 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, pos, facing,
0)`, holder offset 0x5c (drop the held part), one of two death animations (own draw & 1),
V28(0). States 8 and 9 share one animation (classDef+0x2c).

Phases: none. Per-machine: (a) none found (the scan on run, setState, ctor; own generator only).
(b) Ogre_draw 0x29fdb4 stores nothing (Creature_draw, V16, holder draw). (c) none.

---

#### Mermaid  (factory name `Mermaid`; vtable 0x516218; size 0x3c8 — no class fields) — passive NPC creature

Functions: ctor 0x285b30, run 0x285c58, draw 0x285c30, setState 0x285ddc, dtor 0x3cb900 (not
read). Everything else base Creature. 0x2858ac / 0x285b10 before the ctor: "Stray helpers".

Constructor: `Creature_ctor(10.0, …, classDef 0x500e60, props)`; radius 25; turn rate 1.2;
speed 0; +0x28 = +0x29 = 0x32; scale +0xdc = 1.0; creature flags |= 0x200040000; +0xf4 = 0;
animation classDef+0x5c pushed; `obj_runEvery60`; `Creature_init`. setState is not called; no
property read.

Run 0x285c58: processDamage; Creature_run; `Creature_updateActive` (result ignored);
stepAnim(1.0); applyKnockback(0.2); V23(0); zero `Creature_moveBy` every frame; then
- 0: age > +0xf4 → 1. 1: `Creature_moveToDest` while age <= +0xf4, then → 0.
- 3: back to 0 as soon as the target handle is empty; otherwise nothing (it never chases).
- 5: not rooted → 3. 0x12: animation flag 0x10 clear → 0.
- 0x14: when animation flag 0x80 (ended) is set → `obj_stopRunning(this)`. No
  `Creature_deadUpdate`.
- 2, 4, 6–0x11, 0x13: return with no exit. There is no attack state at all.
  The run function itself only requests 0, 1 and (from 5) 3; states 3 and 5 are otherwise
  entered from outside the class (base creature code).

setState 0x285ddc: **does not call `Creature_filterState`** — the number is stored as given.
0: +0xf4 = age + ownrand % 120, idle animation. 1: clear path, pick a wander point, +0xf4 =
age + 300 + ownrand % 120, walk animation classDef+0x54. 5 and 0x12: blend classDef+0x5c
with flag 0x10. 0x14: plays classDef+0x5c with flags 6 and nothing else — **no
`Creature_dropLoot`, no slot 28 (onDeath) call**. Any other number: stored only. So a state
0x13 (stun) or 6–0x11 written from outside leaves her inert until something else calls
slot 27 — Observed in the code; whether that happens in play is Unknown.

Script-driven: scripts/ISLC1.txt and ISLC2.txt address an object named `mermaid` with
`startDialog('mermaid', …)` and `hideMonster('mermaid')` (grep); nothing in the class itself
reads properties or runs scripts.

Per-machine: (a) none found (the scan; body read). (b) Mermaid_draw 0x285c30 is one
`Creature_draw` call. (c) none.

---

### Orc, Skeleton, Soul, the arachnids

*Reader's notes for this group.* Everything is Observed at the address given unless marked Inferred or Unknown. Angles are
16-bit units as written in the code. "rand" = `GameObject_rand` (the object's own generator,
16-bit result) unless another source is named.

#### Orc  (factory names `Orc2*`, `Orc*`; vtable 0x50ffd0; size 0x488)

Functions: ctor 0x2a0954, pickHandParts 0x2a14f8, applyVariantFlags 0x2a169c, draw 0x2a1770,
run 0x2a1848, takeDamage 0x2a2eac, slot 12 (notify) 0x2a2ec8, saveState 0x2a3018, loadState
0x2a311c, setState 0x2a323c, severPart 0x2a3de0. Helper just outside the range, used by the
class: 0x2a4240 "hand 2 holds a shield" (hand-2 part index in 0xf..0x17).

One class holds six variants. **How the variant is chosen** (ctor 0x2a0c04–0x2a0d40): the
type name is compared, case-insensitively and as a prefix test (`str_prefixDiffers` 0x159c20),
against twelve names in this order; first match wins; no match leaves 0.

| +0x478 | names tested | role |
|---|---|---|
| 0 | `orcrecruit`, `orc2recruit` | melee, light |
| 1 | `orcsoldier`, `orc2soldier` | melee |
| 3 | `orcleader1`, `orc2leader1` (tested before `orcleader`) | melee, larger |
| 2 | `orcleader`, `orc2leader` | melee |
| 4 | `orcarcher`, `orc2archer` | archer |
| 5 | `orcshaman`, `orc2shaman` | caster / healer |

Model set: the factory (0x15b1f4–0x15b288) passes a flag as the last constructor argument:
1 for names starting `Orc2`; for names starting `Orc` it is 1 when `save_getAct()` (0x217edc,
the word 0x88d3d4) is 2 or more, else 0. Flag 0 = class block 0x501c80 (`orc.lmp`) with weapon
list 0x501f70 (`orc_weap.lmp`); flag 1 = class block 0x501df8 (`orc_vari.lmp`) with weapon
list 0x502090 (`orc_wep2.lmp`). The flag changes nothing else in the constructor.

Constructor: `Creature_ctor` max-hp argument = `rand % 14 + 4` (first draw of the object).
Embedded weapon holder at +0x3d8 (`WeaponShield`, table 0x50cda0), pointer in +0x50; weapon
list pointer in +0x480. Byte +0x28 = 0x28, speed +0xb8 = 80, turn rate +0xb0 = 1.2, radius
+0x1c = 18, state 0, cflags |= 0x40400, +0xec = sim frame, +0x47c = 0. No
`Creature_setStats` / `scaleStats` call (callee list); no property is read by the class
itself (`Creature_ctor` / `Creature_init` read theirs). Run list: `obj_runEvery60`.
Start animation: one of three idle clips (classdef +0xfc + 0x10 × (rand % 3)).
14 `creature_setDefEntryParams` calls (entries 0x13–0x1a and 3–8).
Then per variant, all from the own generator (0x2a0d50–0x2a10e8); r = one draw taken first:
- recruit (0) / archer (4): one of five model-variant bits (0x100/0x200/0x400/0x2/0x1 by bits
  0–2 of r). Recruit: if r & 0x32 and a second draw is even, hand 2 = part 0xf (shield).
  Archer: hand 2 = part 0x21; 10 % (draw × 2^-16 < 0.1) an element: draw % 3 → cold, fire,
  fire-burst.
- soldier (1): variant bits 0x400000 (+0x800000 if r&1) (+0x200000 if r&2), 0x2000, one of
  0x10/0x8/0x4, one of bits 15–18; if r & 0x16c hand 2 = part 0x11 or 0x13 (shield);
  10 % element: cold or fire.
- leader / leader1 (2, 3): variant bit 0x20 or 0x40 (+0x1000 with 0x20 when r&1), 0xe04000,
  bit 19 or 20; hand 2 = part 0x15 or 0x17 (always a shield); 10 % element: cold, fire,
  shock or poison (draw & 3).
- shaman (5): variant bit 0x20000000, no element, no shield.
The element is applied through the holder's table: offset 0x20 cold (kind 2), 0x10 fire
(kind 1), 0x30 shock (kind 4), 0x28 poison (kind 3), 0x18 fire-burst (kind 6); each calls
`creature_buildElementDamage` (0x1176e0) on the holder's descriptor at holder+0x50. The same
offsets are the ones `Creature_init` calls for the `ColdWeapons` / `FireWeapons` /
`ShockWeapons` / `PoisonWeapons` / `FireBurstWeapons` properties (0x10a3fc–0x10a5b0).
`creature_buildElementDamage` draws the shared seed once (creatures symbol file; body not
read here), so an orc that rolls an element costs one `g_randSeed` draw in its constructor,
and one more when a saved element is restored by loadState. The kind numbers read back
through holder offset 0x84 are those of `damageDesc_getElement` (0x117e88, read): descriptor
type 0x15 → 1, 0x16 → 2, 0x17 → 3, 0x18 → 4, 0x1f → 6.
- pickHandParts 0x2a14f8 (hand 1): recruit part 1, 5 or 7 (bits of one draw); archer hand 1 =
  3 and hand 2 = 0x21; soldier 9, 0xd or 0x1b; leaders 0x1b, 0x1d or 0x1f (draw % 3).
- applyVariantFlags 0x2a169c: clears cflags 0xe00000000 and tint +0xa0, then recruit/archer
  cflag 0x200000000; soldier 0x800000000; leaders 0x2000000000 (leader1 also scale +0xdc =
  1.3 and radius 22); shaman 0x400000000 and tint preset 6. What these cflags do was not
  traced (Unknown).

Fields:
| offset | type | meaning | where |
|---|---|---|---|
| +0x3c8 | Vec3 | target position stored at the end of each chase frame | written 0x2a1cc0 (state 3), state 4; read state 4 |
| +0x3d8 | object | weapon holder (`WeaponShield`) | ctor |
| +0x478 | s32 | variant 0–5 (table above) | everywhere |
| +0x47c | s32 | shaman: clock value until which it stays in state 0x17 after a cast | set at the end of state 6, read state 0x17 |
| +0x480 | ptr | weapon part list (static block 0x501f70 or 0x502090) | holder update/draw, severPart |
| +0xf4 | s32 | state 0: clock after which it starts wandering; state 6: frames to stand after the swing; state 0x11: clock when the block ends; state 0x17: clock deadline | setState |

Run prologue (0x2a1848): `Creature_processDamage`, `Creature_run` (non-zero ends),
`Creature_updateActive` (0 ends), holder update (table offset 0xac, arguments 0.5, weapon
list, this), `Creature_stepAnim(1.0)` → events `ev`, `Creature_applyKnockback(0.4)`, slot 23
with 0, then the state switch. "melee" below = variants 0–3.

States:
- 0 idle: archer first tries slot 25 with force = 1; everyone then slot 25 with 0; either
  non-zero → 3. Otherwise → 1 when clock > +0xf4 (set on entry to clock + 120 + rand % 60) or
  when `Creature_isAwayFromHome`; else stay.
- 1 wander: same two sight tests → 3; else `Creature_moveToDest` (which itself requests state
  0 on arrival). Entry: `Creature_pickWanderDest`; speed 90 for leaders and shaman, 80 others.
- 2 run to an alert point (entered only from slot 12, see below; speed 170, leaders/shaman
  90): sight tests → 3; else `Creature_moveToDest`; when that returns 0 → 0.
- 3 chase. No target → 0. Every exit of the melee branch copies the target position to +0x3c8.
  - melee: target within 30 and inside arc 6000 of the facing (`Creature_canSeeTargetIn(0,
    30, 0, this, facing, 6000, 0)`) → 6. Else within 30 in any direction → turn toward it.
    Else: soldiers and leaders with `Creature_countAlliesNearTarget(30)` > 0 → 0x17; recruits
    with that count > 1 → 0x17. Else, recruits and soldiers only: when rand % 30 == 0 and
    fewer than 3 living non-player creatures are in the box of half-size (target radius ×
    1.75) around the target (0x108970), compare the bearing from the orc to the target with
    the target's facing: `(bearing − targetFacing + 0x3fff)` unsigned < 0x7fff → 4, otherwise
    `Creature_moveToTarget`. In all remaining cases `Creature_moveToTarget`.
    Entry speeds (setState case 3): recruit 170, soldier and archer 80, leaders and shaman 90.
  - archer: target within 80 any direction → 0x10 (back off); else within 400, arc 6000,
    ray mode 1 → 6; else `Creature_moveToTarget`.
  - shaman: within 400, arc 6000, ray mode 1 → 6; else within 30, arc 6000 → 7; else within
    6000 any direction → only turns toward the target (does not approach); else
    `Creature_moveToTarget`.
- 4 run in (recruits and soldiers, speed 170): no target → 0. In reach (30, arc 6000) → slot
  27 with 6; within 30 any direction → turn. Then: if rand % 30 == 0 and the target moved
  less than 1.3333 units (2-D) from the position stored in +0x3c8 → 3, else
  `Creature_moveToTarget`. Stores the target position. (setState 4 entered from state 3 also
  writes +0xf4 = clock + 40 + rand % 120; nothing reads it while in state 4.)
- 5 between attacks (root timer +0x314 running): melee in reach (30, arc 6000) → request 6;
  archer/shaman with the 400 / 6000 / ray-1 test → request 6 (the filter keeps 5 while the
  timer runs); then `Creature_isNotRooted` → 3. Entry animation: archer and shaman own
  clips; melee with a shield use the guard clip (classdef +0xe4), others one of three.
- 6 attack. Entry: +0xf4 = 10 + rand % 10; clip chosen by variant, hand-1 part (1, 5, 9 use
  the two-clip set) and draws. While the clip plays (anim flag 8) the function returns after
  the per-variant work; once it has ended, each frame: +0xf4 −= 1, and if the holder reports
  hand 2 occupied (table offset 0x74 with hand 2) cflag 0x200 (blocking) is set; when +0xf4
  reaches 0: shaman sets +0x47c = clock + 60 + rand % 60 and → 0x17, everyone else → 3.
  `setState` clears cflag 0x200 on every accepted state change (0x2a3268–0x2a3280).
  - melee: on event bits 0 or 1 (`ev & 3`): `Creature_hitTargetAtReach(36, this, +0xd0, +0xd2,
    +0xd4, flags, descriptor)` — the target is hit when it is alive and within 60 units of
    the point 36 ahead of the orc; flags 0x40008 when the target lacks object flag 0x40 (not
    a player), 8 when it has it; descriptor = holder table offset 0x8c for hand 1 (the
    holder's element descriptor). On bit 0 additionally: rand % 5 == 0 → request 3. While the
    clip plays: `Creature_turnToTarget`.
  - archer: aim point = position + facing × 300, replaced by `Creature_leadTargetPoint(400)`
    (target position + target velocity × distance / 400, z + half height) when there is a
    target. Bit 0: hand 2 part = 0 (arrow leaves the hand); origin = position + (0, 0, 48);
    velocity = unit(aim − origin) × 400 + a random vector inside the unit sphere × 40
    (rejection loop, three draws per attempt); one more draw picks one of four sounds; then
    by the element kind of hand 1 (holder offset 0x84):
    kind 2 → `ColdArrowProjectile` (pool 0xb0, ctor 0x2d718c, skill pointer `ColdArrow` 44);
    kind 1 → `FireArrowProjectile` (0xb0, ctor 0x2d6440, `FireArrow` 43);
    kind 6 → `ExplodeArrowProjectile` (0x74, ctor 0x2dafe0, `ExplodeArrow` 47);
    these three get position = own position + (0, 0, height × 0.5 + 12), the velocity, the
    orc, `(int)` of the monster-level float 0x4f714c and the Skill pointer (no skill-table call
    here — the pointer is a constructor argument);
    anything else → plain `MissileWeapon` (pool 0x1c8, ctor 0x150ee4, kind 0, two words from
    the static block 0x3e9ce0 (+8, +0xc), origin, velocity, angle = atan2(vy, vx) − 0x4000,
    owner, damage +0xd0..+0xd2, rating +0xd4, last argument 4).
    Bit 1: hand 2 part = 0x21 again. While the clip plays: slot 26 (mode 0) toward the aim.
  - shaman: same aim point. Bit 0 only: if the target is within 80 (any direction) neither
    search is made; otherwise `creature_findCorpseOfClass(400)` and
    `creature_findWoundedAlly(400)`. Priority:
    1. corpse found → its slot 32 (revive) with 1, a sound on the corpse;
    2. wounded ally found → `Healing` (55) skill-table offset 0x14 (cast) with (slot 35 value
       of the shaman, **the ally in the caster argument**, the shaman's own position, the
       shaman's facing); the returned spell is linked to the shaman with `creature_addSpell`;
    3. else rand % 3 == 0 → `PoisonRain` object (pool 0x6c, ctor 0x2f8f48: (int) monster
       level, shaman, aim point, Skill pointer `PoisonRain` 24, classdef +0x16c) — created
       directly, no skill-table call; otherwise `Shock` (37) offset 0x14 with (slot 35 value,
       shaman, position + (0, 0, height/2), facing).
    Each branch also writes the two flash colour quads +0x90..+0x9e. No 0x0c "can cast" call
    anywhere in the class.
- 7 shaman melee: bit 0 → `Creature_hitTargetInArc(0, 30, this, facing, 6000, +0xd0, +0xd2,
  +0xd4, flags 1, holder descriptor)`; clip ended → 0x17.
- 0x10: `Creature_isAttackReady` → 0, else `Creature_fleeFromTarget`. Entry: +0x318 = 60,
  speed 170 (shaman 130).
- 0x11 shield block: entry sets cflag 0x200, the guard clip and +0xf4 = clock + 120; run:
  clock > +0xf4 → 3.
- 0x12: until anim flag 0x10 clears → 3. A request for 0x12 while in state 6 with the clip
  still playing is turned into "stay in 6" (0x2a3aac–0x2a3acc): an attacking orc is not
  interrupted by the hit reaction.
- 0x13: `Creature_isNotStunned` → 0.
- 0x14: `Creature_deadUpdate(30, this, ev, (−cos, −sin) × 30, 0)`.
- 0x17 hold near the target (entry: idle clip, +0xf4 = clock + 240 + rand % 240). No target →
  0. Shaman: clock > +0x47c → 3; else in reach (30, arc 6000) → 7; else turn toward the
  target. Archer: turn only. Soldier / leaders: target within 30 any direction → 3; else when
  `countAlliesNearTarget(30)` is 0 → 3; else keep waiting. Recruit: in reach (30, arc 6000) →
  3; clock > +0xf4 → 3; else when the count is below 2 → 3. Always ends with
  `Creature_turnToTarget`.
- 8–0xf, 0x15, 0x16: the run function returns at once; setState has no case for them.

setState 0x14 (0x2a3b10): byte +0x28 = 0x46; both hands dropped through the holder (table
offset 0x5c, hands 1 and 2). Dismemberment: only when (`g_decalDetail` 0x44fdc0 ≥ 2 **or**
`g_networkMode` 0x402791 is non-zero) and the pending-damage flag word +0x2dc equals exactly
8: rand % 100 < 25 → part = rand % 5 + 1, skipped when model-variant bit 0x400000 is set and
part is 4 or 5, or bit 0x800000 and part is 2 or 3; otherwise severPart 0x2a3de0: hides the
part (variant bits 0x10000000 >> (part−1)), reads the attach point (bones 8, 6, 7, 4, 5) and
creates a `GutChunk` (pool 0x268, `GutChunk_ctorFromProp` 0x201ad0) with a part mask built
from the orc's variant bits. (Parts 6 and 7 of the helper would drop a hand part as a
`PhProp`; the only caller never passes them.) Death clip: leaders always clip 3; a severed
part selects 6/4/5/7/8; otherwise 4 + rand % 5. Unless cflag 0x100000000: `Creature_dropLoot`
and, for the archer, rand < 8000 (of 65536) → `loot_spawnNamedItem(pos, "arrows")`. Then
slot 28 with 0.

takeDamage 0x2a2eac: tail call to `Creature_takeDamage`.

Slot 12 (0x2a2ec8; arguments kind, position, source object):
- kind 0 (sent by `Creature_processDamage` 0x110dc8 for any creature with pending damage,
  box of 600, **only when `g_numPlayers` == 1**): if the source's dynamic type is exactly Orc
  (`rtti_typeInfoEquals` with 0x3c4658) and this orc is in state 0 or 1 → state 2 and the
  destination +0x104 = the given position.
- kind 2 (docs/player.md: a player aims a ranged attack at it): if hand 2 holds a shield,
  state is 3 or 5 and the bearing to the source is within ±9999 of the facing → state 0x11.

Save / load (0x2a3018 / 0x2a311c): after the creature record, four words: variant, hand-1
part, hand-2 part, element kind of hand 1. Load restores them (element through holder offset
0x44), re-runs applyVariantFlags, and empties hand 2 when the loaded state is 0x14. The model
variant bits and the shaman timer are not in the class record.

Phases: none (no hit-point threshold in the class).

Script-driven: nothing class-specific found in run/setState (no property read, no script
call). Level scripts were not searched beyond a name grep.

Per-machine:
(a) None found (the scan on run, setState, takeDamage, slot 12, ctor and the three helpers, then
by hand). Every decision draws from the own generator. Two things to know: the dismember
branch reads the local option 0x44fdc0 but takes network mode as an alternative, so in a net
game the draws and the `GutChunk` creation do not depend on it (offline they do; the
`GutChunk` life-time issue is docs/objects.md O2 and Orc is one more creator of that class);
the scan's "hardware timer" hit at 0x2a415c is a false match on the constant 0x10000000.
(b) No: Orc_draw 0x2a1770 stores nothing in the object.
(c) No: it calls `Creature_draw`, the holder's draw (table offset 0x94) and, for the archer,
one extra model-part draw (0x178c28 with weapon-list entries +0x5c / +0x64).

Open: what cflags 0x200000000 / 0x400000000 / 0x800000000 / 0x2000000000 are for; the body
of `MissileWeapon_ctor` and of the three arrow constructors (not in this range); why Healing
is cast with the ally in the caster argument (the skill's cast body was not read).

#### Skeleton  (factory names `WatSkel`, `Skeleton*`; vtable 0x5175f8; size 0x478)

Functions: ctor 0x2a5af4, draw 0x2a67c4, run 0x2a6864, saveState 0x2a7508, loadState
0x2a75d4, slot 12 (notify) 0x2a7688, takeDamage 0x2a774c, setState 0x2a7768, hasShield
0x2a7da0, slot 20 (isEnemy) 0x2a7e04, shatter 0x2a7ef0, and two unreferenced formation
helpers 0x2a815c / 0x2a8378. (0x2a59f0, listed with this range, is a Scorpion helper: its
only caller is Scorpion_setState 0x2a5908 — see Scorpion.)

**How the variant is chosen.** Three independent things:
1. Model set = last constructor argument n; class block = 0x5022e0 + n × 0x40
   (0 `skelnorm.lmp`, 1 `skelwat.lmp`, 2 `skelred.lmp`, 3 `skelblue.lmp`). The factory passes
   1 for the exact name `WatSkel` (0x15b4b4–0x15b4ec) and 0 for names starting `Skeleton`.
   Its tests for sets 2 and 3 (0x15b50c–0x15b594) compare the *same* name pointer, which has
   just matched the prefix `Skeleton`, against the prefixes `red` and `blue`; they cannot
   succeed, so sets 2 and 3 are never selected by the factory. The other caller (0x2bfe2c, a
   Wraith helper, not read) passes the name pointer stored at 0x5034ec (`Skeleton`) and set 0. Animations and weapon parts
   are shared by all sets: static block 0x5023e0 (`skelcom.lmp`).
2. Weapon kind +0x3d0 and side +0x3d4 from the type name (ctor 0x2a5d10–0x2a5f10;
   case-insensitive prefix tests in this order; default kind = rand % 5, side 0):

| name prefix | kind +0x3d0 | side +0x3d4 |
|---|---|---|
| `skeletonred` / `skeletonblue` | random | 2 / 1 |
| `skeletonswordohwred` / `…blue` | 0 one-handed sword + shield | 2 / 1 |
| `skeletonsworddhwred` / `…blue` | 1 two-handed sword | 2 / 1 |
| `skeletonaxered` / `…blue` | 2 axe | 2 / 1 |
| `skeletonspearred` / `…blue` | 3 spear | 2 / 1 |
| `skeletonbowred` **and** `skeletonbowblue` | 4 bow | **2 for both** (0x2a5e74–0x2a5e84) |
| `skeletonswordohw`, `skeletonsworddhw`, `skeletonaxe`, `skeletonspear`, `skeletonbow` | 0, 1, 2, 3, 4 | 0 |

3. Hand parts, element and model-variant bits from own draws (0x2a5f1c–0x2a63a4): kind 0 hand
   1 = part 0x54 or 0x52 and hand 2 = 0x60 or 0x62 (the shield); kind 1 hand 1 = 0x5e; kind 2
   0x5c or 0x5a; kind 3 0x66 or 0x64; kind 4 (bow) hand 1 = 0x58. Element with 10 % chance:
   kinds 0–3 cold or fire, kind 4 cold, fire or fire-burst (holder offsets 0x20 / 0x10 /
   0x18 as for Orc, with the same one shared-seed draw when an element is rolled). Variant
   bits: optional bit 0–2; bow gets 0x80, others optionally one of bits 9–20; one of bits
   21–25 unless bit 14 is set; bit 5 or 6. cflags by those bits:
   0x800000000 if any of 0x21e00, else 0x2000000000 if any of 0x1de000, else 0x10000000000
   (meaning not traced).

Constructor: `Creature_ctor` max-hp argument 10; holder (`WeaponShield`) at +0x3d8; byte
+0x28 = 0x14; turn rate 1.2; radius 18; **speed +0xb8 = 0 and the class never writes it
again** (Inferred: it moves by clip root motion — the walk/chase clips are started with flag
0x803); byte +0xb4 = 0x10; resistance floats +0x64 and +0x68 = 1.0; cflags |= 0x10000;
+0x3c8 = +0x3cc = 0; +0xec = sim frame. HomeRange +0x3c0 = 1000 for side 0, 200 for a red or
blue skeleton. No `Creature_setStats` call. No property read by the class. Direct call of
`Skeleton_setState(0)`, `obj_runEvery60`, 15 calls of 0x1183d0 on block 0x5023e0, then
`Creature_init`.

Fields:
| offset | type | meaning | where |
|---|---|---|---|
| +0x3c8 | handle | "skeleton I follow" | zeroed in ctor; used only by 0x2a815c / 0x2a8378 / 0x2a873c (unreferenced) |
| +0x3cc | handle | "skeleton following me" | same |
| +0x3d0 | s32 | weapon kind 0–4; indexes the 0x70-byte per-kind clip rows at 0x5023e8 | ctor, setState, run, save |
| +0x3d4 | u8 | side: 0 none, 1 blue, 2 red | ctor, slot 20 |
| +0x3d8 | object | weapon holder | ctor |
| +0xf4 | s32 | state 0/1/0x11: clock deadline; 3→5: "wait in line" deadline; 6/8: frames to stand after the clip | setState, run |

Run prologue as Orc (holder update with block 0x5023e0; `Creature_applyKnockback(0.7)`).
States:
- 0 idle (entry: +0xf4 = clock + 120): slot 25 with 0 → 3; bow also slot 25 with 1 → 3;
  clock > +0xf4 or `Creature_isAwayFromHome` → 1.
- 1 walk (entry: `Creature_clearPath`, +0xf4 = clock + 300; **no** `Creature_pickWanderDest`,
  so it walks to whatever +0x104 holds): same sight tests → 3; while clock ≤ +0xf4
  `Creature_moveToDest`; after that → 0.
- 3 chase. No target → 0.
  - bow: `Creature_canSeeTargetIn(0, 400, 0, this, facing, 2000, 1)` → 8; else the same with
    arc 0x7fff → turn toward the target; else `Creature_moveToTarget`.
  - others: within 24, arc 6000 → 6; else `creature_allyInLineOfFire(300, radius × 3, this,
    target, 0)` non-zero → +0xf4 = clock + 240 + rand % 240 and state 5 (wait behind the
    ally); else within 20 any direction → turn; else `Creature_moveToTarget`.
- 5 wait: bow with (400, arc 2000, ray 0) → 8; others within 20, arc 6000 → 6. Otherwise,
  once `Creature_isNotRooted`: clock > +0xf4 → 3; no target → stay; else
  `creature_allyInLineOfFire(…, 1)` zero → 3.
- 6 melee (entry: one of two clips for the kind, +0xf4 = 20 + rand % 20): bit 0 →
  `Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags 8, holder descriptor)` (hit
  when the target is within 60 of the point 36 ahead). While the clip plays: turn toward the
  target. After it ends: cflag 0x200 (blocking) is set while there is a target — for every
  kind, shield or not — and +0xf4 counts down one per frame; at 0 → 3.
- 8 bow shot (entry: +0xf4 = 1). No target → slot 27 with 0. Aim point = `Creature_leadTargetPoint(400)`
  (default 300 ahead). Bit 0: hand 2 part = 0; origin = position + (0, 0, height × 0.5 + 18);
  d = aim − origin; angle = atan2(d.y, d.x). If |angle − facing| > 1000 the aim point is
  reset to 300 straight ahead, but d is **not** recomputed and the angle is recomputed from
  the same d (0x2a6f6c–0x2a7014), so the shot direction is unchanged; only the point used for
  turning changes. Velocity = unit(d) × 400 + random in-sphere vector × 48 (three draws per
  attempt), one draw for the sound. Then by hand-1 element kind (holder offset 0x84):
  2 → `ColdArrowProjectile` (pool 0xb0, ctor 0x2d6fb4), 1 → `FireArrowProjectile` (0xb0, ctor
  0x2d6238), 6 → `ExplodeArrowProjectile` (0x74, ctor 0x2daeb4) — these take (origin, the
  **angle**, owner, (int) monster level 0x4f714c, Skill pointer 44 / 43 / 47), not the
  velocity, so the spread does not apply to them; otherwise `MissileWeapon` (pool 0x1c8, ctor
  0x150ee4: kind 0, origin, velocity, angle − 0x4000, owner, damage min = +0xd0, **max =
  +0xd2 / 2**, rating +0xd4, last argument 4 — 0x2a7320–0x2a7388). Bit 1: hand 2 part = 0x56.
  While the clip plays: slot 26 toward the aim point. After it ends, +0xf4 −1 → 3.
  No skill-table call is made; the Skill objects are only constructor arguments.
- 0x10: `Creature_isAttackReady` → 0, else `Creature_fleeFromTarget`.
- 0x11 block (entry: cflag 0x200, +0xf4 = clock + 120): clock > +0xf4 → 3.
- 0x12: anim flag 0x10 clear → 3. 0x13: `Creature_isNotStunned` → 0.
- 0x14: `Creature_deadUpdate(20, this, ev, zero vector, 1)` (the object is already queued for
  deletion, see below).
- 0x17 rise: `fx_spawn(7, position)` every frame; anim flag 0x10 clear → 0.
- 2, 4, 7, 9–0xf, 0x15, 0x16: run returns at once. setState has a case 7 (a third attack
  clip, +0xf4 = 20 + rand % 20) but nothing in the class requests 7 and run does nothing in
  it.

setState (0x2a7768): every accepted change clears cflag 0x200; every change except to 0x17
also clears 0x200000 and 0x800 (0x2a7798–0x2a77c0).
- 0x17: sets cflags 0x200800 (docs/creatures.md: 0x200000 "model not drawn by
  `Creature_draw`", 0x800 "nobody's enemy or ally"), queues the rise clip (flag 0x10) and
  chains the idle clip. A request for 0x12 while in 0x17 is turned into "stay in 0x17".
- 0x12: picks between two clips on cflag 0x200, but the flag was cleared a few instructions
  earlier in the same call, so the "blocking" clip (0x502404 row) is never chosen.
- 0x14: both hands dropped through the holder; object flags |= 0x4002; cflags |=
  0x20000000000; shatter(this, 8); unless cflag 0x1000000 (the bit generators set on what they
  spawn — not the 0x100000000 "revived" bit other classes test) `Creature_dropLoot(36, 2, 1.6,
  0.6, 1.6, 0.25, this, pos, facing, "bonechip")`; **`obj_delete(this)`**; slot 28 with 0. A
  skeleton leaves no corpse (so nothing for a reviver to find).
- shatter 0x2a7ef0 (this, group): fills the static table 0x8e44c0 with a zero-terminated list
  of 64-bit part masks for the group (group 8 = 16 masks, the whole body; groups 1–5 are
  never requested), and for each mask that intersects the visible-part mask +0x220 creates
  a `PhProp` (pool 0x248, `PhProp_ctor2` 0x1556c0, part mask = the intersection, flags
  0x107) at the skeleton's position and removes those bits from +0x220.

Slot 20 isEnemy (0x2a7e04): r = `Creature_isEnemy`; non-zero r is returned as r + 1. When r is
0 and the other object is exactly a Skeleton, alive (object flag 8 clear) and this skeleton
is not charmed (+0x312 == 0): returns 1 when the sides are 2 vs 1 or 1 vs 2. So red and blue
skeletons treat each other as enemies (score 1, below every base enemy, which scores at
least 2 here). Because `skeletonbowblue` gets side 2, a "blue" archer fights for red.

Slot 12 (0x2a7688): kind 2 only: hand 2 holds part 0x60 or 0x62 (hasShield 0x2a7da0), state 3
or 5, bearing to the source within ±9999 of the facing → state 0x11. No kind-0 response.

takeDamage 0x2a774c: tail call to `Creature_takeDamage`.

Save / load (0x2a7508 / 0x2a75d4): three words after the creature record: weapon kind,
hand-1 part, hand-2 part. The side byte, the element and the variant bits are not saved.

Unreferenced code (no call and no data pointer: `xref` and `ptrs` both empty):
- 0x2a815c: box ±200 around itself; among other Skeletons whose +0x3cc is empty and whose
  +0x3c8 chain does not lead back to this one (0x2a873c), inside an angular window, picks the
  nearest within 120 and links the pair (+0x3cc of the other ← this, +0x3c8 of this ← other).
- 0x2a8378: with a +0x3c8 link: heads for a point 48 units behind (or beside) the linked
  skeleton at speed 50, turns to its facing, `Creature_moveBy`; queues a line record through
  0x18fd18. Without a link: `Creature_moveBy` with a zero vector.
Inferred: an abandoned "march in file" behaviour.

Phases: none.

Script-driven: `ScriptGenerator_spawn` (0x265fc4, monsters symbol file) puts a spawned
Skeleton into state 0x17. No property or script is read by the class itself.

Per-machine:
(a) None for gameplay (the scan on run, setState, takeDamage, slots 12 and 20, ctor, helpers;
then by hand). `fx_spawn(7)` in state 0x17 (0x2a6998) is the camera-gated cosmetic call. The
"hardware timer" hit at 0x2a7f70 is the constant 0x10000010 of a part mask. shatter writes
the static scratch table 0x8e44c0 and reads it back in the same call.
(b) No: Skeleton_draw 0x2a67c4 stores nothing.
(c) No: `Creature_draw` and the holder draw only.

Open: where the speed comes from (root motion is Inferred); the meaning of the three cflags
chosen from the variant bits; the Wraith helper at 0x2bfd5c (not in this range).

#### Soul  (factory name `Soul`, exact; also created by Minion as `soul`; vtable 0x517740; size 0x3e0)

Functions: ctor 0x2a9478, draw 0x2a9678, run 0x2a9870, takeDamage 0x2aa908, slot 3 (empty)
0x2aab60, saveState 0x2aab68, loadState 0x2aabd0, setState 0x2aac38, slot 16 (get model)
0x2ab298, isDemonNear 0x2ab2b4, static initialiser 0x2ab39c + stub 0x2ab430 (builds the
particle definition 0x8e4600 used by every particle call of the class).
(0x2a946c, at the start of the range, is not a Soul function: its only caller is
Skelight_setState 0x2a9360, with arguments (this, 8); it only zeroes the first entry of the
static table 0x8e4560 — an emptied counterpart of Skeleton's shatter.)

Two different uses share the class:
- **Free soul** (factory 0x15b6ec, owner argument 0): an ambient creature. `Creature_setCharm(
  this, −1, 0)` in the constructor puts it permanently on team 0.
- **Held soul** (Minion_run 0x286cb4–0x286d10, on event bit 0 of a Minion state): created at
  the Minion's attach point 0 with the Minion as owner, linked from Minion +0x3c8 and put in
  state 0x1a. While held, Minion_run writes the soul's position and facing every frame
  (0x2862c0 prologue). The Minion later throws it (state 0x1b) as a homing missile.

Constructor (0x2a9478; arguments this, name, position, angle, props, owner): `Creature_ctor`
max-hp argument 10, class block 0x502778; turn rate 1.2; radius 15; byte +0x28 = 0x1e; speed
0; +0xf4 = 0; cflags |= 0x200080000, later |= 0x8000000000000000 ("is active"); the five
resistance floats +0x5c..+0x6c = 1.0; `obj_runEveryFrame`; one `creature_setDefEntryParams`
(entry 0xb); `Creature_init`. No `Creature_setStats`; no property read by the class.
Owner non-zero: object flags |= 9, owner handle +0x3c8 linked. Owner zero: when the level
name (0x41b721) equals `airhub` → `Soul_setState(0x22)`; otherwise it stays in state 0.

Fields:
| offset | type | meaning | where |
|---|---|---|---|
| +0x3c8 | handle | owner (the Minion holding it); cleared on entering 0x1b | ctor, setState, draw, slot 16 |
| +0x3cc | handle | homing victim, written by Minion_run (0x2862c0 state 8: `creature_findEnemyInCone(275, 500, minion, facing, 2000)`) just before it requests 0x1b | run state 0x1b |
| +0xf4 | s32 | clock deadline of the current state | setState, run |

The class block has two models: +0xc / +0x14 (standing figure, drawn by `Creature_draw`) and
+0x1c / +0x24 (the held / flying shape). Slot 16 returns +0x1c while owned, else +0xc.

Run prologue: `Creature_processDamage`, `Creature_run`, `Creature_updateActive`,
`Creature_stepAnim(1.0)`, `Creature_applyKnockback(0)`, slot 23; then, when not owned and not
in 0x1b, `Creature_moveBy` with a zero vector (gravity / push-out only).

States (free soul):
- 0 (entry: +0xf4 = clock + 60 + rand % 120): every 16th frame (`(g_simFrame ^ serial) & 15
  == 0`) isDemonNear → 0x18. Else clock > +0xf4 or `Creature_isAwayFromHome` → 1.
- 1 wander (entry: `Creature_pickWanderDest`, +0xf4 = clock + 300 + rand % 120): same Demon
  test → 0x18; `Creature_moveTo(dest)` arrived, or clock > +0xf4 → 0.
- 0x18 alarmed (entry: +0xf4 = clock + rand % 120, own clip): every 16th frame, no Demon
  near → 0.
- 0x12 / 0x19: wait for anim flag 0x10 to clear → 0x18. A 0x12 request calls slot 27 again
  with 0x19 when already in 0x18 (flinch clip) or with 0x18 otherwise, then stores 0x12.
- 3: target gone → 0 (nothing requests 3 in the class). 5: `Creature_isNotRooted` → 0.
  0x17: clock > +0xf4 → 1.
- Requests for 0x10 and 0x13 leave the state unchanged (no back-off, no stun state).
- 0x14 dead (entry: death clip, +0xf4 = clock + 180, object flag 0x4000, slot 28 with 0 —
  **no `Creature_dropLoot`**): each frame up to 3 particles at random model sample points;
  when clock > +0xf4 or the clip has ended (flag 0x80): 2 particles per sample point, object
  flag 2, `obj_delete`.
- 0x22 (level `airhub` only; there every request is rewritten to 0x22, 0x2aac78–0x2aac8c;
  entry: death clip, +0xf4 = clock + 300, object flags |= 9): same particle loop as 0x14; at
  the end object flags |= 0xb and `obj_stopRunning` (hidden, not deleted).
- isDemonNear 0x2ab2b4: box ±300; true when it contains an object whose dynamic type is
  exactly `Demon` (typeinfo 0x3ca81c) with object flag 8 clear.

States (held soul; requested by Minion_run / Minion_setState through slot 27):
- While +0x3c8 is set, `Soul_setState` accepts only 0x1a–0x20 (0x2aaca0–0x2aacc8).
  0x1a, 0x1c, 0x1e, 0x1f, 0x20: only start a clip; run does nothing in them.
- 0x1d: on event bit 0: 2 particles per sample point (through the owner's attach matrix
  0x287940), object flag 2, `obj_delete`.
- 0x1b thrown (entry: owner handle cleared, +0xf4 = clock + 240; **once in 0x1b no state
  request is accepted**, 0x2aaccc–0x2aace4). Each frame: up to 3 trail particles. With a
  victim: aim = victim position + victim velocity (+0x308, +0x30c) × 0.2, turn rate +0xb0 =
  0.4, slot 26 toward it; velocity = (cos facing × 400, sin facing × 400, z of the unit
  vector to the victim × 400, forced to at most −60). Without: (cos × 400, sin × 400, −80).
  The position is advanced directly (no `Creature_moveBy`) in 4 sub-steps of velocity / 240.
  After each sub-step, for each player slot below `g_numPlayers` (table 0x4dcec8, stride
  0x4c30) whose object is alive: if the point 36 ahead of the soul is within (soul radius +
  player radius) of the player's centre → `damage_apply(10, 50, player, soul, rating 100000,
  0, 0, flags 0x4000140, no descriptor, 0)`, mark "hit", stop scanning players for this
  sub-step. The sub-step loop is not left on a hit, so up to four applications can happen in
  the frame of contact. After the four sub-steps: if nothing was hit, clock ≤ +0xf4 and the
  soul is not below `terrain_height` → keep flying; otherwise `obj_delete` and 2 particles
  per sample point. Only players are ever damaged; the victim handle only steers.
- 0x21 (requested by Minion_setState case 0x14 for the soul it still holds): particles,
  object flags |= 0x4002, `obj_delete` — but the request arrives while +0x3c8 is still set,
  so the filter above rejects it. Observed at both ends; what then happens to that soul was
  not traced (Unknown).

takeDamage 0x2aa908: compares the dynamic type of the attacker with `Demon`. Only then:
`Creature_takeDamage`, followed by up to 6 particles (1 + 3n own draws each). Damage from
anything else is ignored. A null attacker goes to the bad-typeid throw routine 0x3b3338
(0x2aa908 head) — Observed; whether any damage source reaches a Soul without an attacker is
Unknown.

Other overrides: slot 3 (trigger) is empty. Save / load: on `airhub` nothing is written or
read (0 bytes); elsewhere the plain creature record. Slot 15 (clone) is the base
`Creature` clone 0x11c298 (0x3c8 bytes) although the object is 0x3e0 bytes (vtable).

Phases: none. Script-driven: nothing in the class.

Per-machine:
(a) None found (the scan on run, setState, takeDamage, ctor, isDemonNear; then by hand). The
periodic test uses `g_simFrame` and the serial byte; the player scan uses `g_numPlayers` and
the player table; every particle position/velocity is drawn from the own generator in run
code, before `particle_spawn`, so the draw count does not depend on the particle pool or the
camera. One draw-count dependence on data: the rejection loops.
(b) No: Soul_draw 0x2a9678 only builds matrices on the stack.
(c) No: `Creature_draw` or `model_draw` (0x1779b0) with the second model.

Open: the fate of a held soul whose Minion dies; who (if anyone) can damage a Soul with a
null attacker; cflags 0x80000 and 0x200000000.

### Arachnid family: Scorpion, BlackWidow / Drachnid, SmallSpider

Shared traits (Observed in each constructor): `Creature_ctor`, no `Creature_setStats` call,
no property read by the class, byte +0xb4 = 0x12, cflags 0x8000001000 (0x1000 is a body
material bit; 0x8000000000 not traced), `obj_runEvery60`, default slot 2 (base
`Creature_takeDamage`) and base save/load. Scorpion and BlackWidow share the "poison bite":
a damage descriptor built on the stack whose first free effect slot is set to type 0x17
(poison) with v1 = +0xd0, v2 = +0xd2, v3 = 0, passed with flags 0x10004. Both drop a named
item through the last argument of `Creature_dropLoot`. SmallSpider is a harmless critter.

#### Scorpion  (factory name `Scorpion`, exact; vtable 0x50fe88; size 0x3d0)

Functions: ctor 0x2a4d68, draw 0x2a5030, run 0x2a5068, setState 0x2a55ec, severPart 0x2a59f0.
Constructor: max-hp argument 10; class block 0x502238; turn rate 1.2; byte +0x28 = 0x46;
speed 0; resistance float +0x64 = 0.4; scale +0xdc = 0.75 + 0.05 × (rand % 6) (double
arithmetic through 0x3aef58 / 0x3af410 / 0x3afb90; the 0.75 is the constant
0x3fe8000000000000 — the helper identities are Inferred); radius = 30 × scale; byte +0x3c8 =
rand & 1; start clip classdef +0x84; six `creature_setDefEntryParams` (entries 5–8, 0xb, 0xc).
Fields: +0x3c8 u8 skin index — draw passes classdef[+0x14 + 8 × skin] as the second model
argument of `Creature_draw` (0x2a5030). +0xf4: state 0 deadline; states 6/7 frames to stand.
Run prologue: processDamage, `Creature_run`, updateActive, stepAnim(1.0) → ev,
applyKnockback(0.5), slot 23.
States:
- 0 (entry +0xf4 = clock + 120 + rand % 60): slot 25 → 3; `Creature_isAwayFromHome` → 1;
  clock > +0xf4 → 1.
- 1: slot 25 → 0 (the request is 0, not 3: 0x2a519c); else `Creature_moveToDest`.
- 3: no target → 0; within 20, arc 6000 → 6; within 20, arc 0x7fff → turn; else
  `Creature_moveToTarget`.
- 5: within 20, arc 6000 → 6; else `Creature_isNotRooted` → 3.
- 6 claw / 7 sting. setState(6) decides: rand % 6 == 0 → the state becomes 7 (sting clip
  classdef +0x44), otherwise one of three claw clips; +0xf4 = rand % 20.
  - 6, bit 0: `Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags 8, no
    descriptor)`.
  - 7, bit 0: **first, when `g_difficultyIdx` (0x4f719c) is 2 the stored damage range +0xd0
    and +0xd2 is divided by 4, when it is 3 by 8 (signed, rounding toward zero), and the
    result is written back into the object** (0x2a5330–0x2a53b0). Then the poison descriptor
    (type 0x17, the new +0xd0, the new +0xd2, 0) and `Creature_hitTargetAtReach(36, this,
    +0xd0, +0xd2, +0xd4, flags 0x10004, descriptor)`. The write-back is not undone, so on
    those two difficulty values every sting hit frame (with a target, whether or not it
    connects) shrinks the damage of all later claw and sting attacks of that scorpion.
  - both: while the clip plays turn toward the target; after it, +0xf4 counts down; at 0
    one draw r: r & 1 → 0x17; else r & 2 → 0x18; else → 3.
- 0x17 / 0x18 (two display clips): `Creature_moveBy(zero)`; clip ended (flag 8 clear) → 3.
- 0x10: `Creature_isAttackReady` → 0 else flee. 0x12: flag 0x10 clear → 3. 0x13:
  `Creature_isNotStunned` → 0. 0x14: `Creature_deadUpdate(25, this, ev, zero, 0)`.
setState: 0x12 is ignored while stunned (state 0x13) and while a claw clip is still playing
in state 6. 0x14: rand % 3 == 0 → severPart(this, rand % 6): sets model-variant bit
1 << n, rebuilds the mask and creates a `GutChunk` (pool 0x268, `GutChunk_ctorFromProp`
0x201ad0) — no option or network test here; then `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4,
0.25, this, pos, facing, "poisongland")`, one of two death clips, slot 28 with 0.
Phases: none. Script-driven: nothing in the class.
Per-machine: (a) none found (the scan + by hand); `g_difficultyIdx` is shared game state.
(b) no stores in draw. (c) draw only calls `Creature_draw`.
Open: whether 0x4f719c values 2 and 3 are the two highest difficulties (not checked here).

#### BlackWidow  (factory: names starting `BlackWidow` → kind 0, exact `Drachnid` → kind 1; vtable 0x510de8; size 0x420)

Functions: ctor 0x2ab958, draw 0x2abdb0, run 0x2abdd8, setState 0x2acb78. Helpers just
outside the range that belong to the class: 0x2acfd8 severPart, 0x2ad158 reach (36 kind 1 /
24 kind 0), 0x2ad180 lunge range (120 / 60), 0x2ad1a8 constant 500. The web strand
controller embedded at +0x3d8 is shared with SpiderQueen (functions 0x2afc04 init, 0x2afc1c
arm, 0x2afc28 launch, 0x2b0080 update, 0x2afe38 queue the strand for drawing, 0x2b04ac
release, 0x2b04ec "active?"; read only as far as needed here).

Constructor: max-hp argument 32 + (rand & 7) + (rand & 7); class block 0x502870 + kind × 0xb0;
controller init (flight 35 frames, hold 180 frames); turn rate 0.7; speed 0; +0x3ac = +0x3ae
= 300 (the two sight ranges of the base class); resistance +0x64 = 1.0; +0x3c8 = clock +
rand % 360; radius 35 for kind 1; kind 0: radius 15, scale 0.5. Ten
`creature_setDefEntryParams`.
- kind 0 whose name starts `blackwidowpit`: clip classdef +0xa4 queued with flag 4, object
  flag 1, cflags 0x1200800, **start state 0x18**.
- other kind 0: idle clip, then `anim_randomizeTopTime` (cosmetic-seed phase, docs/engine.md
  P4), state 0. Kind 1: no clip queued by the constructor, state 0.

Fields:
| offset | type | meaning | where |
|---|---|---|---|
| +0x3c8 | s32 | clock before which no web shot / long pounce is tried (set to clock + 360 after one) | ctor, run 3/5/0x17, setState 10/0x17 |
| +0x3cc | s32 | 0 until the death clip has ended, then 1 | run 0x14 |
| +0x3d0 | s32 | clock at which the death clip ended | run 0x14 |
| +0x3d4 | float | sink offset of the corpse | run head/tail, run 0x14 |
| +0x3d8 | struct | web strand controller (to +0x414); its +0xc (= +0x3e4) is "attached" | run |
| +0x414 | s32 | kind: 0 BlackWidow, 1 Drachnid | everywhere |
| +0x418 | s32 | last attack state requested (6–10) | setState, run 3 |

Run (0x2abdd8): when cflag 0x1000000 is set, z += +0x3d4 on entry and z −= +0x3d4 on every
exit after the prologue (so the stored z is the sunk one, the logic sees the unsunk one).
Prologue as usual (applyKnockback 0.5), then every frame the controller update and the
strand queue call with the point 10 above the position.
States (reach R = 36/24, lunge L = 120/60):
- 0 (entry +0xf4 = clock + 120 + rand % 60): slot 25 → 3; away from home or clock > +0xf4 → 1.
- 1: slot 25 → 3 (unlike Scorpion, which requests 0); else `Creature_moveToDest`.
- 3: no target → 0. If the target is not charging (`Creature_isTargetCharging` 0x118f90) and
  is within R, arc 4000 → 5. If the last attack was not 9 and the target is between R and
  L, arc 4000 → 9. If clock > +0x3c8, the target is charging and is between L and 500, arc
  6000 → 5. Else, not charging and within R any direction → turn; else `Creature_moveToTarget`.
- 5: target within R, arc 4000: rand % 3 → 0: state 6; 1: state 7; 2: nothing this frame
  (the compiled test for "3 → state 8" can never be true, 0x2ac204). Otherwise, **only when
  `g_networkMode` == 0 and `g_pvpModeB` == 0** (0x2ac22c–0x2ac23c), clock > +0x3c8, target
  charging and between L and 500, arc 6000 → 10. Otherwise `Creature_isNotRooted` → 3.
  So the web shot is never started in a network game. (Inferred from the two transitions,
  not traced further: online, state 3 still requests 5 for a charging target between L and
  500, and 5 hands back to 3 as soon as the root timer is clear, so the two states alternate
  until the target is within R.)
- 6, 7, 8 bites: on event bit 1 (`ev & 2`): state 7 → `Creature_hitTargetInArc(0, R, this,
  facing, 4000, +0xd0, +0xd2, +0xd4, flags 0x10004, poison descriptor)`; states 6 and 8 →
  the same with flags 4 and no descriptor. Clip ended → 3. (Nothing requests 8.)
- 9 lunge: `Creature_moveBy(zero)`; bit 1 → the poison bite of state 7; clip ended → 3.
- 10 web shot (entry: +0x3c8 = clock + 360, controller armed): bit 0 → launch the strand at
  speed 300 from 10 above the position toward the target (0x2afc28). Controller no longer
  active → 3; controller attached → 0x17.
  Controller behaviour (0x2b0080, Observed): the tip flies in 3 sub-steps per frame for at
  most 35 frames; hitting the ground or a non-creature target leaves a `WebTrap` (pool 0xa0,
  ctor 0x2b07c0); reaching the target's radius attaches for 180 frames. While attached the
  target's knockback speed +0x2e8 is set to 160 and its knockback angle +0x2e0 to the
  direction of the spider every frame (it is dragged in); a player target (object flag 0x40)
  whose action state +0x58c is 1 lowers a counter from 5, at most once per 5 frames, and is
  released at 0.
- 0x17 reeling in (entry: +0x3c8 = clock + 360): controller inactive → +0x3c8 = clock + 360
  and 3. Target within R, arc 4000 → release the web and request 7 (poison bite). Turns
  toward the target.
- 0x18 pit emerge: bit 0 → cflag 0x200000 cleared (model drawn again); clip ended (0x80) →
  object flag 1 and cflag 0x800 cleared, state 0. While in 0x18 `setState` accepts only a
  request for 0.
- 0x10 / 0x13 as Scorpion. 0x12: flag 0x10 clear → 3; calls `Creature_applyKnockback(1.0)` a
  second time that frame.
- 0x14: without cflag 0x1000000: `Creature_deadUpdate(50, …, 0)`. With it:
  `Creature_deadUpdate(50, …, 1)`; when the death clip ends +0x3cc = 1 and +0x3d0 = clock;
  then at 10, 20, … 80 frames later severPart(this, 0 … 7) (one leg each, kind 0 only); after
  80 frames, every frame: 3 particles (def 0x8e46a0, 12 or more own draws), +0x3d4 += 0.15,
  +0x3c = z − +0x3d4; after 240 frames `obj_delete`.
setState: 6–10 store the state in +0x418. 0x12: clip chosen by pending-damage flags +0x2dc &
0x380000 (knockback strengths), else one of two by a draw. 0x14: severPart(this, rand & 7);
rand % 3 == 0 → severPart(this, 8); `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this,
pos, facing, "venomsac")`; one of four death clips; slot 28 with 0. Every state other than
0x18 clears cflag 0x800, and other than 0x14 also object flag 1.
severPart 0x2acfd8 (this, n): returns at once for kind 1. Sets model-variant bit 1 << n
(n 0–0xb); for n 0–7 also creates a `GutChunk` (pool 0x268, 0x201ad0, the creature's scale).
Phases: none (no hit-point threshold). Script-driven: nothing in the class; what wakes a pit
spider (object flag 1, clip queued with flag 4) was not traced — Unknown.
Per-machine: (a) none found (the scan + by hand). `g_networkMode` / `g_pvpModeB` are the same on
all machines of a session, but they make the class behave differently online and offline.
The strand queue call (0x2afe38 → 0x18fd18) fills a draw list from run code; nothing reads
it back in the class. Constructor: cosmetic-seed clip phase (engine.md P4). (b) no stores in
draw. (c) draw only calls `Creature_draw`.
Open: the controller functions' full behaviour (SpiderQueen area); meaning of flag 4 on the
queued pit clip.

#### SmallSpider  (factory name `SmallSpider`; vtable 0x50fd40; size 0x3c8 — no class fields)

Functions: ctor 0x2ab450, draw 0x2ab590, run 0x2ab5d8, setState 0x2ab704, onTouch 0x2ab8e0.
Constructor: max-hp argument 1; class block 0x502818; speed 50; radius 5 (10 is written
first); turn rate 0.7; scale 0.2; resistance +0x64 = 1.0; cflags also 0x4000000 (docs:
"friendly: picks no target, is nobody's enemy"); idle clip with `anim_randomizeTopTime`
(cosmetic-seed phase, engine.md P4); state 0.
Run: processDamage, `Creature_run`, updateActive, stepAnim, applyKnockback(1.0); **no target
picking, no attack**. State 0: clock > +0xf4 → 1. State 1: `Creature_moveToDest`. State
0x14: `Creature_deadUpdate(10, …)`. Nothing else.
setState: 0 → +0xf4 = clock + 120 + rand % 300; 1 → `Creature_pickWanderDest`; 5, 0x10, 0x12,
0x13 leave the state unchanged; 0x14 → object flags |= 9, `decal_add(10 + rand % 10, pos,
angle = an earlier draw, type 6, 1)` (three own draws in all with the clip choice), one of
four death clips (jumped to its end when the object is hidden), slot 28 with 0. No loot call.
onTouch 0x2ab8e0 (slot 6): touched by an object with flag 0x40 (a player) while not dead →
slot 27 with 0x14 (it is squashed); then the base `Creature_onTouch`.
Per-machine: (a) none in run / setState / onTouch (the scan + by hand); `decal_add` depends on
the local decal option (engine.md P15) but the draws are taken before the call.
Constructor: cosmetic-seed clip phase (P4). (b), (c): draw sets a model draw state
(0x179960 with 0), calls `Creature_draw`, resets it (0x179978); no stores.

### WoodElfSoldier, Wraith family, Vampire, UndeadKnight, Warrior, Ulthork, WarBoar

*Reader's notes for this group.* All statements are Observed at the address given unless marked Inferred / Unknown.
Method: every function in the listed ranges was read from the decompile, with the
disassembly (`tools/dis.py`) used where stack arguments or branch order mattered.
Animation handles are quoted as class-definition offsets (`def+0x..`), event bits are bits of
the `Creature_stepAnim` result.

#### WoodElfSoldier  (factory prefixes `WoodElf*`, `evilwoodelf*`; vtable 0x50f820; size 0x3e8)

Functions: ctor 0x2bc820, run 0x2bccec, draw 0x2bcc94, takeDamage 0x2bccd0 (plain tail call
of `Creature_takeDamage`), trigger (slot 3) 0x2bd968, setState 0x2bdb24, clone 0x129568,
destructor 0x3c4a48 (clears the handle +0x3c8, then `Creature_dtor`). Private helpers
0x2bcc38, 0x2be3fc–0x2bf1c8, static-init stubs 0x2bf26c / 0x2bf28c (these two sit in the
"Wraith" address range but belong here). 0x2bc7c8 sits in this range but is a **Warrior**
helper (only caller 0x2bb9f4 in `Warrior_run`); see Warrior.

Constructor (0x2bc820):
- Max-hp argument of `Creature_ctor` is `(GameObject_rand(this) % 14) + 4` as a float, but the
  draw is made at 0x2bc868, BEFORE `Creature_ctor`/`GameObject_ctor` has seeded +0x44 (the
  base constructor stores the seed unconditionally at 0x14cd80), on the block `pool_new`
  has just zero-filled. Inferred from that: the generator state is 0, the
  draw returns 0x3c6e (15470), 15470 % 14 = 0, so the argument is always 4.0 and the "random
  hit points" never vary. Class definition 0x503220.
- +0xb8 speed 100, +0xb0 turn rate 1.2, +0x1c radius 20, +0x28 draw half-width 40, state 0,
  +0xec = current sim frame, cflags |= 0x800040000 (0x40000 = ordinary blood; bit 35 not
  traced), +0x3c8 / +0x3d0 / +0x3e4 cleared.
- Variant +0x3cc from the type name (prefix test `str_prefixDiffers`, in this order):
  `woodelfsoldier` 0, `woodelfarcher` 1, `woodelfspear` 2, `woodelfscout` 3,
  `evilwoodelfsoldier` 0, `evilwoodelfarcher` 1, `evilwoodelfspear` 2, `evilwoodelfscout` 3.
- **Friendly or hostile**: a local flag is set only when one of the four `evilwoodelf…` names
  matched. When it is NOT set (the four plain names, and also any other name that reached
  this constructor through the factory prefixes, which keeps variant 0) the constructor calls
  `Creature_setCharm(this, -1, 0)` (permanent charm, team 0 — the same call script
  `charmMonster` makes) and sets object flag 0x1000000 (+0xc, "friendly to players")
  (0x2bca0c–0x2bca2c, call 0x2bca18). The evil names get neither and are ordinary monsters. Nothing else in
  the class tests friendliness; the rest follows from the base target pickers (charm team).
- 0x2bcc38 sets the model-variant bits +0xe8 by variant: 0 -> 0x80, 1 -> 0x100 (and registers
  the archer in the static archer list, below), 2 -> 0x200, 3 -> 0x4000; then
  `model_buildHideMask` -> +0x220, `anim_clear`, setState(0), +0xf4 = 0.
- Run list: variant 3 (scout) sets cflag bit 63 ("is active") and joins the every-frame list;
  all others join the staggered 60 list (0x2bca88 / 0x2bca98).
- Seven `creature_setDefEntryParams` calls (entries 0x11, 0x18, 0x19, 0x22, 0x1b, 0x23, 0x26),
  then `Creature_init`. No properties are read by this constructor itself.

Fields:

| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | handle | partner elf (spear <-> archer pair); never linked in the shipped code, see below | 0x2bea1c, 0x2be9cc, 0x2be884, run state 3 |
| +0x3cc | s32 | variant: 0 soldier, 1 archer, 2 spear, 3 scout | everywhere |
| +0x3d0 | s32 | cleared by ctor, copied by clone, otherwise unused | 0x2bc820 |
| +0x3d4 | Vec3 | position of the cosmetic "practice" arrow | 0x2bf0e4 (run), 0x2bf024 (draw) |
| +0x3e0 | s16 | heading of that arrow | same |
| +0x3e4 | s32 | 1 while that arrow is flying | same |
| +0xf4 | s32 | clock value: idle / wander / guard time-out | states 0, 1, 0x17 |

Static data: 0x503370 = array of 10 handles, the **archer list**. 0x2be7cc links an archer
into the first empty slot (silently does nothing when all 10 are used); 0x2bf1c8 is the
compiler's static constructor/destructor for the array (zeroes the 10 words / clears the 10
handles), reached through the stubs 0x2bf26c (pointer in the init table at 0x3e9a54) and
0x2bf28c (its address is the data word at 0x3e9b94, Inferred the destructor table). 0x2be81c removes a given object from the list but has no caller and no pointer
reference (xref); Inferred: entries go away only through the handle mechanism when the
object is deleted.

The pairing code is dead. 0x2be884 returns the nearest living (object flag 8 clear) list
entry whose own +0x3c8 is empty, within 600 units (squared distance < 360000), after
dropping the caller's existing partner (0x2be9cc unlinks both sides). 0x2be970 links the
result and the caller to each other through +0x3c8. **0x2be970 has no caller and no pointer
reference** (xref, plus a scan of the whole file for j/jal to it and for a data word
holding its address: none), and it is the only code that links +0x3c8, so 0x2bea1c ("has a living
partner") always answers 0. Consequences, Inferred: the spear's "stand between my archer
and the target" branch of state 3 and the guard state 0x17 are unreachable unless something
outside the class requests state 0x17 (docs/script.md lists only built-ins that request
states 0 and 0x14).

States (run 0x2bccec; order of work each frame: `Creature_processDamage`, `Creature_run`,
`Creature_updateActive` (inactive returns), `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.2)`, slot 23 pickTarget(0), 0x2bf0e4 (advance the cosmetic arrow),
then the switch):
- 0 idle: slot 25 canSeeTarget(0) -> 3. Else away from home -> 1. Else wait until clock >
  +0xf4; then an archer standing at a ledge (0x2bea48, below) -> 0x18, everyone else -> 1.
- 1 wander: sees target -> 0 (state 0 then sends it to 3 next frame). `Creature_moveTo`
  toward +0x104; arrived, or clock > +0xf4 -> 0.
- 2: sees target -> 0; `Creature_moveToDest(this,0)` until it returns 0 -> 0. No code in this
  class requests state 2.
- 3 chase: no target -> 0.
  - archer (1) and scout (3): the scout first tests melee, target within 24, arc 3000 -> 6.
    Then target within 400, arc 6000 -> 0x19 (shoot); otherwise `Creature_moveToTarget`.
  - spear (2): with a living partner (dead branch, see above): walk to the point 50 units
    from the partner toward the target; on arrival -> 0x17. Without: target within 70, arc
    2000 -> 6; within 70 at any angle (arc 0x7fff) -> turn toward it; else move to target.
  - soldier (0): target within 24, arc 3000 -> 6; within 24 at any angle -> turn; else move.
- 5 between attacks: scout within 24 / arc 3000 -> 6; archer within 400 / arc 6000 -> 0x19;
  spear within 70 / arc 2000 -> 6; soldier within 24 / arc 3000 -> 6; otherwise when the root
  timer is clear -> 3.
- 6 melee: with a target, on event bit 0 `Creature_hitTargetAtReach(60, this, +0xd0, +0xd2,
  attack rating +0xd4, flags, 0)` (hits the target if it is within 60 units of the point 60
  units ahead, 0x1196e8). Flags are 0x40008 when the target is not a player (object flag 0x40
  clear) and 0x8 when it is a player (test 0x2bd368, calls 0x2bd39c / 0x2bd3d8) — so only non-players get the
  knock-back-on-kill bit. Turns toward the target every frame. Animation over (flag 8 of
  +0x11a clear) -> 3.
- 0x10: `Creature_fleeFromTarget` until the attack cooldown is over -> 0.
- 0x12: until animation flag 0x10 clears -> 3. 0x13: until not stunned -> 0.
- 0x14 dead: `Creature_deadUpdate(20, this, events, v, 0)` with v = (-cos, -sin)(facing) x 20;
  on event bit 1, if object flag 2 is clear, sets object flag 1 (not solid).
- 0x17 guard (cflag 0x200 "blocking" is set for exactly this state by setState): no target ->
  0; clock > +0xf4 (entry + 60) -> 3; target within 70 / arc 2000 -> 6; else turn to target.
- 0x18 archer "practice shot" (cosmetic, but part of the simulation): on event bit 0
  variant bit 0x400 of +0xe8 is cleared (the arrow part; which sense of the bit means
  "visible" was not determined), one own-generator draw picks one of
  four arrow sounds (`swsh_arrow%d.anm` in `fx.lmp`), and the cosmetic arrow is started:
  +0x3d4 = own position with z + 58, +0x3e0 = facing, +0x3e4 = 1. On event bit 1 bit 0x400 is
  set again. Every frame 0x2becd8 re-tests the four ledge probes, stores the first probe
  that found the drop in +0x104 and turns toward +0x104 (slot 26, mode 0). Animation over
  -> 0. **No object is created and nothing is damaged**: the arrow is three floats advanced
  by 0x2bf0e4 (400 units/s along +0x3e0, z falling by 400 x sin(0x2000) per second, 1/60 per
  call) and switched off when z < 0 (absolute world height, not the ground).
- 0x19 shoot (archer, scout): with a target, on event bit 0: clear variant bit 0x400; aim
  vector = from (own x, y, z + 58) to the target position raised by half the target's
  height (+0x20 x 0.5), normalised, x 400; plus a random offset: a point in the unit sphere
  by rejection sampling (three own-generator draws per attempt) x 40; one more own draw for
  the sound; then `pool_new(0x1c8)` + `MissileWeapon_ctor` (0x150ee4) with type 0, the arrow
  model pair at 0x3e9ce8/0x3e9cec, start position, that velocity, angle = atan2 of the
  velocity - 0x4000, owner = this, and on the stack (0x2bd6a4–0x2bd714): missile +0xd4 =
  creature +0xd0, missile +0xd8 = creature +0xd2 / 2 (signed halving), missile +0xe4 =
  creature +0xd4 (the attack rating a missile passes to `damage_apply`), missile +0xe8 = 4,
  no descriptor, no launch sound. Inferred: +0xd4/+0xd8 are the missile's damage min/max, so
  an arrow does (min .. max/2). On event bit 1 variant bit 0x400 is set again. Every frame
  turns toward the target (slot 26). Animation over -> 3.
- 4, 7–0xf, 0x11, 0x15, 0x16: return without doing anything (no transition out).

Ledge test 0x2bea48 (archers): four `terrain_heightBelow(10, world, p)` probes 30 units
from the archer — p1 = pos + 30 x dir(0), p2 = pos + 30 x dir(0x4000), p3 = p2 + 30 x
dir(0x7fff), p4 = p3 + 30 x dir(-0x4000) (the last two are cumulative, as written) — true as
soon as one probe's ground is more than 100 below the archer's z. Used by state 0 and by
setState(0).

setState (0x2bdb24), non-routine parts:
- cflag 0x200 set when the new state is 0x17, cleared for every other state (before the
  switch, so also for requests that the switch then leaves unchanged).
- 0: +0xf4 = clock + rand%120 + 120 (own generator); an archer at a ledge instead gets clock +
  rand%60 (a second own draw). 1: clear path, `Creature_pickWanderDest`, speed 100 (scout
  150), +0xf4 = clock + rand%120 + 300 (own). 3: speed 150, archer 100. 0x10: speed 150.
- 0x12 (hit reaction): refused while stunned (stays 0x13) and while a melee swing is still
  playing (state 6 with animation flag 8); otherwise only the spear plays a hit animation
  (def+0xe4, mode 0x10) and enters 0x12 — soldier, archer and scout keep their current
  state, i.e. they never flinch.
- 0x14: unlinks a living partner; if object flag 2 is clear, 0x2be3fc(this, 1) sets the
  variant's weapon bit in +0xe8 (0x800 soldier, 0x1000 archer and scout, 0x2000 spear)
  and creates **two PhProp objects** (size 0x248, `PhProp_ctor2` 0x1556c0) at the body
  position from the class definition and the live animation state, each with its own 64-bit
  part mask and object flags 0x4001 (the dropped weapon pieces); death animation def+0x134;
  `Creature_dropLoot` **only when the charm timer +0x312 is 0** (so the permanently charmed
  friendly elves drop nothing); slot 28 onDeath(0).
- 0x17: animation def+0xec, +0xf4 = clock + 60. 0x18 has an animation only for the archer,
  0x19 for archer and scout (both def+0xc4).

Trigger (slot 3, 0x2bd968): if the object has a `dialogScript` property -> `Creature_trigger`
(the base behaviour). Otherwise it **fires one arrow straight ahead**: clears variant
bit 0x400 (it is not set again here), one own-generator draw for the sound, and a
`MissileWeapon` exactly as in state 0x19 but with velocity 400 x (cos, sin)(facing), z
velocity 0, start z + 58, angle facing - 0x4000 (0x2bda6c–0x2bdaec). The function itself
makes no variant, state, death or hidden test. Reached from script `trigger(name,
arg)` (0x142264, calls slot 3 on up to 99 objects of that name).

Phases: none. No hit-point test.

Script-driven: `trigger` as above. In `scripts/FAY1.txt` / `FAY2.txt` objects named
`elf…` are driven with `charmMonster`, `setCreatureParams`, `setMonsterVal`, `hideMonster`,
`followPath`, `setWeaponType` (generic creature built-ins; whether those objects are of this
class was not checked — the level object lists were not read).

Per-machine:
- (a) None found (the scan on run, setState, takeDamage, trigger and their direct callees; all
  four read by hand). All random draws are own-generator draws made in run/setState/trigger
  code. The terrain probes read the world, not the camera.
- (b) No. `WoodElfSoldier_draw` = `Creature_draw` + 0x2bf024, which only reads +0x3d4…+0x3e4.
- (c) No. 0x2bf024 builds a matrix and calls `model_draw` for the cosmetic arrow when
  +0x3e4 is set; no creation, no generator, no script, no world query.

Open:
- Whether anything outside the class ever requests state 0x17 (not searched).
- cflag bit 35 (0x800000000) meaning. Meaning of the seven class-definition entries.
- `PhProp_ctor2` and `MissileWeapon` bodies were not read (the arrow's hit behaviour is the
  generic missile's).

### Wraith family (Wraith, WarWraith)

Shared behaviour, Observed in both classes unless a class is named:

- **Fade byte +0x3c8** (signed, 0–100; constructor sets 100). The draw function hands it to
  the model code (0x1797b8 stores it in the draw parameter 0x41c149) and calls
  `Creature_draw` only while it is below 98, so 100 = not drawn, 0 = fully drawn (Inferred
  sense: the value is "how faded"). The run function changes it by state: states 0 and 1 add
  1 per frame up to 100; state 3 (chase) moves it 1 per frame toward 60; states 6 and 7
  (attacks; Wraith also 0x17) subtract 2 per frame while it is above 0; state 0x11 moves it
  by 2 toward 70; state 0x14 (dead) adds 1 per frame and at 100 the object deletes itself.
- Every frame, before the state switch (Wraith 0x2bf5ec–0x2bf67c, WarWraith from 0x2c0d08):
  fade >= 21 sets creature flags 0x54 (the "immune" marks for damage classes 4, 8 and 1 in
  `damage_apply`), fade < 21 clears them; fade >= 99 sets object flag 1 (not solid) and
  faces the target (Wraith: facing snapped to atan2 toward the target; WarWraith:
  `Creature_turnToTarget`); fade < 99 clears object flag 1 unless dead. Per
  docs/gameplay.md the 0x54 bits only choose the colour of the damage number unless cflag
  0x100000 is also set; neither constructor sets 0x100000 (Wraith cflags |= 0x20400200000,
  WarWraith |= 0x20400210000). Whether the fade protects the wraith in some other way was not
  traced.
- **Movement ignores collision and terrain.** In state 3, when the target is not within 20
  units, the run function turns toward the target and then writes the position directly:
  x, y += (cos, sin)(facing) x speed / 60 with speed = +0xb8 (140), multiplied by
  `SpellDrowsy_getStat3Fraction` of an attached `SpellDrowsy` when timer +0x31a > 0; z moves
  1/6 per frame toward the target's z; then `obj_updateGridCell`. No `Creature_moveBy` /
  path call (Wraith 0x2bf93c–0x2bfa48, WarWraith 0x2c0f1c–0x2c1028). The same z-follow runs in
  both attack states. `Creature_applyKnockback(0, this)` each frame.
- State machine: 0 idle (fade out; sees target (slot 25) -> 3; clock > +0xf4 -> 1; the Wraith
  also goes to 1 when away from home); 1 `Creature_moveToDest`, sees target -> 0; 3 chase: no
  target -> 0; target within 20, arc 6000 -> **7 if clock > +0x3cc, else 6**; within 20 at any
  angle -> turn only; else fly as above; 5: same attack choice, else -> 3 when not rooted;
  0x10 flee until the attack cooldown ends -> 0; 0x11 wait until clock > +0xf4 -> 3 (nothing
  in either class requests 0x11); 0x12 until animation flag 0x10 clears -> 3; 0x13 until not
  stunned -> 0. pickTarget (slot 23) is skipped once dead.
- 6 plain attack: on event bit 0 `Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4,
  flags 8, descriptor)`; descriptor 0 for the Wraith, for the WarWraith the result of the
  weapon holder's table offset 0x8c with argument 1 (hand 1's descriptor, 0 without a
  holder). Animation over -> 3.
- 7 **draining attack**: on event bit 0 builds an empty descriptor on the stack, asks
  SKILL[14 ColdWeapons] through skill-table offset **0x5c** with (0, (int) monster level
  0x4f714c, 0) and writes one rider: type 0x16 (cold), v1 = v2 = that value; then
  `Creature_hitTargetAtReach(36, ..., flags 0x404, descriptor)`. **If the hit landed (non-zero
  result) the wraith heals itself by max hp / 15** (+0x228 += +0x22c x 0.0667, capped at
  max). Animation over -> 3. setState(7) sets +0x3cc = clock + rand%120 + 300 (own
  generator), so the drain is offered again 300–419 clock frames later; +0x3cc starts at 0
  (zero-filled block, never initialised), so the first attack of every wraith is the drain.
- Death: setState(0x14) calls **`loot_generateDrops` (0x100d54) directly** with (36, 2, 2.8,
  0, 3, 0.25, position, facing, 0, 0) — not `Creature_dropLoot` — clears the target, sets
  object flag 0x4000 and calls slot 28. Inferred from the symbol note of `Creature_dropLoot`:
  the `noloot` / revived tests it makes are bypassed for wraiths. The run function never
  calls `Creature_deadUpdate`; the corpse fades and `obj_delete`s itself (within 100 frames).
- setState(0): clears the target handle, +0xf4 = clock + rand%120 (own). setState(0x11):
  +0xf4 = clock + rand%60 + 120 (own). setState(0x12) is refused while stunned and while an
  attack animation (state 6 or 7, flag 8) is still playing.
- **One wraith per victim — slot 20 (isEnemy) override with a side effect** (Wraith
  0x2c061c, WarWraith 0x2c1bc0; identical code on different lists). Each class keeps a static
  list of every instance constructed since level load: Wraith 0x5033f8 (count 0x5034e8),
  WarWraith 0x503590 (count 0x503680), 60 handles each; both counts are zeroed by
  `objects_levelReset` (0x15da80). isEnemy(other), for other != 0, walks the list in order:
  an entry equal to `this` sets "seen myself"; any other live entry W whose target is
  `other` is compared by 2-D distance to `other`: if dW <= 3 x dThis and (dW <= dThis or
  myself not yet seen) the answer is 0 (not my enemy — someone of my class already has it);
  otherwise **W's target handle is cleared** and the walk goes on. After the walk the base
  `Creature_isEnemy` decides. So a query can take a target away from another wraith that is
  more than 3 times farther (or simply farther and later in the list).
- **No bound check on the list** (Wraith ctor 0x2bf474–0x2bf4a8, WarWraith ctor 0x2c0b18–0x2c0b40): the
  constructor links itself at index `count` and increments the count, and the count is
  stored immediately after the 60th slot (0x5033f8 + 60 x 4 = 0x5034e8; 0x503590 + 60 x 4 =
  0x503680). Deleted wraiths leave empty slots but the count never goes down within a level.
  Inferred: the 61st Wraith (or WarWraith) constructed in one level writes its handle over
  the counter, the counter then becomes that pointer + 1, and the next isEnemy walk runs far
  past the array. Whether any level can construct 61 was not checked. The clone functions do
  not register (xref of the two arrays: constructors, slot 20 and the static initialiser
  0x2c1d4c only).
- Both constructors make the max-hp draw `GameObject_rand(this) % 14 + 4` before
  `Creature_ctor` (Wraith draw 0x2bf304, base ctor 0x2bf340; WarWraith 0x2c07f0 / 0x2c0828), i.e. on the zero-filled
  block: Inferred constant 4.0, as for WoodElfSoldier.
- Common constructor values: radius 18, speed 140, turn rate 1.2, draw half-width 20,
  HomeRange +0x3c0 = 600, kind byte +0xb4 = 0x10, +0x64 = 1.0, +0x68 = 1.0, +0x6c = 0.3
  (poison / disease / lightning resistance per docs/gameplay.md), fade 100, state 0, 60-list.

Per-machine (both classes):
- (a) None found (the scan on run, setState, slot 20; all read by hand). All draws are
  own-generator draws in run/setState. The slot-20 side effect matters only if slot 20 is
  ever called on a wraith from per-machine code: a scan for the slot-20 call pattern (add
  0xa0 to the table pointer, then load +0/+4) finds 68 calling functions, all run / touch /
  cast / projectile functions by name and none a draw function; in `Player_run` and
  `Player_castSkill` the receiver is the player, not the monster. The individual call
  sites in spells and projectiles were not read; by shape the receiver there is the caster
  or owner, which is a wraith only for the wraith's own hits.
- (b) No. The draw functions only read +0x3c8 and write the global draw parameter, which
  `model_resetDrawState` restores.
- (c) No.

#### Wraith  (factory name `Wraith`; vtable 0x50f6d8; size 0x3d8)

Functions: ctor 0x2bf2ac, draw 0x2bf4e4, run 0x2bf538 (3384 bytes; the "helper at 0x2bfe2c"
is the state-0x17 code inside it, not a separate function), setState 0x2c0270, isEnemy
(slot 20) 0x2c061c, clone 0x129b18, destructor 0x3c4b08.

Constructor: class definition 0x503398; common values above; +0x3d0 = 0; idle animation
def+0x4c pushed; two `creature_setDefEntryParams` (entries 3, 5); registers in the list;
`lump_load` of `skelnorm.lmp` and `skelcom.lmp` (the skeleton it summons); `Creature_init`.
No properties read here.

Fields: +0x3c8 s8 fade; +0x3cc s32 clock value after which the next attack is the drain;
+0x3d0 handle of the summoned skeleton.

States beyond the family list:
- 3: when the target is farther than 20 and **the skeleton handle +0x3d0 is empty**, probes
  `terrain_height(15, world, own position + 30 x facing direction)`; if that ground is
  within 6.0 of the wraith's own z -> state 0x17. So a Wraith with a target re-summons as
  soon as its previous skeleton object has been deleted; there is no cooldown.
- 0x17 **summon**: on event bit 0: point 30 ahead, z = terrain height there + 1;
  `pool_new(0x478)` + `Skeleton_ctor` (0x2a5af4) with (position, the wraith's facing, 0, type
  name `Skeleton`, 0); on the new skeleton: cflag 0x1000000 (corpse sinks and is deleted),
  the two flash-colour quads set (+0x90..+0x96 = 0, 0x80, 0xff, 0x32; +0x98..+0x9e = 0,
  0x80, 0xff, 0x96); `handle_link(wraith+0x3d0, skeleton)`; a sound from `fx.lmp` on the
  skeleton. Animation over -> 3. The skeleton is not put in state 0x17 by this code (compare
  `ScriptGenerator_spawn`); what state it starts in is the Skeleton constructor's business
  (not read). No `Weapon1` is created by any Wraith function (calls checked in
  0x2bf538–0x2c07a8); the first-pass "Creates: Weapon1" on the Wraith row belongs to
  WarWraith, whose constructor builds an embedded `Weapon1` in place.
- 0x14: besides the fade, three times per frame: one own draw picks a model sample point
  (`model_getSamplePoint`), then a loop driven by the sample's size value spawns particles
  (definition 0x8e4b00), each costing 3 own draws for a jitter and 3 per attempt of a
  unit-sphere rejection loop. All in run code.
- setState(3 / 0x10): speed 140; the move animation is not restarted when coming from 3, 6
  or 7.

Open: Skeleton constructor's start state; whether summoned skeletons count toward anything.

#### WarWraith  (factory name `WarWraith`; vtable 0x517f80; size 0x468)

Functions: ctor 0x2c07a8, draw 0x2c0b70, run 0x2c0c2c, setState 0x2c1648, isEnemy (slot 20)
0x2c1bc0, destructor 0x3ccc48.

Constructor: class definition 0x5034f0; an embedded `Weapon1` holder is built in place at
+0x3d0 (table 0x50cf40, with its descriptor area initialised empty) and +0x50 points at it;
one own-generator draw (after `Creature_ctor`, so a real one) picks the weapon:
holder slot 1 (hand 1 on, type (rand % 3) x 2 + 13, i.e. 13, 15 or 17); idle animation
def+0x5c for types 13 and 15, def+0x64 for 17 (type read back through holder table offset
0x7c); four `creature_setDefEntryParams` (entries 3, 4, 5, 7); registers in its list;
`Creature_init`. No properties read here.

Differences from the Wraith: weapon-holder update (table offset 0xac, 0.5) each frame; no
summon and no state 0x17; state 0 has no leash test; the plain attack carries the weapon's
descriptor; setState picks animations by weapon type (6: def+0x1c for types 13 / 15, else
one own draw chooses def+0x24 or def+0x2c); setState(0x14) first calls holder table offset
0x5c (hand 1, this, 0, 0) — the "drop the held part as a PhProp" slot — then the loot call.
State 0x14 in run: fade + 1, one own draw for an angle and a unit-sphere rejection loop (3
own draws per attempt) for one particle per frame (definition 0x8e4ab0, lazily constructed
on first use behind the flag 0x503684 — in run code).

Fields: +0x3c8 s8 fade; +0x3cc s32 drain clock; +0x3d0… embedded Weapon1.

#### Vampire  (factory name `Vampire`; vtable 0x50f968; size 0x3c8 — no class fields)

Functions: ctor 0x2b69d0, draw 0x2b6bd4 (`Creature_draw` only), run 0x2b6bfc, setState
0x2b7208, clone 0x128978, destructor 0x3c4990. takeDamage is the base one.

Constructor: `Creature_ctor` max-hp argument 10.0, class definition 0x502df8; turn rate 0.7,
radius 18, **speed +0xb8 = 0** (the class never sets it again: all movement comes from the
animations, which are started with flag 0x800 — Inferred root-motion tracks, compare
docs/engine.md P3); +0x5c = -0.2, +0x64 = 1.0, +0x68 = 1.0, +0x6c = 0.3 (fire / poison /
disease / lightning resistance per docs/gameplay.md; the negative fire value is as
written); kind +0xb4 = 0x10; cflags |= 0x400000000; idle track def+0x7c pushed and
`anim_randomizeTopTime` applied to it (cosmetic seed, see Per-machine); 60-list; three
`creature_setDefEntryParams` (entries 3, 4, 5); **one own-generator draw sets one of
variant bits 0–7 of +0xe8** (`1 << (rand & 7)`, a random look), `model_buildHideMask`;
`Creature_init`. No properties read here.

Fields: only base fields. +0xf4 is used three ways: clock deadline (states 0, 0x18), frame
countdown after an attack (6, 7: set to 20), clock at death (0x14).

States (run 0x2b6bfc; `Creature_stepAnim(1.0)`, `Creature_applyKnockback(0.5)`, pickTarget):
- 0 idle: sees target -> 3; away from home, or clock > +0xf4 -> 1.
- 1 and 0x17: sees target -> 3; else `Creature_moveToDest`. (0x17 is entered only from
  outside the class; its setState clears the path and starts the move animation.)
- 3 chase: no target -> 0. Target within 20, arc 5000 -> 6 (bite). Within 20 at any angle
  (this test is made with facing argument 0 and arc 0x7fff) -> turn toward it. Target within
  84, arc 3000 -> **one own-generator draw: (rand & 3) == 0 -> 0x19 (side leap), else 7
  (lunge)**. Otherwise `creature_allyInLineOfFire(radius x 6, radius x 3, this, target, 0)`:
  non-zero -> 0x18 (hold), zero -> `Creature_moveToTarget`.
- 5: target within 20, arc 5000 -> 6; else when not rooted -> 3.
- 6 bite: `Creature_settle` each frame; on event bit 0 `Creature_hitTargetInArc(0, 20, this,
  facing, 5000, +0xd0, +0xd2, +0xd4, flags 8, 0)`; turns toward the target while the
  animation plays; when it ends -> **0x19** (always leaps away after a bite).
- 7 lunge: `Creature_settle`; on event bit 0 `Creature_hitTargetInArc(0, 24, …, 5000, …,
  flags 8, 0)`; turns while the animation plays; after it ends +0xf4 (20) counts down one
  per frame and at 0 -> 3.
- 0x10: flee until the attack cooldown ends -> 0.
- 0x12 hit reaction: zero-velocity `Creature_moveBy`; animation flag 0x10 clear -> 3.
- 0x13: never the stored state — setState turns a request for 0x13 into 0x12 (below).
- 0x14 dead: zero-velocity `Creature_moveBy`; `Creature_deadUpdate(20, this, events, zero
  vector, 1)`; for the first 60 clock frames after death (+0xf4 holds the clock at death)
  calls the camera-gated, cosmetic-seed particle helper 0x1f5210 on the model; after that
  sets object flag 2 and cflag 0x20000000000 every frame (the body is no longer drawn by the
  grid walk — it "turns to dust").
- 0x18 hold (an ally is in the way): no target -> 0; clock > +0xf4, or
  `creature_allyInLineOfFire(…, 1)` now clear -> setState(3); turns toward the target.
- 0x19 leap: `Creature_settle`; animation over -> 3.
- 2, 4, 8–0xf, 0x11, 0x15, 0x16: return.

setState (0x2b7208), non-routine parts:
- 0: +0xf4 = clock + rand%90 + 90 (own). 6 and 7: +0xf4 = 20; 7 picks one of two attack
  animations (def+0x1c / def+0x24) with an own draw.
- **0x13 is rewritten to 0x12**: a stunned vampire plays hit reactions instead of a stun
  state (the filter keeps redirecting to 0x13 while the stun timer runs, so the reaction
  repeats). 0x12: in state 7 with the swing still playing nothing happens (state stays 7);
  in state 6 with the swing still playing the reaction animation is blended in but the
  state stays 6; otherwise state 0x12. One own draw picks the reaction animation (def+0x6c /
  def+0x74) whenever one is started.
- 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6, 1.4, 0.25, this, position, facing,
  "vampirefang")` (the last argument is the reagent filter); one own draw (% 3) picks the
  death animation; +0xf4 = clock; object flag 0x4000; slot 28.
- 0x18: +0xf4 = clock + rand%240 + 240 (own).
- 0x19: one own draw picks the turning sense for `creature_findClearHeading(3.0, this,
  position, facing, sense)`; the leap animation is chosen from the returned heading
  relative to the facing d (signed 16-bit): -0x5fff..-0x2001 -> def+0x5c, 0x2000..0x5fff ->
  def+0x54, anything else -> def+0x64.

Phases: none. No skill is used and nothing heals the vampire (no drain in this class).

Per-machine:
- (a) Two cosmetic-seed users reachable from simulation code, neither decides anything in
  the code read: (1) the constructor's `anim_randomizeTopTime` on the idle track def+0x7c
  (already listed as P4 in docs/engine.md). The run function acts on animation event bits
  only in states 6, 7 and 0x14, each of which starts its own tracks; state 0 ignores the
  event mask. Not determined: whether the fading idle track can still contribute event
  bits or root motion during the first blend (0.1 s) out of it. (2) state 0x14 calls
  0x1f5210 (reads the camera, draws the cosmetic seed, spawns particles; writes nothing to
  the object in the part read). the scan: no other hits.
- (b) No (draw is `Creature_draw` only). (c) No.

Open: animation data (which tracks carry event markers / root motion).

#### UndeadKnight  (factory name `UndeadKnight`; vtable 0x517918; size 0x478)

Functions: ctor 0x2b3e30, draw 0x2b421c, run 0x2b4370, trigger (slot 3) 0x2b4cc0 (empty:
returns at once, so script `trigger` and the base dialog behaviour do nothing for this
class), takeDamage 0x2b4cc8 (plain tail call of `Creature_takeDamage`), setState 0x2b4ce4,
**0x2b5370 "set mount"** (below), static initialiser 0x2b53cc + stub 0x2b5518 (three particle
definitions 0x8e4970, 0x8e49c0, 0x8e4a10; only 0x8e4970 has another reference, in run state
0x17), clone 0x1282d8, destructor 0x3cc8c4.
Not this class: 0x2b3afc (788 bytes) + stub 0x2b3e10 are the static initialiser of the
seven particle definitions 0x8e4740–0x8e4920, whose other references are all in the light
classes just before (Torch_run 0x2b2088, Candle_run 0x2b2dc4, Candle2_run 0x2b3164, Lamp_run
0x2b3858; 0x8e4790 has no user). It only sits in this address range.

Constructor (0x2b3e30) takes two extra arguments (variant bit index, class-definition
index). The only caller is the factory at 0x15b94c and it passes 0, 0. So: class
definition 0x502ab8 (+ index x 0x138), +0x470 = 0 ("has variant"), +0x474 = 0, and the
branch that would set the variant bit `1 << index` in +0xe8 is not taken. `Creature_ctor`
max-hp argument 10.0. An embedded weapon holder is built in place at +0x3d0 with the
**WeaponShield** table 0x50cda0 and +0x50 points at it; holder slot 1 is called twice: hand
1 on with type 0x16, hand 2 on with type 0x18. Radius 20, turn rate 1.2, **speed 0** (all
movement is animation root motion; the move animation is started with flag 0x800), draw
half-width 20, kind +0xb4 = 0x10, activity radius +0x3c4 = 1200, scale +0xdc = 1.3, +0x5c =
-0.2, +0x64 = 1.0, +0x68 = 1.0, +0x6c = 0.3, cflags |= 0x2020020000 (0x20000 body material,
0x20000000 no ice shatter / gibs, bit 37 not traced), +0x3c8 and +0x3cc cleared, idle track
def+0x54, 60-list, six `creature_setDefEntryParams` (entries 3, 4, 5, 6, 0xe, 8),
`Creature_init`. No properties read here.

Fields:

| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | handle | mount. Linked only by 0x2b5370, which has no caller | draw, run head, setState 0x12 / 0x13 |
| +0x3cc | handle | a second linked object (revealed in 0x17, killed on death). Never linked: the class only clears and reads it (field search 0x2b3e30–0x2b5370, full listing) | run 0x14 / 0x17, setState 0x14 |
| +0x3d0… | WeaponShield | embedded weapon holder | +0x50 |
| +0x470 | s32 | 1 when the ctor's definition index was non-zero; write-only | ctor |
| +0x474 | s8 | the ctor's variant index; write-only | ctor |
| +0xf4 | s32 | three uses: idle deadline (clock), post-swing countdown (rand % 20), and compared against the GLOBAL frame counter in state 3 | below |

0x2b5370 (this, object): clears and links the mount handle +0x3c8 and sets object flag 1
(not solid). No call and no pointer reference to it exists (xref, plus a scan of the whole
file for j/jal to it and for a data word holding its address: none). This settles the
first-pass question: the mounted paths (the draw function's position overwrite, the
`obj_updateGridCell` at the top of run, the "no hit reaction / no stun animation while
mounted" tests in setState) are unreachable in the shipped game unless something outside
the monsters area links +0x3c8 by offset (not searched).

States (run 0x2b4370). Order each frame: `Creature_processDamage`, `Creature_run` (non-zero
returns), weapon-holder update (table offset 0xac, 0.5), `Creature_updateActive` — **result
ignored, the state machine also runs while "inactive"** — `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.5)`, pickTarget, and (not mounted) a zero-velocity
`Creature_moveBy` every frame, then the switch:
- 0 idle: sees target -> 3; clock > +0xf4 -> 1. No leash test.
- 1: sees target -> 0; else `Creature_moveToDest`.
- 3 chase: no target -> 0. Tests in this order (facing = own facing):
  1. target within 60, arc 0x5b04: own draw % 100 < 65 -> **10**, else -> **9**;
  2. within 80, arc 11000: own draw % 100 < 65 -> **9**, else -> **7**;
  3. within 80, arc 6000: own draw % 100 < 65 -> **8**, else -> 7. Inferred unreachable: a
     target inside the 6000 arc at 80 already passed test 2, so state 8 is never chosen;
  4. within 120, arc 3000, and `g_simFrame >= +0xf4` -> **0xb**. The comparison is with the
     global simulation frame 0x44fdcc (0x2b4680–0x2b4690), while +0xf4 holds either
     creature-clock + rand%120 (from state 0) or a spent 0..19 countdown — as written;
  otherwise `Creature_moveToTarget`.
- 5: target within 40, arc 6000 -> 6; else when not rooted -> 3.
- 6 (and 2, 4, 0xc–0xf, 0x15, 0x16, any unknown number): run calls setState(3). setState's
  default case itself calls setState(3) and then stores the requested number, so these
  states last one frame and only serve as a hop into the chase.
- 7, 9, 10, 0xb swings (four animations: def+0x24, def+0x1c, def+0x2c, def+0x34 over base
  def+0x3c): with a target, **on any of event bits 0–2** `Creature_hitTargetAtReach(36,
  this, +0xd0, +0xd2, +0xd4, flags 0x40008, 0)` — a swing can hit on up to three marked
  frames — and turn toward the target. After the animation ends +0xf4 counts down one per
  frame; at <= 0 -> 3. setState sets +0xf4 = rand % 20 (own) for these four.
- 8: same hit test with animation def+0x74; animation over -> 3 (no countdown).
- 0x10: flee until the attack cooldown ends -> 0.
- 0x11: (setState sets cflag 0x200 "blocking", animation def+0x3c) after the animation ends
  count +0xf4 down -> 3. 0x18: animation def+0x64, same countdown -> 3. setState does not
  load +0xf4 for either. Neither state, nor 0x17, is requested anywhere in this class.
- 0x12: until animation flag 0x10 clears -> 3. 0x13: until not stunned -> 0.
- 0x14 dead: `Creature_deadUpdate(20, this, events, zero vector, 0)`; if +0x3cc is linked,
  clears object flag 2 on that object every frame (dead path).
- 0x17: every frame sets the second flash-colour quad (+0x98, +0x9a, +0x9c = -150, +0x9e =
  0). If +0x3cc is linked (dead path): 75 particles per frame (definition 0x8e4970) from a
  random sample point of its own model to a random sample point of the linked object's
  model, two own-generator draws each; on event bit 0 clears object flag 2 on the linked
  object (reveals it). Animation over -> 3. setState(0x17) computes a point (120 ahead with
  no target; 36 behind the target otherwise) that nothing uses, and starts def+0x44.

setState (0x2b4ce4), non-routine parts: clears cflag 0x200 on every call (0x11 sets it
again). 0: +0xf4 = clock + rand%120 (own). 0x12: refused in state 6 with a playing
animation, in state 0x13, and when mounted. 0x14: `Creature_dropLoot(36, 2, 1.8, 0.6, 2,
0.25, this, position, facing, 0)`; weapon-holder table offset 0x5c for hand 1 and hand 2
(drops both held parts as props); death animation def+0x7c; if +0x3cc is linked (dead
path) `damage_apply(5000, 5000, linked object, this, attack 10000, flags 0x40)`; slot 28.

Phases: none. No skill, no object creation in reachable code.

Per-machine:
- (a) None found (the scan on run, setState, takeDamage, ctor; read by hand). The state-3 test
  reads the simulation frame counter, which is shared. All draws are own-generator.
- (b) Reachable path: no stores (`Creature_draw`, slot 16, holder draw at table offset
  0x94). The mounted path stores position and facing without restoring (docs/monsters.md
  7.8); with 0x2b5370 uncalled it stays unreachable.
- (c) No.

Open: whether anything outside this class requests states 0x11, 0x17 or 0x18 (scripts can
only request 0 and 0x14 per docs/script.md); the meaning of weapon types 0x16 / 0x18.

#### Warrior  (factory names `Samurai` (exact), `Gladiator*` (prefix); vtable 0x517e38; size 0x480)

Functions: ctor 0x2bafb4, draw 0x2bb5a4, run 0x2bb640, setState 0x2bc320, helper 0x2bc7c8
("can block", only caller 0x2bb9f4 in run), destructor 0x3ccb98. takeDamage is the base one.

Weapon-holder calls used below were checked in the WeaponShield bodies: table offset 0x0c
= set the item type of a hand (non-zero switches the hand on; 0x11bc18), 0x74 = "is hand n
on" (0x11bde0), 0x7c = item type of hand n (0x3c2590), 0x8c = pointer to hand 1's damage
descriptor at holder+0x50, 0 for hand 2 (0x11be20), 0x5c = drop the held part as a prop.

Constructor (0x2bafb4) has a sixth argument, the kind: the factory passes 0 for `Samurai`
(0x15ba1c) and 1 for `Gladiator*` (0x15ba64). Class definition 0x503030 + kind x 0xf8;
`Creature_ctor` max-hp argument 10.0; embedded WeaponShield holder at +0x3d0 (table
0x50cda0), +0x50 points at it; kind byte +0xb4 = 9; +0x3c8 = kind; turn rate 1.2, radius
18, **speed 0** (root-motion movement); cflags |= 0x40000 (ordinary blood); +0x470, +0x474
cleared. All randomisation is own-generator, after the base constructor:
- Samurai (0): hand 1 type 0x16 + 2 x (rand % 3) (0x16, 0x18 or 0x1a); variant bit
  `1 << (rand % 13)`; cflags |= 0x400000000.
- Gladiator (1): hand 1 type 0x16 + 2 x (rand & 1). Then by type-name prefix:
  `gladiatorroman`: variant bit `1 << (rand % 7 + 5)`, with 0x400 replaced by 0x1000; a
  second draw: odd -> hand 2 on with type 0x1c; cflags |= 0x800000000.
  `gladiatorbare`: variant bit `1 << (rand % 6)`, with 0x20 replaced by 0x400; odd second
  draw -> hand 2 type 0x1a; cflags |= 0x200000000.
  any other `Gladiator…`: variant bit `1 << (rand % 13)`; second draw even -> a third draw
  picks hand 2 type 0x1a or 0x1c; cflags |= 0x400000000.
- then `model_buildHideMask`, setState(0), 60-list, eight `creature_setDefEntryParams`
  (entries 3, 4, 5, 6, 9, 10, 0xb, 0xc), `Creature_init`. No properties read here.

Fields:

| offset | type | meaning | where read |
|---|---|---|---|
| +0x3c8 | s8 | kind: 0 Samurai, 1 Gladiator | 0x2bc7c8, run 0x14, setState 0x14 |
| +0x3d0… | WeaponShield | embedded holder | +0x50 |
| +0x470 | s32 | last opening swing started, 6 or 8 | run state 7 |
| +0x474 | s8 | swings started since the last chase (combo count); +1 in setState 6 / 7 / 8, 0 in setState(3) | run 6, 8 and the tint code |
| +0x478 | s32 | 1 once the target was found blocking in state 5; 0 in setState(3) | run 6, 8, tint |
| +0xa0 | u8 | tint preset, rewritten every frame by run (below) | base draw |

0x2bc7c8 "can block": Samurai -> 1; Gladiator -> whether hand 2 is on (holder table offset
0x74 with 2), i.e. only gladiators that rolled an off-hand item; other kinds 0.

Each frame (run 0x2bb640): `Creature_processDamage`, `Creature_run`, `Creature_updateActive`
(inactive returns), holder update (0.5), `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.4)`, pickTarget, then the **tint**: in states 6–0xf, if +0x478 is
0 the tint preset is 0; otherwise combo count 2 -> preset 9, 3 -> 10, 4 or more -> 11
(count 0–1 leaves it alone); in every other state preset 0.

States:
- 0 idle: sees target, or is away from home -> 1.
- 1: no visible target -> `Creature_moveToDest`. Otherwise turn toward the target and, once
  it is within the creature's `visualrange` (+0x3ae) in arc 8000 -> 3.
- 3 chase: no target -> 0. Target within 12, arc 8000 -> 5. If the target is not "charging"
  (`Creature_isTargetCharging`: faces me and moves faster than 100/s) and is within 36, arc
  8000 -> 5; not charging and within 36 at any angle -> turn only. Target within 120, arc
  8000 **and at least one ally already near the target** (`Creature_countAlliesNearTarget(36)`
  >= 1) -> pickTarget(1) (forced re-pick) and -> 5: it stands off instead of crowding in.
  Otherwise `Creature_moveToTarget`.
- 5 stance. Target within 36, arc 8000:
  - if the target is attacking me (`Creature_isTargetAttackingMe`), an own draw % 3 == 0 and
    "can block" -> **0x17 (block)**;
  - otherwise: `Creature_isBlockedByTarget` true -> +0x478 = 1; one own draw: even -> **8**,
    odd -> **6**.
  Target within 36 but outside the arc -> turn. Target farther and not rooted: each frame
  one own draw % 60; on 0: if the target is within 156, arc 8000 and an ally is near it,
  keep waiting, else -> 3. (So a waiting warrior re-engages on average once a second, and
  only when no ally is on the target.)
  After any of these, if clock > +0xf4 a flourish animation is started (def+0x8c, or
  def+0x6c chained into def+0xac when the stance track def+0x84 is present) and +0xf4 =
  clock + rand % 600 (own). This check also runs in the frame an attack was just started.
- 6 and 8 opening swings (def+0x1c / def+0x2c): zero-velocity `Creature_moveBy`, turn; on
  event bit 0 `Creature_hitTargetInArc(0, 36, this, facing, 8000, +0xd0, +0xd2, +0xd4,
  flags, hand-1 descriptor)`. Flags: 8; **0x440008 when this is the 3rd swing of the chain
  (count == 3) and no ally is near the target; 0x100008 when it is the 5th and no ally is
  near**. On event bit 1 (chain window), while count < 5 and the target is still within 36,
  arc 8000: if count == 1, chain to 7 when the target was blocking, else on an own-draw
  coin flip; if count > 1, chain to 7 only when the target was blocking. Animation over -> 3.
- 7 follow-up (def+0x24): same movement; on bit 0 the same arc hit with flags 8 and the
  descriptor; on bit 1 with the target within 36, arc 8000 chains to the opening swing it
  did not use last (+0x470 == 6 -> 8, else 6). Animation over -> 3.
  Net effect: 6/8 -> 7 -> 8/6 -> 7 -> 6/8, at most five swings; beyond the second swing the
  chain continues only against a target that was blocking when the exchange began, and the
  tint steps up with it.
- 9 (def+0x34): arc hit on bit 0 with flags 8; 10 (def+0x9c): no hit. Both end in 3. Neither
  is requested anywhere in this class.
- 0x10: flee until the attack cooldown ends -> 0 (setState(0x10) itself loads +0x318 = 60).
- 0x12: until animation flag 0x10 clears -> 3. 0x13: until not stunned -> 3.
- 0x14 dead: zero-velocity `Creature_moveBy`, `Creature_deadUpdate(20, this, events, zero,
  0)`; a Samurai whose death animation is def+0x64 has that track snapped to its end
  (`anim_snapTopToEnd`) in the frame the corpse becomes active again (cflag bits 63:62 ==
  "active now, not last frame").
- 0x17 block: cflag 0x200 while in this state; ends when clock > +0xf4 -> 3.
- 2, 4, 0xb–0xf, 0x11, 0x15, 0x16 and unknown numbers: run requests 0; setState stores 0
  for any number it has no case for, without touching the animation.

setState (0x2bc320), non-routine parts: cflag 0x200 cleared on every call, set by 0x17.
0: +0xf4 = clock + rand%120. 5: +0xf4 = clock + rand%360. 0x17: +0xf4 = clock + rand%120 +
60 (all own). 0x12 is never refused (a swing can be interrupted); coming from the block
state it plays def+0x44 instead of def+0x74. 0x14: `Creature_dropLoot(36, 2, 1.6, 0.6,
1.4, 0.25, this, position, facing, 0)`; one own draw picks death animation index 9–12
(def+0x4c…def+0x64); both hands' parts are dropped as props **except** for a Samurai that
drew index 12, who keeps them; slot 28.

Phases: none (no hit-point test); the only escalation is the combo count.

Per-machine:
- (a) None found (the scan on run, setState, ctor, 0x2bc7c8; read by hand). The constructor
  stores `g_simFrame + 300` in +0xf4 but setState(0) overwrites it at once. State 0x14's
  snap depends on the active/inactive bits that `Creature_updateActive` maintains (common
  hazard, not repeated); it only changes the corpse's animation time.
- (b) No. (c) No. Draw = `Creature_draw` + slot 16 + holder draw.

Open: meaning of damage flag 0x400000 (not tested in `damage_apply`); item-type numbers
0x16–0x1c; whether anything requests states 9 and 10.

#### Ulthork  (factory prefix `Ulthork*`; vtable 0x517a60; size 0x468)

Functions: ctor 0x2b5538, draw 0x2b594c, run 0x2b5a08, saveState (slot 9) 0x2b6448,
loadState (slot 8) 0x2b64cc, setState 0x2b65c4, destructor 0x3cc988. takeDamage is the base
one. (0x2b5370, 0x2b53cc and 0x2b5518 at the start of this address range belong to
UndeadKnight, see there.)

Constructor: `Creature_ctor` max-hp argument 10.0, class definition 0x502d28; embedded
`Weapon1` holder at +0x3c8 (table 0x50cf40), +0x50 points at it; turn rate 1.2, radius 35,
draw half-width 90, **speed 0** (root-motion movement), +0x60 = 1.0 and +0x5c = -0.3 (cold
and fire resistance per docs/gameplay.md), cflags |= 0x200040000, +0xf4 = 0. One own draw
sets the **scale +0xdc = 0.8 + 0.3 x rand/65536** (each Ulthork has its own size). Then
the variant byte +0x460, then the weapon, `model_buildHideMask`, idle track def+0x74,
60-list, six `creature_setDefEntryParams` (entries 5, 6, 7, 0x12, 8, 9), `Creature_init`.
No properties read here.

**Variant selection is inverted as compiled** (0x2b56c4–0x2b572c; `str_prefixDiffers`
0x159c20 returns 0 on a match — body read — and the factory, the WoodElf and the Warrior
constructors all treat 0 as "matches"):
- type name does NOT start with `ulthorkrecruit` -> variant 0;
- type name starts with `ulthorkrecruit` -> the code compares it with `ulthorksoldier`
  (exact, case-insensitive); it differs, so variant 1;
- variant 2 would need a name that starts with `ulthorkrecruit`, equals `ulthorksoldier`
  and does not start with `ulthorkshaman` — impossible.
So from the constructor: recruits get variant 1, soldiers, shamans and every other
`Ulthork…` name get variant 0, and **variant 2 is never assigned**. The only other writer
of +0x460 is loadState, which restores what was saved. Inferred consequence: everything
keyed on variant 2 — tint preset 6, weapon type 0x17, variant bit 1, and the whole casting
state 7 (ShockOfFrost, FrostStorm, reviving a corpse) — is unreachable in the shipped game
unless a save record or some code outside this class writes 2 (not searched outside the
class; the level files were not available to check which names are used). Variants 0 and 1
differ only in the second model handed to `Creature_draw` (def+0x14 + 8 x variant).
For variants 0 and 1 one own draw picks hand-1 item type 0x13 or 0x15.

Fields: +0x3c8… embedded Weapon1; +0x460 s8 variant (read by run 3 / 5, draw, save/load);
+0xf4 clock deadline (idle, wander, state 7).

States (run 0x2b5a08; holder update 0.5, `Creature_stepAnim(1.0)`,
`Creature_applyKnockback(0.3)`, pickTarget):
- 0 idle: sees target -> 3; away from home, or clock > +0xf4 -> 1.
- 1: sees target -> 3; while clock <= +0xf4 `Creature_moveToDest`, then -> 0.
- 3 chase: no target -> 0. Target within 20, arc 5000 -> 6. Within 20 at any angle (facing
  argument 0, arc 0x7fff) -> turn. Variant 2 only: target within 400, arc 5000, ray mode 1
  -> 7. Otherwise `Creature_moveToTarget`.
- 5: target within 20, arc 5000 -> 6; variant 2: within 400, arc 5000 -> 7; else when not
  rooted -> 3.
- 6 melee (one of three animations def+0x2c / 0x34 / 0x3c by own draw % 3 in setState): on
  event bit 0 `Creature_hitTargetAtReach(36, this, +0xd0, +0xd2, +0xd4, flags, hand-1
  descriptor)`; flags by two own draws: first (rand & 7) == 0 -> 0x80008; otherwise second
  (rand & 3) == 0 -> 0x40008, else 8. On event bit 1 an own draw % 5 == 0 -> setState(3)
  at once (cuts the swing short one time in five). Turns toward the target while the
  animation plays; animation over -> 3.
- 7 cast (variant 2 only — see above): every frame computes the point P 300 ahead and
  passes it through `Creature_leadTargetPoint(400, this, P)`, and turns toward the target.
  On event bit 0: one own draw (bit 0) and `creature_findCorpseOfClass(300, this)` (a dead,
  still drawn creature of the same class whose death animation has ended; never when the
  caster is charmed). The weapon holder's table offsets 0x4c and 0x54 are called first in
  every branch (hand 1; arguments 0, 0x80, 0xff, 0x32 and 0, 0x80, 0xff, 0x96 — Inferred a
  weapon flash; bodies not read). Then:
  - **corpse found -> revive it**: slot 32 of the corpse with argument 1 (`Creature_revive`:
    full hp, state 0, cflag 0x100000000) and a sound on it. Takes priority over both casts.
  - else, low bit of the draw 0 -> **ShockOfFrost**: angle = `creature_aimAngleAt(350, this, target)`
    (uses own generator for spread, per its symbol note); `pool_new(0xd0)` +
    `ShockOfFrost_ctor` (0x2f7404) with (position raised by half the height, angle, (int)
    monster level 0x4f714c, owner this, SKILL[23 ShockOfFrost]). The skill object is only
    passed as a pointer; none of its table entries is called here.
  - else, low bit of the draw 1 -> **FrostStorm**: SKILL[58 FrostStorm] table offset **0x64** is called
    four times with (index 0..3, (int) monster level, this, 0 / 10 / 10 / 10) giving q0..q3;
    `pool_new(0xac)` + `FrostStormSpell_ctor` (0x1fe508) with (q1 x 12 as float, P, q2 x
    60, q0, owner this, velocity = facing direction x q3). No 0x0c "can cast" and no 0x14
    "cast" entry is used by this class.
  The state then lasts until clock > +0xf4 (-> 3) or the target comes within 20, arc 5000
  (-> 6). setState(7) sets +0xf4 = clock + 180 + (int)(rand/65536 x 180) (own) and starts
  the cast animation def+0x94 once, so there is one cast per visit, every 3–6 seconds.
- 0x10: flee until the attack cooldown ends -> 0. 0x12: until animation flag 0x10 clears ->
  0. 0x13: until not stunned -> 0. 0x14: `Creature_deadUpdate(30, this, events, zero, 0)`.
- 2, 4, 8–0xf, 0x11: return.

setState (0x2b65c4), non-routine parts: 0: +0xf4 = clock + rand%120; 1: +0xf4 = clock +
rand%120 + 300 (own). 3: the run animation is not restarted when coming from 3 or 6. 0x12:
refused in state 6 while the swing plays and in 0x13; one own draw picks one of four
reactions. 0x14: `Creature_dropLoot(36, 2, 1.8, 0.6, 2, 0.25, this, position, facing, 0)`
**only if cflag 0x100000000 is clear** (an Ulthork that was revived drops nothing the
second time — the test is made here in addition to whatever `Creature_dropLoot` does); one
own draw picks the death animation; holder table offset 0x5c drops hand 1's part; slot 28.

Save / load: saveState appends 8 bytes to the base record: hand-1 item type (holder table
offset 0x7c) and the variant. loadState reads them back: sets hand 1's type, the variant,
tint 0 and variant bits 0 (variant 2: bit 1 and tint 6), rebuilds the mask, and for a
record in state 0x14 switches hand 1 off (type 0). The random scale +0xdc is not in these
8 bytes (whether the base record carries it was not checked).

Phases: none.

Per-machine: (a) none found (the scan on run, setState, ctor, save, load; read by hand); all
draws own-generator in run / setState / ctor. (b) No: the draw sets a model draw parameter
(0x1797c8 with 2.0, reset by `model_resetDrawState`), `Creature_draw`, slot 16, holder
draw. (c) No.

Open: which type names the levels actually use (decides whether variant 1 ever occurs and
confirms that no shaman exists); the FrostStorm 0x64 query indices' meanings; holder table
offsets 0x4c / 0x54.

#### WarBoar  (factory prefix `WarBoar*`; vtable 0x517cf0; size 0x3d8)

Functions: ctor 0x2ba03c, draw 0x2ba340, run 0x2ba3a0, slot 11 0x2bac58 (empty body — the
"list of touched objects" callback does nothing, same as the base), setState 0x2bac60,
destructor 0x3ccae8. takeDamage is the base one. (0x2b9f8c + stub 0x2ba01c at the start of
this address range are the static initialiser of particle definition 0x8e4a60, whose only
other reference is `VampireLord_run` 0x2b7e8c: they belong to VampireLord.)

Constructor: `Creature_ctor` max-hp argument 10.0, class definition 0x502f80; draw
half-width 40, **speed 0** (root-motion movement), turn rate 1.0, radius 30, kind +0xb4 =
3, cflags |= 0x200040000, +0x5c = -0.2, forward draw offset +0xe0 = -15, scale +0xdc =
0.75. Type-name prefix `WarBoarSmall`: +0x3d0 = 1, +0xe0 = -10, scale 0.6 (radius stays
30). Variant bits 0, idle track def+0x84, 60-list, seven `creature_setDefEntryParams`
(entries 4, 5, 6, 7, 10, 0xb, 0xc), `Creature_init`. No properties read here.

Fields: +0x3c8 s32 "this attack's hit frame has passed" (0 at attack start, 1 on event bit
0); +0x3cc s32 last attack state started (6–10); +0x3d0 s8 1 = small boar.

States (run 0x2ba3a0; `Creature_stepAnim(1.0)`, `Creature_applyKnockback(0.2)`,
pickTarget). "Left" / "right" below mean the cone centred on facing + 8000 / facing - 8000:
- 0 idle: sees target -> 3; away from home, or clock > +0xf4 (entry + 180, fixed) -> 1.
- 1: sees target -> 0; else `Creature_moveToDest`.
- 3 chase: no target -> 0. In this order:
  1. target within 25, arc 3000 ahead -> own draw % 5: 0 -> 8, 1 -> 9, else -> 6;
  2. target between 25 and 100, arc 3000 ahead -> **10 (charge)**;
  3. target within 25 in the facing + 8000 cone -> 8; in the facing - 8000 cone -> 9;
  4. any enemy (`creature_findEnemyInCone(0, 25, this, facing, 3000)`) ahead -> own draw
     % 5 as in 1; in the + 8000 cone -> 8; in the - 8000 cone -> 9;
  5. target within 20 at any angle -> turn; else `Creature_moveToTarget`.
- 5 between attacks: no target -> 3 when not rooted. Target within 25, arc 3000: if the
  last attack was 6, own draw % 3 == 0 -> a second own draw % 3 picks 10, 8 or 9; in all
  other cases -> 6. Else target in the + 8000 cone -> 8, - 8000 cone -> 9; else any enemy
  ahead -> 6, + 8000 -> 8, - 8000 -> 9; else -> 3 when not rooted.
- 6, 7, 8, 9, 10 share one body: zero-velocity `Creature_moveBy`; on event bit 0
  **`Creature_hitAllEnemiesInArc(0, 25, this, facing, 3000, +0xd0, +0xd2, +0xd4, flags, 0)`**
  (every enemy in the arc, not only the target) and +0x3c8 = 1. Flags are 8, except for a
  big boar's charge (state 10, +0x3d0 == 0) and for state 7, where an own draw % 3 gives
  0x80008 on 0 and 0x40008 otherwise. While the animation plays, state 6 before its hit
  frame, and states 10 and 7 throughout, turn toward the target when it is within 10, arc
  3000. On event bit 1: target within 25, arc 8000, or any enemy in that cone -> 5 (which
  picks the next attack at once); otherwise, and when the animation ends -> 3.
  State 7 (def+0x54) is never requested by this class.
- 0x10: flee until the attack cooldown ends -> 0. 0x12: until animation flag 0x10 clears ->
  3. 0x13: until not stunned -> 3.
- 0x14 dead: on event bit 2 sets object flag 1 (not solid); `Creature_deadUpdate(30, this,
  events, zero, 0)`.
- 2, 4, 0xb–0xf, 0x11: return.

setState (0x2bac60), non-routine parts: attack states 6–10 clear +0x3c8 and record the
state in +0x3cc; animations 6 def+0x24, 7 def+0x54, 8 def+0x2c, 9 def+0x3c, 10 def+0x34.
0x12 is honoured only outside states 6–0xf (an attack is never interrupted by a hit
reaction). 0x14: clears object flag 1 unless flag 2 is set (the body stays solid until the
animation's bit-2 marker), `Creature_dropLoot(36, 2, 2.8, 0, 3, 0.25, this, position,
facing, 0)`, one own draw picks the death animation (def+0x5c / def+0x64), slot 28.

Phases: none in the AI. The draw function switches the second model from def+0x14 to
def+0x1c when hit points fall below 25% of the maximum (a wounded skin; display only).

Per-machine: (a) none found (the scan on run, setState, ctor; read by hand). (b) No — the draw
reads +0x228 / +0x22c and calls `Creature_draw`. (c) No.

Open: nothing class-specific.

### Cross-class observations

- **Functions that sit in a class's address range but belong to a neighbour** (file order:
  a class's static initialiser follows its last method, so it lands at the head of the next
  class's range): 0x2b3afc / 0x2b3e10 (light classes, not UndeadKnight); 0x2b5370, 0x2b53cc,
  0x2b5518 (UndeadKnight, not Ulthork); 0x2b9f8c / 0x2ba01c (VampireLord, not WarBoar);
  0x2bc7c8 (Warrior, not WoodElfSoldier); 0x2bf26c / 0x2bf28c (WoodElfSoldier, not Wraith).
  The four stubs 0x2b3e10, 0x2b5518, 0x2ba01c, 0x2bf26c are consecutive entries of the
  static-constructor table at 0x3e9a48–0x3e9a54.
- **Max-hp draw before the base constructor** (WoodElfSoldier 0x2bc868, Wraith 0x2bf304,
  WarWraith 0x2c07f0): `GameObject_rand(this) % 14 + 4` on a zero-filled block always
  yields 4.0. Vampire, UndeadKnight, Ulthork, WarBoar and Warrior pass the constant 10.0.
- **Speed 0 / root-motion movers**: Vampire, UndeadKnight, Warrior, Ulthork and WarBoar set
  +0xb8 = 0 and start their move animations with flag 0x800; WoodElfSoldier (100 / 150) and
  the wraiths (140, written directly to the position) use the speed field.
- **Dead code found by caller search**: WoodElf pairing (0x2be970, with it state 0x17 and
  the spear's escort branch), UndeadKnight mount (0x2b5370) and second handle +0x3cc, Ulthork
  variant 2 (inverted name test), UndeadKnight state 8 (shadowed arc test), Warrior states 9
  and 10, WarBoar state 7 (never requested).
- Own-generator draws are the only random source in every run / setState / constructor
  read here; the shared seed appears only inside callees (`Creature_dropLoot`,
  `loot_generateDrops`, `damage_apply`); the cosmetic seed only in the Vampire constructor's
  `anim_randomizeTopTime` and in the Vampire death particle helper.

## 5. Monster and spell projectiles

Projectiles that belong to one boss are described with it in section 3: HateBeam, HateProjectile, HateSoul and SpellHateEffect (Innoruuk), DustDevil, SpawnMummy and MummySnake (MummyKing), WebTrap and the web strand (SpiderQueen), JunkProjectile (IronGuardian), BoltGoRound (CloudGiant), LavaBomb (LavaMonster). Sparks and IceBall are in 6.2 with their neighbours.

#### beetleProjectile  (created only by FireBeetle_run state 7; vtable 0x50e3d8; size 0x1d0; base MissileWeapon)

Functions: ctor 0x247884, draw 0x247978 (empty), run 0x247980, onTouch 0x247e1c.
Constructor (this, pos, velocity, facing, owner, min, max, a8, stack: s0, s1, sound):
MissileWeapon_ctor(this, type 0, 0, 0, pos, velocity, facing, owner, 0, 0, min -> +0xd4, max ->
+0xd8, a8 -> +0xdc, s0 -> +0xe0, s1 -> +0xe4, 4 -> +0xe8, descriptor 0) (0x2478ec-0x247928);
then owner handle at +0x1c8 and the impact sound at +0x1cc. With the beetle's call: damage
+0xd0/+0xd2 of the beetle, +0xe4 (the attack-rating argument of damage_apply in
MissileWeapon_onTouch 0x152a18) = the beetle's +0xd4, flags 4, no descriptor — the beetle's
optional fire effect is not carried by the projectile. Lifetime: MissileWeapon_ctor sets +0xec
= g_simFrame + 300.
run (every frame): three particles (definitions 0x8e30f8 x2 and 0x8e3148) placed with own
rand (rejection loops, so a variable number of draws, all in run code); vertical velocity
+0x1b8 -= 9; obj_moveAndCollide(this, velocity +0x1b0); a non-zero result sets +0xec = 0. When
+0xec <= g_simFrame: impact sound, then five times: own-rand point within 20 units, z =
terrain_height(6) under the projectile + 1; if the owner handle is still alive a LooseFire
(pool 0x54, ctor 0x202b70) there with the owner object; decal_add(24, point, own-rand angle,
type 9). Then deletes itself through slot 1.
onTouch: ignores an object whose class is exactly FireBeetle; everything else goes to
MissileWeapon_onTouch.
Per-machine: (a) none found by the scan. decal_add depends on a local detail option (per its
symbol note) but its own-rand argument is drawn before the call either way. (b) draw is empty.
(c) no.

#### DiseaseProjectile  (no factory name; vtable 0x513f50; size 0x98)

Functions: ctor 0x249a50, run 0x249c18, draw 0x249b38, onTouch (slot 6) 0x24a3a8. Created
only by Bubo_run state 10 (xref of the ctor: one caller).

Constructor `(scale, obj, Vec3 *pos, Vec3 *vel, angle, owner)`: `Projectile_ctor(obj, pos,
owner, 0)`; +0x59 = 1; +0x90 = scale; `obj_runEveryFrame`; +0x94 = starting z; +0x7c..+0x84 =
velocity; facing +0x38 = angle; +0x88 = 0; object flags |= 1; +0x8c = g_simFrame + 300.

Fields: +0x7c Vec3 velocity; +0x88 s32 "damaged someone" latch (set by onTouch); +0x8c s32
expiry frame; +0x90 float draw scale; +0x94 float launch height; owner handle +0x4c (base).

Run (every frame): vertical velocity -= 4.95; `obj_moveAndCollide(this, velocity)`. A
non-zero result sets expiry = 0 (so the object deletes itself at the end of this call) and:
- if the latch +0x88 is 0 and the result is exactly 1: z is raised to
  `terrain_height(5, world, pos)` when below it; if z is then more than 24 below the launch
  height, three `GameObject_rand` values (angle, size 12..17, type 7 or 8) feed `decal_add`;
- always: three loops of 12 particles (definitions 0x8e3198, 0x8e31e8, 0x8e3238), each
  particle using rejection-sampled own-generator triples (a variable number of draws).
When expiry <= g_simFrame: slot 1 (3) = delete.

onTouch(other): only if the owner handle is set and the owner's slot 20 (isEnemy) of `other`
is non-zero (argument register checked in the instructions at 0x24a3bc-0x24a3e0). Builds a
descriptor on the stack whose first free effect slot is type 0x26 (disease) with v1 = owner
+0xd0, v2 = owner +0xd2, v3 = 0, then `damage_apply(min = owner +0xd0, max = owner +0xd0
(the minimum twice), victim = other, attacker = owner, attackRating = owner +0xd4, 0, 0,
flags 1, descriptor, noCrit 0)`. A non-zero result sets the latch +0x88. The projectile is
not deleted here; deletion follows from the collision result in run.

Draw: builds a matrix from position, facing + 0x4000 and scale +0x90, looks up
`gutchunks.vif` / `gutchunks.tex` in `fx.lmp` with `res_find` and calls `model_draw`.

Per-machine: (a) none found (the scan and by hand); the decal call depends on a local detail
option inside `decal_add` (docs symbol note), but the three generator draws are made before
the call regardless. (b) draw stores nothing in the object. (c) none; `res_find` is a
resource lookup.

Open: units of the velocity handed to `obj_moveAndCollide` (per second or per frame) not
checked; return codes of `obj_moveAndCollide` other than "1 leads to the decal" not checked.

---

#### SnowballSpell  (no factory name; vtable 0x5152c8; base Projectile; size not known)

Functions: ctor 0x26d884, draw 0x26d940, run 0x26da20, onTouch 0x26de54.
NOT INSTANTIATED: the constructor has no caller and no pointer to it anywhere
(ps2elf xref and ptrs on 0x26d884: nothing; text.asm has no jal to it; the only reference to
the table 0x5152c8 is inside the constructor). Everything below is what the dead code would do.
Constructor (this, pos, velocity, damage int, owner): Projectile_ctor(this, pos, owner, 0);
+0x58 velocity, +0x68 damage, +0x6c = 0 (has hit), +0x64 = g_simFrame + 300 (expiry);
obj_runEveryFrame.
Run: one particle per frame (particle_spawn with descriptor 0x8e35f8; position and velocity
from 6+ GameObject_rand draws, rejection-sampled); spin +0x54 −= 2000;
obj_moveAndCollide(this, velocity): result bit 0, or bit 1 after a hit (+0x6c), sets expiry to 0.
At expiry: sound `expl_ice%d` (GameObject_rand mod 3), fx_spawn(10), seven PhProp pieces
(pool 0x248, ctor 0x155a0c, model `boulder` from fx.lmp, part bit 1<<i, flags 0x112) whose
velocity is 0.3×own + 0.3×ball velocity, then deletes itself through slot 1.
onTouch (this, other): nothing after the first hit. Team filter on the owner handle +0x4c
(owner a player: other players and charmed creatures are skipped; owner a monster: non-player
creatures are skipped; +0x312 non-zero on the owner swaps the rule). A non-player creature with
cflag 0x200 (blocking) is skipped. Otherwise damage_apply(dmg, dmg, other, THIS PROJECTILE,
100000, 0, 0, flags 0, empty descriptor, 0) and +0x6c = 1.
Per-machine: (a) run: GameObject_rand only, fx_spawn(10) is camera-gated cosmetics.
(b) draw stores nothing. (c) draw: two res_find lookups and model_draw only.

### Family: small effect / projectile objects 0x2931bc–0x295cf4

None of these is a monster. None of their draw functions does anything: LostSoul_draw
0x2936fc, Root_draw 0x29400c, OniBall_draw 0x2946f0, UnholyAura_draw 0x294f9c and
LightningRod_draw 0x29594c are 8-byte returns; LightningBolt uses the base slot 5 (0x3c7ea0).
What is seen comes from trails, beams, particles and glows queued by the RUN functions.
Per-machine (b) and (c) are therefore "nothing" for all six (the draw scan and vtable read).

#### LostSoul  (no factory name; vtable 0x50e7e8; size 0xb0)

Functions: ctor **0x2931bc** (568 bytes, prologue at 0x2931bc; the catalogue in
docs/monsters.md give 0x293228, which is an address in the middle of this function's argument
copy and not a function entry — symbols/monsters.tsv already carries the corrected entry),
run 0x2933f4, draw 0x2936fc (empty), dtor 0x3c5ec0.
Slot 6 (touch) is the base no-op 0x3c7ea8.

Constructor (this, pos*, velocity*, facing, unused, mode, lightOn): `Projectile_ctor(this,
pos, owner 0, 0)`; embedded light at +0x64 (position +0x94) is linked; radius +0x1c = 0;
velocity +0x58..+0x60; +0xa4 = mode; +0xa8 = lightOn; object flags |= 0x4001; expiry frame
+0x54 = g_simFrame + 60 (mode 1) or + 600 (other); `obj_runEveryFrame`; a trail handle
(`trail_create`) at +0xac. Mode 1 without light: the light is unlinked again.

Created by: `SkillRepulseUndead_cast` 0x2f4e2c — a ring of them, mode 1, no light, speed 450
outward + 50 up, angle step 0x10000 / (level + 4); and `DismissUndeadProjectile_onHit`
0x2f6364 — one, mode 0 with light, when the projectile's victim ends at hp <= 0.

Run: mode 0: facing += 500 per frame and velocity = (cos, sin) × 240 with 50 upward (a rising
spiral). Mode != 0: keeps its velocity; while (expiry − g_simFrame) < 30.0 it adds 50 to the
vertical speed each frame (the test goes through the soft-double helpers 0x3afa08 / 0x3af9b8;
"less than" is Inferred from the sign test on the result). `obj_moveAndCollide(this, velocity)`; adds a trail point offset
sideways/up by 0.754 × cos/sin(g_simFrame × 0x1ae0); light follows when lightOn; at the
expiry frame calls its own slot 1 (3).
Hits nothing, no damage, no generator draws: a visual only.

Per-machine: (a) none found (the scan; body read: only g_simFrame). (b)(c) empty draw.

#### Root  (no factory name; vtable 0x50e758; size 0xc0)

Functions: ctor 0x293704, run 0x293ae0, draw 0x29400c (empty), dtor 0x3c5fd0.

Created by: Player_run 0x1a5030 at 0x1ac02c only, in the branch taken when the s16 at +0x20 of
the record being used equals 0x19 (decompile line 3013–3019: after the current animation
track's progress reaches 1.0); duration argument 30.0,
position from the stack, caster = the player. (What the record is — Inferred: a used item
definition — was not traced.)

Constructor (seconds, this, pos*, facing(unused), caster): `Projectile_ctor(this, pos, 0, 0)`;
flags |= 0x4001; expiry +0x58 = g_simFrame + seconds × 60; `obj_runEveryFrame`. Then a box
query ±360 around the position (at most 0x20 objects) picks ONE victim: an object with the
creature flag 0x20, not dead (0x8), **not a player** (0x40), with status counter 7 (+0x388)
<= 0, not the Root itself and not the caster. Two running bests are kept, "in front of the
caster" (dot of the caster's facing with victim − caster > 0) and "behind"; the front one
wins if any. As written (the two compares at 0x2938c8–0x2938d8) a candidate is accepted when it is nearer than
EITHER best, so a side's stored best can be replaced by a farther candidate. No
enemy/ally test (slots 20/21 are not called): any non-player creature qualifies.
- no victim: +0xb0 = 0 and the object deletes itself inside its constructor (slot 1 (3)).
- victim: +0xb0 = **raw object pointer** (not a handle); +0x54 = g_simFrame; victim +0x388 =
  seconds × 60 (status counter 7, which `Creature_run` turns into the slow amount) and
  victim +0xf0 = g_simFrame; the Root takes the victim's position and facing; trail handle
  +0xb8; +0xbc = 1.

Run (effect only): facing += 0x1ff; own position = victim position + 20 × (cos, sin)(g_simFrame
<< 11), height += 0.937 per frame; trail point for the first 90 frames; for every surface
sample point of the victim's model (victim slot 16, `model_getSamplePointCount`) one own-
generator draw, and when it is below 0x17a and the point is lower than (frames alive × 1.5)
three more own draws and one `leafclump` particle (def 0x8e4290). At the expiry frame slot 1
(3). No damage is ever dealt; the whole gameplay effect is the one write of counter 7 in the
constructor.

Hazard (Observed pointer use, Inferred consequence): the victim pointer at +0xb0 is
dereferenced every frame for 1800 frames (position, table call slot 16, animation state)
with no handle and no liveness test, so a victim deleted within 30 s (e.g. a sinking corpse)
leaves the Root reading a freed pool block.

Per-machine: (a) none found (the scan; body read). Two one-time resource guards 0x5016c4 /
0x5016c8 (`leafclump.vif` / `.tex` from `fx.lmp`) are set from run code. (b)(c) empty draw.

#### OniBall  (no factory name; vtable 0x50e878; size 0xb8) — the LifeTap orb

Functions: ctor 0x294014, run 0x2941e4, draw 0x2946f0 (empty), touch 0x2946f8 (slot 6),
dtor 0x3c5db0 (not read).

Created by:
- `Creature_processDamage` 0x110d30 at 0x111fcc, in the death branch: killer handle +0x2e4 is
  a player object → chance = `SkillLifeTap_getStat0Fraction(SKILL[59], player_getSkillRank(
  slot, 59))`; one draw from the dying creature's OWN generator; below chance × 65536 → orb at
  the creature's position.
- `Player_processDamage` 0x1b2cc0 at 0x1b36cc (PvP branch, killer is a player): same with
  chance × 3 and a SHARED-seed draw.

Constructor (this, pos*, facing(unused), deadCreature): `Projectile_ctor(this, pos, 0, 0)`;
radius 0; facing = own draw; flags |= 0x4000; expiry +0x54 = g_simFrame + 600. One own draw
picks the kind +0x74: below 0x7333 of 65536 → 0, and the dead creature's status counter 8
(+0x38c) = 30; else 1, and counter 10 (+0x394) = 30; dead creature +0xf0 = g_simFrame.
+0x58 = (int)(dead creature max hp × 0.05) — written, never read in this class.
`obj_runEveryFrame`; height += 36; wander point +0x68..+0x70 = position + (own % 100 − 50,
own % 100 − 50, own % 2000 + 36).

Run: finds the nearest (3-D) entry of `g_alivePlayers` (0x4f8440, count 0x4f8420 — the list
of all living players, not the local-only list) whose LifeTap rank is > 0. One own draw per
frame; below 0x1428 of 65536 (about 8 %) three more own draws choose a new wander point within
±500. **Homing** when that player's record hit points (record +0xac) are > 0 and the pad word
at `g_pads[slot] + 8` (0x41bfe0 + slot × 0x58) has a bit of `g_btnBlock[slot]` set, i.e. the
block button is held: destination = player position + 36 up, turn limit 0x666 per frame,
horizontal speed 200 × clamp(distance / 72, 0.6, 1.0), vertical speed ±200 (0 within ±9).
Not homing: turn limit 0x147 toward the wander point, then the velocity is replaced by 60
along the facing and 50 upward. One particle per frame (def 0x8e42e0 for kind 0, 0x8e4380 for
kind 1); `obj_moveAndCollide(this, velocity)`; at the expiry frame slot 1 (3).

Touch 0x2946f8 (called for what it touches): only when the other object is a player (flag
0x40) that is not the prediction copy (flag 0x20000 clear), has LifeTap rank > 0 and holds
block. amount = `SkillLifeTap_getStat1(SKILL[59], rank)`. Kind 0: player record +0xb4
(pending heal) += amount, clamped so hp + pending <= max hp; player object counter 8 (+0x38c)
= 30. Kind 1: record +0xc8 (pending mana) += amount, clamped to max mana − mana; counter 10
(+0x394) = 30. Player object +0xf0 = g_simFrame. Then the orb's expiry = current frame (it
deletes itself in its next expiry test).

Per-machine: (a) run and touch read the pad word `g_pads[slot] + 8` and `g_btnBlock` (0x41b9d0)
for a gameplay decision (homing, pick-up). docs/monsters.md 7.9 already records that word as
the lockstep pad block ("Observed; not a hazard"); nothing here contradicts it, and the touch
handler does test the prediction-copy flag. The orb also walks `g_alivePlayers`, which carries
the known caveat in docs/player.md ("the copy's death rebuilds the alive list"). No camera,
cosmetic seed or local-slot call (the scan: none). (b)(c) empty draw.

#### UnholyAura  (no factory name; vtable 0x50e6c8; size 0xa0)

Functions: ctor 0x29486c, run 0x29496c, draw 0x294f9c (empty),
dtor 0x3c60e0 (not read).

Created by: Player_run 0x1a5030 at 0x1ac164 only, in the same "record +0x20" switch as Root,
value 0x1a: if the player's status counter 12 (+0x39c) is < 1 it creates a LightEffect and
this object with duration argument 50.5; otherwise it only writes counter 12 = 0 (switches
the aura off).

Constructor (seconds, this, pos*, owner): `GameObject_ctor` (not Projectile_ctor); flags
|= 0x4001; owner handle at +0x98; `obj_runEveryFrame`; +0x54 = −1 (not ending); +0x58 = 0
(brightness); +0x4c = g_simFrame; +0x50 = g_simFrame + seconds × 60; **owner +0x39c = 1**
(status counter 12; docs/gameplay.md: > 0 enables reflection).

Run: no owner handle → returns (never deletes itself in that case — Observed 0x29496c head).
Owner counter 12 == 0 → +0x54 = 1 (ending) and brightness −= 4.2667 per frame. First 30
frames: eight spokes of particles per frame, each with 6 own-generator draws for jitter
(def 0x8e43d0). First 60 frames: brightness += 2.1333. Every frame it queues three rings of
glow sprites around the OWNER's position with `glow_add` (a draw-queue call made from run
code). Ending and brightness <= 0 → slot 1 (3).
The expiry +0x50 is never read: the duration argument has no effect; the aura lasts until
something zeroes the owner's counter 12. It deals no damage and touches nothing itself.

Per-machine: (a) none found for decisions; `glow_add` and the texture word 0x4f849c are used
from simulation code (once per simulated frame, not per displayed frame) — cosmetic.
(b)(c) empty draw.

#### LightningBolt  (no factory name; vtable 0x5168e8; size 0x60)

Functions: ctor 0x295360 (this, pos*, lifeFrames, withLight: beam straight up 240 units),
ctor2 0x295584 (this, from*, to*, lifeFrames, withLight), dtor 0x295784, run 0x2957e4; draw
is the base no-op.

Both constructors: `GameObject_ctor`; +0x4c = life; flags |= 0xb; end point +0x54;
`beam_create(25, 1.5, from, to, 0x10e, 0xf, 0x5e808080)` → handle +0x50; with withLight a
`LightEffect` (0xbc bytes, ctor 0x201bd8) 12 above the start; `obj_runEveryFrame`.
Run: life −= 1; `beam_update(handle, pos, end, 0x5e, −1)`; `fx_spawn(0x13, pos)`; life < 1 →
`obj_delete`. No collision, no damage: the damage of the things that use it is done by the
creator.
Created by: Hag_run at 0x270068, LightningRod_run 0x2959d4 (life 0x11, light on),
`LightningStrikeSpell_run` 0x31b594 (ctor 1); `SpellConeOfShock_run` 0x31bf3c (ctor 2).

Per-machine: (a) none (fx_spawn is camera-gated but creates nothing for id 0x13). (b)(c) n/a.

#### LightningRod  (factory name `LightningRod`; vtable 0x516858; size 0x5c) — level object

Functions: ctor 0x2958a8, run 0x295954, draw 0x29594c (empty), dtor 0x3cbcd4 (not read).
Properties: none read (the property list is only handed to `GameObject_ctor`).
Constructor: flags |= 0xb; +0x54 = (int)(ownrand/65536 × 1200) frames; `obj_runEvery60`.
Run: `+0x4c = obj_updateActive(this, +0x4c, 600)`; nothing else when inactive. Active:
when +0x54 < 1 it creates a LightningBolt (ctor 0x295360, life 17 frames, with light), plays
`spel_ew_shock_hit.anm` from `fx.lmp` at its position and sets +0x54 = 1200 + (int)(ownrand
/65536 × 600); otherwise +0x54 −= 1. Every even frame: two rejection-sampled points in the
unit sphere (3 own draws per try) → one particle (def 0x8e3f60, guard 0x5016cc). Every 8th
frame `fx_spawn(0x13, pos)`.
No trigger, touch, interact or script; nothing saved (base slots 8/9). No damage: decoration.

Per-machine: (a) the whole body (timer, own-generator draws, object creation) is gated by
`obj_updateActive` with radius 600, so it inherits that function's known camera dependence
during net cutscenes (docs/objects.md O4); nothing else. (b)(c) empty draw.

---

#### PoisonProjectile  (no factory name; vtable 0x517888; size 0xa8; base Projectile)

Functions: ctor 0x2b153c, draw 0x2b16a4, run 0x2b176c, onTouch (slot 6) 0x2b1c4c.

Who creates it (xref of the constructor, five call sites, each `pool_new(0xa8)` inside a
loop of a monster run function; the addresses are the call instructions): 0x234f60 in
Amphian_run (0x23483c), 0x23624c in Ant_run (0x2359fc), 0x2572cc in Cyclops_run (0x256b18),
0x258b04 in FatCyclops_run (0x258200), 0x2ae7a0 in SpiderQueen_run (0x2ad630). Every site
passes: scale = 0.5 +
0.5 × (one draw of the **creator's** generator / 65536); the creator's class block; four
resource indices into that block (model, texture, clip, impact sound): Amphian 0x10 / 0x11 /
0x12 / 0x14, Ant 0xf / 0x10 / 0x11 / 0x13, Cyclops 0x13 / 0x14 / 0x15 / 0x1b, FatCyclops 0x14
/ 0x15 / 0x16 / 0x18, SpiderQueen 0x16 / 0x17 / 0x18 / 0x1a; start position; velocity. The
constructor also takes a facing and the owner as its 10th and 11th (stack) arguments; the
values the creators pass for those, and the creators' own code, were not read here.

Constructor (0x2b153c): `Projectile_ctor(this, pos, owner, classBlock)` (owner handle +0x4c,
radius 12 per the objects symbol file); stores the four indices at +0x54 / +0x58 / +0x5c /
+0x60 and the scale at +0xa0; queues the clip and calls `anim_randomizeTopTime` (cosmetic-seed
phase, docs/engine.md P4); `obj_runEveryFrame`; velocity → +0x8c; start height → +0xa4; +0x98
= 0; object flags |= 1; expiry frame +0x9c = `g_simFrame` + 300.

Fields:
| offset | type | meaning | where |
|---|---|---|---|
| +0x4c | handle | owner (base Projectile) | onTouch, run |
| +0x54, +0x58, +0x5c, +0x60 | s32 ×4 | model, texture, clip, impact-sound index into the class block (+0x24) | draw, ctor, run |
| +0x64 | struct | animation state | run, draw |
| +0x8c | Vec3 | velocity, units per second | run |
| +0x98 | s32 | "counts as a hit" flag | onTouch, run |
| +0x9c | s32 | frame number at which it deletes itself | ctor, run |
| +0xa0 | float | draw scale | draw |
| +0xa4 | float | height it was fired from | run |

How it moves (run 0x2b176c, every frame): advances its clip; emits 4 particles (definition
0x8e46f0, velocity = random in-sphere vector × 8: three own draws per attempt in a rejection
loop); velocity z −= 4.95; `obj_moveAndCollide(this, velocity)` moves it by velocity / 60,
tests the terrain and calls slot 6 on both sides for every overlapping object except the
owner (result bit 1 = terrain, bit 2 = object; body read at 0x1509f8).

What it hits and how it ends:
- result 0: keeps flying; when `g_simFrame` ≥ +0x9c (300 frames) it deletes itself through
  slot 1 with argument 3, with no effect.
- any non-zero result: impact sound; +0x9c = 0 (so it is deleted at the end of this call).
  Result exactly 1 (terrain only): +0x98 = 1, z raised to the terrain height; if it landed
  more than 24 below its start height: three own draws and `decal_add(12 + rand % 6, pos,
  angle, type 4 or 5, 0)`.
- onTouch (0x2b1c4c): an object of the same dynamic type as the owner is ignored; otherwise,
  unless the other object is itself a PoisonProjectile, +0x98 = 1. (A null "other" would go
  to the bad-typeid throw 0x3b3338; `obj_moveAndCollide` never passes one.)
- if +0x98 is set and the owner still exists: v = `PoisonWeapons` (26) skill-table offset
  **0x5c** with (0, `(int)` monster level 0x4f714c, 0) (call at 0x2b1a40). Two own draws r1, r2. Descriptor:
  effect slot type 0x17 (poison), v1 = v, v2 = v + (int)(v × 0.2 × r1 / 65536), v3 = 0.
  `combat_applyAreaDamage(12, 36, owner, position, min = v, max = v + (int)(v × 0.2 × r2 /
  65536), flags 0x10000, descriptor)`: box of 36; every object other than the owner that the
  owner's slot 20 calls an enemy (creature owners) and that is closer than 36 (octagonal
  distance minus its radius) takes `damage_apply(d, d, victim, owner, rating 10000, …)` with
  d = (36 − distance) × max / 24 clamped to [min, max]. The shared seed is drawn inside
  `damage_apply`, not here.
- then `fx_spawn(6, position)` (camera-gated cosmetic), and the deletion.
A collision whose result is 2 or 3 with only ignored objects (owner's class, other poison
blobs) therefore ends the projectile without damage, even when it also touched the ground
(result 3) — Observed from the `== 1` test at 0x2b1910–0x2b1914.

Generators: its own (`GameObject_rand`) for everything in this class — particles (12 or more
draws per frame), the decal (3), the two damage rolls. No direct use of `g_randSeed`,
`g_cosmeticSeed` or 0x404468 in run or onTouch.

Other slots: takeDamage (slot 2) is the shared empty stub 0x3c7e88; clone (slot 15) is the
base `Projectile` clone 0x11c7f8 (0x54 bytes) although the object is 0xa8 bytes (vtable).

Per-machine:
(a) None found for gameplay (the scan on run, onTouch, ctor; then by hand). Cosmetic and known:
`fx_spawn(6)` at 0x2b1be8, `decal_add` (local decal option; its three draws are taken before
the call, so the draw count does not depend on the option), the sound, and the
cosmetic-seed clip phase set in the constructor (engine.md P4) — run never reads the clip
state (it only advances it), draw does.
(b) Does draw change anything? No: PoisonProjectile_draw 0x2b16a4 builds a matrix on the
stack from position, facing + 0x4000 and scale and calls `model_draw` (0x1779b0) with the
clip state as an input; it stores nothing in the object (the draw scan: no hits).
(c) No draws, no creation, no run-list change, no script, no world query in draw.

Open: whether `model_draw` writes into the clip state it is given (engine area); the
creators' velocity and count logic.

## 6. Level objects

### 6.1 The data-driven family

### The Auto family, CreatureContainer, Generator

*Reader's notes for this group.* Method: every function listed was read in the Ghidra decompile; doubtful spots were
settled with tools/dis.py (said where). Default status is Observed at the address given.
`own draw` = GameObject_rand(obj) (0x1509d0, returns the upper 16 bits: 0..65535).

### 0. How the factory creates the family (0x159c94)

Observed in the factory tail (decompile lines 1812-1905, calls at 0x15d6bc-0x15d8c8). These classes
are NOT chosen by the type name. After every name comparison has failed, the factory looks at
the object's PROPERTY LIST (props_getInt 0x14f730 / props_getStr 0x14f850 on the list argument)
in this order; the type name is only handed to the constructor, which uses it as the model name:

| property present (non-zero int unless noted) | LP test 0x23a2b4 | class | pool size | ctor |
|---|---|---|---|---|
| `CreatureContainer` | - | CreatureContainer | 0x3d0 | 0x243624 |
| `AutoContainer` | 0 / 1 | AutoContainer / AutoContainerLP | 0x148 / 0x150 | 0x23d93c / 0x24259c |
| `AutoChest` | 0 / 1 | AutoChest / AutoChestLP | 0xf8 / 0x100 | 0x23ad18 / 0x241468 |
| `AutoProp` | 0 / 1 | AutoProp / AutoPropLP | 0x198 / 0x448 | 0x23c44c / 0x2416c4 |
| `AutoEmitter` | - | AutoEmitter | 0x60 | 0x240dc8 |
| `AutoDoor` or `AutoSwitch` | not tested | AutoProp (plain) | 0x198 | 0x23c44c |
| `Critter` | - | Critter | 0x448 | 0x2547fc |
| `Generator` (string) | - | Generator | 1000 | 0x2657a0 |
| `SmokeGen` (string) | - | SmokeGen | 0x490 | 0x31d180 |

Named entries that reach the family directly: `AntMaker` -> Generator (line 58); `AntTrapa` ->
AntTrap (0x1a0); `Antlighta/b/c` -> AutoPropLP (0x448; label shared with the AutoProp+LP case);
`ScriptGenerator` (0x4c), `HateGate`, `HateInto` (0x1b8 each). AutoObject itself has no factory
entry (xref 0x23a354: only the AutoChest, AutoProp and AutoContainer constructors call it).
AddParticle is never made by the factory: xref 0x23fae0 -> AutoChestLP_ctor, AutoContainerLP_ctor;
xref 0x23fc50 -> AutoEmitter_ctor (4 calls) and AutoPropLP_ctor (4 calls).

**What "LP" means.** 0x23a2b4(props) returns 1 when the property list has a non-zero
`ParticleEmitter`, `DynamicLight` or `Halo` key, or one of `ParticleEmitter<n>` /
`DynamicLight<n>` / `Halo<n>` for n = 0..3 (0x23a200 tests one index; 0x23a100 is the
case-folding "key=value -> atoi" lookup on a bare list; note it lower-cases its key argument in
place). So an LP object is the same object with an attached light / particle / halo helper
(an `AddParticle`, section 9). Inferred: LP = "Light + Particle". The LP classes add only: a
helper pointer (or four), a draw that first asks the helper(s) to place the light and halo
(helper slot 17) and a run that first asks the helper(s) to emit particles (helper slot 18).
Everything else is inherited (tables compared with vtab.py).

### 1. AutoObject (no factory entry; vtable 0x5134f8; base part ends at +0xd8)

Functions: ctor 0x23a354, draw 0x23aa20, run 0x23ad00 (empty), save 0x23ad08 / load 0x23ad10
(both return 0 bytes). Slots 2, 3, 6, 13, 14 are the GameObject stubs (vtab.py).

Constructor (this, typeName, pos, angle16, props): GameObject_ctor; facing +0x38 = angle;
+0x4c = the type name lower-cased and cut at the first `-`, `;` or `,`.

| key | type | lands in | meaning | address |
|---|---|---|---|---|
| `LumpName` | str | +0x6d (file name, ".lmp" appended) | archive holding the model; default = the type name | 0x23a354 l.60 |
| (none) | | +0x90 / +0x94 | model `<name>.vif` and texture `<name>.tex` from that archive (res_find) | l.72-77 |
| `radius` | int | +0x1c (float; default 12) | collision radius; a value of 0 also sets flag 0x1 (not solid) | l.80 |
| `radius2` | int | +0x1c | same field, read second, so it wins | l.88 |
| `height` | int | +0x20 (default 60) | collision height | l.96 |
| `drawradius` | int | +0x28 (u8, max 255) | cull radius; default = half the horizontal diagonal of the model bounds, at least the collision radius | l.165 |
| `drawheight` | int | +0x29 (u8, max 255) | cull height; default = half the vertical extent of the model bounds, at least the collision radius | l.176 |
| `initScript` | str | - | script_runByName at construction unless a cutscene is active | l.188 |
| `multiwak` | str, repeated | +0x6c (bool: present) | extra models drawn with the object: each value names `<v>.vif` / `<v>.tex` in the same archive (looked up inside the draw, every frame) | l.191, draw l.62 |
| `fullbright` | int | +0xd0 mask 2 | drawn with a fixed ambient colour instead of level lighting | l.193, draw l.53 |

Fields: +0x98 animation state (cleared in the ctor; +0x9c track count, +0x9e u16 status where
0x80 is tested as "top track finished" by the subclasses), +0xc0 result of the last animation
advance, +0xc8 64-bit mesh hide mask handed to model_draw, +0xd0 draw flags (mask 1 = no shadow
pass, i.e. model_drawShadow 0x1762e8 is skipped; mask 2 = fullbright).

draw 0x23aa20: builds the matrix from position and facing, optional animation pose, model_draw
with the hide mask, then every `multiwak` model. Stores: (1) global 0x41c148 = 1 when
drawradius or drawheight is 255; (2) the object flag word: flag 0x100 (hit flash, the bit the
creature draw also consumes) makes it draw with the flash ambient 0x4fece0, and after drawing
the bit is CLEARED - only when 0x100 or fullbright was set (l.81-83). No other store.

Per-machine: (a) nothing (run is empty). (b) the draw clears flag 0x100. Inside this family
0x100 is set only by the three LP draws, and those stores are dead code (section 5); no run,
trigger, damage, save or load function of the family reads 0x100 (pattern search over all 99
functions for the +0xc word, then read by hand: the only reader is this draw). So the first-pass
open row is settled: the bit is 0x100 and it never reaches shared logic through this family.
Whether outside code (damage helpers) sets 0x100 on these objects was not read. (c) no generator
draw, no object creation, no run-list change, no script; model_drawShadow reads terrain
heights (read-only, per its symbol note) and res_find is called for each `multiwak` model
(resource lookup, no state).

### 2. AutoChest (property `AutoChest`; vtable 0x513468; 0xf8) and AutoChestLP (0x513168; 0x100)

Functions: ctor 0x23ad18, save 0x23b06c, load 0x23b0b4, run 0x23b170, prompt 0x23b6bc (slot 13),
trigger 0x23b854 (slot 3), interact 0x23b894 (slot 14), loot 0x23ba3c.
LP: ctor 0x241468, dtor 0x2414f8, draw 0x241568, run 0x241604, interact 0x241670.

Constructor: AutoObject_ctor; flags |= 0x100018 (0x100000 interactable, 0x10 standable top, 0x8).

| key | type | lands in | meaning | address |
|---|---|---|---|---|
| `Sound` | str | +0xf0 (0 wood, 1 metal, 2 stone) | which opening sound; any other value leaves 0 | 0x23ad18 l.33 |
| `bomb` | int | +0xe4 = 1 | forces a trapped chest | l.56 |
| `gold` | float | multiplier (default 1.5) | gold = own draw % 100 + 50 + (own draw % 12 + 12) x gold x (max(save_getAct(),0)+1) x level_monsterLevelTimes0_4() -> +0xdc (s16) | l.76-92 |
| `item` | str, repeated | - | presence clears the trap flag and the gold in the ctor; each value is a named item dropped on opening | l.113, loot l.99 |
| `key` | str, repeated | - | each names a script; the chest is usable only when every one returns non-zero | prompt l.19 |
| `lockMessage` | str | - | text id shown while a key script fails | prompt l.34 |
| `openmessage` | str | - | text id of the prompt (default id OpenChest) | prompt l.21 |
| `action` | str, repeated | - | scripts run when the lid animation is a third done (obj_runActionScripts(this, 1)) | run l.42 |
| `spawncreep` | any | - | creates an object of type `creep` at the chest, facing - 0x4000 | loot l.89 |
| `potions` | int | - | that many random consumables | loot l.155 |
| `random` | float, repeated | - | one random item each (below) | loot l.209 |

Other constructor decisions: trapped (+0xe4) when one own draw < 2000 (of 65536) or `bomb`;
type names `leanto` and `excal` clear the trap and set +0xec = 1 (no default loot); `venchest`
and `deathweb` clear the trap; gold is 0 in PvP mode A (g_pvpModeA) and when a further own draw
< 0xc80; a trapped chest without `item` has gold 0. Hide mask +0xc8 = model_buildHideMask(model,
bits) with bits 0 (no gold) / 1 / 2 (gold >= 0x78) / 4 (gold >= 0xf0) / 8 (trapped) / 0 (`item`).
+0xf4 = animation `<name>.anm`. The object is NOT on a run list until opened.

Fields: +0xd8 state 0 closed / 1 opening / 2 opened; +0xdc s16 gold; +0xe0 frame the trap was
armed; +0xe4 trapped; +0xe5 (saved, never written elsewhere in the class); +0xe8 frame at which
the lid is a third open; +0xec no-default-loot; +0xf0 sound kind; +0xf4 animation; LP: +0xf8
AddParticle helper.

State machine:
- closed (+0xd8 = 0): prompt returns usable only when every `key` script returns non-zero.
  trigger (slot 3, any value) calls its own slot 14 with player slot 0 - this path does NOT test
  the keys (0x23b854). interact(slot) does not test them either; the key test lives only in the
  prompt (the caller decides from the prompt result; that caller, Player_interact, was not read
  here).
- interact on a closed chest (0x23b894): +0xe8 = frame + animation length / 3, opening sound by
  +0xf0, lid animation pushed (flags 0x204), state 1, obj_runEveryFrame, +0xe0 = +0xe8, and the
  interactable flag 0x100000 is cleared when there is no gold.
- interact when already opened: hide mask = 1, coin sound, hud_addGoldFloater(slot, pos, gold),
  gold = 0 (the gold goes to the player slot passed in; with the trigger path that is slot 0).
  Note the flag 0x100000 is not cleared on this path.
- run, not trapped: advances the animation; in state 1 once frame > +0xe8: state 2,
  obj_runActionScripts(this, 1), AutoChest_dropLoot; leaves the run list when the animation
  status has bit 0x80.
- run, trapped: once frame > +0xe8, two fuse particles per frame (velocity from six own draws
  each, rejection-sampled), and once frame - +0xe0 > 90: explosion sound, fx_ringBurst,
  camera_shake(10), world_damageInRadius(inner 40, outer 180, attacker = the chest, damage
  (g_levelMonsterLevel - 2) x 20 + 15, type 0x40840), a floor decal (angle from an own draw), a
  LightEffect (0xbc), obj_delete. A trapped chest never drops loot and never runs its actions.

AutoChest_dropLoot 0x23ba3c (`autoobject_dropLoot` until the rename; xref: ONE caller, AutoChest_run 0x23b674 - the first pass listed
AutoProp_run and 0x23d2ec as callers; they are not):
- `spawncreep`, every `item` (item_parseDescriptor -> a 0x248-byte item prop given horizontal
  velocity 24 in the direction facing +- 0x2000, the offset from an own draw);
- `potions` times item_generateConsumable;
- every `random` value v: worth = v x level_monsterLevelTimesDifficulty() x (0.95 + own draw x
  0.1/65536) x 300, then DOUBLED when save_getAct() >= 1 and ZERO when it is below 1 (l.232-238);
  item_generateWithAffixes(item, worth, category = table 0x4fece8[own draw % 3], -1, 1);
- default loot, only when there was no `random`, +0xec is 0 and neither `spawncreep` nor `item`
  was present: three loot_generateDrops(36, 2, 0, 0, row, chance, pos, facing, 0, 0) calls with
  (row, chance) = (5, 0.95), (6, 0.02), (9, 0.005);
- and, when there was no `potions` and the same two conditions hold: one own draw, below 5000 ->
  the named item `arrows`, below 15000 -> a consumable, else nothing.
First-pass correction: the `random` worth factor here is 300 doubled (zero in act 0), not the
Chest formula; the category table is 0x4fece8.

save/load (12 bytes): low 32 bits of the hide mask, gold, +0xe4, +0xe5, state. load of an
opened chest pushes the lid animation at its end and clears 0x100000 when gold <= 0. The trap
timers +0xe0/+0xe8 are not saved and a loaded opened chest is not put back on a run list
(a trapped chest saved while its fuse burns therefore stays unexploded after a load - Inferred
from the code, not tested).

AutoChestLP: ctor = AutoChest_ctor + one AddParticle (0x184 bytes, unindexed keys) at +0xf8.
run 0x241604: helper slot 18 (position, 0, 0) then AutoChest_run. interact 0x241670: on a
closed chest first starts the helper's emitter in one-shot mode (0x240cf4(helper, 1)), then
AutoChest_interact. draw 0x241568: helper slot 17 (position), then AutoObject_draw. The LP
chest never switches the helper's light on (no call to 0x240d2c), so its DynamicLight stays the
static light linked by the helper constructor and its Halo is never drawn (Observed: slot 17
needs helper +0xfc).

Per-machine:
(a) run / interact / trigger / loot: no camera, local-slot, audio or cosmetic-seed read for a
decision (pm-style read by hand). The fuse particles and loot use the chest's own generator;
loot_generateDrops and item_generateConsumable use the shared generator (their documented
behaviour). camera_shake and fx_ringBurst are cosmetic.
(b) AutoChestLP_draw: `flags |= 0x100` is guarded by 0x240db0(helper), a function that returns
constant 0 (dis 0x240db0: two instructions, result 0), AND by bit 0x40 of g_drawFrame. The store
(0x2415e8) is
unreachable; the frame-counter read can influence nothing. Had it been live it would only have
blinked the hit-flash ambient (64 displayed frames on / 64 off) through AutoObject_draw.
(c) The draw calls helper slot 17, which can draw from the HELPER's own generator (section 9).
(d) PROMPT 0x23b6bc runs every `key` script (script_runByName) each time it is evaluated; it
changes no object field. Known first-pass item (docs/script.md P1): prompts are evaluated from
both Player_run and Player_draw, so a key script with side effects runs at display rate on the
owning machine.

### 3. AutoProp (properties `AutoProp`, `AutoDoor`, `AutoSwitch`; vtable 0x5133c0; 0x198)

Functions: ctor 0x23c44c, dtor 0x23cac8, run 0x23cb54, save 0x23cea0, load 0x23ceb8,
takeDamage 0x23cf0c (slot 2), prompt 0x23d014 (slot 13), interact 0x23d1b0 (slot 14),
trigger 0x23d1fc (slot 3), nextState 0x23d2ec (slot 17), setState 0x23d680 (slot 18),
setPassable 0x23d7ac (slot 19), runStateActions 0x23d890.
NAMING ERROR in the symbol files: 0x23cea0, 0x23ceb8, 0x23cf0c, 0x23d014, 0x23d1b0, 0x23d1fc,
0x23d2ec, 0x23d680, 0x23d7ac are called `AutoPropLP_*` but they are the AutoProp members
(vtab.py: all sit in table 0x5133c0; slots 2, 3, 8, 9, 13, 14 are shared with 12 other classes,
slots 17 / 18 with 10, slot 19 with 8).

**Slots 17 / 18 / 19 in this family (first pass: Unknown)**
- slot 17 = "advance to the next state" (no argument). Called by takeDamage, interact and
  trigger of the class itself.
- slot 18 = "set state n" (argument n): the entry used by script built-in `autoPropSetState`
  (0x142320: for up to 100 objects of the given name that carry flag 0x10000000, calls slot 18
  with the state), by the `StartState` property and by load.
- slot 19 = "set passable (bool)": makes the object non-solid (flag 0x1) and, for an AutoDoor,
  switches the level's moving piece. Called with (current state's flags & 1).
- slot 3 (script `trigger(name, arg)`, 0x142264) = advance one state when `Triggerable`.
For AddParticle the same slot numbers mean something else (section 9).

Constructor: AutoObject_ctor; flag 0x10000000 (the "is an auto prop" bit the two script
built-ins test); state +0x178 = 0; obj_runEvery60.

| key | type | lands in | meaning | address |
|---|---|---|---|---|
| `Breakable` | int | +0x11c mask 4 | damage advances the state; meshes that disappear fly off as debris | l.34 |
| `Crumble` | int | +0x11c mask 8 | damage advances the state; debris uses launch flags 0x1020e and a dust effect | l.38 |
| `Pokeable` | int | +0x11c mask 0x10, object flag 0x100000 | can be used by a player (prompt + interact) | l.42 |
| `Triggerable` | int | +0x11c mask 0x40 | slot 3 advances the state | l.47 |
| `LoopingState` | int | +0x11c mask 0x80 | advancing past the last state wraps to state 0 | l.51 |
| `RemoveChunks` | int | +0x11c mask 0x100 | adds 0x100 to the debris launch flags | l.55 |
| `States` | int n | +0x120 | number of states; animations `<name>0.anm` .. `<name>n.anm` (n+1 files) -> +0x128 + 8i. 0 = one animation `<name>.anm` in slot 0 | l.59 |
| `Passable` | string of 0/1, one char per state, max 10 | state flags (+0x12c + 8i) mask 1 | object is passable in that state | l.80 |
| `NoMessage` | same | state flags mask 4 | no prompt in that state | l.94 |
| `ActionAtEnd` | same | state flags mask 8 | the state's actions run when its animation ends instead of at once | l.110 |
| `LoopingAnimation` | same | state flags mask 2 | the state's animation loops | l.126 |
| `AutoDoor` | int | +0x11c mask 1 | binds the nearest moving level piece (world_findMovingPiece -> +0x18c, height -> +0x190), collision on; with `States` absent: 2 states, the animation moves to state 1 and state 1 is passable | l.145, 167-183 |
| `DoubleSided` | int | - | read and discarded | l.168 |
| `AutoSwitch` | int | +0x11c mask 2 | with `States` absent: 2 states, the animation moves to state 1 | l.147-163 |
| `StartState` | int | via slot 18 | initial state | l.198 |
| `action<n>` | str, repeated | - | scripts run on entering state n (0x23d890) | 0x23d890 |
| `key` | str, repeated | - | predicate scripts for the prompt | prompt l.18 |
| `message` / `message<n>` | str | - | prompt text id (general / per state) | prompt l.20-34 |
| `lockMessage` | str | - | text id while a key fails | prompt l.40 |

Other fields: +0x118 active (obj_updateActive result), +0x124 "piston out" (pipepistona only),
+0x17c frames spent active in the current state, +0x180 64-bit "states reached" bits (bit n
set when state n was entered) from which the mesh mask +0xc8 is rebuilt
(model_buildHideMask), +0xd8 / +0xf8 the model and texture FILE NAMES used for debris.
State flags mask 0x10 = "actions of this state already run".
A plain prop (neither door nor switch) with an animation plays it looping from a random start
time (anim_randomizeTopTime, COSMETIC seed) except type `shards`; doors and switches with an
explicit state-0 animation start at its end. Type `laundry` gets cull radius 0xa8. Type
`pipepistona` patches four event markers into its animation data (0.25 -> kind 1, 1.0 -> kind
2, 1.85 -> kind 1, 2.6 -> kind 2; Inferred: a marker of kind k raises event mask k).

State machine (state index +0x178, saved):
- nextState 0x23d2ec: state 0 first marks bit 0. If state < States-1: state+1, counter 0, bit
  set, that state's "done" bit cleared; else with LoopingState: state 0. Mesh mask rebuilt. On
  a change: unless the new state is ActionAtEnd, runStateActions + setPassable(state flags & 1).
  `Breakable`: for every mesh bit present in the old mask and absent from the new one (bit 36
  skipped for type `hateicon`) a 0x248-byte PhProp of that single mesh is created (launch flags
  0x22e, or 0x1020e with Crumble, +0x100 with RemoveChunks); Crumble also fx_spawn(2, or 0x11
  when level flag word 0x44fe08 has 0x100) at the piece. The new state's animation is pushed
  (looping 3 / once 6) and the status bit 0x80 cleared. Always obj_runEveryFrame. Type
  `dt_brazier` plays a sound.
- setState(n) 0x23d680 (n < States, otherwise ignored): state = n, bits 0..n set (none for 0),
  mask rebuilt, the state's animation pushed AND jumped to its end, counter = animation length
  + 1, setPassable. It runs NO action script, does not touch the "done" bits and does not move
  the object to the every-frame list.
- takeDamage 0x23cf0c (amount and attacker ignored): when States != 0 and Breakable or
  Crumble: nextState + impact sounds. Any hit of any size advances one state.
- interact 0x23d1b0: Pokeable and States != 0 -> nextState. No key test here.
- trigger 0x23d1fc: Triggerable and States != 0 -> nextState (+ a sound for `gothtrap` on
  reaching state 1 and for `fayactuator`). The argument is ignored.
- run 0x23cb54: (1) if the top animation has ended (status 0x80) and the current state is
  ActionAtEnd and not done: runStateActions, setPassable(state flags & 1). (2) obj_updateActive(this, +0x118,
  cull radius + 480; 1000 in the front end) -> +0x118; that call also moves the object
  between the every-frame and the every-60 list. (3) inactive: a non-looping animation is
  snapped to its end. (4) active: animation advanced (events -> +0xc0), counter +0x17c + 1.
  (5) type prefix `pipepistona`, active only: animation event mask 1 sets +0x124, mask 2 clears it; while
  set, every living player within 18 units of the point 48 units ahead of the prop takes
  damage_apply(level x 0.3, level x 0.3, player, this, attack 10000, flags 0x41), gets +0x2e8 =
  100 and +0x2e0 = facing + 0x4000 or + 0xc000 by the side he stands on (knock-aside).
- runStateActions 0x23d890: sets the done bit, then runs every `action<state>` property with
  g_scriptSelectedObj (0x4039f8) = this.
- setPassable 0x23d7ac(on): on -> door piece collision off and the piece moved to offset
  (0,0,-256), object flag 0x1 set; off -> collision on, piece back to (0,0,0), flag cleared.
- save/load: 4 bytes, the state. load stores it and calls slot 18 with it (0x23ceb8), i.e.
  the saved state is re-entered silently (no actions, animation at its end).

Scripts: `autoPropSetState` has 62 call sites in 13 scripts (doors, portals, braziers:
BLOOD1, DIS2, DRUNARE, DRUNDAR, FAY3, HUB, HUB2, TORMENTA/B, VALOR, BOSSEVIL/GOOD, DISEASE0);
`autoPropGetState` (0x1423e0, returns +0x178) has none; `trigger` reaches slot 3
(e.g. 'portal', 'bridgeN', 'shardshell', 'cartN'). In the four extracted levels the
objects of this family carry lower-case keys (`autoprop`, `autochest`, `autocontainer` with
`lumpname`), and the `arenadoor` objects carry `autodoor`, `triggerable`, `states`, `passable`
and `loopingstate` - but the factory matches the type name Arenadoor first, giving HackDoor.

Per-machine:
(a) run: obj_updateActive at 0x23cc0c - the known camera-focus hazard (objects.md O4) decides
activity, and here activity gates: the animation advance, the frame counter +0x17c, when an
ActionAtEnd script fires (the animation must reach its end by being advanced), the snap-to-end,
and the piston damage. Nothing else per-machine in run / nextState / setState / trigger /
takeDamage (scan and reading); fx_spawn in nextState is cosmetic and the debris is created
regardless of it.
NEW: the piston. A plain AutoProp's looping animation starts at a COSMETIC-seed time
(0x23c44c l.151-154 -> anim_randomizeTopTime; engine.md P4 lists the call). For type
`pipepistona` the damage window +0x124 is driven by that animation's event bits (run l.62-69),
so the frames on which the piston hurts and shoves players can differ between machines when
the instance is neither AutoDoor nor AutoSwitch. Limiting factor (Observed, run l.38-42): on
every run call made while the prop is INACTIVE, a state without the LoopingAnimation mask has
its top track snapped to its end, which erases the random phase; from then on the phase is
counted from the frame the prop becomes active. So the difference survives only for a piston
that is already active on its first run call (a player within cull radius + 480 from the
start) or whose state 0 is marked LoopingAnimation. Observed in code; whether a shipped level
places such an instance was not checked (no level containing one is extracted).
(b)/(c) draw is AutoObject_draw (section 1).
(d) prompt 0x23d014: needs Pokeable and a state without NoMessage; runs every `key` script
(script_runByName at 0x23d068), then copies a text; no object field is written. Same
display-rate caveat as the chest prompt.

### 4. AutoPropLP (AutoProp + LP test, or type names Antlighta/b/c; vtable 0x5130c0; 0x448)

Functions: ctor 0x2416c4, dtor 0x241e84, draw 0x241ee4, run 0x2421e0. Subclasses: EggSack,
RingPortal, DiseasePort.

Constructor: AutoProp_ctor, then up to four AddParticle helpers (0x184 each, index i = 0..3,
made only when `ParticleEmitter<i>`, `DynamicLight<i>` or `Halo<i>` is non-zero) at +0x198 +
4i, copied again to +0x1a8 + 4i. Per helper i:

| key | type | lands in | meaning |
|---|---|---|---|
| `Shadowballemitter<i>` | present | +0x1b8 + 4i mask 1; also object +0xd0 mask 1 (no shadow pass) | particles are emitted from every sample point of the model instead of attach point i |
| `Particle<i>` | string of 0/1 per state | table +0x1c8 + 8(10i + s): {on, off} | emitter on ('1' -> on 0, off -1) or off ('0' -> on -1, off 0) in state s |
| `Particle<i>State<s>on` | int | on (1 is stored as 0) | frame of the state at which emission starts |
| `Particle<i>State<s>off` | int | off | frame of the state at which it stops |
| `Light<i>`, `Light<i>State<s>on`, `Light<i>State<s>off` | same | table +0x308 + 8(10i + s) | same scheme for the helper's light / halo |

No `Particle*` key at all for helper i -> on in every state (on 0, off -1); same for lights.
"On" test used by both run and draw: (on == 0 or on < counter) and (off == -1 or (on < counter
and counter < off)), counter = +0x17c, state = +0x178. Type prefix `lamp` or `antlight` sets
helper +0x17c = 30 (first argument of the halo sprite, default 100). All helper lights start
unlinked.

run 0x2421e0: AutoProp_run; then only while active (+0x118): for each helper evaluate the two
windows -> emitter start (0x240cf4(h, 0)) / stop (0x240d24), light on (0x240d2c) / off
(0x240d6c); then the helper's slot 18 at attach point i of the model (facing - 0x4001, current
pose), or - Shadowballemitter - once per model sample point with mode 1 (first), 2, 3 (last).
The per-helper flag mask 2 (pass the attach direction) is never set by this constructor.

draw 0x241ee4: for each helper the SAME two window tests and the SAME four helper calls, then
helper slot 17 at the attach point (for a Shadowballemitter helper slot 17 is called with a
position buffer the function never fills - stale stack data; cosmetic), then AutoObject_draw.

Per-machine:
(a) run: as AutoProp.
(b) the draw stores (1) into the HELPERS: emit-enabled +0x5c / one-shot +0x60 and light-on
+0xfc (and links / unlinks the light). They are recomputed from the run-owned state and counter
with the identical expression, so the draw writes the value the run would write; the only
difference is that the run does it only while active and the draw whenever the object is
drawn. The helper fields feed particle emission (cosmetic seed) and lighting only. (2) the
object flag word: `flags |= 0x100` (store at 0x2421ac), reachable only when 0x240db0(helper) returns
non-zero for one of the four helpers; that function is the constant 0, so the store and the
g_drawFrame test (bit 0x40) in front of it are dead. Same answer as the chest: no influence
on whether the object runs, animates, collides, deals damage or reports to scripts.
(c) helper slot 17 from the draw can draw from the helper's own generator (section 9). No
object creation, run-list change, script or world query in the draw.

### 5. The LP draw flag store (first-pass open row) - summary

All three simple LP draws have the same tail (dis 0x241568-0x241604 read in full; decompile of
0x24268c and 0x241ee4): `if (helper && 0x240db0(helper) && (g_drawFrame & 0x40)) flags |=
0x100; AutoObject_draw()`. 0x240db0 is a two-instruction function returning 0 (dis). Therefore:
the bit is 0x100 (hit flash); the stores (0x2415e8, 0x2421ac, 0x24270c) never execute; the
g_drawFrame read sits behind the dead test (in AutoEmitter_draw, section 10, it is read first
but everything after it needs 0x240db0 != 0); AutoObject_draw merely clears 0x100 again. No run function, trigger, damage, save or load of the family reads
0x100. Inferred: 0x240db0 is a compiled-out "is selected / highlight" query (editor or debug
blink, 64 frames on / 64 off).

### 6. AutoContainer (property `AutoContainer`; vtable 0x513330; 0x148) and AutoContainerLP (0x513030; 0x150)

Functions: ctor 0x23d93c, dtor 0x23e0e8, load 0x23e1b8, save 0x23e220, prompt 0x23e238,
interact 0x23e280, trigger 0x23e2ec (slot 3), onTouch 0x23e358 (slot 6), run 0x23e430,
takeDamage 0x23fa60. LP: ctor 0x24259c, dtor 0x24262c, draw 0x24268c, run 0x242728.
No slot 17-19 (the table ends at slot 16).

Constructor: AutoObject_ctor; object flag 0x10 (standable top); not on a run list.

| key | type | lands in | meaning | address |
|---|---|---|---|---|
| (none) | | +0xd8 / +0xdc, names at +0xe0 / +0x100 | debris model `<name>_explode.vif` / `.tex` from the object's archive | l.45-53 |
| `Breakable` | int | +0x124 mask 1 | any damage breaks it | l.54 |
| `Explodeable` | int k | +0x124 mask 4; +0x139 = k (default 1); object flag 0x100000 | can be ignited by a player; k scales the blast | l.58-66 |
| `NoChainReaction` | int | absent/0 -> +0x124 mask 0x800 | with the mask set, explosion damage (damage flag 0x800) sets it off | l.61 |
| `Immovable` | int | +0x124 mask 8 | cannot be pushed, is not moved by run | l.68 |
| `Sound` | str | +0x120: `barrel` 0, `pot` 1, `crate` / `basket` 2 | break sound; then overridden by 30 type-name prefixes (weaprack, smalcrat, boxafay, boxbfay, lavakeg, hatebox, uncrate, cratei -> 0; vaseweb, hgurn, goyle, crispy01-03, gothpot1-2, ap_barrel, dt_pota/b -> 1; boxcfay, baskcold, greenpot, kelbask1-2, gothpic1-6 -> 2) | l.73-218 |
| `extraLength` | int | +0x140 / +0x144 | two extra Blocker objects (0x4c, radius 36, flag 0x4000) 50 units ahead and 40 behind along facing + 0x4000; deleted with the container | l.236-284 |
| `action` | str, repeated | - | obj_runActionScripts(this, 1) when ignited and when hit | interact, takeDamage |
| `spawncreep` | any | - | breaking creates a `creep` object and nothing else | run l.281 |
| `item` | str, repeated | - | breaking drops exactly these named items | run l.289 |
| `reduceCarnage` | int | - | on explosion each debris piece is skipped when an own draw is even | run l.650-658 |

Fields: +0x124 flags (masks 0x200 and 0x400 are tested in run - debris step 1 instead of 2 /
effect id 8 instead of 2 - but no function of the family sets them; script built-in
`setContainerProps` (0x14799c) writes only mask 8); +0x128 / +0x12c horizontal velocity; +0x130
fuse frames; +0x134 fuse sound handle; +0x138 "in water"; +0x139 blast factor; +0x13c state.

States (+0x13c, the only saved field): 0 intact, 3 just ignited, 2 fuse burning, 1 break /
explode on the next run, 4 broken remains.
- onTouch(other) 0x23e358: other is a player (flag 0x40) with +0x47c == 0, container not
  Immovable: unless the container already moves faster than 52 along the player's velocity
  direction (player +0x4bc / +0x4c0), velocity += player velocity x 0.52; obj_runEveryFrame.
- interact 0x23e280 and trigger 0x23e2ec (identical bodies; argument ignored): Explodeable
  only: clears 0x100000; if state 0: state 3, every-frame list, fuse 180, action scripts.
- takeDamage(amount, attacker, flags) 0x23fa60: unless state 1 or 4: Breakable, or (Explodeable
  and damage flag 0x800 and container mask 0x800) -> action scripts, every-frame list, fuse 0,
  state 1. The amount is ignored. (dis 0x23faa0: the tested register is the third integer
  argument, the damage flags.) The explosions of this family call world_damageInRadius with
  type 0x40800 (container) and 0x40840 (trapped chest), both containing 0x800;
  world_damageInRadius hands that word to damage_apply as its flags (Observed, 0x161270 call
  to 0x1e8230). That damage_apply forwards the flags to slot 2 is taken from gameplay.md 2.4,
  not re-read: so one explosion sets off the next container.
- prompt 0x23e238: Explodeable -> text id Ignite; always returns 1. No script, no store.
- run 0x23e430, each frame on the list:
  1. state 4 -> return (the remains stay on the list doing nothing).
  2. not Immovable: obj_moveWithCollision(this, velocity, 0, 0).
  3. water: not in water -> every 8th frame (g_simFrame & 7) water_test(12); on entering: flag
     set, ONE OWN DRAW whose value is discarded, splash sound, water_disturb(1000, 24). In
     water -> when moving, water_disturb(300, 12), else water_test; a zero result clears the
     flag.
  4. velocity x 0.86. State 0: leaves the run list once speed^2 < 0.01.
  5. not Explodeable, Breakable, state 1 = BREAK: sound by +0x120; six fx_spawn(2 or 8) (twelve
     fx_spawn(0x11) when level flag word 0x44fe08 has 0x100) at positions from three own draws
     each; one 0x248-byte PhProp per debris mesh (every second mesh unless mask 0x200; launch
     flags 0x20e); state 4; object flags = 0x4003 (assigned: non-solid, undrawn, never saved).
     Loot, in this order: `spawncreep` -> creep, stop. `item` list -> those items, stop.
     Otherwise: own draw < 24000 -> a Gold object (0xc0) worth (own draw & 3) x
     level_monsterLevelTimes0_4() + 1; own draw < 9000 -> a drop, repeated n times where n comes
     from one own draw r (r < 63000: 1; r < 0xffdc: 2; else 3) and the kind from ONE further
     own draw shared by all repeats (< 10000 `arrows`; < 20000 item_generateConsumable; else
     four loot_generateDrops(36, 2, 0, 0, row, chance) with (1.5, 1), (2.5, 0.01), (3.5, 0.001),
     (4.5, 0.0001)); finally own draw / 65536 <= 0.015 -> a throwable potion: own draw < 0.33
     `firepotion`, < 0.66 `explodingpotion`, else `gaspotion`, with item-record word +4 = (own draw
     & 3) + 3 (Inferred: the stack count).
  6. Explodeable, fuse > 0: at 180 the fuse sound starts; state 2; fuse - 1; at 0:
     camera_shake(10) and state 1. Two fuse particles per frame from own draws.
  7. Explodeable, fuse <= 0, state 1 = EXPLODE: sounds, fx_ringBurst, damage base = (max(act,
     0) x 4 + 4) x 15, or 4 on level `cellar1`, x 3 on difficulty index 2, x 6 on index 3;
     world_damageInRadius(inner 40 x k, outer cull radius x 3 x k, attacker = the container,
     pos, base x k, type 0x40800); decal (angle own draw); LightEffect (0xbc); debris: every
     mesh of the debris model as a PhProp (launch flags 0x216), each skipped on an even own draw
     when `reduceCarnage`, and on (own draw & 7) == 0 the piece gets its byte +0x23a = 1
     (0x155108; meaning not read); fuse sound stopped; the object destroys itself at once
     through slot 1 (argument 3), not through obj_delete.
  A container that is both Breakable and Explodeable takes path 7 (the Explodeable test comes
  first), so any hit makes it explode.
- load: state; state 2 restarts a full 180-frame fuse (clears 0x100000, every-frame list).
  Broken remains carry flag 0x4000 and are not written.

Script-driven: `setContainerProps(name, 1, v)`: v == 0 sets Immovable, otherwise clears it -
only for objects whose dynamic type is EXACTLY AutoContainer (rtti_typeInfoEquals call at 0x147a18), so
AutoContainerLP objects are skipped. Used by WATG2A/B/C on 'rockplug'. `trigger(name, x)`
ignites.

AutoContainerLP: ctor adds one AddParticle (unindexed keys) at +0x148; run = helper slot 18
(pos, 0, 0) then AutoContainer_run; draw = helper slot 17 then the dead flag store (section 5)
then AutoObject_draw. The helper is never started (no call to 0x240cf4 / 0x240d2c for this
class), so with the code as read it emits nothing and shows only the static light linked by
its constructor.

Per-machine:
(a) run / takeDamage / onTouch / trigger: no camera, local slot, audio or cosmetic-seed read
for a decision (scan and reading). fx_spawn positions are drawn from the own generator BEFORE
the camera gate inside fx_spawn, so the draw count is the same everywhere. One inherited item:
water_disturb's return value (engine.md P14: forced to 0 while g_cutSkip) decides the
"in water" flag here (run step 3), and re-entering water costs one own draw - so a difference
in that return would shift this container's later loot rolls. pool_new failure skips the
second gold draw (run l.347-348) - the usual pool-occupancy dependence (objects.md O1).
(b)/(c) plain draw as section 1; LP draw as section 5.
(d) prompt: no script, no state change.

### 7. CreatureContainer (property `CreatureContainer`; vtable 0x513780; 0x3d0; Creature-derived)

Functions: ctor 0x243624, dtor 0x243770, run 0x2437ec, setState 0x24386c (slot 27). Every
other slot is the Creature base (vtab.py), including draw = the empty base stub 0x3c7ea0.

Constructor: Creature_ctor(max-hp argument 1.0, this, typeName, pos, angle, class def 0,
props); then creates a PLAIN AutoContainer (pool 0x148, ctor 0x23d93c, same type name,
position, angle and property list - never the LP variant) and keeps a handle to it at +0x3c8;
radius = container radius + 5; creature flags |= 0x4000010000; object flags: 0x8 cleared,
0x40003 set (non-solid, undrawn, and the bit the object sweep 0x18b014 tests);
Creature_setCharm(this, -1, 0); obj_runEvery60; Creature_init. Inferred, not tested: an
`initScript` property runs twice for such an object - once in the embedded container's
AutoObject_ctor (read) and once in Creature_init (per its symbol note; not re-read).
run: handle empty (container destroyed, i.e. it exploded) -> obj_delete(self); else copy the
container's position and relink the grid cell. Then Creature_processDamage(this, 0),
Creature_run(this, 0), Creature_updateActive(this) with results unused.
setState(n): only n == 0x14 while the container exists stores the state; everything else is
ignored - the object has no AI.
Inferred purpose: a creature-shaped stand-in so that code which only considers creatures
(targeting) can pick a container. The class has no code that passes damage on to the
container; the container is hit itself because it is the solid object. A broken (not
exploded) container keeps its handle alive, so the stand-in then stays for the rest of the
level.
Per-machine: nothing beyond the common creature calls.

### 8. Generator leftovers (0x265754-0x266088)

#### Generator  (type `AntMaker`, or any object with a string property `Generator`; vtable 0x510638; 1000 bytes; Creature-derived)

Functions: ctor 0x2657a0, draw 0x265930 (empty), run 0x265938, trigger 0x265e08 (slot 3),
save 0x265ea0, load 0x265ec4, setState 0x265ee8.
Constructor: Creature_ctor(max-hp argument 8.0, no type name, no class def); radius 20, cull
radius 20; state 0; creature flag 0x4000000; object flags |= 9 (non-solid, 0x8);
Creature_setStats(1,1,1,1,1,this,1); obj_runEvery60.

| key | type | lands in | meaning | address |
|---|---|---|---|---|
| `generator` | str | +0x3c8 (pointer to the property text) | factory type name of what it makes | l.26 |
| `triggerable` | int | +0x3dc mask 1 | makes one object per slot-3 call; never wakes by sight unless mask 2 is also set | l.28 |
| `radiustrigger` | int | +0x3dc mask 2 | also wakes on the box test (set automatically when `generator` is `ant`) | l.32, l.46 |

Other fields: +0x3d4 = 4 maximum made, +0x3d8 number made (saved), +0x3e0 handle of the last
creature made, +0x3cc = 600 and +0x3d0 = creature clock at construction (neither is read by
run, trigger, save or setState - Unknown purpose).
run 0x265938 (skimmed against the first pass - it is right): returns when Creature_run is
non-zero or Creature_updateActive is zero. State 0: mask 2 clear and mask 1 set -> nothing;
mask 2 clear and mask 1 clear -> a 500-unit ray ahead from 10 units up (world_raycast) that
hits a player -> setState 3; mask 2 set -> the same ray, and on frames where ((g_simFrame ^
byte +0x230) & 7) == 0 any living player in the 400-unit box centred 200 ahead -> setState 3.
State 3: nothing while the last creature made is alive or +0x3d8 >= +0x3d4; otherwise
world_createObject(type, pos, facing); a creature result gets its name pointer +0x34, creature
flag 0x1000000 and is linked at +0x3e0; the count rises even when creation failed.
trigger 0x265e08 (script `trigger(name, x)`): with mask 1 it creates one object of the type at
once - no count, no limit, no handle, no state test - and writes +0x34 and creature flag
0x1000000 into it WITHOUT testing that the result is a creature (dis 0x265e68-0x265e7c); then
Creature_trigger(this, x) (the base behaviour: dialogScript).
setState 0x265ee8: Creature_filterState, then requests for 5, 0x12, 0x13 and 0x14 are replaced
by the current state (it cannot be rooted, hit-reacted, stunned or killed through slot 27);
anything else is stored. No animation, no timers.
save / load: 8 bytes = state, number made.
Per-machine: nothing beyond the common creature calls; no draw code.

#### ScriptGenerator  (type `ScriptGenerator`; vtable 0x514e60; 0x4c)

Functions: ctor 0x265f54, spawn 0x265fc4 (not virtual; one caller, script built-in
`generateMonster` 0x1473d4, 136 call sites in 11 scripts). Every virtual slot is a GameObject
stub (vtab.py): it never runs or draws. Ctor: facing stored, flags |= 9. It reads no property.
spawn(this, typeName): world_createObject(typeName, pos, facing - 0x4000, the generator's own
property list); the new object gets +0x34 = name and creature flag 0x1000000 (again without a
creature test); if its dynamic type is exactly Skeleton, slot 27 with state 0x17.

### 9. AddParticle - the light / particle / halo helper (vtable 0x513288; 0x184)

Functions: ctor 0x23fae0 (unindexed keys), ctor2 0x23fc50 (keys with index suffix n),
readEmitterProps 0x23fdc0, readLightProps 0x24045c, slot 17 0x240800, slot 18 0x240b64, slot 19
0x240da8 (empty), startEmitter 0x240cf4, stopEmitter 0x240d24, lightOn 0x240d2c, lightOff
0x240d6c, 0x240db0 (returns 0). Slots 4 and 5 are the GameObject stubs: it never runs or draws
itself; flags |= 0x400f (never saved, non-solid, undrawn). Created only by owners
(AutoChestLP, AutoContainerLP: one, unindexed; AutoPropLP, AutoEmitter: up to four, indexed).

Meaning of its slots (different from AutoProp's):
- slot 17 (pos) = place and refresh the dynamic light and the halo. Called from the owners'
  DRAW functions.
- slot 18 (pos, direction or 0, mode) = emit this frame's particles. Called from the owners'
  RUN functions.
- slot 19 = empty.

Properties (all int; `<n>` = "" for ctor, the index for ctor2; key text = stem + n):

| key | lands in | meaning (I = inferred from use in 0x18f118 / 0x195400) |
|---|---|---|
| `ParticleEmitter<n>` | +0x50 = 1 | has an emitter; the keys below are read only then |
| `psr` `psg` `psb` `psa` | +0x64..+0x67 | particle start colour and alpha (arguments 5-8 of the definition builder 0x18f118) |
| `per` `peg` `peb` `pea` | +0x68..+0x6b | end colour (`pea` is stored but not passed on) |
| `pss` `pes` | +0x6c, +0x6e (s16) | start / end size (float arguments 1, 2) |
| `pgr` | +0x70 (s16) | third float of the definition (I: vertical acceleration) |
| `plf` `prm` `ptx` | +0x72, +0x73, +0x74 | stored; no reader found (see Open) |
| `bcn` | +0x75 (s8) | burst count per call; negative = one burst every abs(n) frames |
| `bxo` `byo` `bzo` | +0x76, +0x78, +0x7a | emitter offset (x, y turned by the yaw; z) |
| `bvx` `bvy` `bvz` | +0x7c, +0x7e, +0x80 | base velocity |
| `byw` `bpt` | +0x82, +0x84 | yaw and pitch of the emitter frame |
| `box` `boy` `boz` | +0x86, +0x88, +0x8a | random box size |
| `bvr` | +0x8c | random velocity spread |
| `bar` | +0x8e | random cone angle |
| `bot` `bft` | +0x90, +0x94 | on time / off time of the burst cycle, frames |
| `bwa` `bfa` | +0x98 mask 1 / mask 2 | `bwa`: velocity turned by the global angle 0x4f66a0 and the particle is made only while global 0x4f66a4 is non-zero (both unnamed; I: wind / weather); `bfa`: velocity turned by the emitter's own yaw and pitch only, ignoring the caller's direction (0x195400 l.174-205) |
| `DynamicLight<n>` | +0x54 = 1 | has a light |
| `lsrad` `lerad` | +0x144, +0x148 | radius A and B, each clamped to 0..300 |
| `lrc` | +0x14c | radius mode: 0 fixed A; 1 a new random radius between A and B every `lrt` frames; 2 ramp between A and B; 3 toggle A / B |
| `lrt` | +0x150 | period in frames |
| `lsr` `lsg` `lsb` `lsa` | +0x154..+0x160 | light colour |
| `Halo<n>` | +0x58 = 1 | has a halo sprite |
| `hlr` `hlg` `hlb` `hla` | +0x164..+0x170 | halo colour |
| `hls` `hlf` | +0x174, +0x178 | halo size and flicker shift |

Fields: +0x4c index (-1 = unindexed), +0x5c emitter enabled, +0x60 one-shot, +0x64 emitter
record (0x40 bytes; +0x9c next on/off switch frame, +0xa0 "on"), +0xac particle definition,
+0xfc light / halo enabled, +0x100 light node (position +0x130), +0x13c next radius change
frame, +0x140 ramp direction, +0x17c first glow argument (100; 30 for lamp / antlight owners),
+0x180 emission frame index.
startEmitter(h, oneShot): enabled = 1, one-shot = arg; a one-shot also forces the record "on"
and schedules its end at frame + `bot`. slot 18: needs emitter and enabled; frame index =
g_simFrame (mode 0), an own draw % abs(bcn) (mode 1 with negative bcn), else previous + 1;
calls the burst function 0x195400 (every random number in it is the COSMETIC seed), with a
direction argument the pitch is temporarily turned toward it; a finished one-shot disables
itself (modes 0 and 3).
slot 17: light: radius by mode (mode 1 takes one draw from the helper's OWN generator when its
timer, counted in simulation frames, has run out; mode 2 adds one ramp step per CALL), clamp
0..299, light node rewritten and linked. Halo: glow_add with a size wobble from math_noise
indexed by the object's address and g_simFrame.

Per-machine: slot 17 runs from draw code and (a) advances the helper's own generator (mode 1),
(b) advances the mode-2 ramp once per draw call, (c) writes the helper's light node and timer.
The same generator feeds slot 18's burst phase (mode 1 with negative `bcn`). So a helper's
generator and its +0x13c / +0x140 / +0x180 are NOT the same on all machines. Everything they
feed is lighting, sprites and cosmetic-seed particles; no owner reads them for a decision
except RingPortal_run, which reads helper +0xfc (section 11). The helper is a separate object
with its own generator, so the owner's generator is untouched. The helpers carry flag 0x4000
and have no save slots. Not checked: whether any consistency hash covers per-object seeds.

### 10. AutoEmitter (property `AutoEmitter`; vtable 0x5131f8; 0x60; derives from GameObject, not AutoObject)

Functions: ctor 0x240dc8, draw 0x2410f0, run 0x241310. Fields: +0x4c..+0x58 four AddParticle
helpers (indexed keys 0..3, section 9), +0x5c active.
Ctor: each helper that exists is started for good (startEmitter(h, 0) when it has an emitter,
lightOn when it has a light or halo); properties `drawradius`, `drawheight` (cull bytes
+0x28 / +0x29, max 255); obj_runEvery60.
run: obj_updateActive(this, +0x5c, cull radius + 480) -> +0x5c (and list change); while active,
helper slot 18 (position, 0, 0) for each helper.
draw: helper slot 17 (position) for each helper. The rest - a pulsing marker sprite sized and
turned by g_drawFrame - needs (g_drawFrame & 0x40) AND 0x240db0(helper) != 0, i.e. never.
No trigger, damage, touch, interact, save or state: it cannot be switched by scripts.
Per-machine: (a) obj_updateActive only (known item); what it gates is cosmetic. (b) no store
into the object. (c) helper slot 17 as section 9.

### 11. Fixed-purpose subclasses

All are AutoProp or AutoPropLP with the table entries listed; everything not listed is
inherited, in particular takeDamage 0x23cf0c, trigger 0x23d1fc, prompt 0x23d014, interact
0x23d1b0, save / load, so every AutoProp property of section 3 works on them (Observed: their
constructors pass the property list to AutoProp_ctor). None reads a property of its own.

#### AntTrap  (type `AntTrapa`; vtable 0x513d60; 0x1a0)  ctor 0x24290c, run 0x2429d8

Ctor: AutoProp_ctor; flag 0x1; +0x198 = animation `anttrapa.anm` from its archive; when found
the animation state is replaced by that track at its end with the "finished" status set, and
an event marker (time 1.0, kind 1) is patched into the animation data.
run: AutoProp_run; then (1) on the frame the animation raises event mask 1: every object
without flag 0x8 in the box of half-size radius around the trap - no creature or team test,
so players, monsters and props alike - gets damage_apply(2 x level, 2 x level, obj, trap,
attack 10000, flags 8); (2) on frames with g_simFrame % 30 == 0 while the animation is finished:
for each living creature (flag 0x20) in the same box the snap animation is started
(anim_start 0.1 s blend, flags 6) - once per creature found. The damage loop has no test that
skips the trap itself.
Per-machine: activity (obj_updateActive inside AutoProp_run) gates the animation advance and
therefore the snap event; no other item.

#### EggSack  (type `EggSac`; vtable 0x513cb8; 0x448)  ctor 0x242bd8

AutoPropLP whose four per-helper flag words (+0x1b8..) are set to 2 = "pass the attach
direction to the emitter" and whose state-2 flags get mask 2 (looping animation). Run and draw
are AutoPropLP's.

#### HateInto  (type `HateInto`; vtable 0x513c10; 0x1b8)  ctor 0x242c5c, run 0x242cd0

#### HateGate  (type `HateGate`; vtable 0x513b68; 0x1b8)  ctor 0x242e7c, run 0x242edc

AutoProp with draw flag mask 1 (no shadow pass). HateInto also restarts its state-0 animation
looping from time 0 (so no cosmetic-seed phase). run: AutoProp_run, then one particle at
every 2nd (HateInto, parity = frame & 1, definition 0x8e3058) or every 8th (HateGate, phase =
frame & 7, definition 0x8e30a8) model sample point, each offset by three own draws. This part
runs on every run call, active or not; own draws are used for nothing else.

#### GothTrap  (type `GothTrap`; vtable 0x513ac0; 0x1a0)  ctor 0x243088, run 0x2430fc (EMPTY), setPassable 0x243104

Ctor: AutoProp_ctor, flag 0x1, obj_runEveryFrame, own slot 19. Slot 19 (argument ignored):
piece collision ON, then by state: 0 -> piece at offset 0 and height = stored height +0x190;
1 -> piece moved down 350 and height - 350; 2 -> piece moved down 350 and height + 256.
Because run is empty, AutoProp_run never executes for it: no animation advance, no
ActionAtEnd, no activity test. Slot 19 is reached only from nextState / setState.

#### HateHole  (type `HateHole`; vtable 0x513a18; 0x1a0)  ctor 0x24323c, run 0x2432c0, setPassable 0x2432dc

Ctor: flag 0x1, +0x198 = piece height, obj_runEveryFrame. run = AutoProp_run. Slot 19
(argument ignored): state 1 -> piece down 350, height - 350; state 2 -> height + 256 (piece
not moved); state 0 -> nothing.

#### HateBridge  (type `HateBrdg`; vtable 0x513970; 0x1a0)  ctor 0x243398, run 0x243414, setPassable 0x24348c

Ctor: flag 0x1, own slot 19, obj_runEveryFrame, cull radius 0xb0. Slot 19: collision on;
state 0 -> piece at 0, stored height; 1 -> piece down 350, height - 350; 2 -> height + 256.
run: AutoProp_run, then a second obj_updateActive(this, +0x118, 1000); on the change from the
value +0x118 had before AutoProp_run: became active -> obj_addToAlwaysDraw(this); became
inactive -> world_clearAlwaysDraw(), which empties the WHOLE always-draw list (every member
loses flag 0x2), not just this object.

#### HackDoor  (type `Arenadoor`; vtable 0x5138c8; 0x198)  ctor 0x243594, setPassable 0x2435f4

AutoProp with flag 0x1; slot 19 = AutoProp's, then flag 0x1 set again: the object itself is
never solid, only the level piece blocks (collision on / off and the 256 drop). Run is
AutoProp_run. With the level data seen (autodoor, triggerable, 2 states, loopingstate) it is
driven by `autoPropSetState(name, 1)` and `trigger`.

#### GothTrap / HateHole / HateBridge / HackDoor caveat

The piece index +0x18c is filled only when the instance has the `AutoDoor` property
(AutoProp_ctor l.167-173); otherwise it stays -1 and the piece calls are made with -1.
Whether the engine functions tolerate -1 was not read.

#### RingPortal  (type `apprings`; vtable 0x5136d8; 0x498)  ctor 0x24388c, dtor 0x2439d4, draw 0x243a44, run 0x243b48, nextState 0x243c10, setState 0x243c70

AutoPropLP plus an inner animated model `apblobs` (.vif / .tex / .anm from its archive) drawn
60 units above the object at scale +0x450. Slots 17 and 18 call the AutoProp versions and
then: state 0 -> inner model off (+0x448 = 0), scale 0.01; state 1 -> inner model on, counter
+0x44c = 180. run: AutoPropLP_run; while on: inner animation advanced; scale < 0.8: grows by
0.005 per frame but ONLY while helper 0 exists and its light is on (helper +0xfc); from 0.8
on: scale = 1 + 0.2 x sin16(counter x 0x400 - 0x4000), counter + 1. draw: AutoPropLP_draw,
then the inner model (shadow pass + model_draw).
Per-machine: (b) run reads helper +0xfc, a field that the draw function also writes (section
4 (b)). The draw writes the value the run would write, but it does so even while the object
is inactive, so the moment growth starts can differ by machine. What depends on it: +0x450 and
+0x44c, which only the draw reads (size of the inner model). They are not saved and no script
built-in reads them. No shared consequence found.

#### DiseasePort  (types `disportGOOD`, `disportEVIL`; vtable 0x513630; 0x448)  ctor 0x243cd0, nextState 0x243d24, setState 0x243e20

AutoPropLP. nextState: when leaving state 0, `disportGOOD` plays two sounds and has the
Breakable mask set just for the duration of the base call (so the meshes that vanish fly off
as debris), then cleared again; `disportEVIL` plays one sound. setState is a plain call of
AutoProp's. Scripts: DIS2 switches eight 'evilportalA..H' objects with autoPropSetState.

#### TormentBridge  (type `ptbridge`; vtable 0x513588; 0x198)  ctor 0x243e3c, run 0x243ea0

AutoProp put on the always-draw list at construction (flag 0x2), obj_runEvery60. run: when
flag 0x2 is clear and isNearView(1200, pos) -> obj_addToAlwaysDrawOnce; then AutoProp_run.
Driven by `trigger('bridgeN', 0)` in TORMENTA / TORMENTB (slot 3 -> next state).
Per-machine: isNearView (camera focus while g_cullByCamera) decides only the always-draw
membership / flag 0x2.

#### Static initialisers

0x242794 (called by the stub 0x2428ec, pointer in the static-constructor table at 0x3e99fc)
builds three particle definitions: 0x8e2f68 and 0x8e2fb8 (the fuse spark and smoke used by
AutoChest_run and AutoContainer_run) and 0x8e3008 (no user found in this range). 0x243ef8
(stub 0x243ff8, table entry 0x3e9a00) builds 0x8e3058 (HateInto) and 0x8e30a8 (HateGate).

### 11b. Which scripts the family runs, and when (summary)

| property | run by | when | context |
|---|---|---|---|
| `initScript` | AutoObject_ctor 0x23a9b0 (script_runByName) | construction of every AutoChest / AutoProp / AutoContainer (and subclasses), unless a cutscene is active | level load / object creation |
| `key` (repeated) | AutoChest prompt 0x23b6e8, AutoProp prompt 0x23d068 | every evaluation of the interact prompt; first zero result stops and shows `lockMessage` | simulation AND draw (script.md P1) |
| `action` (repeated) | obj_runActionScripts(this, 1) - the "raw" form, names used as written | chest: once, when the lid is a third open (0x23b170 l.42); container: on ignite (interact / trigger) and on the hit that breaks or detonates it | simulation |
| `action<n>` (repeated) | AutoProp_runStateActions 0x23d8fc, with g_scriptSelectedObj = the prop | on entering state n through slot 17, or at the end of the state's animation when `ActionAtEnd`; never through slot 18 / autoPropSetState / load | simulation |

Script built-ins that drive the family: `trigger(name, arg)` -> slot 3 (chest: open; prop:
next state when Triggerable; container: ignite; Generator: make one); `autoPropSetState(name,
n)` -> slot 18 on flag-0x10000000 objects; `autoPropGetState(name)` -> +0x178 (unused by the
shipped scripts); `setContainerProps(name, 1, v)` -> Immovable mask of exact AutoContainers;
`generateMonster(generator, class)` -> ScriptGenerator_spawn. No `deathScript` or `script`
property is read by the AutoObject-derived classes (their key strings, 0x541e98-0x5428f0, were
listed in full); CreatureContainer and Generator get the usual creature properties from the
Creature base, which was not re-read.

### 6.2 Doors, switches, lights, bombs and the rest

Written in list form; see the shorthand note in the introduction.

#### WorldPart (table 0x511de8; 0x50 bytes) ctor 0x28a6b0, dtor 0x28a7b4

- A WorldPart is the game object that owns one movable piece of the level geometry. Ctor: GameObject; flags |= 0x100003 (interactable, hidden, bit 0); a `name` property clears 0x100000 (named parts are meant to be driven by scripts); piece index +0x4c (s16) = world_findMovingPiece(g_world, position); collision of the piece switched on (world_setPieceCollision); +0x4e (s16) = piece height; no piece found -> obj_delete.
- Engine calls used by the family: world_movePiece(world, piece, Vec3 offset, angle) 0x182c98, world_setPieceCollision 0x182b00, world_setPieceHeight 0x182bb4, piece bounds 0x182940, 0x182bf4 (shake).

#### Switch (table 0x50df48; 0x50) ctor 0x28a850, prompt 0x28a8b4, interact 0x28a8f0

- Always interactable. Prompt text id FlipSwitch. Interact: clears 0x100000 (one use), moves the piece by (8,0,0), obj_runActionScripts(this, 1). No run, no save.

#### DoorSwing (table 0x50e100; 0x5c) ctor 0x28a960, prompt 0x28a9ec, trigger 0x28aa48, interact 0x28aa7c, slot17 0x28ae34 (empty), save 0x28ae3c, load 0x28ae74, run 0x28af54

- Properties: `disable` (int): non-zero deletes the object in the ctor (the piece stays as closed geometry) and suppresses the prompt; `name`: not openable by hand; `key`: name of a script run on interact, result 0 = locked; `sound`: "jail" selects the jail-door sounds, absent = wooden, anything else = silent.
- Fields: +0x50 s16 angle; +0x54 float angular speed; +0x58 s8 swing direction.
- trigger (slot 3): calls its own interact with player slot -10 (skips the key test).
- interact(slot): key script fails -> locked sound, player_voice(slot, 7), HUD text DoorLocked for 180 frames. Otherwise: clears 0x100000, obj_runEveryFrame, speed = 600, open sound, piece collision off, direction chosen from which side of the door player `slot` stands (slot -10 uses player 0), inverted when piece flag 0x40 is set, flags |= 1.
- run: angle += speed; speed *= 0.98; past 0x637c (0x43e8 when the level name contains "gothic") with positive speed the speed is reflected x0.74 (x0.1 gothic); piece rotated to angle*direction; leaves the run list when |speed| < 1.
- save 8 bytes (angle, direction, speed); load restores, and an opened door gets collision off and rejoins the run list.

#### DoorSecret (table 0x50dfd8; 0x5c) ctor 0x28b0a8, prompt 0x28b120, trigger 0x28b15c, save 0x28b1a0, load 0x28b1b8, interact 0x28b268, run 0x28b370

- Always interactable; prompt shown only when the level name is "cellar1". Property `key` as DoorSwing. trigger: interact(0) if still interactable. interact: +0x58 = 1, clears 0x100000, run list, +0x54 = frame. run (t = frame - start): recess 20 quarter-units over the first 20 frames, slide sound at t=120, slides up to 100 units over the next 60 frames (hermite), collision off after t=180, leaves the run list at t=301. save 1 byte (+0x58); load of an opened door: collision off, piece dropped 300 units, not interactable.

#### FloorSwitch (table 0x50deb8; 0x58) ctor 0x28b4e0, save 0x28b53c, load 0x28b554, run 0x28b56c

- On the every-15th-frame list (obj_runEvery15 0x14f330). Properties: `keyObject` (only an object whose `name` equals it presses the plate), `onOnly`, `offOnly`. run: box = piece bounds raised 6; pressed when any object without flag 1 is inside (or the key object). +0x50 0 up / 1 down; +0x54 depth 0..1 in steps of 0.25 (piece moved and its height set); on press: every-frame list, one of two sounds by an own draw, actions; on release: actions. Action value = offOnly == 0 && (onOnly != 0 || pressed). Back to the every-15 list when travel ends. save/load 1 byte (+0x50).

#### FallPlatform (table 0x50de28; 0x70) ctor 0x28b88c, path helper 0x28b91c, trigger 0x28badc, save 0x28bb2c, load 0x28bb44, run 0x28bb5c

- No caller or reference to the constructor exists (xref): Inferred never instantiated in this build. Logic: `goal` property marks goal platforms; a "leader" platform (ctor argument -> +0x69) that is stepped on builds a random path through neighbouring platforms (156-unit box, own-generator choice, recursion 0x28b91c) to a goal and triggers every neighbour off that path; a triggered platform shakes, falls 720 units (9 units/frame^2), waits on the every-60 list, then rises again. Uses a static scratch list at 0x8e3ec0.

#### RollDoor (table 0x50e068; 0x5c) ctor 0x28dd94, prompt 0x28de30, interact 0x28de6c, slot17 0x28dee0 (empty), save 0x28dee8, load 0x28df24, trigger 0x28dfe8, run 0x28e01c, draw 0x28e110

- WorldPart with its own drawn model (class def 0x501428, flag 2 cleared). Prompt OpenDoor. interact: clears 0x100000, run list, stone sound, +0x5a = 1. trigger: interact(0). run: counter +0x54; for 151 frames the object slides along facing+0x4000 at speed +0x50 (starts 0, +0.01/frame) and rolls (+0x58 -= speed*200); piece collision off once the counter passes 120; then leaves the run list and hides (flag 2). save 16 bytes (+0x5a, piece index, speed, counter); load re-enables collision and rejoins the run list when opened. The position is not saved.

#### PokeReflector (table 0x50d9a8; 0x4c) ctor 0x28e1e4, prompt 0x28e24c, interact 0x28e2ec

- Invisible interactable proxy. Property `target`: prompt is forwarded to slot 13 of the object with that name; interact is forwarded to slot 14 of up to 16 objects with that name.

#### Lever (table 0x50d918; 0x54) ctor 0x28e394, save 0x28e414, load 0x28e450, prompt 0x28e4c0, interact 0x28e60c, draw 0x28e64c, run 0x28e748

- Class def 0x501448; flags |= 0x100001; +0x50 = 1. Properties `onOnly`, `offOnly`, `action`. Prompt PullLever / PushLever by the side the prompting player stands on (reads that player's position; prompt code only). interact: clears 0x100000, run list, +0x51 = 1. run as in the first pass. save 10 bytes: position +0x4c, THE WHOLE FLAG WORD +0xc, direction, moving; load writes the flag word back.

#### WeaponRack (table 0x50d6d8; 0x98) ctor 0x28e87c, prompt 0x28ea50, interact 0x28ea8c (EMPTY), draw 0x28ea94

- Ctor builds an item record at +0x50: worth = level_monsterLevelTimesDifficulty() * (0.95 + own draw * 0.1) * (monster level * 0.2 + 0.8) * 200, times the float property `random` when present; item_generateWithAffixes(item, worth, 0, -1, 1); on failure the named item "arrows" with count 40. Prompt SearchWeaponRack. The interact slot is an empty function and nothing else references the class table or type info (xref): the item is drawn on the rack but no code hands it out. draw: item model; no stores.

#### Timer (0x50d7f8; 0x54) ctor 0x28ec1c, trigger 0x28ec7c, run 0x28ecd4; Counter (0x50d888; 0x50) ctor 0x28ed14, save 0x28ed74, load 0x28ed8c, trigger 0x28eda4

- Both hidden (flags |= 3). Timer property `time` (seconds); trigger(value) starts time*60 frames and remembers value; run fires the actions with it. Counter properties `count` (default 1), `onOnly`, `offOnly`; trigger(non-zero) counts up, trigger(0) down; action when the count is reached (up) or left (down). Counter saves its count (4 bytes? see save) - Timer saves nothing.

#### Teleporter (table 0x50d590; 0x3c8, Creature-derived) ctor 0x28ee80, draw 0x28ef04 (empty), run 0x28ef0c, setState 0x28f154 (empty)

- Ctor: Creature_ctor(max hp arg 10000, no type name, no class def); flags |= 0xf; runEvery60. run: Creature_updateActive (result unused) and two particles from its own generator; no Creature_run. Every other slot is the Creature base (vtab): slot 3 = Creature_trigger and slot 14 = Creature_interact, both of which run the object's `dialogScript`. No code in the class moves a player and no script built-in or level script mentions teleport: Inferred that the teleporting, if any, is done by the level script named in `dialogScript`.

#### Blocker ctor 0x28f15c (table 0x511570)

- Properties `radius`, `radius2` (both write the radius, radius2 wins), `standable` (flag 0x10, height 1), `ignoreprojectiles` (flag 0x20000000); radius 0 -> flags |= 0x205; always hidden.

#### VehicleBodySphere (0x50d0e8) ctor 0x28f2c4, onTouch 0x28f340

- Collision sphere at a static position whose touch is forwarded to slot 6 of its owner (raw pointer +0x4c).

#### PointSourceSound (0x50d208) ctor 0x28f370, run 0x28f4ac

- Positional sound switched by obj_updateActive(radius +0x58); the constructor has no caller (xref).

#### CdEyeball (0x50fab0; 0x3d0) ctor 0x28f5dc, draw 0x28f6cc, run 0x28f7c0

- Decorative creature; properties `pitch`, `scale` (percent); run: updateActive, V23 pickTarget, turns to the target but stays within +-6000 of its initial facing +0x3ca. Per-machine: none.

#### Sparks (0x50e998; 0xb8; Projectile) ctor 0x28f880, run 0x28fa3c, onTouch 0x2900c8, draw 0x2902e4 - the ShockOfFire bolt (created by skill 57 0x2ed4e4, Cazic 0x24c5a4, Demon 0x25e730, Mummy 0x2996c4, 0x1f4ad8)

- Life 600 frames; obj_moveAndCollide with velocity +0x58; a collision ends it. onTouch(other): when the owner (handle +0x4c) calls other an enemy (slot 20): damage_apply(0,0,other,owner,attack 10000000, flags 0xc060, descriptor slot 0x1f: 100 % chance, +0xac..+0xa8 fire). End: 50 particles and, when +0xb0 > 0, world_damageInRadius(40, +0xb4, owner or self, pos, +0xb0, flags 0x40860). All randomness own generator. draw: one glow, no stores.

#### IceBall (0x50e638; 0xac; Projectile) ctor 0x290390, run 0x290528, draw 0x290908 (created by 0x1f3a90)

- Life 600 frames; first collision: fx_spawn(10), LightEffect, world_damageInRadius(40, 80, self, pos, +0xa8, flags 0x40500).

#### Lights: Torch (0x50f298; 0x8c) ctor 0x2b1e80, save 0x2b2028, load 0x2b2040, run 0x2b2088, onTouch 0x2b2860, draw 0x2b2ae8; Candle (0x50f0e8; 0x94) 0x2b2c70 / run 0x2b2dc4 / draw 0x2b30ac; Candle2 (0x50f058; 0x50) 0x2b30ec / 0x2b3164 / 0x2b33b4; Lantern (0x50efc8; 0x98) 0x2b33f4 / 0x2b3554 / 0x2b3638; Lamp (0x50ef38; 0x8c) 0x2b3718 / 0x2b3858 / 0x2b3a64; static initialiser 0x2b3afc (+stub 0x2b3e10)

- No light constructor reads a property. The Torch kind byte +0x8a (0-5) is the factory's fourth constructor argument (which type name was used); kind 0 sets flag 1, others flag 0x200; all torches get flags 0x50008. Torch save/load: 4 bytes (the kind), load re-derives flags 1 / 0x200. Candle's third ctor argument -> +0x90.
- Run (all five): flame/smoke particles placed with GameObject_rand(this), light radius flicker from math_noise(object address * 0x19660d + frame * 16 + const) (Torch, Lantern, Lamp), a "frames since drawn" byte counted up; at 31 obj_stopRunning and the "running" byte cleared. Lantern_run tests whether the level name contains "mine". No run function writes anything but the light block, the two bytes and (through GameObject_rand) the object's own seed.
- Draw (all five): clears the "frames since drawn" byte and, when the running byte is 0, calls obj_runEveryFrame and sets it. Pairs: Torch +0x89/+0x88, Candle +0x8d/+0x8c, Candle2 +0x4d/+0x4c, Lantern +0x95/+0x94, Lamp +0x89/+0x88. Candle, Candle2, Lantern and Lamp also call obj_runEveryFrame in their constructors with the running byte left 0.
- Torch_onTouch(other): only for a player (flag 0x40), torch kind not 2 or 3, and frame % 12 == 0: fire slot 0x15 with min = skill 13 FireWeapons table+0x5c value at (int)monster level x 0.15 and max = min + 20 % x ONE g_randSeed draw; damage_apply(0, 0, player, torch, attack 10000000, flags 0x100c040). (The decompile also shows an unreachable "1..1 damage for non-players" branch.)
- Can a light being on the run list on one machine only change shared state? (a) the run functions draw only the light's own generator, which nothing else reads; (b) no shared code reads the fields run writes; (c) Torch_onTouch reads only the kind byte (constructor/load), the frame counter, the monster level and g_randSeed, nothing run or draw wrote; (d) obj_runEveryFrame 0x14f248 unlinks the object's run node and calls handle_link(g_runListActive 0x5db3a8, obj+4, obj), which pushes at the HEAD of the list: other objects keep their relative order, only the light's own place differs. What the draw-time call does consume is two 20-byte nodes of the global handle-node free list 0x864ea8 (handle_link 0x1a1738 pops them without a null test). So the number of free handle nodes differs between machines by two per light in view; that changes behaviour only if the node pool runs out, where handle_link would write through a null pointer.

#### FireTrail (0x50dd98; 0x64) ctor 0x28c160, onTouch 0x28c2c4, run 0x28c44c; FireTrailMaker (0x50dd08; 0x70) ctor 0x28c6d8, run 0x28c910

- FireTrailMaker_ctor has no caller and no pointer reference (xref, ptrs): Inferred that neither class is created in this build. FireTrail_ctor is called only by the maker. Logic: the maker (life seconds, wave amplitude/frequency, optional target handle +0x58, owner handle +0x5c) moves 300 units/s along its facing, homing 0x111 per frame on the target, and every 7 frames (4 when the owner is a player) lays a FireTrail segment (pool_new(100)); a segment is a flame strip from its start to the maker's later position, radius 12 (28 and flag 0x800 when the owner is a player), life from the ctor argument; onTouch on frame % 12 == 0 gives fire slot 0x15 damage 1..1 (owner is a player) or 3..3 through damage_apply(…, attack 100000, flags 0x100c040), never to the owner and never player-on-player.

#### Catapult (0x514270; 0xfc) ctor 0x24d440, dtor 0x24d7e0, trigger 0x24d8e0, save 0x24d92c, load 0x24d948, run 0x24d9c0, draw 0x24dc40, takeDamage 0x24de9c

- Properties: `launchvel` (int units/s; default 5.5167 per frame), `stagger` (seconds before the first cycle), `script` (name, pointer kept at +0x50), `hide` (int -> +0x56; no blockers), `cutHold` (non-zero: no animation queued and stagger 0 until triggered), `reduceCarnage` (halve the debris by own draws), `deathScript`.
- Ctor: class def 0x4ff240; flag word cleared; run list; unless hidden creates a grid of Blocker objects (flag 0x4000, radius 38 or 30) kept in the handle list +0xf8.
- trigger (slot 3): restarts the throwing animation. save 1 byte "an animation is queued"; load re-queues it.
- run: nothing once destroyed (+0x57); obj_updateActive(this, +0x4c, 1600) false -> return; stagger countdown; when the animation time +0x7c is below 2.10 and no cycle is open: opens one; if there is no `script` or script_runByName(script) returns non-zero: pool_new(0xb8) FireBomblet_ctor 0x2622a8(start = own position +100 high, velocity = facing x launchvel, vz = launchvel/2, fireOK 1), raw pointer kept at +0x58, bomb held (0x26329c(bomb, 1)), +0x4e = 1, animation runs; otherwise the animation is frozen for the cycle. Above time 158.58 the bomb is released (0x26329c(bomb, 0)) and the cycle closes. While held the bomb's position is written from model attach point 0.
- takeDamage: the first hit of any size destroys it: +0x57 = 1, one PhProp (0x248) per part of catapult_broken, a held bomb is released and thrown away from the attacker at speed 4 (not during a cutscene), `deathScript` is run, obj_delete.
- draw: reads the camera position and view matrix to choose the shadow pass (distance along the view < -244); stores nothing.
- Per-machine: run is gated by obj_updateActive (players, or the camera focus while g_cullByCamera is set - FINDINGS D6): the script call, the bomb creation and its shared-seed draw inherit that. +0x58 is a raw pointer, not a handle.

#### FireBomb (kelethinBomb; 0x50db58; 0x58) ctor 0x261dbc, run 0x261f48; FireBomblet (0x514dd0; 0xb8) ctor 0x2622a8, dtor 0x262500, run 0x262588, draw 0x262ea4, bounce 0x262f7c, 0x263294 (clear launcher pointer), 0x26329c (set held byte); FireBombletJr (0x50dac8; 0x70) ctor 0x2632a4, run 0x2636dc, draw 0x263aa0, bounce 0x263b78; static init 0x263d70 (+stub 0x263dfc)

- FireBomb properties: `frequency` (seconds, default 240 frames), `skydrop` (int), `fireOK` (int, default 1), `script`. Ctor: flag word = 0x4001, radius 60, phase +0x54 = one g_randSeed draw % period.
- FireBomb_run: every period: `script` present and returning 0 -> skip. Then ONLY IF isNearView(960, position): one g_randSeed draw for a heading within +-0xfdd of the facing; skydrop 0: a second draw for a distance 332..717, target point 1037 below; skydrop non-zero: lands 401 ahead, start 357 above with a fixed descent; pool_new(0xb8) FireBomblet_ctor(…, &FireBomb+0x4d, target, velocity or 0, fireOK).
- FireBomblet: ballistic (gravity 0.1097/frame^2, terminal -7.03); after the apex every 8th frame damage_apply(2, 2, obj, bomb, 100000, flags 0x100c040, fire 1..1) to EVERY object in a +-radius box except itself (no enemy test); on reaching the ground: speed < 1 -> delete, else bounce (0x262f7c): velocity x0.5 (x0.33 for catapult bombs), from the second bounce a g_randSeed draw (1 in 4) adds a scorch decal (second draw) and counts in the launcher's byte (raw pointer +0xac, max 3); with fireOK and (cutscene active or frame % 37 == 0): five g_randSeed draws place a StaticFire (0x4ac, ctor 0x2c5240) lasting 240..780 frames. First bounce: a g_randSeed draw (3 in 4, always in a cutscene) then a draw for 2..4 FireBombletJr (5 in a cutscene) and one more draw. During a cutscene the bomb's own seed is forced to 0x246553 at each bounce. Deleted below the kill height +0xa4. An isNearView(960) call at the top of run has its result discarded (0x2625e8).
- FireBombletJr: ctor draws g_randSeed 7 times (direction, speed); same flight; damage_apply(1, 1, …) every 8th frame; bounce 0x263b78 can add a StaticFire of 120..240 frames by the same rule.
- Per-machine: FireBomb_run's launch (shared-seed draws, object creation) is gated by isNearView(960): players normally, the camera focus while g_cullByCamera is set (D6). FireBomblet +0xac is a raw pointer into the FireBomb object. Draw functions: no hits.

#### SpiritAnchor (SpiritAnchorAct / SpiritAnchorExp; 0x516738; 0x98) ctor 0x295ff4, dtor 0x296194, draw 0x296204, run 0x2964a8, takeDamage 0x296888, prompt 0x296b5c, interact 0x296c7c, load 0x296d4c, save 0x296dc4

- Kind +0x50 from the type name: Act = 1 (interactable), Exp = 0 (breakable). Properties: `key` (script), `message`, `lockMessage`, `action`.
- run: +0x58 decays 0.5/frame; obj_updateActive(this, +0x54, 480 + byte +0x28); while active: particles from the own generator every 8th (Exp) or 4th (Act) frame and the light radius.
- takeDamage (Exp, once): +0x4c = 1, a PhProp per model part, 100 particles, flags |= 3, obj_runActionScripts(this, 1), run list.
- interact (Act, once): clears 0x100000, +0x4c = 1, +0x58 = 40, run list, obj_runActionScripts(this, 1).
- prompt (Act, not yet used): RUNS THE `key` SCRIPT (script_runByName) and shows `message` when it returns non-zero, otherwise the text looked up under the `key` value (the code tests `lockMessage` but looks up `key`: Observed, probably a bug) and returns 0.
- save/load: 4 bytes (+0x4c); a used Exp anchor is hidden on load.
- Per-machine: the prompt slot runs a level script; prompts are evaluated on the draw path for the local player (as PushTrigger_prompt), so the key script runs a per-machine number of times. run's own-generator draws depend on obj_updateActive; nothing shared reads that generator.
- 0x296ddc (+stub 0x297768): static init of the particle definitions used by FireTrail, Teleporter, Sparks, IceBall, SpiritAnchor and neighbours (0x5012e0…0x501750, 0x8e3fc0…0x8e4420).

## 7. Per-machine state

The test applied to every class is the one of `docs/monsters.md` section 7: (a) does run code
(run, setState, takeDamage, touch, trigger, and what they call inside the area) read the
camera, the local player slot, audio state, a cosmetic generator for a gameplay decision, a
hardware timer or anything draw code wrote; (b) does the draw function change anything run
code reads; (c) does the draw function draw from a generator, create objects, change the run
list, run a script or query the world. Each class section ends with its own answer. This
section collects the answers that are not "none found". Not repeated: what every creature
inherits from `Creature_run`, `Creature_updateActive`, `Creature_processDamage` and
`Creature_draw` (FINDINGS D6, D12–D14; `docs/creatures.md` C1–C12).

### 7.1 New places where per-machine state can reach the simulation

| # | Where | What | Kind |
|---|---|---|---|
| M1 | `CloudGiant_run` state 3, 0x250930 (king variant, +0x3d8 = 1) | "hand 2 empty **and +0x530 == 0** → state 0x17 (conjure a bolt)". +0x530 is the return value of `beam_create` (0x193088), which is 0 when none of the 20 beam slots is free or `trail_create` fails. The same tables are filled by `fx_modelParticlesNearCamera_1f61c0` (call at 0x1f6478, after its camera test) and `fx_modelStatusEffects` (0x1f826c), so their occupancy differs between machines. If the create at the throw (0x2519e8) fails on one machine only, that machine's king conjures while the bolt is still flying and the others wait for it to land | read Observed; divergence Inferred, needs a full beam table |
| M2 | `FireBomb_run` 0x261f48, gate at 0x261fd0 | the launch — one or two `g_randSeed` draws, `pool_new`, `FireBomblet_ctor` (another seed draw) — happens only when `isNearView(960, position)` is true. `isNearView` uses the players, or the camera focus while `g_cullByCamera` is set (D6). The FireBomblet's later draws (bounce, FireBombletJr, StaticFire) are unconditional | Observed; a hazard exactly when D7 fails |
| M3 | `Catapult_run` 0x24d9c0 (`obj_updateActive`, radius 1600, at 0x24d9e4); `LightningRod_run` 0x295954 (radius 600); `AutoProp_run` 0x23cb54 (0x23cc0c) | activity gates, respectively: the `script` call and the bomb creation; the timer, own-generator draws and `LightningBolt` creation; the animation advance, the `ActionAtEnd` scripts, the snap-to-end and the piston damage. Same camera dependence as D6 / `docs/objects.md` O4 | Observed; D6 family |
| M4 | `Critter` constructed with a `path` property: `Critter_ctor` 0x2547fc → `anim_randomizeTopTime` (0x16d0b8, cosmetic generator), run state 0x16 | the move clip starts at a per-machine phase and state 0x16 adds its root motion to the position every frame. The position feeds the path follower, the grid, and for the bullfrog species the "squashed by a player" test, which runs `deathScript` and deletes the object | Observed; whether any level gives a bullfrog a `path`, and whether the clip's root motion is uniform, Unknown |
| M5 | plain `AutoProp` of type `pipepistona` (neither `AutoDoor` nor `AutoSwitch`), ctor 0x23c44c | its looping animation starts at a cosmetic-generator phase, and the frames on which the piston damages and pushes players are that animation's event bits. A run call made while the prop is inactive snaps a non-looping state to its end, which removes the phase | Observed; whether a shipped level places one Unknown |
| M6 | `NPC_draw` 0x29e3ec, `Gnome_draw` 0x2691f0, `GnomeNavigator_draw` 0x26a000, `Rondo_draw` 0x29f28c | the `exclamation` script is run on every drawn frame when **camera mode == 1** (the word at 0x4f8450 is the camera object pointer; mode at +0x34, written by `Camera_setMode` 0x2072e8: 0 while this machine's inventory, shop, dialog camera or a cutscene is up). NPC adds: only when more than 240 units from the camera (300 in a cutscene) and in front of it. `script_runByName` puts no restriction on what the script does. The two scripts found by name (`check1Exclam`, `check2Exclam`, INNOVAT1) only read | Observed; harmless unless some level's script writes |
| M7 | interact prompts (slot 13): `AutoChest` 0x23b6e8, `AutoProp` 0x23d068, `SpiritAnchor` 0x296ba0 | each runs the object's `key` script(s) every time the prompt is evaluated; prompts are evaluated from `Player_run` and from `Player_draw` (`docs/script.md` P1). None of the three stores into its object. `Lever`, `DoorSwing`, `DoorSecret`, `RollDoor`, `Switch`, `WeaponRack`, `AutoContainer` and `PokeReflector` prompts run no script (PokeReflector forwards to its target's prompt) | Observed |
| M8 | light draw functions (`Torch_draw` 0x2b2ae8, `Candle_draw` 0x2b30ac, `Candle2_draw` 0x2b33b4, `Lantern_draw` 0x2b3638, `Lamp_draw` 0x2b3a64) | `obj_runEveryFrame` from draw code calls `handle_link` (0x1a1738), which takes two 20-byte nodes from the global free list 0x864ea8 **without a null test**. The number of free handle nodes therefore differs between machines by two per light in view. Nothing else: the link is pushed at the head of the run list (other objects keep their order), the run functions draw only the light's own generator, and no shared code reads what they write. `Torch_onTouch` (0x2b2860, one `g_randSeed` draw per burn tick) reads nothing run or draw wrote | Observed; matters only at node-pool exhaustion |
| M9 | `AddParticle` slot 17 (0x240800), called from the draw functions of the LP classes and `AutoEmitter` | advances the helper's own generator (light-radius mode 1, 0x2408d8) and writes helper fields from draw code. Consumers found: lighting, sprites, cosmetic-generator particles, and `RingPortal_run`, which reads helper +0xfc for the inner model's scale only | Observed; no gameplay reader found |

### 7.2 First-pass rows now settled

| First-pass row (`docs/monsters.md` 7.9) | Answer |
|---|---|
| Critter, FireBeetle, FireFly, Mosquito, AntQueen draw store to position or facing | all save and restore before returning: AntQueen subtracts +0x3e4 from the facing at 0x236f50 and adds it back at 0x236f64; FireBeetle saves the position at 0x245cbc and restores it at 0x245f1c; FireFly restores at 0x247634; Mosquito saves at 0x297a3c and restores at 0x297afc; Critter raises z and writes x, y, z back on every path of 0x254f24. Only code running inside `Creature_draw` sees the offset |
| `AutoObject_draw` and the LP draws store to the flag word; LP draws read 0x44fdd0 | the bit is 0x100 (flash). `AutoObject_draw` only clears it. The LP stores (0x2415e8, 0x2421ac, 0x24270c) sit behind `0x240db0(helper) && (g_drawFrame & 0x40)` and 0x240db0 returns the constant 0, so they never execute and `g_drawFrame` influences nothing |
| `Creep_draw` stores to the creature flag word | sets cflag 0x200000 ("model not drawn") while the fade counter +0x4fe is above 100 and clears it unconditionally afterwards; the only reader found is `Creature_draw` |
| Teleporter: where does the teleport happen (open question 7) | nowhere in the class. Table 0x50d590 has only run (two particles), an empty draw and an empty setState of its own; everything else is the Creature base, whose trigger and interact run `dialogScript` |
| UndeadKnight_draw's uninitialised position (7.8) | still unreachable: the only function that links the mount handle, 0x2b5370, has no caller |
| AntWave draws its own generator from draw code (7.5) | unchanged, but AntQueen state 0x19 — the only creator of AntWave — has no requester in the class (**Inferred** unreachable; slot-27 calls with a computed argument in other classes were not traced) |

### 7.3 Smaller items

| Where | What | Kind |
|---|---|---|
| `RedDragon_run` state 0xf, 0x260888 | when `players_findFarthestWithin` finds nobody the index −1 is used anyway: the word at 0x4d8298 (0x4c30 below player 0's object pointer) is read as an object pointer. What that word holds, and whether it is the same on every machine, was not determined | Observed read; content Unknown |
| `Wraith_isEnemy` 0x2c061c, `WarWraith_isEnemy` 0x2c1bc0 | the slot-20 override clears another wraith's target handle as a side effect. All 68 functions that call slot 20 are run, touch, cast or projectile functions by name, none a draw function | Observed; safe as long as that holds |
| Marr death effects 0x284b68; Cazic death effects (first pass) | generator 0x404468 chooses particle counts and directions only; the stage timer +0x4a4 and the `obj_delete` do not depend on it. The white fade is a `ui_drawRect` call made from run code | Observed; cosmetic |
| `Torch_run`, `Lantern_run`, `Lamp_run`, `Torch_draw`; `WebTrap_draw` 0x2b0954; strand lines 0x2af510 | flicker noise, glow rotation and strand end points are computed from an object's **address** | Observed; cosmetic, but differs wherever addresses differ |
| `SpiritAnchor_run` 0x2964a8, `AutoEmitter_run`, `PointSourceSound_run` | `obj_updateActive` gates only particles, light or sound; the anchor's own-generator draws depend on it but nothing shared reads that generator | Observed; cosmetic |
| `OniBall_run` / `OniBall_onTouch` | read the lockstep pad block and walk the alive-player list (see `docs/player.md` for that list's caveat) | Observed; as the first pass said |
| `Droid` +0x3c8, `Innoruuk` +0x4c8, `CloudGiant` +0x534 | sound handles returned by audio code are stored in the object and only ever handed back to `sound_stop` | Observed; object bytes differ, no decision reads them |
| `decal_add` callers (Zek, beetleProjectile, DiseaseProjectile, PoisonProjectile, SmallSpider, Droid, FireBomblet) | the decal depends on a local detail option, but every caller draws its random angle **before** the call, so generator use does not depend on the option | Observed; a guard |
| `Orc`, `GnawSpawn`, `Mosquito`, `Ant`, `Scorpion`, `BlackWidow` part-loss helpers | create `GutChunk` objects, whose lifetime depends on a local display option (`docs/objects.md` O2). Orc's dismember branch takes "network mode" as an alternative to the option, so creation itself is the same on every machine in a net game | Observed; O2 applies |
| `AutoContainer_run` (and `Container_run` of the first pass), the every-8th-frame water test | the "standing in water" flag comes from `water_disturb`'s return value (`docs/engine.md` P14: forced to 0 while a cutscene is being skipped); re-entering water costs one own-generator draw, so a difference there would shift that container's later loot rolls | Observed; inherited from P14 |
| Raw pointers where the rest of the game uses handles | `FireBomblet` +0xac points at a byte inside the `FireBomb` that launched it; `Catapult` +0x58 points at the held `FireBomblet`; `Root` keeps its victim pointer for 1800 frames; `VehicleBodySphere` +0x4c points at its owner | Observed; a crash risk if the pointee is deleted, not a desync by itself |

### 7.4 Checked and found clean

By scan and by reading, no per-machine read in run code and no store, generator draw, object
creation, run-list change, script or world query in draw code: Zek, Innoruuk (and HateBeam,
HateProjectile, HateSoul, SpellHateEffect), Marr, MummyKing (and DustDevil, SpawnMummy,
MummySnake), Natasla, SpiderQueen, WebTrap, VampireLord, Nightmare, Hag, LightningBolt,
IronGuardian, Droid, JunkProjectile, BoltGoRound, Demon, SeaMonster, LavaMonster, LavaBomb,
Minion, GnawSpawn, Ant, AntQueen, Arenabeast, FireBeetle, FireFly, beetleProjectile, Badger,
CastBadger, Agony, Amphian, Bubo, DiseaseProjectile, FemaleDarkElf, Creep, Cyclops, FatCyclops,
Clockwork, Goblin, MaleDarkElf, Froglock, Rondo, Gnome and GnomeNavigator (apart from M6),
Ghoul, Gnaw, Mummy, LostSoul, Root, UnholyAura, Tormentor, Minotaur, Kobold, Gremlin,
Mosquito, Ogre, Mermaid, Orc, Skeleton, Soul, Scorpion, BlackWidow, SmallSpider,
PoisonProjectile, WoodElfSoldier, Wraith, WarWraith, Vampire, UndeadKnight, Warrior, Ulthork,
WarBoar, CdEyeball, Sparks, IceBall, the door and switch classes, Lever, Timer, Counter,
WeaponRack, PokeReflector, Teleporter, FireBomblet and FireBombletJr (apart from M2),
CreatureContainer, Generator and ScriptGenerator. "Clean" is by the method of the introduction: virtual calls and
functions outside the area (the creature base, the weapon holder, `fx_modelStatusEffects`, the
skills cast) were not followed.

Three bosses do not use the result of `Creature_updateActive` at all — Innoruuk (0x273bd0),
MummyKing (0x29b360) and Minion (0x2862c0) — so their AI is not subject to D6.

## 8. Function names

New names are in `symbols/monsters2.tsv`: 147 addresses, 146 of them inside the area. The file only holds addresses that no other symbol file named when it was written, so the renames below are **proposals** and were not applied (`tools/symtab.py check` treats a second name for an address as a conflict).

### 8.1 Proposed renames

Slot numbers are `tools/vtab.py` numbers. The naming used: slot 3 `_trigger`, 10 `_onHitTerrain`, 11 `_onTouchList`, 12 `_onNearbyEvent`, 16 `_getModel`, 38 `_getSecondModel`, 20 `_isEnemy`, 21 `_isAlly`, 36 `_getDodgeLevel`; for the AutoProp family 17 `_nextState`, 18 `_setState`, 19 `_setPassable`.

| Address | Current name (file) | Proposed name | Evidence |
|---|---|---|---|
| 0x118058 | `Weapon2_slot21` (creatures) | `Weapon2_update` | (f, classDef, creature): for each full hand, when the creature is not hidden and isNearView(480, pos) holds, calls fx_modelStatusEffects with the hand's descriptor and the state block at +0xc / +0x9c. Called from run functions at table offset 0xac. Body read; fx_modelStatusEffects not read |
| 0x11aff0 | `Weapon1_slot8` (creatures) | `Weapon1_setElement` | (which, element): creature_buildElementDamage(…, +0x50, element) when which < 2. Demon_loadState calls it with (saved word, 0). Body read |
| 0x11b020 | `Weapon1_slot9` (creatures) | `Weapon1_setHandColour` | (which < 2, four 8-bit values) into +0x60..+0x66. Colour meaning Inferred. Body read |
| 0x11b050 | `Weapon1_slot10` (creatures) | `Weapon1_setHandColour2` | Same as slot 9 but into +0x68..+0x6e. Body read |
| 0x11b148 | `Weapon1_slot16` (creatures) | `Weapon1_getElement` | (hand == 1): damageDesc_getElement of the descriptor at +0x50, else 0. Used by Demon_saveState. Body read |
| 0x11b5f0 | `Weapon2_slot1` (creatures) | `Weapon2_setHandPart` | (hand, entry): stores the model-entry byte of hand 1 (+8) or hand 2 (+0x98) and sets/clears bit 0 / bit 1 of +4; entry 0 empties the hand. Body read |
| 0x11b668 | `Weapon2_slot9` (creatures) | `Weapon2_setHandColour` | (which, r, g, b, a): four 8-bit values into +0x60.. (hand 1) and/or +0xf0.. (hand 2). That they are a colour is Inferred from the values passed (150,150,200,30). Body read |
| 0x11b708 | `Weapon2_slot11` (creatures) | `Weapon2_dropPart` | (which, creature, …): creature_dropHeldPartAsProp for each selected hand that is full, then clears its bit in +4. Body read |
| 0x11b858 | `Weapon2_slot14` (creatures) | `Weapon2_isHandFull` | (hand): bit 0 or bit 1 of +4. Body read |
| 0x11b898 | `Weapon2_slot15` (creatures) | `Weapon2_getHandPart` | (hand): the model-entry byte +8 or +0x98. Body read |
| 0x11b8c8 | `Weapon2_slot16` (creatures) | `Weapon2_getElement` | (hand): damageDesc_getElement of that hand's descriptor (1 fire, 2 cold, 3 poison, 4 lightning, 6 type 0x1f). Used by CloudGiant_saveState. Body read |
| 0x11b920 | `Weapon2_slot17` (creatures) | `Weapon2_getDescriptor` | (hand): pointer to the damage descriptor, +0x50 for hand 1, +0xe0 for hand 2, else 0. Body read |
| 0x11b948 | `Weapon2_slot18` (creatures) | `Weapon2_draw` | (classDef, model, drawResult): draws the model entry of each full hand through 0x178c28; stores nothing. Called from CloudGiant_draw at table offset 0x94. Body read |
| 0x2378f4 | `AntQueen_vslot3` (monsters) | `AntQueen_trigger` | slot 3 override, empty function: the Creature trigger (dialog script) is disabled for this class |
| 0x239b9c | `Arenabeast_vslot3` (monsters) | `Arenabeast_trigger` | slot 3 override, empty function |
| 0x23a028 | `Arenabeast_vslot11` (monsters) | `Arenabeast_onTouchList` | slot 11 (zero-terminated list of touched objects from Creature_moveBy): in state 0xd until the first contact hit / event 0x10, and always in states 0xe and 0xf, calls damage_apply(+0xd0, +0xd2, victim, this, 100000, 0, 0, 0x100041, 0, 0) on every listed object with object flag 0x20 |
| 0x23b854 | `AutoChest_vslot3` (monsters) | `AutoChest_trigger` | slot 3: a closed chest (+0xd8 == 0) calls its own slot 14 with player slot 0; no key test on this path. Shared with AutoChestLP |
| 0x23ba3c | `autoobject_dropLoot` (monsters) | `AutoChest_dropLoot` | xref shows one caller (AutoChest_run 0x23b674) and it reads the AutoChest field +0xec, so it is a chest member; rename optional |
| 0x23cea0 | `AutoPropLP_saveState` (monsters) | `AutoProp_saveState` | slot 9 of table 0x5133c0 (AutoProp), shared with 12 other classes (vtab.py); writes 4 bytes = state +0x178 |
| 0x23ceb8 | `AutoPropLP_loadState` (monsters) | `AutoProp_loadState` | slot 8 of AutoProp; stores the state and calls slot 18 with it |
| 0x23cf0c | `AutoPropLP_takeDamage` (monsters) | `AutoProp_takeDamage` | slot 2 of AutoProp; Breakable or Crumble with States != 0 -> slot 17 + sounds; the amount is ignored |
| 0x23d014 | `AutoPropLP_interactPrompt` (monsters) | `AutoProp_interactPrompt` | slot 13 of AutoProp; Pokeable and state without NoMessage: runs every 'key' script (0x23d068), text from message / message<state> / lockMessage; writes no object field |
| 0x23d1b0 | `AutoPropLP_interact` (monsters) | `AutoProp_interact` | slot 14 of AutoProp; Pokeable and States != 0 -> slot 17; no key test |
| 0x23d1fc | `AutoPropLP_vslot3` (monsters) | `AutoProp_trigger` | slot 3 of AutoProp (table 0x5133c0; currently misnamed AutoPropLP_vslot3): Triggerable and States != 0 -> slot 17; sounds for gothtrap / fayactuator |
| 0x23d2ec | `AutoPropLP_vslot17` (monsters) | `AutoProp_nextState` | slot 17 of AutoProp (misnamed AutoPropLP_vslot17): advance one state (wraps with LoopingState), rebuild the mesh mask, debris for Breakable, run actions unless ActionAtEnd, push the state animation, obj_runEveryFrame |
| 0x23d680 | `AutoPropLP_vslot18` (monsters) | `AutoProp_setState` | slot 18 of AutoProp (misnamed AutoPropLP_vslot18): set state n silently (animation at its end, no actions); the entry used by script autoPropSetState 0x142320, by StartState and by loadState |
| 0x23d7ac | `AutoPropLP_vslot19` (monsters) | `AutoProp_setPassable` | slot 19 of AutoProp (misnamed AutoPropLP_vslot19): (on) object flag 0x1 on/off; for an AutoDoor also piece collision off/on and piece offset -256/0 |
| 0x23e2ec | `AutoContainer_vslot3` (monsters) | `AutoContainer_trigger` | slot 3: same body as AutoContainer_interact 0x23e280 - ignite an Explodeable container (state 3, fuse 180, action scripts) |
| 0x240800 | `AddParticle_vslot17` (monsters) | `AddParticle_updateLightAndHalo` | slot 17 of AddParticle (pos): called from owners' draw functions; recomputes the light radius by mode 'lrc' (mode 1 draws GameObject_rand on the helper at 0x2408d8), relinks the light, queues the halo sprite |
| 0x240b64 | `AddParticle_vslot18` (monsters) | `AddParticle_emit` | slot 18 of AddParticle (pos, dir or 0, mode): called from owners' run functions; picks the frame index (+0x180) and calls the cosmetic-seed burst function 0x195400; ends a finished one-shot |
| 0x240da8 | `AddParticle_vslot19` (monsters) | `AddParticle_slot19Empty` | slot 19 of AddParticle: empty function |
| 0x243104 | `GothTrap_vslot19` (monsters) | `GothTrap_setPassable` | slot 19 override (argument ignored): piece collision on, piece offset and height by state 0 / 1 / 2 (0, -350, -350 with height +256) |
| 0x2432dc | `HateHole_vslot19` (monsters) | `HateHole_setPassable` | slot 19 override (argument ignored): state 1 piece down 350 and height -350; state 2 height +256 |
| 0x24348c | `HateBridge_vslot19` (monsters) | `HateBridge_setPassable` | slot 19 override (argument ignored): collision on; state 0 piece at 0 and stored height; 1 down 350; 2 height +256 |
| 0x2435f4 | `HackDoor_vslot19` (monsters) | `HackDoor_setPassable` | slot 19 override: AutoProp_setPassable then object flag 0x1 forced on (the object is never solid, only the level piece) |
| 0x243c10 | `RingPortal_vslot17` (monsters) | `RingPortal_nextState` | slot 17 override: AutoProp_nextState, then state 0 -> inner model off and scale 0.01, state 1 -> inner model on, counter 180 |
| 0x243c70 | `RingPortal_vslot18` (monsters) | `RingPortal_setState` | slot 18 override: AutoProp_setState, then the same inner-model update as 0x243c10 |
| 0x243d24 | `DiseasePort_vslot17` (monsters) | `DiseasePort_nextState` | slot 17 override: leaving state 0 plays sounds; disportGOOD has the Breakable mask set only around the AutoProp_nextState call |
| 0x243e20 | `DiseasePort_vslot18` (monsters) | `DiseasePort_setState` | slot 18 override: plain tail call of AutoProp_setState |
| 0x244a9c | `Badger_vslot11` (monsters) | `Badger_onTouchList` | slot 11 override, empty function |
| 0x245518 | `CastBadger_vslot11` (monsters) | `CastBadger_onTouchList` | slot 11 override, empty function |
| 0x246fe8 | `FireBeetle_vslot11` (monsters) | `FireBeetle_onTouchList` | slot 11: only in state 0x17 (flying); every touched object of a different dynamic class gets a direct slot-2 takeDamage((own rand & 7) + 4, this, 0x40001); with a target and a touched object lacking object flag 4 it requests state 3; other states call the empty Creature_slot11 |
| 0x249404 | `Bubo_vslot12` (monsters) | `Bubo_onNearbyEvent` | slot 12 (kind, Vec3 *pos, source): kind 0 from an object whose type-info equals Bubo's, own state < 2 -> setState(1) and wander destination +0x104 = pos. Kind 0 is sent by Creature_processDamage through world_notifyObjectsNear only when g_numPlayers == 1 |
| 0x249a30 | `Bubo_vslot38` (monsters) | `Bubo_getSecondModel` | slot 38: returns class-definition resource +0x1c when byte +0x468 == 1, else +0x14; Bubo_draw passes the result as the third argument of Creature_draw. That it is a texture rather than a model was not checked |
| 0x24c028 | `Cazic_vslot12` (monsters) | `Cazic_onNearbyEvent` | slot 12; was Cazic_vslot12: empty function |
| 0x24c04c | `Cazic_vslot11` (monsters) | `Cazic_onTouchList` | slot 11; was Cazic_vslot11: in the charge state 0xf damages every touched player and requests state 5 (first pass, docs/monsters.md) |
| 0x24d8e0 | `Catapult_vslot3` (monsters) | `Catapult_trigger` | slot 3; was Catapult_vslot3: restarts the catapult animation |
| 0x252444 | `CloudGiant_vslot3` (monsters) | `CloudGiant_trigger` | was CloudGiant_vslot3. Slot 3: calls Creature_trigger (0x11a5f0) only when +0x3d8 == 0, i.e. the king variant ignores the signal |
| 0x2542a0 | `Creep_vslot12` (monsters) | `Creep_onNearbyEvent` | slot 12: empty body (copies the position argument to the stack and returns); instructions read |
| 0x25aa30 | `FemaleDarkElf_vslot12` (monsters) | `FemaleDarkElf_onNearbyEvent` | slot 12: kind 2 only (sent by Player_run to the creature a player's shot is aimed at; that reading of kind 2 is Inferred): with the shield hand on, state 3 or 5 and the source within +-9999 of the facing -> setState(0x11) (block) |
| 0x25cfc0 | `MaleDarkElf_vslot12` (monsters) | `MaleDarkElf_onNearbyEvent` | was MaleDarkElf_vslot12. Slot 12: only kind 2: has a shield (0x25dc00), state 3 or 5, source within +-9999 of facing -> setState 0x11 |
| 0x25f378 | `Demon_vslot20` (monsters) | `Demon_isEnemy` | was Demon_vslot20. Slot 20: Creature_isEnemy; if that is 0 and the other object is exactly a Soul (RTTI vs Soul type info 0x3cc7a0) and not dead, returns 3 |
| 0x260d50 | `RedDragon_vslot3` (monsters) | `RedDragon_trigger` | slot 3; empty |
| 0x265e08 | `Generator_vslot3` (monsters) | `Generator_trigger` | slot 3: with 'triggerable' creates one object of the generator's type at once (no count, no creature test before writing +0x34 and creature flag 0x1000000, dis 0x265e68-0x265e7c), then Creature_trigger |
| 0x266bac | `Ghoul_vslot12` (monsters) | `Ghoul_onNearbyEvent` | was Ghoul_vslot12. Slot 12: kind 0 with a Ghoul source while in state 0 or 1 -> setState 0x17 and destination +0x104 = pos |
| 0x269ab8 | `Gnome_vslot11` (monsters) | `Gnome_onTouchList` | was Gnome_vslot11. Slot 11: if not dead, clock > +0x3d4 and the FIRST touched object is a Gnome in state 0x17: partner handle +0x3d0 = it, setState 0x17, +0x3d4 = partner's +0x3d4 + 60; then base slot 11 |
| 0x26c9f4 | `Goblin_vslot12` (monsters) | `Goblin_onNearbyEvent` | was Goblin_vslot12. Slot 12 (radius, kind, pos, source): kind 0 from a Goblin source in state 0/1 -> setState 2 with destination = pos; kind 2 with shield out, state 3/5, source within +-9999 of facing -> setState 0x11. Kind 0 is sent by Creature_processDamage 0x110dc8 only when g_numPlayers == 1 |
| 0x26d690 | `Goblin_vslot10` (monsters) | `Goblin_onHitTerrain` | was Goblin_vslot10. Slot 10 (called by Creature_moveBy after hitting terrain): in state 0x12 with animation flag 0x20 clear starts class animation +0xac (knokinto) with flag 0x20 |
| 0x26d6fc | `Goblin_vslot11` (monsters) | `Goblin_onTouchList` | was Goblin_vslot11. Slot 11 (zero-terminated list of touched objects): same knokinto rule as slot 10, then calls slot 2 (1.0, this, 1) on every touched object whose RTTI is Container |
| 0x27090c | `Hag_vslot16` (monsters) | `Hag_getModel` | slot 16: classDef+0x1c when variant byte +0x3c8 == 1 (type name hagred) else classDef+0xc |
| 0x27092c | `Hag_vslot38` (monsters) | `Hag_getSecondModel` | slot 38: classDef+0x24 when +0x3c8 == 1 else classDef+0x14 |
| 0x27142c | `Nightmare_vslot10` (monsters) | `Nightmare_onHitTerrain` | slot 10: in state 7 (charge) calls setState(3) |
| 0x271484 | `Nightmare_vslot11` (monsters) | `Nightmare_onTouchList` | slot 11: in state 7 damages every touched Player not in a knock-down animation (damage_apply 2x range, rating 100000, flags 0x100041), then sets own object flag 1 and +0x3d0 = clock + 120 |
| 0x2769c0 | `Innoruuk_vslot3` (monsters) | `Innoruuk_trigger` | slot 3; was Innoruuk_vslot3: a non-zero value stores AI state 0x17 directly and starts the arming sound and animation |
| 0x279420 | `SpellHateEffect_takeDamage` (monsters) | `SpellHateEffect_update` | Spell slot 2 (the per-frame update Creature_updateSpells calls); was SpellHateEffect_takeDamage: every 30th frame until expiry damage_apply to the victim with the skill 30 value |
| 0x280434 | `Kobold_vslot21` (monsters) | `Kobold_isAlly` | vtable 0x515ef0 slot 21 (other): base Creature_isAlly AND other's type name (+0x34) strcasecmp-equal to "koboldshaman" |
| 0x282868 | `LavaMonster_vslot16` (monsters) | `LavaMonster_getModel` | was LavaMonster_vslot16. Slot 16: returns class-definition model (+0xc) unless +0x424 != 0, then 0. +0x424 has no writer in the class |
| 0x282888 | `LavaMonster_vslot38` (monsters) | `LavaMonster_getSecondModel` | was LavaMonster_vslot38. Slot 38: returns class-definition +0x14 unless +0x424 != 0, then 0 |
| 0x28453c | `Marr_vslot12` (monsters) | `Marr_onNearbyEvent` | slot 12; was Marr_vslot12: kind 2 with a source object within +-10000 of the facing while in state 3 or 5 requests state 0x18 (guard) |
| 0x2845e4 | `Marr_vslot11` (monsters) | `Marr_onTouchList` | slot 11; was Marr_vslot11: in state 0xb every touched player not in a knockdown clip gets damage_apply(0, 0, ..., flags 0x100041) |
| 0x284b50 | `Marr_vslot36` (monsters) | `Marr_getDodgeLevel` | slot 36; was Marr_vslot36: 20 in state 0x18, else 5. Slot 36 is read by MissileWeapon_onTouch (0x152eec, 0x152f0c) as the level for the skill 2 Dodge value query |
| 0x287430 | `Minion_vslot3` (monsters) | `Minion_trigger` | was Minion_vslot3. Slot 3: empty function (the Minion ignores signals) |
| 0x28aa48 | `DoorSwing_vslot3` (monsters) | `DoorSwing_trigger` | slot 3; was DoorSwing_vslot3: calls its own interact (slot 14) with player slot -10, which skips the key test |
| 0x28b15c | `DoorSecret_vslot3` (monsters) | `DoorSecret_trigger` | slot 3; was DoorSecret_vslot3: interact(0) while the door is still interactable |
| 0x28badc | `FallPlatform_vslot3` (monsters) | `FallPlatform_trigger` | slot 3; was FallPlatform_vslot3: starts the fall (state 1) with a delay of 16 + own draw & 7 |
| 0x28dfe8 | `RollDoor_vslot3` (monsters) | `RollDoor_trigger` | slot 3; was RollDoor_vslot3: interact(0) |
| 0x28ec7c | `Timer_vslot3` (monsters) | `Timer_trigger` | slot 3; was Timer_vslot3: (value) joins the run list, +0x4c = `time` property x 60, +0x50 = value |
| 0x28eda4 | `Counter_vslot3` (monsters) | `Counter_trigger` | slot 3; was Counter_vslot3: non-zero counts up, zero counts down; fires the actions at `count` |
| 0x29aeb8 | `Mummy_vslot17` (monsters) | `Mummy_updateSpells` | vtable 0x516e48 slot 17, replaces Creature_updateSpells: runs slot 2 of every attached spell (+0x364) with the world position of model attach point 0 (model_getAttachPoint index 0) and the facing, instead of the position passed in |
| 0x29c3b0 | `MummyKing_vslot3` (monsters) | `MummyKing_trigger` | slot 3; was MummyKing_vslot3: value 1 clears cflag 0x4000000 and object flag 0x1000000; value 0 toggles the weapon in hand 1 with a particle effect |
| 0x29eed0 | `NPC_vslot3` (monsters) | `NPC_trigger` | was NPC_vslot3. Slot 3 (value): cutscene + name 'sylea' -> hide bits +0xe8 = 0 / 2; name 'firlow' in level 'hate3' -> +0x478 = 1 and idle1.anm; otherwise Creature_trigger 0x11a5f0 (runs dialogScript) |
| 0x29f720 | `Rondo_vslot3` (monsters) | `Rondo_trigger` | was Rondo_vslot3. Slot 3 (value): value 0 -> hide bits +0xe8 = 2, +0x3cc = 1, hide mask +0x220 rebuilt; other values ignored |
| 0x2a2ec8 | `Orc_vslot12` (monsters) | `Orc_onNearbyEvent` | vtable 0x50ffd0 slot 12 (kind, pos, source): kind 0 from an Orc while in state 0/1 -> state 2 toward pos; kind 2 with a shield in state 3/5 and source within +-9999 of facing -> state 0x11 |
| 0x2a4a9c | `SeaMonster_vslot11` (monsters) | `SeaMonster_onTouchList` | was SeaMonster_vslot11. Slot 11 (list of touched objects): empty function, returns at once |
| 0x2a7688 | `Skeleton_vslot12` (monsters) | `Skeleton_onNearbyEvent` | vtable 0x5175f8 slot 12: kind 2 only; with a shield (0x2a7da0), state 3 or 5 and source within +-9999 of facing -> state 0x11 |
| 0x2a7e04 | `Skeleton_vslot20` (monsters) | `Skeleton_isEnemy` | vtable 0x5175f8 slot 20: base result r -> r+1 when non-zero; otherwise 1 for a living Skeleton of the opposite side byte +0x3d4 (1 vs 2) when not charmed |
| 0x2a946c | `Skelight_clearStatic8e4560` (arena) | `Skelight_shatter` | only caller Skelight_setState 0x2a9360 with (this, 8); body only zeroes the first entry of static table 0x8e4560 (an emptied counterpart of Skeleton_shatter); not a Soul function |
| 0x2aab60 | `Soul_vslot3` (monsters) | `Soul_trigger` | vtable 0x517740 slot 3; empty (returns at once) |
| 0x2ab298 | `Soul_vslot16` (monsters) | `Soul_getModel` | vtable 0x517740 slot 16: class block +0x1c while the owner handle +0x3c8 is set, else +0xc |
| 0x2ad1b8 | `SpiderQueen_vslot3` (monsters) | `SpiderQueen_trigger` | slot 3; empty (jr ra) |
| 0x2b4cc0 | `UndeadKnight_vslot3` (monsters) | `UndeadKnight_trigger` | slot 3 override, empty body (returns at once): script trigger / dialogScript do nothing for this class |
| 0x2b9d10 | `VampireLord_vslot16` (monsters) | `VampireLord_getModel` | slot 16: bat.vif from bat.lmp while +0x3cc != 0, else classDef+0xc |
| 0x2b9d50 | `VampireLord_vslot38` (monsters) | `VampireLord_getSecondModel` | slot 38: bat.tex while +0x3cc != 0, else classDef+0x14 |
| 0x2bac58 | `WarBoar_vslot11` (monsters) | `WarBoar_onTouchList` | slot 11 override (list of touched objects from Creature_moveBy), empty body |
| 0x2bd968 | `WoodElfSoldier_vslot3` (monsters) | `WoodElfSoldier_trigger` | slot 3 override: with a dialogScript property -> Creature_trigger; otherwise creates one MissileWeapon (arrow) straight ahead at speed 400 from z+58 |
| 0x2c061c | `Wraith_vslot20` (monsters) | `Wraith_isEnemy` | slot 20 override: walks the Wraith list 0x5033f8 (count 0x5034e8); returns 0 when another wraith already targets 'other' and is close enough, otherwise clears that wraith's target handle; then Creature_isEnemy |
| 0x2c1bc0 | `WarWraith_vslot20` (monsters) | `WarWraith_isEnemy` | slot 20 override: same code as Wraith_isEnemy on the WarWraith list 0x503590 (count 0x503680) |
| 0x2c3c54 | `Zek_vslot35` (monsters) | `Zek_getSkillLevel` | slot 35; was Zek_vslot35: tail-calls the base Creature_slot35 0x118c50 (monster level x 0.3) |
| 0x3c1d08 | `Weapon1_slot2` (runtime) | `Weapon1_setFireWeapons` | (which < 2): creature_buildElementDamage(…, +0x50, 1). Demon_ctor calls it for the fire variants. Body read |
| 0x3c1fc8 | `Weapon2_slot2` (runtime) | `Weapon2_setFireWeapons` | (which: 0 both, 1 hand 1, 2 hand 2): creature_buildElementDamage(…, descriptor, 1). Called by Creature_init for the FireWeapons property. Body read |
| 0x3c2168 | `Weapon2_slot6` (runtime) | `Weapon2_setShockWeapons` | Same shape with element 4 (type-0x18 rider from SKILL 12 LightningWeapons); Creature_init calls it for the ShockWeapons property; CloudGiant_ctor calls it directly. Body read |
| 0x3c2238 | `Weapon2_slot8` (runtime) | `Weapon2_setElement` | (which, element): creature_buildElementDamage with the given element code on hand 1 (+0x50) and/or hand 2 (+0xe0). Used by CloudGiant_loadState. Body read |
| 0x3cb50c | `IronGuardian_slot36` (runtime) | `IronGuardian_getDodgeLevel` | Slot 36 override: returns the constant 11 (disassembly 0x3cb50c-0x3cb510). What slot 36's value is used for is Unknown, hence the neutral name |

Two `Class_vslotN` names are left as they are: `DoorSwing_vslot17` (0x28ae34) and `RollDoor_vslot17` (0x28dee0) are empty functions in a slot that only the door classes have; what calls it is Unknown.

### 8.2 Read but not named

| Address | What it is |
|---|---|
| 0x1797c8 | Stores its float argument in the global 0x41c14c, which model_resetDrawState (0x179978) sets back to 1.0. IronGuardian_draw passes 3.0, SeaMonster_draw and LavaMonster_draw 2.0, always bracketed by model_resetDrawState. Meaning of the parameter not established |
| 0x238360 | rebuilds the hide mask and creates one GutChunk at the object's position (same shape as Ant_loseBodyPart without setting a part bit, def texture name index 4); no call and no data pointer found (xref, ptrs): unreferenced. Sits between the AntQueen helpers, so probably AntQueen_spawnGib, but nothing proves the class |
| 0x259a2c | 8-byte empty function (jr ra; nop) between FemaleDarkElf_ctor and FemaleDarkElf_draw; not in the inventory; no call or pointer reference found (xref) |
| 0x2672f4 | 296 bytes, NO caller (no jal, no pointer, no decompile reference). (object, part 0-4): ORs hide bit 2/4/8/0x10/1 into +0xe8, creates a GutChunk from the object's own model (pool 0x268, GutChunk_ctorFromProp 0x201ad0, chunk +0x1c4 += 2.0), rebuilds hide mask +0x220. Lies between Ghoul_setState and Gnaw_ctor; the class is not provable. Descriptive alias if one is wanted: creature_shedPartAsGutChunk |
| 0x293228 | not a function entry (inside the argument copy of LostSoul_ctor 0x2931bc); docs/monsters.md catalogue still quotes it as the constructor |
| 0x29dcb8 | 12 bytes: stores 0 to the global 0x501b78 and returns. Called from NPC_ctor2 0x29dec4 and NPC_loadState 0x29e3b8. gxref finds no other reference to 0x501b78 (no reader), so the purpose cannot be named |

### 8.3 Functions that sit in another class's neighbourhood

The first pass attributed unnamed functions to the class whose constructor follows them. Most of these are the previous unit's static initialiser or a helper of the previous class.

#### (range head) 0x24fd8c is a Clockwork helper, not CloudGiant

0x24fd8c (804 bytes; callers 0x24f3ac… inside Clockwork_run and 0x24fbf8… inside
Clockwork_setState, 16 call sites) takes (creature, group 0..7, alt). It writes a
zero-terminated list of 64-bit part masks into the static scratch table 0x8e3378 (one mask
for groups 0–3, three for groups 4–7; two different sets chosen by the byte at creature
+0x3c8 == 1), and for every mask that still has bits in the model-variant word +0x220 creates
one `PhProp` (`pool_new(0x248)` + `PhProp_ctor2`, part mask = those bits, launch flags 0x4116
when `alt` is non-zero else 0x4107, read at 0x24fff0–0x250058) and clears the bits from
+0x220. No generator, no camera. The Clockwork class itself was not in my task.

#### (range head) 0x25dc00 is a MaleDarkElf helper, not Demon

0x25dc00 (108 bytes; only caller 0x25cff8 in MaleDarkElf slot 12, 0x25cfc0) returns 1 when
the model entry in hand 2 of the weapon holder (holder slot 15) is 0x2e, 0x30 or 0x32, else 0.
The caller uses it, on a "nearby event" of kind 2 while in state 3 or 5 and with the source
within ±9999 of the facing, to enter state 0x11. That those three entries are shields is
Inferred from this use only.

#### (range head) 0x2a4240 is an Orc helper, not SeaMonster

0x2a4240 (76 bytes; callers 0x2a2f88 in Orc slot 12 and 0x2a36dc in Orc_setState) returns
true when the hand-2 model entry of the weapon holder (holder slot 15) is in 0x0f..0x17.
Orc slot 12 uses it exactly as MaleDarkElf uses 0x25dc00 (nearby event kind 2, state 3 or 5,
source within ±9999 of the facing → state 0x11). "Holds a shield" is Inferred.

#### The six functions before Agony (0x232300-0x23396c): not monster code

- **0x232300 (3816 bytes) is the draw task of the mission-select menu.** missionMenu_open
  0x231520 registers it with task_add(0x232300, 20, `missionmenudraw`, 1) next to the run task
  missionMenu_run 0x2316fc. It has no call sites; the four references to its address are the
  task registration and removal code (0x231670, 0x2316e0, 0x2320fc, 0x2321ac). (The "27" in
  the inventory is its callee count.) What it draws, from `msel.lmp`: the frame strips, the
  scrolling background (through 0x2331e8), one row per plane from the table at 0x4fe540 (0x34
  bytes per row: name, optional second name, picture names, x/y) with shard / amulet / bonus
  icons chosen by the helper predicates 0x2310a8-0x2314bc, connecting pipes, a pulsing glow on
  the selected entry (sine of g_drawFrame), then the title and description text looked up as
  `<plane>_mis` / `_med` / `_bon` (+ `_title`) and a prompt: `AcceptBack` when
  net_localIsFirstActive, `clientMissionSelect` otherwise in a network game while the pause
  menu is closed. It uses the alternative picture name when game_getEvil is true.
  Per-machine: it is draw code and reads g_drawFrame, net_localIsFirstActive and
  pauseMenu_isOpen only to choose what to show. Its only stores are two globals that nothing
  else references (0x8e2e98 scroll origin, 0x4fe7e4 first-draw latch; xref). The body was
  read in full for the first half and skimmed for the text half.
- 0x2331e8 (lump, scrollA*, alphaA, scrollB*, alphaB, layer): tiles `cosmiclines.tex` and
  `starfield.tex` 2 x 2 across a 640 x 448 screen, each shifted by its scroll vector modulo
  640 / 448 (0x3a5a38 is used as fmod: Inferred), then draws `starsparkle.tex`. Callers:
  0x232300 and 0x223e30 (a second menu, not read).
- 0x2337ac / 0x2337a4: static-initialiser stub (constructor table 0x3e99f4) and its body,
  which is empty — this translation unit has nothing to construct.
- 0x2337cc (char): ASCII to a full-width Shift-JIS code: digits, upper- and lower-case letters
  by offset (table 0x4fe878: 0x824f from '0', 0x8260 from 'A', 0x8281 from 'a'), punctuation
  ranges through the table at 0x4fe774 (space gives 0x8140); anything else 0.
- 0x2338d0 (asciiStr, out): converts a string with 0x2337cc, storing each code high byte
  first, and terminates it with a zero word. Only caller: save_init 0x216fcc at 0x217338
  (memory-card setup; presumably the save title — the use was not read).

#### Stray helpers found in this group's ranges (they belong to OTHER classes)

GCC emits a translation unit's static-initialisation pair at the END of the unit, so the
"unnamed function + 32-byte stub" in front of several constructors belongs to the class
BEFORE it. Checked for each by reading what it constructs and who references those objects
(`ps2elf.py xref`):

| address | what it does | whose it is |
|---|---|---|
| 0x27ef4c (340 bytes) + stub 0x27f0a0 | constructs three particle definitions 0x8e3948, 0x8e3998, 0x8e39e8 (`particleDef_ctor`) when called with (1, 0xffff) | JumpGate unit: the three are referenced by JumpGate_run 0x27cb58 and jumpgate_travelEffect 0x27e770. Not Kobold. Stub is listed in the static-constructor table (pointer at 0x3e9a28) |
| 0x26dfec (128) + stub 0x26e06c | one particle definition 0x8e35f8 | SnowballSpell unit: referenced by SnowballSpell_run 0x26da20. Not Gremlin |
| 0x29fa24 (140) + stub 0x29fab0 | one particle definition 0x8e4470 | NPC / Rondo unit: referenced by NPC_run 0x29ea40. Not Ogre |
| 0x2858ac (612) + stub 0x285b10 | five particle definitions 0x8e3d30, 0x8e3d80, 0x8e3dd0, 0x8e3e20, 0x8e3e70 | Marr unit: all five referenced by Marr's death-effect function 0x284b68. Not Mermaid |
| stub 0x297768 | calls 0x296ddc (2444 bytes, outside this group's ranges; skimmed): fifteen particle definitions 0x8e3fc0–0x8e4420 | the unit that runs from LostSoul to SpiritAnchor: 0x8e4290 is Root's leaf particle, 0x8e42e0 / 0x8e4380 OniBall's two, 0x8e43d0 UnholyAura's. Not Mosquito |
| 0x287940 (88) | (creature, out matrix): `0x175330(scale +0xdc, model, position, facing, anim state, 0, out)` = world matrix of model attach point 0 | callers are only Soul_draw 0x2a96a4, Soul_run 0x2aa748, Soul_setState 0x2ab0d8. Sits after Minion_setState, before Tormentor_ctor; used by neither |
| 0x2982cc (332) | Mosquito_losePart (see Mosquito) | Mosquito, not Mummy |

#### 0x265754 - not Generator code

A Froglock helper (three call sites inside Froglock_run 0x264314; reads Froglock +0x460..+0x462
and the standing-in-water creature flag); described in the Froglock section.

## 9. Corrections to earlier documents

### 9.1 The ones that change a conclusion

| Document | What it says | What the code says |
|---|---|---|
| `tools/localstate.py`, `tools/ps2elf.py func` | used as a first pass for per-machine reads | both cut a function at its first switch case label (see the introduction). For every monster run function the tool saw only the code before the state switch |
| `docs/monsters.md` 7.7 | "the structure at 0x4f8450 has 1 at +0x34" | 0x4f8450 holds a **pointer** to the camera object; the test is camera mode == 1, a per-machine value (7.1 M6) |
| `docs/monsters.md` 4, Innoruuk | "takeDamage ignores all damage while the handle at +0x3e0 is set"; "death creates a Prop and four HateSoul objects" | +0x3e0 is an integer set once from the `invulnerable` property and never cleared by code in this area. The death sequence creates a HateSoul every 47 / 37 and later every 17 / 37 frames for 12 seconds. The Prop of state 0x12 is his dropped weapon |
| `docs/monsters.md` 4, Zek | "state 0xe finds an enemy and links a handle; the tail creates LightEffect objects" | state 0xe launches a ground wave that travels 5 units a frame, homes on that enemy and explodes for half melee damage in a 180 radius |
| `docs/monsters.md` 4, MummyKing | "state 9 creates two SpawnMummy objects" | one per player slot at one-second steps, then a shaman; the type depends on his hit points |
| `docs/monsters.md` 4, SpiderQueen / VampireLord / RedDragon / Nightmare | jump; melee chain with cold rider; breath helper 0x261328 | web strand that drags the victim; only the second hit of two states carries the rider and it heals him; the helper is effects only and the breath damage is a tick in run; the charge damage is in slot 11 (section 3) |
| `docs/monsters.md` 5, Teleporter | "whatever moves the player is not in its run, draw or setState … probably the creature interact path or a level script" | confirmed: nothing in the class; only the base `dialogScript` paths exist |
| `docs/monsters.md` 5, AutoChest family | `autoobject_dropLoot` is called from AutoChest_run, AutoProp_run and 0x23d2ec | one caller, `AutoChest_run` 0x23b674; the `random` worth factor is 300 (doubled from act 1, zero in act 0) |
| `docs/monsters.md` 3.2 | `LostSoul` ctor 0x293228; `LavaBomb` ctor 0x281194; nine `AutoPropLP_*` functions at 0x23cea0–0x23d7ac | 0x293228 is inside the constructor that starts at 0x2931bc; 0x281194 is a case label, the bomb is built inline at 0x2813c8–0x28149c; the nine are AutoProp members inherited by the LP class |
| `docs/monsters.md` 1.4 | state 0x17 "usually rise / appear" | only for Skeleton and Skelight |
| `symbols/monsters.tsv` | `SpellHateEffect_takeDamage` 0x279420 | it is slot 2 of a **Spell** table, the per-frame update, not a take-damage function |
| `docs/creatures.md` | slot 36 "0, 4 or 10 by boss rank; purpose Unknown" | the level for the Dodge skill against missiles (2.1) |
| `docs/creatures.md` C10 and slot 12 note | `world_notifyObjectsNear` "one caller, when there is a single player" | confirmed from the receiving side: the comrade-in-trouble reactions of Bubo, Goblin, Ghoul and Orc exist only in single-player games |

Nothing in FINDINGS was found to be wrong. D6 gains four users (7.1 M2, M3).

### 9.2 Corrections listed by each group

**SpiderQueen, WebTrap, VampireLord, RedDragon, Nightmare, Hag.**

- SpiderQueen: states 6, 7, 10, 0xb do carry the PoisonWeapons rider (confirmed), but 7, 10 and
  0xb are grab attacks that drag the target with its knockback fields before biting; 8-9 are
  not a jump: 0x2afc28 launches a web strand at the target (state 8) and state 9 reels the
  caught victim in. The spit makes two projectiles per event and the animation has three
  events. takeDamage thresholds are absolute hit points (140 … 40), and the effect is visual.
- VampireLord: only state 7 (and 0x18) carries the ColdWeapons rider, on the second hit, with
  twice the queried value, and heals the lord 8% of his maximum when the bite does damage;
  states 8-0xb have no rider and belong to the second form. States 0x10 and 0x14 each make
  six Critter bats (confirmed; the "four own draws" are per bat at minimum: three or more for
  the offset plus one for the angle). State 0x14 deletes the lord only after the flee timer.
  The forced 0x19 goes through the state filter and can be lost (see takeDamage).
- RedDragon: 0xf confirmed, with the detail that the FireStorm object is constructed directly
  (FireStorm_ctor2, no skill-table call) at the farthest player within 600, with a missing
  "nobody found" check. 0x1b picks among 0xb-0xf from cone tests on any enemy plus the
  last-attack memory. Breath damage is a 15-frame tick of a quarter of the melee range plus an
  equal fire rider; helper 0x261328 is effects only (the "arc tests" are the damage calls).
- Nightmare: 6 / 0x17 / 0x18 are the same four-hit kick; the charge (7) does its damage in the
  slot-11 override 0x271484, not in run.
- Hag: confirmed skills 37 / 100 / 101; additionally two forms (immune, grown) and a guard state.

**Ants, Arenabeast, beetles, badgers, Agony, Amphian.**

- 7.9 last-but-two row ("Critter, FireBeetle, FireFly, Mosquito, AntQueen draw ... Unknown"):
  for FireBeetle, FireFly and AntQueen the stores are temporary and undone before return
  (addresses in the three sections above). Critter and Mosquito are not in this group's ranges.
- 7.5 / line 572: AntWave is created only in AntQueen state 0x19, and no requester for that
  state was found (see AntQueen). The hazard described in 7.5 therefore looks unreachable.
- Line 572 "bites carry a PoisonWeapons rider": the bite (state 6, hit call at 0x23747c with the
  descriptor register zeroed at 0x237480) carries none; the rear attack (7) and the sting (9 / 10) carry it.
- Catalogue sizes marked `?`: AntWave 0x3d8 (0x237668), beetleProjectile 0x1d0 (0x24683c).
- FireFly's slot 27 (0x24787c) is an empty function, not a real setState.
- 1.3 says the corpse handler's "animation ended" bit is 0x80: in these classes 0x80 is an
  event-marker mask the constructors place on the death clips (Ant at 0.5 s, Arenabeast at
  2.0 s, Amphian at 0.2 s), passed on to Creature_deadUpdate with the other event bits.

**Goblin, MaleDarkElf, Froglock, the talking creatures, Ghoul, Gnaw.**

- Section 7.7: "the structure at 0x4f8450 has 1 at +0x34" should read "the camera object
  pointed to by 0x4f8450 is in mode 1 (follow)"; the mode is written only by Camera_setMode
  0x2072e8 and Camera_updateFree 0x20440c and is 0 while a menu, shop, dialog camera or
  cutscene holds the local camera. NPC_draw additionally needs the NPC to be more than 240
  units (300 in a cutscene) from the camera; the other three draws have no such test.
- Section 6 table, Goblin rows 7 (FireStorm) and 58 (FrostStorm): these are cast through table
  offset 0x14 (0x26c4cc ff.), not passed to a constructor.
- Section 6, MaleDarkElf MultiFire (46): the 0x5c query result is the NUMBER of
  MultiFireProjectile objects created (query call at 0x25c984), not a melee rider.
- Catalogue "Creates" column: Goblin, MaleDarkElf and Froglock also create plain MissileWeapon
  objects (ctor 0x150ee4) when the weapon has no element.
- Catalogue, SnowballSpell: the class is never instantiated (no caller of 0x26d884).
- Section 1.3 says every run function returns when Creature_run is non-zero: NPC_run 0x29ea40
  ignores the result, and NPC_run / GnomeNavigator_run (in two levels) do not call
  Creature_processDamage.
- Unnamed functions attributed by address: 0x263d70/0x263dfc are FireBomblet's static
  initialiser (not Froglock); 0x268f38/0x268f80 are GnawSpawn helpers (not Gnome).

**Mummy, Tormentor, Minotaur, Kobold, Gremlin, Mosquito, Ogre, Mermaid.**

- Catalogue row LostSoul: constructor is 0x2931bc, not 0x293228 (0x293228 is inside the
  argument copy of the function that starts at 0x2931bc; symbols/monsters.tsv is already
  corrected, the catalogue row is not).
- Catalogue row Tormentor lists ConeOfFrost (56) as "cast": the code exists (state 8) but no
  code in the class requests state 8. Same situation: Kobold FrostArmor (96) (state 9), and the
  Mummy teleport state 0x17.
- Catalogue row Mummy "objects created" omits PoisonRain (0x6c bytes, ctor 0x2f8f48),
  SpellDiseaseShield (0x1b0) and SpellConeOfFire (0x58); section 6 lists DiseaseShield as a
  value query only — it is also constructed (`SpellDiseaseShield_ctor` 0x2ccfc8).
- Section 7.9 "Critter, FireBeetle, FireFly, Mosquito, AntQueen draw: store to position …
  Unknown": resolved for Mosquito only — saved at entry and restored after `Creature_draw`
  (0x297a3c–0x297a54, 0x297afc–0x297b14). The other four were not in this group's ranges.
- Section 10 lists Root, LostSoul, LightningRod as not read: now read (above). Root is not a
  monster projectile: its only creator is Player_run.

**Orc, Skeleton, Soul, the arachnids.**

- Catalogue row Skeleton, "red*, blue* variants": the factory's `red` / `blue` prefix tests
  (0x15b50c–0x15b594) are applied to a name that has just matched `Skeleton` and cannot
  succeed; class blocks `skelred.lmp` / `skelblue.lmp` are never selected there. The red /
  blue distinction that does work is the side byte +0x3d4 set from `skeleton…red` /
  `skeleton…blue` names in the constructor, used by the isEnemy override.
- Section 1.4 says 0x17 is "usually rise / appear". In this batch only Skeleton uses it
  that way: Orc 0x17 = hold near the target, Scorpion 0x17 / 0x18 = two display clips,
  BlackWidow 0x17 = reeling in a webbed target and 0x18 = pit emerge, Soul 0x17 = a timed idle.
- "Skeleton … state 8 … with four own draws": it is three draws per rejection attempt plus
  one for the sound (at least four).
- Catalogue sizes / blanks: PoisonProjectile is 0xa8 bytes (all five `pool_new` sites);
  SmallSpider's states are 0, 1 and 0x14; Orc also creates `MissileWeapon`, `PoisonRain` and
  `GutChunk`; BlackWidow creates `GutChunk` and (through the strand controller) `WebTrap`;
  Skeleton creates `MissileWeapon` and `PhProp` pieces; Scorpion creates `GutChunk`.
- Slot 12 has class overrides here (Orc kinds 0 and 2, Skeleton kind 2); slot 20 is
  overridden by Skeleton.

**WoodElfSoldier, Wraith family, Vampire, UndeadKnight, Warrior, Ulthork, WarBoar.**

1. Catalogue row Wraith, "Creates: Weapon1": the Wraith functions create no Weapon1; the
   embedded Weapon1 is WarWraith's (ctor 0x2c07a8). 0x2bfe2c is not a helper function but
   the state-0x17 code inside `Wraith_run` (function size 3384).
2. Section 2.2 / 7.8, UndeadKnight +0x3c8 "never linked anywhere": a linker exists
   (0x2b5370) but nothing calls it; the conclusion (path unreachable) stands and is now
   backed by a whole-file scan. The same holds for a second handle, +0x3cc, not mentioned
   there.
3. Section 4, UndeadKnight "0x17 emits particles": only when +0x3cc is linked, i.e. never;
   and 0x17 itself is not requested by the class. "Swings chosen with three own draws":
   one draw per decision (three alternative sites), and state 8 cannot be chosen.
4. Catalogue row Ulthork, skills ShockOfFrost / FrostStorm: referenced, but only in state
   7, which needs variant 2, which the constructor cannot assign.
5. Slot 11 "Observed for Cazic only": WarBoar overrides it with an empty body (0x2bac58).
6. Slot 20 "4 overrides here": the Wraith and WarWraith ones have a side effect (they clear
   another wraith's target handle).

**The Auto family, CreatureContainer, Generator.**

1. Section 5 row "AutoObject_draw 0x23aa20 and the LP draws store to +0xc ... Unknown which
   flag": the flag is 0x100. AutoObject_draw only CLEARS it (0x23aa20 l.83); the LP draws
   would set it but the store is unreachable (guard 0x240db0 returns 0). Nothing reads it.
2. `autoobject_dropLoot` 0x23ba3c has one caller, AutoChest_run (0x23b674); it is not called
   from AutoProp_run or 0x23d2ec. AutoProp has no loot at all; AutoContainer has its own
   inline loot code with different odds (section 6).
3. dropLoot `random` items: worth x 300, doubled from act 1 on and zero in act 0; category
   table 0x4fece8 - not the Chest numbers.
4. Slots 17-19 "AutoProp family only / Unknown": 17 next state, 18 set state, 19 set
   passable (AutoProp family); for AddParticle 17 = place light/halo, 18 = emit, 19 empty.
5. Catalogue names: the functions called `AutoPropLP_saveState ... AutoPropLP_vslot19`
   (0x23cea0-0x23d7ac) belong to AutoProp. Factory names were missing for most of the family:
   see section 0 (properties, not type names) and section 11.
6. CreatureContainer: "also references AutoContainer" = it creates and shadows one.

## 10. Patch proposals

Both are **untested**: nobody has run them. One change each. Original words were read from the
executable.

| Id | Address | Original word | New word | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| P-M1 | 0x00261fd0 | `0C079DF0` (`jal isNearView`) | `24020001` (`addiu v0, zero, 1`) | `FireBomb_run` launches on its timer whether or not anything is near, so the launch no longer depends on `isNearView` (camera focus during net cutscenes, 7.1 M2). The delay-slot instruction at 0x261fd4 only sets up an argument and is harmless | every `kelethinBomb` in a level now throws bombs all the time: more objects alive (FireBomblet, up to five FireBombletJr, StaticFire up to 780 frames each), which raises pool pressure (`docs/objects.md` O1) and moves every later shared-seed draw. The `script` gate is unchanged | yes |
| P-M2 | 0x00250930 | `8E420530` (`lw v0, 0x530(s2)`) | `8E420508` (`lw v0, 0x508(s2)`) | the CloudGiant king's "may I conjure a new bolt" test reads the simulation flag "a thrown bolt is in flight" (+0x508) instead of the `beam_create` handle (+0x530). In normal play the two are zero and non-zero together (set at the throw 0x2519e8 on, cleared when the bolt lands; the slam and death paths clear +0x530 while +0x508 is already 0) | differs from the original only when `beam_create` failed (then the original conjures early) and in one corner: a king killed while his bolt is in the air and then revived waits for that bolt to land before conjuring. The held bolt's beam still depends on `beam_create`, but only for drawing | yes |

## 11. Proposed ledger rows

For the maintainers of `FINDINGS.md`; numbering left to them.

| Kind | Finding | Status | Evidence |
|---|---|---|---|
| D | The CloudGiant king's AI reads a `beam_create` handle; the beam and trail tables are also filled by camera-gated effect code, so a failed create on one machine changes that machine's state choice | Observed read; divergence Inferred | 0x250930, 0x2519e8; `beam_create` 0x193088; 0x1f6478, 0x1f826c |
| D | `FireBomb_run` draws `g_randSeed` and creates objects only when `isNearView(960)`; `Catapult_run`, `LightningRod_run` and `AutoProp_run` gate scripts, object creation and damage on `obj_updateActive`. Four more consumers of D6 | Observed | 0x261fd0; 0x24d9e4; 0x295954; 0x23cc0c |
| D | Cosmetic-generator animation phase reaches game state for a `path` Critter (position, bullfrog squash test and its `deathScript`) and for a plain `pipepistona` AutoProp (damage frames) | Observed mechanism; whether a shipped level has either Unknown | 0x2547fc, Critter run state 0x16; 0x23c44c, AutoProp_run |
| D | The `exclamation` scripts run from draw code are conditioned on the camera mode of the machine (and, for NPC, on distance to its camera) | Observed; harmless while the scripts only read | 0x29e5ac–0x29e5f4, `Camera_setMode` 0x2072e8 |
| D | Each light that is drawn takes two nodes from the global handle-node pool from draw code; `handle_link` has no empty-pool test | Observed; consequence only at exhaustion | 0x2b2ba4, 0x2b30cc, 0x2b33d4, 0x2b36f8, 0x2b3adc; 0x1a1738 |
| G | Rules that differ by game mode, the same on every machine: BlackWidow's web shot only offline; slot-12 kind 0 reactions only with one player | Observed | 0x2ac22c–0x2ac23c; 0x110d90 |
| G | Innoruuk, MummyKing and Minion do not gate their AI on `Creature_updateActive` | Observed | 0x273bd0, 0x29b360, 0x2862c0 |

## 12. Open questions and what was not done

1. **Object lists.** Only four levels' object lists are on disk (DRUNARE, DRUNARM, DRUNDAR,
   PVPARENA). Whether any level places a plain `pipepistona`, a bullfrog Critter with a
   `path`, a Teleporter, or an `exclamation` / `key` script with side effects could not be
   checked. Extracting the other levels settles 7.1 M4–M7.
2. **States nobody requests.** MummyKing 0x17 / 0x18, Mummy 0x17, Innoruuk 8 and 0xd,
   Tormentor 8, Kobold 9, AntQueen 0x19, Arenabeast 0x17 / 0x18, Agony 0x11, Badger 7 have no
   requester in their own class. Slot-27 calls whose argument is computed, and calls from
   outside the area, were not traced; until they are, "unreachable" is Inferred.
3. **The beam table (M1).** How many beams and trails can be alive at once in the CloudGiant
   fight, and so whether 20 slots can fill on one machine only.
4. **0x4d8298** (RedDragon, 7.3): what the word is.
5. **Not followed out of the area:** `fx_modelStatusEffects` 0x1f6ac8 (called from several run
   heads and from every weapon-holder update), `fx_modelParticlesNearCamera_1f5210`, the
   weapon-holder update bodies, `Creature_dropLoot`, the skills monsters cast, `MissileWeapon`
   internals, `PhProp` launch flags, `Player_interact`.
6. **Animation event tables.** The time unit of the (time, mask) pairs was not verified, and
   the mapping to `Creature_stepAnim`'s result is Inferred.
7. **Door slot 17.** `DoorSwing_vslot17` and `RollDoor_vslot17` are empty functions in a slot
   the door classes add; no caller was looked for.
8. **Handle-node pool (M8).** Its size and whether a level with many lights and objects can
   exhaust it.
9. Destructors and the slot-15 clone functions of the classes read here were not read.

### What each group did not get to

**SpiderQueen, WebTrap, VampireLord, RedDragon, Nightmare, Hag.**

- Not read: destructors and clone functions (slots 1 and 15) of all classes; BlackWidow_run
  beyond the call sites of the four helpers that sit in the SpiderQueen range; Critter beyond
  its constructor and states 0x17/0x18; PoisonProjectile beyond its constructor and the impact
  branch; FireStorm, LightEffect, the Horsemen side of the mount protocol; the skill
  implementations behind ids 14, 26, 37, 100, 101.
- Event-table times are quoted as written; their unit and the exact frame of each event were
  not verified in anim_advance.

**Ants, Arenabeast, beetles, badgers, Agony, Amphian.**

- Creature base functions (Creature_run, Creature_processDamage, Creature_deadUpdate,
  Creature_dropLoot, damage_apply) were used through their symbol notes, not re-read; the
  loot-call float arguments are quoted without meaning.
- The clone functions in slot 15 of Ant, AntWave, FireBeetle, FireFly and beetleProjectile
  (0x11f188, 0x11fcd0, 0x122120, 0x122700, 0x12dde8) are outside this group's ranges and not read.
- AntWave_run / AntWave_draw were not re-read (already documented).
- PoisonProjectile, LooseFire, LightEffect, GutChunk and MissileWeapon_onTouch behaviour:
  only the constructor arguments passed from my classes were established.
- Variable-argument slot-27 calls in other classes were not traced, so "no requester" for
  AntQueen 0x19 / 10, Arenabeast 0x17 / 0x18, Agony 0x11, Badger 7 is limited as stated at
  the top.

**Bubo, FemaleDarkElf, Critter, Creep, Cyclops family, Clockwork.**

- All six priority items were read. Not read: the unique clone bodies (slot 15) and other
  out-of-range unique slots named in each section; `Creature_stepAnim` (so "time -> event
  bit" stays Inferred); `fx_modelStatusEffects`; `MissileWeapon_ctor` and
  `PoisonProjectile` beyond their constructors; 0x24fd8c beyond its head.
- No level data was searched for `path` bullfrogs, `Critter=` records or the
  `deathScript` values; scripts/*.txt were only grepped for the class names (hits quoted in
  the sections).
- The three static-initialiser pairs in these ranges (0x247e9c/0x247f90, 0x2530a8/0x253128,
  0x2593d0/0x25945c) build particle definitions used by the code that PRECEDES them
  (0x8e30f8 and 0x8e3148 -> beetleProjectile_run 0x247980; 0x8e3418 -> CloudGiant_run
  0x250714, reference at 0x2511f4; 0x8e3468 -> Cyclops dust 0x257ba0), found by xref of the
  definition addresses. The 32-byte stubs are entries of the constructor table (pointers at
  0x3e9a04, 0x3e9a10, 0x3e9a14). Bubo's own DiseaseProjectile particles
  (0x8e3198, 0x8e31e8, 0x8e3238) are built by 0x24a504, just past the Bubo range.

**Goblin, MaleDarkElf, Froglock, the talking creatures, Ghoul, Gnaw.**

- All classes in this group's list were read. Functions outside the ranges were read only where a
  class function called them (0x25dc00, 0x265754, weapon-holder slots, camera mode writers).
- No level object list with these classes is on disk, so property VALUES (and the
  `exclamation` values) could not be listed.
- Creature_dropLoot, creature_allyInLineOfFire, the projectile constructors and
  fx_modelStatusEffects were not read; their arguments are quoted as passed.
- Gameplay names of cflags 0x200000000 / 0x400000000 / 0x1000000000 / 0x2000000000,
  0x200000000000 and 0x800000000000 remain Unknown.

**Mummy, Tormentor, Minotaur, Kobold, Gremlin, Mosquito, Ogre, Mermaid.**

- Destructors (0x3cbf34, 0x3cba74, 0x3cbb24, 0x3cb5d0, 0x3cacf0, 0x3cbe84, 0x3cc458, 0x3cb900,
  0x3c5db0, 0x3c60e0, 0x3cbcd4) were not read (outside the ranges), except Root's and
  LostSoul's.
- Trap and DragonGoldPile skipped as instructed.
- Not traced outside the classes: who calls slot 27 with 0x17 on a Mummy, 8 on a Tormentor,
  9 or 0x17 on a Kobold. What was checked: the base Creature slots these classes inherit
  (3 trigger, 6 touch, 7, 10, 12 — bodies read, none sets a state); the script built-ins in
  docs/script.md only pass 0 and 0x14; `ScriptGenerator_spawn` 0x265fc4 passes 0x17 to
  Skeletons only (type test read); a text search of all decompiles for slot-27 calls with the
  literals 0x17, 8 and 9 finds only other classes calling it on themselves. Calls with a
  computed state were not searched. Also not traced: the reader of creature flag 0x800000000000 other than Mummy_run
  (two other run functions mention it: 0x25bbe4, 0x25e17c); internals of MissileWeapon and of
  the arrow / spell constructors that receive the skill pointers.

**Orc, Skeleton, Soul, the arachnids.**

All five priority items were read in full inside this group's ranges. Not read (outside the
ranges, cited only through symbol-file notes or the call sites): the three arrow projectile
constructors and `MissileWeapon_ctor` beyond its argument list; `PoisonRain_ctor`; the skill
cast bodies (Healing, Shock) and the PoisonWeapons 0x5c query; the weapon holder's update,
draw and drop functions; the strand controller's draw feed 0x2afe38 / 0x2af510 (partly);
`WebTrap`; Minion beyond the Soul creation / throw / death call sites; the creators of
PoisonProjectile; destructors and clone functions of the six classes. Level scripts were
only grepped for type names.

**WoodElfSoldier, Wraith family, Vampire, UndeadKnight, Warrior, Ulthork, WarBoar.**

- Bodies outside the ranges were read only where named in the text (`Creature_hitTargetAtReach`,
  `creature_findCorpseOfClass`, `str_prefixDiffers`, three WeaponShield slots, the head and
  tail of `MissileWeapon_ctor`, 0x1f5210, `objects_levelReset`, 0x2c1d4c). Not read:
  `Skeleton_ctor`, `PhProp_ctor2`, `FrostStormSpell_ctor`, `ShockOfFrost_ctor`,
  `Creature_dropLoot`, `loot_generateDrops`, the weapon holder's other slots, the clone
  functions beyond their field lists, the destructors beyond WoodElfSoldier's.
- Level object lists were not available for Faydark / Ulthork levels: which type names are
  placed (evil vs plain wood elves, `ulthorkrecruit…`) is unknown.
- The 68 callers of slot 20 were classified by name only.
- Animation data (event markers, root motion) was not examined.

**The Auto family, CreatureContainer, Generator.**

- 0x1797c8 (called with 2.0 before each model draw) and 0x14a0f8 (fullbright path) were not
  read; PhProp launch-flag meanings (0x20e, 0x216, 0x22e, 0x1020e, 0x441) were not decoded;
  PhProp byte +0x23a (set on 1 debris piece in 8) not identified.
- Player_interact (who calls slots 13 / 14 and whether slot 14 is skipped after a failed
  prompt) was not read here; the statement "keys are tested only in the prompt" is about this
  family's code.
- Whether any shipped level places a plain `pipepistona` (section 3 per-machine item) could
  not be checked: only four levels are extracted and none has one.
- Emitter keys `plf`, `prm`, `ptx` (and `pea`): stored, but no reader in 0x23fdc0, 0x240b64 or
  the burst function 0x195400 (whole decompile searched for the record offsets 0xe-0x10).
  0x195400 itself was read only as far as needed to map the record fields.
- Container flag masks 0x200 / 0x400: no setter found in the family.
- Two more two-instruction functions at 0x240db8 and 0x240dc0 (each returns 1) sit between
  0x240db0 and AutoEmitter_ctor; they are not in the inventory and have no caller or pointer
  (xref). Not named.
- The engine piece functions called with index -1 (section 11 caveat) and the Creature base
  slots of CreatureContainer / Generator were not re-read.
- Everything in this group's list was read; the Generator run and the loot function were skimmed
  as instructed (run compared line by line with the first-pass text, which holds).

