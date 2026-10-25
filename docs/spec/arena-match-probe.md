# Offline arena match probe, recipe 0

**Round 6 (2026-10-21):** `--real-creatures` replaces the constructor fixtures described
below with the original chain, executes `world_findFreeSpot` and the kill/loot path, and
corrects round 5's placement claim. See the section "Real creature chain" at the end;
the earlier sections describe the fixture modes, which are unchanged.

**Round 7 audit correction (2026-10-22):** The remaining `pool_new` fallback is
restricted to site `0x117e30`, size `0x248`: `creature_dropHeldPartAsProp` (`0x117d30`)
constructs a dropped `PhProp` there (`docs/spec/weapon-holder.md` §3.3). Both seeds
produce six such blocks in fighting and none in the three builders or idle run; the
probe asserts those counts. These blocks are allocated but not ticked by this driver.

US `SLUS_209.73` v2.00, 2026-10-21. **Executed** in `tools/ee_emu.py` by
`tools/probe_arena_match.py` on the owner's disc executable, copied into this
worktree's ignored `local/` folder. Seeds 20973 and 7 produced the same wave
counts. This is a constructed offline one-player state, not a live match.

The 30-entry arena class-name table at `0x5037f0` identifies the first three
recipe-0 classes as Goblin (index 3), Mummy (index 1), and Scorpion (index 0).
`arena_startWave` `0x305ed4`, `arena_setRingStep` `0x3065b0`,
`arena_spawnMonster` `0x3065fc`, `world_createObject` `0x14f6c8`,
`world_objectFactory` `0x159c94`, and `Creature_scaleStats` `0x1185d8`
execute their original bodies. The original factory selects the pool size
and constructor; the probe asserts both for each requested index. The
**authored constructor fixture** returns a creature-shaped block with its
original class vtable and authored stats. Their scaled values are not asserted by this probe.
The fighting scenario runs bounded class AI ticks on those fixtures.
Virtual slots 27 and 34 are recording stubs during construction; the world
free-spot service supplies the requested point. The factory
mapping was separately compared for all 30 names in
`tools/difftest_monster_build.py`. The constructor fixture is distinct from
the neutral constructor difftests in `docs/spec/arena-goblin.md` and
`docs/spec/arena-mummy.md`.

Each spawn now allocates its 0x18-byte SpellArena record. The probe checks
the owner, vtable, and shared-seed draw against the documented spawn contract.
Without `--real-player`, the 0x590-byte player replacement at `arena_startWave` returns null,
class constructors are fixtures, and slots 27 and 34 are stubbed during
construction; the resulting seed stream is therefore
verified for this constructed probe, not for a complete real match.

| Wave | Constructor fixtures | Original factory calls | Original spawn calls | Original scale calls | Indices |
|---:|---:|---:|---:|---:|---|
| 0 | 2 | 2 | 2 | 2 | 3, 3 |
| 1 | 3 | 3 | 3 | 3 | 3, 3, 1 |
| 2 | 4 | 4 | 4 | 4 | 3, 3, 1, 0 |

The first call of wave 0 reaches `world_createObject` for index 3. With the
constructor fixture installed, all nine requests across waves 0–2 pass
through the original factory, return an object, and scale it. The counts
agree with the independently modelled wave plans in
`tools/difftest_arena_modes.py`.

`run_match` also executes `arena_runTask` `0x306b78`, `arena_nextWave`
`0x305e9c`, preparation `0x3063fc`, and each subsequent wave builder in one
emulator state. The authored world walk reports living fixture objects. Idle
fixtures remain in wave 0 for 2,400 task frames. In the attacked scenario the
driver injects a lethal hit from the player pointer after each intro. The
original `Creature_takeDamage` `0x116638`, `Creature_processDamage` `0x110d30`,
state filter `0x10a9c0`, and the Goblin/Mummy/Scorpion death set-state bodies
execute. All nine objects reach state `0x14`; the world walk checks their
death flag. The original task sees the empty wave and advances: wave 0 has
2 objects, wave 1 has 3 more, and wave 2 has 4 more. The driver stops after
1,687 frames when it kills wave 2's objects. It does **not** execute player input, an attack animation,
collision, class AI, or the full constructors. It demonstrates arena flow and
damage-to-death on authored objects; it cannot establish a live match or
real-world timing.

The fighting fixture gives each constructed creature a target handle to the
player and two class AI ticks after each intro. A fixed close-range sight answer
starts an attack; the driver moves the player fixture to each creature for the
melee event. The original `Creature_hitTargetAtReach`, `damage_apply`,
`Player_takeDamage`, and `Player_processDamage` bodies run. The player then deals
authored lethal damage to clear the wave. On both seeds the three waves finish
in 1,688 task frames: 9 enemy hits are accepted and the player's authored
10,000 HP became 9,910 in the executed probe for seeds 20973 and 7. The probe
now bounds cumulative loss by nine documented 10–20 damage rolls; exact HP is
a result for those seeds, not a general assertion. This exercises class attacks
and player damage processing with scripted sight, positions and animation events. It does not
establish world collision, player input, full creature constructors, or a live
match.

## Real Player replacement and tick (`--real-player`, 2026-10-21)

With `--real-player` the probe no longer refuses the `0x590` allocation. Recipe 0 is the
first recipe record, the only one waves 0–2 use. In waves 0–2 the following execute in
one emulator state:

- the slot loop of `arena_startWave`;
- the old player's slot-1 destructor;
- `pool_free` → `pool_new` reuse of the same block (zero-filled);
- `Player_ctor` → `Creature_ctor` → `GameObject_ctor`;
- `game_resetTimers4f84a8`;
- `arena_pickSpawnPoint` with the C library;
- every frame, `Player_run` with its modelled helpers and `Player_pickAttackAnim`.

Each piece has its own difftest (`docs/spec/arena-player.md`,
`docs/spec/arena-player-tick.md`). Results, identical in shape on seeds 20973 and 7:

