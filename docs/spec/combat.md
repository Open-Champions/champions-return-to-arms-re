# Combat and statistics rules: a tested reference

US `SLUS_209.73` v2.00. This is the implementer's version of the rules that decide a fight:
the damage function, monster statistics, experience, and the player's derived numbers. It
is the prose form of `tools/ref_combat.py`; `tools/difftest_combat.py` runs the original
machine code under `tools/ee_emu.py` and compares it with that model.

Evidence labels: **Executed** = the game's own instructions were run in the interpreter on
constructed state and the model agreed (section 11 says for which inputs); **Observed** =
read at the address given; **Inferred**; **Unknown**. "Executed" says what the code does
with those inputs, not that the inputs occur in play; nothing here was seen on a console.
Everything in sections 1–9 is Executed unless a sentence says otherwise.

No table contents are reproduced. The model reads the experience curve, the per-class
constants, the passive masks and the name fragments from your own executable
(`ref_combat.Tables.load`).

## 1. Arithmetic you have to reproduce

Lockstep play means the last bit counts. Three kinds of arithmetic occur.

**1.1 Single precision on the console FPU.** No NaN, infinity or denormal; exponent field 0
is zero, 255 is an ordinary large number; overflow and division by zero give ±0x7fffffff;
every result is truncated toward zero; `sqrt` takes the magnitude; float → int truncates
and saturates. Compiler constants are the decimal value truncated to 24 bits (0.6 is
0x3f199999, 0.85 is 0x3f599999, 1/30 is 0x3d088888), with one exception that matters here:
0.01 is 0x3c23d70a, the nearest value. The last bit of sums on real hardware is not
established (`docs/issues/dynamic-tests.md`); the model and the interpreter share four
selectable adder models and agree under each.

**1.2 Doubles go through library routines, and those are not IEEE either.** int → double
0x3afa08 and fmod 0x3a5a38 are exact; single → double 0x3aef58 reads exponent field 255 as
an ordinary number and field 0 as zero; add 0x3af410 and multiply 0x3af4d0 **truncate
toward zero** to 53 bits; double → single 0x3afb90 **truncates toward zero** to 24 bits,
gives zero below 2^-126 and the pattern 0x7f800000 from 2^129 up and for a not-a-number.
Two rules use them: the damage roll (3.4) and the monster hit-point roll (4).

**1.3 `powf` 0x3a5ac8 → 0x3a7930.** The usual single-precision power kernel, built with the
FPU above, the NaN and infinity tests removed and "zero" widened to "exponent field 0".
`powf(x, 1.0)` returns `x` unchanged, `powf(x, 2.0)` is `x·x`, `powf(x, 0.5)` for `x ≥ 0`
is the bit-by-bit `sqrtf` 0x3a84c0. Otherwise the result is close to, but not, the
correctly rounded power (1234.5^1.4 comes out as 0x46a64b59 = 21285.674; the real value is
21285.680), so a port must copy the kernel operation for operation — `ref_combat.powf`
does, with `scalbnf` 0x3aa810.

**1.4 The generator.** `state = state·0x19660d + 0x3c6ef35f (mod 2^32)`; a draw is the
upper 16 bits of the new state. Three users here: the shared seed 0x404464 (in the sync
hash), the cosmetic seed 0x404460 (per machine), and each object's own seed at +0x44
(seeded by one shared draw in the object constructor).

## 2. `damage_apply` 0x1e8230 — interface

`damage_apply(min $f12, max $f13, victim $a0, attacker $a1, attack $a2, –, –, flags $t1,
descriptor $t2, noCrit $t3)`; returns 0 when nothing landed, else 1. Field layouts and flag
bits are in `docs/gameplay.md` §2.1–2.4 and were confirmed by execution; what differs is
in section 12. `$a3` and `$t0` are not read (the test passes junk there).

Descriptor: four effect slots `{s16 type, v1, v2, v3}` at +0x24 + 8·i; every lookup takes
the first slot of the wanted type and reads 0 when there is none. For a melee hit the
descriptor is the weapon's item record, so the slots are its modifier slots.

What a port has to supply because the original reaches it through a virtual table:

| What | How the original reaches it |
|---|---|
| take-damage(amount, attacker, flags) | victim virtual slot 2 |
| class of an object, class of a spell | type-info getter in the virtual table, compared by name |
| skill statistic | Skill slot 10 `stat(stat, level)`, slot 12 `statFor(stat, level, caster, cap)`, slot 14 `adjust(level, n)` → level |
| cast a skill (type 0x29) | Skill slot 2 `(level, caster, pos, facing)` |
| stun | victim virtual slot 30 `(frames, 1)` |
| "is enemy" (PvP mode A only) | creature virtual slot 22 |

## 3. `damage_apply` — order of operations

`dmg` is the running amount, **S** one draw from the shared seed, **C** draws from the
cosmetic seed. Everything is single precision unless it says double.

1. Attacker has flag 0x20000 (prediction copy): return 0.
2. No cutscene and `sqrt((fx − x)² + (fy − y)²) < 340` (camera focus against the victim's
   x, y): increment the byte `0x4f7158[s16 0x4f717a]`. Per-machine, no reader known.
3. Victim's class is `Innoruuk` and its +0x3e0 is non-zero: return 0.
4. Victim is not a creature (flag 0x20 clear): **S**, `dmg = roll(min, max)` (3.4),
   take-damage(dmg, attacker, flags), return 1.
5. Return 0 if: creature flag 0x800; or creature flags 0x100000 and (0x10 or 0x40) with
   flag bits 0x9; or flag 0x8000000 and kind ≠ 0x10.
6. Attacker has flag 0x80 and a non-null link at +0x4c, victim is not a player, and the
   victim's class equals the class of the object behind the link: return 1.
