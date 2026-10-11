# Monsters and level objects (0x232000–0x2c3cd4)

885 functions, 148 virtual tables: 73 creature classes (monsters, bosses, a few creature-shaped
helpers such as `Generator`, `Teleporter`, `CreatureContainer`, `AntWave`) and 75 plain
`GameObject` classes (chests, containers, doors, switches, save points, jump gates, lights,
traps, monster projectiles). Everything here was read from the executable; nothing was run.
That still describes this document. The project has a live game now — the Play! emulator, which is not a PlayStation 2 and not PCSX2
(`FINDINGS.md`, "Run on the live game" (rows V1–V13) and `docs/issues/live-rig.md`) — but none of
its runs looked at a monster class or a level object of this document. No test patch has been run on a live game.

Claims are marked **Observed** (read at the address given), **Inferred** or **Unknown**.
Where a paragraph gives an address and no mark, it is Observed.

How this document was made: the catalogue tables, the per-state call summaries and the
per-machine scan were produced by scripts over `vtables`, the object factory and the
decompiles; the bosses named in the task, the Drundar arena classes and the level objects
that carry game rules were then read by hand. "What was not done" is at the end.

## 1. How the pieces fit

### 1.1 Where objects come from

- The object factory is the 15,668-byte function at 0x159c94 (objects area). It compares the
  type name from the level file against a chain of strings (`libc_strcasecmp`, or the prefix
  test at 0x159c20, shown below as `Name*`), calls `pool_new(size)` and then the class
  constructor. The "factory type names" and sizes in the catalogue come from that chain.
  Observed for the names checked by hand (Horsemen, Cazic, Skelight, Savepoint, JumpGate,
  Container, Chest); the rest were attributed by a branch-following script and a few may be
  attached to the wrong neighbour.
- A constructor calls the base constructor (`GameObject_ctor` 0x14cb10, or the creature
  constructor `Creature_ctor` (0x109d68)), stores its virtual table at +0x48, sets class fields, and puts
  the object on a run list: `obj_runEveryFrame` (0x14f248) (run every frame) or `obj_runEvery60` (0x14f2b8) (staggered lists).
  `obj_stopRunning` (0x14f290) takes an object off its run list and `obj_delete` (0x14f200) queues it for deletion.
- Monsters created at run time come from three places in this area: `Generator_run`
  (0x265938), `ScriptGenerator_spawn` (0x265fc4) and individual AI states (see the
  "Creates" column). All three go through the factory entry `world_createObject` (0x14f6c8) or call a constructor
  directly, always from run code.

### 1.2 Virtual slots used in this area

Slot numbers are `tools/vtab.py` numbers (slot n is at table offset n×8).

| Slot | Meaning | Kind | Evidence |
|---|---|---|---|
| 1 | destructor (most are outside this range, in 0x3c3000–0x3cd000) | Observed | called with argument 3 to delete itself, e.g. at the end of Container_run 0x290e78 |
| 2 | take damage | given | overrides are thin wrappers around the creature version 0x116638 |
| 3 | receive a signal / start (value) | Observed for Timer 0x28ec7c and Counter 0x28eda4 | other classes' slot 3 not read; named `Class_vslot3` |
| 4 | run | given | |
| 5 | draw | given | |
| 6 | touched by another object | given | |
| 8 | load saved state from a buffer, returns bytes read | Observed | Savepoint 0x28dcd0, JumpGate 0x27d998 |
| 9 | save state to a buffer, returns bytes written | Observed | Savepoint 0x28dc9c (6 bytes), JumpGate 0x27d974 (2 bytes), Skeleton 0x2a7508 (calls the creature version 0x116780 first, then adds 12 bytes) |
| 11 | creature only: called with a zero-terminated list of touched objects | Observed for Cazic 0x24c04c only | two more overrides, from `docs/monsters-2.md` section 9.2: WarBoar's is an empty body (0x2bac58), and Nightmare's (0x271484) is where the charge of state 7 does its damage |
| 13 / 14 | interact prompt / interact | given | Chest 0x29297c / 0x292a2c, Savepoint 0x28da58 / 0x28dc30, Lever 0x28e4c0 / 0x28e60c |
| 16 | creature: returns the model handle used for drawing and effects | Inferred | result is passed where other classes pass `*(+0x24)+0xc` (compare Cazic_run 0x24aaf0 head with Horsemen_run 0x27236c head) |
| 17–19 | AutoProp family only | Unknown here; read since (`docs/monsters-2.md` sections 6 and 9.2): 17 next state, 18 set state, 19 set passable for the AutoProp family; for `AddParticle` 17 places the light and halo, 18 emits, 19 is empty | named `_vslot17..19` when this was written; since renamed |
| 20 | "is this object my enemy" | given | 4 overrides here; Skeleton overrides it too (the red / blue side byte +0x3d4), and the Wraith and WarWraith overrides have a side effect: they clear another wraith's target handle (`docs/monsters-2.md` 9.2) |
| 23 / 25 / 26 / 28 | creature base helpers called from every run function with small integer arguments (table offsets 0xbc, 0xcc, 0xd4, 0xe4). `docs/creatures.md` names them: 23 pick target, 25 can see target, 26 turn toward a point, 28 on death | Observed there (this row said Unknown) | not overridden in this area |
| 27 | **set AI state** (new state) | Observed | every run function ends by calling it with the next state; overridden by 71 of 73 creature classes; each override starts with the common filter `Creature_filterState` (0x10a9c0), picks the animation for the state and stores the state at +0x232 |
| 35 | creature: returns the level value handed to a skill when the monster casts it. True for casts through skill slot 2; the arrow constructors of the bow-carrying monsters are given `(int)g_levelMonsterLevel` unscaled instead (0x25c7d8, 0x2a7274; `docs/spec/skills-35-68.md` section 4.6) | Inferred | its result is always the first argument of the skill's cast call (Horsemen_run state 0x17, Cazic_run states 7, 0xc, 0xd) |
| 38 | creature: the texture `Creature_draw` passes to `model_draw` with the model (class block +0x14 unless overridden). The earlier version called it a "second model"; the functions named `…_getSecondModel` in `symbols/monsters.tsv` are overrides of this slot and return a texture (`docs/formats/model-texture.md`) | Inferred | Cazic_draw 0x24aa6c |

A skill is called through its own table at skill+0x60: offset 0x0c answers "can this caster
use it now" (one argument, the caster), offset 0x14 casts (level, caster, position, facing)
and returns the spell object, which the caller sometimes links with `creature_addSpell`.
Offsets 0x44, 0x5c and 0x64 are parameter queries; 0x5c is the one monsters use to add an
elemental rider to a melee hit. Observed at the call sites listed in section 6; the
meaning of 0x44 and 0x64 was left Unknown here. In the slot numbering of `docs/skills.md`
these are slot 1 (0x0c, can use), slot 2 (0x14, cast), slot 8 (0x44, value range around a
statistic), slot 11 (0x5c, statistic from the non-player tier) and slot 12 (0x64, statistic
chosen by whether the caster is a player).

### 1.3 Shape of a monster run function

Observed in every one of the 14 run functions read by hand; the script found the same call
set in 68–72 of the 73.

1. optional: update the embedded weapon helper through its own table (object at +0x50).
   It is the first step only in some classes: `Horsemen_run` does it first (holder slot 21),
   `Zek_run` after the activity test of step 4, and `Skelight_run` after step 4 as well and
   through a different slot (22, with an item model) — executed,
   `docs/spec/arena-monsters.md` 3.3, 4.3, 5.3;
2. `Creature_processDamage` (0x110d30) with (this, model) — creature damage reaction (creatures area);
3. `Creature_run(this, model)`; a non-zero result ends the function (not in every class:
   `NPC_run` 0x29ea40 ignores the result, and `NPC_run` and `GnomeNavigator_run` do not call
   `Creature_processDamage` at all — `docs/monsters-2.md` 9.2). The test is there, but the
   exit is dead: `Creature_run` has one return and it loads 0 (0x113c10), so the result is 0
   on every path (executed, `docs/spec/creature-tick.md` section 1). `Creature_run` has no
   entry test for dead, inert or far-away creatures either, and does no damage or target
   work; those are the separate calls of steps 2 and 4 and of slot 23;
4. `Creature_updateActive(this)`; several classes return when it says "inactive";
5. `Creature_stepAnim` (0x1162b0) with (speed, this) advances the animation and returns a bit mask of animation
   events for this frame (bit 0 is "the hit frame" in every attack state read; bits 1–3 are
   further event markers; 0x80 is "animation ended" in the death handler `Creature_deadUpdate` (0x1108a0).
   That reading of 0x80 does not hold for every class: for Ant, Arenabeast and Amphian it is
   an event-marker mask their constructors place on the death clips (at 0.5 s, 2.0 s and
   0.2 s), passed on to `Creature_deadUpdate` with the other event bits — `docs/monsters-2.md` 9.2);
6. `Creature_applyKnockback` (0x115eb8) with (x, this) and the base call at table offset 0xbc;
7. `switch (state at +0x232)`, then one call to slot 27 with the next state.

