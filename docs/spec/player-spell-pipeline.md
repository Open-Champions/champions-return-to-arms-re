# Player spell pipeline — SLUS-20973 v2.00

Research synthesis, 2026-10-23, branch `t3/research-spells` from main `034d0c0`.
This is a port contract for player-controlled spells. The original instructions are
read at the addresses below; the cited reference models execute individual functions
against `tools/ee_emu.py` on constructed state. A function-level comparison does not
establish a playable native cast or an unbroken whole-game damage path.

**Evidence labels.** Observed = read in the original instructions at the address
shown. Executed = original and reference called in `ee_emu.py` with compared calls,
stores, seed and result. Inferred = composition of separate observations. Unknown =
neither instruction tracing nor the bounded comparisons settled it.

## 1. Selection and request

| Step | Evidence | Address and state |
|---|---|---|
| Raw D-pad opens a local selector after menu, dialog, camera, pause, memory-card and task gates. Direction + ability A/B sends quick-slot message 0. Direction + Use sends quick-cast warning message 13. A direction also masks A/B/Use in local input for three frames. | Observed; Executed in `t3/research-hud-inputs` `44c6720`, `difftest_hud_inputs.py` and predecessor `difftest_hud_quickslots.py` | `hud_spellSelect` 0x1dd270; `net_maskLocalButtons` 0x13e540; raw pads 0x4028d0 + 0x58·slot; button masks 0x41b990/0x41b9a0/0x41b9c0 |
| Message 0 changes quick-slot index A or B, swapping a duplicate assignment. Message 13 queues a forced record only in neutral state; kind 1 gets a warning instead. | Observed; Executed in pinned HUD branch | `hud_onQuickSlot` 0x1de28c; message 13 handler 0x1de340; record `R+0x4a84/85`; forced pointer `P+0x488` |
| Ability A/B pressed in the lockstep pad chooses the matching quick-slot index and a 0x68-byte record. The last chosen button is retained. | Observed; Executed in `ref_player.py`/`difftest_player.py` | `Player_run` 0x1a5030, input 0x1a5768–0x1a5b10; `R+0x4a60`, `R+0x4440 + 0x68·index`; pad 0x41bfd8 + 0x58·slot; ability masks 0x41b990/0x41b9a0 |
| The record's id selects `g_skillTable[id]`; kind is copied from skill+8 when assigned. Kind 7 casts immediately, kind 8 waits for a ranged release, ordinary kinds enter cast state 5. | Observed; Executed for the player state machine | `R+0x4440 + 0x68·index`, id +0x20, kind +0x25; `g_skillTable` 0x41b170; `hud_onAssignSpell` 0x1de61c; `Player_run` 0x1a7034–0x1a709c, 0x1a837c, 0x1a9174 |

`R` is `g_players + 0x4c30·slot` (base 0x4d8af0), `P` the player object.
The selector is a local HUD task; its message must enter the simulation through
the existing message/input path. `g_spellSelectorHeld` 0x41b818 additionally gates
`Player_interact` at 0x1a5c08–0x1a5c1c. It is not a cast cooldown (Observed).

## 2. Admission, timing and mana