7. Attacker present and neither side a player: `flags |= 0x1000000`.
8. `AC` = victim +0xe4 (s16). With a `BloodLust` spell on the victim:
   `AC = trunc(AC · factor)`, at least 1, where factor is 1.0 when the spell's +0x2c is 0,
   else `1 − stat(2, level)·0.01` (0x3047b0).
9. Mitigation, for a player victim or anyone in PvP mode A, with the **unmodified** armour:
   `cut = armour · (1/30)`; `min = max(min − cut, min·0.5, 0)`, same for `max`.
10. If `min < max`: **S**, `dmg = roll(min, max)`; else `dmg = min`.
11. Unless flag 0x40:
    - victim creature flag 0x200, attacker present and
      `cos16(facing)·(ax − vx) + sin16(facing)·(ay − vy) > 0`: block — sound, 50 sparks
      (**C** ×3 or more each); return 0, or with flag 0x20000 `dmg ·= 0.5`;
    - then `SpiritShield` on the victim (0x315888): `limit = statFor(0, level, owner, 10)`,
      `chance = statFor(1, …)`; if `float(limit) < spell +0x1c` nothing; else **S**, and if
      `S % 100 < chance` the hit is absorbed: return 0, or with flag 0x20000 `dmg ·= 0.5`.
      On the first absorb the spell's +0x18 becomes 1 and +0x20 = +0x1c + 0.19199899.
12. `p = sqrt(attack / AC)` if `AC > 0` else 1.0. `c = v1(0x1d) · 0.01`.
13. **S — first hit roll**: `hit = float(S) < p · 65536`.
14. Reflection: victim +0x39c > 0, `hit`, attacker is a creature other than the victim,
    `dmg > 0`, attacker kind 0x10 → nested `damage_apply(dmg, dmg, attacker, victim,
    100000000, flags 0x100, same descriptor, noCrit 0)`; then attacker +0x398 = 0x11,
    +0xf0 = frame counter.
15. `FrostArmor` on the victim (0x318264): `f = max(1 − statFor(1, level, owner, 0)·0.01,
    0)`; with an attacker **S**, and if `S % 100 < statFor(2, …)` the attacker takes a
    nested `damage_apply(0, 0, attacker, spell owner, 100000, flags 0x540, {0x16: a, a},
    noCrit 0)` with `a = trunc(dmg − f)` — the amount minus the *factor*, not the absorbed
    part. Then `dmg ·= f`.
16. If `AC > 0`: `dmg ·= min(attack / (AC · 0.5), 1.0)`.
17. Unless flag 0x40000000, attacker not a player, or noCrit: `c += max(b51, max(b21,
    b35))`, the critical bonuses of skills 0x21, 0x35, 0x51 (3.2).
18. If `c > 0`, `hit` and not noCrit: **S — critical roll**; if `float(S) < c · 65536`:
    `crit`, `dmg ·= 3.0`, voice cue for a player attacker.
19. Only if `hit`, in this order (the four chance rolls are made whether or not the slot
    exists; a chance is `float(S) < v1·0.01·65536`; `src` is the attacker if it is a
    creature):
    - 0x29, creature attacker and `v2 ≠ 0`: **S**; if `S < v2·655`: cast skill `v1` at
      level `v3` from the attacker's position and facing (so `v2` = 100 is 65500 in 65536,
      not a certainty);
    - 0x1f: **S**; on success burn = `1 − fireRes` (status 0), then **S** and
      `dmg += a − a·fireRes` with `a = amount(v2, v3)`;
    - 0x20: **S**; on success **S**, `dmg += a − a·coldRes`, cold status = `min(old +
      dmg·60 / hp, 60)` using the *running total* (`old + 60` when hp is 0);
    - 0x21: **S**; on success a `poisonGasSpell` is created if the pool has a block (life
      300, radius `30·v2 + 30`, damage `25·v2 + 25`, owner = attacker); its constructor
      draws **S**;
    - 0x22: **S**; on success shock = 2.0, **S**, `dmg += a − a·lightningRes`.
20. Always, in this order:
    - 0x1b, `v1 ≠ 0`, kind 0x10: `dmg = v1·0.01·dmg + dmg`;
    - 0x15, `v1 ≠ 0`: **S**, `dmg += a − a·fireRes` with `a = amount(v1, v2)`; burn =
      `2 − 2·fireRes` unless flag 0x10000000;
    - 0x16, `v1 ≠ 0`: **S**, `a' = a − a·coldRes`, `dmg += a'`, cold status = `min(old +
      a'·60 / hp, 60)` using this slot's amount;
    - 0x17, `v1 ≠ 0`: poison status = `5 − poisonRes·5`; victim +0x358 = v1, +0x35a = v2;
    - 0x26, `v1 ≠ 0` and no `SpellDiseaseEffect` on the victim: a block of 0x1b0 bytes is
      requested; if granted the spell is built with strength `trunc(5 − diseaseRes·5)`
      (its constructor draws **S**); the add-spell call is made even with a null block;
    - 0x18, `v1 ≠ 0`: **S**, `dmg += a − a·lightningRes`, shock = `2 − 2·lightningRes`;
    - 0x19, `v1 ≠ 0`, kind 0x12: shock = 2.0, **S**, `dmg += a − a·lightningRes`;
    - 0x1a, `v1 ≠ 0`, kind 0x12: **S**; if `S % 100 ≤ v1`: `flags |= 0x800`, `dmg += hp`;
    - 0x1c, `v1 ≠ 0`, kind 0x10: **S**; if `S % 100 ≤ v1`: `flags |= 0x2000000`,
      `dmg += hp`.
