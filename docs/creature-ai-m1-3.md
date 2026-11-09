# Creature AI for missions 1–3 (SLUS_209.73 US v2.00)

Research date 2026-11-09, branch `t3/research-campaign-combat`. **Status: MORE.**
The per-tick decisions of every hostile class that missions 1–3 place are
executed and compared on both seeds. Live movement, animation timing, pathing and
landed player damage are not established here.

Fix round 2026-11-09 (audit CAI-1..CAI-10): the walk now runs the full context
grid instead of a sample, with count answers and clock fields at and around each
threshold, an HP pass and both tick exits, and prints model line coverage. One
boundary moved: the WarWraith dead-state delete is at a stored fade ≥ 100 (§3.2).
The `hitAtReach` distance is now executed on all three axes, and both radii (§2.5).
Claims that are still not executed are labelled Observed.

Labels: **Executed** = an original function ran in `tools/ee_emu.py` and was
compared with an authored model (always on a synthetic object, with the stubs
named next to the claim). **Observed** = read in the executable or a prior note,
not run here. **Inferred** = a conclusion from those. **Unknown** = still open.
Addresses are EE virtual addresses. No disassembly, decompiler output, game text
or game bytes are included. Level contents are given as record counts only.

## 1. Which creatures a player meets

**Executed** (`check_levels`, `tools/difftest_creature_ai_m1_3.py:374-407`):
every record of the eleven level archives is parsed, the per-level totals and the
creature counts below match `tools/ref_creature_ai_m1_3.py:19-46`, and the
original factory `0x159c94` picks the listed pool size and constructor for all
**807** creature/hazard records (allocation and constructors stubbed). The run
order is shuffled per seed. The property-**key** counts named in the table and
in §3.13 are asserted too (`KEY_COUNTS`, `tools/ref_creature_ai_m1_3.py`; key
names only, no values): one `drundar` Ogre and both `islc2` SeaMonsters have
`miniboss`; of the two `drunarm` `RalosZek` records one has `visualarc` and
`dropitem` and no `wait`, the other `wait` and neither of those.

| Mission / level | Records | Creature records (count) | Class (constructor) |
|---|---:|---|---|
| 1 `blood1` | 363 | `Kobold` 118, `Koboldtough` 8, `koboldshaman` 5 | Kobold (`0x27f0c0`) |
| | | `WarWraith` 9 | WarWraith (`0x2c07a8`) |
| 1 `strife` | 283 | `Orc2Soldier` 43, `Orc2Archer` 20, `Orc2Leader` 2, `Orc2Leader1` 2, `Orc2Shaman` 2 | Orc (`0x2a0954`) |
| | | `Catapult` 2 | Catapult object (`0x24d440`) |
| 1 `drundar` | 270 | `GoblinSoldier` 39, `GoblinArcher` 23, `GoblinRecruit` 9 | Goblin (`0x26a624`) |
| | | `Ogre` 14 (one has a `miniboss` key) | Ogre (`0x29fad0`) |
| 1 arena `drunare` | 39 | `UndeadKnight1`–`4` 1 each, `CazicAvatar` 1, `RalosZek` 1 | Horsemen (`0x271c70`), Cazic (`0x24a670`), Zek (`0x2c1f94`) |
| 1 arena `drunarm` | 302 | `GladiatorBare` 82, `RalosZek` 2, `Catapult` 4 | Warrior (`0x2bafb4`), Zek, Catapult |
| 2 `innovat1` | 297 | `clockworkhammer` 29, `clockworkcutter` 23, `Rat` 36, `Seagull` 30 | Clockwork (`0x24e124`), Critter (`0x2547fc`) |
| 2 `inmine1` | 213 | `clockworkcutter` 23, `clockworkhammer` 23, `Droid` 30 | Clockwork, Droid (`0x27b840`) |
| 2 `inmine2` | 118 | `clockworkcutter` 20, `clockworkhammer` 14 | Clockwork |
| 2 `innovat2` | 71 | `IronGuardian` 1, `Rat` 8, `Seagull` 12 | IronGuardian (`0x27a00c`), Critter |
| 3 `islc1` | 262 | `Froglock` 46, `Crab` 39 | Froglock (`0x263e1c`), Critter |
| 3 `islc2` | 255 | `Amphian` 37, `Crab` 44, `SeaMonster` 2 (`miniboss` key) | Amphian (`0x234584`), Critter, SeaMonster (`0x2a428c`) |

`Rat`, `Seagull` and `Crab` records all carry a `critter` key and become the
ambient Critter class (**Executed** factory selection). The skeleton that the
fourth knight summons (Skelight) is created at run time, not placed.

## 2. What is shared by every class

### 2.1 Per-tick entry