| Rule | Evidence | Address |
|---|---|---|
| `canUse` is skill virtual slot 1. The requested rank is Player slot 39; mana cost is Skill slot 5. A request with insufficient `R+0xc0` is refused. Kind 1 needs half its listed cost to start. | Observed; Executed through `ref_player.py`/`difftest_player.py`; per-skill costs in `ref_skills_[abc].py` | `Player_run` 0x1a5c6c–0x1a5e28, 0x1a6f84–0x1a6f90; skill table +0x60; Player slot 39 0x3c3b40 |
| Recast counter decrements once per normal player tick; positive counter refuses the cast helper. The skill's recast delay is stored after dispatch, including when cast returns no `Spell`. | Observed; Executed in the player model | `P+0x4ae`; tick 0x1a5030–0x1a5624; `Player_castSkill` 0x1a42b8; skill+0x0c |
| In state 5, cast fires when animation blend value reaches 1.0 offline or 0.5 in a network game. Kind 7 bypasses animation; kind 8 fires at the ranged release. | Observed; Executed in player model | state 5 0x1ab4f8–0x1ab7dc, blend at animation track +8; instant 0x1a7048; ranged 0x1a837c/0x1a9174 |
| The helper checks copy eligibility (skill flag bit 0), calls `canUse`, finds the hand midpoint and first accepted enemy within an arc, then invokes Skill slot 2 `(rank,P,pos,facing)`. A returned `Spell` attaches to `P+0x364`; kind 1 also gets held handle `P+0x588`. A prediction copy destroys its returned spell. | Observed; Executed in player model | `Player_castSkill` 0x1a42b8; `creature_addSpell` 0x11a838; skill+4, +8; `P+0x588` |
| The helper pays cost once and starts recast even when Skill slot 2 returns zero. Kind 1 pays `cost × 1/60` here and again each held phase-2 tick. Held spell is stopped on release, leaving state 5 or exhausted mana. | Observed; Executed in player model | 0x1a42b8; 0x1ab4f8–0x1ab7dc; `Player_updateCast` 0x1a3f70; `R+0xc0`, `P+0x47b` |
| Mana regeneration is real-player-only and capped at `R+0xc4`. Base gain starts at maximum mana × float bits `0x38d1b717`, modified by passive 0x200, `P+0x475`, equipped modifier 0xc, Blessed and Regeneration. Class 0 has no natural base gain. A pending mana potion adds `R+0xbc` per tick while `R+0xc8` remains. | Observed; Executed in player model | `Player_regenMana` 0x1b3900; `R+0xc0/+0xc4/+0xc8/+0xbc`; potion entry `Player_usePotion` 0x1b9cb8 |

The cast helper does **not** recheck available mana after the animation delay;
the request gate checked it earlier. The port must preserve that ordering rather
than moving the debit to button press (Observed: `Player_run`/`Player_castSkill`).
The exact visual time in seconds depends on the clip and animation advance, so a
single universal casting duration is **Unknown**.

## 3. Concrete projectile and damage path: Disease Bolt (skill id 4)

This is an example of an active caster skill that returns **no attached `Spell`**.
The distinction matters: returning zero does not mean no projectile was created.

| Stage | Evidence | Address |
|---|---|---|
| `SkillDiseaseBolt` is kind 0, recast 30 frames. Slot 5 evaluates `float32(9.0 + float32((rank−1) × 2.0000129…))`; debit that float after the cast animation, not an integer `9 + 2·(rank−1)`. | Observed; Executed at levels 0–40 in the skills sweep and ranks 1, 2, 3, 4, 5, 10, 20, 21, 30, 40 in the focused `s04` difftest | skill table 0x518468; `SkillDiseaseBolt_manaCost` 0x2cb33c; `Player_castSkill` 0x1a42b8 |
| Cast allocates 0x7c bytes, constructs `DiseaseBolt`, applies a caster flash, returns zero. Constructor stores facing, owner handles, skill, rank, 350-unit/second horizontal velocity, expiry at frame+300, homing arm at frame+10, and selects the first accepted enemy in a forward arc. | Observed; Executed in `ref_skills_a.py`/`difftest_skills_a.py` | cast 0x2cb1c0; `DiseaseBolt_ctor` 0x2c9eb0; fields +0x38, +0x4c/+0x54, +0x5c/+0x60, +0x64..+0x74; object table 0x5183d8 |
| Projectile run homes only when `frame > armFrame`, calls `obj_moveAndCollide`, and ends when `expiry <= frame`. Movement result bit 0 (ground) sets expiry to zero. Bit 1 (object contact) does so only when the hit latch at +0x78 is set. The touch handler ignores friendly and blocking creatures, asks skill stat 0 for damage, makes one object RNG draw for the upper end, and passes base range plus descriptor type 0x26 to `damage_apply`. | Observed; Executed for boundary frames 299/300, ground, contact without/with hit latch, outgoing call arguments, stores and seeds | run 0x2ca1a8; `obj_moveAndCollide` 0x1509f8; hit 0x2caec8; `damage_apply` 0x1e8230 |
| `damage_apply` rolls and mitigates damage, handles descriptor effects, then calls the victim's damage handler. A type-0x26 entry may create a disease effect; the exact resulting HP delta depends on defender state, resistance and the separate damage pipeline. | Observed; separately Executed in `ref_combat.py`/`difftest_combat.py`; composed end-to-end hit **Unknown** | 0x1e8230; `docs/spec/combat.md` §2; `docs/spec/skills-01-34.md` §4 |

