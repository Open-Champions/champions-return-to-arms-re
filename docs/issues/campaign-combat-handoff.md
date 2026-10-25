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
compared for both class names across all 78 record angles, using zero positions
and empty properties. The test stubs `Creature_ctor`, so it does not
claim full placement, grid membership or initialized stats.

**Observed** at `WarBoar_ctor` 0x2ba03c: both names use vtable 0x517cf0 and
definition 0x502f80. After the base ctor, the class writes radius +0x1c = 30,
half-width +0x28 = 40, speed +0xb8 = 0, turn +0xb0 = 1, kind +0xb4 = 3,
flags +0xa8 |= 0x200040000, +0x5c = -0.2, forward offset +0xe0 = -15,
scale +0xdc = 0.75, and small marker +0x3d0 = 0. It clears state +0x232,
+0xec, +0xe8 and +0x220. `WarBoarSmall` changes the forward offset
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
state 6 clears +0x3c8, stores +0x3cc = 6 and calls `Creature_filterState`
0x10a9c0 before starting a blend; state 0x14
calls `Creature_dropLoot` 0x10f2c8, draws once from the object's own seed
0x1509d0 for a death clip, starts animation and calls `Creature_onDeath`
0x10beb8. **Unknown:** actual target selection, damage dealt, animation event
schedule and a full kill in this level. Those answers were stubbed or absent.
The state-6 no-hit transition in the ten tick cases follows the stubbed
animation-end answer, not an observed combat animation finishing.

**Observed** in `BALANCE.LMP` and **Executed** at `balance_lookup` 0x223a4c:
the single row matching each name's computed hash (`WarBoar`,
`WarBoarSmall`) is found. The difftest prints the hashes and extracts the five signed percentages
at run time and checks the original's single-precision multiplication by
0.01 against `ref_campaign_combat_r2.py`; no balance file data is committed.
The difftest reads the `valor` level table row at 0x4f7b70 from the ELF,
asserts its level byte +4 is 20 and its name differs from both fixed-scale
names at 0x52fb70/0x52fb80. The existing `ref_combat.level_scale` model,
previously compared bit for bit with the original `game_loadLevel` 0x1e5b70
stretch, gives monster level 22 at difficulty 1. This round checks the model
only, including difficulty 1; it does not execute the level-load stretch for
any difficulty. Difficulties 2–5 follow `docs/spec/combat.md` 4.1.
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

## Research round 3: bounded `valor` service and shared-world probes (2026-10-22)

**Executed** by `tools/difftest_campaign_combat_r3.py` in `tools/ee_emu.py`
with seeds 20973 and 7, the pinned US v2.00 executable, private `VALOR.GOB`,
its `valor.world`, and `WARBOAR.LMP`. The two seeds select probe order and
start the independent loot and synthetic combat cases. All references to
assets below are identifiers or counts; no asset bytes are tracked.