| Scenario | Frames | Waves reached (cumulative objects) | Player constructions | `Player_run` ticks | States (ticks) | Shared draws in `Player_run` | Final seed |
|---|---:|---|---:|---:|---|---:|---|
| idle, 20973 | 2,400 | 0 (2) | 1 | 2,400 | 2: 2,400 | 0 | `0x03199571` |
| fighting, 20973 | 1,688 | 0, 1, 2 (2, 5, 9) | 3 | 1,688 | 1: 1,100; 2: 588 | 36 | `0x65c9ba25` |
| idle, 7 | 2,400 | 0 (2) | 1 | 2,400 | 2: 2,400 | 0 | `0xed4ea82b` |
| fighting, 7 | 1,688 | 0, 1, 2 (2, 5, 9) | 3 | 1,688 | 1: 1,100; 2: 588 | 36 | `0x324380ff` |

Every wave places the player at the original ring point x = 36.0, y = `0x37100000`,
z = 0, facing 1. The new object reuses the old block, and the constructor draws exactly
once. Fighting still sees 9 accepted enemy hits. Record HP ends at 9,851 (seed 20973)
and 9,879 (seed 7), inside the nine-roll 10–20 bound; the probe asserts only the
bound. The 36 draws are combo swings in `Player_pickAttackAnim`. The driver taps
attack every 30 frames during fighting, as an authored pad binding.

**Placement is now faithful for this state** (one active slot, offline, mode B, entry 0
at the origin). The player's own share of the seed stream is also faithful: one draw
per construction and one per combo swing, with the same rules as the executed models.
**The match's seed stream as a whole is not faithful yet**, for these reasons:

- The creature constructors are still fixtures. Each real one makes at least the base
  `GameObject_ctor` draw (`arena-monsters.md` §2.1, `arena-goblin.md`), so waves 0–2
  are missing at least 9 shared draws.
- Animation callees are stubs, so swings never finish (state 1 persists). Idle
  fidgets, which need four animation tracks, never happen.
- `Player_move` is a stub. Its only draw, on entering water, cannot occur in this dry
  fixture (`combat-movement.md` §3).
- The idle-voice draw needs 3,600 frames; idle stops at 2,400.

Commands, with the disc-derived executable placed only in ignored `local/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 20973 --real-player
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 7 --real-player
```

The native client's prerequisites, ranked by first dependency and wave reach:

1. Replace the player at `arena_startWave` with a real 0x590-byte Player
   constructor, record link, tick and input path. **Executed** with
   `--real-player` (section above): constructor chain, destructor, pool reuse,
   placement and tick. Still needed for exact play: real animation stepping,
   `Player_move` with world collision, and real pad input.
2. Build the Goblin constructor with its base Creature/stat and holder chain,
   then run/set-state, target pursuit, attack, damage and death. Wave 0 needs two.
3. Build the Mummy constructor and class combat path for wave 1.
4. Build the Scorpion constructor, including the sting's difficulty-dependent
   damage write-back, for wave 2.
5. Attach SpellArena to each creature and retain its shared-seed draw within
   the arena wave/task lifecycle. The offline probe checks its block and draw,
   but its add-spell service is still stubbed.
6. Add Orc2's constructor, variants and class combat for wider recipes; the
   first three waves of recipe 0 do not request Orc2.
7. Run the assembled player, creatures, world and arena task in the target
   runtime with real input and assets, then compare seeded runs. `ee_emu`
   execution alone is not target-runtime proof.

The seed stream matches the documented SpellArena draw after each constructed
spawn. With `--real-player` the Player replacement and its placement are the
original code (section above). The class constructors are still fixtures, and
their base `GameObject_ctor` draws are missing, so a real match's final seed is
still **not** proved.

`tools/difftest_arena_match_combat.py` adds 69 comparisons per seed 20973 and 7:
all 25 Orc2 set-state and run numbers in a neutral recruit fixture, close and
distant chase for all four classes, four melee hits through Player damage
processing (a 10–20 HP loss per isolated case), four lethal damage/death paths,
and Scorpion sting at difficulty values 0, 2 and 3. The original bodies run;
base activity, sight, animation, `Creature_filterState` and world services have
fixed answers. Rooted, stunned and cooldown rewrites are unexercised. The Orc2
run/set-state call lists and distant chase state are regression pins for seeds
20973 and 7; the CLI rejects other seeds because the documented random recruit
branch can change the distant state. The
other class variants and their spell/projectile branches remain open.

Of the two common later indices, index 25 is `snobadge` and uses the Badger
contract in `tools/ref_monsters_1.py` and `docs/spec/monsters-1.md`. Its quick
difftest was rerun on seeds 20973 and 7: 380 and 366 comparisons, respectively,
with no mismatches. Index 4 is `orc2`; the factory row (size `0x488`, constructor
`0x2a0954`) and bounded recruit class behavior now have difftest coverage.

2026-10-21 coordination handoff: `t3/research-arena-match` reaches mode-B
recipe-0 waves 0–2 through the original factory and arena task with constructor
fixtures. The fighting fixture executes nine enemy hits and Player damage ticks;
69 class comparisons per seed cover Orc2 neutral states and four-class melee.
Native order and proof limits are ranked above. The canonical coordination log
is the coordination log in the open-champions repo.

## Real creature chain (`--real-creatures`, round 6, 2026-10-21)