**Executed** for all twelve classes in §3 (event list compared on every answer
path, `walk` in `tools/difftest_creature_ai_m1_3.py`): the class run
function (vtable slot 4) calls `Creature_processDamage` `0x110d30`,
`Creature_run` `0x112948` (nonzero return ends the tick), `Creature_updateActive`
`0x10c0f0` (zero ends the tick). Both exits are executed in every state of every
class variant: with `Creature_run` stubbed to 1 the tick makes no call after it,
and with `updateActive` stubbed to 0 none after that (the "exit" contexts;
model `entry()` in `tools/models_creature_ai_m1_3.py`). Then — in class order — the weapon-holder update
(holder table word `+0xac`), `Creature_stepAnim` `0x1162b0` (scale 1.0; its result
is the animation-event mask `ev`), `Creature_applyKnockback` `0x115eb8` with the
class scale, and slot 23 target pick with force 0, then the state switch. The
knock-back scale per class is pinned in `head()` calls
(`tools/models_creature_ai_m1_3.py`): Kobold 1.0, WarWraith 0.0, Orc 0.4,
Goblin 0.5, Ogre 0.1, Warrior 0.4, Clockwork 0.4, Droid 1.0, IronGuardian 0.0,
Froglock 0.5, Amphian 0.5, SeaMonster 0.2. WarWraith picks its target **before**
the knock-back step and skips the pick once dead. Kobold and the goblin shaman
also call slot 24 (pick ally) every tick.

### 2.2 Target choice, notice range and leash

**Observed, asserted against the executable image** (`check_slots` in
`tools/difftest_creature_ai_m1_3.py` reads the vtable words of the loaded image;
no code runs there): in all twelve class tables slot 23 is the base
`Creature_pickTarget` `0x10ded0`, slot 24 the base `Creature_pickAlly` `0x10e2c0`
and slot 25 the base `Creature_canSeeTarget` `0x10e658`; slot 2 is the base
`Creature_takeDamage` `0x116638` except Orc (`0x2a2eac`, a tail call to the base).
Slot 21 is overridden only by Kobold (`0x280434`) and slot 20 only by WarWraith
(`0x2c1bc0`). **Executed** for slots 23, 24 and 25: the walked run calls reach
those three addresses (they are recorded by address as `pickTarget`, `pickAlly`
and `sight`).

**Observed, reused** (not re-executed here; `research-boar-ai` `3f81c89`
`docs/issues/warboar-ai-handoff.md`, "Perception, aggro and home range", and
`docs/spec/creature-tick.md` 6): the pick scans a grid box of ± HomeRange on
staggered 32nd frames; candidates are scored by slot 20 (team/flag rules), +1
for the last attacker and +1 for the current target, ties by XY distance; when not
damaged in the last 480 frames a candidate beyond HomeRange is refused under the
documented leash test. Base defaults: HomeRange 1000, pointblank range 300,
visual range 500, visual arc `0x4000`; slot 25 first tests the point-blank
circle, then the facing cone. **Observed** class overrides of HomeRange:
WarWraith 600, IronGuardian 3000 (`docs/monsters-2.md:6199`, `:1355`).

**Observed** special pickers: WarWraith slot 20 gives a victim to at most one
wraith and clears the farther wraith's target (`docs/monsters-2.md:6175-6185`);
Kobold slot 21 treats only a `koboldshaman` as an ally (`docs/monsters-2.md:4981`).
Neither override was executed in this round (**Unknown** by execution).

### 2.3 State requests and the base filter

**Executed** (`check_filter` in `tools/difftest_creature_ai_m1_3.py`): each
class setState first runs `Creature_filterState` `0x10a9c0` (executed for real
with `isNotRooted` `0x1195e0`, `isAttackReady` `0x1195f0`, `isNotStunned`
`0x119608`). Under every class: root timer `+0x314` turns a chase request into 5
with a target and 0 without one, but keeps 6; stun timer `+0x31c` turns it into
0x13; attack cooldown `+0x318` turns it into 0x10 with a target and is cleared to
0 without one; request 0x14 clears `+0x314/+0x318/+0x31c`. Droid stores 0 for a
kept 6 (no case).

States a class has no case for are stored as 0 (**Executed**,
`SET_ENTRY` landings in `tools/models_creature_ai_m1_3.py`): Kobold 4,
0xa, 0x11; Ogre 4, 0xa, 0x11, 0x17; Warrior 4, 0x11; Clockwork 4, 0xa, 0x11,
0x17; Droid 4, 6, 0xa, 0x11; IronGuardian 4, 0x11, 0x17; Amphian 4, 0xa, 0x11.

### 2.4 Flee, cooldown, hit reaction, stun, death

**Executed** for all classes: entering 0x10 stores attack cooldown `+0x318 = 60`
(SeaMonster does not: its setState(0x10) is asserted to write no `+0x318`); state
0x10 calls `isAttackReady` and requests 0 when ready, otherwise
`Creature_fleeFromTarget` `0x119f08`. This is cooldown-driven retreat.
**Executed** (HP pass): no class run function here reads hit points into a flee
or any other decision except Amphian's block (§3.11). Every state of every class
variant was walked with hit points `+0x228` 10, 49, 50 and 51 of maximum `+0x22c`
100 (three contexts each), and with 100 of 100 in the grid; a hidden HP test would
show as a mismatch. Scope: `Creature_processDamage` and the base `Creature_run`
are stubs here, so an HP rule inside them is not covered (**Unknown**).
0x12 waits for animation flag `0x10` (Goblin `0x30`) to clear; 0x13 waits
for `isNotStunned`. Death 0x14: `Creature_deadUpdate` `0x1108a0` with the class
corpse distance (Kobold 20, Orc 30, Goblin 20, Ogre 30, Warrior 20, Clockwork 20,
IronGuardian 30, Froglock 25, Amphian 20, SeaMonster 30); setState 0x14 calls
`Creature_dropLoot` `0x10f2c8` and slot 28 `0x10beb8` (WarWraith calls
`loot_generateDrops` `0x100d54`; Droid only slot 28, and its setState 0x14 and
0x17 are asserted to call neither `dropLoot` nor `loot_generateDrops`). Loot
callees are stubs.