| Boundary | Observed or executed result | Portable now | Still Unknown |
|---|---|---|---|
| Model and animation resources | **Observed**: class definition 0x502f80 names `warboar.lmp` and 20 entries (model, two textures, 17 clips), all present in that private archive. **Executed**: `GameObject_ctor` 0x14cb10 calls `res_find` 0x17365c in those 20-slot order at generation 1, makes no second lookup in that generation, and resolves all 20 again when `g_lumpGeneration` 0x41bf78 becomes 2. The test supplies synthetic nonzero handles. | Definition names, slot order, generation invalidation, archive presence and animation entry IDs. | The resource manager's loaded pointer values, decoded model/clip content, hide-mask result 0x179550, clip events and root motion in the native renderer. Presence in an archive is not a loaded resource answer. |
| `valor` ground | **Executed**: the original `world_fixup` 0x181d30 loads the private `valor.world`; `terrain_height` 0x183820 agrees bit for bit with `ref_world.terrain_height` at all 78 boar record positions for radii 12 and 30 (156 queries). | Load and query this level's actual height field through the existing world-query contract. Use the queried value and requested radius, not the record z as ground. | Boar movement's full terrain service sequence, water/root-motion interaction, and gold scatter landing in a running level. |
| Starting player gear and melee state | **Executed**: `player_giveStartingItems` 0x1acc78, with parser/inventory/equip stubs, selects different grant routes by class byte at player record +0x50. The model index +0x54 remains zero and debug switches 0x41b550–0x41b554 are zero-initialized; class-only descriptors and call counts in `ref_campaign_combat_r3.py` include impossible class/model pairs and are not portable starting-gear evidence. **Observed earlier**: `Player_run` state 1 (0x1a5030) queries grid A at swing start and calls `Player_meleeHit` 0x1b6a98 at its hit frame; `Player_recalcDamage` 0x1b7158 reads the active weapon set at record +0x4434/+0x4a7c. | State-1 target/hit timing already modelled in `ref_player.py`. | Portable grants by valid model/class and debug state; which class and saved or newly granted item is actually equipped on the client's route; parser, inventory and equip results; actual weapon damage/attack rating and swing animation in that session. The round-3 call counts are not equipped-record evidence. |
| One-grid targeting and damage | **Executed** on two synthetic base GameObjects at a boar record's location, given the original Player and WarBoar vtables: the original grid query 0x14a928 returns both. The player's team byte at record +0x4c24 is 1; the boar's team remains zero-initialized in this probe. `Creature_pickTarget` 0x10ded0, its enemy slot 20 at 0x119328 and handle service 0x1a1738 link the player at boar +0x234 (node +0xc). The original normal `Player_meleeHit` with a clear-ray stub calls `damage_apply` 0x1e8230 then boar slot 2 / `Creature_takeDamage` 0x116638; with a fixed synthetic 15–15 unarmed range and attack rating 200, HP +0x228 goes 100→55, pending +0xc8 becomes 45, damage flags +0x2dc gain bit 1, and attacker handle +0x2e4 links the player. A prediction-copy player (flag 0x20000) makes no second hit. | The same address, grid and target-handle contract can drive both AI and player melee; the original entry points and damage order are pinned. | A level-loaded boar with initialized stats and resources, actual player gear, line-of-sight terrain answer, hit-frame animation, counterattack, full kill and client fight. The 45 damage is a synthetic-input result, not `valor` balance. |
| Loot and gold | **Observed/Executed**: `WarBoar_setState` 0x2bac60 passes zero gold chance to `Creature_dropLoot` 0x10f2c8. On a synthetic boar with the base property service stubbed and the original boss-rank function executed, the original dispatcher calls `loot_generateDrops` 0x100d54 once and forwards that zero. In a bounded one-player/class-0, difficulty-1, level-22 generator call with its other boar arguments, seed 20973 produces one consumable after ten shared draws; seed 7 produces no item after seven. The original and `ref_items.loot_generate_drops` agree on kind, defined item fields and ending seed. Neither produces Gold, and none of the 78 boar placement properties says `dropitem`. **Executed separately**: a synthetic 42-gold floater added at frame 100 by `hud_addGoldFloater` 0x1dc268 begins credit at frame 143; `hud_tickGold` 0x1dcb80 pays the full 42 into player record +0xe4 by frame 160, matching `ref_campaign_combat_r3.gold_credit` every frame. | Boar drop parameters, seeded roll order, zero-gold outcome from this call, and the delayed floater credit rule. | Actual shared seed at a campaign kill, whether another source on the route spawns Gold, a real Gold pickup and its terrain landing. The boar drop cannot satisfy a test requiring a Gold object from this call alone. |
| Shared world | **Executed**: one original `GameObject_ctor`/pool/grid world holds synthetic Player and WarBoar objects. `world_collectObjectsInBox` sees both and `runObjects` 0x14b910 invokes their slot-4 bodies from the same every-frame list, player then boar after front insertion; the virtual bodies are recording stubs. **Observed** at 0x14b910: active, 15 and 60 lists dispatch slot 4 before the script run task (priority 125, `docs/spec/object-system.md` 6.2). In the read-only `play-enemies` client checkout, `Session::bind_hp` exists for a World-owned address and serial, but the level factory's `kPorted` still omits WarBoar, `kNotCopied` still excludes HP/stat fields, and `combat_creature::Adapter` still owns its own `combat::World`. | Preserve one factory object identity and original grid/run-list order, use address plus live generation for binding, route target handles and damage through that identity, and snapshot/deletion through the same owner. The existing `bind_hp` is a possible integration seam. | A production script-host-to-combat binding and dispatch path for level-created boars and players, resource-backed animation, save/restore of the combined state, and a strict client fight. A two-object ee_emu case does not establish that implementation. |

### Updated native port order

1. Select and load an enemy-bearing route, recording whether the client enters
   `valor` or the first mission's `blood1`; do not infer a story choice from this
   bounded `valor` case.
2. Add the WarBoar family to the factory using its 0x3d8 allocation, original
   ctor argument order, class definition and 20 resource slots. Resolve the
   actual archive through the resource manager, use `valor.world` queries for
   ground and animation/root-motion services, and refuse construction when
   those required answers are absent.
3. Bind each factory-created creature and actual player to the one
   `objects::World` identity by address and live serial. Reuse or extend
   `Session::bind_hp` so combat reads and writes that same position, flags,
   grid, run list, handles and seed. Remove the `kNotCopied` stat gap only
   when production `Creature_ctor`/`Creature_setStats` and resource results
   supply those fields. Verify deletion and restore before declaring a bound
   actor live.
4. Run the class-dependent starting grants through parser, inventory and
   equip, then the real active weapon's `Player_recalcDamage`, state-1 target
   acquisition and hit-frame call. Run WarBoar AI and its attack/death states
   in the same tick scheduler. The synthetic 15–15 melee case is a path test,
   not a player damage preset.
5. Port the class loot call with its zero gold chance and test the seeded item
   outcome. For Gold credit, choose and verify an actual Gold-producing source
   on the route; run its spawn, terrain placement, countdown, touch and HUD
   credit in one client session. Keep a drop, a touched Gold object and the
   later +0xe4 balance increase as distinct assertions.

**Current status:** these services and call contracts are portable research.
The native real enemy fight, actual starter equipment, runtime resource
answers, full boar/player tick and Gold-producing playthrough remain Unknown.

## Research round 4: grant, clip, binding and Gold boundaries (2026-10-22)

**Executed** by `tools/difftest_campaign_combat_r4.py` in `tools/ee_emu.py`
on seeds 20973 and 7. The private `valor` and boar archives supplied input
only; no game asset bytes or level-record derivatives are tracked.

