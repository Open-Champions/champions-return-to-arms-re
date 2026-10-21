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
original class vtable and known stats. Its AI tick, damage, and class-specific
set-state do not run in this probe. Virtual slots 27 and 34 are recording
stubs; the world free-spot service supplies the requested point. The factory
mapping was separately compared for all 30 names in
`tools/difftest_monster_build.py`. The constructor fixture is distinct from
the neutral constructor difftests in `docs/spec/arena-goblin.md` and
`docs/spec/arena-mummy.md`.

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
driver marks the fixtures dead after each intro, standing in for a player's
lethal attacks. The original task sees the empty wave and advances: wave 0 has
2 objects, wave 1 has 3 more, and wave 2 has 4 more. Wave 2 is reached by frame
1,687. The driver does **not** execute an attack, class damage, death, or AI
body. It demonstrates arena flow under those outcomes; it cannot establish
combat behavior or real-world timing.

Commands, with the disc-derived executable placed only in ignored `local/`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_arena_match.py local/SLUS_209.73 --seed 7
```

The native client's first prerequisites by observed reach are: the Goblin
constructor and its base Creature/stat chain; Goblin set-state, run and damage
through death; the Mummy constructor and class behavior for wave 1; the already
modelled Scorpion constructor, state/run and death path for wave 2. The arena
helper sequence and factory row selection already have independent difftests;
the synthetic wave proof does not replace the missing class contracts.
