# Combat and statistics rules: a tested reference

US `SLUS_209.73` v2.00. This is the implementer's version of the rules that decide a fight:
the damage function, monster statistics, experience, and the player's derived numbers. It
is the prose form of `tools/ref_combat.py`; `tools/difftest_combat.py` runs the original
machine code under `tools/ee_emu.py` and compares it with that model.

Evidence labels: **Executed** = the game's own instructions were run in the interpreter on
constructed state and the model agreed (section 11 says for which inputs); **Observed** =
read at the address given; **Inferred**; **Unknown**. "Executed" says what the code does
with those inputs, not that the inputs occur in play; nothing here was seen on a console.

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
0.01 is 0x3c23d70a. The last bit of sums on real hardware is not established
(`docs/issues/dynamic-tests.md`); the model and the interpreter share four selectable adder
models and agree under each.

**1.2 Doubles go through library routines, and those are not IEEE either.** Executed
(`soft double` properties): int → double 0x3afa08 and fmod 0x3a5a38 are exact; single →
double 0x3aef58 reads exponent field 255 as an ordinary number and field 0 as zero; add
0x3af410 and multiply 0x3af4d0 **truncate toward zero** to 53 bits; double → single
0x3afb90 **truncates toward zero** to 24 bits, gives zero below 2^-126 and the pattern
0x7f800000 from 2^129 up and for a not-a-number. Two rules use them: the damage roll (3.4)
and the monster hit-point roll (4).

**1.3 `powf` 0x3a5ac8 → 0x3a7930.** The usual single-precision power kernel, built with the
FPU above, the NaN and infinity tests removed and "zero" widened to "exponent field 0".
`powf(x, 1.0)` returns `x` unchanged, `powf(x, 2.0)` is `x·x`, `powf(x, 0.5)` for `x ≥ 0`
is the bit-by-bit `sqrtf` 0x3a84c0. Otherwise the result is close to, but not, the
correctly rounded power (1234.5^1.4 comes out as 0x46a64b59 = 21285.674, the real value is
21285.680), so a port must copy the kernel operation for operation — `ref_combat.powf`
does, with `scalbnf` 0x3aa810.

**1.4 The generator.** `state = state·0x19660d + 0x3c6ef35f (mod 2^32)`, a draw is the
upper 16 bits of the new state. Three users here: the shared seed 0x404464 (in the sync
hash), the cosmetic seed 0x404460 (per machine), and each object's own seed at +0x44
(seeded by one shared draw in the object constructor).

## 2. `damage_apply` 0x1e8230 — interface

`damage_apply(min $f12, max $f13, victim $a0, attacker $a1, attack $a2, –, –, flags $t1,
descriptor $t2, noCrit $t3)`; returns 0 when nothing landed, else 1. Layouts of the
arguments are in `docs/gameplay.md` §2.1–2.4 and were confirmed by execution; the
differences found are listed in section 12.

Descriptor: four effect slots `{s16 type, v1, v2, v3}` at +0x24 + 8·i; every lookup takes
the first slot of the wanted type and reads 0 when there is none. For a melee hit the
descriptor is the weapon's item record, so the slots are its modifier slots.

Calls out of the function that a port has to provide:

| What | How the original reaches it |
|---|---|
| take-damage(amount, attacker, flags) | victim virtual slot 2 |
| class of an object, class of a spell | virtual type-info getter, compared by name |
| skill statistic | Skill slot 10 `(stat, level)`, slot 12 `(stat, level, caster, cap)`, slot 14 `(level, n)` → level |
| cast a skill (type 0x29) | Skill slot 2 `(level, caster, pos, facing)` |
| stun | victim virtual slot 30 `(frames, 1)` |
| "is enemy" (PvP only) | creature virtual slot 22 |

## 3. `damage_apply` — order of operations

`dmg` is the running amount, `S` one draw from the shared seed, `C` draws from the cosmetic
seed. Everything is single precision unless it says double.

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
    +0xf0 = frame counter. (Two kind-0x10 creatures that both have +0x39c > 0 recurse
    without a bound other than a missed roll or `dmg ≤ 0` — Observed, not executed.)
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
19. Only if `hit`, in this order (the chance rolls happen whether or not the slot exists;
    a chance is `float(S) < v1·0.01·65536`; `src` is the attacker if it is a creature):
    - 0x29, creature attacker and `v2 ≠ 0`: **S**; if `S < v2·655`: cast skill `v1` at
      level `v3` from the attacker's position and facing;
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
    the code, "hp > 0 and hp ≤ 0", can never hold.)
26. Hit sound unless flag 0x4000; **take-damage(dmg, attacker, flags)**.
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
  `(10, 5)` gives 10…13. Executed.
- `hi = lo − 1`: division by zero. The CPU does not trap. The interpreter refuses to guess
  unless told to continue with what the R5900 is *reported* to leave (remainder =
  dividend), in which case the amount is `lo + S`, up to 65535 more. The model follows that
  report so the two can be compared; **the console's result is not established.**

### 3.2 Helpers

