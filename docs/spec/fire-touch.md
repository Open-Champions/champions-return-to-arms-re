# A LooseFire touching a player or a creature: the fire entry and the burn it leaves

US `SLUS_209.73` v2.00. Prose of `tools/ref_fire_touch.py`; the comparison is
`tools/difftest_fire_touch.py`, the synthetic tests `tools/test_ref_fire_touch.py`.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
on state the difftest built, and the model agreed on the stub calls in order with their
arguments, the shared seed `0x404464` (every draw, in order) and the cosmetic seed
`0x404460`, every field of every object and player record the model accounts for, the
music bytes, and that nothing else was stored. **Observed**: read at the address.
**Inferred**: follows from those. Nothing here ran on a console, in PCSX2 or on the live
rig.

## 1. What was executed before, and what was not

- `LooseFire_onTouch` `0x1fcb70`: executed in `tools/difftest_potion_ctors.py`
  (`docs/spec/potion-ctors.md`) with `damage_apply` a recording stub. That compared the
  descriptor it passes, not what the descriptor does.
- `damage_apply` `0x1e8230`: executed in round 1 (`tools/difftest_combat.py`,
  `docs/spec/combat.md` §3), with random descriptors that include type 0x15, but never with
  the touch's arguments (rating 10,000,000, flags `0x0100c040`, range 0..0, entry
  `(0x15, v, v, 0)`), and never behind the real touch.
- The burn tick in `Creature_run` `0x113278`–`0x113538`: executed in
  `tools/difftest_creature.py` (`docs/spec/creature-tick.md` §4.8; in this tree the full
  run enters 1191 of 1216 instructions of `Creature_run`, the seven missing ones the dead
  slot search of the burn record). Its `damage_apply` was a recording stub there.
- `poisonGasSpell_run` `0x1fd0f0` (item 6 of the brief): executed in combat round 6
  (`docs/spec/combat-round6.md` §2). Re-run in this tree:
  `python3 tools/difftest_combat_round6.py --seed 20973` and `--seed 7`: `poisonGas` 10
  cases each, 0 failed, 296 of 303 instructions. Nothing was redone here.

New here: the real `LooseFire_onTouch` calling the real `damage_apply`, and the burn
tick's own `damage_apply` on the state the touch left.

## 2. The touch, end to end (*Executed*)

`LooseFire_onTouch(fire, toucher)`, slot 6 of table `0x50e2b8`:

1. Nothing unless `g_simFrame` `0x44fdcc` (read at `0x1fcb78`) `% 20 == 0`, a signed
   divide (`0x1fcb88`). No draw.
2. Owner: the object behind the fire's handle `+0x4c` when its flags `+0xc` have `0x20`.
   With one, its slot 20 (table `+0xa0`, `0x1fcbcc`) is asked `(owner, toucher)`; 0 ends
   the touch with no draw. An owner without `0x20` is ignored and not asked.
3. The descriptor on the touch's stack: four entries of type −1 (`0x1fcbe8`–`0x1fcc10`),
   bytes `+0x20`, `+0x21` = −1, halfwords `+0x10`…`+0x1e` = 0, then slot 0 =
   `(0x15, v, v, 0)`:
   - toucher flag `0x40` (player): v from `g_difficultyIdx` `0x4f719c` (`0x1fcc60`):
     2, 3, 4, 5 as they are (`0x1fcc70`, `0x1fccd4`, `0x1fcd34`, `0x1fcd90`), anything
     else 1 (`0x1fcde8`);
   - flag `0x20` without `0x40`: v = 8 (`0x1fce4c`);
   - otherwise no entry (an empty descriptor).
4. `damage_apply(toucher, owner or the fire, 10000000 (0x1fcea4/0x1fcebc), 0, 0,
   0x0100c040 (0x1fcea8/0x1fcec8), descriptor, 0; f12 = f13 = 0.0)`. Its result is
   dropped.

What `damage_apply` then does with these arguments (round 1's rules, `docs/spec/combat.md`
§3 step numbers):

