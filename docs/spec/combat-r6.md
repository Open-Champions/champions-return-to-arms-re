# Hit direction, stagger, kill credit, creature death and real cast bodies (round 6)

Status: **Executed, partial**. Original functions ran in `tools/ee_emu.py` on seeds
20973 and 7. `tools/difftest_combat_r6.py` reports PASS, 864 assertions, 0 failures.
This is not a playable session and nothing ran on a console.

This note closes five items that `docs/spec/player-spells-numeric-r3.md` left
**Unknown**: the hit direction at `+0x2e0`, the stagger threshold, creature kill
credit, the creature death path, and the real cast body inside `Player_castSkill`.
No reference API, test vector or earlier difftest changed.

Labels: **Executed** means the original function ran in the interpreter and a check
in the probe compared the result. **Observed** means read in the code at the named
addresses, not run here. **Inferred** is a conclusion from those. **Unknown** is open.

## How it was run

From the worktree root, with unittest imported first:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["tools/difftest_combat_r6.py"]; runpy.run_path(sys.argv[0], run_name="__main__")'
```

One process runs both seeds. The ignored receipt `local/spells-r3/combat-r6-counts.json`
stores counts only. A missing or unexpected private executable exits 2.

Per run, both seeds together: 30 `Player_takeDamage`, 62 `Player_processDamage`,
58 `Creature_takeDamage`, 42 `Creature_processDamage`, 24 `Creature_applyKnockback`,
28 `Creature_deadUpdate`, 6 `Creature_run`, 52 `SkillStrongStance_getStat0` and 32
`Player_castSkill` calls.

Every case starts a fresh interpreter, except the cast cases, which use the
round-3 family rigs. Callees that are not followed are stubs. The stubs are named
next to each claim below and in the probe's docstrings. One fixture is shared:
sixteen zeroed handle nodes on the free list at `0x864ea8`. Without it the real
`handle_link` `0x1a1738` would store through a null node. The knock cases of
section 2.2 also run the executable's own skill start-up (`0x16ac74`, `0x1ebca0`),
as `tools/difftest_skills_b.py` does, so the Skill objects and their statistics are
the executable's.

Controls: `tools/mutate_combat_r6.py` swaps one probe-side oracle at a time (a
constant or a probe method, never the guest) and runs the section that uses it on
seed 20973. Each of 24 swaps must fail: angle + 1, a stagger limit one lower, the
0.04 constant, the killer swapped, no half share for a dead player, the sink step,
the knock-back scale, the aim offset; for the skill `0x3e` roll, 4 × rank for the
chance, modulus 101, and one draw in the reaction; for the block rules, the boundary
`0x6001`, a front block that adds everything, and state `0xb` ignoring `0x20000`; for
the death path, four wrong event orders, the flag store at `0x111e08`, the award
sites swapped, the class state store at `0x2735c0` and the `Dead` query at `0x111e04`;
for the knock animation name, the letter shifted by one and the prefix `knockdown2_`.
All 24 were rejected. The ignored log
`local/spells-r3/combat-r6-mutations.log` names the probe and the control script by
their sha256.

## 1. Hit direction `+0x2e0`

**Executed** (`tools/difftest_combat_r6.py:250-314`). Six attacker offsets, both
seeds. `Player_takeDamage` `0x1b5330` and `Creature_takeDamage` `0x116638` store

`+0x2e0 = s16(0x4000 − math_atan2_16(victim.x − attacker.x, victim.y − attacker.y))`

The stored half-word equals the `ref_core.atan2_16` oracle in every case (`:267`,
`:282`). Followed: `math_atan2_16` `0x166798` and its C library, `strcmp`, the
local-slot test and the handle pair. Stubbed, returning 0: the holy-shield search
(`0x3cf124`, `0x11a710`) and the jump-gate query `0x27dd68`.

- The player slot writes the angle only when an attacker is passed and the
  OR-ed flag word at `+0x2dc` lacks `0x800000` (store at `0x1b56dc`). With no
  attacker, or with that bit, the planted `0x1234` stays, nothing is stored, and
  `atan2` is not called (`:297`). The handle is still linked when the bit is set
  (`:301`). Unlike the creature slot, the player slot has no hit-point test
  (**Observed**, `0x1b56a0`).
- The creature slot writes it only while hit points are above 0. A creature
  already at 0 gets no angle and no link, and its hit points still drop (`:312`).

**What the angle means. Executed** (`:353-375`). It points from the attacker to
the victim: the direction of the push. `Creature_applyKnockback` `0x115eb8`, with
speed 30 and scale 1, passes `Creature_moveBy` the velocity
`(cos16(+0x2e0)·speed·scale, sin16(+0x2e0)·speed·scale, 0)`. That is the bit
pattern of `ref_core` `mul(cos16, speed)` times the scale. Its dot product with
`victim − attacker` is positive for all six offsets, for a player victim and a
creature victim. Followed: `cos16` `0x166630`, `sin16` `0x1666e0`. `moveBy` is a
stub that keeps the vector and returns 3.

**Who is linked at `+0x2e4`. Executed** (`:270`, `:762-801`). The handle names:

- the attacker;
- for an attacker with flag `0x80` (a projectile), the object behind its `+0x4c`
  handle, that is, the owner;
- for flag `0x10000000`, the object behind the victim's `+0x360` handle (the
  timed-effect source);
- the attacker itself when that handle is empty.

Both slots use this rule. Read in the player slot at `0x1b56e4-0x1b572c`; it is
the same rule as `docs/spec/creature-tick.md` 12.1.

**Player block. Executed** (`:316-351`). Facing 0, attacker 30 units ahead or
behind, pending damage planted at 3.0. In block state 8 or `0xb`, with flag `0x40`
clear, `Player_takeDamage` compares the facing vector with `attacker − victim`. In
front, the amount added to pending damage is 0, or half with flag `0x20000`. Behind,
it is the full 40. Flag `0x40` adds the full 40. Each case checks the store of
`3.0 + added` at `0x1b56a4`, and that the same call went on to store the angle and
link the attacker (`:344`, `:350`), so an early return cannot pass. Cases: state 8
front, front with `0x20000`, behind, and flag `0x40`; state `0xb` front, front with
`0x20000`, and behind. State 8 makes one shared-seed draw first, which chooses the
block animation (`0x1b548c-0x1b54b8`), on both the front and the back hit. State
`0xb` and flag `0x40` draw nothing. Also followed: `cos16`, `sin16`. Stubbed: the animation
`0x16ceb0`, `strcpy` `0x3b7ef0`, `res_find` `0x17365c`, the sound `0x214428`, and
`0x1b9658`.

**Blocking in `Player_processDamage`. Executed** (`:595-610`).
`rel = s16(+0x2e0 − facing +0x38)`. While blocking (state 8), `rel ≥ 0x6000` or
`rel ≤ −0x6000` lowers one knock level. The attacker is then in front, because
the angle points away from it. Boundaries `0x5fff` (kept), `0x6000` (lowered),
`−0x5fff` (kept), `−0x6000` (lowered), `0` (kept), `0x8000` (lowered). Facing
`0x6000` with angle `0x6000` is `rel` 0 and keeps the level.

The creature hit effect and gib directions also read `+0x2e0`
(`docs/spec/creature-tick.md` 3.2, 3.4, executed by `tools/difftest_creature.py`).
That was not re-run here.

## 2. Stagger

There is no damage-amount threshold. **Executed** (`:378-640`), `Player_processDamage`
`0x1b2cc0`, both seeds. The seed is planted so that the next draw has a chosen upper
half. Every callee is a stub returning 0 unless a case names it.

### 2.1 Surviving-hit roll (`0x1b3718-0x1b3830`)

This roll runs after the debit when record hit points are still above 0:

```
skip, with no draw: flag 0x400000, state 3 or 7, or +0x44c == 2
p    = max(0, 0.04 − 0.04 × record+0xdc)                 0.04 = 0x3d23d70a
one shared draw H (upper 16 bits)
stagger when float(H) < p × 65536, or the flag word has 0x4000000
stagger: state 3 unless the state is 6 or 10; +0x448 = g_frame 0x44fdcc;
         0x1b7ba8(slot, 0xc)