| Question | Observed / Executed result | Remaining boundary |
|---|---|---|
| Initial equipment | **Observed** at `player_initNewCharacter` 0x1b1d70: model +0x54 derives class +0x50. **Executed**: all 12 valid model/class pairs through `player_giveStartingItems` 0x1acc78 with debug bytes 0x41b550–0x41b554 explicitly zero. Parser 0x1069b8, grant 0x1c1868 and equip 0x1c27c0 call counts and first weapon descriptors agree with `ref_campaign_combat_r4.py`. Model pairs share these default grant routes; the special model paths for 10 and 11 are included. | The parser, inventory and equip services were stubbed, so active weapon set +0x4434/+0x4a7c and damage are still unproven. A `Player1` level record is a start marker, not an equipped character. No character save or level-entry player record was supplied to identify the actual model, debug state, carried items or equipped weapon on this route. Capture those record fields at entry, then run the parser/inventory/equip chain and `Player_recalcDamage` 0x1b7158. |
| Boar resources and animation | **Observed**: class definition 0x502f80 resolves from `warboar.lmp`. **Executed**: all 17 clip entries from that definition pass the original `anm_relocate` 0x1707b8, `anim_push` 0x170838 and three `anim_advance` 0x16d748 steps each; `ref_anim` agrees on event bits, root deltas and yaw. The seven `WarBoar_ctor` 0x2ba03c calls to `creature_setDefEntryParams` 0x118378 populate real clip event slots. On the configured `atak_mid` clip, original advance and the reference agree on hit bit 1 at frame 18 and later bit 2 at frame 42. | This uses archive bytes mapped into the interpreter, not the full `res_find` 0x17365c / on-demand lump manager, model/texture upload or native renderer. Hide-mask 0x179550, animation-driven `WarBoar_run` hit dispatch and a full resource-backed boar tick remain unexecuted. |
| Level actor identity | **Executed**: `world_createObject` 0x14f6c8 passes a synthetic `WarBoar` request to the installed factory and returns exactly the one address it supplied; original `GameObject_ctor` 0x14cb10 had already linked that same pool block. Round 3 separately checked original grid and run-list identity for synthetic player and boar objects. | The factory body here is a recording stub, so this does not establish the native script-host-to-combat binding. A read-only check of the `play-enemies` client on this date finds `Host::build` still refuses WarBoar at `script_commands_objects.cpp` 0x2ba03c, while `Session::bind_hp` requires the live `objects::World` address and serial. That host now conditionally copies stat fields when `stats_ready_`, superseding round 3's unconditional `kNotCopied` statement. It still needs one production actor binding, tick dispatch, handle/deletion and snapshot/restore path. |
| Gold source on `valor` | **Observed**: `VALOR.GOB` contains `Minotaur` records. **Executed**: `Minotaur_setState` 0x28a16c death state 0x14 calls `Creature_dropLoot` 0x10f2c8, which calls `loot_generateDrops` 0x100d54 with nonzero Gold chance (raw float 0x3f199999); this is a Gold-capable source distinct from WarBoar's zero chance. With a fresh synthetic shared seed, one player and modelled level 22, the original generator and `ref_items.loot_generate_drops` agree on the full drop sequence and ending seed: seed 20973 makes one Gold spawn request; seed 7 makes none. | The `loot_spawnGold` 0x100974, terrain, pool and Gold constructor were stubbed. The actual shared seed after loading and fighting, death conditions, Gold object landing/touch and player record +0xe4 increase remain unobserved. A Minotaur must be reachable and killed on the chosen playthrough for this path to satisfy the Gold milestone. |

### Port plan after round 4

1. Observe the level-entry player record and save state to pin model, class,
   debug switches and equipped item. Run the original grant/equip chain with
   real inventory services before importing weapon statistics into the client.
2. Resolve the boar model, textures and clips through the client resource
   manager. Apply the seven measured event-parameter calls to loaded clips,
   then compare hit dispatch, root motion and hide mask in a resource-backed tick.
3. Bind the factory's World-owned address and live serial directly to combat
   state. Feed class stats when their balance/level inputs are ready; dispatch
   the boar and player through one scheduler and verify target handles,
   deletion and restored snapshots against that identity.
4. Keep the WarBoar item-only death path distinct from the Minotaur Gold path.
   For the latter, follow the actual campaign seed through death, Gold spawn,
   terrain landing, touch and delayed record credit in one loaded session.

**Status:** these are bounded original-code contracts and a Gold-capable source.
The requested real `valor` fight and actual route equipment remain Unknown.

## Research round 5: exact loader boundary for play-enemies-r3 (2026-10-22)

**Executed** by `tools/difftest_campaign_combat_r5.py` on SLUS-20973 US v2.00,
seeds 20973 and 7. The original `world_loadRecords` 0x14e808 consumed 7,196
bytes of the private `VALOR.GOB` object stream and handed all 201 records to
the installed factory callback in file order, with bit-identical positions,
angles and matching property strings. This callback returned no object, so
this test does **not** claim a populated grid or successful actor construction.
The original factory 0x159c94 independently selected a 0x3d8 allocation and
`WarBoar_ctor` 0x2ba03c for all 34 `WarBoar` and 44 `WarBoarSmall` records,
and a 0x470 allocation and `Minotaur_ctor` 0x288fdc for all six Minotaurs.
The two supplied seeds are repeatable test controls, not a measured campaign
seed after the hub-to-valor load.

**Observed** in the executable's definitions: 0x502f80 names 20 entries in
`warboar.lmp`; 0x501200 names 26 entries in `minotaur.lmp`. All 46 named
entries exist in the corresponding private archives. Archive presence is not
an `res_find` 0x17365c result. `GameObject_ctor` 0x14cb10 resolves definition
entries only when +4 differs from `g_lumpGeneration` 0x41bf78. **Executed**:
with an `res_find` recording stub, the original base ctor asks for all 46
`(lump, entry)` pairs in definition order at generation 1, makes zero repeat
lookups in the same generation, and asks for all 46 again at generation 2.
The stub returned zero on every lookup. The actual
generation, allocation addresses and decoded model handles of a valor session
were not captured.

