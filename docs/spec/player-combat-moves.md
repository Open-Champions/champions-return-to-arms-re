# Player combat moves — SLUS-20973 US v2.00

2026-10-23. Branch `t3/research-combat-moves` starts at research main
`034d0c0`. This is a port map of the original Player code, not a new combat
system. **Observed** means read at the listed original address. **Executed**
means original instructions ran in `tools/ee_emu.py` on constructed state; it
does not establish a console or level-loaded fight. **Ran** is reserved for the
separate Play! capture cited below. **Unknown** stays open.

Sources already on main: `docs/spec/player-tick.md` / `tools/ref_player.py` and
`tools/difftest_player.py` for `Player_run` 0x1a5030; `docs/spec/combat.md` /
`tools/ref_combat.py` for `damage_apply` 0x1e8230 and
`Player_recalcDamage` 0x1b7158; `docs/spec/creature-tick.md` for target
reactions. Cross-branch evidence, not merged here: campaign combat
`328b072` (`Player_meleeHit` → damage → WarBoar, plus an assisted live kill),
player animation `4ad5721` (weapon row and action-state selector), and
combat walk `e20760a` (melee-to-walk timing). The `t3/research-combat*`
branches retain constructor/runtime studies. Their native fixture and the
optional Souls combat mode are not evidence of extra original moves.

## 1. Inputs and action states

**Observed** (`Player_run` 0x1a5030–0x1a5e80): a selected pad has per-slot
held and pressed words; attack mask table is 0x41b980, block 0x41b9d0,
swap 0x41ba30, and two ability masks 0x41b990/0x41b9a0. Dialog, spawn
protection, cutscenes and other gates can replace it with the zero pad
(`player-tick.md` section 2). The active set is record `R+0x4a7c`; the
weapon animation class is `R+0x4a86`; `P+0x58c` is the state. State 2 is
neutral, 1 melee, 0 bow/throw, 8 guard, 0xb guard move, 3 hit reaction,
4 death, 5 cast, and 10 the older ground-pound action. The model index at
`R+0x54` selects the body/animation definition independently of the
weapon class (player-animation `4ad5721`, `Player_ctor` 0x1a1d98).

## 2. Basic melee and combo

**Observed** (state 2 0x1a76c0–0x1a7fbc; state 1
0x1a9678–0x1aafe0): outside bow/throw classes, a pressed attack starts
state 1 after the minimum delay `P+0x48c × 60 ≤ frame − P+0x448`.
The delay is 0.15 s with an ordinary primary weapon and 0.33 s unarmed
or with item definition class 4. The first swing selects row clip
`class*0x68+0x74`, variant 1, and stores its frame at `P+0x448`.
The class-2 sweep and heavy attack use different hit paths below.

| Weapon animation class (`R+0x4a86`) | Combo steps | Other observed difference |
|---:|---:|---|
| 0 one hand | 7 | ordinary reach 48 |
| 1 two hand kind 1 | 7 | reach 58; after 60 frames of the swing, hit flag 0x1000 |
| 2 two hand kind 2 | 4 | sweep on step 3, through target list `P+0x4b8` |
| 3 long weapon | 9 | reach 58 |
| 4 bow | 7 | ordinary state is ranged; close target can enter state 1 |
| 5 unarmed | 2 | ordinary reach 48 |
| 6 thrown | 7 | ordinary state is ranged; close target can enter state 1 |
| 7 dual wield | 7 | shorter combo window; alternate weapon on odd steps when passive 0x40000 is ranked |

For classes 0/1/3/5/7 the normal hit is at
`t == trunc(16.02 / swingSpeed)` offline. In a net game it is at `t == 1`
only if `P+0x55c == 0`; guard sets that counter to 16 and each melee tick
reduces it. **Observed/Executed** in `player-tick.md` 6 and 12. A class-2
weapon instead builds a forward target list on combo step 3 and sweeps
through it from its speed-adjusted sweep frame. Target selection scans a
48-unit box (58 for classes 1/3), looks within a 60-degree half-angle
(`dot ≥ 0.5`), and picks the lowest distance/facing score. The hit function
checks line of sight for an ordinary scale-zero attack. Prediction copies
cannot apply it (`Player_meleeHit` 0x1b6ae8).

The next swing needs a fresh attack press after the window:
`(22.02 − min(haste*60*0.5,17.4)) / swingSpeed` frames; dual wield starts
at 17.616 before the same trim. The combo step rises and caps at the
class's length minus one; `Player_pickAttackAnim` 0x1bba88 picks the
variant from model index, weapon class, old variant and frame hash. It
draws the shared seed once but does not use that draw for selection.
**Executed** by `difftest_player.py`; see `player-animation-selection.md`
on `4ad5721`. A held stick above 0.8 ends a swing at 39.3 frames;
otherwise the ordinary 1.6 s action deadline is 96 frames. A new combo
swing restarts that deadline. `difftest_combat_walk.py` on `e20760a`
executed the 40-tick walking resumption and indefinite 12-frame mash
when each press restarts a swing.

### Damage for each hit