21. Unless `crit`: **S — second hit roll**; if `float(S) ≥ p·65536`: miss sound (unless
    flag 0x8000), take-damage(0, attacker, 0x2000 for a player victim, else 0x42000),
    return 0. Statuses, objects and nested hits of steps 14–20 stay.
22. Colour class for the number (3.3). Never changes the amount.
23. Attacker present and `flags & 0xd`:
    - both creatures: a player victim runs thorns (3.2) for skill 9 and then skill 0x52,
      each if its rank is non-zero; a non-player victim with creature-flag bit 45 runs
      thorns for skill 9 at level `trunc(monster level)`;
    - player victim, creature attacker of kind 0x10: `SpellUndeadShield`, else
      `SpellSecondaryUndeadShield`, is called with `trunc(dmg)` (not modelled further).
24. PvP mode A and player victim: `dmg ·= 0.5`. `number = trunc(dmg + 0.5)`.
25. Flag 0x800000: `acc = victim +0xcc + dmg`; `dmg = 0`; store `acc`. If `frame & 31 == 0`:
    +0xcc = 1.0 when `acc ≤ 1.0`; `number = trunc(+0xcc + 0.5)`; take-damage(
    `float(trunc(+0xcc))`, attacker, flags); +0xcc = 0. (The other delivery condition in
    the code, "hp > 0 and hp ≤ 0", can never hold — Observed at 0x1ea710–0x1ea724.)
26. Hit sound unless flag 0x4000; **take-damage(dmg, attacker, flags)** — with flag
    0x800000 this is a second call, with 0.
27. Player attacker: `chance` = stun chance (3.2); **S**; if `S % 100 < chance`: stun
    effect (3.2). Then `Retribution` on the attacker (3.2) gives `share`.
28. Floating number. Skipped when: the victim is a player (unless PvP mode A, a player
    attacker and attacker ≠ victim); the number option 0x44fcf8 is 0 and the game is not a
    net game; the victim is dead (flag 8); flag 0x200 with creature flag 0x100; a cutscene;
    PvP "blocked from the front" (mode A, player victim in state 8 or 0xb, flags 0x20040
    clear, attacker in front); flag 0x800000 on a frame with `frame & 31 ≠ 0`; otherwise
    flag 0x1000000. Else a `FlyingText` is created if the pool has a block (constructor
    draws **S**): text `number`, crit, victim-is-player, colour, kind 0. If `share ≠ 0` a
    second one (kind 2, again **S**) shows `trunc(dmg · share + 0.5)`.

### 3.1 `amount(lo, hi)` and what happens when `hi < lo`

`amount = float(lo + S rem (hi − lo + 1))`, a signed 32-bit divide with no test of the
divisor (first use at 0x1e914c; the same sequence at 0x1e92e4, 0x1e974c, 0x1e990c,
0x1e9a8c, 0x1e9f34, 0x1ea0c4). `S` is 0…65535, so:

- `hi ≥ lo`: uniform in `lo…hi`.
- `hi < lo − 1`: the divisor is negative, the remainder keeps the sign of the dividend, so
  the result is `lo + S mod (lo − hi − 1)` — values from `lo` **upward**, never below it.
  `(10, 5)` gives 10…13. Executed (1,084 such ranges drawn in the full sample).
- `hi = lo − 1`: division by zero. The CPU does not trap. The interpreter refuses to guess
  unless told to continue with what the R5900 is *reported* to leave (remainder =
  dividend), in which case the amount is `lo + S`, up to 65535 more. The model follows that
  report so that the two can be compared, and they agree (389 such ranges drawn, in 253
  cases); **the console's result is not established.** `docs/spec/skills-01-34.md` (section 18, hazard SA4) lists skills that
  pass `v2 < v1`.

### 3.2 Helpers

| Helper | Rule |
|---|---|
| critical bonus 0x2e76c4 `(skill, attacker, rank)` | level = `rank` if `rank ≠ 0` and the attacker carries a `SpellCriticalHit`; otherwise the first other alive player (list order) within 1000 units (3-D, squared test `< 1e6`), passing the enemy test in PvP mode A, carrying the spell, with `r = max(rank 0x35, rank 0x51, rank 0x21) ≠ 0` and within `12·stat(1, r)` in x, y — level = `r` if positive. Bonus = `stat(0, adjust(level, 20))·0.01`, or 0 when the adjusted level is 0 |
| thorns 0x2ddccc `(skill, victim, attacker, level)` | level 0: nothing. `d = statFor(0, level, victim, 10)`, `chance = statFor(1, …)`; **S**; continue if `trunc(float(S)·2^-16·100) < chance`; victim flash colours set; stop if the victim's model reports 0 sample points; 200 particles (**C**); **S**; nested `damage_apply(d, d + d·(S·2^-16)·0.2, attacker, victim, 100000, flags 0x40, empty, noCrit 1)` |
| stun chance 0x308c10 | 0 for a non-creature or in PvP mode A; else `stat(0, rank)` of skill 0x40; 0 against boss rank 2; capped at 5 against rank 1 |
| stun effect 0x308cb4 | sound; `LightEffect` if the pool has a block (constructor **S**); **S**; victim slot 30 with `trunc((S·2^-16 + 1.5)·60)` frames |
| Retribution 0x314790 | owner flash colours; `share = stat(1, level)·0.01`; a player owner with record hp > 0 gets `hp += dmg·share` capped at max hp; a player owner at hp ≤ 0 makes the share 0 |
| status setter 0x118950 | stores the value; a value > 0 also re-links the status-source handle +0x360 to `src` (or leaves it empty) |

### 3.3 Colour class

