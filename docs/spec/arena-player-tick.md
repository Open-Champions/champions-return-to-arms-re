# Arena player tick on a constructed Player

US `SLUS_209.73` v2.00. **Executed** with `tools/difftest_arena_player_tick.py` on
seeds 20973 and 7 (`work/` log, not tracked):

| Entry | Reference model | Compared per seed | Mismatches |
|---|---|---|---:|
| `Player_run` `0x1a5030` | `tools/ref_player.py` (`docs/spec/player-tick.md`) | 1,500 ticks; states 1, 2, 3, 4 | 0 |
| `Player_takeDamage` `0x1b5330` | `tools/ref_combat_ptick.py` (`docs/spec/combat-player-defence.md`) | 400 cases | 0 |
| `Player_processDamage` `0x1b2cc0` | `tools/ref_combat_ptick.py` | 400 cases | 0 |

State coverage at the start of each tick, as ticks for states 1 / 2 / 3 / 4:

| Seed | State 1 | State 2 | State 3 | State 4 | Rebuilds |
|---|---:|---:|---:|---:|---:|
| 20973 | 510 | 648 | 102 | 240 | 6 |
| 7 | 459 | 676 | 205 | 160 | 4 |

Shared draws in the damage cases: takeDamage 31 (seed 20973) and 42 (seed 7);
processDamage 262 and 245. Each was equal to the model's count, case by case.

## What is new here

Earlier tick and damage difftests started from authored player objects. Here the
object comes from the original constructor chain (`docs/spec/arena-player.md` §1–2):
`Player_ctor` → `Creature_ctor` → `GameObject_ctor`, with the real class definition
`0x4ecc58`, zero-filled first as `pool_new` does, at the arena ring point from
`arena_pickSpawnPoint` (x = 36.0, y = `0x37100000`, z = 0, facing 1). Offline mode B is
set (`g_pvpModeB` `0x4f7120` = 1). Every construction is checked to draw the shared seed
exactly once, link the record, and leave state 2.

The pad script drives the probe's reach:

- neutral idle;
- a held stick (walking from state 2);
- melee combos from attack taps (state 1, `Player_pickAttackAnim` with its one shared draw);
- the harness's scripted hits (state 3);
- the harness's scripted deaths (state 4).

After 40 dead ticks the object is rebuilt in the same block by the constructor, as
`player_respawn` does (`arena-player.md` §6).

## Fixture changes after construction

These are named changes, not results:

- +0x48 is set to the harness's scripted virtual table. The virtual slots (17, 20,
  26 and 39 for the tick) are the harness's call-outs.
- Every constructor `res_find` answers with one of the harness's animation handles.
  The handle page is mapped as zeroed memory, so the constructor's event-field stores
  land there.
- The record (equipment, one-hand sword for the tick) comes from the harness.
- For the damage entries, the case's combat state is written back after
  construction: action state, protection countdown, pending damage and flags, vehicle,
  spell links, track count.

## Reused work, not redone

- `Player_move` `0x1b4020` (a scripted call-out here) and its collision are executed in
  `docs/spec/combat-movement.md` (`tools/difftest_combat_move.py`), from
  `t3/research-combat-walk`. That branch's commits `a10fe26` / `e20760a` (walking
  after a swing, not merged here) cover the walk that follows a swing.
- `Player_takeDamage` / `Player_processDamage` bodies, blocking and knock-downs:
  `t3/research-combat`, `docs/spec/combat-player-defence.md`.
- The full `Player_run` state machine with all states and helpers:
  `docs/spec/player-tick.md` §11.

## Limits

- Animation events, ground contact, targets and world queries are scripted answers.
- No real pad hardware and no real assets.
- The tick does not include another player's prediction copy (offline).
- States 0 and 5–15 are covered only by the earlier authored-object difftests, not on
  a constructed player.