`--real-creatures` implies `--real-player`. Recipe 0 is the first recipe record (the
task's "recipe 1"). Its waves 0–2 run in one emulator state with the following original
bodies executing instead of fixtures:

- **Constructors.** The whole factory chain for each requested class
  (`docs/spec/arena-creature-chain.md`): class constructor, `Creature_ctor`,
  `GameObject_ctor`, `balance_lookup`, `Creature_setStats` and `Creature_init`.
- **Spawn services.** Slot 34 (home range) and slot 27 (the class set-state with state
  0). The 101 Skill objects and the handle node pool are built first by the game's own
  initialisers. The property list is `arena_init`'s.
- **SpellArena.** `creature_addSpell` and `handle_link` link the record into `+0x364`.
  The record's owner, vtable and draw are still checked at entry.
- **Placement.** `world_findFreeSpot` (0x14acf8), for every creature spawn and for the
  player's spawn point. Its three shared draws per unit-ball sample were previously
  stubbed.
- **Kill path.** In fighting, `Creature_processDamage`'s death branch with gib chunks, the
  Life Tap orb roll, `Creature_onDeath`, `arena_addKill`, `Creature_dropLoot` and the
  whole loot chain, plus every type-info getter.
- **Executed bodies.** Every other body that some difftest of this tree executed
  (`probe_full_placement.executed_bodies()`, 853 bodies). The exceptions are the
  services in `KEPT_SERVICES` (animation, sound, presentation, terrain/ray queries,
  camera/net/dialog checks) and `Player_*`/`player_*` bodies. The player keeps round 5's
  configuration.

Checks made during the runs:

- **Chain model at every spawn.** `ref_arena_creature_chain.chain` is evaluated at each
  spawn's `world_createObject` entry, then compared with the object when SpellArena's
  block is requested. It covers the shared seed, the own seed, and 26–27 fields after
  `Creature_scaleStats` (`ref_arena_match_core.scale_stats`).
- **Free-spot model.** Each `world_findFreeSpot` call is compared with
  `ref_arena_creature_chain.free_spot` on the box query's actual answers: seed, spot and
  `ok`.
- **Seed ledger.** Every value stored to the shared seed lies on the documented
  generator's sequence and is attributed to the function holding the store. The two
  samplers (`world_findFreeSpot`, `loot_spawnGold`) advance in multiples of three.

| Scenario, seed | Frames | Waves (cumulative objects) | Shared draws | Largest consumers | Final seed |
|---|---:|---|---:|---|---|
| idle, 20973 | 3,700 | 0 (2) | 16 | free spot 9, `GameObject_ctor` 3, SpellArena 2, ring step 1, idle voice 1 | `0xee0d357d` |
| fighting, 20973 | 1,688 | 0, 1, 2 (2, 5, 9) | 637 | `item_generateWithAffixes` 299, loot 89, `damage_apply` 64, free spot 57, gold 39, swings 36, `GameObject_ctor` 32 | `0xead31674` |
| idle, 7 | 3,700 | 0 (2) | 34 | free spot 27 (rejection sampling), `GameObject_ctor` 3, SpellArena 2, ring step 1, idle voice 1 | `0x9f20eef1` |
| fighting, 7 | 1,688 | 0, 1, 2 (2, 5, 9) | 1,014 | `item_randomizeVariant` 371, `item_generateWithAffixes` 311, loot 85, `damage_apply` 63, free spot 60, gold 42, swings 36 | `0xd05bbc05` |

In fighting, the chain model matched all 9 constructions on both seeds, and every
free-spot call (12 per run) matched its model. On seed 20973 one Mummy took the rare
element branch, which costs one more shared draw. The kills built 3 and 1 gib chunks,
11 and 9 loot objects, and no Life Tap orb. That orb roll is real now: round 5's float
stub had left a stray `f0`. Enemy hits accepted: 9 and 9, with record HP 9,862 and 9,897.
The probe now asserts only 1–9 hits and a loss bounded by the creatures' own damage
high, since the stats are the real ones. The idle run reaches 3,700 frames, so
`Player_run`'s idle-voice draw at 3,600 happens. That is round 5's fourth missing draw.

**Correction to round 5's placement claim.** Round 5 placed the player at exactly
x = 36.0, because the free-spot service returned the requested point. The original
`world_findFreeSpot` scatters it within range 36: (26.2, 7.8, 0) on seed 20973 and
(32.5, 3.4, 0) on seed 7, with the facing following the moved point. Placement is now
the original code's, on authored flat open ground (`terrain_testFlag1` 0.0,
`terrain_height` 0.0) and the real grid.

**What still keeps the match's seed from being the real game's:**

1. **Authored world.** The ground is flat and open. In fighting, sight
   (`Creature_canSeeTargetIn`), activity and animation events are scripted. The player
   is moved onto each creature and the kills are the driver's 1,000-damage hits.
2. **Animation.** Every animation call is a service. Player swings never finish (state 1
   persists), and idle fidgets, which need four real tracks, never happen. Creature
   attack timing is scripted. `res_find` answers one authored part, so no clip or model
   from the disc is loaded.
3. **Creature ticks.** Creatures are not ticked every frame: never in idle, and two
   scripted ticks per wave in fighting. Objects made during the match (gold piles, item
   props, gib chunks) are never ticked.
4. **Unexecuted bodies reached in fighting.** `Mummy_updateSpells` (slot 17, 4 calls),
   `Creature_setEffectTimer` (seed 20973 only), `fx_modelStatusEffects` and
   `Player_onTouch`. `Goblin_onNearbyEvent` (40 calls: each kill notifies nearby Goblins
   through `world_notifyObjectsNear`) and `Goblin_hasShieldUp` now run for real, with
   their contract in `arena-creature-chain.md` §7. They left the figures above unchanged. Also round 5's player stubs: `Player_move` (dry world: its only
   draw cannot occur), `Player_recalcDamage`, `Player_interact`, `Player_slot37`,
   `player_giveExp`, `player_recalcStats` and `player_resetIdleAnim`.

```text
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 20973 --real-creatures
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 7 --real-creatures
```

### Native ranking for `native-arena-match` (final, round 6)

Ranked by first dependency in the first recipe's waves 0–2, then by shared-seed weight:

1. **Creature construction chain** for arena indices 3, 1 and 0, then 4 and 25.
   The steps, each with its contract in `ref_arena_creature_chain`:
   - `GameObject_ctor`: one shared draw; `+0x44` is the draw.
   - `Creature_setStats` with the `monsters.bal` row: read the user's `balance.lmp` at
     run time, then one own draw.
   - `Creature_scaleStats`, which truncates hit points and experience even at 1.0.
   - `Creature_init`'s height floor of 84.
   - The class's own draws, the Goblin family block, and the rare Mummy's weapon element
     (a second shared draw).
2. **`world_findFreeSpot`.** Three shared draws per unit-ball sample, the 6.0 height
   step, the blocker rule `d² ≤ radius² + r²`, and 50 tries. Every creature spawn and
   every player spawn calls it, so placement and the seed cannot match without it.