### 2.5 From attack to `damage_apply`

**Executed** (`check_hits` in `tools/difftest_creature_ai_m1_3.py`, 81
cases a seed; `damage_apply`, sight, `Creature_isEnemy` `0x119328` and the grid
collect `0x14a928` stubbed; `math_cos16/sin16` executed):

- `Creature_hitTargetInArc` `0x119938` (c, facing, arc, min, max, rating,
  flags, descriptor; near, far): one `creature_canSeeObj` `0x10c810` on the
  target with that arc and range; if it passes, one `damage_apply` `0x1e8230`.
  No target, no call.
- `Creature_hitTargetAtReach` `0x1196e8` (c, min, max, rating, flags,
  descriptor; reach): no sight test. Hits when the distance of the target centre
  (`+0x10/+0x14/+0x18`) from the attacker position + facing × reach is **below
  60 on all three axes together**. Executed boundaries: 59.9 hits and 60.0 misses
  along `+0x10` and `+0x18` (reach 36 and 60); 59.9 hits and 60.1 misses along
  `+0x14` either way; two-axis 59.40 / 60.10 and three-axis 59.93 / 60.10; an
  attacker raised by 10 on `+0x14` moves that window to −49.9 … 69.9. Target
  radius 5 / 40 and attacker radius `+0x1c` 5 / 60 do not change the result. A
  target with object flag 8 is skipped (0x40 is not); what flag 8 means is not
  established here. Exactly 60.0 along `+0x14` still hits; **Inferred**: at
  facing 0 the reach point is not exactly on the `+0x10` axis (the sine
  value is not exactly 0), so that boundary is asserted at 60.1.
- `Creature_hitAllEnemiesInArc` `0x119b58`: collects up to `0x80` candidates,
  then per candidate `isEnemy` and `canSeeObj`; one `damage_apply` per passing
  enemy (only the enemy candidate in the probe).
- Every call passes `damage_apply(victim, attacker, rating, 0, 0, flags,
  descriptor)` with min and max converted to floats in f12/f13.

**Observed, reused**: `damage_apply` applies armour for a player victim (or
anyone in PvP mode A): each endpoint cut by armour/30, at least half
(`docs/spec/combat.md:95`, with the executed mitigation row at `:420`); then the hit
roll and descriptors. Knock-back (`research-spells-r3` `1e764d4`
`docs/spec/player-spells-numeric-r3.md`, "Knock-back"): a player victim adds to pending
damage in `Player_takeDamage` `0x1b5330`, and `Player_processDamage` `0x1b2cc0`
subtracts it and sets knock-back speed 100/150/200/250 for the first of flag bits
`0x40000/0x80000/0x100000/0x200000`. So the flags below decide the knock-back a
player feels: e.g. Kobold tough `0x440008` → 100, Ogre crush `0x80001` → 150,
Ogre shield-bash `0x100001` → 200. Real stat values (`+0xd0/+0xd2/+0xd4`) come
from balance scaling and are **Unknown** for live actors (probes used 11/22/33).

## 3. Class state machines (Executed decision order)

How the walk works: the class run executes; each listed query is answered from
an answer list and the probe follows every answer path depth-first. Boolean
queries are answered 0/1. Ally counts are answered 0, 1, 2 and 3, and the
`0x108970` box count 0, 2, 3 and 4. So `> 0`, `> 1`, `> 2`, `== 0`, `< 2`, `≥ 1`
and `< 3` each meet a value on both sides of the threshold.

Context is the **full grid**, not a sample. It covers: target present or not;
every class `ev` value; animation flags `+0x11a` 0/8/0x10/0x80; deadline
`+0xf4` 50, 99, 100, 101 and 150 against clock 100 (Orc adds 0, 1, 2); ally
present or not (Kobold); and every class variant. Boundary variants put the
clock-compared fields at 99/100/101: WarWraith `+0x3cc`, Orc shaman `+0x47c`,
goblin shaman `+0x3d8`, Droid `+0x3cc` and IronGuardian `+0x3cc`. They also
cover the IronGuardian counter at 119/120/121, the WarWraith fade at 98/99 and an
IronGuardian run with the alive-player count `0x4f8420` at 1. An equality case is
therefore run for every `>`/`≥` and `<`/`≤` test listed below.

Rare own-generator branches are driven too. The whole grid is repeated with seeds
whose first own draw, and then whose first two own draws, are multiples of 60
(the "draw" contexts). So every `% n == 0` and `& 3 == 0` test in a first or
second draw passes at least once, and the ordinary seeds cover the other side.

