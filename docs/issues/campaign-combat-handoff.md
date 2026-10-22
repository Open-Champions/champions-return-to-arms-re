# Campaign combat handoff (SLUS-20973 US v2.00)

Research for Open Champions `play-enemies-r1`, dated 2026-10-22. **Status: the
client's real-level fight remains blocked.** The tests below execute individual
original functions in `tools/ee_emu.py`; they do not run the game or establish a
campaign fight in the client. No disc content is recorded here.

## 1. What the first 16 unbuilt records actually are

**Observed in the client:** the strict playthrough result enters level index 36
and reports 0 built, 16 unbuilt, 0 live enemies. The client's sorted level list
maps index 36 to `hub`. **Observed in private input:** `HUB.GOB` has 24 object
records. **Executed** by `difftest_campaign_combat.py`: the original factory
constructs 16 GameObjects, none hostile. These are the 16 the client counted as
unbuilt. It did not report 16 creature records.

| Record indexes | Count | Original factory result | Reason the client cannot build them |
|---|---:|---|---|
| 0 | 1 | `apprings`: 0x498, ctor 0x24388c | RingPortal/AutoProp path not in the five ported classes |
| 1–5 | 5 | `bflya`/`bflyb` with `critter=1`: 0x448, ctor 0x2547fc | property fallback to Critter not ported |
| 6 | 1 | `Portal`: 0x164, ctor 0x27c694 | portal not ported |
| 7, 9 | 2 | `Player1`: 0x4c, ctor 0x158928 | start marker is not a combat Player; marker path not ported by this factory host |
| 8 | 1 | `Savepoint`: 0x118, ctor 0x28cb90 | save point not ported |
| 10 | 1 | `NPC`: 0x480, ctor 0x29df04 | friendly talking creature not in the five ported classes |
| 11–12 | 2 | `PushTrigger` 0x4c / 0x1ec900; `Trigger` 0x70 / 0x1ecdf4 | triggers not ported |
| 16–18 | 3 | character light markers: 0x4c, ctors 0x158bcc / 0x158c6c / 0x158d0c | marker constructors not ported |

The six ambient/directional lighting records at indexes 13–15 and 19–21 make
no object. `clearColor` and `customVars` at 22–23 are side effects, not combat
actors. The factory is `world_objectFactory` 0x159c94, installed at 0x15da54;
the loader calls it in file order at 0x14e808–0x14ea98. The test runs the
factory and its string/property helpers for real, with only allocation and
constructors stubbed. `PushTrigger` additionally reads `g_world` 0x44fdc8 +
0x70 before its ctor; the difftest supplies a synthetic world pointer.

**Observed in current client source:** `script_commands_objects.cpp`'s `kPorted`
contains only `SmallSpider`, `Gnaw`, `Mosquito`, `Scorpion`, `Badger`; every one
of these 16 uses another constructor, so `Class::None` becomes a stub. That is
the immediate explanation of 0 built, without a factory build refusal. The hub
contains no hostile creature, so building those 16 alone cannot make step 4
pass. The playthrough must reach an enemy-bearing level. `valor` is an observed
hub-to-fight route in this research repository and has `WarBoar` placements;
the first mission menu's story row instead names `blood1` (mission table
0x4fe540). Which destination the client should select is a product decision,
not a value to infer from the hub fixture.

## 2. The original construction and actor handoff

**Observed** in `world_loadRecords` 0x14e808: every level record carries class
name, position, angle and `key=value` properties. The matching factory branch
allocates the class's pool size (0x14fdb8) and calls that class ctor. The object
is then stored at +0x34 under its type name; a saved record may call virtual
slot 8. `GameObject_ctor` 0x14cb10 registers its name, grid link and own random
seed. There is no separate original "copy to combat World" step: the creature
*is* the GameObject in the simulation's grid/run lists.

For a hostile class, its ctor calls `Creature_ctor` 0x109d68, sets a class
definition (model/resource entries) and fields, links a run list via
`obj_runEvery60` 0x14f2b8 or `obj_runEveryFrame` 0x14f248, configures animation
events, and calls `Creature_init` 0x10a230 where appropriate. The class owns
virtual slot 4 (`run`), 27 (state) and usually 5 (`draw`). `runObjects`
0x14b910 invokes slot 4 from the active, 15-frame and 60-frame lists (unless
hidden/frozen). `Creature_updateActive` 0x10c0f0 and `obj_updateActive`
0x14db08 move between active and slow lists. A real combat World therefore
needs the same object identity, list membership, grid position, class virtual
dispatch, and player objects; a one-time copied enemy sprite is insufficient.