Helpers that appear in almost every state (all in the creatures area; the names are the
creatures symbol file's, the descriptions are what the monster code relies on):

| Address | What the monster code uses it for | Evidence |
|---|---|---|
| `Creature_canSeeTargetIn` (0x118d40) | "is my target between these two distances, inside this arc" | reads the target handle +0x234, forwards to `creature_canSeeObj` (0x10c810) |
| `creature_findEnemyInCone` (0x10cf78) | find an enemy in range/arc, returns the object | result dereferenced as an object in Cazic_run states 10–0xc |
| `Creature_moveToTarget` (0x1143e8) | chase the target (path move) | used alone in the chase state of every class |
| `Creature_moveToDest` (0x119f38) | walk to the wander point +0x104, pick a new one when stuck | body read |
| `Creature_isAwayFromHome` (0x10eed8) | "am I outside my leash" (home +0x3b4, radius +0x3c0) | body read |
| `Creature_turnToTarget` (0x1187e0) | turn toward the target (calls table offset 0xd4) | body read |
| `Creature_hitAllEnemiesInArc` (0x119b58) / `Creature_hitTargetInArc` (0x119938) | melee hit test in an arc with damage min/max and attack rating from +0xd0/+0xd2/+0xd4, then a flag word (8, 0x40001, …) that carries the damage class; non-zero when something was hit. The earlier version called +0xd4 the damage type | called on the hit-frame event bit; 0x119938 forwards the third value as `damage_apply`'s `attack` |
| `Creature_isNotRooted` (0x1195e0) / `Creature_isAttackReady` (0x1195f0) / `Creature_isNotStunned` (0x119608) | test timers +0x314 / +0x318 / +0x31c for zero. `Creature_isAttackReady` is not only a test: for a creature without a target it first stores zero to the cooldown +0x318 (0x1195f4–0x1195f8; executed, `docs/spec/creature-tick.md` section 16) | bodies read |
| `Creature_deadUpdate` (0x1108a0) | dead-body handler: blood decal, then sink into the ground and delete when creature flag 0x1000000 is set | body read |
| `Creature_dropLoot` (0x10f2c8) | called once on entering state 0x14 (death); not read here | setState case 0x14 of Cazic and Horsemen |
| `model_getAttachPoint` (0x1754a0) | world position of a model bone / attachment point | used before every projectile or effect spawn |

### 1.4 AI state numbers

State numbers are per class, but these are shared. **Observed**: the transitions; the
English names are **Inferred** from them.

| State | Behaviour seen | Evidence |
|---|---|---|
| 0 | idle; look for a target (base call at offset 0xcc); leave to 3 with a target, to 1 when outside the leash | Cazic 0x24aaf0, Horsemen 0x27236c, Skelight 0x2a8b84 |
| 1 | walk back / wander (0x119f38). Leaving it on sight of the target is per class: the skeleton and Zek go to 3, a knight (`Horsemen`) goes to **0** and starts the chase a tick later (0x27236c case 1; executed, `docs/spec/arena-monsters.md` 3.3) | same |
| 3 | chase; chooses an attack state when in range | same |
| 5 | between attacks: waits for timer A (+0x314), chooses the next attack | same |
| 6 … 0xf, 0x15 … | class-specific attacks and casts | see catalogue and section 4 |
| 0x10 | forced while timer B (+0x318) runs; moves through `Creature_fleeFromTarget` (0x119f08) → `Creature_fleeFrom` (0x115910) away from the target | filter `Creature_filterState` (0x10a9c0); Cazic setState case 0x10 sets the timer to 60 |
| 0x12 | wait until animation flag 0x10 clears (hit reaction) | Cazic, Horsemen |
| 0x13 | forced while timer C (+0x31c) runs (held / stunned) | filter `Creature_filterState` (0x10a9c0) |
| 0x14 | **dead**: the run function only calls the dead-body handler `Creature_deadUpdate` (0x1108a0); setState 0x14 calls `Creature_dropLoot` (0x10f2c8) and class death effects | Cazic_setState 0x24c118 case 0x14, Skelight_setState 0x2a91b8 |
| 0x17 | "rise / appear" for Skeleton and Skelight only (the earlier version said "usually", bosses' entrance included). Other classes use the number for something of their own: Orc holds near the target, Scorpion's 0x17 / 0x18 are two display clips, BlackWidow's 0x17 reels in a webbed target (0x18 is the pit emerge), Soul's is a timed idle (`docs/monsters-2.md` 9.1, 9.2) | Skelight ctor 0x2a8770 enters it; ScriptGenerator_spawn puts Skeletons in it |

The filter `Creature_filterState` (0x10a9c0) runs at the top of every setState override. It returns without a
change when a PvP condition holds or when +0x231 is set and the request is state 1; it
redirects requests to 5, 0x13 or 0x10 while timers A, C or B are running; a request for
0x14 clears all four timers; a result of 0 also clears the target handle +0x234.
More exactly, executed in `docs/spec/creature-tick.md` 12.3: the three redirects are one
chain, not three independent tests. While timer A (root) runs, a request other than 0, 5
and 6–15 becomes 5 only when there is a target and 0 when there is none, and the stun and
cooldown tests are then skipped; otherwise timer C forces 0x13; otherwise, after the
cooldown has been zeroed for a creature without a target, timer B forces 0x10.
Timers A, B and C are the root, attack-cooldown and stun timers of `docs/creatures.md`,
whose list of state numbers describes the same states from the base class's side.

Earlier project notes describe state 0x14 as "cutscene actor". In every class read here it
is the death state; a defeated boss that then speaks in a cutscene is in it because he is
dead. (Affects the wording of FINDINGS D19, not its conclusion; D19 has since been
reworded.)

## 2. Data structures

### 2.1 Creature fields as used by monster code

Offsets into any creature-derived object. "How" names where the use was read.

| Offset | Type | Meaning | How |
|---|---|---|---|
| +0x0c | u32 | object flags; in this area also 0x2 hidden, 0x8 dead, 0x400000 "busy" (tested by Savepoint), 0x4000 set by the dead-body handler, 0x8000000 set only around one move call | 0x28d6dc, `Creature_deadUpdate` (0x1108a0), 0x119e38 |
| +0x24 | ptr | per-class static block: model at +0xc, the model's texture at +0x14 (the class tables list `x.vif` followed by `x.tex`; the earlier version called it a second model — `docs/formats/model-texture.md`), animation handles from +0x1c upward in 8-byte steps | every setState override indexes it |
| +0x2c | ptr | zero-terminated list of `key=value` parameter strings from the level file (read with `obj_getPropStr` (0x14f4c0) string / `obj_getPropInt` (0x14c880) integer / `obj_getPropFloat` (0x14c9c0) float) | `obj_runActionScripts` (0x14dcc8) walks it |
| +0x34 | ptr | type name; generators write it on what they spawn | Generator_run 0x265938 |
| +0x50 | ptr | weapon helper sub-object, embedded in armed monsters. Its class is `WeaponShield` (table 0x50cda0, base `Weapon1`) in Horsemen and UndeadKnight and plain `Weapon1` (table 0x50cf40) in Skelight; other armed classes use one of these or `Weapon2` (0x50ce70). The earlier version gave table 0x50cda0 for all three and no class name | Horsemen, Skelight, UndeadKnight ctors (the last table address each loads for the helper: 0x271d94, 0x2a87e8, 0x2b3f64) |
| +0xa8 | u64 | creature flags; here: 0x1000000 corpse sinks and is deleted, 0x4000000 MummyKing ignores damage, 0xc00000 and 0x8000000 select the leash rule, 0x20000000000 set on boss death | `Creature_deadUpdate` (0x1108a0), 0x29c544, `Creature_isAwayFromHome` (0x10eed8), 0x24c118 |
| +0xd0, +0xd2, +0xd4 | s16 ×3 | melee damage low, high and attack rating passed to the hit helpers (the earlier version said "type"; the damage class is in the flag word passed after them) | every attack state; `Creature_setStats` 0x10a620 |
| +0xe8 | u32 | model variant bits: each set bit applies one variant record of the model, which shows some meshes and hides others (the earlier version called it a mask of hidden parts). +0x220 (u64) is the mask computed from it by `model_buildHideMask` (0x179550); despite that name the result is a *show* mask — a set bit draws the mesh (`docs/formats/model-texture.md`) | Horsemen ctor, SpiderQueen_takeDamage 0x2aed60 |
| +0xec | s32 | frame number from which hits register (`+0xec <= g_frame` in 0x15153c and 0x1ba940); every constructor here stores the current frame counter 0x44fdcc. Caution added later: 0x15153c and 0x1ba940 are `MissileWeapon_run` and `playerProjectile_run` and test the missile's own +0xec, so only the constructor store is established for creatures; `docs/creatures.md` lists creature +0xec as Unknown | ctor of every monster |
| +0xf0 | s32 | start frame of a timed effect; read by `Creature_run` 0x113768 in the status-counter-7 branch | field search |
| +0xf4 | s32 | class timer (Skelight: attack frames left — in fact the constant 1, taken off once the swing clip has stopped, `docs/spec/arena-monsters.md` 4.3; Horsemen: idle until age) | Skelight_run 0x2a8b84, Horsemen_run 0x27236c |
| +0x104 | Vec3 | wander destination | `Creature_moveToDest` (0x119f38) |
| +0x114 | struct | animation controller; byte +0x118 is the number of queued animations, u16 +0x11a flags: 0x8 "still playing", 0x10, 0x80 "ended" | tests after every attack state |
| +0x228 / +0x22c | float | hit points / maximum | 0x24c564, 0x2b93d8 |
| +0x230 | s8 | per-object phase, xor-ed with the frame counter to stagger periodic checks | Generator_run |
| +0x232 | s16 | AI state | given |
| +0x234 | handle | current target (object at node+0xc) | `Creature_canSeeTargetIn` (0x118d40), `Creature_turnToTarget` (0x1187e0) |
| +0x300 | s32 | age in simulated frames; compared against the class timers | Horsemen_run 0x27236c, Cazic_run 0x24aaf0 |
| +0x314, +0x318, +0x31c, +0x31a | s16 | timers A, B, C (and a fourth); in `docs/creatures.md` the root, attack-cooldown and stun timers (and one paired with a speed-changing spell) | `Creature_isNotRooted` (0x1195e0) … `Creature_filterState` (0x10a9c0) |
| +0x3b4 / +0x3c0 | Vec3 / float | home position / leash radius | `Creature_isAwayFromHome` (0x10eed8) |
| +0x3c8 … | | first class-specific field | |

### 2.2 Class fields read by hand

| Class | Offset | Type | Meaning | How |
|---|---|---|---|---|
| Horsemen | +0x3c8 | handle | mount (a Nightmare); empty for UndeadKnight1–4 | ctor 0x271c70 links it only when the last argument is non-zero |
| | +0x3d0 | object | embedded weapon helper | ctor |
| | +0x470 | u8 | variant 0–3 (selects mesh parts and the skill) | ctor, run state 0x17 |
| | +0x472 | s16 | countdown used by state 0x1a | run |
| | +0x474 | s32 | age at which the next skill may be cast; set to age + 480 + (own random mod 120) | ctor, run state 0x17 |
| Cazic | +0x3c8 | s8 | hits landed since the last special; 5 unlocks the ground pound / cast choice | run states 5–9 |
| | +0x3c9 | u8 | 1 when the type name is `cazicavatar` | ctor 0x24a670 |
| | +0x3cc | s32 | age before which the charge (state 0xf) is not used again (age + 300) | run state 0xf |
| | +0x3d0, +0x3d4 | u32, float | death-sequence event bits and elapsed seconds | 0x24c994 |
| | +0x3d8, +0x3dc, +0x3e0 | handles | three beam effects of the death sequence | 0x24c994 |
| Skelight | +0x3c8 | object | embedded weapon helper | ctor 0x2a8770 |
| | +0x460 | s32 | level supplied by whoever created it | ctor |
| UndeadKnight | +0x3c8 | handle | mount; cleared by the ctor and never linked anywhere. More exactly: a function that links it exists (0x2b5370) but nothing calls it, so the conclusion stands, now backed by a whole-file scan; the same holds for a second handle at +0x3cc (`docs/monsters-2.md` 9.2) | ctor 0x2b3e30, field search; no reference to 0x2b5370 |
| | +0x470, +0x474 | u32, u8 | "mounted" argument and variant | ctor |
| Generator | +0x3c8 | ptr | type name to spawn | run 0x265938 |
| | +0x3d4, +0x3d8 | s32 | maximum and number spawned so far | run |
| | +0x3dc | u32 | detection flags (bit 0, bit 1) | run |
| | +0x3e0 | handle | last spawned creature | run |
| Savepoint | +0x80 | s32 | 0 dormant, otherwise frames since activation (saved) | run 0x28cdd0, 0x28dc9c |
| | +0x84 | s32 | "a save was requested here" | interact 0x28dc30, run |
| | +0xc4 | u8 | active (from `obj_updateActive`, radius 480) | run |
| | +0xc5, +0xc6 | u8 | has been used; auto-save armed (both saved) | 0x28dc9c |
| | +0xc7, +0xc8 | s8, u8 | living players within 120 units; +0xc7 is −1 when any of them has object flag 0x400000 | 0x28d6dc |
| | +0xc9 | u8 | a player of this machine is within 120 units | 0x28d6dc |
| | +0xcc | s32 | step 0–4 of the "saved" burst | 0x28cdc4, run |
| JumpGate | +0x4c | u8 | active (radius 480) | run 0x27cb58 |
| | +0x4d, +0x4e | u8 | gate has been opened; light and idle animation on (both saved) | 0x27d974 |
| | +0x4f | u8 | integer parameter `hurt` | ctor 0x27c694 |
| | +0xd0 | u8 | **set to 1 by the draw function, cleared at the end of run** | 0x27d634, 0x27cb58 |
| Container | +0x68 | u32 | flags: 1 drops loot, 4 explosive, 0x20 no gold or items, 0x200 debris selection | run 0x290e78 |
| | +0x6c, +0x70 | float | push velocity, multiplied by 0.86 per frame | run |
| | +0x74 | s32 | fuse, starts at 180 | run |
| | +0x7c | u8 | standing in water (checked every 8th frame) | run |
| | +0x80 | s32 | 0 intact, 2 fuse burning, 1 broken | run |
| Chest | +0x4c | s16 | gold left inside | interact 0x292a2c |
| | +0x50 | s32 | frame it was opened | interact, run |
| | +0x58 | u8 | trapped | run 0x2923a8 |
| | +0x84 | s32 | 0 closed, 1 opening, 2 open | interact, run |
| Timer | +0x4c, +0x50 | s32 | frames left; value to send | 0x28ec7c, 0x28ecd4 |
| Counter | +0x4c | s32 | count | 0x28eda4 |
| Lever | +0x4c, +0x50, +0x51 | float, s8, u8 | position 0–1; direction ±1; moving | 0x28e748 |
| Torch | +0x88, +0x89, +0x8a | u8, s8, u8 | on the run list; frames since last drawn; kind 0–5 | 0x2b2ae8, 0x2b2088 |

### 2.3 Globals owned by this area

| Address | Meaning | How |
|---|---|---|
| 0x500ae8 | jump-gate travel state: 0 idle, 1 when a destination is confirmed, then counts frames to 180 | 0x27dd74 |
| 0x8e3a3a, 0x8e3a3b | menu state 0–7; index of the player whose pad drives the menu | 0x27dd74, 0x27da24 |
| 0x8e3a50, 0x8e3c30 | destination names (0x20 bytes each) and their count | 0x27db60, 0x27dcf4 |
| 0x8e3c34, 0x8e3c38 | destination parameter of the opening gate; "gate was not drawn" flag | 0x27da24 |
| 0x8e3938 | scratch Vec3 holding the active gate's effect position | 0x27cb58 |

Other globals this area reads a lot: 0x44fdcc (`g_simFrame`) is the frame counter (equal to the lockstep
frame inside a simulated tick, see `net_frameLoop`); 0x4f714c is a float "monster level"
used to scale trap, explosion and summon strength (written by `arena_startWave` (0x305ed4); temporarily
replaced inside the Skelight constructor and 0x245568); 0x4dcec8 + i×0x4c30 is player i's
object pointer; 0x44fe18 and 0x41b721 hold the current level name.

**0x404468 is a fourth random generator** (same constants as the other three; it is the
third global seed word, after 0x404460 and 0x404464 — "fourth" counts the per-object
generators — and `docs/OVERVIEW.md` lists it as a further cosmetic one). In the whole
program it is used by seven functions: the creature damage reaction `Creature_processDamage` (0x110d30) (blood),
`Player_run` (which of four swing sounds; the branch at 0x1aa8ac runs for non-local players
and for the prediction copy), Cazic_deathEffects 0x24c994, Marr's death effects 0x284b68 and
three skill functions. Every use read here chooses a sound or scatters particles, so it is
a second cosmetic generator; it differs between machines by construction. Observed for the
four functions named; the three skill functions (0x2c7808, 0x2ee068, 0x308578) were not read.

## 3. Catalogue

Generated from the virtual tables and the factory. `base` means the class uses the
inherited function (for TakeDamage: `Creature` 0x116638 or the empty `GameObject` one).
"AI states" is the set of `case` labels in the run function's switch on +0x232 — states the
class names explicitly, not necessarily ones it can reach. "Skills referenced" and
"Creates" come from the class's own functions and private helpers; "Creates" lists classes
whose constructor is called directly (objects made through the factory by name do not
show). Sizes are the `pool_new` argument at the factory call; `?` means the class is only
created by other code. All **Observed** by script; rows for the classes in sections 4 and
5 were also checked by hand.

### 3.1 Creature classes

| Class | Factory type names | Vtable | Size | Ctor | Run | Draw | TakeDamage | SetState | AI states (hex) | Skills referenced (id) | Creates |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Agony | AvatarAgony | 0x512c58 | 0x3d0 | 0x23396c | 0x233bdc | 0x233b90 | base | 0x234168 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  |  |
| Amphian | Amphian | 0x512da0 | 0x3c8 | 0x234584 | 0x23483c | 0x2347cc | base | 0x2350d0 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  | PoisonProjectile |
| Ant | AntTough, AntBlocker, Ant* | 0x5111c0 | 0x3e8 | 0x235418 | 0x2359fc | 0x2359b0 | base | 0x236708 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | FireWeapons (13), PoisonWeapons (26) | PoisonProjectile |
| AntQueen | AntQueen | 0x511078 | 0x3e8 | 0x236c70 | 0x236f78 | 0x236f10 | 0x2378fc | 0x237918 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 | PoisonWeapons (26) | AntWave |
| AntWave |  | 0x50d298 | 0x3d8 (`pool_new` at 0x237668) | 0x238654 | 0x238938 | 0x2387d0 | base | base |  |  |  |
| Arenabeast | Arenabeast | 0x512ee8 | 0x3d8 | 0x238bb8 | 0x238f5c | 0x238f18 | 0x239ba4 | 0x239bc0 | 0 1 3 5 6 7 8 9 a b c d e f 10 12 13 14 17 18 |  |  |
| Badger | SnoBadge, Badger* | 0x510f30 | 0x3d0 | 0x244018 | 0x244380 | 0x244320 | base | 0x244aa4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| BlackWidow | BlackWidow*, Drachnid | 0x510de8 | 0x420 | 0x2ab958 | 0x2abdd8 | 0x2abdb0 | base | 0x2acb78 | 0 1 3 5 6 7 8 9 a 10 12 13 14 17 18 |  |  |
| Bubo | Bubonian* | 0x513fe0 | 0x470 | 0x247fb0 | 0x248598 | 0x2484c8 | base | 0x2494c0 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | DiseaseBolt (4), DiseaseShield (5), DiseaseEffect (29), Healing (55), DiseaseBlade (97) | DiseaseProjectile |
| CastBadger | castbadger | 0x513e08 | 0x3d0 | 0x244e4c | 0x2450d8 | 0x2450b0 | base | 0x245660 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| Cazic | cazicthule, cazicavatar | 0x514128 | 0x3e8 | 0x24a670 | 0x24aaf0 | 0x24aa6c | base | 0x24c118 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | FireStorm (7), SummonSkeleton (11), ShockOfFrost (23), GroundPound (38), ShockOfFire (57), FrostStorm (58), WaveOfFlame (95), FrostArmor (96) | GroundPoundEffect, ShockOfFrost, Sparks |
| CdEyeball | cdeyeball | 0x50fab0 | 0x3d0 | 0x28f5dc | 0x28f7c0 | 0x28f6cc | base | base |  |  |  |
| Clockwork | Clockwork* | 0x514300 | 0x500 | 0x24e124 | 0x24e758 | 0x24e6dc | base | 0x24f90c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  | LightEffect |
| CloudGiant | CloudGiant* | 0x514448 | 0x538 | 0x2500b0 | 0x250714 | 0x250678 | 0x25246c | 0x252488 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | ColdWeapons (14) | BoltGoRound |
| CreatureContainer |  | 0x513780 | ? | 0x243624 | 0x2437ec | base | base | 0x24386c |  |  |  |
| Creep | Creep | 0x514620 | 0x500 | 0x253148 | 0x2535c8 | 0x253514 | base | 0x2542c4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a 1b |  |  |
| Critter | Orca | 0x510ca0 | 0x448 | 0x2547fc | 0x255008 | 0x254f24 | 0x255c54 | 0x255c5c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a |  |  |
| Cyclops | CyclopsNew, CyclopsGrey, Cyclops | 0x510b58 | 0x458 | 0x2566d4 | 0x256b18 | 0x256acc | base | 0x257668 | 0 1 2 3 5 6 7 8 9 a 10 12 13 14 |  | PoisonProjectile, dustCloud, poisonGasSpell |
| Demon | Demon* | 0x514b40 | 0x468 | 0x25dc6c | 0x25e17c | 0x25e118 | base | 0x25efd0 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | FireStorm (7), ShockOfFire (57) | FireStorm, Sparks |
| Droid | droid | 0x515da8 | 0x3d0 | 0x27b840 | 0x27ba78 | 0x27ba08 | base | 0x27c0a0 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  | LightEffect |
| FatCyclops | FatCyclops | 0x514768 | 0x468 | 0x257de8 | 0x258200 | 0x258134 | base | 0x258f8c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  | PoisonProjectile, dustCloud, poisonGasSpell |
| FemaleDarkElf | FemaleDarkElf* | 0x5149f8 | 0x478 | 0x25947c | 0x259a98 | 0x259a34 | base | 0x25ab14 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | SummonSkeleton (11), PoisonRain (24), PoisonWeapons (26), Shock (37), Healing (55), PusStorm (80), SpiritShield (94) |  |
| FireBeetle | BBeetle, LBeetle, FireBeetle* | 0x510a10 | 0x430 | 0x24587c | 0x245f54 | 0x245c8c | base | 0x2469d0 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | FireWeapons (13) | LightEffect, beetleProjectile |
| FireFly | FireFly | 0x5108c8 | 0x470 | 0x24726c | 0x247670 | 0x24742c | base | 0x24787c |  |  |  |
| Froglock | Froglock* | 0x510780 | 0x468 | 0x263e1c | 0x264314 | 0x264278 | base | 0x265150 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | ColdArrow (44), PoisonArrow (45) | ColdArrowProjectile, PoisonArrowProjectile |
| Generator | AntMaker | 0x510638 | 0x3e8 | 0x2657a0 | 0x265938 | 0x265930 | base | 0x265ee8 |  |  |  |
| Ghoul | Ghoul*, GhulBlue* | 0x5104f0 | 0x3d8 | 0x266088 | 0x266420 | 0x2663f8 | base | 0x266c68 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a |  |  |
| Gnaw | Gnaw | 0x515038 | 0x3c8 | 0x26741c | 0x267654 | 0x267604 | base | 0x267a0c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| GnawSpawn | GnawSpawner | 0x514ef0 | 0x3e0 | 0x267cf4 | 0x268070 | 0x268000 | 0x268c40 | 0x268c5c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 |  |  |
| Gnome | Gnome* | 0x5103a8 | 0x3d8 | 0x268fd4 | 0x2693d0 | 0x2691f0 | base | 0x269bb4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  |  |
| GnomeNavigator | GnomeNavigator | 0x515180 | 0x3c8 | 0x269eb8 | 0x26a1e0 | 0x26a000 | base | 0x26a3f4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| Goblin | fgoblin*, Goblin* | 0x510260 | 0x498 | 0x26a624 | 0x26b27c | 0x26b1d0 | base | 0x26ccfc | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | FireStorm (7), FireWeapons (13), ColdWeapons (14), ShockOfFrost (23), Shock (37), FireArrow (43), ColdArrow (44), ExplodeArrow (47), ShockOfFire (57), FrostStorm (58) | ColdArrowProjectile, ExplodeArrowProjectile, FireArrowProjectile |
| Gremlin | Gremlin | 0x515358 | 0x460 | 0x26e08c | 0x26e4c4 | 0x26e40c | base | 0x26ee98 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | FireArrow (43), ColdArrow (44), ExplodeArrow (47) | ColdArrowProjectile, ExplodeArrowProjectile, FireArrowProjectile |
| Hag | Hag* | 0x5154a0 | 0x3d8 | 0x26f120 | 0x26f504 | 0x26f494 | base | 0x270264 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a | Shock (37), LightningStrike (100), ConeOfShock (101) | LightningBolt |
| Horsemen | RiderDisease, RiderWar, RiderPestilence, RiderDeath, UndeadKnight1, UndeadKnight2, UndeadKnight3, UndeadKnight4 | 0x515730 | 0x478 | 0x271c70 | 0x27236c | 0x2721f8 | base | 0x272f4c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e 1f 20 21 22 23 | DiseaseBolt (4), FireStorm (7), SummonSkeleton (11), TagarsInsects (87) | Nightmare |
| Innoruuk | Innoruuk | 0x515a28 | 0x4d0 | 0x2735dc | 0x273bd0 | 0x273b20 | 0x276a58 | 0x276a80 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | HateBeam (27), BallOfHate (28) | HateBeam, HateProjectile, HateSoul, LightEffect |
| IronGuardian | IronGuardian | 0x515c60 | 0x3e8 | 0x27a00c | 0x27a390 | 0x27a30c | base | 0x27b550 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  | Droid, JunkProjectile |
| Kobold | Kobold* | 0x515ef0 | 0x3d0 | 0x27f0c0 | 0x27f52c | 0x27f504 | base | 0x27ff6c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | Healing (55), FrostArmor (96) |  |
| LavaMonster | EarthElemental, LavaMonster | 0x510118 | 0x430 | 0x28048c | 0x280b44 | 0x280a60 | base | 0x282460 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | FireWeapons (13) |  |
| MaleDarkElf | MaleDarkElf* | 0x5148b0 | 0x4f8 | 0x25afd8 | 0x25bbe4 | 0x25bb80 | base | 0x25d084 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | FireArrow (43), ColdArrow (44), PoisonArrow (45), MultiFire (46) | ColdArrowProjectile, FireArrowProjectile, MultiFireProjectile, PoisonArrowProjectile |
| Marr | MattMarr | 0x5160d0 | 0x4a8 | 0x2835a0 | 0x283afc | 0x2838ec | base | 0x28468c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 | PlanarWind (66), SpiritShield (94) |  |
| Mermaid | Mermaid | 0x516218 | 0x3c8 | 0x285b30 | 0x285c58 | 0x285c30 | base | 0x285ddc | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| Minion | Minion | 0x5164a8 | 0x3e8 | 0x285f10 | 0x2862c0 | 0x28625c | 0x287438 | 0x287454 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | FrostStorm (58) | LightEffect, Soul |
| Minotaur | Minotaur* | 0x5165f0 | 0x470 | 0x288fdc | 0x2894b8 | 0x289400 | base | 0x28a16c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  |  |
| Mosquito | Mosquito* | 0x516a08 | 0x3c8 | 0x297788 | 0x297b30 | 0x297a14 | base | 0x297f54 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  |  |
| Mummy | Mummy* | 0x516e48 | 0x480 | 0x298418 | 0x298d18 | 0x298c7c | base | 0x29a6f4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 | DiseaseBolt (4), DiseaseShield (5), FireStorm (7), ConeOfFire (18), ShockOfFrost (23), PoisonRain (24), ShockOfFire (57), FrostStorm (58) | DiseaseBolt, DustDevil, FireStorm, ShockOfFrost, Sparks |
| MummyKing | MummyKing | 0x516b50 | 0x4a0 | 0x29afb4 | 0x29b360 | 0x29b2c4 | 0x29c544 | 0x29c574 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 | DiseaseWeapons (25), PoisonWeapons (26) | DustDevil, MummySnake, SpawnMummy |
| Natasla | Natasla | 0x516f90 | 0x3c8 | 0x29d70c | 0x29dbf0 | 0x29d844 | base | 0x29dc3c |  |  |  |
| Nightmare | Nightmare | 0x5155e8 | 0x3d8 | 0x270968 | 0x270bbc | 0x270b4c | base | 0x27155c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a |  | Nightmare |
| NPC | NPC | 0x50f590 | 0x480 | 0x29dcc4, 0x29df04 | 0x29ea40 | 0x29e3ec | 0x29eeb8 | 0x29efcc |  |  |  |
| Ogre | Ogre | 0x517220 | 0x468 | 0x29fad0 | 0x29fe50 | 0x29fdb4 | base | 0x2a060c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| Orc | Orc2*, Orc* | 0x50ffd0 | 0x488 | 0x2a0954 | 0x2a1848 | 0x2a1770 | 0x2a2eac | 0x2a323c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | PoisonRain (24), Shock (37), FireArrow (43), ColdArrow (44), ExplodeArrow (47), Healing (55) | ColdArrowProjectile, ExplodeArrowProjectile, FireArrowProjectile |
| RedDragon | RedDragon | 0x514c88 | 0x418 | 0x25f470 | 0x25f988 | 0x25f93c | 0x260d58 | 0x260d74 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d |  | FireStorm |
| Rondo | Rondo | 0x5170d8 | 0x3d0 | 0x29f10c | 0x29f46c | 0x29f28c | base | 0x29f768 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| Scorpion | Scorpion | 0x50fe88 | 0x3d0 | 0x2a4d68 | 0x2a5068 | 0x2a5030 | base | 0x2a55ec | 0 1 3 5 6 7 10 12 13 14 17 18 |  |  |
| SeaMonster | SeaMonster | 0x517368 | 0x3d0 | 0x2a428c | 0x2a44a8 | 0x2a445c | base | 0x2a4aa4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 |  |  |
| Skeleton | WatSkel, Skeleton* (red*, blue* variants) | 0x5175f8 | 0x478 | 0x2a5af4 | 0x2a6864 | 0x2a67c4 | 0x2a774c | 0x2a7768 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | FireArrow (43), ColdArrow (44), ExplodeArrow (47) | ColdArrowProjectile, ExplodeArrowProjectile, FireArrowProjectile |
| Skelight | Skelight | 0x5174b0 | 0x468 | 0x2a8770 | 0x2a8b84 | 0x2a8a64 | base | 0x2a91b8 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  |  |
| SmallSpider | SmallSpider | 0x50fd40 | 0x3c8 | 0x2ab450 | 0x2ab5d8 | 0x2ab590 | base | 0x2ab704 |  |  |  |
| Soul | Soul | 0x517740 | 0x3e0 | 0x2a9478 | 0x2a9870 | 0x2a9678 | 0x2aa908 | 0x2aac38 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 1a 1b 1c 1d 1e 1f 20 21 22 |  |  |
| SpiderQueen | SpiderQueen | 0x50fbf8 | 0x430 | 0x2ad1c0 | 0x2ad630 | 0x2ad5e4 | 0x2aed60 | 0x2aeec4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 | PoisonWeapons (26) | PoisonProjectile |
| Teleporter | Teleporter | 0x50d590 | 0x3c8 | 0x28ee80 | 0x28ef0c | 0x28ef04 | base | 0x28f154 |  |  |  |
| Tormentor | SnowBeast, SnowBoss, Tormentor* | 0x516360 | 0x3d8 | 0x287998 | 0x287db0 | 0x287d78 | base | 0x288b70 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | ShockOfFrost (23), ConeOfFrost (56) | ShockOfFrost |
| Ulthork | Ulthork* | 0x517a60 | 0x468 | 0x2b5538 | 0x2b5a08 | 0x2b594c | base | 0x2b65c4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | ShockOfFrost (23), FrostStorm (58) | FrostStormSpell, ShockOfFrost |
| UndeadKnight | UndeadKnight | 0x517918 | 0x478 | 0x2b3e30 | 0x2b4370 | 0x2b421c | 0x2b4cc8 | 0x2b4ce4 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 |  |  |
| Vampire | Vampire | 0x50f968 | 0x3c8 | 0x2b69d0 | 0x2b6bfc | 0x2b6bd4 | base | 0x2b7208 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 |  |  |
| VampireLord | VampireLord | 0x517ba8 | 0x480 | 0x2b76e4 | 0x2b7be0 | 0x2b7af0 | 0x2b93d8 | 0x2b944c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 | ColdWeapons (14) | Critter |
| WarBoar | WarBoar* | 0x517cf0 | 0x3d8 | 0x2ba03c | 0x2ba3a0 | 0x2ba340 | base | 0x2bac60 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 |  |  |
| Warrior | Samurai, Gladiator* | 0x517e38 | 0x480 | 0x2bafb4 | 0x2bb640 | 0x2bb5a4 | base | 0x2bc320 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 |  |  |
| WarWraith | WarWraith | 0x517f80 | 0x468 | 0x2c07a8 | 0x2c0c2c | 0x2c0b70 | base | 0x2c1648 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | ColdWeapons (14) |  |
| WoodElfSoldier | WoodElf*, evilwoodelf* | 0x50f820 | 0x3e8 | 0x2bc820 | 0x2bccec | 0x2bcc94 | 0x2bccd0 | 0x2bdb24 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 18 19 |  |  |
| Wraith | Wraith | 0x50f6d8 | 0x3d8 | 0x2bf2ac | 0x2bf538 | 0x2bf4e4 | base | 0x2c0270 | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 15 16 17 | ColdWeapons (14) | none (the earlier version listed Weapon1: the embedded Weapon1 is WarWraith's, built by its constructor 0x2c07a8) |
| Zek | raloszek | 0x5180c8 | 0x480 | 0x2c1f94 | 0x2c2440 | 0x2c2378 | 0x2c34e4 | 0x2c382c | 0 1 2 3 4 5 6 7 8 9 a b c d e f 10 11 12 13 14 | GroundPound (38) | GroundPoundEffect, LightEffect |

### 3.2 Other objects

| Class | Factory type names | Vtable | Size | Ctor | Run | Draw | TakeDamage | OnTouch | Skills referenced (id) | Creates |
|---|---|---|---|---|---|---|---|---|---|---|
| AddParticle |  | 0x513288 | ? | 0x23fae0, 0x23fc50 | base | base | base | base |  |  |
| AntTrap | AntTrapa | 0x513d60 | 0x1a0 | 0x24290c | 0x2429d8 | 0x23aa20 | 0x23cf0c | base |  |  |
| AutoChest |  | 0x513468 | ? | 0x23ad18 | 0x23b170 | 0x23aa20 | base | base |  | LightEffect |
| AutoChestLP |  | 0x513168 | ? | 0x241468 | 0x241604 | 0x241568 | base | base |  |  |
| AutoContainer |  | 0x513330 | ? | 0x23d93c | 0x23e430 | 0x23aa20 | 0x23fa60 | 0x23e358 |  | Gold, LightEffect |
| AutoContainerLP |  | 0x513030 | ? | 0x24259c | 0x242728 | 0x24268c | 0x23fa60 | 0x23e358 |  |  |
| AutoEmitter |  | 0x5131f8 | ? | 0x240dc8 | 0x241310 | 0x2410f0 | base | base |  |  |
| AutoObject |  | 0x5134f8 | ? | 0x23a354 | 0x23ad00 | 0x23aa20 | base | base |  |  |
| AutoProp |  | 0x5133c0 | ? | 0x23c44c | 0x23cb54 | 0x23aa20 | 0x23cf0c | base |  |  |
| AutoPropLP | Antlighta, Antlightb, Antlightc | 0x5130c0 | 0x448 | 0x2416c4 | 0x2421e0 | 0x241ee4 | 0x23cf0c | base |  |  |
| beetleProjectile |  | 0x50e3d8 | 0x1d0 (`pool_new` at 0x24683c) | 0x247884 | 0x247980 | 0x247978 | base | 0x247e1c |  | LooseFire |
| BoltGoRound |  | 0x514590 | ? | 0x252a6c | 0x252cb4 | base | base | base |  |  |
| Candle | Candle, Candle2 | 0x50f0e8 | 0x94 | 0x2b2c70 | 0x2b2dc4 | 0x2b30ac | base | base |  |  |
| Candle2 | Candle3 | 0x50f058 | 0x50 | 0x2b30ec | 0x2b3164 | 0x2b33b4 | base | base |  |  |
| Catapult | catapult | 0x514270 | 0xfc | 0x24d440 | 0x24d9c0 | 0x24dc40 | 0x24de9c | base |  | FireBomblet |
| Chest | Chest*, Chest2, Chest3, ChestCav, IceChestLarge | 0x5118d8 | 0x88 | 0x292030 | 0x2923a8 | 0x29288c | base | base |  | LightEffect |
| Container | Container, Barrel*, SnowBarrel, Basket, IceBarrel, IceCrate, SnowCrate, HRBarrel, PowderKegSnow, PotA1, PotA2, | 0x5119f8 | 0x84 | 0x2909b0, 0x290c24 | 0x290e78 | 0x291ec8 | 0x291e40 | 0x290da8 |  | Gold, LightEffect |
| Counter | Counter | 0x50d888 | 0x50 | 0x28ed14 | base | base | base | base |  |  |
| DiseasePort | disportGOOD, disportEVIL | 0x513630 | 0x448 | 0x243cd0 | 0x2421e0 | 0x241ee4 | 0x23cf0c | base |  |  |
| DiseaseProjectile |  | 0x513f50 | ? | 0x249a50 | 0x249c18 | 0x249b38 | base | 0x24a3a8 |  |  |
| DoorSecret | DoorSecret | 0x50dfd8 | 0x5c | 0x28b0a8 | 0x28b370 | base | base | base |  |  |
| DoorSwing | DoorSwing | 0x50e100 | 0x5c | 0x28a960 | 0x28af54 | base | base | base |  |  |
| DragonGoldPile | dragongoldpile | 0x5167c8 | 0x64 | 0x295cf4 | 0x295d58 | base | base | base |  |  |
| DustDevil |  | 0x516db8 | ? | 0x29caa8 | 0x29cb98 | base | base | base |  |  |
| EggSack | EggSac | 0x513cb8 | 0x448 | 0x242bd8 | 0x2421e0 | 0x241ee4 | 0x23cf0c | base |  |  |
| FallPlatform |  | 0x50de28 | ? | 0x28b88c | 0x28bb5c | base | base | base |  |  |
| FireBomb | kelethinBomb | 0x50db58 | 0x58 | 0x261dbc | 0x261f48 | base | base | base |  | FireBomblet |
| FireBomblet |  | 0x514dd0 | ? | 0x2622a8 | 0x262588 | 0x262ea4 | base | base |  | FireBombletJr, StaticFire |
| FireBombletJr |  | 0x50dac8 | ? | 0x2632a4 | 0x2636dc | 0x263aa0 | base | base |  | StaticFire |
| FireTrail |  | 0x50dd98 | ? | 0x28c160 | 0x28c44c | base | base | 0x28c2c4 |  |  |
| FireTrailMaker |  | 0x50dd08 | ? | 0x28c6d8 | 0x28c910 | base | base | base |  | FireTrail |
| FloorSwitch | FloorSwitch | 0x50deb8 | 0x58 | 0x28b4e0 | 0x28b56c | base | base | base |  |  |
| GothTrap | GothTrap | 0x513ac0 | 0x1a0 | 0x243088 | 0x2430fc | 0x23aa20 | 0x23cf0c | base |  |  |
| HackDoor | Arenadoor | 0x5138c8 | 0x198 | 0x243594 | 0x23cb54 | 0x23aa20 | 0x23cf0c | base |  |  |
| HateBeam |  | 0x515908 | ? | 0x277468 | 0x2775e8 | base | base | base | HateEffect (30) | SpellHateEffect |
| HateBridge | HateBrdg | 0x513970 | 0x1a0 | 0x243398 | 0x243414 | 0x23aa20 | 0x23cf0c | base |  |  |
| HateGate | HateGate | 0x513b68 | 0x1b8 | 0x242e7c | 0x242edc | 0x23aa20 | 0x23cf0c | base |  |  |
| HateHole | HateHole | 0x513a18 | 0x1a0 | 0x24323c | 0x2432c0 | 0x23aa20 | 0x23cf0c | base |  |  |
| HateInto | HateInto | 0x513c10 | 0x1b8 | 0x242c5c | 0x242cd0 | 0x23aa20 | 0x23cf0c | base |  |  |
| HateProjectile |  | 0x515878 | ? | 0x278158 | 0x2783e8 | 0x279048 | base | base | HateEffect (30) | SpellHateEffect |
| HateSoul |  | 0x515998 | ? | 0x279640 | 0x279850 | base | base | base |  |  |
| IceBall |  | 0x50e638 | ? | 0x290390 | 0x290528 | 0x290908 | base | base |  | LightEffect |
| JumpGate | PortalHurt, Portal | 0x50dbe8 | 0x164 | 0x27c694 | 0x27cb58 | 0x27d634 | base | base |  |  |
| JunkProjectile |  | 0x515bd0 | ? | 0x27c2c8 | 0x27c4c0 | 0x27c3b8 | base | 0x27c5e8 |  |  |
| Lamp | Lamp | 0x50ef38 | 0x8c | 0x2b3718 | 0x2b3858 | 0x2b3a64 | base | base |  |  |
| Lantern | Lantern | 0x50efc8 | 0x98 | 0x2b33f4 | 0x2b3554 | 0x2b3638 | base | base |  |  |
| LavaBomb |  | 0x516038 | 0x1d8 | none: built inline in `LavaMonster_run` at 0x2813c8–0x28149c (the earlier version gave 0x281194, which is the case label of state 8 in that function; `docs/monsters-2.md`) | 0x282954 | 0x2828a8 | base | 0x283214 |  |  |
| Lever | Lever | 0x50d918 | 0x54 | 0x28e394 | 0x28e748 | 0x28e64c | base | base |  |  |
| LightningBolt |  | 0x5168e8 | ? | 0x295360, 0x295584 | 0x2957e4 | base | base | base |  |  |
| LightningRod | LightningRod | 0x516858 | 0x5c | 0x2958a8 | 0x295954 | 0x29594c | base | base |  | LightningBolt |
| LostSoul |  | 0x50e7e8 | ? | 0x2931bc (the earlier version gave 0x293228, an address inside the constructor) | 0x2933f4 | 0x2936fc | base | base |  |  |
| MummySnake |  | 0x516c98 | ? | 0x29cfe4 | 0x29d0c0 | base | base | base | PoisonWeapons (26) |  |
| OniBall |  | 0x50e878 | ? | 0x294014 | 0x2941e4 | 0x2946f0 | base | 0x2946f8 | LifeTap (59) |  |
| PointSourceSound |  | 0x50d208 | ? | 0x28f370 | 0x28f4ac | base | base | base |  |  |
| PoisonProjectile |  | 0x517888 | 0xa8 (all five `pool_new` sites) | 0x2b153c | 0x2b176c | 0x2b16a4 | base | 0x2b1c4c | PoisonWeapons (26) |  |
| PokeReflector | PokeReflector | 0x50d9a8 | 0x4c | 0x28e1e4 | base | base | base | base |  |  |
| RingPortal | apprings | 0x5136d8 | 0x498 | 0x24388c | 0x243b48 | 0x243a44 | 0x23cf0c | base |  |  |
| RollDoor | RollDoor | 0x50e068 | 0x5c | 0x28dd94 | 0x28e01c | 0x28e110 | base | base |  |  |
| Root |  | 0x50e758 | ? | 0x293704 | 0x293ae0 | 0x29400c | base | base |  |  |
| Savepoint | SavePoint | 0x50dc78 | 0x118 | 0x28cb90 | 0x28cdd0 | 0x28d854 | base | base |  |  |
| SnowballSpell |  | 0x5152c8 | ? | 0x26d884 | 0x26da20 | 0x26d940 | base | 0x26de54 |  |  |
| Sparks |  | 0x50e998 | ? | 0x28f880 | 0x28fa3c | 0x2902e4 | base | 0x2900c8 |  | LightEffect |
| SpawnMummy |  | 0x516d28 | ? | 0x29ce20 | 0x29cea8 | base | base | base |  | Weapon1 |
| SpellHateEffect |  | 0x515b70 | ? | 0x27930c | 0x279420 (slot 2 of a `Spell` table, the per-frame update, `SpellHateEffect_update`; the earlier version listed it under TakeDamage) | - | - | - |  |  |
| SpiritAnchor | SpiritAnchorAct, SpiritAnchorExp | 0x516738 | 0x98 | 0x295ff4 | 0x2964a8 | 0x296204 | 0x296888 | base |  |  |
| Switch | Switch | 0x50df48 | 0x50 | 0x28a850 | base | base | base | base |  |  |
| Timer | Timer | 0x50d7f8 | 0x54 | 0x28ec1c | 0x28ecd4 | base | base | base |  |  |
| Torch | Torch, Fire, Campfire, Firepot, Firepot2, OilLamp | 0x50f298 | 0x8c | 0x2b1e80 | 0x2b2088 | 0x2b2ae8 | base | 0x2b2860 | FireWeapons (13) |  |
| TormentBridge | ptbridge | 0x513588 | 0x198 | 0x243e3c | 0x243ea0 | 0x23aa20 | 0x23cf0c | base |  |  |
| Trap | Trap | 0x516978 | 0x50 | 0x294fa4 | 0x29507c | 0x295074 | base | base | FireWeapons (13), PoisonWeapons (26) |  |
| UnholyAura |  | 0x50e6c8 | ? | 0x29486c | 0x29496c | 0x294f9c | base | base |  |  |
| VehicleBodySphere |  | 0x50d0e8 | ? | 0x28f2c4 | base | base | base | 0x28f340 |  |  |
| WeaponRack | WeaponRack | 0x50d6d8 | 0x98 | 0x28e87c | base | 0x28ea94 | base | base |  |  |
| WebTrap | WebTrap | 0x50e348 | 0xa0 | 0x2b04f8, 0x2b07c0 | 0x2b0c74 | 0x2b0954 | base | base |  |  |
| WorldPart |  | 0x511de8 | ? | 0x28a6b0 | base | base | base | base |  |  |

**Notes to the two tables**, from the class-by-class reading in `docs/monsters-2.md`
(section 9.2). The tables above were generated by script and say what a class's functions
*reference*; these are the places where that differs from what the class can do.

- Referenced but not reachable: Tormentor's ConeOfFrost (56) is cast in state 8 and Kobold's
  FrostArmor (96) in state 9, and nothing in either class requests that state; the same
  for the Mummy's teleport state 0x17. Ulthork's ShockOfFrost and FrostStorm are used only
  in state 7, which needs variant 2, which the constructor cannot assign. UndeadKnight's
  state 8 cannot be chosen and its 0x17 is not requested. AntQueen's state 0x19 (the only
  creator of `AntWave`) has no requester that was found.
- "Creates" is short for several classes: Goblin, MaleDarkElf and Froglock also create
  plain `MissileWeapon` objects (constructor 0x150ee4) when the weapon has no element;
  Mummy also `PoisonRain` (0x6c bytes, constructor 0x2f8f48), `SpellDiseaseShield` (0x1b0)
  and `SpellConeOfFire` (0x58); Orc also `MissileWeapon`, `PoisonRain` and `GutChunk`;
  BlackWidow `GutChunk` and, through the strand controller, `WebTrap`; Skeleton
  `MissileWeapon` and `PhProp` pieces; Scorpion `GutChunk`.
- Skeleton, "red*, blue* variants": the factory's `red` / `blue` prefix tests
  (0x15b50c–0x15b594) are applied to a name that has just matched `Skeleton` and cannot
  succeed, so the class blocks `skelred.lmp` / `skelblue.lmp` are never selected there. The
  red / blue distinction that works is the side byte +0x3d4, set in the constructor from
  `skeleton…red` / `skeleton…blue` names and used by the is-enemy override.
- SmallSpider's states are 0, 1 and 0x14 (the row shows none). FireFly's set-state
  0x24787c is an empty function, not a real set-state.
- `SnowballSpell` is never instantiated: its constructor 0x26d884 has no caller.
- 0x2bfe2c, which the Skeleton paragraph of section 4 calls "a Wraith helper", is not a
  function: it is the state-0x17 code inside `Wraith_run`.
- The nine functions once named `AutoPropLP_…` at 0x23cea0–0x23d7ac belong to `AutoProp`
  and are inherited by the LP class (since renamed in `symbols/monsters.tsv`).

## 4. Bosses

Unless a state is described in a sentence, the entry is the script's summary of which
helpers that state calls (**Observed** call sites, not a full reading of every branch).
"Rider" means the monster asks a weapon-enchant skill for a number (table offset 0x5c) and
attaches it to the melee hit as an elemental effect.

### Horsemen (the four knights) — read in full

Constructor 0x271c70, run 0x27236c, draw 0x2721f8, setState 0x272f4c. One class, four
variants (+0x470). `UndeadKnight1–4` are created without a mount; `Rider*` get a Nightmare
(constructor 0x270968) linked both ways through +0x3c8 and start in state 0x1b.

- Unmounted: the normal run skeleton, then the state switch. Mounted: the rider copies the
  mount's position and facing every frame, re-links itself in the world grid (0x14f028),
  and takes over the mount's target (0x2723c4–0x272490).
- State 3 (chase): target within 36 units → 5; a second 36-unit test with a 6000 arc and
  `Creature_isTargetCharging` (0x118f90) true → 8 (as coded that helper is true for a target
  moving faster than 100 whose facing agrees with the bearing from the knight **to** it — a
  target facing away, not one running at the knight; 0x118fb0–0x118fe8, executed,
  `docs/spec/arena-monsters.md` 2.3); target within 400 units and `Creature_countAlliesNearTarget` (0x119258) (36 units) positive → 5. Then
  the skill: variants 0–2, once `age > +0x474`, go to state 0x17 when an enemy is within
  400 units in a 6000 arc; **variant 3 goes to 0x17 whenever SummonSkeleton's "can cast"
  test passes, without looking at +0x474** (0x2726a0–0x27271c). Otherwise keep chasing.
- State 5: while timer A runs, a target within 36 units → 6. With timer A clear and the target within 36 units, two draws from the knight's
  own generator choose between states 10, 7 and 6; with the target within 72 units in a
  narrow arc → 0xb; otherwise one own-generator draw in 60 per frame returns to chase.
  Executed (`docs/spec/arena-monsters.md` 3.3): the choice is "first draw odd **and**
  `creature_isBlockedBy` true → 10; otherwise a second draw, odd → 6, even → 7" (so one or
  two draws, not always two); and the "one in 60" return to chase also needs
  `Creature_countAlliesNearTarget(36)` to be zero — with an ally near the target the knight
  stays.
- States 6, 7, 10, 0xb: melee swing; on the hit event a full-damage arc test (flag 8 plus
  the weapon helper's value), on event bit 1 a second test with a third of the damage.
  The two are alternatives on one tick, not a pair (executed, `docs/spec/arena-monsters.md`
  3.3, 14): the constructor's event table gives bit 1 to exactly one clip, state 10's, and
  that clip has no bit-0 event. So state 10 is the one-third hit — flags 0x100001, no
  weapon descriptor, the divisions truncating — and nothing else, and 6, 7 and 0xb are
  two, three and three full hits. State 8: single heavy swing (flags 0x40008).
- **State 0x17 (cast)** on the hit event: variant 0 casts skill 4 DiseaseBolt from chest
  height; variant 1 casts skill 7 FireStorm at the target's position; variant 2 casts
  skill 87 TagarsInsects on itself and links the spell; variant 3 casts skill 11
  SummonSkeleton at its own position. Then `+0x474 = age + 480 + own random mod 120`.
- States 0x1f–0x22 are the mounted swings (arc turned 90° to the side); 0x1a counts +0x472
  down; 0x23 is an animation hand-over; 0x14 dead. Besides the usual death work, case
  0x14 of the set-state looks up the summoned skeleton by name for variant 3 and, if it
  is still in the world, sends it to state 0x14 in the same tick (0x273260–0x2732ac), and
  drops both held weapon parts (FINDINGS K8, `docs/issues/kill-loot-xp.md`).
- Two properties of `Horsemen_setState` that no earlier document had (executed,
  `docs/spec/arena-monsters.md` 3.4). A **mounted** knight (mount handle +0x3c8 set)
  returns for every request below 0x19 — 0x14 included, so the set-state cannot kill it
  while it rides — after `Creature_filterState` has run and creature flag 0x200 has been
  cleared (0x272f4c head). And a request for a state the class has no case for (2, 4, 9,
  0xc–0xf, 0x15, 0x16, 0x24 and up) runs a nested set-state 3 and then stores the
  **requested** number as the state; the next run turns it into set-state 0.
  `Skelight_setState` and `Zek_setState` store 0 for such a request (Zek's without
  touching the animation).
- All randomness is the knight's own generator. No global, camera, pad, audio or timer
  read in run, setState or draw. Draw calls `Creature_draw` and then the weapon helper's
  draw (table offset 0x94), neither in this area.

### Cazic — read in full; the run function is 0x24aaf0

Constructor 0x24a670, run **0x24aaf0**, draw 0x24aa6c, setState 0x24c118, slot 11 0x24c04c,
helpers 0x24c564, 0x24c5a4, 0x24c7fc, 0x24c994. The function at 0x248598 that earlier notes
call Cazic's run belongs to `Bubo` (type `Bubonian*`, table 0x513fe0); Cazic's table
0x514128 has 0x24aaf0 in slot 4 (**Observed**: table words, and the constructor stores
0x514128 at +0x48).

Two variants. The constructor compares the type name with `cazicavatar`: the avatar gets
`+0x3c9 = 1`, radius 25 and scale 0.7; `cazicthule` gets `+0x3c9 = 0` and loads an extra
lump. `Cazic_isNonAvatarAboveHalfHp` (0x24c564) returns 1 only for the non-avatar variant
with more than half its hit points; every casting branch is behind it.

- Every frame: byte +0xa0 is 6 while that test is true and no cutscene is active, else 0.
- State 3 (chase): target within 48 units → 5. If the test is false and `+0x3cc < age` and
  the target is 144–360 units away → 0xf (charge). If the test is true: SummonSkeleton
  "can cast" → 0xd; an enemy within 360 → 5; an enemy within 60 → 5.
- State 5: target not within 60 units — test true and SummonSkeleton castable → 0xd; test
  true and an enemy within 360: 0xc when +0x3c8 ≥ 5, else state 10 or 0xb by one own
  draw; test true otherwise: 0xd when +0x3c8 ≥ 5; in all other cases wait for timer A and
  return to 3. Target within 60 units — by angle to the target: in front → 0xe (combo) or,
  when +0x3c8 ≥ 5, 7 (ground pound); to either side → 8 or 9.
- State 6, 8, 9, 0xe: melee arcs; each hit increments +0x3c8.
- State 7: on the hit event creates a 0x9c-byte ground-pound object 60 units ahead through
  `GroundPoundEffect_ctor` (0x2c74ac) with skill 38 (GroundPound) and the slot-35 level, then a 60-unit melee test;
  resets +0x3c8.
- States 10 / 0xb: `Cazic_castShockOfFire` (0x24c5a4, builds a `Sparks` object) when the
  enemy is within 200 units, else `Cazic_castShockOfFrost` (0x24c7fc).
- State 0xc: the same pair on earlier event bits, and on event mask 8 casts skill 7
  FireStorm (enemy within 200) or skill 58 FrostStorm.
- State 0xd: when SummonSkeleton is castable, casts skill 11 twice, 60 units to the left
  and right; otherwise casts skill 96 FrostArmor on himself if he has no spell of type
  `SpellFrostArmor_typeinfo` (0x3d1d70), else skill 95 WaveOfFlame; the result is linked as his spell.
- State 0xf: charge; slot 11 (0x24c04c) damages every player he touches and goes to 5;
  when the animation ends `+0x3cc = age + 300`.
- State 0x14 (setState): creature flag 0x20000000000, the common death call `Creature_dropLoot` (0x10f2c8), then
  every creature named `skelightm` (up to 10, found with `world_findObjectsByName` (0x14bf58)) is sent to state 0x14,
  and the base call at offset 0xe4 runs. The run-side of 0x14 calls the dead-body handler
  and, for the non-avatar only, `Cazic_deathEffects`.

**Consequence (Inferred from the above):** the avatar (+0x3c9 = 1) can reach only states
0, 1, 3, 5, 6, 7, 8, 9, 0xe, 0xf and the common ones. It never casts FireStorm, FrostStorm
or SummonSkeleton; its only skill object is the ground pound. In the arena the summoned
skeletons therefore come from knight variant 3 alone. This contradicts the note on
`Cazic_ctor` in `names.tsv` and FINDINGS D3's reading of who casts what; it holds only if
the arena object's type really is `cazicavatar` (taken from `names.tsv`, not re-checked in
the level file).

### Skelight (the summoned skeleton)

Constructor 0x2a8770 (called by the factory for type `Skelight` and by the SummonSkeleton
skill at 0x2e2040), run 0x2a8b84, setState 0x2a91b8. The constructor temporarily writes its
level argument into the monster-level global 0x4f714c, calls the stat scaler `Creature_setStats` (0x10a620) (one
argument differs when the current level name is `blomedal`), restores the global, and
enters state 0x17. State 0x17 calls `fx_spawn(7, position)` every frame until the rise
animation ends. State 3 chases; 6 is the only attack (48-unit arc, flag 8, +0xf4 counts the
swing down). setState 0x14 clears the static 0x8e4560, spawns an effect and queues the
object for deletion. No per-machine read in run, setState or draw.

Executed since (`docs/spec/arena-monsters.md` 4.3, 4.4, 14), and differing from the shared
table of 1.4 in four places: state 0x13 leaves to **0**, not 3; a set-state 0x12 is ignored
(the skeleton has no hit reaction, the state stays what it was); states 2, 4, 7–0xf, 0x11,
0x15 and 0x16 have no case in the run function — a skeleton put in one stays there — and
the set-state turns a request for any of them into state 0; and "+0xf4 counts the swing
down" is one step, not a count of frames: set-state 6 stores 1, and the decrement happens
only on a tick on which the clip is no longer playing, so the state ends on the first such
tick.

`fx_spawn` (0x1ef270, gameplay area) returns early when the position is not near the local
camera, except for effect type 5 — the only type that draws from the shared generator and
creates objects (**Observed**: test at 0x1ef2e0; shared-generator use only in case 5). Type
7 is particles from the cosmetic generator.

### Skeleton and UndeadKnight

- Skeleton (0x2a5af4 / run 0x2a6864): state 8 is the archer shot — references skills 43,
  44, 47 and creates FireArrow, ColdArrow, ExplodeArrow or plain projectiles with four own
  draws; 0x17 rises from the ground with `fx_spawn`. Constructor is also called from
  0x2bfe2c (a Wraith helper).
- UndeadKnight (0x2b3e30 / run 0x2b4370): states 7–0xb are melee swings chosen in state 3
  with three own draws; 0x17 emits particles. Its draw function has a latent bug, see 7.
  Corrected by `docs/monsters-2.md` 9.2: it is one own draw per decision (three alternative sites),
  not three; state 8 cannot be chosen; 0x17 emits particles only when the handle at +0x3cc
  is linked, which never happens, and the class does not request 0x17 itself.
- Skeleton again: the "four own draws" of state 8 are three per rejection attempt plus one
  for the sound, so four at least.

### Zek (`raloszek`)

Run 0x2c2440 (already named), takeDamage 0x2c34e4 (840 bytes, not read), setState
0x2c382c. States 6–0xc: melee arcs. State 0xd: creates a `GroundPoundEffect` with
skill 38. State 0xe: finds an enemy and links a handle. The function tail creates
`LightEffect` objects and plays sounds on animation events. What state 0xe does with the
handle, from `docs/monsters-2.md` (sections 3 and 9.1): it launches a ground wave that travels 5 units
a frame, homes on that enemy and explodes for half melee damage in a radius of 180.

### Innoruuk

Constructor 0x2735dc, run 0x273bd0 (11,760 bytes), takeDamage 0x276a58.
State 3 picks the next attack with six own-generator draws. State 9 creates a `HateBeam`
object (skill 27 pointer); state 10 a `HateProjectile` (skill 28); 0xb, 0xc and 0xe are
shock attacks with camera shake and a `LightEffect`; 0x12 creates a `Prop` and links it;
0x17 is a particle sequence around two bones. Death (0x14) creates a `Prop` and four
`HateSoul` objects, plays nine sounds and calls 0x277110. takeDamage (0x276a58) ignores all
damage while the word at +0x3e0 is non-zero. That word is not a handle, as the earlier
version said: the constructor sets it to 1 when the object has the `invulnerable` property
and to 0 otherwise (0x2735dc, string reference at 0x2737a0), and nothing in the class
clears it. `docs/monsters-2.md` section 3 has the whole fight; it also corrects the death
sequence (a `HateSoul` at intervals for 12 seconds, not four) and identifies the `Prop` of
state 0x12 as his dropped weapon. `HateBeam` (run 0x2775e8) and `HateProjectile` (run
0x2783e8) apply skill 30 (HateEffect) through a `SpellHateEffect`.

### Marr (`MattMarr`)

Run 0x283afc, setState 0x28468c, death effects 0x284b68. State 9 casts skill 66
PlanarWind and links the spell. setState 0x17 adds skill 94 SpiritShield if he does not
already carry that spell type. 0x284b68 is the death sequence (camera shake, particles
from generator 0x404468, deletes the object).

### Natasla

Run 0x29dbf0 is 76 bytes: the creature run and activity calls and nothing else — no AI
states. Draw 0x29d844 is 940 bytes (not read). **Observed.**

### MummyKing

Run 0x29b360, takeDamage 0x29c544 (ignored while creature flag 0x4000000 is set).
State 7: melee with DiseaseWeapons (25) and PoisonWeapons (26) riders. State 8 creates a
`MummySnake` (run 0x29d0c0, PoisonWeapons rider); state 9 creates two `SpawnMummy` objects
(run 0x29cea8); state 0x17 creates a `DustDevil` (run 0x29cb98). State 9 is not "two":
it creates one `SpawnMummy` per player slot at one-second steps and then a shaman, and the
type created depends on his hit points (`docs/monsters-2.md` sections 3 and 9.1).

### SpiderQueen

Run 0x2ad630, takeDamage 0x2aed60. States 6, 7, 10, 0xb: bites with a PoisonWeapons rider.
State 0xc: spits a `PoisonProjectile` (three own draws). States 8–9 are not a jump, as the
earlier version said: 0x2afc28 launches a web strand at the target in state 8, and state 9
reels the caught victim in (`docs/monsters-2.md` sections 3 and 9.2).
Helper 0x2b0080 creates `WebTrap` objects (second constructor 0x2b07c0). takeDamage calls
the creature version and then, for each of six legs, hides the leg (bits in +0xe8) and
spawns effect 3 once hit points fall to that leg's threshold. More from `docs/monsters-2.md` 9.2:
states 7, 10 and 0xb are grab attacks that drag the target with its knockback fields
before biting; the spit makes two projectiles per event and the animation has three
events; the leg thresholds are absolute hit points (140 … 40) and the effect is visual.

### VampireLord

Run 0x2b7be0, takeDamage 0x2b93d8: after the creature version, the first time hit points
drop below half it forces state 0x19 (+0x3ec remembers). States 7–0xb: melee chain with a
ColdWeapons (14) rider; states 0x10 and 0x14 create `Critter` objects with four own draws
(0x14 then deletes the lord). Corrected by `docs/monsters-2.md` (sections 3, 9.1, 9.2): only state 7
(and 0x18) carries the ColdWeapons rider, on the second hit, with twice the queried value,
and it heals the lord by 8 % of his maximum when the bite does damage; states 8–0xb have
no rider and belong to the second form. States 0x10 and 0x14 each make six `Critter` bats,
and the "four own draws" are per bat and a minimum (three or more for the offset, one for
the angle). State 0x14 deletes the lord only after the flee timer. The forced 0x19 goes
through the state filter and can be lost.

### RedDragon

Run 0x25f988. States 6, 7, 8, 0x1c, 0x1d: bites and claws; 9, 10: tail; 0xb–0xe: breath
(helper 0x261328 twice plus arc tests); 0xf creates a `FireStorm` spell object; 0x1b picks
one of 0xb–0xf from four range tests. Corrected by `docs/monsters-2.md` (9.1, 9.2): helper 0x261328 is
effects only — the "arc tests" are the damage calls, a 15-frame tick of a quarter of the
melee range plus an equal fire rider, made in the run function. State 0xf constructs the
`FireStorm` object directly (no skill-table call) at the farthest player within 600, with
no check for "nobody found". State 0x1b chooses among 0xb–0xf from cone tests on any enemy
plus the memory of the last attack.

### Nightmare

Run 0x270bbc: states 6, 0x17, 0x18 kicks; 7 charge. It is also the mount object of the
mounted Horsemen. From `docs/monsters-2.md` 9.2: 6, 0x17 and 0x18 are the same four-hit kick, and the
charge does its damage in the slot-11 override 0x271484, not in the run function.

### Others with boss-like behaviour (script summary only)

Agony (`AvatarAgony`): melee only. AntQueen: state 0x19 creates an `AntWave`; bites carry
a PoisonWeapons rider (not the bite itself: state 6 passes no descriptor, hit call at
0x23747c; the rear attack of state 7 and the sting of states 9 / 10 carry the rider. And
no code was found that requests state 0x19 — `docs/monsters-2.md` 9.2). GnawSpawn: creates three `Prop` objects per spawn state. Minion:
state 9 queries FrostStorm (58) four times and makes a `LightEffect`; 0x17 creates a
`Soul`. IronGuardian: state 9 fires a projectile, 10 a `JunkProjectile`, and its tail
creates a `Droid`.

## 5. Level objects

### Container (barrels, crates, pots, kegs) — run 0x290e78

Constructors 0x2909b0 (type `Container`) and 0x290c24 (all the named barrels and pots).
Loot is rolled in the run function on the frame the break state +0x80 is 1, **from the
container's own generator** (`GameObject_rand(this)`, seeded from the shared generator when
the container was constructed):