On top of the grid, each state also gets the HP pass (§2.4; Amphian at eight
HP points, §3.11) and the two tick exits (§2.1).

Within one variant/state/target/`ev`/ally group, a grid context whose animation
flags and deadline agree with an executed one on every field that executed run
**read** (on any answer path) is the same executable run. It is not executed
again: its recorded events are compared with the model evaluated on the new
context ("replayed model paths"). A field the code never read cannot change
the run, so the model is still checked at every grid point.

Model line coverage over all compared paths is printed per class (`COVER`).
An unreached model line fails the run unless the line is marked "not walked"
(none are). Compared per path: query arguments, slot-27
requests, hit-helper arguments, movement calls and the final own-generator state
(`GameObject_rand` `0x1509d0` executed). Not compared: holder calls, zero-velocity
`moveBy`, `settle`, math and effect calls, field writes. `see(n,f,arc[,ray])` is
`Creature_canSeeTargetIn` `0x118d40` (false without a target); `cone` is
`creature_findEnemyInCone` `0x10cf78`; `sight` is slot 25. "Request" = slot 27.
Totals per seed are in §5.

Common to all: state 0 idle, 1 wander (`Creature_moveToDest` `0x119f38`), 3 chase
(`Creature_moveToTarget` `0x1143e8`, `Creature_turnToTarget` `0x1187e0`), 5
between attacks, 6–10 attacks, 0x10 flee, 0x12 hit reaction, 0x13 stunned,
0x14 dead, 0x17 class-specific.

### 3.1 Kobold — run `0x27f52c`, setState `0x27ff6c` (model `kobold()` in `tools/models_creature_ai_m1_3.py`; notes `docs/monsters-2.md:4964-5050`)

Variant `+0x3cc`: 0 Kobold, 1 tough, 2 shaman.
- 0: `sight` → 3; `away` (`0x10eed8`) or clock > `+0xf4` → 1. 1: `sight` → 3;
  clock > `+0xf4` → 0 **without moving that tick**; else move to destination.
- 3: no target → 0. Tough: `alliesNearTarget(24) > 2` (2 stays, 3 goes) → 5; `targetCharging` and
  see(0,24,6000) → 7; see(0,24,6000) → 5; see(0,24,0x7fff) → turn; else move.
  Shaman: see(0,24,6000) or see(0,164,5000) → 5; see(0,164,0x7fff) → turn.
  Kobold: see(0,24,6000) → 5; any-angle → turn; else guard logic (`0x119180`
  in-guard-spot → 5; `0x119128` ally-sees-target → guard point + `moveTo`;
  else move).
- 5: no target → 0; turn; see(0,24,6000) → 6; tough stays while rooted or > 2
  allies near; shaman: corpse(200) → 8, else stays while rooted or see(0,200,5000);
  Kobold: rooted stays, no ally → 3, out of the guard spot → 3.
- 6: target and `ev&1` → hitInArc(0,24,6000, flags `0x440008` tough else 8); turn
  with a target; clip over → 5. 7 (tough vs charger): `ev&1` flags `0x80001`,
  `ev&2` flags 1. 8 (shaman): on `ev&1` searches corpse and wounded ally **even
  without a target**; corpse → revive (`0x10bfc8`), else wounded → Healing cast
  (skill table word `+0x14`) and `creature_addSpell`. State 9 is never requested
  by the run (not walked; its FrostArmor cast needs an outside request — Unknown).
- 0x12 → 3; 0x13 → 3; 0x17 → 3 when flag `0x10` clears.
- Entry (**Executed**, `SET_ENTRY`): 0 `+0xf4 = clock + r%120`; 1 `clock + 120 +
  r%120`; 5 `clock + 60 + r%120`; 6/7/8/0x17 store last attack in `+0x3c8`.

### 3.2 WarWraith — run `0x2c0c2c`, setState `0x2c1648` (model `warwraith()`; notes `docs/monsters-2.md:6121-6274`)

- Head: when fade `+0x3c8` ≥ 99 it also turns to the target (98 does not).
- 0: `sight` → 3; clock > `+0xf4` → 1. 1: `sight` → **0**; else move to destination.
- 3: no target → 0; see(0,20,6000) → **7 if clock > `+0x3cc` else 6** (`+0x3cc`
  99 → 7; 100 and 101 → 6); otherwise
  see(0,20,0x7fff) is asked and it turns (out of range it also flies straight,
  writing the position — not compared). 5: no target test; same attack choice;
  else not rooted → 3.
- 6: target and `ev&1` → hitAtReach(36, flags 8, holder descriptor). 7 drain:
  target and `ev&1` → ColdWeapons value (skill table word `+0x5c`), then
  hitAtReach(36, flags `0x404`); a nonzero result heals max HP/15 (write, not
  compared). Turns with a target; clip over → 3.
- 0x11: clock > `+0xf4` → 3; 0x13 → 0. 0x14: a tick that starts with fade ≥ 100
  calls `obj_delete` `0x14f200`. Otherwise it emits one particle (an angle draw
  plus a unit-ball rejection point); fade 98 and 99 both take the particle path
  (corrected 2026-11-09 from "fade + 1, at 100 delete"). The fade write itself
  is not compared.