**Executed with real record inputs and refused downstream services:** all 84
class constructors received each record's actual position, angle and property
list. The class direct-call sequences agree with `ref_campaign_combat_r5.py`
(1,200 calls). Each constructor passes `(object, typeName, stack copy of
position, angle, classDef, properties)` to `Creature_ctor` 0x109d68. The
test stubs that base function and therefore supplies a synthetic definition
pointer. The entries below state argument values **at the class call sites**;
the zero model/clip pointers and zero returns in the test are stub effects,
not observed valor return values. Unused register contents are not arguments.

| Class call sites | Arguments established on every record | Return boundary |
|---|---|---|
| Boar 0x2ba138 → name test 0x159c20 | type name; literal pointer 0x54d7b0 | Original string helper ran. |
| Boar 0x2ba184 → `model_buildHideMask` 0x179550 | resolved model at definition slot 0; variant 0 | Model pointer and 64-bit mask Unknown. |
| Boar 0x2ba19c / 0x2ba1bc → `anim_clear` 0x1707b0 / `anim_push` 0x170838 | animation state `object+0x114`; push clip from definition, mode 1 | Loaded clip pointer and state Unknown. |
| Boar 0x2ba1cc → `obj_runEvery60` 0x14f2b8 | object | Actual list link requires the base object and shared world. |
| Boar 0x2ba1f8–0x2ba308 → `creature_setDefEntryParams` 0x118378 | indexes 4, 5, 6, 7, 10, 11, 12; all four integer masks and raw float times are asserted in `ref_campaign_combat_r5.py` | Round 4 executed the seven boar event writes on relocated clips; loaded-resource addresses Unknown. |
| Boar 0x2ba310 → `Creature_init` 0x10a230 | object | Terrain, scripts, animation and final placement path unexecuted here. |
| Minotaur 0x28914c → string helper 0x3b81a0 | type name; literal pointer 0x548f38 | Original string helper ran. |
| Minotaur 0x2891d0 / 0x2891f8 → WeaponShield hand setup 0x11bc18 | holder `object+0x3c8`, then `(1,0x15,0x20)` and `(2,0x19,0x20)` | Held-part writes Unknown. The holder is shared combat state. |
| Minotaur 0x289200 / 0x289224 → own draw 0x1509d0 / hide mask 0x179550 | object; then resolved model slot 0 and a variant derived from the own draw (1 under the test stub) | Real draw, variant and mask result Unknown. |
| Minotaur 0x28923c / 0x289254 / 0x28925c → `anim_clear` 0x1707b0 / `Minotaur_setState` 0x28a16c / `obj_runEvery60` 0x14f2b8 | `object+0x114`; then `(object,0)`; then object | All three bodies were stubbed in this test. |
| Minotaur 0x289288–0x2893cc → `creature_setDefEntryParams` 0x118378 | indexes 5, 6, 7, 8, 9, 13, 3, 4; integer masks and raw float times asserted in the reference | Loaded animation and final writes Unknown. |
| Minotaur 0x2893d4 → `Creature_init` 0x10a230 | object | Terrain, scripts and final placement path unexecuted. |

The boar call starts at 0x2ba0a8; the Minotaur base call starts at 0x289038.
Their constructor argument orders differ at the factory boundary: boar takes
`(block, position, angle, properties, typeName)`; Minotaur takes
`(block, typeName, position, angle, properties)`. Both call the base with the
six-argument order above. The Minotaur branch for the `Minotaur` name uses
hand-2 type 0x19; its own random bit chooses the hidden-part variant, so the
stubbed variant is not a real valor answer. **Unknown:** every actual resource/model/animation,
terrain and shared-combat return on a complete valor load. `ee_emu.py` here
does not boot `game_loadLevel` 0x1e55c0, establish the real lump manager,
resident `hud.lmp`, player record, shared world and model state, then execute
the base and derived constructors together. The private archives alone cannot
reconstruct allocation-specific returned pointers or the resulting hide mask.
There is consequently no honest 78+6 table of real service return values yet.

**Production actor binding:** **Observed** at `GameObject_ctor` 0x14cb10:
the constructor inserts the one allocated block into grid A (or the off-grid
list) at its position and gives it the shared-seed-derived object seed.
`WarBoar_ctor` 0x2ba1cc and `Minotaur_ctor` 0x28925c choose the 60-frame run
list by calling 0x14f2b8. `world_loadRecords` then stores the record's class
name at object +0x34 and can invoke save-state slot 8. Both grid and run
lists prepend; within a cell or list, file-order creations appear in reverse
order. `runObjects` 0x14b910 dispatches virtual slot 4 from active, 15- and
60-frame lists; targeting walks the same grid at 0x14a928, with target handles
at creature +0x234 through 0x1a1738. There is no separate post-constructor
combat registration in the original. The native `Host::build` still refuses
boars before `built_` insertion; `Session::bind_hp` requires the live
`objects::World` address and serial. The direct constructor probe does not
establish the native binding, tick, targeting, deletion or restore path.

**Player and item gate:** `Player1_ctor` 0x158928 makes a start *marker*, not
the equipped player. The native marker currently requires the caller's
previous level, entrance, gate-travel and loaded-save inputs; it also refuses
when item-load seed accounting or other constructor draws are unmodelled.
`game_loadLevel` 0x1e5690–0x1e56bc runs `item_loadResources` 0x108434 only
outside `intro` when `hud.lmp` is absent. That loader parses 607 definitions
and makes 223 shared draws; the native host has a 223-draw gate but no
observed `hud.lmp` residency for this strict route. A new character needs
`player_initNewCharacter` 0x1b1d70 (model +0x54 determines class +0x50),
`player_giveStartingItems` 0x1acc78, real descriptor parse 0x1069b8,
`inventory_giveItem` 0x1c1868 and `inventory_equipItem` 0x1c27c0.
Alternatively a saved character needs the real import record at 0x1bdb0c.
Only then can the active weapon at +0x4434 indexed by +0x4a7c and damage
from `Player_recalcDamage` 0x1b7158 be known. Round 4's 12 valid-model
grant routes used parser/inventory/equip stubs; the native report's model 0,
class 0, imported false is a created placeholder, not evidence of a real
equipped axe. **Unknown:** the strict route's creation/import choice, player
record, debug switches, actual item bytes and active weapon.