1. Skipped entirely when the level name is `tutor`, or when flag 0x20 is set.
2. One draw is discarded, then a `Gold` object is created with amount
   `(draw & 3) × level_monsterLevelTimes0_4() + 1`.
3. One draw below 7500 of 65536 (11.4 %) → items. Count: 1, or 2 when the next draw is
   ≥ 63000, or 3 when ≥ 65500; two more when the level name contains `tower`. One further
   draw is compared with 10000 (30000 in `tower` levels): below → every item is the named
   item `arrows` (0x1069b8), otherwise every item comes from `item_generateConsumable`
   (0x108590), **which draws from the shared generator** (seven uses in its body).
4. Independently, one draw ≤ 1.5 % → a potion stack: `firepotion`, `explodingpotion` or
   `gaspotion` by thirds of the next draw, quantity 3–6.
5. Every dropped item is thrown in a random direction within ±45° of the container's
   facing (one draw each).

Explosive containers (flag 4): the fuse +0x74 runs 180 frames, then an area hit through
`world_damageInRadius` (0x161270) (float arguments 40 and 180) with damage `(monster level − 2) × 20 + 15`, a camera shake, a
`LightEffect` and debris props; the container deletes itself. A container that is pushed
keeps a velocity that decays by 0.86 per frame and leaves the run list when it stops.