**Observed** (`Player_meleeHit` 0x1b6a98–0x1b7118; `Player_recalcDamage`
0x1b7158): every hit selects the primary weapon, or the second weapon on
odd dual-wield combo steps with passive 0x40000, then recalculates attack
rating `R+0xcc` and bounds `R+0xd0/+0xd4`. It takes damage-class bits
from the item definition `+0x20` (1 unarmed), passes the item as the
on-hit descriptor, and calls `damage_apply` 0x1e8230. Normal swings carry
knockback-class flag `0x40000`. There is no observed per-combo-step
damage multiplier in this path: step changes the chosen weapon and clip,
while the same recalculation and bounds reach the resolver. Class skills,
item modifiers and buffs can still change those bounds. The full formula
is `combat.md` section 9: strength contributes to melee, dexterity to bow
and throw; class 4 has an additional weapon conditional, class 5 gains
Berserker Rage/Blood Lust factors in state 1, and class 6 can gain Giant
Growth. Archery and Throwing passives, Ancestral Call, damage-type
passives and status counters also feed it.

**Executed here:** `tools/difftest_combat_moves.py` runs `Player_meleeHit`
with the real `skill_rankScale` helper and stubbed recalculation/resolver.
With constructed 10–20 bounds, attack 100 and a zero rank-scale input,
steps 0–3 all hand off 10–20. A heavy request `P+0x44c=2` adds 90% of
each bound to produce 19–38 and adds flag 0x200000. An explicit
scale 0.5 (the Cyclone-style caller) yields 5–10 normal or 10–19 heavy
after rounding and uses flag 0x80000 instead of 0x40000. This probe
does not claim those zero-rank inputs are a legal equipped character or
prove the full hit resolver; `difftest_combat.py` verifies the latter.
**Unknown:** a complete table of actual damage by combo step across
equipped items, skill ranks, target armour and seeds; it cannot be one
universal number.

## 3. Guard and special attacks

**Observed** (`Player_run` 0x1a5e2c, 0x1a60e0, 0x1a7ff0;
`player_canBlock` 0x1bee48): held block requests state 8 when the
level's 0x10000000 veto is clear and the player has a weapon or shield
in equipment slot 0, 2 or 3. A class-4 bow in slot 2 prevents it.
The blocking byte is `P+0x47f`; the state starts guard clips from the
weapon row. A release returns to neutral once the top track reaches its
marker. Pressing swap while holding block calls `Player_tryBlockMove`
0x1bf150: state 0xb, evade clip at row `+0xa4`, and 47 frames of stick
lock. `R+0x4a5c` grows in neutral and shrinks in
guard; no gameplay reader is known (`player.md`), so it is not a stamina
bar or guard resource.

**Observed/Executed here** (`Player_takeDamage` 0x1b5440–0x1b5628): in states 8 or
0xb, a hit from the front is reduced to zero, or half with damage flag
0x20000; flag 0x40 bypasses the guard. This is separate from
`damage_apply`'s guard for a creature carrying flag 0x200 and facing its
attacker (`combat.md` section 3 step 11), with the same zero/half and
0x40 rules. Armour and hit/critical rolls are handled by `damage_apply`,
not by a stamina cost. **Unknown:** an exact live player-versus-player
guard trace from an unmodified campaign session.
`difftest_combat_moves.py` compares 18 constructed front/back,
neutral/guard/guard-move and flag cases per seed, with real direction
helpers and the original `Player_takeDamage` body. A 25-point front hit
becomes 0 in states 8/0xb, 12.5 with flag 0x20000, and 25 with flag
0x40; a rear hit remains 25. In state 8, with flag 0x40 clear, the
function advances the shared seed once at 0x1b54b8 even when the
attacker is behind; state 0xb makes no such draw in these cases.

**Observed** (`Player_run` state 2 0x1a71f8–0x1a7544): old ability
id 0x25 starts a heavy attack only on the ground, with a usable record,
enough mana and fewer than six tracks. It pays the skill's mana cost,
sets `P+0x44c=2`, uses row clip `+0x64`, has one combo step and a
0.857 s action length. `Player_meleeHit` adds the rank-scaled bonus,
flag 0x200000 and sparks on a creature target. Old id 0xc starts the
ground-pound state 10: animation event bits 1/2/4 call
`world_damageInRadius` and bit 8 creates its effect (0x1a6818–0x1a6950).
Old id 0xe starts the war cry in state 0xc. New `Skill` records use
`Player_castSkill` 0x1a42b8 and state 5, except kind 7 instant and kind
8 next ranged release. These are skill-specific attacks, not additional
universal light-combo buttons; their effects and costs are catalogued in
`docs/spec/skills-01-34.md`, `skills-35-68.md` and `skills-69-101.md`.
The old inline record id 0x25 is a different dispatch path from the
new-style `Skill` object whose numeric id is 37 (Shock). Do not merge them
by number alone.

**Observed class-tree availability** (`skills-35-68.md` section 1.7,
`skills_screen` 0x1d4660; class names **Inferred** from tree pictures):
the weapon state machine above is shared, while learned actions vary.