World queries, pool allocation, collision, and `damage_apply` are scripted stubs in
the skill difftest. The model verifies the projectile's outgoing damage call, not a
victim HP change. This is the boundary for a native gameplay acceptance test.

**Exact rank example (Executed in `ee_emu.py`).** At player ranks 1, 2, 5 and 20,
the original slot-5 returns 9 (`0x41100000`), 11.0000123978 (`0x4130000d`),
17.0000514984 (`0x4188001b`) and 47.0002441406 (`0x423c0040`) mana. Its
player-tier stat-0 getter 0x3c85fc gives 30, 39, 66 and 201 respectively, from
first level 1, base 30, float step `0x41102484` (9.008915…). The hit uses this
stat as the low damage bound and `d + d × objectRandom/65536 × 0.19999999` as
the high bound. `damage_apply` can miss or mitigate the direct hit; descriptor
0x26 separately attaches a level-zero disease whose later tick is at least one
point. The disease entry's copied stat is an enable value, not another direct
damage add (Observed: 0x1e9d68, 0x2d5854; Executed only across separate
function boundaries).

The projectile begins with expiry `castFrame + 300`. It is alive at frame
`castFrame + 299` and deletes itself on its run at `castFrame + 300` if movement
does not end it earlier. In the focused comparison, a ground contact deleted it
with a future expiry; an object contact before the hit latch survived, while the
same contact after the latch deleted it. These are scripted-world comparisons,
not a live level or console observation.

For every player rank 1–20, `tools/probe_player_spell_ranks.py` calls the original
slot 5 and tier-1 stat getter in `ee_emu.py`. Its JSON lines include exact cost
float bits and stats 0–4. For Disease Bolt, stat 0 is direct-hit base damage;
the effect handler supplies the spread and disease descriptor above. These
getter values are not final victim HP loss.

## 4. Castable spells in each player class

The seven class skill trees at 0x4f4898/0x4f4e38/0x4f4b68/0x4f5108/0x4f53d8/
0x4f5720/0x4f5a18 select 75 castable entries. The table order is tree order;
passives (kind 3) are deliberately excluded because button admission never
casts them. Each listed ID can occupy a 0x68-byte assignment record and is
selected by the same D-pad/quick-slot path in §1; the record rank goes to its
Skill slot 5 and slot 2. Availability still depends on the tree's level and
prerequisite, `canUse`, and current mana (Observed: `skills_screen` 0x1d4660,
`Player_run` 0x1a5c6c, 0x1a6f84).

In the Kind column, **5** means the common state-5 animation threshold; **5
held** means kind 1, then 1/60 of the shown cost is paid on each held tick;
**instant** is kind 7; **ranged release** is kind 8. All kinds use the admission
gate and cast helper from §2. The mana samples show original `ee_emu.py` slot-5
returns at ranks 1 / 2 / 20, called after the game's own static skill construction
at 0x16ac74 and stat initialization at 0x1ebca0. For every intervening rank,
the rank probe also called slot 5 and the tier-1 stat getter: 75 entries × 20
ranks = 1,500 executed rows. Run it with
`PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_player_spell_ranks.py SLUS_209.73`.
The exact stat-4 and float-step rules are in `docs/skills.md` and the per-skill
specifications; stat 0 is not universally damage. The
`Primary effect` column identifies the object family created or attached; it
does not imply that slot 2 returns that object. An independent object may be
created while slot 2 returns zero.