| Helper | Rule |
|---|---|
| critical bonus 0x2e76c4 `(skill, attacker, rank)` | level = `rank` if `rank ≠ 0` and the attacker carries a `SpellCriticalHit`; otherwise the first other alive player (list order) within 1000 units (3-D, squared test `< 1e6`), an enemy test in PvP mode A, carrying the spell, with `r = max(rank 0x35, rank 0x51, rank 0x21) ≠ 0` and within `12·stat(1, r)` in x, y — level = `r` if positive. Bonus = `stat(0, adjust(level, 20))·0.01`, or 0 when the adjusted level is 0 |
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
disease resistance. Class = 2 if immune, else 1 if resisted, else 0. Note that **any**
non-zero resistance colours the number, whatever the damage type.

### 3.4 The base roll

`span = (max − min) + 1.0` in single precision; then in the library doubles
`dmg = single(double(min) + fmod(double(S), double(span)))`, truncated. `S` is used as the
unsigned 16-bit draw. A span of exactly zero (possible only on the non-creature path, with
`max = min − 1`) makes `fmod` return a not-a-number and `dmg` the pattern 0x7f800000,
which the FPU treats as 2^128.

## 4. Monster statistics — `Creature_setStats` 0x10a620

Inputs: the five factors of `monsters.bal` (hp, armour, damage, attack, experience; 1.0 =
100 %), `rank` = `creature_bossRank`, `L` = the level's monster level (float 0x4f714c),
`n` = player count.

```
damage *= 1.54                                   (0x3fc51eb8)
rank == 1:  hp *= 9.6 (0x41199999); damage *= 1.3 (0x3fa66666); attack *= 3; exp *= 4
n >= 2 and word 0x4f713c == 0:
    exp *= (n-1) + 1.0
    hp  *= (n-1)*0.6 (0x3f199999) + 1.0
    rank != 2 and type name present and not the exempt name:
        damage *= (n-1)*0.15 (0x3e199999) + 1.0
rollHp:
    r  = own generator draw, unsigned, rem 5
    hp = single( (double(r) + 15.5) * double(powf(hp*L, 0.85)) )      library doubles, truncated
    level name is neither of the two fixed-scale names (case-insensitive):
        difficulty 2: *1.5   3: hp + hp   4: *2.5   5: *3.0
    maxHp = hp
armour  (+0xe4 s16) = trunc((armour*14.0)*L)
dmgLow  (+0xd0 s16) = trunc(damage * powf(L, 1.0))                    powf(L, 1.0) is L
dmgHigh (+0xd2 s16) = trunc((damage+damage) * powf(L, 1.0));  if < dmgLow+1: dmgLow+1
attack  (+0xd4 s16) = trunc((L*14.0)*attack)
exp     (+0xd8 float) = float(trunc(powf(exp*L, 1.322 (0x3fa9374b)) * 8.0))
Dead property: hp = 0 (maxHp keeps the rolled value)
```

The s16 stores keep the low 16 bits of the saturated conversion. `creature_bossRank`
0x10d940: 0 for a non-creature; with no type name, bit 0 of the creature flags; 2 when the
type name equals (case-insensitive) one of 13 names, a 14th, one of three name-plus-`name`
-property pairs, or one of two more; otherwise bit 0 of the creature flags (`MiniBoss`).

## 5. Experience for a kill — 0x111e3c–0x112248 in `Creature_processDamage`

```
sum = levels (+0x59, signed bytes) of slots 0..n-1
raw = trunc(powf(expValue / float(sum), 1.4 (0x3fb33333)))
killer made the kill (a player): chance = stat(0, adjust(rank 0x3b, 1))*0.01;
    d = own generator draw; if float(d rem 65536) < chance*65536: kill orb if the pool has a block
xp  = trunc(float(raw) * 0.75)
n < 2:   for the one slot, only if record hp > 0:
             xp = min(xp, cap(level));  giveExp(slot, xp)
             class 0: mana = min(mana + monster maxHp*(1/30), maxMana)
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
at 0x1b6740–0x1b694c (a class index outside 0–6 keeps the chain's defaults).

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

**Modifiers 5 and 6 are overwritten.** `player_recalcStats` stores its own max mana and max
hp right after this call (0x1b69bc, 0x1b69c4), and nothing reads the two fields in between,
so the flat hit-point and mana modifiers summed in step 3 have no lasting effect through
this path. Executed. Whether another path applies them is Unknown.

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

`round(x)` adds 0.5 for `x ≥ 0`, subtracts 0.5 otherwise, and truncates. Note the thrown
branch: the maximum grows by the share of the *already raised minimum*, not of the maximum
(0x1b7478). `item_getDamageRange` 0x104100: definition range × `(modifier 0x23 · 0.01 +
1.0)` when that modifier is non-zero; with the flag, `min += v1`, `max += v2` of modifiers
0x15, 0x16, 0x18, 0x17, 0x26 (each when its v1 ≠ 0); each end is `trunc(x + 0.5)`. Item
attack rating 0x103f88: definition +0x1a, plus `modifier 0x23 · 0.01` of it, truncated.

## 10. Worked examples

Filled in by running the model; see the end of this file (section 14).

## 11. What the differential test covers

See section 13 (written from the test's output).

## 12. Corrections to earlier documents

See section 15.
