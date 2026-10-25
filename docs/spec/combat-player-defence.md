# Combat round 2: the player's defence and the real player tick

US `SLUS_209.73` v2.00. This document adds to [`docs/combat-runtime.md`](../combat-runtime.md)
(round 1) and is the prose of `tools/ref_combat_ptick.py`. Nothing in round 1's files is
changed: round 1's `Runtime`, `CombatModel` and its vectors (the 80-tick duel self-pin)
are as they were; the new bodies live in a subclass and are a superset of round 1's.

Evidence labels as in round 1: **Executed** = run one function at a time in
`tools/ee_emu.py` (an instruction interpreter, not a console) against the model, test
named; **Observed** = read at the address given; **Inferred**; **Unknown**; **Authored** =
a choice of this contract. Nothing here was run on a console, in PCSX2 or on the live rig.

## 1. In brief

1. **A block from the front cancels the hit.** A player in action state 8 (block) or 0xb
   (block move) hit by an attacker with flags lacking 0x40, and with the attacker in the
   front half-plane (`cos·dx + sin·dy > 0`), takes **nothing**, or **half** when the flags
   have 0x20000. A block from behind takes the full hit. *Executed* (§2).
2. **Blocking costs one shared draw only in state 8** (the block clip choice), none in
   state 0xb; **a front block walks the player's own seed by at least 150 draws**
   (`Player_blockSparks`: 50 sparks, a unit-ball point of three own draws each, retried).
   *Executed*.
3. **Knock-downs** (knock-back level ≥ 2, i.e. flag 0x80000 / 0x100000 / 0x200000, after
   PvP and block reductions) pick `knockdown{1,2}_{a,b,c,d}.anm` by weapon class and
   bearing; a resisted one calls `SkillStrongStance_trigger` (real player only) and zeroes
   the knock-back speed; an unresisted one sets action state 3 first, then starts the clip
   unless it already plays. *Executed* (§3).
4. **The stagger roll is not made for every surviving hit**: it is skipped in action states
   3 and 7, with flag 0x400000, on a heavy attack (+0x44c = 2) - and so also after a
   knock-back reaction of the same call set state 3. A knock-back hit therefore draws
   **once** (Strong Stance), not twice. *Executed*; corrects round 1 §2.3 (§7).
5. **Blood draws the shared seed** for the real player whenever flags & 0xd and
   (`g_decalDetail` > 0 or a net game), and on a draw with `& 7 == 0` asks the pool for a
   `GutChunk` object (0x268 bytes). *Executed*.
6. **The real tick as slot 4** (`TickRuntime`): a standing player draws the shared seed
   **once every tick** in `Player_idleFidget` (exactly four animation tracks - what
   `player_resetIdleAnim` 0x1b2470 leaves), not when a fifth (swing, reaction) track plays;
   the idle voice adds one draw when its counter passes the limit +0x4b2. Round 1's
   authored driver made neither. *Composition of executed models* (§5).

## 2. `Player_takeDamage` 0x1b5330 - the block and the Holy Shield

*Executed* (`tools/difftest_combat_ptick.py`, entry `takeDamageFull`: 3,000 cases, 0
mismatches, 280 of 280 instructions; on the 2,399 of them inside round 1's domain the
round-1 method makes the same calls, stores and draws). Model:
`DefenceModel.player_take_damage_full`. Order, after round 1's early exits, the tint and
the hit-immunity test (unchanged):

| Step | Condition | Effect | Address |
|---|---|---|---|
| block clip | attacker ≠ 0, state 8 or 0xb, `flags & 0x40` = 0; **state 8 only** | one shared draw `d`; `d > 0xafc7`: `anim_startBlendInOut(P+0x114, anim(0x8c), 0x812; 0.1, 0.1)`, else `anim(0x94)` with 0.2, 0.2 | 0x1b546c-0x1b553c |
| in front? | same | `dot = cos16(facing)·(A.x−P.x) + sin16(facing)·(A.y−P.y)`; `0 < dot` | 0x1b5540-0x1b55a8 |
| front block | `0 < dot` | `sound_playAtPos(res_find('fx.lmp', block sound 0x5376d0), P.pos; 1.0)`; `Player_blockSparks(P, 0)`; amount = `flags & 0x20000 ? amount × 0.5 : 0` | 0x1b55b0-0x1b5624 |
| Holy Shield | the spell found (looked up on every hit) and record mana +0xc0 > 0 | `frac = SpellHolyShield_absorb(spell)`; `paid = amount × frac`; amount −= paid; mana (read again after the call) −= paid; each floored at 0 | 0x1b5628-0x1b5688 |
| pending | always | as round 1 (+0xc8 += amount, flags, hit angle, last attacker, HUD flash) | 0x1b568c- |