**Observed:** `Creature_pickTarget` 0x10ded0 queries the grid through
`world_collectObjectsInBox` 0x14a928, applies enemy slot 20 at 0x119328 and
stores a handle at +0x234. `Creature_hitTargetInArc` 0x119938 uses that target
and calls `damage_apply` 0x1e8230. The player's attack follows `Player_run`
state 1, `Player_meleeHit` 0x1b6a98 and `Player_recalcDamage` 0x1b7158;
the box query sees only grid A and skips prediction copies. There is no
independent global "player attack target list" to fill: the live grid, handles
and class flags define its candidates.

## 3. Stats, death, drops and gold are production code

**Observed:** `balance_load` 0x223998 loads `monsters.bal`; `balance_lookup`
0x223a4c hashes the *record type name* and returns five factors (HP, armour,
damage, attack, experience). `Creature_ctor` calls `Creature_setStats` 0x10a620
for a non-null type name. It combines the factors with `g_levelMonsterLevel`
0x4f714c (set by `game_loadLevel` 0x1e5b70), difficulty, player count and boss
rank, drawing once from the object's own seed when rolling HP. It writes HP
+0x228, maximum +0x22c, damage +0xd0/+0xd2, attack +0xd4, experience
+0xd8 and armour +0xe4. A missing balance row gives five 1.0 factors; no
level property supplies these statistics. Relevant property keys read by
`Creature_ctor` include `wait`, `hide`, `ShowName`, `Dead`, `HomeRange`,
`pointblankrange`, `visualrange`, `visualarc`, `Scale`, `MiniBoss`,
`IgnoreDamage` and light keys; `Creature_init` reads `change%d`, elemental
weapon keys and `initScript`. Class ctors also set body kind, resistances,
speed, radius and animation event times. The detailed arithmetic is already
executed against a reference model in `difftest_combat.py`; do not replace it
with the Full fixture's authored HP/weapon values.

**Observed:** player melee reaches `damage_apply` 0x1e8230, then creature
virtual slot 2 / `Creature_takeDamage` 0x116638 subtracts HP immediately,
accumulates pending damage at +0xc8, records flags +0x2dc and attacker +0x2e4.
The class's slot 4 calls `Creature_processDamage` 0x110d30 on a later tick;
at HP <= 0 it sets state 0x14 through slot 27 and applies experience. This
base function does *not* call `Creature_dropLoot`: class set-state/death code
does so (0x10f2c8), then slot 28 / `Creature_onDeath` 0x10beb8 runs a death
script and any `dropitem` property. `loot_generateDrops` 0x100d54 and
`loot_spawnGold` 0x100974 use balance/quality tables, terrain placement,
shared seed and pool allocation; items and gold become world objects. Gold's
touch handler 0x157a9c requires a real player, a completed spawn countdown and
nonzero amount; HUD gold-floater processing 0x1dc268 / 0x1dcb80 eventually
credits the player record +0xe4. A generated drop and a credited gold balance
are separate checks.

## 4. Ranked port work for `play-enemies`

1. **Choose and enter a real enemy-bearing level.** Keep `hub` as the start
   and prove the story/portal level transition. For a bounded fight, `valor`
   has `WarBoar`/`WarBoarSmall` records and documented live fight routes;
   the first mission menu points at `blood1`. Record the selected level and
   its actual object classes before selecting a combat class to port.
2. **Unify level objects and combat actors.** Feed factory-built creature
   identity, position, grid/run-list membership, properties, seed and class
   dispatch into the runtime used by input and AI. Preserve record order and
   refuse unsupported constructors rather than inserting fixture actors.
3. **Port that level's class constructor and tick/state chain.** For `valor`,
   the first targeted class is `WarBoar` (factory prefix, 0x2ba03c, size
   0x3d8; slot 4 0x2ba3a0, slot 27 0x2bac60). Wire its resource definition,
   animation events/root motion and terrain answers, plus the base Creature
   activity/target/hit helpers. Port other classes only as the chosen route
   needs them.