`immune`/`resisted` start clear. A resistance `r` sets immune when `r ≥ 1`, else resisted
when `r > 0`. In order: lightning resistance if flag 0x100; creature flags 0x2/0x4 if flag
4; 0x8/0x10 if flag 8; 0x20/0x40 if flag 1 (first of each pair resisted, second immune);
cold, fire resistance; creature flag 0x80 resisted, 0x100 immune; lightning, poison,
disease resistance. Class = 2 if immune, else 1 if resisted, else 0. **Any** non-zero
resistance colours the number, whatever the damage type.

### 3.4 The base roll

`span = (max − min) + 1.0` in single precision; then in the library doubles
`dmg = single(double(min) + fmod(double(S), double(span)))`, truncated. `S` is used as the
unsigned 16-bit draw. A span of exactly zero (possible only on the non-creature path, with
`max = min − 1`) makes `fmod` return a not-a-number and `dmg` the pattern 0x7f800000,
which the FPU treats as 2^128.

### 3.5 Recursion without a bound

The nested calls of steps 14, 15 and 23 re-enter the function with the roles swapped.
Two set-ups never terminate except by a failed roll:

- an object with `FrostArmor` hitting **itself**: the nested hit has the same object as
  victim and attacker, so the strike repeats while the chance roll succeeds; with a chance
  statistic of 100 or more it always does. Executed: with the statistic at 100 the
  interpreter's stack ran out after 2,672 draws; at 60 the call ended and matched the
  model. The test generator removes Frost Armor from self-hits;
- two creatures of kind 0x10 that both have +0x39c > 0 reflect each other's hit for as long
  as the first hit roll succeeds and `dmg > 0` (with attack 100000000 it always succeeds).
  Observed, not executed; the generator never builds it.

Whether either set-up occurs in play is Unknown.

## 4. Monster statistics

### 4.1 The level's monster level — `game_loadLevel`, 0x1e5b70–0x1e5c94

```
b = signed byte +4 of the level's table row
L = float(b + 2);  in PvP mode B: L = 3.0
difficulty 2: L = (b+2)*0.75 + 34     3: + 61     4: + 88     5: + 115
level name equal (case-sensitive) to the first fixed-scale name: L = 1.0;  the second: L = 2.0
```

The difficulty line is computed from `b + 2` after the PvP store, so **PvP mode B's 3.0
survives only on difficulty 1** (or a difficulty index outside 2–5).

### 4.2 `Creature_setStats` 0x10a620

Inputs: the five factors of `monsters.bal` (hp, armour, damage, attack, experience; 1.0 =
100 %), `rank` = `creature_bossRank`, `L`, `n` = player count.

```
damage *= 1.54                                   (0x3fc51eb8)
rank == 1:  hp *= 9.6 (0x41199999); damage *= 1.3 (0x3fa66666); attack *= 3; exp *= 4
n >= 2 and word 0x4f713c == 0:
    exp *= (n-1) + 1.0
    hp  *= (n-1)*0.6 (0x3f199999) + 1.0
    rank != 2 and a type name is present and it is not the exempt name (any case):
        damage *= (n-1)*0.15 (0x3e199999) + 1.0
rollHp:
    r  = own generator draw, unsigned, rem 5
    hp = single( (double(r) + 15.5) * double(powf(hp*L, 0.85)) )      library doubles, truncated
    level name is neither of the two fixed-scale names (any case):
        difficulty 2: *1.5   3: hp + hp   4: *2.5   5: *3.0
    maxHp = hp
armour  (+0xe4 s16) = trunc((armour*14.0)*L)
dmgLow  (+0xd0 s16) = trunc(damage * powf(L, 1.0))                    powf(L, 1.0) is L
dmgHigh (+0xd2 s16) = trunc((damage+damage) * powf(L, 1.0));  if < dmgLow+1: dmgLow+1
attack  (+0xd4 s16) = trunc((L*14.0)*attack)
exp     (+0xd8 float) = float(trunc(powf(exp*L, 1.322 (0x3fa9374b)) * 8.0))
Dead property: hp = 0, whether or not it was rolled (maxHp keeps its value)
```

The s16 stores keep the low 16 bits of the saturated conversion.

### 4.3 `creature_bossRank` 0x10d940

0 for a non-creature; with no type name, bit 0 of the creature flags; 2 when the type name
equals (any case) one of 13 names, a 14th, one of three name-plus-`name`-property pairs, or
one of two more; otherwise bit 0 of the creature flags (`MiniBoss`). The model reads the
names from the executable.

## 5. Experience for a kill — 0x111e3c–0x112248 in `Creature_processDamage`

```
sum = levels (+0x59, signed bytes) of slots 0..n-1
raw = trunc(powf(expValue / float(sum), 1.4 (0x3fb33333)))
a player made the kill:  chance = stat(0, adjust(rank 0x3b, 1))*0.01
    d = own generator draw; if float(d rem 65536) < chance*65536: kill orb if the pool has a block
                                                                  (its constructor draws S)
xp  = trunc(float(raw) * 0.75)
n < 2:   for the one slot, only if record hp > 0:
             xp = min(xp, cap(level));  giveExp(slot, xp)
             class 0: mana = min(mana + monster maxHp*(1/30), maxMana)       whoever made the kill
n >= 2:  for each slot in order:
             share = 0.5 if no player made the kill, 0.6 (0x3f199999) for the killer, 0.4 (0x3ecccccc) otherwise
             a = trunc(float(xp)*share);  record hp <= 0:  a = trunc(float(a)*0.5)
             giveExp(slot, min(a, cap(level)))
             class 0 and killer: the mana gain above
cap(level) = table[level+1] - table[level] below level 80, table[level] from 80 on
```

With several players `giveExp` is called for dead players too (half share) and for an
amount of 0. The mana gain is applied after `giveExp`, so after a level-up refill.