```

Executed limits: the largest staggering H is 2621 at resistance 0, 1966 at 0.25
and 1310 at 0.5. At that H the player staggers, and at H + 1 the state stays 2.
Both use exactly one draw (`:512-516`). Resistance 1.0 and 1.5 clamp the chance to
0 (`:523`). Flag `0x4000000` staggers at H `0xffff` (`:526`). The four skip cases
leave the seed unchanged (`:531`). States 6 and 10 draw but keep their state
(`:536`). A killing hit makes no roll (`:540`).

`+0xdc` is the item stagger resistance, the sum of modifier `0x1e` × 0.01
(`docs/spec/combat.md` section 7). **Inferred:** at resistance 0, a surviving hit
with no knock bit staggers with chance 2622/65536, about 4%.

### 2.2 Knock bits (`0x1b2d28-0x1b30c8`)

With any of `0x3c0000`, and a state other than 6 or 10:

```
level, speed from the first set bit: 0x40000 → 1, 100; 0x80000 → 2, 150;
                                     0x100000 → 3, 200; 0x200000 → 3, 250
rank   = player virtual slot 39 (skill rank) for skill 0x3e
chance = 0x30851c(*0x41b268, rank)                       = 5 × rank, no cap
one shared draw; resist = (H % 100) < chance
PvP mode A (0x4f711c): level − 1 and speed × 0.5; level 0 → no knock reaction
blocking (state 8) and the attacker in front: level − 1
level ≤ 1 → state 3 (light reaction)
level ≥ 2 → state 3, unless resisted
resisted  → +0x2e8 = 0; if object flag 0x20000 is clear, 0x308578(skill, object, animation, int(speed))
```

**Executed** (`:544-640`). Slot 39 (the rank) is a recorded stub returning 8. The
chance getter `SkillStrongStance_getStat0` `0x30851c` runs for real, after the
executable's skill start-up, with its two skill slots `0x3c88dc` and `0x3c85fc`.
The reaction `SkillStrongStance_trigger` `0x308578` runs for real with every callee,
except four fixture stubs: `pool_new` returns a zeroed block, the model's
sample-point count `0x1799c8` returns 8 and `model_getSamplePoint` `0x178e18` writes
(0, 0, 0), because the planted player has no model (with a count of 0 the real code
divides by zero at `0x3086b8`, as `docs/spec/skills-35-68.md` says), and `res_find`
`0x17365c` returns 0, so the phantom starts no clip. In these cases the library
`sprintf` `0x3b7ef0` is also a stand-in that copies its format. Followed as library
code, it left the buffer empty here (one of its callees, `0x3c0170`, lies past the
followed library range and is a stub), so the name `Player_processDamage` builds
with `sprintf` at `0x1b2f54` (prefix) and `strcat` at `0x1b2fd0` (suffix) lost its
prefix. The format seen is `knockdown1_`, with no conversion.

- The chance is 5 × rank for every rank 0 to 25: 5, 50, 100 at ranks 1, 10, 20, and
  125 at 25, so there is no cap (`:620-631`). This matches the **Observed** ladder in
  `docs/spec/skills-35-68.md` (StrongStance statistics).
- With rank 8 the chance is 40. A planted roll H with `H % 100` = 39 resists and one
  with 40 does not (`:549-552`). Slot 39 is asked for `0x3e`, and `0x30851c` gets
  `(*0x41b268, 8)` (`:562`).
- A resisted heavy hit keeps state 2, stores the speed and then 0, and gives no
  stagger feedback. Cases: `0x80000` (150), `0x100000` (200) and `0x200000` (250),
  so level 3 is covered too (`:556-583`).
- **Shared draws on a resisted heavy hit:** 4 for the player, 2 for the prediction
  copy (object flag `0x20000`). The four are the knock roll, the reaction's
  `LightEffect` and `StrongStancePhantom` (one `GameObject_ctor` `0x14cb10` draw
  each), and the surviving-hit roll. The probe checks that `0x308578` gets
  `(*0x41b268, player, name, speed)`, where name, read while the call is live, is
  `knockdown1_<letter>.anm` with the letter of the **Observed** rule in
  `docs/spec/skills-35-68.md` for hit angle minus facing (`b` at 0, `c` at −0x5fff in
  the block cases). It builds the light from a `0xbc` block and the phantom from a
  `0x3d8` block with `(block, player, name, speed, 0)`, the same name pointer, stores the
  phantom's `+0x2e8` = speed × 1.25, and moves the seed by exactly 2 between its
  entry and its return (`:469-494`, `:579`). The copy skips `0x308578` (`:577`).
  This is the count of `docs/spec/skills-35-68.md` (steps 2 and 4 of `0x308578`,
  one shared draw each). The receipt prints 4, 4, 4 and 2
  (`knock_resisted_draws_*`). If `pool_new` fails, that object and its draw are
  skipped (**Observed**, the null tests in `0x308578`); not run here. The count does
  not depend on the sample-point stub: the 25 particles draw the third generator
  `0x404468`, not the shared seed. It does rest on the `res_find` stub for the
  phantom: with 0 the phantom starts no clip, so its clip start
  (`anim_startBlendInOut` with a real clip) was not run. That part of the count,
  that the whole phantom construction makes one shared draw, is **Observed** only
  (`docs/spec/skills-35-68.md`, `0x308578` step 4).
- An unresisted one staggers, keeps 150, does not call `0x308578`, and makes one
  draw (`:585`).
- A light hit staggers even when the roll resists (`:591`).
- In PvP mode A, `0x40000` stores 50, does not change the state, and makes two
  draws. `0x80000` stores 75 and staggers with one draw (`:615`).
- While blocking, a hit from behind that is resisted keeps state 8 and makes the
  same 4 draws (`:607`).

The surviving-hit roll was held at chance 0 here (resistance 1.0). Its draw still
happens; it is the last of the counts above.

**Observed only:** with flag word `& 0xd`, object flag `0x20000` clear, and either
`g_decalDetail` `0x44fdc0` > 0 or a net game, a surviving hit makes one more shared
draw. When `& 7 == 0` it asks `pool_new(0x268)` for a gut chunk (`0x1b3248-0x1b32d4`).
These cases keep `& 0xd` at 0.

## 3. Kill credit

**Executed** (`:661-818`). Each case runs one or more original `Creature_takeDamage`
calls, then original `Creature_processDamage` `0x110d30`.

- Followed: `math_atan2_16`, the handle pair, `powf` `0x3a5ac8` with its C library,
  `player_getSkillRank` `0x1bf330`, and the slot-27 body.
- Recorded stubs: `player_giveExp` `0x1d3150`; `0x2f8e78`, which sets f0 to the
  case's fraction (0 unless named); `GameObject_rand` `0x1509d0`, which returns the
  case's draw; `pool_new`, which returns a zeroed block; `obj_getPropInt`, which
  returns 0 unless named; and slot 28.
- The creature has experience value 9000, maximum hit points 900 and 40 hit points.

Who gets the experience:

1. The killer is the object linked at `+0x2e4` (section 1). The link is rewritten
   only by a hit that lands while hit points are above 0. Case: player 0 hits for
   30, player 1's projectile lands 40, then player 0 hits the corpse. Player 1 keeps
   the credit (`:800`).
2. That object is compared with each record's object pointer `+0x43d8`. Slot 0
   wins if it matches, otherwise the last matching slot; no match is −1
   (**Observed** `0x111ec4-0x111f20`; executed only with distinct objects). A
   projectile credits its owner. Flag `0x10000000` credits the timed-effect
   source. An attacker that is a creature, or a projectile without an owner handle,
   gives no player killer (`:784`).
3. The awards reach `player_giveExp` as `(slot, amount)` in a0/a1. Every award call
   with one player is made from `0x1121e8`, and every award call with two players
   from `0x1120e4`; the probe checks the call site in each kill case (`:731-735`).
   `docs/issues/kill-loot-xp.md` steps 8 and 9 had the two sites swapped; that table
   is corrected (2026-11-09). The recorded amounts
   equal an independent oracle (`R.powf`, `ftoi`, the shares, and the cap from
   `g_expTable` `0x41b558` read from memory) (`:642-659`):
   - one player, level 30: `(0, 2202)`. That is the same for a player kill, a
     creature kill and a projectile kill, because this branch needs no killer
     (`:767`). A dead lone player gets nothing (`:774`).
   - two players, levels 30 and 34, killer slot 1: `(0, 304), (1, 457)`. With slot 0
     dead: `(0, 152), (1, 457)` (`:792-795`). No player killer: `(0, 381), (1, 381)`,
     for a creature attacker and for a projectile without an owner (`:790`).
   - class-0 mana +900/30: with one player it goes to that player (10 →
     `0x421fffff`, 39.999996); with several, only to the killer (`:768`, `:786`).
4. The kill orb uses the killer's own rank of skill `0x3b`. `player_getSkillRank`
   ran on a planted list `(0x3b, 4)` and `0x2f8e78` got `(*0x41b25c, 4)` (`:808`).
   With fraction 0.5, own draw `0x7fff` makes `pool_new(0xb8)` and
   `OniBall_ctor(block, position, facing, creature, 0)`, and `0x8000` does not
   (`:812-816`). The orb gets the creature, not the killer. The award does not
   change.

**Loot is not credited to the killer.** **Executed** (`:849-909`): the class
set-state's `Creature_dropLoot` call gets the creature in a0, a pointer to a copy of
its position in a1, its facing in a2 and 0 in a3, and the six floats of section 4.
All eight integer argument registers a0-t3 were recorded. None of them is the killer
object or its handle node, and for killer slot 1 none is 1. Between player 0's own
kill and player 1's projectile kill the probe compares all eight integer registers
a0-t3 (a0 as an offset from the creature, a1 as a value), the three words behind
a1 and f12-f17: they are identical. t0-t3 held 0, `0x864ea8` (the handle
free list, left over), 0 and 0 in both. The four integer and six float
arguments of the **Observed** signature (`docs/issues/kill-loot-xp.md` section 2,
step 3) all fit in registers, so there are no stack arguments. **Observed:**
`0x10f2c8-0x11075f` has no load of `+0x2e4` or of a record's `+0x43d8`. Its inputs
are listed in `docs/issues/kill-loot-xp.md` section 3. The rolls become world
objects (`docs/loot-drop.md` section 1). Gold is credited on contact
(`docs/loot-drop.md` section 6). **Inferred:** a drop belongs to whoever picks it
up, not to the killer. This note did not execute `Creature_dropLoot` or
`loot_generateDrops`.

## 4. Creature death path after hit points ≤ 0

**Executed** (`:820-924`), both seeds, same stubs as section 3.

- Slot 27 is called once, from `0x111de8`, with `(creature, 0x14)`. The base body
  `0x3c2688` stores `0x14` at `+0x232`. After that store, the flag word with
  `0x2000` is stored once, at `0x111e04`; the probe checks that pc (`:829`). The one
  `obj_getPropInt` call comes from `0x111e08`, with the creature and the name `Dead`:
  the `Dead` property query (`:838`). The flags end at
  `0x2129`: the planted `0x20`, plus `0x100`, `9` and `0x2000`. The award follows.
  Nothing is deleted in this function (`:827-840`).
- The `Dead` property (stub returns 1) calls `anim_snapTopToEnd` `0x170c80` once
  and gives no award. Creature flag `0x100000000` gives no award. The state is
  still `0x14` in both (`:843-848`).
- **The loot trigger is the class's slot 27.** With `Horsemen_setState` `0x272f4c`
  as slot 27 (followed), two players, and the killer either player 0 or player 1, the
  killing hit calls `Creature_dropLoot` once from `0x273314`, with the floats 36, 2,
  1.8, 0.6, 2 and 0.25 in f12-f17 (`:860`), and slot 28 (on death) once from
  `0x2733b0` with the creature (`:863`). The probe orders writes and calls on one
  clock (`:737-756`). The executed order is: `Creature_dropLoot`, slot 28, the
  set-state's own `+0x232` store of `0x14` at `0x2735c4`, the flag store at
  `0x111e04`, then the awards (`:879`). The state store is the only store of `0x14`
  at `+0x232`, its pc is `0x2735c4`, and the base body `0x3c2688` is not called, so
  the class body stores the state itself (`:869`). `Creature_dropLoot` and slot 28
  have no logged write between them (stack writes are not logged), so they share a
  clock stamp in all four runs; their order is the recorded call order, call index
  2 before 4, checked on its own (`:883`) and used to break the tie, never the event
  name. So with this class, loot and slot 28 come
  before the state store, not after it. Stubbed: `Creature_dropLoot` and slot 28
  (recorded), and the set-state's name lookup `0x10a9c0` and animation call
  `0x16cfe0` (return 0). `docs/issues/kill-loot-xp.md` section 2 lists the rest of
  that case.
- A corpse (state `0x14`) with more pending damage stores pending 0 and leaves
  `+0x2dc` unwritten (`0x11`). It makes no slot-27 call and gives no award (`:921`).

**Despawn. Executed** (`:926-993`):

- `Creature_deadUpdate` `0x1108a0` runs with every callee stubbed and
  `obj_delete` `0x14f200` recorded. The cases have creature flag `0x1000000`, the top
  clip finished (`+0x11a & 0x80`), a1 = 0 and a3 = 0. Body `+0x18` is 5. Four
  argument sets: f12 = 0 with a vector whose z is 7, and f12 = 20, 30 and 100 with a
  zero vector, as the monster classes pass them (`docs/monsters-2.md`, for example
  `Creature_deadUpdate(100, this, events, zero vector, 0)`). In all four, each call
  adds 0.35 (`0x3eb33333`) to `+0x2f4` and stores `+0x3c = +0x18 − sink`, not
  `vector.z − sink` (`:950`). The object flags are reset to `0x20` before each call;
  each call that does not delete leaves `0x4020`, so `0x4000` is ORed on every call
  (`:958`). When `+0x20 < sink`, it stores flags `0x4022` and calls
  `obj_delete(creature)`. With `+0x20` = 1.0 that is the third call in all four sets
  (`:954-960`). While the clip is still running, the sink is stored as 0. Without
  flag `0x1000000` there is no sink and no delete (`:974-976`).
- The `Creature_run` `0x112948` tail (`0x113bc8-0x113c08`) ran with every callee
  stubbed and a zero-filled virtual table. Flag `0x1000000`, active bit 63 clear
  and state `0x14` store flags `| 0x4002` and call `obj_delete` from `0x113c04`.
  With bit 63 set, or without flag `0x1000000`, that call is absent (`:991`).
- Creatures without flag `0x1000000` keep their corpse for the level
  (`docs/creatures.md` C5, **Observed** there). The raven or rat scavenger is
  `docs/spec/creature-tick.md` 4.11.

**Unknown:** what `+0x20` measures, what the `deadUpdate` arguments a1, a3 and f12
are (f12 = 0, 20, 30 and 100 did not change the sink; a1 and a3 were only 0), and
its branch without flag `0x1000000`. Monster classes call it, for example
from `0x234120` (**Observed** call sites).

## 5. The real cast body inside `Player_castSkill` `0x1a42b8`

**Executed** (`:995-1132`). IDs 16, 23, 49 and 55 ran at ranks 1, 5 and 20, and at
rank 5 with a target, on both seeds: 32 helper calls. The real cast slots
(`0x2ecfcc`, `0x2f8840`, `0x2de3bc`, `0x2e8cf8`) ran inside the helper on the
round-3 family rigs, whose named stubs answer the world. Every call target is real
or named (`:1084`). The helper, in order (**Observed**, `0x1a42e4-0x1a4690`):

1. Return when recast is positive, the ability is missing, or the ability name is
   not the `Skill` marker. Return for the prediction copy (object flag `0x20000`)
   unless the skill flag bit 0 is set.
2. Skill slot 1, can-use. Return on 0.
3. Aim origin: the midpoint of attach points 0 and 1 (`0x1754a0`). When that point
   is more than 58 above or below the player, its z becomes player z + 58. The C
   library's double helpers make that test.
4. Arc query `0x1614f0`, radius 340, with 20 and 0. The first candidate that passes
   player slot 20 is the target. Its heading is
   `s16(0x41c2 − atan2_16(target.x − player.x, target.y − player.y))`. With no
   target, the heading is the player's facing.
5. Rank from player slot 39, then **skill slot 2 (skill, rank, player, aim, heading)**.
6. A non-zero result is the spell. For the copy, spell slot 1 is called with 3.
   Otherwise `0x11a838(player, spell)` attaches it. A skill of kind 1 also links
   `player+0x588` (`0x1a4600`).
7. Recast: `+0x4ae = skill+0xc` (`0x1a4610`).
8. Rank again, then the cost (skill slot 5). Kind 1 multiplies the cost by 1/60.
   The debit to record `+0xc0` is at `0x1a4690`. The arc list is cleared.

What the probe compared:

- At the cast entry, mana is the planted 1000 and recast is 0, so nothing has been
  paid. The arguments are skill, rank and player (`:1089-1090`).
- With no target, the heading is the player's facing. With a target, it is the
  `0x41c2` formula against the `ref_core` oracle (`:1095-1098`).
- At the cost getter's entry, recast is already 30 and mana is still 1000
  (`:1099`). There is exactly one recast store at `0x1a4610`, then one debit store at
  `0x1a4690` of `fsub(1000, cost)`, with the cost from the separately executed
  getter (`:1102`). There is no kind-1 link (`:1106`).
- IDs 16 and 23 return 0, so nothing is attached. The bolt's level field equals the
  rank, its velocity is `(cos16, sin16)(heading) × 450` (ID 16) or `× 350` (ID 23),
  and it is scheduled with `obj_runEveryFrame` (`:1108-1117`).
- IDs 49 and 55 return the spell. `0x11a838` gets the player and the first block
  the cast asked of `pool_new` (`:1121`). At the entry of `0x11a838`, mana is
  still 1000 and recast is still 0, so the attach comes before the recast store
  (`:1124`). The ID 55 spell's `+0x1c` equals the round-4 heal product (`:1131`).

So nothing happens between the debit and the effect. The effect object is built
first. Between the cast's return and the debit, the helper does only the attach
(or the copy's slot 1), the recast store, a second rank query and the cost getter.
The later ticks of these spells are in `docs/spec/player-spells-projectiles-r3.md`
and `docs/spec/player-spells-support-r3.md`.

## What a client can implement from this note

- On a hit with an attacker, store `+0x2e0 = s16(0x4000 − atan2_16(victim − attacker))`.
  A creature does this only while its hit points are above 0. A player does it
  unless the flag word has `0x800000`. Push knock-back along `(cos16, sin16)(+0x2e0)`.
- Link `+0x2e4` to the attacker, to a projectile's owner, or to the timed-effect
  source for flag `0x10000000`. A creature relinks only while its hit points are
  above 0.
- Player block (state 8 or `0xb`, no flag `0x40`): from the front, add 0 (half with
  `0x20000`); from behind, add the full amount. State 8 makes one shared draw either
  way; state `0xb` draws nothing. The angle and the link are still made.
- Player stagger on a surviving hit: one shared draw against
  `max(0, 0.04 − 0.04 × resistance) × 65536`, or forced by `0x4000000`. Skip it
  for flag `0x400000`, states 3 and 7, and `+0x44c == 2`. States 6 and 10 draw but
  keep their state.
- Knock bits: the level and speed table above; skill `0x3e` roll `(H % 100) < chance`
  with chance = 5 × rank from `0x30851c` (executed, ranks 0 to 25) resists a level-2
  or level-3 hit; a front block or PvP mode A lowers one level, and PvP mode A halves
  the speed. A resisted knock zeroes the speed. For the player (not the prediction
  copy) it also runs `0x308578`, which makes two more shared draws: a resisted heavy
  hit costs 4 shared draws in all, 2 for the copy. The two inner draws need both
  allocations to succeed. The phantom's draw with a real clip is **Observed**
  (`docs/spec/skills-35-68.md`, step 4); here `res_find` was a stub returning 0.
- Creature death: slot 27 with `0x14`, then flag `0x2000`, then experience by the
  section 3 rules, with `player_giveExp(slot, min(amount, cap))`. A class's own
  set-state (executed for `Horsemen_setState`) drops the loot and calls slot 28
  before it stores the state. Loot is not credited to the killer: no `dropLoot`
  argument names it (executed). **Inferred:** a drop belongs to whoever picks it up.
- Despawn only creatures with flag `0x1000000`. Sink 0.35 per `deadUpdate` once the
  death clip ends, from `+0x18`, and delete past `+0x20`. Executed with a1 = a3 = 0
  and f12 = 0, 20, 30 and 100 only. Also delete in `Creature_run` when the creature
  is inactive and in state `0x14`.
- Cast: aim, then the cast slot, then attach, then recast, then the debit, in that
  order.

## Still open

- The meaning of `+0x44c` (planted here). The reaction `0x308578` ran with four
  fixture stubs (allocation, the model's sample points, `res_find`) and a `sprintf`
  stand-in in its caller; its particle and
  phantom effects beyond the shared draws and the phantom's speed were not compared.
  The skill `0x3e` rank itself (player slot 39) is a stub here.
- Player-victim kill credit. **Observed only:** in PvP mode B, `0x305580(slot,
  killer)` or `0x305650(slot)` is called. In PvP mode A, a class-0 player killer
  gains a third of maximum mana, and a player killer gets a LifeTap orb roll on
  the shared seed at three times the fraction (`0x1b3588-0x1b3714`).
- The `Player_takeDamage` branch for record byte `+0x4c27 > 0`, which adds no
  damage and sets bit 0 of `0x41b930[slot]` (**Observed**, `0x1b5438-0x1b5760`).
- The holy-shield split, the gut-chunk roll in `Player_processDamage`, and
  `Creature_dropLoot` / `loot_generateDrops` themselves. The last two are covered
  by `docs/issues/kill-loot-xp.md` section 3 and `docs/loot-drop.md`, not run here.
- Live reachability on a console, and anything between two machines.
