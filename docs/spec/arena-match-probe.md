# Offline arena match probe, recipe 0

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
spawn. It does **not** prove a real match's final seed or placement: the Player
replacement and class constructors are fixtures, and those missing bodies can
draw from the shared generator.

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