## 6. Levelling — `player_giveExp` 0x1d3150

`exp = min(exp + amount, table[80] − 1)`. While `table[level] ≤ exp`: skill points +1 below
level 6, +2 below 16, +3 below 26, +4 below 36, else +5; stat points (+0xec) +3; level
(+0x59) +1; `player_recalcStats`; if record hp > 0: hp = max hp, mana = max mana. The
threshold to leave level `l` is `table[l]` (81 entries at 0x41b558, read at run time).

## 7. Player statistics — `player_recalcStats` 0x1b6458

For every slot below the player count; a slot whose record has no object only gets
`effective = base`.

```
effective[0..3] (+0x90) = base (+0x78)                       strength, intelligence, dexterity, stamina
stagger (+0xdc) = 0
for the 17 equipped items (+0x43f0):  effective[k] += modifier 7+k;  stagger += modifier 0x1e * 0.01
object bonus bytes (+0x474+k): effective[k] - 30 for k = 0, 2;  effective[k] - 5 for k = 1, 3;  negative -> 0
armour (object +0xe4) = player_recalcArmor(slot)             section 8; it also changes effective[]
loadLimit (+0x124) = float(effective[0] + 125) + passiveLevel(mask 0x40)*15.0; +5000 if word 0x4d8ae8; max 9999
maxMana (+0xc4) = (float(effective[1]) - manaIntOffset)*manaPerInt + float(level)*manaPerLevel
maxHp   (+0xb0) = (float(level)*hpPerLevel + float(effective[3])*hpPerStamina) - hpOffset
mana = min(mana, maxMana);  hp = min(hp, maxHp)
```

`level` is +0x59. The six constants are float immediates selected by the class test chain
at 0x1b6740–0x1b694c; `ref_combat.read_class_formula` walks that chain in your executable.
The passive level is the byte at record +0xef + row for the first row of the class's
passive table whose mask matches (0 when negative).

## 8. Player armour and resistances — `player_recalcArmor` 0x1b5790

Not described in the earlier documents.

1. The object's five resistances (+0x5c…+0x6c) are zeroed.
2. Figurines: every one of the 64 slots of bag 2 whose definition has flag bit 45. The
   definition name is searched for four fragments that choose the statistic (0–3) and four
   that choose the amount per figurine: 5, 10, 20 or 25, and 15 when none matches.
   `effective[stat] += count · amount`. This runs after the bonus bytes were computed and
   before max hp, max mana and the load limit, so figurines raise those three but not the
   bonus bytes.
3. The 17 equipped items, except slot 3 (shield) while the active weapon set's primary
   weapon has subtype 4 (bow):
   - category 1 (armour): `AC += armour + trunc(float(armour)·(float(pct)·0.01))` with pct
     = modifier 0x0d (`item_getArmorValue` 0x103ec8); other categories: `AC += modifier
     0x0d` as a flat value;
   - resistance `k` += `modifier k · 0.01` for k = 0…4, then every resistance += `modifier
     0x2a · 0.01`;
   - record max hp += modifier 5, max mana += modifier 6.
4. Every resistance += `stat(0, adjust(rank 0x3f, 1))·0.01`, capped at 1.0.
5. Return `AC + effective[2] / 2` (signed, toward zero).

**Modifiers 5 and 6 (the `healthbonus` and `manabonus` item tokens) are overwritten.**
`player_recalcStats` stores its own max mana and max hp right after this call (0x1b69bc,
0x1b69c4) without reading the two fields in between, so what step 3 added is gone when the
function returns. Executed. Any other writer would be wiped by the next recalculation,
which runs on every equip, pick-up and level-up (Inferred); whether some reader adds the
modifiers itself is Unknown.

## 9. Player attack rating and weapon damage — `Player_recalcDamage` 0x1b7158

`(player object, weapon item or 0, flag)` writes record +0xcc (attack), +0xd0, +0xd4.

```
bs = strength / 4, bd = dexterity / 4            (effective, signed, toward zero)
attack = level58 * 20
no weapon:   min = bs + 1; max = bs + 2; attack += bs
weapon:
    (min, max) = item_getDamageRange(weapon, flag);  attack += item attack rating
    b = bd for subtype 4 (bow) and 6 (thrown), else bs;   min += b; max += b; attack += b
    f1 = 1.15 + 0.05*rank(0x3c) if that rank != 0 else 1.0     (0x3f933333, 0x3d4ccccc)
    f8 = the same with skill 0x3d
    subtype 4: s = stat(0, adjust(rank 0x30, 20))*0.01;  min += round(min*s); max += round(max*s)
    subtype 6: s = stat(0, adjust(rank 0x4f, 2))*0.01;   min += round(min*s); max += round(NEW min*s)
    second weapon equipped and subtype != 6:
        damage type 1: f1 *= (passiveLevel(0x40000)*2.5 + 100)*0.01;   type 8: f8 likewise
    damage type 1: min = trunc(min*f1 + 0.5); max likewise;   type 8: with f8
    class 4 and ((subtype 0, item flag bit 36 clear, damage type 8 or 4) or item flag bit 43):
        s = stat(0, adjust(rank 0x5c, 1))*0.01;  min = round(min*s); max = round(max*s)
AncestralCall: best = largest stat(0, level)*0.01 over the alive players' spells that reach this
    player (the owner itself, or within 12*stat(3, level) in x, y; enemy test in PvP mode A);
    best != 0:  min, max, attack = round(each * best)
f = 1.0
class 5 in state 1:
    frame - (+0x45c) < 27 and rank(0x47) > 0 and hp/maxHp <= 0.5:
        f = max(f, stat(1, adjust(rank, 20))*0.01 * min((frame - (+0x458))*(1/60), 1.0) + 1.0)
    BloodLust on the player with +0x2c set:  f = max(f, stat(1, level)*0.01 + 1.0)
class 6 in state 1 with GiantGrowth:  f = max(f, the spell owner's float at +0xdc)
min, max, attack = trunc(each * f)
status counter 2 (+0x374) != 0:  trunc(each * 1.5)
status counter 4 (+0x37c) != 0:  trunc(each * 1.2 (0x3f999999))
```