`anim(k)` = `*(P+0x24) + record+0x4a86 × 0x68 + k`. The two "in front" tests differ: the
block in `Player_takeDamage` is a half-plane (dot > 0, 180°), the level reduction in
`Player_processDamage` is `|s16(hit angle − facing)| ≥ 0x6000` (a 90° cone; §3) -
*Observed*, both executed.

`SpellHolyShield_absorb` 0x2e8534 is a call-out (its particles use the spell's own
generator; it may create a `LightEffect`, a pool object; symbol note). The Runtime has no
spells, so the branch only runs with a plugged lookup (test `test_holy_shield_pays_from_mana`).

### 2.1 `Player_blockSparks` 0x1b9658, silent = 0

*Executed* (entry `blockSparks`: 3,000 cases, 0 mismatches, 198 of 408 instructions - all
of the silent-0 path; the other 210 are the silent ≠ 0 branch, refused). The only call
from `Player_takeDamage` passes 0 (0x1b5604); the other caller (0x152fa8) is not in the
domain.

1. `sound_playOnObject(res_find('fx.lmp', spark sound 0x5379c8), R+0x43d8; 1.0)`
   - the record's object, which is the real player even when P is the prediction copy.
2. Hand points `model_getAttachPoint(P+0x544, P.pos, facing, P+0x114, 0 / 1, out, 0; 1.0)`;
   `M = (h0 + h1) × 0.5`.
3. `V = (cos16(facing) × 10, sin16(facing) × 10, 10)`; 50 times: `v` from own draws
   (`GameObject_rand(P)`; component `2·(d × 2^-16) − 1`, retried while `1 < |v|²`),
   **`V += 5·v` without reset** (the velocity walks from spark to spark),
   `particle_spawn(0x8657c0, M, V; 0.0)`.

So P+0x44 (simulation state: other own-seed users are reactions and dust) advances by 150
or more per front block, on every machine that runs the hit. The silent ≠ 0 branch draws
the **shared** seed over model sample points (0x1b9928-0x1b9c68, *Observed*, refused).

## 3. `Player_processDamage` 0x1b2cc0 - the parts round 1 refused

*Executed* (entry `processDamageFull`: 2,991 cases, 0 mismatches, 9 refused, 699 of 784
instructions; round-1 agreement 1,437 of 1,437). Model: `player_process_damage_full`.
Not executed: the PvP-A kill credit by a player (0x1b35b0-0x1b36d0, refused) and nops.

- **PvP mode A** (0x1b2e50-0x1b2e7c): without a knock-back class, on to C; else level − 1
  and +0x2e8 × 0.5, *before* the block reduction.
- **Knock-down** (level ≥ 2 after the block reduction; 0x1b2f0c-0x1b30c4). Name =
  `knockdown2_` for record+0x4a86 (read unsigned) in {2, 3}, else `knockdown1_`, plus the
  bearing `rel = s16(+0x2e0 − facing)`:

  | rel | suffix |
  |---|---|
  | < −0x5fff or ≥ 0x6000 (hit travelling against the facing: attacker in front, *Inferred*) | `a.anm` |
  | −0x5fff … −0x2000 | `c.anm` |
  | −0x1fff … 0x2000 | `b.anm` |
  | 0x2001 … 0x5fff | `d.anm` |

  Resisted (the Strong Stance roll): for the real player
  `SkillStrongStance_trigger(g_skillStrongStance, P, name, trunc(+0x2e8))`; +0x2e8 = 0
  after it (copy: only the zeroing); action state not changed. Not resisted: action state
  3 (set before the name is built, with its voice), then unless `Player_hasAnim(P, name)`
  the top-track fix-up and `anim_startBlendInOut(P+0x114, res_find(*(*(P+0x24)), name),
  0x80a; 0.1, 0.1)`. Flag 0x400000 does not suppress a knock-down clip (it does the small
  one).
- **Blood** (0x1b3230-0x1b32d8): `point = (P.x, P.y, P.z + 36)`; with flags & 0xd and
  (`g_decalDetail` > 0 or `g_networkMode`): `fx_spawn(0, point)` when the decal option is
  > 0; real player only: **one shared draw**, and on `draw & 7 == 0`
  `pool_new(0x268)` and, given a block, `GutChunk_ctor(block, point, 2, 1; 1.0)`.
- **Disintegration** (0x1b32e4-0x1b334c): flags & 0x10 and record hp ≤ 0:
  `fx_disintegrateModel(P, P+0x544, P+0x114, P.pos, facing, 0; 1.0)`, then on as before.