### Chest — interact 0x292a2c, run 0x2923a8

First interact: opening animation and sound, `+0x84 = 1`, `+0x50 = frame`, joins the run
list; the interact flag is cleared when no gold is inside. Loot comes from the chest's
level-file parameters, in this order:
- every `item=<name>`: that named item (0x1069b8);
- `potions=<n>`: n times `item_generateConsumable` (shared generator);
- every `random=<value>`: an item of worth `2 × value × level_monsterLevelTimesDifficulty()
  × (0.95 + own draw × 0.1) × 600` built by `item_generateWithAffixes`, with one own draw
  mod 3 choosing an entry of the table at 0x5016b8;
- then one `loot_generateDrops` call.
A second interact while gold remains gives the gold (+0x4c) to that player. A trapped chest
(+0x58) explodes 90 frames after opening: the same area hit with damage
`(monster level − 2) × 4 + 15`.

### AutoChest / AutoProp / AutoContainer family

`AutoObject` (constructor 0x23a354, draw 0x23aa20) is the base of 16 data-driven classes;
the `…LP` variants and `EggSack`, `DiseasePort` share run 0x2421e0 and draw 0x241ee4.
`AutoChest_dropLoot` (0x23ba3c, `autoobject_dropLoot` in the earlier version; one caller,
`AutoChest_run` 0x23b170 at 0x23b674 — not AutoProp_run or 0x23d2ec as first written;
AutoProp has no loot) follows the same parameter scheme as Chest — `spawncreep`, `item`, `potions`,
`random` — and otherwise three `loot_generateDrops` calls plus one own draw: below 5000 →
`arrows`, below 15000 → a consumable. Its `random` items are not priced by the Chest
numbers: worth × 300, doubled from act 1 on and zero in act 0, with the category from the
table at 0x4fece8; and AutoContainer has its own inline loot code with different odds
(`docs/monsters-2.md` sections 6 and 9.2). AutoContainer_run (0x23e430, 5,680 bytes) repeats
the Container logic with a `reduceCarnage` parameter; it was only skimmed.