**Evidence:** tree membership, kind, slot-5 address and effect constructors are
Observed at the table/function addresses above and in `docs/spec/skills-01-34.md`,
`docs/spec/skills-35-68.md` and `docs/spec/skills-69-101.md`. The cost samples
are Executed against the original. Individual effects are covered by
`ref_skills_[abc].py` and `difftest_skills_[abc].py`; their executed coverage and
untaken paths are recorded in the matching `*-executed.md` specs. The final
column is an **Inferred cross-function route** to the existing damage/creature
models, not a claim that selection through HP change has been executed as one
case. An exact final damage number is Unknown without victim defenses, hit
rolls, status state and the separate `damage_apply` call (§3).

### Barbarian (class 0)

| ID / skill | Kind | Slot 5 / mana at ranks 1, 2, 20 | Primary effect | Damage or gameplay effect |
|---|---:|---|---|---|
| 49 bash | 5 | `0x2de60c`; 16 / 19 / 73 | SpellBash | bash event → damage_apply |
| 53 criticalhit | 5 | `0x2e7690`; 25 / 29 / 101 | SpellCriticalHit | critical-hit buff on later attack |
| 38 groundpound | 5 | `0x2c7478`; 28 / 31 / 85 | no object in cast | ground impact → radial damage_apply |
| 35 charge | 5 | `0x2c8c80`; 35 / 38 / 92 | SpellCharge | charge contact → damage_apply |
| 41 cyclone | 5 | `0x2d1794`; 24 / 27 / 81 | SpellCyclone | spin melee events → damage_apply |
| 51 ancestralcall | 5 | `0x2e0980`; 85 / 89 / 161 | SpellAncestralCall | attack buff; later damage_apply |

### Cleric (class 1)

| ID / skill | Kind | Slot 5 / mana at ranks 1, 2, 20 | Primary effect | Damage or gameplay effect |
|---|---:|---|---|---|
| 16 holystrike | 5 | `0x2ed1e4`; 7 / 10 / 64 | HolyStrike | projectile hit → damage_apply |
| 34 shieldbash | 5 | `0x2facb0`; 27 / 31 / 103 | SpellShieldBash | bash event → damage_apply + stun |
| 55 healing | 5 | `0x2e8e94`; 55 / 61 / 169 | SpellHealing | healing; no damage |
| 54 holyshield | 5 | `0x2e82c8`; 24 / 30 / 138 | SpellHolyShield | mana shield; no outgoing damage |
| 10 blessed | 5 | `0x2e0040`; 1 / 2 / 20 | SpellBlessed | mana regen; no damage |
| 15 undeadshield | 5 | `0x2eb944`; 41 / 45.000023 / 117.000465 | SpellUndeadShield | undead retaliation on incoming hit |
| 17 hammerofwrath | 5 | `0x2efecc`; 75 / 82.000969 / 208.018402 | HammerOfWrath, SpellHammerOfWrath | hammer impact → damage_apply |
| 20 blindinglight | 5 | `0x2f4ae4`; 45 / 52.000954 / 178.018173 | BlindingLightEffect | blind status + periodic damage_apply |
| 21 repulseundead | 5 | `0x2f50a8`; 59 / 62 / 116 | LostSoul | radial undead damage; LostSoul visual |
| 31 clericroot | 5 | `0x2e6894`; 55 / 59 / 131 | SpellRoot | root status; no direct damage |
| 39 convertenemy | 5 | `0x2d0120`; 97 / 104 / 230 | SpellConvertEnemy | conversion control; no direct damage |
| 22 dismissundead | 5 | `0x2f6674`; 70 / 72.001022 / 108.019432 | HolyBolt | bolt hit → damage_apply |
| 70 unspokenword | 5 | `0x2fd334`; 51 / 59 / 203 | SpellUnspokenWord | expanding ring → damage_apply + stun |
| 69 retribution | 5 | `0x314454`; 75 / 83 / 227 | SpellRetribution | retaliation/heal on later hits |
| 68 resurrect | 5 | `0x3126d8`; 90 / 98 / 242 | SpellResurrect | resurrection; no damage |