4. **Supply production stats and player attack state.** Load the actual
   `monsters.bal` factors and level scale, execute the original stat formula,
   retain HP/attack/armour/experience fields, and use the player's real
   equipment, action timing and `Player_meleeHit` path. In the current host
   `kNotCopied` explicitly removes HP, maximum HP, damage, attack, experience
   and armour, so a built object alone still cannot fight.
5. **Complete death, loot and pickup services.** Keep the actual class death
   transition, `Creature_processDamage`, class loot call, terrain/pool/seed
   answers, spawned item and Gold objects, touch and delayed gold credit in
   the same session. Then rerun strict step 4 for damage, death, drop and gold.

**Unknown / not established here:** a production transfer contract between
Open Champions' separate script host and `combat::World`; exact `WarBoar`
animation/resource service answers in that client; whether its current level
selection implements the first mission path. Existing Full combat fixture
success is evidence only for its isolated authored actors and services.

## Verification

`difftest_campaign_combat.py` compares 24 private hub records plus five
synthetic hostile class strings with the original factory on seeds 20973 and
7. It checks return pointer, pool size and constructor address; it does not
execute ctors. Existing `difftest_objects.py`, `difftest_creature.py` and
`difftest_combat.py` own the list, AI/damage and statistics reference models;
their seed reruns are reported in the commit and coordination line.

## Research round 2: `valor` WarBoar boundary (2026-10-22)

**Executed** by `tools/difftest_campaign_combat_r2.py` on US v2.00 in
`tools/ee_emu.py`, seeds 20973 and 7. The private `VALOR.GOB` has 201 records,
including 34 `WarBoar` and 44 `WarBoarSmall`; all 78 take the factory's
0x3d8-byte, 0x2ba03c constructor branch. The factory receives the class string,
but the ctor receives `(block, position, angle, properties, type name)`; this
argument order matters to a port. The class's own writes and service calls were
compared for every boar record. The test stubs `Creature_ctor`, so it does not
claim full placement, grid membership or initialized stats.

**Observed** at `WarBoar_ctor` 0x2ba03c: both names use vtable 0x517cf0 and
definition 0x502f80. After the base ctor, the class writes radius +0x1c = 30,
half-width +0x28 = 40, speed +0xb8 = 0, turn +0xb0 = 1, kind +0xb4 = 3,
flags +0xa8 |= 0x200040000, forward offset +0xe0 = -15, scale +0xdc =
0.75, and small marker +0x3d0 = 0. `WarBoarSmall` changes the forward offset
to -10, scale to 0.6 and marker to 1, while radius remains 30. The ctor
calls `Creature_ctor` 0x109d68, prefix test 0x159c20, model hide-mask
0x179550, animation clear/push 0x1707b0/0x170838, `obj_runEvery60`
0x14f2b8, seven entry-parameter calls 0x118378 (entries 4, 5, 6, 7, 10,
11, 12), then `Creature_init` 0x10a230. The test checks this order and the
class-written fields. **Unknown:** the resolved clip/model pointers and
hide-mask answer from real resource loading; those services were stubbed.

**Executed:** the active `WarBoar_run` 0x2ba3a0 on a constructed object with
scripted base activity and animation answers. A no-target state 0 calls
`Creature_processDamage` 0x110d30, `Creature_run` 0x112948,
`Creature_updateActive` 0x10c0f0, animation step 0x1162b0,
knockback 0x115eb8 and target pick 0x10ded0, then sight/home checks.
State 3 hands a transition to `WarBoar_setState` 0x2bac60. State 6's
hit event calls `Creature_hitAllEnemiesInArc` 0x119b58 with damage flags 8,
and writes the hit-frame marker +0x3c8 = 1. The no-target state 0x14 calls
`Creature_deadUpdate` 0x1108a0. Direct setState execution confirms attack
state 6 clears +0x3c8, stores +0x3cc = 6 and starts a blend; state 0x14
calls `Creature_dropLoot` 0x10f2c8, draws once from the object's own seed
0x1509d0 for a death clip, starts animation and calls `Creature_onDeath`
0x10beb8. **Unknown:** actual target selection, damage dealt, animation event
schedule and a full kill in this level. Those answers were stubbed or absent.