### Generator (`AntMaker`) — run 0x265938

A creature-derived object. Returns at once when `Creature_updateActive` says inactive.
State 0 (dormant) wakes to state 3 when it sees a player: flag bit 1 set → a 500-unit ray
ahead (0x18ad94) hitting a player, or, every 8th frame (frame counter xor +0x230), any
living player in a 400-unit box centred 200 units ahead; bit 1 clear and bit 0 clear → the
ray only; bit 1 clear and bit 0 set → it never wakes by itself. State 3: when the previous spawn is dead or absent and fewer than +0x3d4 have
been made, creates an object of type +0x3c8 through the factory, and for a creature stores
the type name at +0x34, sets creature flag 0x1000000 and links it at +0x3e0.
`ScriptGenerator` (constructor 0x265f54) is the script-driven version: 0x265fc4 spawns the
type it is given and puts a Skeleton into state 0x17.

### CreatureContainer — run 0x2437ec

Follows the object in its handle +0x3c8 (copies its position and re-links the grid cell)
and queues itself for deletion when the handle is empty; otherwise only the base creature
calls. Its constructor 0x243624 also references `AutoContainer`: it creates one and
shadows it (`docs/monsters-2.md` 9.2).

### Savepoint (`SavePoint`) — run 0x28cdd0