### Shadowknight (class 2)

| ID / skill | Kind | Slot 5 / mana at ranks 1, 2, 20 | Primary effect | Damage or gameplay effect |
|---|---:|---|---|---|
| 4 diseasebolt | 5 | `0x2cb33c`; 9 / 11.000012 / 47.000244 | DiseaseBolt | bolt hit → damage_apply + disease |
| 6 diseasetrail | 5 | `0x2ccdfc`; 36 / 39.503983 / 102.575729 | SpellDiseaseTrail | trail segment → damage_apply |
| 36 darkness | 5 | `0x2cf42c`; 33 / 37 / 109 | DarknessProjectile | darkness projectile/area damage |
| 67 shadowstep | 5 | `0x311604`; 64 / 69 / 159 | SpellShadowStep | movement/control; later StaticFire |
| 5 diseaseshield | 5 | `0x2ce284`; 43 / 47.000015 / 119.000313 | SpellDiseaseShield | shield area → damage_apply + disease |
| 11 summonskeleton | 5 | `0x2e2340`; 86 / 91 / 181 | Skelight, SpellSummonSkeleton | summoned creature attacks |
| 49 bash | 5 | `0x2de60c`; 16 / 19 / 73 | SpellBash | bash event → damage_apply |
| 40 convertundead | 5 | `0x2d0c8c`; 104 / 109 / 199 | SpellConvertUndead | undead conversion; no direct damage |
| 97 diseaseblade | 5 | `0x318aa0`; 50 / 56 / 164 | SpellDiseaseBlade | weapon disease on later hit |
| 91 raisearmy | 5 | `0x3137a4`; 160 / 167 / 293 | SpellRaiseArmy | raised creatures attack |
| 42 harmtouch | instant | `0x2d2950`; 135 / 141 / 249 | SpellHarmTouch | instant touch → damage_apply |

### Ranger (class 3)

| ID / skill | Kind | Slot 5 / mana at ranks 1, 2, 20 | Primary effect | Damage or gameplay effect |
|---|---:|---|---|---|
| 33 rangercriticalhit | 5 | `0x2e7690`; 35 / 39 / 111 | SpellCriticalHit | critical-hit buff on later attack |
| 46 multifire | ranged release | `0x2da130`; 5 / 7 / 43 | MissileWeapon | multi-shot weapon projectiles |
| 75 summonarrows | 5 | `0x2ff848`; 38 / 43 / 133 | SpellSummonArrows | summoned ammunition; later attacks |
| 44 coldarrow | ranged release | `0x2d6f80`; 14 / 17 / 71 | ColdArrowProjectile | cold arrow impact damage |
| 43 firearrow | ranged release | `0x2d6204`; 25 / 28 / 82 | FireArrowProjectile | fire arrow impact damage |
| 32 rangerroot | 5 | `0x2e6894`; 30 / 33 / 87 | SpellRoot | root status; no direct damage |
| 45 poisonarrow | ranged release | `0x2d8a30`; 37 / 40 / 94 | PoisonArrowProjectile | poison arrow impact damage |
| 47 explodearrow | ranged release | `0x2dae80`; 55 / 58 / 112 | ExplodeArrowProjectile | explosive arrow impact/area damage |
| 50 minorhealing | 5 | `0x2e0354`; 100 / 109 / 262 | SpellMinorHealing | healing; no damage |