### Ordered native port list after round 5

1. Supply the actual hub-to-valor level-entry state, `hud.lmp` residency and
   shared seed. Execute the conditional item loader and all prior constructor draws
   in record order; retain counted refusals until those inputs are measured.
2. Resolve the 20 boar and 26 Minotaur definition slots through the real
   resource manager. Complete base `Creature_ctor`, hide-mask, animation,
   terrain, shared-combat and `Creature_init` services and compare their
   actual returned values and writes for all 84 records.
3. Register each constructed block once in `objects::World`; bind its address
   and live serial into `Session` combat, and route grid queries, run-list
   ticks, target handles, damage, deletion and restore through that owner.
4. Create or import the real player record, run parser/inventory/equip,
   read its active item and recalculate damage. Then rerun strict step 4 to
   prove target, damage, death, drop, Gold pickup and balance credit.

**Status: MORE.** The original record path and class call contracts are
measured, but play-enemies-r3's real service returns, native binding and
equipped player remain blocked by the explicit inputs and runtime paths above.

## Research round 6: attempted no-stub full load (2026-10-23)

`tools/difftest_campaign_combat_r6.py` checks the read-only ISO index and
compares the available private local inputs against their disc files. It then
runs two **no-stub** `ee_emu.py` probes on each of seeds 20973 and 7. The
seeds are test controls; neither is a captured campaign seed. No game bytes
or disassembly enter tracked files.

| Probe | Executed result on each seed | Exact boundary |
|---|---|---|
| ELF entry 0x14fa88, the real boot route before a hub session | 1,913,112 instructions, no calls, resource lookups or enemy constructors | `SYSCALL` at 0x14fc48 with v1 = 60 (0x3c). `EE._syscall` in `tools/ee_emu.py` raises because there is no EE kernel. |
| Direct `game_loadLevel` 0x1e55c0 with a `valor` name allocated in EE memory | 2,277 instructions, 64 calls, no `res_find` 0x17365c or hostile constructor call | `SYSCALL` at 0x352e14 with v1 = 124 (0x7c), reached through the SDK debugger-link wrapper 0x352e10. `EE` has no `Deci2Call` service. This call starts from fresh ELF memory, not the hub's real player, level, resource or saved state. |

These are **Executed** boundaries, not a completed `valor` load. The direct
call is only an early entry diagnostic and cannot substitute for the original
campaign transition. `ee_emu.py` intentionally implements a function-level
EE interpreter with no kernel, IOP, hardware, timing or BIOS; it also has no
disc-backed resource-manager environment. Adding a zero-return syscall hook
would repeat round 5's stub problem. The original `main` startup, hub
session, full resource manager, `Creature_ctor` 0x109d68,
`GameObject_ctor` 0x14cb10, terrain, shared combat state, equipped player,
`runObjects` 0x14b910, damage, death, drop and Gold sequence therefore did
not execute together. There is no honest service-return table or real-run
combat reference model for these seeds. Round 6 adds a fail-closed boundary
difftest; rounds 1–5 remain bounded reference models.

### Ordered native port list from observed call sites

1. **Observed** at startup 0x14fc48 and level entry 0x352e14: provide the
   kernel/IOP/disc behavior needed to boot and load without stubbed returns;
   capture the actual hub-to-valor state. The return values are **Unknown**.
2. **Observed** at `game_loadLevel` 0x1e5690–0x1e56bc: resolve actual
   `hud.lmp` residency and conditional `item_loadResources` 0x108434 before
   comparing shared draws. The entry state and seed are **Unknown**.
3. **Observed** at `GameObject_ctor` 0x14cbc4–0x14cc20: resolve the 20
   WarBoar and 26 Minotaur definition entries with `res_find` 0x17365c,
   then execute the base and class constructors at 0x109d68, 0x2ba03c
   and 0x288fdc. Their actual resource and service returns are **Unknown**.
4. **Observed** at `GameObject_ctor` 0x14cc24–0x14cce0 and the class sites
   0x2ba1cc / 0x28925c: preserve one grid object and its 60-frame list
   link. `runObjects` 0x14b910 uses virtual slot 4, grid query 0x14a928
   finds targets, and handle service 0x1a1738 links them. Actual populated
   `valor` registration and AI state are **Unknown**.
5. **Observed** at `player_initNewCharacter` 0x1b1d70 or import 0x1bdb0c,
   descriptor parse 0x1069b8, inventory grant 0x1c1868, equip 0x1c27c0,
   active weapon +0x4434/+0x4a7c and `Player_recalcDamage` 0x1b7158:
   obtain the real player record before attempting melee. The equipped
   item and melee state at this entry are **Unknown**.
6. **Observed** at `Player_meleeHit` 0x1b6a98, `damage_apply` 0x1e8230,
   `Creature_takeDamage` 0x116638, `Creature_dropLoot` 0x10f2c8 and
   `hud_tickGold` 0x1dcb80: run and record the real kill and credit path
   only after steps 1–5. The actual `valor` damage, death, drops and Gold
   credit are **Unknown**.

**Status: BLOCKED for the requested full no-stub `ee_emu.py` playthrough.**
The alternative was the strict boot and direct level-entry diagnostic above,
plus the existing bounded round 1–5 probes. No stub result is promoted to a
`valor` value.