- Entry: 0 `+0xf4 = clock + r%120`; 7 `+0x3cc = clock + 300 + r%120` (so the
  first attack of a fresh wraith is the drain); 0x11 `clock + 120 + r%60`.

### 3.3 Orc — run `0x2a1848`, setState `0x2a323c` (model `orc()`; notes `docs/monsters-2.md:5271-5491`)

Variant `+0x478`: 0 recruit, 1 soldier, 2 leader, 3 leader1, 4 archer, 5 shaman.
- 0/1/2: archer first asks `sight(1)` (forced), everyone `sight(0)`. 0 → 3 on
  sight; else clock > `+0xf4` or `away` → 1. 1 → 3 on sight, else move.
  **2 (run to an alert point): a plain sight requests 0, a forced archer sight 3**
  (`orc()`); `moveToDest` returning 0 → 0.
- 3 melee: see(0,30,6000) → 6; any-angle → turn; soldier/leaders with
  `alliesNearTarget(30) > 0` (1 goes), recruit with > 1 (1 stays, 2 goes) → 0x17;
  recruit/soldier: own draw %30 == 0 and fewer than 3 in `0x108970` (2 goes, 3
  stays) → 4 (rear approach; geometry fixed in
  the probe); else move. Archer: see(0,80,0x7fff) → 0x10; see(0,400,6000,ray 1) → 6;
  else move. Shaman: see(0,400,6000,1) → 6; see(0,30,6000) → 7; see(0,6000,0x7fff)
  → turn; else move.
- 4: no target → 0; see(0,30,6000) → 6 or any-angle → turn, and **in the same
  tick** one own draw and `moveToTarget` still follow.
- 5: melee see(0,30,6000) / ranged see(0,400,6000,1) → 6, then `notRooted` → 3 in
  the same tick.
- 6: melee with a target: `ev&3` → hitAtReach(36, `0x40008`), and on `ev&1` own
  draw %5 == 0 → 3; turns while the clip plays. Archer with a target:
  `leadTargetPoint`, `ev&1` → unit-ball spread, sound draw, one missile pool block.
  Shaman with a target on `ev&1`: see(0,80,0x7fff); if not near, corpse(400) and
  wounded(400); corpse → revive; wounded → Healing (`+0x14`) + addSpell; else own
  draw %3 == 0 → PoisonRain object, otherwise Shock (`+0x14`). Then the stand
  counter `+0xf4`: **decremented only once the clip has ended but tested every
  tick** (`orc()`, state 6); ≤ 0 → shaman draws and requests 0x17, others 3.
- 7 (shaman melee): `ev&1` → hitInArc(0,30,6000, flags 1); clip over → 0x17.
- 0x11 block: clock > `+0xf4` → 3. 0x13 → 0. 0x17: shaman: clock > `+0x47c` → 3
  (`+0x47c` 99 → 3; 100/101 stay), else see(0,30,6000) → 7, else
  **see(0,6000,0x7fff) → an extra turn** (new 2026-11-09: never reached before,
  when `+0x47c` was always 0); archer turns; soldier/leaders: any-angle see or no
  allies → 3; recruit: see(0,30,6000), clock > `+0xf4` or allies < 2 (1 goes, 2
  stays) → 3; turns with a target.
- Entry: 0 `clock + 120 + r%60`; 4 `clock + 40 + r%120`; 6 `+0xf4 = 10 + r%10`;
  0x11 `clock + 120` and cflag `0x200`; 0x17 `clock + 240 + r%240`.

### 3.4 Goblin — run `0x26b27c`, setState `0x26ccfc` (model `goblin()`; notes `docs/monsters-2.md:3763-3991`)

Role `+0x3d4` as Orc (0–5). Matches the class note, with: turns in 6 only with a
target; states 7 and 8 (bow shot, shaman cast) were **not walked** (projectile and
cast bodies; Unknown here).
- 0: archer `sight(1)` or `sight(0)` → 3; `away` → 1. 1: archer `sight(1)` → 0,
  `sight(0)` → 3. 2: either → 0; `moveToDest` 0 → 0.
- 3: archer: see(0,80,0x7fff) → 0x10, see(0,400,6000,1) → 7, else move — and then
  **also** the melee block below in the same tick. Shaman: see(0,60,0x7fff) →
  0x10, see(0,400,6000,1) → 8, else move (returns). Melee block: see(0,30,6000)
  → shield (`0x26d7e4`) and `targetAttacking` and own draw %3 == 0 → 0x11, else 6;
  any-angle → turn; role > 0 and `allyInLineOfFire` → 0x17; own draw %30 == 0 and
  box count < 3 (2 goes, 3 stays) → 4; else move.
- 4: see(0,30,6000) → 6; else draw + move. 5: no target → 3; ranged → 7/8; melee →
  6; else `notRooted` → 3. 6: target and `ev&3` → hitAtReach(36, `0x40008`), `ev&1`
  and draw %5 == 0 → 3; clip over → 3.