### Wizard (class 4)

| ID / skill | Kind | Slot 5 / mana at ranks 1, 2, 20 | Primary effect | Damage or gameplay effect |
|---|---:|---|---|---|
| 23 shockoffrost | 5 | `0x2f8af8`; 7 / 10.000032 / 64.000618 | ShockOfFrost | frost projectile hit → damage_apply |
| 37 shock | 5 | `0x2c3f28`; 19 / 22 / 76 | ShockProjectile | shock projectile/area damage |
| 58 froststorm | 5 | `0x2edd44`; 40 / 48 / 192 | FrostStormSpell | storm area → damage_apply |
| 1 wizardbeam | 5 held | `0x2f3da8`; 26 / 28.000008 / 64.000145 | SpellWizardBeam | beam tick → damage_apply |
| 96 frostarmor | 5 | `0x317ce8`; 41 / 46 / 136 | SpellFrostArmor | defense + reactive damage_apply |
| 57 shockoffire | 5 | `0x2ed80c`; 31 / 33 / 69 | Sparks | fire shock projectiles → damage_apply |
| 12 lightningweapons | 5 | `0x2e3480`; 20 / 27.000771 / 153.014633 | SpellLightningWeapons | weapon lightning on later hit |
| 8 fireflares | 5 | `0x2dd88c`; 17 / 27.999825 / 225.996658 | SpellFireFlares | flare hit → damage_apply |
| 7 firestorm | 5 | `0x2d5300`; 43 / 53.999905 / 251.998215 | FireStorm | storm area → damage_apply |
| 14 coldweapons | 5 | `0x2e6140`; 25 / 34.000874 / 196.016602 | SpellColdWeapons | weapon cold on later hit |
| 52 root | 5 | `0x2e6894`; 88 / 96 / 240 | SpellRoot | root status; no direct damage |
| 13 fireweapons | 5 | `0x2e4dcc`; 35 / 46.000824 / 244.015686 | SpellFireWeapons | weapon fire on later hit |
| 18 coneoffire | 5 held | `0x2f1210`; 51 / 52 / 70.000015 | SpellConeOfFire | channeled cone → damage_apply |
| 56 coneoffrost | 5 held | `0x2e9ad4`; 48 / 49 / 67 | SpellConeOfFrost | channeled frost cone damage |
| 95 waveofflame | 5 | `0x316cdc`; 60 / 65 / 155 | SpellWaveOfFlame | expanding fire wave → damage_apply |

### Berserker (class 5)

| ID / skill | Kind | Slot 5 / mana at ranks 1, 2, 20 | Primary effect | Damage or gameplay effect |
|---|---:|---|---|---|
| 76 roar | 5 | `0x300138`; 16 / 19 / 73 | SpellRoar | shout event → damage_apply |
| 72 summonaxe | 5 | `0x2fe938`; 26 / 32 / 140 | SpellSummonAxe | summoned weapon; later attacks |
| 78 bloodlust | 5 | `0x303220`; 30 / 33 / 87 | SpellBloodLust | melee damage buff; later attacks |
| 98 fireaxe | ranged release | `0x319ea0`; 25 / 28 / 82 | playerProjectile | fire axe impact damage |
| 81 berserkercriticalhit | 5 | `0x2e7690`; 35 / 39 / 111 | SpellCriticalHit | critical-hit buff on later attack |
| 99 coldaxe | ranged release | `0x31a7d4`; 70 / 73 / 127 | playerProjectile | cold axe impact damage |
| 84 berserkercyclone | 5 | `0x2d1794`; 51 / 55 / 127 | SpellCyclone | spin melee events → damage_apply |
| 77 battlecry | 5 | `0x3016e0`; 60 / 67 / 193 | SpellBattleCry | stun/swing-speed buff; later attacks |

### Shaman (class 6)