## Research round 7: real emulator capture, incomplete kill (2026-10-23)

**Ran on Play!'s headless PS2 core**, not PCSX2, with the user's SLUS-20973
v2.00 disc image. The copied `tools/rig` runner, its data directory, scripts,
states and raw logs are under the ignored `work/valor-capture/` in this
worktree. No files in the main workspace were changed. No other PCSX2 or
Play-RTA process was running when the runner started; runs were sequential.
`loader-targeted.rig` uses the original character-creation buttons from the
read-only `fight.rig` and then **writes `valor` to the pending-level field** at
hub simulation frame 100. The game's own level loader, resource manager and
constructors run after that request. This is an emulator-observed loader
session, **not a normal campaign gate transition or a PCSX2 result**. The
later `fight-no-pokes.rig` copies that rig's movement/attack input after a
Valor entry state, omitting its player-HP and target-HP writes. These limits
apply to every value below. Run-specific heap addresses are examples of one
session, not portable constants.
Six copied earlier rig states were also probed: three loadable ZIP states
were in `strife`; three `.state` files could not be loaded by this runner.
None supplied a verified normal-route Valor entry.

### Captured loader and player state

The hub appeared at runner frame 2537. The pending-level request led to
`valor` at runner frame 2951. At runner frame 3224 / Valor simulation frame
60, the shared seed `g_randSeed` 0x404464 was `0x661acaed`. The
`difftest_campaign_combat_live.py` check matches each actor address seen at
`GameObject_ctor` 0x14cb10, its derived constructor and its
`obj_runEvery60` 0x14f2b8 call: **78 WarBoar-family actors and six
Minotaurs**, without an actor stub. The first boar at `0x00628dc0` has
vtable `0x00517cf0`, grid-link head `+0x8 = 0x008472a4`, 60-frame
run-list head `+0x4 = 0x00847574`, and HP `+0x228 = 545.687377` in the
entry state. The first Minotaur at `0x0062d8c0` has vtable
`0x005165f0`, grid link `0x00849310`, run-list link `0x008492e8`, and
HP `1173.97656`. The boar constructor addresses span `0x00628dc0` through
`0x006459c0`; Minotaurs span `0x0062d8c0` through `0x0062f1c0`.

**Ran:** `res_find` 0x17365c returned nonzero for all 20 WarBoar slots in
definition `0x502f80` and all 26 Minotaur slots in `0x501200`, each on
the first `GameObject_ctor` resolution at caller return address 0x14cbfc.
The exact return values from this session follow in definition order:

| Definition | Entry | `res_find` return |
|---|---|---|
| WarBoar | `warboar.vif` | `0x019edb00` |
| WarBoar | `warboar.tex` | `0x019dc500` |
| WarBoar | `warboar_b.tex` | `0x019f9d00` |
| WarBoar | `atak_mid.anm` | `0x019cd400` |
| WarBoar | `atak_left_close.anm` | `0x019cc500` |
| WarBoar | `atak_front.anm` | `0x019cab80` |
| WarBoar | `atak_right_close.anm` | `0x019ced00` |
| WarBoar | `backup.anm` | `0x019cfa80` |
| WarBoar | `charge.anm` | `0x019d0a80` |
| WarBoar | `chargetak.anm` | `0x019d1480` |
| WarBoar | `death1.anm` | `0x019d2600` |
| WarBoar | `death2.anm` | `0x019d3b80` |
| WarBoar | `hit2front.anm` | `0x019d5180` |
| WarBoar | `hit2left.anm` | `0x019d5c80` |
| WarBoar | `hit2right.anm` | `0x019d6900` |
| WarBoar | `idle1.anm` | `0x019d7580` |
| WarBoar | `roar.anm` | `0x019d8380` |
| WarBoar | `walk.anm` | `0x019d9d80` |
| WarBoar | `walk_trn_lft.anm` | `0x019daa80` |
| WarBoar | `walk_trn_ryt.anm` | `0x019db800` |
| Minotaur | `minotaur.vif` | `0x01a89e00` |
| Minotaur | `minotaur.tex` | `0x01a5bc00` |
| Minotaur | `atak_180.anm` | `0x01a40680` |
| Minotaur | `atak_back.anm` | `0x01a42080` |
| Minotaur | `atak_f1.anm` | `0x01a43700` |
| Minotaur | `atak_f2.anm` | `0x01a44780` |
| Minotaur | `atak_f3.anm` | `0x01a45d80` |
| Minotaur | `atak_left.anm` | `0x01a47200` |
| Minotaur | `atak_right.anm` | `0x01a48280` |
| Minotaur | `block.anm` | `0x01a50d00` |
| Minotaur | `death.anm` | `0x01a51200` |
| Minotaur | `death2.anm` | `0x01a54880` |
| Minotaur | `gore.anm` | `0x01a57980` |
| Minotaur | `hitreaction.anm` | `0x01a58f80` |
| Minotaur | `idle1.anm` | `0x01a59c80` |
| Minotaur | `idle2.anm` | `0x01a5b100` |
| Minotaur | `run.anm` | `0x01ab8f00` |
| Minotaur | `taunt.anm` | `0x01ac2000` |
| Minotaur | `taunt2.anm` | `0x01ac3780` |
| Minotaur | `walk.anm` | `0x01ac5d80` |
| Minotaur | `axe.vif` | `0x01a4f200` |
| Minotaur | `axe.tex` | `0x01a49600` |
| Minotaur | `shield.vif` | `0x01abd100` |
| Minotaur | `shield.tex` | `0x01ab9e00` |
| Minotaur | `shield2.vif` | `0x01ac1380` |
| Minotaur | `shield2.tex` | `0x01abe800` |

