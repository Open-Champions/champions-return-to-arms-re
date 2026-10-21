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
The 0x590-byte player replacement at `arena_startWave` still returns null,
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

Commands, with the disc-derived executable placed only in ignored `local/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 7
```

The native client's prerequisites, ranked by first dependency and wave reach:

1. Replace the player at `arena_startWave` with a real 0x590-byte Player
   constructor, record link, tick and input path. The probe refuses that
   allocation and rebinds its authored player for combat.
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