- 0x17: shaman: see(0,60,0x7fff) → 0x10, clock > `+0x3d8` → 3 (99 goes, 100/101
  stay); others: clock >
  `+0xf4` or no ally in the line of fire → 3; turns.
- Entry: 0 `clock + 120 + r%60`; 4 `clock + 40 + r%120`; 0x11 `clock + 120` and
  cflag `0x200`; 0x17 `clock + 240 + r%240`.

### 3.5 Ogre — run `0x29fe50`, setState `0x2a060c` (model `ogre()`; notes `docs/monsters-2.md:5175-5224`)

Executed exactly as the class note; last attack `+0x460`.
- 0: `sight` or `away` → **1** (not 3). 1: `sight` → 3, else move.
- 3: see(0,60,2000) → 5; last not 8/9 and see(0,60,0x7fff) → 9; not charging and
  any-angle → turn; see(0,120,2000) and allies near > 0 → 5; else move.
- 5: in (0,60,2000): last not 8/9 and draw %3 == 0 → 8; last not 7 and
  `blockedByTarget` and draw %3 == 0 → 7; else 6. Out of range and not rooted:
  outside (0,156,2000) and draw %60 == 0 → 3; then draw %60 == 0 and no ally near → 3.
- All hits `hitAllEnemiesInArc(0,60,6000)`: 6 `ev&1` flags `0x40001`; 7 `ev&1`
  **literal damage 1–5** flags `0x100001`; 8 `ev&1` flags 1 else `ev&4` flags
  `0x80001`; 9 turns, `ev&5` flags 1. Clip over → 3.

### 3.6 Warrior (`GladiatorBare`) — run `0x2bb640`, setState `0x2bc320` (model `warrior()`; notes `docs/monsters-2.md:6464-6582`)

Fields: combo count `+0x474`, blocking-seen `+0x478`, last opener `+0x470`.
- 0: `sight` or `away` → 1. 1: no sight → move; else turn and see(0, visual range
  `+0x3ae`, 8000) → 3.
- 3: see(0,12,8000) → 5; not charging and see(0,36,8000) → 5; not charging and
  any-angle → turn; see(0,120,8000) and allies near ≥ 1 (0 stays, 1 goes) → **pickTarget(1)** and 5;
  else move.
- 5: see(0,36,8000): `targetAttacking` and draw %3 == 0 and can-block (`0x2bc7c8`)
  → 0x17, else `blockedByTarget` then draw even → 8, odd → 6. Any-angle → turn.
  Not rooted: see(0,156,8000) is asked **every tick**, allies only when the 1-in-60
  draw hits; draw 0 and not (near and allies) → 3. Then clock > `+0xf4` → a
  flourish draw.
- 6/8 openers, 7 follow-up: turn; `ev&1` → hitInArc(0,36,8000) flags 8, or
  `0x440008` at combo 3 / `0x100008` at combo 5 when no ally is near. `ev&2` chain
  window with see(0,36,8000): from 7 → the other opener (`+0x470` 6 → 8, else 6);
  from 6/8 with combo < 5: combo 1 → 7 when blocking or an **even** own draw;
  combo > 1 → 7 only when blocking. 9/10 turn every tick (9 also hits on `ev&1`)
  and → 3. 0x17 → 3 at clock > `+0xf4`.
- Entry: 0 `clock + r%120`; 3 clears `+0x474/+0x478`; 5 `clock + r%360`; 6/8
  store `+0x470` and count +1; 0x17 `clock + 60 + r%120` and cflag `0x200`.

### 3.7 Clockwork (cutter/hammer) — run `0x24e758`, setState `0x24f90c` (model `clockwork()`; notes `docs/monsters-2.md:3650-3751`)

Sub-kind `+0x3c8`: 0 cutter, 1 hammer.
- 0: `sight` or `away` → 1. 1: as Warrior (visual range, arc 8000) → 3.
- 3: see(0,36,8000) → 5; see(0,280,16000) → 9 (charge); else move.
- 5: in (0,36,8000): last attack `+0x3cc` ≠ 6 → 6, else own draw &3 == 0 → 8, else
  7; any-angle → turn; not rooted → 3.
- 6: hitInArc(0,36,8000) flags 1 (hammer) / `0x40008` (cutter); 7: `0x40001` / 8.
  8: no target → 0; hammer hits all around (`hitAll`, arc `0x7fff`, flags 1),
  cutter hitInArc flags 8; out of (0,36,8000) → 3; clock > `+0xf4` → 5.