- Every 8th frame `Savepoint_scanPlayers` (0x28d6dc) counts living players within 120
  units and re-arms the auto-save when nobody is within 150.
- **Resurrection:** in a game with more than one player, when someone is dead and a living
  player is within 120 units, the last player who is dead, for whom `net_isSlotActive` (0x13dd40) is true and
  whose entry in the table at 0x4f84a8 is zero is brought back at the save point with
  `player_respawn`, using one draw from the shared generator (inside the every-8th-frame
  block of Savepoint_run).
- **Auto-save:** armed, at least one player near, none "busy", and not in a no-save zone →
  `save_game(0,0,0)`, mark used.
- **Manual save:** interact (0x28dc30) sets +0x84, asks the memory-card code to open the
  save dialog for that player, lights the point and fires its `action` scripts. The
  "saved" burst (+0xcc 1→4: a sound, an animation, four rings of particles from the
  point's own generator, `+0x80 = 1`) starts when game message type 5 arrives.
- State saved in the level record: +0x80 (or +0x84), +0xc5, +0xc6.

### JumpGate (`Portal`, `PortalHurt`) — run 0x27cb58

- A `script` parameter names a script that is run every frame while the gate is in use;
  its result enables the gate.
- First activation (+0x4d = 0): when every living player is within 100 units, calls
  `JumpGate_openMenu(player, destination parameter, notDrawn)` and sets +0x4d.
- Later (+0x4d = 1): the same test, but only on frames where +0xd0 is set (see 7.1), and
  only when no task named `jumpgate` exists.
- `jumpgate_menuRun` (0x27dd74) is a run task: state 0 finds the current level in the
  destination list and, when the gate has a destination parameter, skips to state 4;
  offline it also pauses the game. State 2 reads the chosen player's lockstep pad: cancel,
  confirm (sets 0x500ae8 to 1), up/down. State 5 counts 0x500ae8 to 180 and then writes the
  next world name to 0x41b6d0. `script_gamePaused` reads 0x500ae8.
- The destination list (0x8e3a50) is saved and loaded by 0x27dcf4 / 0x27dd30; a level adds
  itself with 0x27db60.

### Teleporter — run 0x28ef0c

The run function only emits two particles per frame from the object's own generator. The
class is creature-derived (0x3c8 bytes); whatever moves the player is not in its run,
draw or setState (0x28f154 is an empty function). **Unknown** where the teleport happens —
probably the creature interact path or a level script. Confirmed by `docs/monsters-2.md` (9.1):
nothing in the class moves a player; only the base `dialogScript` paths exist, so the
teleport is a level script's doing.

### Trap (`Trap`) — run 0x29507c

Every 32nd frame: box query of its radius; every living player inside takes a hit through
`damage_apply` (20–30, flag 0x40, plus 0x4000000 on every 64th frame) with a rider: skill
13 FireWeapons when the object has a `fire` parameter, otherwise skill 26 PoisonWeapons.
The rider strength is that skill's +0x5c value at the monster level × 0.15.

### Lever, Timer, Counter and the `action` mechanism

`0x14dcc8(object, on)` (objects area) runs, for every `action=<name>` parameter of the
object, the script `<name>` when `on` is non-zero and `not<name>` when it is zero.
- Lever: interact starts the swing; run moves +0x4c by 1.5/60 per frame and at the end
  fires the action — "on" when the `onOnly` parameter is set or the lever moved forward,
  never "on" when `offOnly` is set — flips direction and becomes usable again unless one
  of those parameters is set.
- Timer: slot 3 starts it with `time` × 60 frames and remembers the value; run counts down
  and fires the action with that value, then leaves the run list.
- Counter: slot 3 counts up for a non-zero value and down for zero; on reaching the
  `count` parameter (default 1) fires the action (forced on by `onOnly`, off by `offOnly`).
- FloorSwitch, Switch, DoorSwing, DoorSecret, RollDoor, FallPlatform are the `WorldPart`
  classes (tables 0x50de28–0x50e100); not read.

### Lights

Torch (also `Fire`, `Campfire`, `Firepot`, `Firepot2`, `OilLamp`), Candle, Candle2
(`Candle3`), Lamp, Lantern. A light is put on the run list by its draw function and takes
itself off after 31 undrawn frames; see 7.4. Torch's touch handler 0x2b2860 burns whoever
touches it with a FireWeapons rider and one shared-generator draw.

### DragonGoldPile, WeaponRack, others

DragonGoldPile_run (0x295d58) only makes sparkles (see 7.3). WeaponRack has no run
function. LightningRod (run 0x295954) creates `LightningBolt` objects. SpiritAnchor has
its own takeDamage (0x296888). Not read further.

## 6. Skills cast by monsters

Skill ids index the table at 0x41b170. "cast" is a call through the skill's own table at
offset 0x14, "can-cast test" at offset 0x0c, "value query" at 0x5c or 0x64 (used to size an
elemental rider or an effect); a bare pointer means the skill object is handed to a spell
or projectile constructor. **Observed** by script over every function of each class; the
Horsemen, Cazic and Trap rows were also read by hand.

| Class | Skill id | Skill | How it is used | In function |
|---|---|---|---|---|
| Ant | 13 | FireWeapons | value query (+0x5c) | 0x2359fc |
| Ant | 26 | PoisonWeapons | value query (+0x5c) | 0x2359fc |
| AntQueen | 26 | PoisonWeapons | value query (+0x5c) | 0x236f78 |
| Bubo | 4 | DiseaseBolt | cast | 0x248598 |
| Bubo | 5 | DiseaseShield | cast | 0x248598 |
| Bubo | 29 | DiseaseEffect | pointer passed to an object constructor or helper | 0x248598 |
| Bubo | 55 | Healing | cast | 0x248598 |
| Bubo | 97 | DiseaseBlade | cast | 0x248598 |
| Cazic | 7 | FireStorm | cast | 0x24aaf0 |
| Cazic | 11 | SummonSkeleton | can-cast test; cast | 0x24aaf0 |
| Cazic | 23 | ShockOfFrost | pointer passed to an object constructor or helper | 0x24c7fc |
| Cazic | 38 | GroundPound | pointer passed to an object constructor or helper | 0x24aaf0 |
| Cazic | 57 | ShockOfFire | call +0x44; value query (+0x64) | 0x24c5a4 |
| Cazic | 58 | FrostStorm | cast | 0x24aaf0 |
| Cazic | 95 | WaveOfFlame | cast | 0x24aaf0 |
| Cazic | 96 | FrostArmor | cast | 0x24aaf0 |
| CloudGiant | 14 | ColdWeapons | value query (+0x5c) | 0x250714 |
| Demon | 7 | FireStorm | pointer passed to an object constructor or helper | 0x25e17c |
| Demon | 57 | ShockOfFire | value query (+0x64) | 0x25e17c |
| FemaleDarkElf | 11 | SummonSkeleton | can-cast test | 0x259a98 |
| FemaleDarkElf | 24 | PoisonRain | cast | 0x259a98 |
| FemaleDarkElf | 26 | PoisonWeapons | cast | 0x259a98 |
| FemaleDarkElf | 37 | Shock | cast | 0x259a98 |
| FemaleDarkElf | 55 | Healing | cast | 0x259a98 |
| FemaleDarkElf | 80 | PusStorm | cast | 0x259a98 |
| FemaleDarkElf | 94 | SpiritShield | cast | 0x259a98 |
| FireBeetle | 13 | FireWeapons | value query (+0x5c) | 0x24587c |
| Froglock | 44 | ColdArrow | pointer passed to an object constructor or helper | 0x264314 |
| Froglock | 45 | PoisonArrow | pointer passed to an object constructor or helper | 0x264314 |
| Goblin | 7 | FireStorm | cast (the earlier scan read it as a pointer passed on; the call is through table offset 0x14 with the level from slot 35, 0x26c4f4–0x26c53c) | 0x26b27c |
| Goblin | 13 | FireWeapons | cast | 0x26b27c |
| Goblin | 14 | ColdWeapons | cast | 0x26b27c |
| Goblin | 23 | ShockOfFrost | cast | 0x26b27c |
| Goblin | 37 | Shock | cast | 0x26b27c |
| Goblin | 43 | FireArrow | pointer passed to an object constructor or helper | 0x26b27c |
| Goblin | 44 | ColdArrow | pointer passed to an object constructor or helper | 0x26b27c |
| Goblin | 47 | ExplodeArrow | pointer passed to an object constructor or helper | 0x26b27c |
| Goblin | 57 | ShockOfFire | cast | 0x26b27c |
| Goblin | 58 | FrostStorm | cast (same call as the FireStorm row, 0x26c514–0x26c53c) | 0x26b27c |
| Gremlin | 43 | FireArrow | pointer passed to an object constructor or helper | 0x26e4c4 |
| Gremlin | 44 | ColdArrow | pointer passed to an object constructor or helper | 0x26e4c4 |
| Gremlin | 47 | ExplodeArrow | pointer passed to an object constructor or helper | 0x26e4c4 |
| Hag | 37 | Shock | cast | 0x26f504 |
| Hag | 100 | LightningStrike | cast | 0x26f504 |
| Hag | 101 | ConeOfShock | cast; value query (+0x5c) | 0x26f504 |
| HateBeam | 30 | HateEffect | pointer passed to an object constructor or helper | 0x2775e8 |
| HateProjectile | 30 | HateEffect | pointer passed to an object constructor or helper | 0x2783e8 |
| Horsemen | 4 | DiseaseBolt | cast | 0x27236c |
| Horsemen | 7 | FireStorm | cast | 0x27236c |
| Horsemen | 11 | SummonSkeleton | can-cast test; cast | 0x27236c |
| Horsemen | 87 | TagarsInsects | cast | 0x27236c |
| Innoruuk | 27 | HateBeam | pointer passed to an object constructor or helper | 0x273bd0 |
| Innoruuk | 28 | BallOfHate | pointer passed to an object constructor or helper | 0x273bd0 |
| Kobold | 55 | Healing | cast | 0x27f52c |
| Kobold | 96 | FrostArmor | cast | 0x27f52c |
| LavaMonster | 13 | FireWeapons | value query (+0x5c) | 0x28048c, 0x2822e8 |
| MaleDarkElf | 43 | FireArrow | pointer passed to an object constructor or helper | 0x25bbe4 |
| MaleDarkElf | 44 | ColdArrow | pointer passed to an object constructor or helper | 0x25bbe4 |
| MaleDarkElf | 45 | PoisonArrow | pointer passed to an object constructor or helper | 0x25bbe4 |
| MaleDarkElf | 46 | MultiFire | value query (+0x5c). The result is not a melee rider: it is the number of `MultiFireProjectile` objects to create (query call at 0x25c984; `docs/monsters-2.md` 9.2) | 0x25bbe4 |
| Marr | 66 | PlanarWind | cast | 0x283afc |
| Marr | 94 | SpiritShield | pointer passed to an object constructor or helper | 0x28468c |
| Minion | 58 | FrostStorm | value query (+0x64) | 0x2862c0 |
| Mummy | 4 | DiseaseBolt | pointer passed to an object constructor or helper | 0x298d18 |
| Mummy | 5 | DiseaseShield | value query (+0x64); the spell is also constructed (`SpellDiseaseShield_ctor` 0x2ccfc8; `docs/monsters-2.md` 9.2) | 0x298d18 |
| Mummy | 7 | FireStorm | pointer passed to an object constructor or helper | 0x298d18 |
| Mummy | 18 | ConeOfFire | pointer passed to an object constructor or helper | 0x298d18 |
| Mummy | 23 | ShockOfFrost | pointer passed to an object constructor or helper | 0x298d18 |
| Mummy | 24 | PoisonRain | pointer passed to an object constructor or helper | 0x298d18 |
| Mummy | 57 | ShockOfFire | value query (+0x64) | 0x298d18 |
| Mummy | 58 | FrostStorm | cast | 0x298d18 |
| MummyKing | 25 | DiseaseWeapons | value query (+0x5c) | 0x29b360 |
| MummyKing | 26 | PoisonWeapons | value query (+0x5c) | 0x29b360 |
| MummySnake | 26 | PoisonWeapons | value query (+0x5c) | 0x29d0c0 |
| OniBall | 59 | LifeTap | pointer passed to an object constructor or helper | 0x2946f8 |
| Orc | 24 | PoisonRain | pointer passed to an object constructor or helper | 0x2a1848 |
| Orc | 37 | Shock | cast | 0x2a1848 |
| Orc | 43 | FireArrow | pointer passed to an object constructor or helper | 0x2a1848 |
| Orc | 44 | ColdArrow | pointer passed to an object constructor or helper | 0x2a1848 |
| Orc | 47 | ExplodeArrow | pointer passed to an object constructor or helper | 0x2a1848 |
| Orc | 55 | Healing | cast | 0x2a1848 |
| PoisonProjectile | 26 | PoisonWeapons | value query (+0x5c) | 0x2b176c |
| Skeleton | 43 | FireArrow | pointer passed to an object constructor or helper | 0x2a6864 |
| Skeleton | 44 | ColdArrow | pointer passed to an object constructor or helper | 0x2a6864 |
| Skeleton | 47 | ExplodeArrow | pointer passed to an object constructor or helper | 0x2a6864 |
| SpiderQueen | 26 | PoisonWeapons | value query (+0x5c) | 0x2ad630 |
| Torch | 13 | FireWeapons | value query (+0x5c) | 0x2b2860 |
| Tormentor | 23 | ShockOfFrost | pointer passed to an object constructor or helper | 0x287db0 |
| Tormentor | 56 | ConeOfFrost | cast | 0x287db0 |
| Trap | 13 | FireWeapons | value query (+0x5c) | 0x29507c |
| Trap | 26 | PoisonWeapons | value query (+0x5c) | 0x29507c |
| Ulthork | 23 | ShockOfFrost | pointer passed to an object constructor or helper | 0x2b5a08 |
| Ulthork | 58 | FrostStorm | value query (+0x64) | 0x2b5a08 |
| VampireLord | 14 | ColdWeapons | value query (+0x5c) | 0x2b7be0 |
| WarWraith | 14 | ColdWeapons | value query (+0x5c) | 0x2c0c2c |
| Wraith | 14 | ColdWeapons | value query (+0x5c) | 0x2bf538 |
| Zek | 38 | GroundPound | pointer passed to an object constructor or helper | 0x2c2440 |

## 7. Per-machine state

Method. For every function in the range a script searched the decompile for reads of the
camera globals (0x44f038–0x44f168), the cosmetic generators (0x404460, 0x404468), the
render counters (0x44fdd0, 0x506048), the prediction-copy and menu globals, the pad block,
and for calls to `net_getLocalPlayerSlot`, `net_isLocalSlot`, the audio status functions,
`isNearCameraFocus480`, `isNearView`; and, for every draw function and everything it calls
inside this range, for `GameObject_rand`, the shared generator, `pool_new`, run-list
changes and `script_runByName`, and for stores into the object. Virtual calls and
functions outside the range (all of the creature base, the weapon helper, effects) were
not followed. Hits were then read by hand. "None found" below means none by that method.

Not repeated per class: every monster run function calls `Creature_run`,
`Creature_updateActive` and `Creature_processDamage` (0x110d30), and every monster draw calls `Creature_draw`; their
known hazards (FINDINGS D6, D12–D14) apply to all 73 creature classes.

### 7.1 JumpGate: run logic depends on whether the gate was drawn — Observed

- `JumpGate_draw` (0x27d634) begins by storing 1 at +0xd0. `JumpGate_run` (0x27cb58) tests
  +0xd0 throughout and stores 0 on every exit path.
- For a gate that has been opened before (+0x4d = 1) the run function returns early when
  +0xd0 is 0 (branch after 0x27d1d8). Skipped on such a frame: the own-generator particle
  draws, the animation step, and **the test "all living players within 100 units → open
  the travel menu"** (`JumpGate_openMenu` adds the run task `jumpgate_menuRun`).
- +0xd0 is also what decides the light on/off every 32nd frame, the six own-generator
  draws of the active effect, and the third argument of `JumpGate_openMenu`, which becomes
  0x8e3c38 (read only by the travel effect).
- Whether +0xd0 is set when run executes differs between machines: the gate may be outside
  one camera's frustum, the draw pass may stop early (FINDINGS D13), and when a machine
  simulates two frames between two rendered frames the second one sees 0.
- **Inferred consequence:** the frame on which the travel menu task starts — and with it
  0x500ae8, which `script_gamePaused` reads, the 180-frame countdown and the frame the next
  world name is written — can differ between machines. With a gate that has a
  `destination` parameter there is no menu input to re-align them: state 0 goes straight
  to the countdown. Not confirmed on a running game.
- **Not reachable with the levels on the disc** (`docs/issues/sync-breakers.md` section 5,
  B7): the automatic open is taken only by a gate whose `hurt` property is non-zero (the
  constructor copies it to +0x4f, 0x27c848–0x27c860), and none of the 38 gates on the disc
  has `hurt` or `destination`. For the gates that exist the drawn flag reaches only the
  gate's own generator, its animation and a glow state.

### 7.2 Jump-gate travel effect writes player fields from a draw task — Observed

`jumpgate_travelEffect` (0x27e770) is called only from the draw task `jumpgate_menuDraw`
(call at 0x27e66c; the task is registered as a draw task at 0x27da84, inside
`JumpGate_openMenu`). It stores into every living player's object: +0xf0 = frame counter
and +0x394 = 0x78 when the countdown is at 30 (menu path), and, on the automatic path with
a 1-in-10 chance per player per drawn frame from the cosmetic generator, the eight shorts
at +0x90…+0x9e. +0x394 is status counter 10 (drawing only, FINDINGS D15). +0xf0 is read by
`Creature_run` at 0x113768, inside the status-counter-7 branch. **Inferred:** harmless
unless counter 7 is running on that player (D16).

### 7.3 DragonGoldPile_run reads the camera — Observed

0x295d58 compares the camera position (0x44f038) and two camera orientation values
(0x44f118, 0x44f124) with copies kept in the object (+0x4c…+0x60); when the camera moved
it makes two sparkles, each placed with three or more draws from **the pile's own
generator**, then stores the new camera values. So the pile's generator state and those
fields differ between machines. Nothing else in the class reads them (**Observed**: the
class has only this run function and inherited slots); **Inferred:** no effect on shared
state.

### 7.4 Lights join the run list from draw code — Observed

`Torch_draw` 0x2b2ae8 clears a "frames since drawn" byte (+0x89) and, when the torch is
not running (+0x88 = 0), calls `obj_runEveryFrame` (0x14f248) (link into the every-frame run list) and sets
+0x88. `Candle_draw` 0x2b30ac, `Candle2_draw` 0x2b33b4, `Lantern_draw` 0x2b3638 and
`Lamp_draw` 0x2b3a64 make the same call and the same two byte stores (found by script,
not read line by line). The run functions count the byte up and call `obj_stopRunning` (0x14f290) after
31 frames. Which lights run, and where they sit in the run list, therefore differs between
machines. Their run functions (0x2b2088, 0x2b2dc4, 0x2b3164, 0x2b3554, 0x2b3858) call only
`GameObject_rand(this)`, the sine table, the particle emitter and `obj_stopRunning` (0x14f290) (Lantern_run also
calls `libc_strstr`), and write only their own light fields; Torch_run and Torch_draw also use the object's address as a noise
phase. **Inferred:** no effect on shared state; the lights' own generators are not in sync.
`Torch_onTouch` (0x2b2860), which does use the shared generator, is called from collision
code, not from the run list.

### 7.5 AntWave draws from its own generator in draw code — Observed

`AntWave_draw` (0x2387d0): when the object's age is a multiple of 3 it takes three or more
values from `GameObject_rand(this)` to place a particle. `AntWave_run` (0x238938) moves the
object toward its target with the path helper `Creature_moveTo` (0x114510), which takes a value from the same
generator to choose a turn direction when blocked (0x114510, call to `GameObject_rand`),
and every 60 frames damages the target when within its radius. **Inferred consequence:**
on machines that drew the wave a different number of times, a blocked wave turns
differently, so its position and the damage it does can diverge. AntWave objects are
created only by AntQueen_run (state 0x19). No code that requests state 0x19 was found
(`docs/monsters-2.md` 9.2), so the hazard described here looks unreachable.

### 7.6 Savepoint — Observed

- `Savepoint_interact` (0x28dc30) acts only when `memcard_isBusy()` and
  `menuMutex_isHeld()` are both false. The first is this machine's memory-card state. What
  it gates: +0x84, the light, and `0x14dcc8(this, 1)`, which **runs the save point's
  `action` scripts**. A machine whose card code is busy (for example the one already
  showing the save dialog) skips them. **Inferred:** matters only for save points that have
  an `action` parameter and are used twice in quick succession. No Savepoint on the disc
  has an `action` (`docs/issues/sync-breakers.md` B7), so with the shipped levels nothing
  is skipped.
- `Savepoint_run` clears +0x84 from `memcard_getState()` and from the save-finished flag
  0x4f8f29, both per machine. The card-state test clears it only when the state is 0, a
  boot-time value, not when the card is idle (−1) (0x28ce40–0x28ce4c). While +0x84 and +0xcc are set it draws from the point's own
  generator and sets +0x80 (which is written to the level save record by slot 9).
- The "saved" burst is started by game message type 5. `hudmsg_sendSavepoint` (0x1de1a0)
  puts the Savepoint's **address** into the message; the handler (`hud_onMsg` case 5, call
  at 0x1d8f00) passes the received word to `Savepoint_startSavedEffect` (0x28cdc4), which stores 1 at
  address+0xcc with no check. A pointer value is sent between machines and dereferenced.
  **Inferred:** correct only while every machine has that object at the same address; if
  not, one word of unrelated memory is overwritten.