3. **SpellArena** record, its attachment at `+0x364`, slot 34 (home range 5000) and
   slot 27 (state 0, with the class's own draws).
4. **The kill path.** In fighting it is the largest seed consumer:
   - the gib burst (one shared draw per `GutChunk`);
   - the Life Tap orb roll (an own draw; `OniBall_ctor` makes one shared draw when it
     succeeds);
   - `Creature_onDeath` / `arena_addKill`;
   - `Creature_dropLoot` → `loot_generateDrops` with the item generators. These are the
     bulk of the 637 and 1,014 draws.
5. `damage_apply` and Player damage processing (already contracted), the Player tick, and
   the idle-voice draw at 3,600 frames.
6. Then the open items above: real animation stepping on clips read from the user's disc
   at run time, per-frame creature AI with real world queries, the unexecuted bodies in
   item 4 of the list above (`Goblin_onNearbyEvent` is done), and runs of dropped objects. Without these, native runs can
   match the probe but not a live match.

## Round 7: disc terrain, clip advance and target selection (2026-10-22)

The new `--disc-terrain ISO` mode reads the arena level's archive from the owner's
disc at run time. Mode B's recipe-0 map comes from the table at `0x503798`
(`docs/arena-modes.md`). It passes `pvparena.world` to original `world_fixup`
`0x181d30`, sets world pointer `0x44fdc8`, and follows original
`terrain_collectElements` `0x183248`, `terrain_testFlag1` `0x183b48`, and
`terrain_height` `0x183820` inside original `world_findFreeSpot` `0x14acf8`.
`ref_world.Level`, `terrain_test_flag1`, and `terrain_height` provide the
independent reference; `difftest_world.py` compared the disc map on seeds 20973
and 7 (300 height, 300 height-below, 150 point-height, and 200 flag cases per
seed, zero mismatches). The probe also compares every free-spot result, success
flag, and shared seed with `ref_arena_creature_chain.free_spot`. The tested arena
spots give the same placements and seeds as round 6's flat-ground answers.
World raycasts, slides, water, full level object loading, and the match's world
walk are still services; this mode establishes only the terrain queries above.

The `--disc-animation ISO` mode additionally reads 214 `.anm` clips from the
owner's `RAGNAR2`, `GOBLIN`, `GOBLIN_Z`, `MUMMY`, and `SCORPION` lumps, without
writing game bytes. It runs original `anim_init` `0x16f9a8`, `anm_relocate`
`0x1707b8`, resolves clips for `res_find` `0x17365c`, and gives each constructed
actor one original `Creature_stepAnim` `0x1162b0` tick with its active flag
authored for this bounded check. Original `anim_advance` `0x16d748` and its
callees run. `ref_anim.py` and `difftest_anim.py` are the independent animation
model/comparison (event bits, track state, decoder slots, root motion and yaw).
Quick advance difftests on the disc's Ragnar, Goblin, Mummy, and Scorpion clip
families passed 12 properties each with zero failures across seeds 20973 and 7.
On both seeds the constructors resolve 133, 179, and 195 clips in waves 0–2;
all 2, 3, and 4 actors have two tracks that advance. The single tick makes no
shared-seed draw. The full match still does not schedule these animation ticks.

In the regular `--real-creatures` fighting probe, the driver now invokes
original `Creature_pickTarget` `0x10ded0` once per living creature; that body
queries the real object grid through `world_collectObjectsInBox` `0x14a928`
and links the selected player's handle. `ref_creature.pick_target` and
`difftest_creature.py` compare the decision, writes, calls and seed on both
seeds (31 and 38 pick-target calls in the quick monster/base runs, zero
mismatches). The original class run-state bodies still receive scripted
activity, sight, player position, and animation-event answers. Per-frame AI
and target scans do not yet run.

Attempting original `world_forEachGridObject` `0x14a610` with arena callback
`0x306a28` in the match exposed a real boundary: after the driver's lethal
wave-1 hits, one creature has object flags `0x612b` and AI state `0x14`.
Original `0x306a28` saves it in pointer table `0x50388c` and sets saved count
`0x8e7340` to one. The next `arena_startWave` `0x305ed4` takes its reuse branch
instead of spawning wave 2. The corrected model in `ref_arena_match_core` and
`difftest_arena_match_core` covers the `0x2` flag's precedence over the `0x8`
death bit on both seeds. The regular probe retains the authored world walk so
that its scripted waves remain comparable. It cannot claim a native world
transition while death animation/AI and object lifecycle are absent.

### Native arena-match ranking (round 7)

1. Run the actual world/object lifecycle: load map objects and execute
   `world_forEachGridObject` `0x14a610` plus `0x306a28` without the saved
   wave-1 creature blocking the next recipe. The `0x612b` state is the first
   observed divergence in the combined flow.
2. Schedule real animation on disc clips through `Creature_stepAnim` `0x1162b0`
   and `anim_advance` `0x16d748`, including death and player clips. The bounded
   one-tick check proves clip loading, not death completion or hit timing.
3. Schedule Goblin, Mummy and Scorpion AI every frame with natural target scans
   (`0x10ded0`), activity, visibility/raycasts, movement, spell/status paths,
   and player input. The current two scripted ticks and forced target scan
   are insufficient for native timing or seed order.
4. Tick spawned drops and props, and remove the remaining authored presentation
   and player-service answers. Then rerun the combined idle/fighting probe and
   compare exact seed, placement, object state and wave transitions. Until then,
   recipe 1 waves 0–2 pass only in the scripted world-walk fixture.

## Round 8: bounded original world transition (2026-10-22)

`tools/difftest_arena_lifecycle.py` builds recipe 0's wave-1 Goblin, Goblin,
Mummy through the original constructors. It then **authors** the observed
post-hit flags: one Goblin `0x612b`, the other two objects `0x6129`. This is a
controlled transition, not a natural kill or a frame schedule. The original
`world_forEachGridObject` `0x14a610` calls the original empty-wave callback
`0x3069e8`, then the original save callback `0x306a28`. The first counts zero
living creatures; the second saves exactly the `0x612b` Goblin in pointer table
`0x50388c` and leaves the shared seed unchanged. Its byte `+0x231` becomes
`0xff`; `obj_moveOffGrid` `0x14ef48` runs. The two `0x6129` objects take the
virtual destructor path. This matches `ref_arena_lifecycle.save_actions` on
both seeds. The authored flags matter: this check does not establish when or
whether a running corpse reaches these exact values.

With saved count `0x8e7340` set to one as `arena_prepareWave` `0x3063fc`
would do, original `arena_startWave` `0x305ed4` advances the wave halfword to 2.
It calls `arena_setRingStep` `0x3065b0`, then `arena_spawnMonster` `0x3065fc`
with a null class-name argument and the saved Goblin pointer. No new
`world_createObject` `0x14f6c8` call occurs. The saved object is placed again
through `world_findFreeSpot` `0x14acf8` and `obj_updateGridCell` `0x14f028`.
The latter free-spot result and the player free-spot result are independently
checked by `ref_arena_creature_chain.free_spot`. The saved branch consumes one
shared draw each at `GameObject_ctor` `0x14cd7c`, the ring step store
`0x3065ec`, the reused-creature spawn store `0x306924`, and the start-wave
store `0x3061ac`, plus the draws from the two free-spot calls. The
`ref_arena_lifecycle.reuse_seed` model compares the final value.

| Seed | Free-spot draws (player, reused creature) | Shared seed before → after | Saved creature placement, raw x/y/z |
|---:|---:|---|---|
| 20973 | 6, 6 | `0x05b7dae3` → `0x7896d3f3` | `0x4319a520`, `0x4271ea66`, `0x00000000` |
| 7 | 30, 15 | `0x50112cb9` → `0x5a2e0ab4` | `0x43429667`, `0xc07bb910`, `0x00000000` |

After this bounded transition, the existing recipe-0 combined probe was rerun
for both seeds with `--real-creatures`. Its **authored world-walk** idle case
remained at wave 0 for 3,700 frames; the fighting case reached cumulative
construction counts 2, 5, 9 after 1,688 frames. Final idle/fighting seeds
were `0xee0d357d` / `0xead31674` for seed 20973 and `0x9f20eef1` /
`0xd05bbc05` for seed 7. The new native save/reuse branch instead has three
constructions at wave 2 in this bounded case, so those fixture final seeds
and wave-2 placements are **not** evidence of a real match seed or placement.

**Distance to a real match:** this establishes the original saved-creature
branch and its placement under authored corpse flags. The combined probe still
uses the authored world walk, scripted attack timing and targets, fixed
visibility/activity answers, and no spawned prop ticks. Its ordinary
four-new-creature wave-2 branch is therefore a different execution. A seed or
placement agreement with that probe is not a live-match fidelity claim.

### Bounded death-clip continuation

`tools/difftest_arena_death_animation.py` repeats the wave-1 construction on
seeds 20973 and 7, reading the goblin's death clip from the owner's disc only at
run time. An **authored lethal hit** reaches original `Creature_takeDamage`
`0x116638`, `Creature_processDamage` `0x110d30`, and `Goblin_setState`
`0x26ccfc`. The death branch calls original `anim_jumpTopToEnd` `0x170bc8`;
the top death track starts at its clip length, 109 ticks. The independent
`ref_anim.Clip` parser and `ref_arena_death_animation.ended_track` model its
held clock and status. With activity answered active, 151 successive calls to
original `Goblin_run` `0x26b27c` each execute `Creature_stepAnim` `0x1162b0`,
`anim_advance` `0x16d748`, and `Creature_deadUpdate` `0x1108a0`. The top track
holds at 109 ticks with ended bits `0x480`; the lower tracks fall away, leaving
one track. The object stays in state `0x14` with flags `0x612b`, and the shared
seed stays at `0x892dfabc` (seed 20973) or `0xebb0d645` (seed 7). The corpse
helper receives event 0 and hold 0 on all 151 ticks, so its non-sinking
deletion rule does not request `obj_delete` `0x14f200`.
The tested deletion condition is the one at `0x1108a0`: creature-flag
`0x1000000` selects a different sinking branch; otherwise a one-track ended
animation deletes only when hold is nonzero. The status bits `0x80` and
`0x400` come from `anim_advance` `0x16d748`.

This bounded result reverses the earlier working hypothesis that simply
finishing the death clip would clear the `0x2` flag before wave 2. The original
reuse branch is a plausible normal path here. Exact match behavior still needs
the real scheduler and input, because the lethal hit, activity and frame calls
above were supplied by the driver.

### Bounded per-frame idle AI

`tools/difftest_arena_ai_frames.py` builds each of recipe 0's waves 0–2 in a
fresh emulator state with the disc's `pvparena.world` and actor clips loaded
at run time. The driver supplies one stationary player activity centre and
32 frame values at `g_simFrame` `0x44fdcc`. Every creature in each wave runs
its original class body each frame: Goblin `0x26b27c`, Mummy `0x298d18`, and
Scorpion `0x2a5068`; original `Creature_updateActive` `0x10c0f0`,
`Creature_pickTarget` `0x10ded0`, `Creature_stepAnim` `0x1162b0`, and
`anim_advance` `0x16d748` execute as callees. The original target scan finds
the player from the object grid without a forced target request. The
independent `ref_arena_ai_frames` model uses the scan condition at `0x10ded0`:
`(frame XOR signed serial byte +0x230) & 0x1f == 0`. The first link appears
on frames 1, 2 for wave 0; 1, 2, 3 for wave 1; and 1, 2, 3, 4 for wave 2,
on both seeds. All these bounded idle ticks stay in AI state 0 and draw no
shared seed. Constructor seeds are `0xb3c33116`, `0x05b7dae3`,
`0x19e63f4e` for seed 20973 and `0x1d30c75a`, `0x50112cb9`,
`0xa025c237` for seed 7.

These are independent wave builders, not one progressing match. No player
movement, real attack timing, spawned-object run, or complete visibility and
collision services are established by the 32-frame idle test.

### Round 9: disc model hull and longer idle AI boundary (2026-10-22)

**Observed** (`SLUS_209.73` v2.00): `creature_dropHeldPartAsProp` `0x117d30`
passes its part definition to `PhProp_ctor` `0x155a0c`. The named constructor
looks up the `.vif` at `res_find` `0x17365c` and stores the model entry at prop
`+0x4c`. `model_getHullPoints` `0x179320` uses header byte `+0x25` times 16,
plus mesh index times 24, to return eight signed-byte xyz points. The previous
fixture returned the same zeroed block for every lookup, so the header byte was
zero; `PhProp_run` `0x155fcc` faulted at `0x1561bc` after a null hull answer.

**Executed** (`tools/difftest_arena_services.py`, seeds 20973 and 7): the
resource boundary now maps `.vif` lookups to entries read from the owner's disc
at test time. The original factory and `PhProp_ctor` bind the model during the
fighting fixture. The first dropped prop uses the goblin axe model on seed
20973 and the goblin sword model on seed 7. The independent
`ref_arena_services.model_hull` model compares the original hull accessor's
pointer and all 24 hull bytes. One original `PhProp_run` tick finishes without
the fault on each seed; shared seed remains `0xead31674` and `0xd05bbc05`.
The test does not execute resource loading, mesh relocation, or a full prop
lifetime. Its disc bytes stay only in ignored emulator memory.

Run the two focused comparisons with `PYTHONDONTWRITEBYTECODE=1`:

```text
python3 tools/difftest_arena_services.py local/SLUS_209.73 --seed 20973 --iso "$ISO"
python3 tools/difftest_arena_services.py local/SLUS_209.73 --seed 7 --iso "$ISO"
python3 tools/difftest_arena_ai_frames.py local/SLUS_209.73 "$ISO" --seed 20973
python3 tools/difftest_arena_ai_frames.py local/SLUS_209.73 "$ISO" --seed 7
```

`ISO` is the owner's local v2.00 disc image path; these commands do not
extract files into the tracked tree.

**Executed** (`tools/difftest_arena_ai_frames.py`, seeds 20973 and 7): the
existing `ref_arena_ai_frames` target-scan model now agrees across 256 original
class-AI ticks per creature in each independent wave builder. Targets link at
frames 1–4 as before, but all objects remain in AI state 0 and at their starting
positions, with no shared draw. This bounded stationary player input does not
produce a fight. The full match driver still moves the player to each creature,
forces attack setup and animation-event answers, and injects lethal damage;
there is no evidence for a natural wave transition or live match.

For the native client, the new portable contract is named `.vif` binding for
dropped held parts and the hull lookup: `model + (u8 at +0x25) * 16 + mesh *
24`, then eight signed-byte xyz points. The prop holds that model at `+0x4c`;
the two observed recipe-0 weapons are named above. The first prop tick made no
shared draw in this fixture. No new attack, damage timing, wave completion, or
full prop lifetime is port-ready from round 9.

### Bounded player and spawned-object services (round 8 baseline)

`tools/difftest_arena_services.py` uses `ref_arena_services` for two small
contracts on seeds 20973 and 7. In a fresh wave-0 builder it runs 200 neutral
`Player_run` `0x1a5030` ticks, following original `Player_move` `0x1b4020`
on every tick. The player stays in state 2 at `+0x58c`; neither run changes
shared seed `0x404464` (final `0xb3c33116` and `0x1d30c75a`). The no-water,
no-input conditions are fixture answers, so this does not compare a real
moving or attacking player. `Player_interact` `0x1b2640`, sight and touch
services remain outside this comparison.

The same script then runs the existing authored fighting fixture to make loot
objects. It calls original `Gold_run` `0x157b58` once on the first constructed
gold pile. Its countdown byte `+0x4c` goes from 41 to 40 on each seed,
matching `ref_arena_services.gold_countdown`; shared seeds remain
`0xead31674` and `0xd05bbc05`. The coin animation advance is still a service
in this fixture. The model's countdown and no-draw rule come from
`Gold_run` `0x157b58` (also `docs/spec/gold-run.md` §4).

The round-8 missing-hull fault was reproduced on both seeds and is resolved
for one original prop tick by the round-9 disc model binding above. Full prop
lifetimes and their rest constructors remain outside this combined fixture.

### Native arena-match ranking (updated after bounded round-8 transition)

1. **World and object lifecycle:** the saved `0x612b` path now has an original
   walker and start-wave comparison. Load the level's objects, run their normal
   list and deletion lifecycle, and determine the corpse state at the actual
   transition. The authored `0x612b` input is the remaining boundary.
2. **Continuous animation:** the bounded Goblin death clip and 151 corpse ticks
   are executed, but schedule all creature and player clips every frame in the
   match, including attack events and movement. Death completion alone did not
   remove the `0x612b` corpse in the bounded test.
3. **Per-frame creature AI:** 256 idle ticks per creature with natural target
   scans and activity now match their scan clock. Extend through fighting and
   death in one scheduler, with real visibility, ray and movement answers.
4. **Player and spawned objects:** neutral `Player_move`, one `Gold_run` tick,
   and one disc-backed `PhProp_run` tick now execute in bounded fixtures.
   Tick dropped props, gold and item objects over their lifetimes; replace
   scripted player actions and remaining service answers. Compare exact
   frame, seed, placement, object state and wave transition against a running
   match. The combined fixture currently cannot make that comparison.

## Round 10: post-intro natural melee and the remaining wave gate (2026-10-23)

US `SLUS_209.73` v2.00. **Observed** at `Creature_filterState` `0x10a9c0`:
when PvP mode B `0x4f7120` is set, mode A `0x4f711c` is clear, match lock
`0x503890` is set and end flag `0x503894` is clear, every requested state
change is refused before the ordinary root, stun and cooldown filters. The
original `arena_startWave` `0x305ed4` leaves that lock at 1. The original
`arena_runTask` `0x306b78` decrements intro halfword `0x5038c8` from 180 to 0
and on its next visit writes `0xffff` there and clears `0x503890`, menu lock
`0x41b4fc`, and second lock `0x41b500` (`docs/arena-modes.md` §3.1).
Round 9 built each wave and ticked creatures without that intro transition;
target handles could link, but class state requests remained refused.

The second missing input was the terrain sight answer. **Observed**:
`Creature_canSeeTarget` slot 25 `0x10e658` calls `creature_canSeeObj`
`0x10c810`, whose clear-line test requires `terrain_raycast` `0x18a5c0` to
return a negative hit parameter or one greater than 1.0. The old idle
fixture left that ray as a service with a zero answer, which means obstructed.
The disc's `pvparena.world`, fixed up by `world_fixup` `0x181d30`, lets the
original ray body and `terrain_collectElements` `0x183248` supply that answer;
`ref_world.terrain_raycast` is its independent model (`difftest_world.py`).
The same disc world supplies `terrain_sweep` `0x185a40` to original
`world_slideMove` `0x14d238` and `terrain_heightBelow` `0x1834a8` to
`Creature_moveBy` `0x113c48`. Leaving either movement service at its prior
default answer produced an invalid slide position or a false 100-unit height.
These are separate conditions: clear sight alone cannot defeat the intro
lock, and clearing the lock alone cannot give the class a visible target.

**Executed** (`tools/difftest_arena_engagement.py` against
`tools/ref_arena_engagement.py`, seeds 20973 and 7): the original task runs
181 intro visits and clears the three locks; `arena_resetScores` `0x307c80`
supplies the offline player speed factor 1.75 at record `+0x4c20`.
The driver supplies the `game_clearLevel` `0x1e4ff0` result, 1.0 at
`g_runSpeed` `0x4f8418`. On the disc terrain and clips, original Goblin
`0x26b27c` and its target scan link the stationary player at absolute
frames 193 and 194. They leave state 0 for chase state 3, move through the
original slide/sweep, and enter melee state 6 without a forced target, state,
position, hit event or damage call. `Creature_stepAnim` `0x1162b0` and
`anim_advance` `0x16d748` read the disc clips; event bit 1 sends the first
hit through `Creature_hitTargetAtReach` `0x1196e8`, `damage_apply`
`0x1e8230`, and `Player_takeDamage` `0x1b5330`, all original bodies.

| Seed | First natural Goblin hit frame | Pending `Player +0xc8` | Record HP `+0xac` before → next player tick | Shared seed after damage | Original empty-wave count |
|---:|---:|---:|---|---|---:|
| 20973 | 327 | 9.0 | 20.0 → 11.0 at 328 | `0x30c8b37e` | 2 |
| 7 | 309 | 9.0 | 20.0 → 11.0 at 310 | `0x5a4d1242` | 2 |

The independent intro, gate, target-clock, unarmed hit-frame and pending-HP
rules are in `ref_arena_engagement`; the lower-level sight, terrain,
animation, damage and player tick bodies also have their existing reference
models. This test checks each original call is not stubbed and uses original
`world_forEachGridObject` `0x14a610` with callback `0x3069e8` to count the
two living Goblins. It does not infer a later wave from a nonempty count.

**Executed, separate input branch:** the driver uses a controller stick to
turn the original `Player_move` `0x1b4020` toward a nearby Goblin and presses
attack once through original `Player_run` `0x1a5030`. Its natural grid target
selection links the Goblin; the unarmed hit frame is 16 ticks after the press.
The wave builder's record has zero attack fields because it omits offline
boot. The input branch now calls original `player_initNewCharacter` `0x1b1d70`
for model 0 with the original class default stats (`g_classStartStats`
`0x4ef400`), then original `player_recalcStats` `0x1b6458` and unarmed
`Player_recalcDamage` `0x1b7158`. The latter computes attack rating
`+0xcc` 28 and damage `+0xd0/+0xd4` 9/10. Starting gear creation remains
a service boundary, so this is a valid class-0 *unarmed* record, not a full
offline character. The initializer runs after the isolated wave builder;
the driver restores the slot's original player object pointer and repeats
`arena_resetScores` so its later 1.75 speed override matches the real order.
`Player_meleeHit` `0x1b6a98`, `damage_apply` and
`Creature_takeDamage` `0x116638` run without a forced hit. The creature's HP
`+0x228` drops immediately and pending `+0xc8` clears on its next class tick
through `Creature_processDamage` `0x110d30`.

| Seed | Turn / press / hit frames | Delivered damage | Goblin HP `+0x228` | Shared seed after hit | Count / wave |
|---:|---|---:|---|---|---|
| 20973 | 300 / 301 / 317 | 8.0 | 64.0 → 56.0 | `0x9738faaa` | 2 / 0 |
| 7 | 287 / 289 / 305 | 7.2 | 64.0 → 56.8 | `0x9b06732e` | 2 / 0 |

The amount is the original `damage_apply` result for each seed; it is
not a fixed unarmed constant. Original empty-wave count remains 2 and wave
halfword `0x8e7338` remains 0. A natural kill and wave transition are still
unverified.

The campaign-combat handoff on `t3/research-campaign-combat` at `f714f66`
independently uses the same grid target identity, `Creature_pickTarget`
`0x10ded0`, and `Player_meleeHit` → `damage_apply` →
`Creature_takeDamage` chain (its `docs/issues/campaign-combat-handoff.md`
rounds 3 and 8). Its boar, equipment and level route are distinct from this
arena fixture; the intro lock and disc arena sight result are the extra
conditions resolved here.

The 181 intro-task visits intentionally do not tick actors. Trying to run the
original `SpellArena_run` `0x305bbc` during that interval reaches a division
at `0x305ce8` with zero returned by the missing actor model/joint service
`0x1799c8`; a complete scheduler needs the actual model there. After intro,
the driver chooses the player-before-creature tick order and one controller
input. It does not load all level objects, run drops over their lifetimes,
or reproduce a Play! match. The separate `difftest_arena_lifecycle.py`
still compares wave reuse under *authored* corpse flags; it cannot supply
the missing natural kill.

Run both seeds without writing game bytes:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_engagement.py local/SLUS_209.73 "$ISO" --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_engagement.py local/SLUS_209.73 "$ISO" --seed 7
```

### Native port order after round 10

1. **Arena phase and activity:** preserve `arena_startWave`'s intro locks and
   the 180-to-`0xffff` task transition at `0x306b78`, then schedule the same
   player and creature identities from the original grid/run lists. The
   after-intro test is a bounded function-level execution.
2. **Sight and movement:** port `Creature_canSeeTarget` `0x10e658`,
   `creature_canSeeObj` `0x10c810`, disc terrain ray `0x18a5c0`, sweep
   `0x185a40`, slide `0x14d238`, and height-below `0x1834a8` together.
   Retain the target handle `+0x234` and the 32-frame scan clock.
3. **Animation and creature damage:** schedule the disc attack clip and
   `Creature_stepAnim` event bits; preserve `0x1196e8` → `0x1e8230` →
   `0x1b5330`, queued `Player +0xc8`, then `0x1b2cc0` on the next player
   tick. The observed nine-point case is this fixture, not a universal value.
4. **Valid player and natural kills:** initialize the real player record and
   equipment before `Player_recalcDamage` and normal input. Original
   class-0 defaults now prove one unarmed positive hit and next-tick
   `Creature_processDamage`; starting gear and a sequence of natural kills,
   death clips, loot and corpse flags remain to be executed together.
5. **Wave lifecycle:** use the original empty-wave callback and saved-object
   walker, then `arena_nextWave` `0x305e9c` / `arena_startWave` on a natural
   death. The current original walker sees two living creatures. The bounded
   authored `0x612b` reuse branch from round 8 is the only executed wave-2
   transition, and a live match remains unverified.

## Round 11: assisted Goblin deaths, empty wave, and result hand-off (2026-10-23)

US `SLUS_209.73` v2.00. **Executed** in `tools/ee_emu.py` by
`tools/difftest_arena_round11.py` on seeds 20973 and 7. This continues the
round-10 disc terrain and animation fixture after its 181 intro-task visits.
The player record is initialized through the original class-0 unarmed path;
the driver raises only its HP and maximum HP to 10,000 so attacks do not end
the observation. It writes no Goblin HP, state, score, or seed. Controller
presses produce 12 and 15 original `Player_meleeHit` calls, respectively.
The reduced fixture then stops producing enough controller hits, so the
driver schedules the **original** `Player_meleeHit` body 14 and 16 further
times, with the same player and a living Goblin as target. The body still
performs collision, attack rolls, `damage_apply` `0x1e8230`, and
`Creature_takeDamage` `0x116638`; some calls miss. This is an assisted
function-level kill, **not** a controller-only natural kill or a live match.

| Seed | Goblin death frames | Score after both | Empty-wave scan / intermission start | Wave 1 start | New creature classes |
|---:|---|---:|---:|---:|---|
| 20973 | 1120, 1408 | 2 | 1408 / 1408 | 1888 | 3, 3, 1 |
| 7 | 1084, 1480 | 2 | 1536 / 1536 | 2016 | 3, 3, 1 |

**Executed:** the original hit body accumulates damage at Goblin HP `+0x228`
until each crosses zero. The next `Goblin_run` call enters
`Creature_processDamage` `0x110d30`, reaches death state `+0x232 = 20`, and
sets death flag `0x8`. Each death segment calls original
`Creature_onDeath` `0x10beb8`, `arena_addKill` `0x3056cc`,
`Creature_dropLoot` `0x10f2c8`, and `loot_generateDrops` `0x100d54` once.
The score record at `0x503898` reaches two kills; the fixture records one
loot-pool allocation across the two deaths, but does not tick that object,
collect it, or establish a Gold credit. The campaign boar research at
`t3/research-campaign-combat` `328b072` confirms the shared
`Player_meleeHit` → `damage_apply` → `Creature_takeDamage` → next-tick
death and loot order in a separate assisted Play! session. Its later Gold
credit came from an AutoContainer, so it is no evidence of Goblin Gold here.

**Executed:** original `world_forEachGridObject` `0x14a610` and empty-wave
callback `0x3069e8` count zero after both deaths. `arena_runTask` `0x306b78`
checks on frames divisible by 128 and starts intermission. After 480 offline
task visits, original `arena_nextWave` `0x305e9c`, preparation `0x3063fc`,
and `arena_startWave` `0x305ed4` advance wave halfword `0x8e7338` from 0
to 1, decrease waves-left `0x8e733a` from 2 to 1, and construct the recipe's
next three creatures. The original score snapshot becomes two. The test does
not tick those newly constructed creatures or run a later wave to completion.

**Observed/Executed end rules**, checked in fresh bounded states by the same
driver and independently modelled in `ref_arena_modes.py`: mode A ends when
the signed kill count reaches the signed limit byte `0x4f8408` (4/5 stays
open; 5/5 opens `arena_openEndPrompt` `0x307ebc`). Mode B's player-out scan
retries with `arena_nextWave(0)` when a saved life snapshot is positive;
with lives `-1`, zero HP, zero countdown, and no snapshot, it sets end flag
`0x503894` and opens that prompt. At full fade, confirm copies the saved
player record, calls shutdown `0x304fb0`, and requests the arena level name
through `strcpy` `0x3b868c`; cancel clears mode B `0x4f7120` and sets session
exit code `0x41b508 = 1`. These are isolated original task-body executions
with UI, active-slot, saved-record lookup, and string services supplied by
the fixture. They do not show a displayed results screen, normal save, or
successful next-level load. The separate `difftest_arena_modes.py` also
checks final-wave `waves-left = 0` pending-level hand-off.

Run this comparison and the earlier arena comparisons with
`PYTHONDONTWRITEBYTECODE=1`; the executable and disc remain ignored inputs:

```text
python3 tools/difftest_arena_round11.py local/SLUS_209.73 "$ISO" --seed 20973
python3 tools/difftest_arena_round11.py local/SLUS_209.73 "$ISO" --seed 7
```

### Native port order after round 11

1. Preserve the original class-0 player initialization, equipment boundary,
   controller input and every-frame player/creature scheduling. The assisted
   direct melee calls must be replaced by normal animation events before
   claiming a natural controller-only kill.
2. Port the shared damage chain, queued damage consumption, death state and
   flag transitions, `Creature_onDeath`, arena score, loot generation and
   actual loot-object lifetime. Keep Goblin rewards distinct from the
   campaign boar and AutoContainer observations.
3. Run the original empty-wave grid scan at the 128-frame clock, preserve the
   480-visit offline intermission, saved-object walker, `arena_nextWave` and
   next-wave constructors. Resolve the corpse `0x612b` reuse branch with a
   complete object and animation scheduler.
4. Implement mode-A kill-limit and mode-B wipe/snapshot end paths, ranking,
   fade, confirm/cancel and pending-level hand-off. Verify a full match and
   displayed results in a running game before promoting the bounded task
   executions to gameplay proof.