| ID / skill | Kind | Slot 5 / mana at ranks 1, 2, 20 | Primary effect | Damage or gameplay effect |
|---|---:|---|---|---|
| 89 poisonbolt | 5 | `0x30f364`; 8 / 10 / 46 | PoisonBolt | bolt hit → damage_apply + poison |
| 88 drowsy | 5 | `0x30e5ec`; 21 / 25 / 97 | SpellDrowsy | drowsy status; no direct hit |
| 87 tagarsinsects | 5 | `0x30c928`; 30 / 43 / 277 | SpellTagarsInsects | insect status/periodic damage |
| 86 shamanhealing | 5 | `0x2e8e94`; 72 / 79 / 205 | SpellHealing | healing; no damage |
| 26 poisonweapons | 5 | `0x315f20`; 70 / 80 / 260 | SpellPoisonWeapons | weapon poison on later hit |
| 90 summonbadger | 5 | `0x310c08`; 120 / 128 / 272 | CastBadger, SpellSummonBadger | summoned creature attacks |
| 94 spiritshield | 5 | `0x314fd8`; 85 / 95 / 275 | SpellSpiritShield | damage absorption; no outgoing hit |
| 80 pusstorm | 5 | `0x30af38`; 55 / 61 / 169 | PusStorm | storm area → damage_apply |
| 65 giantgrowth | 5 | `0x30909c`; 75 / 83 / 218 | SpellGiantGrowth | size/melee damage buff |
| 66 planarwind | 5 | `0x309cd8`; 75 / 78 / 132 | SpellPlanarWind | moving front → damage_apply |
| 85 shamanroot | 5 | `0x2e6894`; 100 / 108 / 252 | SpellRoot | root status; no direct damage |

## 5. Reference and verification map

| Boundary | Reference model | Original-code difftest |
|---|---|---|
| Selector and quick-slot message | `tools/ref_hud_inputs.py`, `tools/ref_hud_quickslots.py` at `t3/research-hud-inputs` `44c6720` | `tools/difftest_hud_inputs.py`, `tools/difftest_hud_quickslots.py` on that pinned branch |
| Player input, admission, timing, cast helper, mana regeneration | `tools/ref_player.py` | `tools/difftest_player.py` |
| Disease Bolt cost at ten ranks, cast, object run, expiry boundaries and hit | `tools/ref_skills_a.py` | `tools/difftest_skills_a.py -k s04` (includes `s04 diseasebolt expiry boundaries`) |
| Generic damage application | `tools/ref_combat.py` | `tools/difftest_combat.py` |

These tests compare constructed states in `ee_emu.py`, seeded with 20973 and 7.
They do not feed a raw D-pad event all the way to a live enemy death. The pinned
HUD branch is deliberately cited instead of copied into this branch; it is not
present in main `034d0c0`.

### Rerun on 2026-10-23

All commands below set `PYTHONDONTWRITEBYTECODE=1` and passed the private US v2.00
executable by absolute path. Counts-only logs are under this worktree's ignored
`local/spells-evidence/`; no game bytes or disassembly are tracked.
`SLUS_209.73` in the table denotes the private local US v2.00 executable
supplied as the command argument.