**Ran:** The entry player record at `g_players` 0x4d8af0 has class `6`,
model `11` (the `MODEL_CLASS` relationship in `ref_campaign_combat_r4.py`),
active weapon set `+0x4a7c = 0`, primary item pointer
`+0x4434 = 0x004d8c20`, and item-definition pointer `0x003f87d0`
(`club`). `Player_recalcDamage` 0x1b7158 ran again from
`Player_weaponSwapInput` after the entry state was saved; record fields
`+0xcc/+0xd0/+0xd4` remained **38 / 19 / 24** (s32 attack / minimum /
maximum). Entry HP was `32.7999954`, Gold at `+0xe4` was `500`.

### Captured melee boundary

**Ran:** in the no-HP-write continuation, at runner frames 2384 and 2408,
`Player_meleeHit` 0x1b6a98 called `damage_apply` 0x1e8230, which called
`Creature_takeDamage` 0x116638 on boar `0x0063a0c0`, in that order both
times. The damage call carried attack `38` and range `19–24`; the
`Creature_takeDamage` entry saw `f12 = 0`. The same boar's HP `+0x228`
was `228.319549` before the two attacks and at simulation frame 2470;
pending damage `+0xc8` was zero and damage flags `+0x2dc` were zero.
There was **no `Creature_dropLoot` 0x10f2c8 call**. `hud_tickGold`
0x1dcb80 ran in a three-frame continuation with player Gold still `500`.
The unmodified fight input did not finish by the 8,000-frame bound and
produced no demonstrated kill, drop, pickup or credit. The first capture's
optional `grid=` and `gold=` breakpoint annotations used an extra memory
indirection and read zero; the direct state reads and corrected Gold
breakpoint above supersede those annotations.

The checker compares the live trace with the bounded `ref_campaign_combat_r4`
model/class mapping and `ref_campaign_combat_r5` definition-slot and actor
call contracts. It reports the two ordered melee paths separately and never
turns those calls into a claimed kill. The raw logs, state files and private
disc bytes remain ignored under `work/valor-capture/`.

### Ordered native port list after the capture

1. **Observed call-site contract; runtime value Unknown on a normal route:**
   enter `valor` through a campaign gate or a legitimate saved character and
   capture the requested level, player, shared seed and `hud.lmp` residency at
   `game_loadLevel` 0x1e55c0. This capture used a pending-level write.
2. **Ran in the scripted loader session:** constructor calls nest as class
   constructor 0x2ba03c / 0x288fdc → `Creature_ctor` 0x109d68 →
   `GameObject_ctor` 0x14cb10 → `res_find` 0x17365c for the first
   definition resolution (20 boar or 26 Minotaur slots). Resource calls
   return before `GameObject_ctor`; base initialization then completes before
   the class constructor returns. The trace records the class and base
   entries and their returns, plus `GameObject_ctor`'s return address in
   `Creature_ctor`; it did not break at `Creature_ctor` entry. The table
   pins this session's nonzero returns; a native port must obtain its own
   allocator addresses.
3. **Ran in the same session:** retain the one object identity in the grid
   and 60-frame list through 0x14f2b8. **Observed call-site contract:**
   `runObjects` 0x14b910 dispatches virtual slot 4; this trace did not
   capture a direct dispatch of these actors. The first actors' link values
   above are captured; full AI, terrain and animation behavior remains Unknown.
4. **Ran for the entry player:** keep the actual class/model, `club` item,
   active set and the `Player_recalcDamage` 38 / 19–24 result. The normal
   campaign route's equipped player remains Unknown.
5. **Ran through nonlethal calls only:** keep the `Player_meleeHit` →
   `damage_apply` → `Creature_takeDamage` order. A real kill must still
   establish HP loss, death state, `Creature_dropLoot` 0x10f2c8, item or
   Gold object creation, pickup and `hud_tickGold` credit. Those values and
   a final fully Observed kill port list remain **Unknown**.

## Research round 8: assisted live kill and separate Gold pickup (2026-10-23)

**Ran on the same headless Play! core and SLUS-20973 v2.00 disc**, using the
round-7 scripted-pending-level Valor state, one emulator instance at a time.
Private scripts, state files, watch tables and breakpoint logs are ignored
under `work/valor-capture/`; the disc remained read-only. The entry still
did **not** use a normal campaign gate. Starting from
`states/two-hits.zip`, the controlled fight changed only player HP and
maximum HP, record `g_players+0xac/+0xb0`, from the recorded starting
`32.7999954` to `10000` to survive enough attack cycles. It made **no
enemy-HP, attack-stat, seed or code write**. The damage, death, loot and
pickup functions below ran in the original emulator, but survival was
assisted; this is not an unassisted campaign playthrough or PCSX2 result.

### Why the round-7 boar survived, and the actual hit

**Ran:** the round-7 two melee calls at frames 2384 and 2408 were misses:
`damage_apply` 0x1e8230 returned `0` and reached
`Creature_takeDamage` 0x116638 with `f12=0` and miss flags `0x42000`
from return site 0x1eac6c. The boar at `0x0063a0c0` had active/inert
byte `+0x231=0`, armour `+0xe4=369`, HP/max HP
`+0x228/+0x22c=228.319549`, and unchanged damage flags `+0x2dc=0`
in the saved state. Thus neither an inert timer nor an omitted HP write
explains those two calls. The original damage routine's two hit rolls and
armour scale are documented in `docs/spec/combat.md` section 3; the
`0x1eac6c` return site is its zero-damage miss path.