- 9: no target → 0 **but the exit tests still run that tick**; with a target
  move + `ev&1` hit (flags 1 / 8); not charging and see(0,12,8000) → 5; outside
  (0,280,16000) → 3. Cutter missile windows were not compared (no missile fires
  at the grid's clock values).
- **0x13 tests `isNotStunned` before → 3** (the note had an unconditional → 3).
- Hammer: every tick two steam-puff draws; each `r&1` adds a unit-ball draw unless
  the dead-state burst (`ev&6` in 0x14) set object flag 2 that tick.
- Entry: 6/7/8 store `+0x3cc`; 8 `+0xf4 = clock + 120`; 9 `+0xf4 = +0x4f8 = clock`.

### 3.8 Droid — run `0x27ba78`, setState `0x27c0a0` (model `droid()`; notes `docs/monsters-2.md:1463-1511`)

- Before the switch: self-destruct time `+0x3cc` < clock and state not 0x14/0x17 →
  0x17 (`+0x3cc` 99 goes; 100 and 101 do not).
- 0: `sight` → 3; `away` → 1. 1: `sight` → 3. 3: no target → 0; see(0,24,0x7fff) →
  0x17; else move. 5: same test → 0x17; not rooted → 3. 0x12/0x13 → 5.
- 0x14: on `ev&0x40` ten prop blocks and delete. 0x17: when the clip ends
  (`+0x11a & 0x80`) `world_damageInRadius` `0x161270`, decal draw, light, delete,
  ten props. No loot call (asserted in `check_setstate`, §2.4).

### 3.9 IronGuardian — run `0x27a390`, setState `0x27b550` (model `ironguardian()`; notes `docs/monsters-2.md:1347-1462`)

- 0: no `sight` → `away` → 1; seen: counter `+0x3cc` + 1 > 120 → 3 (119 stays;
  120 and 121 go, so ≥ 120 before the add). 1: `sight` → 0.
- 3: no target → 0; cone(84,400,2000) → 9; `+0x3cc` < clock (99 yes; 100/101 no)
  and cone(240,400,10000) → 10; cone(0,84,0x7fff) → 5; else move.
- 5: cone(0,84,10000) → 6; cone(0,84,`0x4000`, facing +`0x4000`) → 7; facing
  −`0x4000` → 8; cone(84,400,2000) → 9; junk test → 10; not rooted → 3.
- 6: `ev&1` hitAll(0,84,10000, flags 8). 7/8: turn only while the alive-player
  count `0x4f8420` is 1 (executed with 0 and with 1); `ev&1` hitAll(0,84,`0x4000`, facing ±
  `0x4000`, flags `0x80008`). 9: turns every tick → 5 (missile cadence not
  compared). 10: turns; `ev&1` → one draw, then ten junk blocks each with a draw
  and a unit-ball point; → 3. 0x12/0x13 → 5.
- The Droid-spawn tail is not reached in the probe (`+0x3d0` vs `g_simFrame` both
  0) — Unknown here.

### 3.10 Froglock — run `0x264314`, setState `0x265150` (model `froglock()`; notes `docs/monsters-2.md:4115-4196`)

Weapon from holder word `+0x7c` (hand-1 part): `0x12` trident, `0x10` blowgun.
- 0: `sight` → 3; `away` or clock > `+0xf4` → 1. 1: `sight` → 0.
- 3 trident: see(0,40,6000) → 6; not see(0,300,0x7fff) and see(0,450,1000) → 0x17
  (jump); any-angle (40) → turn; else move. Blowgun: see(0,100,0x7fff) → 0x10;
  see(0,400,6000) → 7 (8 when standing in water); see(0,400,0x7fff) → turn; else move.
- 5: blowgun see(0,400,6000) → 7, trident see(0,40,6000) → 6; else not rooted → 3.
- 6: target and `ev&1` → hitAtReach(36, flags 8). 0x13 → 0. 0x17 → 3 (no damage).
  States 7/8 (blow darts) were not walked.
- Entry: 0 `clock + r%120`; 7/8 `+0xf4 = r%15` (a 0 draw ends the state at once).

### 3.11 Amphian — run `0x23483c`, setState `0x2350d0` (model `amphian()`; notes `docs/monsters-2.md:2822-2856`)

- 0: `sight` → 3; `away` → 1. 1: `sight` → 3.
- 3: see(0,12,8000) → 5; not charging and see(0,36,8000) → 5; not charging and
  any-angle → turn; see(120,360,2000) → 9 (spit); else move.
- 5: see(0,36,8000): **hit points `+0x228` < 0.5 × maximum `+0x22c`** and an own
  draw &3 == 0 → 0x17 (block), else 6 + draw %3 (the draw is made only below
  half); any-angle → turn; see(120,360,2000) → 9; not rooted → 3. Executed at 10,
  49, 50 and 51 of 100, and at 99, 100 and 101 of 200, in the HP pass (three
  contexts per state, every answer path): 49/100 and 99/200 may block; 50/100,
  51/100, 100/200 and 101/200 never do. So the test is strict and relative to
  the maximum.
- 6/7/8: turn; `ev&1` hitInArc(0,36,8000, flags 8); `ev&2` flags `0x40001`; → 5.
  9: turn; `ev&1` → two poison projectiles, each a unit-ball point, a pool block
  and one more draw; → 5. **0x13 tests `isNotStunned`** before → 3. 0x17 → 5 at
  clock > `+0xf4`.
- Entry: 0x17 `clock + 60 + r%120` and cflag `0x200`.

### 3.12 SeaMonster — run `0x2a44a8`, setState `0x2a4aa4` (model `seamonster()`; notes `docs/monsters-2.md:1853-1898`)

- 0: `sight` → 3; `away` → 1. 3: see(0,36,5000) → 5; any-angle → turn; else move.
- 5: out of (0,36,5000) → 3 when not rooted; else draw &1 == 0 → 7; else draw %3 ==
  0 → 9, otherwise 6.
- 6/7/8: target and `ev&1` → hitInArc(0,36,5000, flags 8); 7/8 on `ev&2`, draw &1
  == 0 and still in range → the other of 7/8; → 5. 9 crush: target and `ev&1` →
  flags `0x80008`; → 5. 0x12/0x13 → 5; 0x17/0x18 → 3 when the clip ends.

### 3.13 Arena knights, Zek, Skelight — reused executed model

**Executed, reused**: `docs/spec/arena-monsters.md` §3.3 (Horsemen run
`0x27236c`), §4.3 (Skelight `0x2a8b84`), §5.3 (Zek `0x2c2440`) are compared in
whole-tick runs by `tools/difftest_arena_monsters.py` with the base class running
for real; rerun this round (`--quick`, seeds 20973 and 7, logs §5). In `drunare`
Zek is hidden until the last cutscene (§1 there). In `drunarm` one `RalosZek`
record has `visualarc` and `dropitem` keys and no `wait` key, and the other has
`wait` and neither of those (key presence asserted by `check_levels`, §1). That
the first is the one that can fight is an **inference** from the keys, not
executed.

### 3.14 Not executed here

- **Cazic** (`CazicAvatar`, run `0x24aaf0`, setState `0x24c118`): static notes
  only (`docs/monsters.md:519-566`). **Unknown** by execution.
- **Critter** (rat/seagull/crab, run `0x255008`): ambient, ignores slot 2
  damage, flees/idles (`docs/monsters-2.md:3164-3347`). No attack. Not executed.
- **Catapult** (`0x24d440`, run `0x24d9c0`): a level hazard, destroyed by the
  first hit; its `FireBomblet` hits every object in a box through `damage_apply`
  (`docs/monsters-2.md:7991-8005`). Not executed here.

## 4. Client-implementable list

Implement in this order; each item names the executed evidence.

1. Spawn the §1 classes from the factory names; counts per level must match.
2. One tick per creature in §2.1 order; use the per-class knock-back scale.
   Drive attacks and chains from **animation events** (`ev`) and the
   "clip playing" flag `+0x11a & 8`, never from wall-clock timers.
3. Target: base pick (§2.2) for all twelve; notice = slot-25 sight with the
   class's point-blank/visual values; leash per HomeRange (1000, WarWraith 600,
   IronGuardian 3000). WarWraith one-per-victim and Kobold shaman-only ally rules.