- **It always hits.** The rating is 10,000,000 and armour `+0xe4` is an s16, so
  `p = sqrt(10⁷ / AC) ≥ 17.4` (or 1.0 for `AC ≤ 0`); both hit rolls (steps 13 and 21)
  succeed for every draw (*Inferred*; no miss in either seed's 11,980 touches).
- **Flag bits** of `0x0100c040`: `0x40` unblockable (no block test, no Spirit Shield,
  step 11); `0x4000` no hit sound; `0x8000` no miss sound; `0x01000000` no floating number
  (step 28). It has no `0x10000000`, so the 0x15 entry sets the burn. `flags & 0xd == 0`:
  no thorns (step 23).
- **No reflection.** The range is 0..0, so the running damage is 0 at step 14 and the
  `dmg > 0` test fails (*Inferred*; the 0x15 amount is added later, at step 20).
- **The amount** is `v − v × fire resistance` (`+0x5c`), added at step 20; the armour
  factor of step 16 multiplies the 0 before it and does nothing. A player victim in PvP
  mode A (`0x4f711c`) halves it (step 24).
- **The burn**: `Creature_setEffectTimer` `0x118950` stores `+0x340 = 2 − 2 × fire
  resistance` (a store: a re-touch resets the burn, it never stacks) and, when that is
  above 0, relinks the source handle `+0x360` (`handle_clear`, `handle_link`) to the
  attacker if it is a creature (flag `0x20`), else leaves it empty. The fire effect
  (`0x214230` with `0x53df38`) plays only when the burn was ≤ 0 before and is > 0 after.
- **Take-damage**: the victim's slot 2 with (amount, attacker, flags `0x0100c040`).
- **A non-creature toucher** (no `0x20`) gets the empty descriptor and only the base roll:
  one draw, take-damage(0.0).

### Shared-seed draws per touch (*Executed* per case; the counts are *Inferred* sums)

| Toucher | Attacker | Draws |
|---|---|---|
| creature or player, nothing on it | the fire (no owner, or an owner without `0x20`) or a monster owner | **7**: hit roll, the four chance rolls of step 19 (0x1f, 0x20, 0x21, 0x22, made though the slots are empty), the 0x15 amount, the second hit roll |
| creature | a **player** owner (the thrower) | **8**: the same and the thrower's stun roll (step 27); **9** when the thrower has a critical bonus (step 18); a stun that lands adds the `LightEffect` constructor's draw and the stun-length draw |
| anything without `0x20` | any | **1**: the base roll |
| any, on a frame not divisible by 20, or the owner says 0 | — | 0 |

The 0x15 amount is `v + S rem (v − v + 1)`, a remainder by 1: the draw is made and does
not change the amount. Spells on the victim add their own draws as in round 1 (Frost
Armor's strike-back roll; BloodLust none).

## 3. The burn on the following frames

`Creature_run` (*Executed* in `tools/difftest_creature.py`) lowers `+0x340` by `DT` =
`0x3c888888` (1/60 truncated) on every run while it is above 0, and on frames with
`frame & 0x1f == 0` (not the prediction copy `0x20000`) calls
`damage_apply(c, c, 100000, 0, 0, 0x1180c040, (0x15, lo, hi, 0), 0; 0, 0)`: lo = hi = 1
for a monster; for a player (flag `0x40`) the Skill at `0x41b1a4` slot 11 gives n, base =
`f32(n) × 0x3e199999` (0.15), and ONE shared draw d gives `lo = int(base)`,
`hi = int(base + base × 0x3e4ccccc × d / 65536)`.

That `damage_apply` with those arguments, on the memory the touch left, is *Executed*
here (step 2 of each difftest case). What it does:

- It always hits (rating 100,000, `p = sqrt(10⁵ / AC) ≥ 1.74`).
- `0x10000000`: the 0x15 entry does not set the burn again. `0x00800000`: the damage goes
  through the accumulator `+0xcc`; the tick frame is always `frame & 31 == 0`, so it is
  delivered at once: +0xcc is raised to 1.0 when at most 1.0, take-damage
  (`f32(trunc(+0xcc))`), +0xcc = 0, then the ordinary take-damage with 0. A resisted
  monster (fire resistance 0.25: 0.75) still takes **1.0**. A resistance of 1 leaves no
  burn to tick.
- The number: `0x00800000` on a tick frame lets it through despite `0x01000000`, so a
  monster's tick makes a `FlyingText` (one more draw); a player victim gets none.
- The burning creature is its own attacker: no reflection (attacker = victim). A burning
  **player** is a player attacker, so the tick makes the stun roll (step 27) and may make
  a critical roll; with stun skill 0x40 a burning player can stun itself (*Inferred* from
  round 1's step 27; not seen in the sample).
- Draws per tick: monster **8** (seven, and the FlyingText); player **9** (the range draw
  in `Creature_run`, seven, the stun roll), plus a critical roll with a bonus.

*Inferred* timing: a touch on frame F leaves 2.0 s; `burn_tick_frames` gives the tick
frames, three or four of them (F = 640: 672, 704, 736; F = 600: 608, 640, 672, 704). A
toucher that stays in the fire is re-touched every 20 frames, and every touch resets the
burn to `2 − 2r`, so the ticks continue until 2 s after the last touch.

**Frost Armor and the burn tick.** `docs/spec/combat.md` §3.5 lists "an object with
Frost Armor hitting itself" as a recursion with no bound and says the generator never
builds it. The burn tick is exactly that hit. *Executed*: a burning Frost Armor carrier's
tick re-enters `damage_apply` through `0x318264` with the carrier as victim and attacker,
again and again while the strike-back roll succeeds; with the chance statistic at 100 or
more the interpreter's 1 MB stack ran out after about 1,300 nested calls, the model nested
at least as deep (20 cases over both seeds, counted separately, not as matches). Below 100
the chain ends and matches: 297 burn ticks on carriers, 0 to 3 or more nested hits. So
the case occurs in play whenever a player with Frost Armor burns (*Inferred*); with the
real statistic below 100 it costs one extra roll per strike-back, and two machines stay in
step because the rolls come from the shared seed.

## 4. Fields and constants

Read by the touch and its `damage_apply` (the victim V, the attacker A):

| Where | What |
|---|---|
| `0x44fdcc` | `g_simFrame` (touch period, frame stamps, the 0x800000 delivery) |
| `0x4f719c` | `g_difficultyIdx` (player entry value) |
| fire `+0x4c`, node `+0xc`, owner `+0xc`, `+0x48` | owner handle, owner flags, owner slot 20 |
| V `+0xc`, `+0x10`…`+0x18`, `+0x38`, `+0x5c`…`+0x6c`, `+0xa8`, `+0xb4`, `+0xe4`, `+0x228`, `+0x340`, `+0x364`, `+0x39c`, `+0x3c8`, `+0x58c` | flags, position (music counter), facing, the five resistances (colour class), creature flags, kind, armour, hp, burn, spell list, reflection counter, player slot, player state |
| A `+0xc`, `+0x3c8`, `+0x364` | flags (creature, player, prediction copy), slot, spells (critical bonus) |
| `0x44fcd0`, `0x44f048`, `0x44f04c`, `0x4f717a`, `0x4f711c`, `0x44fcf8`, `0x402791`, `0x4d8ae0`, `0x4f8440` | cutscene, camera focus, music index, PvP mode A, number option, network mode, players, alive list |

Written: V `+0x340` (burn), the handle `+0x360` (through `handle_clear` / `handle_link`),
`+0xcc` (burn tick only), the byte `0x4f7158[index]` (the music counter when the camera
focus is within 340 of V), the shared seed `0x404464`. The victim's own take-damage writes
are its slot 2's (a stub here; `Creature_takeDamage` `0x116638` and `Player_takeDamage` are
executed in their own rounds).

Constants (each Observed at the address given): `0x14` period `0x1fcb74`; slot offset
`0xa0` `0x1fcbcc`; entry type `0x15` `0x1fcc6c` (and the four other arms); creature value
8 `0x1fce4c`; rating `0x989680` `0x1fcea4`/`0x1fcebc`; flags `0x0100c040`
`0x1fcea8`/`0x1fcec8`; burn tick rating 100,000, flags `0x1180c040`, scale `0x3e199999`,
spread `0x3e4ccccc` and `DT` `0x3c888888` as in `tools/ref_creature.py` (executed there).

## 5. Coverage and figures

`python3 tools/difftest_fire_touch.py --seed 20973` and `--seed 7`: 3,000 cases each,
three steps per case (touch, burn tick, re-touch), every property 0 mismatches.

| | Seed 20973 | Seed 7 |
|---|---|---|
| touches compared | 3,000 + 2,988 | 3,000 + 2,992 |
| burn ticks compared (creature / player) | 1,422 (959 / 463) | 1,424 (963 / 461) |
| runaway Frost Armor self-hits (both sides) | 12 | 8 |
| `LooseFire_onTouch` `0x1fcb70` | 162 of 224 | 162 of 224 |
| `damage_apply` `0x1e8230` | 1,372 of 2,722 | 1,400 of 2,722 |

The 62 instructions of `LooseFire_onTouch` not run are the search for a later descriptor
slot in each of the six arms; slot 0 is always free, so they are dead (as in
`docs/spec/potion-ctors.md`). The `damage_apply` instructions not run are the paths a fire
entry cannot reach (blocking, Spirit Shield, the other entry types, the base roll of a
real range, misses); round 1 executes them.

Paths seen, seed 20973 (first touch): entry values 1 (331), 2 (126), 3 (106), 4 (128), 5
(122), 8 (1,529); the fire itself the attacker 1,062; the owner said not an enemy 218; not
a touch frame 316; `damage_apply` returned 0 in 144, and every one is an invulnerable
victim (71), an Innoruuk with its immunity word (34) or an owner that is the prediction
copy `0x20000` (39). No miss.

`python3 -m unittest tools.test_ref_fire_touch`: 17 tests.

## 6. Still not executed on this path

- The victim's slot 2 (take-damage), the stun effect (slot 30), the FX and sound calls,
  the pool and the handle bookkeeping are recording stubs here; their bodies are executed
  (or are presentation) in their own rounds.
- The fire owner's slot 20 (`Creature_isEnemy` `0x119328`, or a Player's) answers what the
  case chooses; `Creature_isEnemy` is executed in `tools/ref_creature.py`.
- What calls slot 6 of a LooseFire, how often, and with several fires on one toucher in
  one frame, is the touch dispatch's (`docs/issues/touch-handlers.md`), not executed here.
- The player burn range's Skill slot 11 answer is a stub in `tools/difftest_creature.py`;
  the real Skill table's numbers are not established here.