| Command (repeat for `--seed 20973` and `--seed 7`) | Seed 20973 | Seed 7 |
|---|---:|---:|
| `python3 tools/difftest_player.py SLUS_209.73 --seed N` | 31,990 ticks; state 5: 351/0 mismatches | 31,991 ticks; state 5: 386/0 mismatches |
| `python3 tools/difftest_skills_a.py SLUS_209.73 --seed N -k s04` | 1,135 calls, 0 mismatches; skill-4 blocks 83/85 | 1,042 calls, 0 mismatches; skill-4 blocks 83/85 |
| `python3 tools/difftest_skills_b.py SLUS_209.73 --seed N --quick` | 55,368 calls, 0 mismatches | 54,338 calls, 0 mismatches |
| `python3 tools/difftest_skills_c.py SLUS_209.73 --seed N --quick` | 119 properties, 0 failed | 119 properties, 0 failed |
| `python3 tools/difftest_combat.py SLUS_209.73 --seed N -k damage --quick` | 39 properties, 0 failed | 39 properties, 0 failed |
| In pinned HUD worktree `44c6720`: `python3 tools/difftest_hud_quickslots.py SLUS_209.73 --seed N` | 5 properties, 0 failed; selector 1,680 cases | 5 properties, 0 failed; selector 1,680 cases |
| In pinned HUD worktree: `python3 tools/difftest_hud_inputs.py SLUS_209.73 --seed N` | 4 properties / 560 cases, pass | 4 properties / 560 cases, pass |

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p
'test_*.py'` in this worktree: 652 tests, OK. The player runner records a few
constructed ticks where both the original and model read unmapped memory; those
agreements are in its fault property, not live cast successes. The damage run is
`--quick` and tests `damage_apply` separately from Disease Bolt's hit callback.
The all-rank probe returned 1,500 rows (75 tree entries at ranks 1–20) from the
original getters. A full `difftest_skills_a.py` sweep on seed 20973 additionally
passed 172,611 calls with zero mismatches; the other skill-family sweeps below
use `--quick` on both seeds.

## 6. Native port order and gates

1. Import the reviewed HUD input/message contract at `44c6720`: D-pad gating,
   quick-slot swap, forced queue and three-frame input mask. Verify selector and
   A/B labels in a rendered local-player session.
2. Represent the 0x68-byte ability record, id/rank, skill kind and quick-slot
   references. Preserve normal and forced requests through the simulation tick.
3. Remove the native rank-one Disease Bolt limit (user-reported `codex/play-spells`
   state). Evaluate the original float slot-5 cost for the assigned rank; rank 2
   is 11.0000123978, not 11. Port request admission, `canUse`, refusal,
   recast decrement and state-5 animation threshold. Test ranks 1, 2, 5 and
   20 with mana immediately below/equal to the float cost, offline and network
   thresholds, kind 7 immediate and kind 8 ranged release.
4. Port the cast helper with the original hand position, target scan, copy guard,
   slot-2 dispatch, attachment and held handle rules. Account for cast functions
   returning zero after constructing an independent projectile.
5. Port mana debit, held-per-frame charge, release and regeneration/potion
   ordering. Check exact float bits and cap behavior, including class 0.
6. Port one projectile completely: Disease Bolt construction, world registration,
   frame/position update, homing, touch filtering and deletion. Preserve the
   inclusive end at `castFrame + 300`, ground-contact end, and object-contact end
   only after the hit latch. Assert survival at +299, expiry at +300, and both
   collision result bits. Keep its own and shared RNG streams separate.
7. Connect projectile touch to the reviewed `damage_apply` and victim handler.
   Verify actual HP change, effects and death in a real hostile level; the
   isolated skill difftest does not establish this integration.
8. Add the 75 class-tree cast entries in §4 by kind and object family, using
   `ref_skills_[abc].py` and the per-skill `*-executed.md` coverage maps. Pay
   rank-specific cost for every entry; distinguish attached spells, independent
   projectiles, weapon-release skills and casts that make no lasting object.
   Check each skill's `canUse`, constructor, run/end, and damage/stat path; the
   class matrix is not itself an end-to-end execution receipt.
9. Verify native visuals and sound after each simulation family has a cast and
   impact path; compare a live hostile target's HP/status/death separately.

**Unknown / remaining gate:** whole-session selection-to-hit parity for every
class entry, a live campaign caster against a real target, exact animation clip
duration, per-victim final damage after defenses and status interaction, and
console floating-point behavior outside the interpreter's model. Unexecuted
compositions in §4 remain Inferred; no addresses or values for these are
promoted to native constants.