4. Every state request goes through the §2.3 filter (root, stun, cooldown,
   death clears) and the class's "no case → 0" list.
5. Per class, the §3 decision order exactly, including the query arguments
   (near, far, arc, ray mode), short-circuit order and own-generator draws
   (`GameObject_rand` on `+0x44`, never the shared seed in these paths).
6. Entry timers of §3 (`+0xf4`, `+0x3cc`, `+0x318 = 60`, cflag `0x200` for blocks).
7. Hits: the three helpers of §2.5 with the class flags; `hitAtReach` uses a
   3-D distance < 60 (x, y and z) from the reach point, ignoring both radii; feed
   `damage_apply` with (victim, attacker, rating, 0, 0, flags, descriptor; min,
   max) and apply the combat.md armour rule and the spells-r3 knock-back rule on
   the victim.
8. Flee = cooldown retreat (0x10) only. No class run function reads HP, except
   for Amphian's block below half (§2.4 HP pass). Any HP rule inside the base
   `Creature_run` / `processDamage` is outside this probe.
9. Death: `deadUpdate` corpse distances, loot call, Droid/Clockwork/WarWraith
   self-deletion paths.

## 5. Reproduction and retained logs

On the mini, worktree `~/malik-champions/research/wt/research-campaign-combat`,
private inputs under ignored `local/` (`local/SLUS_209.73`, SHA-256
`292f6f48…cd675`; `local/levels/*.GOB` links to the read-only disc copy):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_creature_ai_m1_3.py \
  local/SLUS_209.73 --seed 20973 --levels local/levels
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_creature_ai_m1_3.py \
  local/SLUS_209.73 --seed 7 --levels local/levels
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_monsters.py \
  local/SLUS_209.73 --quick --seed 20973   # and --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

Results after the final edit: both seeds PASS — twelve classes, 16,445 / 16,436
answer paths, 261 setState entries, 84 filter redirects, 60 vtable slots, 64 hit
cases, 807 factory selections. The reused arena difftest compares 4,054
(seed 20973) and 4,012 (seed 7) calls with no failing property. The unit suite
runs 659 tests, OK. Logs (ignored, not committed):
`local/creature-ai/seed-20973.log`, `seed-7.log`, `arena-seed-20973.log`,
`arena-seed-7.log`, `unittest.log`.

## 6. Unknown

Live trajectories and pathing; real animation-event spacing under blend and slow;
Goblin 7/8, Froglock 7/8 and Kobold 9 bodies; cutter and IronGuardian missile
cadence; IronGuardian Droid spawning; Cazic, Critter and Catapult execution;
slot 20/21 overrides by execution; final stats and delivered player HP loss;
PCSX2 or console captures.