**Ran:** repeating short Cross press/release cycles with player HP support
gave the first positive boar hit at continuation frame 138:
`Player_meleeHit` 0x1b6a98 → `damage_apply` 0x1e8230 with attack `38`
and equipped club range `19–24` → `Creature_takeDamage` 0x116638,
`f12=3.913278`, flags `0x40001`, return site 0x1ea7e8. The HP watch
fell `228.319549 → 224.406265` on frame 139. A second equal hit at
frame 186 fell HP to `220.492980` on frame 187. These are the first
observed positive damages to a resource-loaded Valor boar in this work;
the boar HP field is confirmed at `+0x228`. The moving continuation then
left melee range. Stationary 24-frame attack cycles from the same saved
state continued it to HP `55.7231254`, with Gold still `500`; the state
was saved as `round8-stationary.zip`.

### Death and loot order

**Ran:** from that state, the same stationary input took the same boar from
HP `55.7231254` to `3.20279169`, then at continuation frame 1194 a
positive `Creature_takeDamage` of `4.325202` reduced `+0x228` to
`-1.12241125` on the next watch row. `damage_apply` returned `1`.
At frame 1195, `WarBoar_setState` 0x2bac60 called
`Creature_dropLoot` 0x10f2c8 for actor `0x0063a0c0`, which called
`loot_generateDrops` 0x100d54. The generator ran once with `f12=36`,
`f13=2`, `f14=2.799999`, `f15=0`; no `loot_spawnGold` 0x100974 call
occurred. A focused replay broke on `PhProp_ctor` 0x155a0c: its 36
calls began much later, at frame 1723, all from `AutoContainer_run`,
so this capture shows no boar-generated item object. The boar's zero-Gold
death parameter documented in round 3 remains consistent with this run.

**Ran, direct actor dispatch:** `runObjects` 0x14b910 was entered each
continuation frame. `WarBoar_run` 0x2ba3a0 for this actor entered with
return address `0x14bb80` (`runObjects+0x270`), including frame 0.
This captures the actor dispatch that round 7 had only established as a
call-site contract.

### Gold object, touch and HUD credit: separate source

**Ran:** after the boar's death, `AutoContainer_run` created Gold objects
through `Gold_ctor2` 0x157668 at frames 1723 and 1795, both using the
reused object address `0x00601ec0`, with amounts `9` and `27`.
`Gold_onTouch` 0x157a9c ran repeatedly on player `0x006c88c0` while
the objects' countdowns remained positive. At frames 1764 and 1836,
`Gold_onTouch` called `hud_addGoldFloater` 0x1dc268 with the same
amounts. The focused replay captured `hud_tickGold` 0x1dcb80 with Gold
`500` at frame 1801, `502` by frame 1808, `509` by frame 1815,
`513` at frame 1880, and `536` by frame 1894; the watched player record
`g_players+0xe4` ended at `536` (`500+9+27`). **These Gold objects came
from AutoContainer, not the WarBoar death generator.** The source
container's world record and the normal-route seed remain unverified.

`tools/difftest_campaign_combat_live.py` now checks the first two positive
hits, direct `runObjects` → WarBoar dispatch, positive last hit, HP crossing zero,
next-frame death and loot call, the separate Gold constructor/touch/floater
orders, and the HUD replay's credited balance. It keeps the round-7
constructor, entry and nonlethal trace checks. The private evidence used
for this round is `round8-supported-breaks.log` /
`round8-supported-watch.tsv`, `round8-stationary-breaks.log` /
`round8-stationary-watch.tsv`, `round8-kill-breaks.log` /
`round8-kill-watch.tsv`, and `round8-credit-breaks.log`; the matching
scripts and states are in the same ignored directory. No existing rig
memory card or loadable saved state established a normal hub-to-Valor
campaign gate, so round-7 loader values are still **not confirmed for
normal-route entry**.

### Ordered native port list after the live kill

1. **Normal entry still Unknown:** obtain the hub gate or a legitimate
   saved-character transition to Valor. Capture requested level, seed,
   player and HUD/resource state at `game_loadLevel` 0x1e55c0 before
   treating this scripted-entry session as normal-route parity.
2. **Ran, constructor order:** class constructor 0x2ba03c / 0x288fdc
   enters `Creature_ctor` 0x109d68, then `GameObject_ctor` 0x14cb10;
   first definition resolution calls `res_find` 0x17365c inside the base
   constructor. Its calls return before base and class initialization
   completes. Resolve the 20/26 slots, retaining each object identity.
3. **Ran, world scheduling:** retain grid and 60-frame registration at
   0x14f2b8, then dispatch that same identity from `runObjects` 0x14b910
   to `WarBoar_run` 0x2ba3a0 at 0x14bb80. Keep the real animation,
   terrain and target services; this trace establishes dispatch, not
   native implementation readiness.
4. **Ran, equipped player and damage:** retain the class-6/model-11
   player, active club, attack 38 and 19–24 damage range. Preserve
   `Player_meleeHit` 0x1b6a98 → `damage_apply` 0x1e8230 miss/armour
   rolls → `Creature_takeDamage` 0x116638, including positive HP writes
   at `+0x228` and zero-damage misses. This live kill required player
   health support; normal survival remains unverified.
5. **Ran, death and rewards:** process the next-frame WarBoar death via
   `WarBoar_setState` 0x2bac60, `Creature_dropLoot` 0x10f2c8 and
   `loot_generateDrops` 0x100d54. Keep its zero-Gold path distinct from
   `AutoContainer_run`'s observed Gold spawn at 0x157668, countdown,
   `Gold_onTouch` 0x157a9c, `hud_addGoldFloater` 0x1dc268 and delayed
   `hud_tickGold` 0x1dcb80 credit. A Gold-producing enemy death and an
   unassisted normal-route fight remain **Unknown**.