- `Savepoint_scanPlayers` sets +0xc9 through `net_isLocalSlot`; +0xc9 only selects who sees
  a HUD line (run, `net_getLocalPlayerSlot` at the end of 0x28cdd0).
- The resurrection and the auto-save use only lockstep state: player positions, hit
  points, the frame counter, the shared generator.

### 7.7 Scripts run from draw code — Observed

`NPC_draw` (0x29e3ec), `Gnome_draw` (0x2691f0), `GnomeNavigator_draw` (0x26a000) and
`Rondo_draw` (0x29f28c): when the camera object that 0x4f8450 points to is in mode 1
(follow; +0x34 of the object — the earlier version read 0x4f8450 as the structure itself;
it is `g_localCamera`, a pointer) and the object has
an `exclamation` parameter, the function runs that script through `script_runByName` on
every drawn frame and draws a marker when it returns 1. The one such script found by name
(`check1Exclam` / `check2Exclam` in INNOVAT1) only reads: getEvil, getv, playerHasItem.
**Inferred:** harmless unless some level's exclamation script writes a variable or calls
getRand; the other levels' scripts were not checked. The gate is a per-machine value: the
mode is written only by `Camera_setMode` 0x2072e8 and `Camera_updateFree` 0x20440c and is
0 while a menu, shop, dialog camera or cutscene holds the local camera. `NPC_draw` also
needs the NPC to be more than 240 units (300 in a cutscene) from the camera; the other
three draws have no such test (`docs/monsters-2.md` 7.1 M6, 9.1, 9.2).

