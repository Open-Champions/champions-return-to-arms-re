# Offline arena match probe, recipe 0

**Round 6 (2026-10-21):** `--real-creatures` replaces the constructor fixtures described
below with the original chain, executes `world_findFreeSpot` and the kill/loot path, and
corrects round 5's placement claim. See the section "Real creature chain" at the end;
the earlier sections describe the fixture modes, which are unchanged.

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