`round(x)` adds 0.5 for `x ≥ 0`, subtracts 0.5 otherwise, and truncates. In the thrown
branch the maximum grows by the share of the *already raised minimum*, not of the maximum
(0x1b7478). `item_getDamageRange` 0x104100: definition range × `(modifier 0x23 · 0.01 +
1.0)` when that modifier is non-zero; with the flag, `min += v1`, `max += v2` of modifiers
0x15, 0x16, 0x18, 0x17, 0x26 (each when its v1 ≠ 0); each end is `trunc(x + 0.5)`. Item
attack rating 0x103f88: definition +0x1a, plus `modifier 0x23 · 0.01` of it, truncated.

## 10. Worked examples

All computed by `tools/ref_combat.py` (default FPU model). Inputs are made up; statistic
callbacks return the numbers stated.

| Rule | Input | Result |
|---|---|---|
| base roll | min 20.5, max 30.25, draw 40000 | span 10.75, 40000 mod 10.75 = 10, dmg 30.5 |
| base roll, truncation | min 0.7, max 5.7, draw 3 | 0x406ccccc = 3.6999998 (round-to-nearest would give 0x406ccccd) |
| mitigation | armour 150, range 20–30 | cut 4.9999995 (0x409fffff); range 15.0–25.0. Armour 600: the half floor gives 10–15 |
| hit chance | attack 400, AC 900 | p = 0.66666663 (0x3f2aaaaa), threshold 43690.66 of 65536; rating scale 0.88888884 |
| a whole hit | seed 0x1234; player with a `SpellCriticalHit` and rank 3 (statistic 0 = 8), stun statistic 0; monster armour 168, fire resistance 0.25, no other resistance; 20–30, attack 400, flags 1; slots {0x15: 5–10}, {0x1d: 10} | eleven draws: 2756 (roll → 26), 62790 (first hit: p = 1.54, always a hit), 36705 (critical 18 %: no), 10756, 7657, 62550, 63982 (the four chance rolls, all fail against 0), 59823 (fire: 5 + 59823 mod 6 = 8, minus 25 % = 6), 7883 (second roll: hit), 19121 (stun: 21 ≥ 0, no), 10370 (number object). take-damage(32.0, flags 1); burn status 1.5; number "32", colour class 1; seed afterwards 0x2882dc75 |
| `amount(10, 5)` | draws 15496, 24200, 33046, 46195, 3312 | 10, 10, 12, 13, 10 |
| `amount(10, 9)` | the same draws | 15506, 24210, 33056, 46205, 3322 (zero divisor, as reported for the R5900) |
| monster | all factors 1.0, L = 12, one player, rank 0, own draw 3 | `powf(12, 0.85)` = 8.266164 (0x41044235); hp = 18.5 × that = 152.92403; armour 168; damage 18–36; attack 168; experience value 213 (`powf(12, 1.322)` = 26.710222, × 8, truncated) |
| monster | factors hp 1.5, armour 0.8, damage 1.2, attack 1, exp 2; L = 12, three players, rank 1, difficulty 2, own draw 3 | hp 4327.4717; armour 134; damage 37–74; attack 504; experience value 14269 |
| kill, two players | experience value 9000; levels 30 (alive, killer) and 34 (dead) | raw = trunc((9000/64)^1.4) = 1016; xp = 762; killer trunc(762 × 0.6) = 457; other trunc(762 × 0.4) = 304, halved = 152 |
| kill, one player | experience value 9000, level 30, class 0, monster max hp 900, mana 10 | raw 2937, award 2202 (below the cap); mana 10 + 900/30 = 39.999996 |
| level-up | a level-5 character 10 short of `table[5]` receives `table[6] − table[5] + 10` | two levels (5 → 7); skill points +1 and +2; stat points +6; hp and mana refilled to the new maxima |
| player statistics | class 0, level 10, base 30 / 12 / 21 / 30; armour item (armour 40; modifiers 0x0d = 25, 0 = 15, 10 = 4, 5 = 50); ring (modifiers 0x2a = 10, 0x0d = 7, 7 = 3, 0x1e = 20); two "10 per piece" stamina figurines | effective 33 / 12 / 21 / 54 (the figurines' 20 included); bonus bytes 3 / 7 / 0 / 29 (computed before the figurines); armour 40 + 9 + 7 + 21/2 = 66; fire resistance 0.25, the others 0.1; stagger 0.19999999; load limit 158; max hp 209.6 against 152.0 with nothing equipped — the difference is the 24 stamina, **not** the +50 modifier |
| player damage, unarmed | level 10, strength 40 | attack 210, damage 11–12 |
| player damage, weapon | the same, weapon 10–20, attack rating 30, damage type 1, modifier 0x23 = 20, modifier 0x15 = 3–6, skill 0x3c rank 4 | item range 12–24 (15–30 with elements), item attack 35; f1 = 1.3499999; attack 245, damage 34–54 |
| thrown-weapon quirk | weapon 10–20, subtype 6, dexterity 0, skill 0x4f statistic 50 | s = 0.49999997; min 10 + 5 = 15; max 20 + trunc(15 × s + 0.5) = 27 (not 30) |

## 11. What the differential test covers

`python3 tools/difftest_combat.py` (seed 20973; `--quick` runs a tenth). The original
function is executed on records the script builds; the model gets the same inputs; outputs
must be equal. Floats are compared as 32-bit patterns. **Every property below matched bit
for bit** under the interpreter's default FPU model and, on a smaller sample, under the
three other adder models and the multiplier-bias and divide-rounding switches (fourth
column). That shows the model does the same operations in the same order; it does not show
that either matches a console in the last bit.

| Property | Result | Cases (default FPU model) | Other FPU configurations | What is compared |
|---|---|---|---|---|
| fpu: model vs interpreter | PASS | 19,998 | – | add sub mul div sqrt int<->float compare, six configurations |
| soft double: int -> double | PASS | 4,000 | – | exact value compared; add, multiply and double -> single truncate toward zero |
| soft double: single -> double | PASS | 4,000 | – | exact value compared; add, multiply and double -> single truncate toward zero |
| soft double: add | PASS | 4,000 | – | exact value compared; add, multiply and double -> single truncate toward zero |
| soft double: multiply | PASS | 4,000 | – | exact value compared; add, multiply and double -> single truncate toward zero |
| soft double: fmod | PASS | 4,001 | – | exact value compared; add, multiply and double -> single truncate toward zero |
| soft double: double -> single | PASS | 4,000 | – | exact value compared; add, multiply and double -> single truncate toward zero |
| powf | PASS | 20,000 | 5 × 2000 cases | result pattern, bit for bit |
| sqrtf | PASS | 20,000 | – | result pattern, bit for bit |
| scalbnf | PASS | 20,000 | – | result pattern, bit for bit |
| cos16 / sin16 | PASS | 20,000 | – | result pattern, bit for bit |
| tables: passive masks | PASS | 7 | – | run-time table built by classSkills_init (executed) vs the model's reader |
| tables: experience curve | PASS | 1 | – | the model's reader vs interpreter memory |
| boss rank | PASS | 3,000 | – | returned rank; the name property supplied by a stub |
| level scale | PASS | 600 | 2 × 600 cases | stretch 0x1e5b88-0x1e5c98 of game_loadLevel; stored float, bit for bit |
| monster statistics | PASS | 6,000 | 5 × 500 cases | hp, max hp, armour, damage range, attack, experience value, own seed; bit for bit |
| monster statistics: no other store | PASS | 6,000 | – | hp, max hp, armour, damage range, attack, experience value, own seed; bit for bit |
| player statistics | PASS | 300 | 5 × 30 cases | every record and object field of all four slots |
| player statistics: no other store | PASS | 300 | – | every record and object field of all four slots |
| level-up | PASS | 300 | 5 × 30 cases | experience, level, points, maxima, refill; all four slots |
| level-up: levels gained | PASS | 300 | 5 × 30 cases | experience, level, points, maxima, refill; all four slots |
| player attack and damage | PASS | 300 | 5 × 30 cases | record attack rating and damage range; all four slots unchanged otherwise |
| item damage range, attack rating, armour | PASS | 242 | – | bit for bit |
| kill experience: ran to the exit | PASS | 2,500 | 2 × 250 cases | stretch 0x111e3c to the function's exit; bit for bit |
| kill experience: records | PASS | 2,500 | 2 × 250 cases | stretch 0x111e3c to the function's exit; bit for bit |
| kill experience: draws and seed | PASS | 2,500 | 2 × 250 cases | stretch 0x111e3c to the function's exit; bit for bit |
| kill experience: orb and level-ups | PASS | 2,500 | 2 × 250 cases | stretch 0x111e3c to the function's exit; bit for bit |
| damage: return value | PASS | 10,000 | 5 × 800 cases | bit for bit |
| damage: amounts handed to take-damage | PASS | 10,000 | 5 × 800 cases | bit for bit |
| damage: effects, in order | PASS | 10,000 | 5 × 800 cases | bit for bit |
| damage: shared-seed draws, in order | PASS | 10,000 | 5 × 800 cases | bit for bit |
| damage: seeds afterwards | PASS | 10,000 | 5 × 800 cases | bit for bit |
| damage: fields written | PASS | 10,000 | 5 × 800 cases | bit for bit |
| damage: no other store | PASS | 10,000 | – | bit for bit |

Run total: 104 properties, 0 failed, 304 s (full sample, one machine).

Paths of the damage function reached in the default-model sample (number of cases; for the three "range" lines, number of ranges drawn):

PvP mode A 1161, cast 216, critical shown 251, damage-over-time delivery 390, disease 597, frost armor strike 308, gas 175, interpreter continued past a zero divisor 253, kill proc 114, light 547, miss on the second roll 718, nested hit 838, non-creature victim 799, player victim 3126, pool refused a block 318, range with v2 < v1 - 1 1084, range with v2 >= v1 2931, range with zero divisor 389, reflection 270, retribution number 109, returned 0 2100, roll with a zero span 91, sparks 583, spirit shield absorb 130, stun 600, take_damage 9759, text 1688, thorns 338, undead_shield 45, voice 588.

What runs for real: the functions under test and every helper named in sections 3–9, the
C library, the object and spell constructors (so their shared-seed draw is executed code),
`classSkills_init`, the type-info getters. What is stubbed, and so **not** covered:

- every virtual call: take-damage (the amounts and flags handed to it are compared, what
  the victim does with them is not), Skill statistics (the stubs return test-chosen values,
  0–127; no real skill table was used), skill cast for type 0x29, the stun slot, "is
  enemy", the model lookup of thorns;
- `SpellUndeadShield` / `SpellSecondaryUndeadShield` strikes (0x2eaec0, 0x2eb5b4): only the
  call and its arguments are compared;
- sounds, particles, text formatting, handle bookkeeping (the status-source link is
  compared as a call sequence), the pool allocator (the test decides whether a block is
  available, so both outcomes are covered, the allocator itself is not);
- inside the damage group, `creature_bossRank` (tested on its own, with the `name`
  property supplied by a stub).

Inputs the test does not generate: a null victim; an attacker with flag 0x80 whose link
points at a null owner; skill ids outside 1–101 in a type-0x29 slot; a player class outside
0–6; the two unbounded recursions of 3.5; the parts of `Creature_processDamage` before
0x111e3c (who the killer is, is an input here). Not modelled at all: `Player_meleeHit`
0x1b6a98 (which scales the record's values for heavy attacks before calling
`damage_apply`), `Creature_scaleStats` 0x1185d8, the `monsters.bal` lookup, regeneration,
and the take-damage implementations.

Interpreter gaps met: none that needed a work-around. Integer division by zero needs
`div_zero = 'r5900'` to continue (3.1); a runaway recursion ends as a memory fault below
the interpreter's stack rather than as a clean error.

## 12. Corrections and additions to earlier documents

| Document | Was | Is | Evidence |
|---|---|---|---|
| `docs/data-tables.md` §3.2 | hit points "double arithmetic, then to float"; `pow` | `powf` (single precision) for the power; only `(r + 15.5) × power` is in the library doubles, which truncate; `powf(L, 1.0)` is exactly `L` | 0x10a78c, 0x10a7cc, 0x10a7d8; section 1.2 |
| `docs/data-tables.md` §3.2 | damage scaling unless type name is "droid" | also skipped when the object has no type name; the compare ignores case | 0x10a720, 0x10a72c |
| `docs/data-tables.md` §3.2 | `Dead`: hp = 0 | also when hit points were not rolled (last argument 0) | 0x10a980 |
| `docs/data-tables.md` §3.5, `docs/issues/kill-loot-xp.md` step 8 | class 0: "the killer also gains mana" | with one player the mana gain needs no killer; with several it is the killer only | 0x112200, 0x112100 |
| `docs/data-tables.md` §4.3 | statistics are base plus item modifiers 7–10 | plus figurines (bag 2, flag bit 45), added by `player_recalcArmor` between the bonus bytes and the maxima | section 8 |
| `docs/data-tables.md` §4.5 | multiplier half "read from the decompile only" | executed; the thrown branch raises the maximum by the share of the new minimum; the dual-wield passive multiplies only the type-1 or type-8 factor | section 9; 0x1b7478 |
| `docs/data-tables.md` §5, first row | "3.0 in PvP mode B" | only on difficulty 1; difficulties 2–5 overwrite it from the level byte | 0x1e5ba4–0x1e5c48 |
| `docs/data-tables.md` §8, §11 | `player_recalcArmor` "not read" | section 8; modifiers 5 and 6 are overwritten by the caller | 0x1b5790; 0x1b69bc, 0x1b69c4 |
| `docs/gameplay.md` §2.5 step 4, 10 | roll "in double precision" | span in single precision; the doubles are the truncating library routines; a zero span gives 0x7f800000 | section 3.4 |
| `docs/gameplay.md` §2.5 step 16 | Frost Armor strikes the attacker (amount not given) | the strike is a cold slot of `trunc(dmg − factor)` | 0x318364–0x318378 |
| `docs/gameplay.md` §2.5 step 18 | bonus from "three skill values" | the attacker's own rank counts only while a `SpellCriticalHit` is attached to it | 0x2e76f8–0x2e7714 |
| `docs/gameplay.md` §2.5 step 20 | type 0x29: "draw; success casts" | the test is `S < v2 × 655`, so 100 % is 65500 / 65536 | 0x1e8ebc–0x1e8ed8 |
| `docs/gameplay.md` §2.5 step 27 | "possibly deliver" | delivery only on `frame & 31 == 0`; the amount is at least 1 and whole; take-damage is called again with 0 | 0x1ea700–0x1ea790 |
| `docs/gameplay.md` §2.2 | ranges "min – max" | `v2 < v1` yields values from `v1` upward; `v2 = v1 − 1` divides by zero | section 3.1 |
| `docs/issues/dynamic-tests.md` §1 | (floating point) "the one place the interpreter approximates" | add: the executable's double routines are integer code, so they are executed exactly — and they truncate | section 1.2 |

No patch is proposed: nothing here was found to differ between machines. Proposed ledger
rows (kind *Executed in isolation*):

| Proposed | Claim | Evidence |
|---|---|---|
| new | With equal inputs (the records, objects, seeds and globals named in sections 3–9) the damage function, monster statistics, kill experience and its split, level-ups and the player's derived statistics produce equal amounts, draws and fields, and they store nothing outside the fields named here. Three of those inputs are per machine: the damage-number option (it only matters when the game is not a net game), the camera focus (a counter nobody reads) and whether the pool has a block. Reads were not audited, only stores | `tools/difftest_combat.py`, the "no other store" properties |
| new | The executable's soft-float double routines truncate; a port that uses host doubles gets different hit points and damage rolls in the last bit | section 1.2 |
| new | `healthbonus` / `manabonus` modifiers are summed and then overwritten in `player_recalcStats` | section 8 |
| new | A range with `v2 = v1 − 1` in an elemental slot divides by zero inside lockstep code; consoles and emulators need not agree on the remainder | section 3.1 |

## 13. Not done

- The console's result for the zero divisor, and the last bit of FPU sums on hardware.
- Whether `healthbonus` / `manabonus` are applied by a reader of the record.
- `Player_meleeHit`, the take-damage functions, `Creature_scaleStats`, regeneration, and
  the undead-shield strikes are not modelled.
- Real skill statistics were not connected: the model takes them as callbacks.
- Who sets word 0x4f713c and word 0x4d8ae8 (both only read here).