### 7.8 UndeadKnight_draw copies uninitialised stack into the position — Observed, unreachable

0x2b421c, when the mount handle +0x3c8 is set: 12 bytes are loaded from the top of the
function's own stack frame, which nothing has written (0x2b424c–0x2b426c), and stored to
the position; facing is set to 0; a bone offset is subtracted; nothing is restored. The
handle is cleared by the constructor and no code links it (**Observed**: field search for
+0x3c8 between 0x2b3e30 and 0x2b5370 finds only the clear and reads), so the path is
**Inferred** dead. (The search stopped one function short: 0x2b5370 itself links the
handle, but nothing calls or references 0x2b5370, so the path is still dead — `docs/monsters-2.md` 9.2,
whole-file scan.) The mounted knights in the game are `Horsemen`, whose draw (0x2721f8)
builds a matrix from the mount instead and writes nothing.

### 7.9 Smaller items

| Where | What | Kind |
|---|---|---|
| Cazic_deathEffects 0x24c994, Marr death 0x284b68 | use generator 0x404468 for beam jitter and particle scatter; the counts of own-generator draws depend only on the death timer | Observed; cosmetic |
| every monster constructor (0x271dd8 in Horsemen_ctor, 0x24a73c in Cazic_ctor, 0x2a8898 in Skelight_ctor) | stores the frame counter at +0xec ("hits register from"); the counter equals the lockstep frame only inside a simulated tick | Observed store; Unknown whether any constructor runs outside a tick with differing values |
| Skelight_ctor 0x2a8770 | swaps the global monster level 0x4f714c during construction | Observed; lockstep as long as the caller is |
| OniBall_run 0x2941e4, OniBall_onTouch 0x2946f8 | read `g_pads[player]+8` (the lockstep pad block) to decide whether the orb flies to the player; the touch handler tests the prediction-copy flag 0x20000 | Observed; not a hazard |
| jumpgate_menuRun 0x27dd74 state 2 | when `net_isLocalSlot(player)` and `pauseMenu_isOpen` (0x18cbfc) are both true it calls `net_lockLocalInput` (0x13e4e8)(player, 4) instead of reading the pad | Observed; whether the other machines see the same thing on that frame is Unknown |
| jumpgate_beginTravel 0x27e6a8 | copies the camera position into 0x8e3918 for the effect | Observed; cosmetic |
| Container_run 0x290e78 | keeps a sound handle at +0x78 and stops it on explosion | Observed; audio only |
| Catapult_draw 0x24dc40, NPC_draw 0x29e3ec | read the camera to orient what they draw | Observed; no store to shared state found |
| Critter, FireBeetle, FireFly, Mosquito, AntQueen draw | store to position or facing fields; not read (expected to be a temporary offset restored after drawing). Read since for four of the five (`docs/monsters-2.md` 9.2): FireBeetle, FireFly and AntQueen undo their stores before returning; Mosquito saves the fields at entry and restores them after `Creature_draw` (0x297a3c–0x297a54, 0x297afc–0x297b14). Critter was not resolved | temporary, restored (four of five); Critter still Unknown |
| AutoObject_draw 0x23aa20 and the LP draws | store to the object flag word +0xc; LP draws read the render frame counter 0x44fdd0. Read since (`docs/monsters-2.md` 9.2): the flag is 0x100. `AutoObject_draw` only clears it; the LP draws would set it, but that store is unreachable (the guard 0x240db0 returns 0). Nothing reads the flag | flag 0x100, no reader (was: Unknown which flag; not read) |
| Creep_draw 0x253514 | stores to the creature flag word +0xa8 | Unknown; not read |

### 7.10 What was looked for and not found

- No draw function in this range (or anything it calls inside the range) creates an
  object, draws from the shared generator 0x404464, or queries the world; the only draw
  functions that draw from an object generator or run a script are the ones above.
- No run function in this range reads the hardware timer, the audio stream position or
  status, the raw pads, or the prediction-copy globals.
- Horsemen, Cazic (avatar), Skelight, Skeleton and UndeadKnight — the Drundar arena set —
  make no per-machine read in their own run, setState, draw or helper functions. What they
  share with every monster is the creature base, the weapon helper object at +0x50 (its
  update is called from run at table offsets 0xac/0xb4 and its draw from draw at 0x94/0x9c;
  class `WeaponShield` at table 0x50cda0 — `Weapon1` at 0x50cf40 for Skelight — not in
  this area, **not read**) and the skills they cast.

## 8. Corrections to earlier notes

- **Cazic's run function is 0x24aaf0, not 0x248598.** 0x248598 is `Bubo_run`. The
  "ruled out" paragraph of FINDINGS that says the function at 0x248598 reads no camera or
  local-player state was checking the wrong class. Having read the right one: the same
  conclusion holds for 0x24aaf0 and its helpers (7.10). (FINDINGS and `names.tsv` have
  since been corrected to 0x24aaf0.)
- The `names.tsv` note on `Cazic_ctor` ("casts FireStorm and SummonSkeleton") is true only
  of the `cazicthule` variant above half health; the `cazicavatar` variant casts neither
  (section 4). (The note has since been rewritten to say this.)
- Horsemen variant 3 does not wait for its skill timer: it casts SummonSkeleton whenever
  the skill's "can cast" test passes (0x2726a0–0x27271c); only variants 0–2 are gated by
  +0x474.
- State 0x14 is the death state, not a cutscene state (1.4).
- 13 tables that `vtables.txt` listed as `Projectile`, `WorldPart` or `FireBeetle` (it has
  since been regenerated with the right names, see `docs/issues/vtable-labels.md`) are
  derived classes whose type-info function names the base first: 0x50de28 FallPlatform,
  0x50deb8 FloorSwitch, 0x50df48 Switch, 0x50dfd8 DoorSecret, 0x50e068 RollDoor, 0x50e100
  DoorSwing, 0x50e3d8 beetleProjectile, 0x50e638 IceBall, 0x50e758 Root, 0x50e7e8
  LostSoul, 0x50e878 OniBall, 0x50e998 Sparks, 0x5108c8 FireFly (**Observed**: the last
  class-name string referenced by each type-info function).

## 9. Open questions

1. Does the arena's Cazic object really have type `cazicavatar`? Read the object list of
   the DRUNARE world file.
2. JumpGate (7.1): does any shipped level reuse an already opened gate with a
   `destination` parameter in a net game? Two running copies would settle whether the
   start frames differ.
3. Savepoint message 5 (7.6): are object addresses identical on all machines at that
   point? Compare the address in the message with the local object in a two-machine run.
4. The weapon helper class (`WeaponShield`, table 0x50cda0; `Weapon1`, table 0x50cf40, in
   Skelight): its per-frame update and its draw are called
   by Horsemen, Skelight, Skeleton, UndeadKnight and other armed monsters. Does its draw
   change anything its update reads?
5. What exactly SummonSkeleton's "can cast" test (skill table offset 0x0c) counts — it is
   the only limit on knight variant 3's summoning.
6. Meaning of slots 10, 12, 17–19, 21, 36 where classes override them (80 functions are
   named `Class_vslotN`). (Table offsets 0xbc, 0xcc, 0xd4, 0xe4 were listed here as well;
   they are slots 23, 25, 26, 28, and `docs/creatures.md` gives the base meaning of every
   creature slot.)
7. Where the Teleporter moves the player. (Answered: not in the class; a level script
   through the base `dialogScript` path — section 5.)
8. The draw functions that store to position, facing or flag fields (7.9, last three
   rows) should be read to confirm the stores are undone. (Done for all but `Critter_draw`
   and `Creep_draw`: see the two rows.)
9. `net_lockLocalInput` (0x13e4e8)(player, n) and `pauseMenu_isOpen` (0x18cbfc), used by the jump-gate menu for the local player.
10. `Orca`, `lb_block` and a few other factory names could not be attributed with
    certainty.

## 10. What was not done

- Read in full: Horsemen, Cazic, Skelight (all functions); Savepoint, Chest, Container
  (loot part), Generator, CreatureContainer, Timer, Counter, Lever, Trap, Teleporter,
  Torch, DragonGoldPile, AntWave, the JumpGate run function and its menu task.
- Summarised by script only (state → helpers called, objects created, skills used): the
  other 66 creature classes, including Zek, Innoruuk, Marr, MummyKing, SpiderQueen,
  VampireLord, RedDragon and Nightmare. Their damage numbers, ranges and timers are not in
  this document.
- Not read at all: the AutoObject family beyond the loot function (about 60 functions),
  the door and switch classes, the monster projectiles (HateBeam, HateProjectile, LavaBomb,
  FireBomb family, IceBall, Root, LostSoul, Sparks, PoisonProjectile, DiseaseProjectile),
  SpiritAnchor, Catapult, WebTrap, LightningRod, NPC, the 32-byte static-initialiser pairs,
  and the four functions before 0x233bdc. (`docs/monsters-2.md` has since read these
  classes. One correction to the list itself: `Root` is not a monster projectile — its
  only creator is `Player_run`.)
- 151 of the 885 functions are unnamed: private helpers called from one class, the
  static initialisers, and a few with no caller found. 81 of the named ones are
  `Class_vslotN` — known to be that class's override of slot N and nothing more.