- **Resurrect** (0x1b3380-0x1b33cc): the spell found and `g_numPlayers` **exactly 1**:
  record hp = `SpellResurrect_onOwnerDeath(spell)` (it draws the shared seed itself, symbol
  note); above 0: flags dropped and return - no death and no stagger roll.
- **Held spell** (0x1b340c-0x1b3434): node +0x588 → object; its slot 1 (table at **+0x14**,
  not +0x48) with 3.
- **PvP**: mode A - no shout from the other player; a player killer gets mana and maybe a
  skill-0x3b orb (`OniBall_ctor` 0x294014, a shared draw) - refused; a creature killer or
  none: nothing. Mode B - `arena_onPlayerKilled(slot, killer)` 0x305580 with a last
  attacker, else `arena_loseLife(slot)` 0x305650 (call-outs).

## 4. `Player_interact` 0x1b2640 - the call the real tick makes every tick

*Executed* for the case of nothing to interact with (entry `playerInteract`: 2,615 cases,
0 mismatches, 385 refused; 142 of 416 instructions - the rest is the interaction). The
real tick calls it with displayOnly 0 for the real player outside menus (0x1a5c18). Nothing
in a vehicle, with hp ≤ 0 or without a record object; else a box query around the
**record's object** `(o.x ± 48, o.y ± 48, o.z … o.z + 60)`, limit 0x100; objects with flag
0x100000 are candidates (nearest in 3-D, below 1e7 squared; refused when there is one).
With none: `0x4d8ac0[slot] −= 7`; at ≤ 0, `0x4d8ad0[slot] = 0`, the timer 0, and the first
two halfwords of `0x864f50 + slot × 0x200` = 0. Who reads these words is not established
(the HUD prompt, *Inferred*); they are written on every tick of a real player.

## 5. The real player tick as slot 4

`TickRuntime` (a `ref_combat_runtime.Runtime`) runs `ref_player.Tick.run` - the model of
all of `Player_run` 0x1a5030 that `tools/difftest_player.py` executes (31,990 ticks, 0
mismatches, 92% of instructions) - on the shared image, with `DefenceModel` as the model.
Every call-out goes through `TickServices` (round 1's table, plug-ins first, unknown names
refused). In the 80-tick duel of the tests it reaches 49 names:

| Call-out | Answered by | Evidence |
|---|---|---|
| `Creature_run`, `Creature_applyKnockback`, slots 12, 17, 26 | ref_creature / round 1 | Executed |
| `Player_processDamage` | `DefenceModel` | Executed (§3) |
| `Player_interact` | `DefenceModel` | Executed (§4) |
| `Player_move` | round 1's restricted body (still stick, modes 0, 3, 4) | Observed; plug the movement model |
| `Player_meleeHit`, `Player_findTarget`, `Player_recalcDamage`, `damage_apply` | round 1 (unarmed) | Executed |
| `Player_pickAttackAnim` | **refused** until plugged | its draw and store executed (difftest_player 9.10) |
| `Player_animStep`, `anim_start*`, `anim_advance` | `PlayerAnim` | Authored |
| `anim_findTrackByFlag` | the image (ref_anim's rule) | Executed in tools/difftest_anim.py |
| `res_find` | a token per name | Authored |
| `model_getAttachPoint` | the object's position | Authored (no skeleton) |
| light lists, weapon trails, sounds, voice, rumble | presentation | traced, ignored |
| `dialog_isOpen`, `game_isFrozen`, `net_*`, `task_isRunning`, terrain | round 1's fixtures | Authored |

**`PlayerAnim`** (*Authored*, matched to *Observed* facts): a player's state keeps the four
base cells `player_resetIdleAnim` writes (count +0x118 = 4; research-anim
`docs/spec/player-animation-dispatch.md` 3.1); a started clip is a fifth track (its token
at track +0, its flags at track +0x1c) until it ends, then the count is 4 again and +0x11a
gets 0x80. Creatures keep round 1's one-track timeline.

**Shared draws of slot 4 per tick** (`TickRuntime.draws_by_player`, counted from the seed,
so the models the tick calls are included):

| Case | Draws | Test |
|---|---|---|
| standing, four tracks | 1 (fidget) | `test_a_standing_player_draws_once_per_tick_for_the_fidget` |
| the tick the idle-voice counter passes +0x4b2 | 2 (fidget, voice); new limit `((d % 30) + slot × 45) × 60 + 0xe10` | `test_the_idle_voice_draws_when_its_counter_passes_the_limit` |
| a swing playing (five tracks) | 0 | `test_a_swing_track_stops_the_fidget_draw` |
| plus pending damage | + Strong Stance roll, + stagger roll, + blood roll (§3) | duel pin |
| the player's own hit | + damage_apply's 8 | duel pin |

This matches `docs/spec/player-tick.md` §10 rows 1 and 2.

**Plug-in points.** `TickRuntime.plug(name, fn)` answers the call-out `name` with
`fn(*args)` from then on, before any built-in answer. The round-2 movement model
(`tools/ref_combat_move.py`) is meant for `'Player_move'` (args `P, mode, pad, ext`) and
`'obj_moveWithCollision'` / `'creature_moveSimple'`, the melee model
(`tools/ref_combat_melee.py`) for `'Player_pickAttackAnim'` (`P, cls`; one shared draw)
and `'Player_meleeHit'` (`P, target, a2, extra, scale`). Note: calls the models make among
themselves (e.g. `Player_move` → `creature_moveSimple` inside `CombatModel`) go through
`CombatModel.INTERNAL`, not the services; replace those by subclassing the model.

## 6. What was run

- `python3 tools/difftest_combat_ptick.py local/SLUS_209.73` (seed 20973, 3,000 cases per
  entry): **11,606 cases compared, 0 mismatches**, 394 refused (385 interactable objects in
  reach, 9 PvP-A player kill credits); round-1 agreement 3,836 of 3,836. `--seed 7
  --quick` passes too.

| Entry point | Compared | Refused | Instructions executed |
|---|---|---|---|
| `Player_takeDamage` | 3,000 | 0 | 280 of 280 |
| `Player_blockSparks` (silent 0) | 3,000 | 0 | 198 of 408 |
| `Player_interact` (nothing in reach) | 2,615 | 385 | 142 of 416 |
| `Player_processDamage` | 2,991 | 9 | 699 of 784 |

  Real: the entry, `Player_blockSparks` inside `Player_takeDamage`, `GameObject_rand`,
  Player slot 39, the angle functions, the C library (`sprintf`, `strcat`; its scratch
  block 0x50c530- is not compared). Everything else is a recording stub.
- `python3 -m unittest tools/test_ref_combat_ptick.py`: 21 synthetic tests (round 1's pin
  with `DefenceModel`, round 1's `Runtime` unchanged, blocking front / behind / 0x20000 /
  0xb / 0x40, Holy Shield, knock-down names, clip, already playing, resisted, blood and
  the refused `GutChunk`, fidget and voice draws, plug-ins, the refused combo choice,
  `Player_interact`, a self-pin of the 80-tick duel on the real tick - evidence about the
  model only).

## 7. Corrections to round 1

| Where | Was | Is | Evidence |
|---|---|---|---|
| `docs/combat-runtime.md` 2.3, proposed FINDINGS row 3 | "one stagger roll for every surviving hit" | not in action states 3 or 7, not with 0x400000, not on a heavy attack - and so not after a knock-back reaction of the same call set state 3; a knock-back hit draws once | Executed (0x1b3718-0x1b37c8; `test_a_heavy_knock_back_class_knocks_down`) |
| `docs/combat-runtime.md` 6.3 (block) | "block (states 8, 0xb; one shared draw in state 8)" | and a front block (half-plane) zeroes the amount, or halves it with flag 0x20000; sound, `Player_blockSparks` (≥ 150 own draws) | Executed (§2) |
| `docs/combat-runtime.md` 6.4 B | the knock-down "not in the contract" | §3 | Executed |
| `docs/combat-runtime.md` 6.4 D | "a Resurrect spell may save (one player only)" | only with `g_numPlayers == 1`, and a save skips the stagger roll (return) | Executed |

No round-1 method was found to disagree with the original: on round 1's domain each
`_full` method made identical calls, stores and draws in every case.

## 8. Not done, not known

- `Player_pickAttackAnim` (combos), the armed `Player_meleeHit`, `Player_move` with a
  moving stick: plug-in points, owned by the parallel round-2 work.
- Objects created on the defence path: `GutChunk` (1 in 8 blood rolls), the Holy Shield's
  `LightEffect`, `SkillStrongStance_trigger`'s object and particles, the Resurrect phantom,
  the PvP orb - refused in the Runtime.
- `Player_blockSparks` with silent ≠ 0 (shared draws); `Player_interact` with an
  interactable object; who reads the prompt words 0x4d8ac0 / 0x4d8ad0 / 0x864f50.
- Net games, the prediction copy in the Runtime, cutscenes, water, more than two alive
  players offline (round 1's `Player_move` refuses the screen clamp).