| Record class (`R+0x50`) | Direct combat abilities relevant to the move port |
|---:|---|
| 0 barbarian | Charge 35, Ground Pound 38, Cyclone 41, Bash 49; Strong Stance 62 and Stunning Strike 64 modify reactions |
| 1 cleric | Holy Shield 54; damage/heal skills use the common cast route |
| 2 shadowknight | Darkness 36, Harm Touch 42 (next melee hit), Bash 49, Shadow Step 67 |
| 3 ranger | Fire/Cold/Poison Arrow 43–45, Multi Fire 46, Explode Arrow 47; Archery 48 modifies bow damage |
| 4 wizard | Shock 37 and other cast attacks; its class-4 weapon conditional also changes `Player_recalcDamage` |
| 5 berserker | Berserker Rage 71 modifies swing speed and damage; Throwing 79 modifies thrown damage; the skill table also has Berserker Cyclone 84 |
| 6 shaman | Giant Growth 65 modifies state-1 damage |

This table names the move-relevant routes, not every spell in the seven
skill trees. Each skill's target, statistic, projectile, mana cost and
effect is in the three skill specifications. Weapon class and character
class are separate fields, so a character class does not imply a fixed
combo length or attack animation.

## 4. Bow and thrown weapons

**Observed** (`Player_run` state 2 0x1a76c0–0x1a7fbc, state 0
0x1a80e0–0x1a9598): weapon classes 4/6 enter ranged state 0 from the
attack/ability mask. For record classes 0/2/3, one own-seed draw gives
a 10% close-melee attempt; missing ammunition also takes that branch.
With a target within 60, the bow uses `b_attackb` and the thrown weapon
an unarmed-style melee clip in state 1. Otherwise class 4 needs an
ammunition pointer; class 6 marks shot kind 7. The old inline arrow
abilities (ids 4/5/6/0x13/0x12) set shot kinds 1/2/3/5/6.

The throw releases at `trunc(11 / speed)` frames offline; the bow at
`trunc(22 / speed)`. In a net game the bases are 5 and 11. Speed includes
twice the primary weapon's 0x14 haste modifier and slow effects. On
release, a throw targets to 300, creates a `playerProjectile`, consumes
one thrown item and can substitute a waiting kind-8 skill. Bow release
targets to 300, performs a 340-range/20-degree arc query, then creates
`MissileWeapon` or casts a waiting skill. It consumes one arrow except
for the recorded skill-0x2e reduction. Both paths draw the shared seed
for spread/aim and use the record's **stored** attack/damage fields;
`Player_weaponSwapInput` refreshes those earlier in the tick, subject
to the pause/menu gate. See `player-tick.md` state 0 and
`kill-loot-xp.md` section 1 for call sites and copy guards.

## 5. Target reactions and port order

**Observed/Executed** (`damage_apply` 0x1e8230;
`Creature_takeDamage` 0x116638; `Creature_processDamage` 0x110d30):
the resolver applies armour, two hit rolls, item procs, criticals and
resistances before the victim's take-damage slot. A positive hit
immediately reduces creature HP and accumulates amount `+0xc8`, flags
`+0x2dc` and last attacker `+0x2e4`. On its later tick, a surviving
creature's first knockback flag chooses speed 100/150/225/375 for
0x40000/0x80000/0x100000/0x200000; reaction state 0x12 is forced
for the strong flag group unless protected. These are victim effects,
not a fixed knock distance. The player-target version uses
`Player_processDamage` 0x1b2cc0 and speeds 100/150/200/250 offline,
halved in PvP mode A; net players do not move by that knockback
(`movement-camera.md` section 4). Skill 0x40 can also roll a stun:
`damage_apply` calls victim slot 30 for roughly 90–150 frames; boss
ranks restrict it (`combat.md` section 3.2). An ordinary melee hit
does not guarantee a stun. `328b072` **Ran** an assisted Valor boar
hit through the original chain, including positive HP change; the
health support and scripted entry limit it as normal-campaign proof.

Ordered native port list:

1. Preserve the real player record, equipped item definitions, class
   index, active set and `R+0x4a86` handoff from equip; select clips by
   `R+0x54` definition plus weapon row (`4ad5721`).
2. Port pad selection/gates, state 2 attack/ability/guard request, and
   states 0/1/8/0xb with their frame stamps, animation markers, target
   search, combo variant, sweep list and net `+0x55c` rule.
3. Port `Player_recalcDamage` and the exact item/skill inputs, then
   `Player_meleeHit`, projectile release constructors and the
   `damage_apply` call contract. Preserve the prediction-copy refusal.
4. Port `Player_takeDamage`/`Creature_takeDamage`, pending flags and
   next-tick reactions, including guard, knockback, stun and death.
5. Integrate world, terrain, animation, pool, seed and real-level services;
   compare an unassisted normal-route fight and all weapon classes.
   Function-level equality and the assisted Valor capture do not close
   this last runtime gate.

No game bytes, disassembly, decompiler output, or resource names from a
private image are included here.