**Observed** in `BALANCE.LMP` and **Executed** at `balance_lookup` 0x223a4c:
the first rows matching name hashes 0xfe90 (`WarBoar`) and 0x270c
(`WarBoarSmall`) are found. The difftest extracts their five signed percentages
at run time and checks the original's single-precision multiplication by
0.01 against `ref_campaign_combat_r2.py`; no balance file data is committed.
The `valor` level table row is at 0x4f7b70. Its level byte +4 is 20, so
`game_loadLevel` 0x1e5b70 gives monster level 22 at difficulty 1; at
difficulties 2–5 it applies the formula in `docs/spec/combat.md` 4.1.
`Creature_setStats` 0x10a620 then uses these factors, player count,
difficulty and the object's own HP roll as documented there. This round did
not run the combined balance, level load and constructor chain in one
emulator world.

**Executed:** `Gold_onTouch` 0x157a9c with a synthetic player and Gold object.
`Gold_run` 0x157b58 decrements nonzero countdown +0x4c on each tested tick
(41, 2 and 1) and calls animation service 0x1709d8.
Prediction-copy flag 0x20000, nonzero countdown +0x4c, non-player flag word
or zero amount +0x80 each prevent pickup. With player flag 0x40, countdown
zero and a synthetic nonzero amount, it calls resource/sound services,
`hud_addGoldFloater` 0x1dc268 and `obj_delete` 0x14f200, and clears +0x80.
**Unknown in this round:** whether a `valor` kill generates Gold on a given
shared seed, its terrain landing, the floater's delayed credit in a running
session, and the final balance.

### Concrete native port order

1. In `script_commands_objects.cpp`, register `WarBoar` and
   `WarBoarSmall` against ctor 0x2ba03c and preserve record type name,
   position, angle, properties, seed and class size. Port the common class
   ctor in the native monster model, plus `Creature_ctor`/`Creature_init`
   effects it needs. Load definition 0x502f80's model and clips through the
   actual resource service; retain its seven animation events and root motion.
   Do not mark the object built while `kNotCopied` still excludes HP,
   damage, attack, experience, armour or resource-dependent fields.
2. Make each host-created object the one simulation actor. The host already
   allocates in file order into `objects::World`, while
   `combat_creature::Adapter` owns a separate `combat::World` and explicitly
   says it is not a shared object allocator. Use the factory object address
   and generation as the combat binding, with one canonical position,
   flags, grid A/B links, active/15/60 run-list node, target handles,
   seed and vtable dispatch. Route `runObjects` 0x14b910 and
   `world_collectObjectsInBox` 0x14a928 through that same identity; bind
   actual player objects before AI or melee queries. Specify how saves
   restore those links and how deletion invalidates handles. No production
   transfer/unification API has been verified yet.
3. Load `BALANCE.LMP`'s `monsters.bal` and the level table row. Execute
   `balance_lookup`, `Creature_setStats`, `Creature_init` and the player
   equipment/grant, `Player_recalcDamage` 0x1b7158 and state-1 melee
   sequence. `Player_run` 0x1a9678 targets from grid A at swing start and
   invokes `Player_meleeHit` 0x1b6a98 on the hit frame; connect this to
   `damage_apply` 0x1e8230, `Creature_takeDamage` 0x116638 and later
   `Creature_processDamage` 0x110d30. The present fixture player weapon
   values cannot stand in for the session equipment.
4. Port `WarBoar_run` 0x2ba3a0 and `WarBoar_setState` 0x2bac60 with
   target/activity, animation event, root-motion/terrain and arc-hit
   services. Keep the class's all-enemies arc hit and state-0x14 loot call.
   Then connect `loot_generateDrops` 0x100d54, `loot_spawnGold` 0x100974,
   terrain placement, pool allocation, Gold ctor/run/touch and HUD floater
   credit. Verify damage, death, a spawned drop, touch and increased player
   record gold separately in one loaded `valor` session.

**Unknown:** the exact resource service outputs, actual terrain query values
for this level, the player's initial equipped weapon on this route, an
integrated hostile tick/target path, loot outcome for a particular seed, and
the native world's transfer API. The reference difftest isolates the class
edges; it is not proof of a playable fight.
