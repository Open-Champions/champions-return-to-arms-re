# Skills and spells (0x2c3cd4–0x320000)

Status: breadth-first pass. Every class in the area was laid out from the virtual tables and
the start-up initialiser; the mechanical parts (slot functions, constructor fields, statistic
constants, what each cast allocates) were extracted by script from the disassembly and the
decompile. About 60 of the 982 functions were read by hand, chosen for the base layout, the
cast path and the per-machine questions. Nothing here was checked on a running game, and
that is still so: the three skill specifications (`docs/spec/skills-*.md`) are readings too,
and the live game the project now has — the Play! emulator, which is not a PlayStation 2 and not PCSX2;
`FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md` — has
not been used to look at a skill. No test patch has been run on a live game.
"Observed" means read at the address given; "Inferred" and "Unknown" are marked.

## What the area contains

| Range | Contents |
|---|---|
| 0x2c3cd4–0x304bc8 | One source file per skill, in the order Shock, StaticFire, GroundPound, Charge, DiseaseBolt … BloodLust, Throwing. Each file holds the effect classes (a `Spell` subclass and/or `GameObject`-derived projectiles), the `Skill` subclass, a few helpers called from the damage and player code, and usually a static initialiser that registers particle type descriptors |
| 0x304bc8–0x30839c | The arena mode (run task "arena", draw task "arenaDraw", `SpellArena`) |
| 0x30839c–0x31c2a0 | More skills: StrongStance … ConeOfShock |
| 0x31c2a0–0x31d2a0 | `SmokeGen` level object |
| 0x31d2a0–0x320000 | Not skills: USB keyboard support, a "CommBuffer" packet queue, a power-off handler and other platform code. Not examined beyond their strings |

The `SkillShock` constructor (0x2c3c68), the constructors and statistics functions of five
skill classes (ids 25 and 27–30; 0x16a98c–0x16ac74 — the earlier version counted eight and
included ids 3, 60 and 61, which are constructed inline in the static initialiser 0x16ac74,
Blunt at 0x16b2cc and Slashing at 0x16b35c, and use the base statistics function;
`docs/spec/skills-35-68.md` section 4.6) and every default slot function
(0x3c8218–0x3c8cb4) live outside this range; they are described here but not named in
`symbols/skills.tsv`. The same goes for most destructors (0x3ccfd4–0x3d21c8).

## How the pieces fit

- A **Skill** is a static, stateless description object, one per skill id, 0x68 bytes (the two
  axe skills are 0x188). It answers "may this caster use me", "what do I cost", "what is
  statistic *n* at level *L*" and it has one action, *cast*, which allocates the thing that
  does the work.
- The thing that does the work is either a **Spell** — a small object attached to a creature
  and run from that creature's own run function — or a **GameObject** in the world (a
  projectile or area effect), or both.
- Skills are looked up through `g_skillTable` (0x41b170), an array of pointers indexed by
  skill id, ids 1–101. The table is initialised data, not filled at run time (Observed: the
  words at 0x41b174–0x41b304 are link-time addresses 0x6e14d8 … 0x6e3fb8; entry 0 and the two
  words after entry 101 are null).
  What happens at start-up is construction of the objects those pointers refer to: the static
  initialiser at 0x16ac74 calls each `Skill` subclass constructor on its slot in the array at
  0x6e14d8 (stride 0x68; the last four objects are at 0x6e3c40, 0x6e3dc8, 0x6e3f50, 0x6e3fb8).

## Data structures

### Skill (0x68 bytes; virtual table pointer at +0x60)

| Offset | Type | Meaning | How known |
|---|---|---|---|
| +0x00 | char* | internal name ("diseasebolt"); text keys are built from it ("<name>_rankdesc") | every constructor, e.g. 0x2cb0e0; UI at 0x1d4660 |
| +0x04 | u32 | flags. Bit 0: the prediction copy of the local player may cast this too. Set only by Cyclone (ids 41, 84) and AncestralCall (51) | constructors 0x2d13ec, 0x2e0640; test in the player cast helper 0x1a42b8 |
| +0x08 | s32 | kind. 0 ordinary, 1 channelled (cost is per second, taken 1/60 per frame; the spell is also linked at player+0x588), 3 passive (never cast; menus test for 3), 7 set by HarmTouch only, 8 set by the five bow skills and the two axe skills. The kind is copied into the ability record (+0x25) by `hud_onAssignSpell` 0x1de61c. Kind 7: `Player_run` calls `Player_castSkill` at once, with no cast animation (0x1a7048, 0x1aac60). Kind 8: tested at 0x1a7034–0x1a7058; the record is kept at player +0x484 (store at 0x1a709c) and consumed by the ranged release, whose two sites call `Player_castSkill` at 0x1a837c and 0x1a9174. (The earlier version said the tests of 7 and 8 were not looked for; `docs/spec/skills-35-68.md` section 4.6.) Player_run also compares the field with 6, which no constructor sets | constructors; 0x1a42b8; 0x1c2648, 0x1d32e4 |
| +0x0c | s16 | recast delay in frames, copied to player+0x4ae after a cast. 30 by default; BlindingLight 180, ConvertUndead and HarmTouch 300, ConvertEnemy 600 | constructors; 0x1a42b8 |
| +0x0e | s16[5] | tier 1: first level at which statistic *i* exists | base slot 10 at 0x3c85fc |
| +0x18 | s16[5] | tier 1: value of statistic *i* at that level | same |
| +0x24 | float[5] | tier 1: increase per further level | same |
| +0x38 | s16[5] | tier 2: first level; 0xffff means "no tier 2 for this statistic, use tier 1". Executed: the test is the sign — any negative first level means "use tier 1" (`bltz` at 0x3c86d8); the constructors store −1, so nothing changes for the shipped tables | constructors write 0xffff; base slot 11 at 0x3c8690 |
| +0x42 | s16[5] | tier 2: value at that level | same |
| +0x4c | float[5] | tier 2: increase per level | same |
| +0x60 | ptr | virtual table | |
| +0x64 | s32 | skill id, only in classes that serve several ids (Dodge, Riposte, Root, CriticalHit, Cyclone, Healing); it selects the name and the statistics | constructors 0x2e62b4, 0x2d13ec … |
| +0x68 | 4 × 0x48 | FireAxe and ColdAxe only: one item record per player slot for the conjured axe | 0x319598, 0x31979c |

Statistic value = base + step × (level − first level), rounded to nearest; 0 when the level is
0 or below the first level. Tier 1 is used for players, tier 2 for everything else (slot 12
picks by the caster's is-player flag). That holds only where the code asks through slots
11–13: Root, ConvertEnemy, ConvertUndead and HolyShield call slot 10, which is tier 1 for any
caster, and ShockOfFire's direct damage calls slot 8 (`docs/spec/skills-35-68.md` section
4.6). Which statistic means what is per skill; by convention
statistic 0 is the main amount (damage, percentage) and statistic 4 is the mana cost.

### Skill virtual slots (tools/vtab.py numbering; slot n is at table offset n × 8)

| Slot | Name used here | Arguments → result | Evidence |
|---|---|---|---|
| 1 | canUse | (caster) → bool. Checks weapon type, PvP restrictions, pet limits; for players it also posts the warning text | callers 0x1a5c6c (Player_run), 0x1a42b8, Cazic 0x24ad6c; e.g. 0x2e2368 |
| 2 | cast | (level, caster, pos*, facing) → Spell* or 0 | 0x1a42b8; monster run functions; e.g. 0x2cb1c0 |
| 3 | — | base returns 0; no class overrides it; no caller found | 0x3c8248 |
| 4 | describeRank | (text buffer, level): formats "<name>_rankdesc" with statistic values; the skill menu calls it for the current and the next level | 0x1d4660; e.g. 0x2cb264 |
| 5 | manaCost | (level) → float. Either a literal a + b × (level − 1), or slot 15, or 0 for passives. Executed: "0 for passives" holds for Dodge's own function only (0x2e8a88); the default 0x3c82a8, which the other passives and Riposte use, returns **1.0** — as the id table's "base (1.0)" has it. Nothing asks a passive for its cost | 0x1a42b8; e.g. 0x2cb33c, 0x2c3f28 |
| 6 | describeExtra | (text buffer) → 1 if it wrote a description. Only SkillResurrect overrides (different text for one player) | 0x1d4660; 0x312500 |
| 7 | getIcon | looks up "ic<name>.tex" in icons.lmp | 0x3c82c0, 0x3ccfb0 (all outside this range) |
| 8 | getStatRange | (spread, stat, level, randomise, int* lo, int* hi): slot 10 value ∓ spread, each at least 1; with randomise set each bound advances the shared generator twice — executed: only the second draw of each pair sets the bound; the first only chooses the direction of the rounding, through the sign of the value it would give (0x3c8354–0x3c840c) | base 0x3c82e4; used by describeRank with randomise 0, e.g. 0x2c3df8 |
| 9 | initStats | fills the tables at +0x0e…+0x5f. The base version writes first level 0, value 1 and step 2.0 for all five tier-1 statistics (0x3c85b0–0x3c85f0); the earlier version said it zeroes tier 1. Called once for every id by `skills_callVslot9All` 0x1ebca0, from `game_initCamera` 0x1e6b68 (call at 0x1e6bac), from `main` (call at 0x323e48); the earlier version said the caller was not found | e.g. 0x2cb14c; base 0x3c85b0 |
| 10 | getStat | (stat, level) → int, tier 1 | base 0x3c85fc |
| 11 | getStatTier2 | (stat, level, cap) → int; level is clamped to cap when cap > 0; tier 2 if present else tier 1 | base 0x3c8690 |
| 12 | getStatFor | (stat, level, caster, cap): slot 10 if the caster has the is-player flag, else slot 11 | base 0x3c87f0 |
| 13 | getStatForHandle | same, the caster given as a handle list head | base 0x3c8864 |
| 14 | adjustLevel | (level, n) → level. Base returns the level unchanged and no class overrides it, so n (seen as 1, 2, 10, 20) has no effect in this build | base 0x3c88dc |
| 15 | manaFromStat4 | (level, n) → (float) slot 10(4, slot 14(level, n)) | base 0x3c88e4 |

Slots 8 and 10–15 are never overridden; only 1, 2, 4, 5, 6, 7 and 9 are.

### Spell (base 0x18 bytes; virtual table pointer at +0x14)

| Offset | Type | Meaning | How known |
|---|---|---|---|
| +0x00 | u8 | level the skill was cast at | constructors, e.g. 0x2c8cb4; used as the level argument of every statistic lookup |
| +0x04 | handle back-list | what `handle_link(creature+0x364, spell+4, spell)` hooks into; cleared by the destructor | creature_addSpell 0x11a838; base destructor 0x3cafc8 |
| +0x08 | Skill* | the skill that made it. Not universal: `SpellDiseaseEffect` and `SpellSecondaryUndeadShield` leave it null (0x2d5594, 0x2eb050); the former keeps its Skill at +0x1ac (`docs/spec/skills-01-34.md` section C) | constructors |
| +0x0c | Creature* | owner: the creature the spell sits on (for buffs this is the caster) | constructors; run functions |
| +0x10 | u32 | private generator state, seeded by one draw from the shared generator in the constructor; advanced by `Spell_rand` | every Spell constructor |
| +0x14 | ptr | virtual table | |
| +0x18… | | per class; very often a second creature pointer or handle (the caster) | |

The base constructor is inlined in every subclass constructor, so **constructing any Spell
draws once from the shared generator**, just as constructing a GameObject does.

One thing the per-class part hides (executed, `docs/spec/skills-01-34-executed.md` section
3, row 10): the light fields that the constructors of `FireStorm` (+0x70, +0x78; 0x2d41f8
and 0x2d4048) and `SpellUndeadShield` (+0x40, +0x48; 0x2ea4d8) leave behind hold
0x7fffffff. They are computed at run time as 1 / (0 × 0), which this FPU answers with its
largest number; the decompile shows the IEEE infinity 0x7f800000 as a constant there, and a
rebuild that copies that constant differs in those four words. Presentation only.

| Slot | Name | Called from | Notes |
|---|---|---|---|
| 1 | dtor | the spell itself when it ends (argument 3 = destroy and free), the player cast helper for the prediction copy, Creature_dtor | |
| 2 | run | Creature slot 17 (0x11a868), once per simulated frame: (pos*, facing). `Creature_run` makes the call for non-players only (is-player test at the top of 0x112948). A player's spells are run from `Player_updateCast` 0x1a3f70, called at 0x1ac6a8 after the action-state switch and only while hit points are above 0. (The earlier version said `Creature_run` and `Player_run` both call slot 17; `docs/spec/skills-35-68.md` section 4.6) | this is where all spell logic is |
| 3 | draw | Creature_draw 0x10b928 loop | overridden only by SpellDrowsy 0x30ed24, SpellSummonBadger 0x311034, SpellResurrect 0x312f48 |
| 4 | getField18 | Player_run, for Bash (id 49) and ShieldBash (34) only | returns spell+0x18; base returns 0 |

### Projectiles and area effects

These are ordinary GameObjects (slot 4 run, 5 draw, 6 touched) — in the `DiseaseBolt`
pattern, which not every effect follows: `DarknessProjectile` (id 36) and `ShockProjectile`
(id 37) call `GameObject_ctor` directly (0x2cf4d8, 0x2c4050) instead of `Projectile_ctor`,
move themselves, do their own hit tests in run and have the empty base slot 6
(`docs/spec/skills-35-68.md` section 4.6). They keep the owner as a
handle, the Skill pointer and the level, and look statistics up through slot 12 or 13 so that
a monster-owned projectile gets tier 2 numbers. Example, `DiseaseBolt` (0x7c bytes,
constructor 0x2c9eb0): +0x38 facing, +0x54 owner handle, +0x58 homing target handle (first
enemy in a cone ahead), +0x5c Skill*, +0x60 level, +0x64/+0x68 velocity (350 units/s),
+0x70 expiry frame (now + 300), +0x74 arming frame (now + 10). Other classes differ in
detail (the arrow classes keep the owner handle at +0x4c and the Skill at +0xac); their
layouts were not tabulated.

### Player record fields this area touches (g_players + index × 0x4c30)

| Offset | Meaning | Seen at |
|---|---|---|
| +0xac / +0xb0 | hit points / maximum (float) | SpellHealing_run 0x2e90b8, SpellMinorHealing_run 0x2e04f8 |
| +0xc0 / +0xc4 | mana / maximum (float) | 0x1a42b8; SpellRoar_run 0x3003d8 refunds half the cost |
| +0xd0 / +0xd4 | two ints the arrow hit handlers pass as the low / high damage of the hit (Inferred: current weapon damage range) | 0x2d685c, 0x2d7aac, 0x2d932c |
| +0x43d8 | the player's object | everywhere |
| +0x43f8 | current thrown-weapon stack (item pointer; count at item+4) | SkillFireAxe_cast 0x31979c |
| +0x4434 + 4 × n, +0x4a7c | item pointer array and the signed byte that indexes it (Inferred: weapon sets and the active set) | weapon-buff spell constructors, e.g. 0x2e24d8 |
| +0x4a86 | weapon-style byte: selects the "ohw_", "nw_", "dha_", "dhs_" animation name prefixes; value 4 is required by the five bow skills and refused by Cyclone, HarmTouch and Bash, value 6 is also refused by Cyclone and HarmTouch | canUse functions 0x2d5fc4, 0x2d1484, 0x2d2984, 0x2de334; SpellRoar_ctor 0x30016c |
| +0x4c20 | float. GiantGrowth writes max(1, 0.75 × scale); Resurrect writes 0.5 (0x312a28); each overwrites the other's value. (The earlier version: "written 1.0 / 0.75 × by GiantGrowth and Resurrect"; `docs/spec/skills-35-68.md` section 4.6) | 0x309524, 0x3127b4, 0x312a28 |

## How a cast happens

### Player (Observed, 0x1a5c6c–0x1a5e28 and helper 0x1a42b8, both in the player area)

1. The pressed ability slot is an ability record (0x68 bytes; kind byte +0x25, a copy of
   skill +0x08; skill id at +0x20). The earlier version read "+0x25 = 7 for a skill"; 7 is
   the kind that casts with no animation (see the Skill table, +0x08).
2. `canUse(player)`; if it refuses, the request is dropped.
3. level = Player slot 39 (0x3c3b40) for that id; cost = `manaCost(level)`. If the record's
   mana (+0xc0) is lower, the "not enough mana" notice is raised and nothing happens. A
   kind-1 (channelled) skill needs only half its cost to start (0x1a6f84–0x1a6f90). For an
   animated cast the helper of step 4 is called on the frame the cast animation's blend
   weight reaches 1.0, or 0.5 in a net game (0x1ab6f4–0x1ab7dc;
   `docs/spec/skills-35-68.md` section 4.6).
4. The helper 0x1a42b8 returns at once while player+0x4ae (recast counter) is above 0, and
   when the player object is the prediction copy and the skill's flag bit 0 is clear.
5. It works out the cast position (midpoint of model attachment points 0 and 1, height clamped to 58 above the feet) and a
   facing: toward the first enemy inside a cone ahead (Creature slot 20 "is enemy"), else the
   player's own facing.
6. `cast(level, player, &pos, facing)`.
7. If a Spell came back: for the prediction copy it is destroyed immediately (slot 1 with 3);
   otherwise `creature_addSpell(player, spell)`, and for kind 1 it is also linked at
   player+0x588.
8. player+0x4ae = skill+0x0c; mana −= cost (cost / 60 for kind 1). The helper makes this
   charge once. The per-frame charge while a channelled skill is held is made by
   `Player_run` in cast phase 2 and keys on the ability record's kind byte; the earlier
   version read the helper's cost / 60 as that per-frame charge (`docs/spec/skills-01-34.md`
   section C, where the row is filed under `docs/player.md`).

Mana and the shared generator are two of the four things the prediction loop restores, so
steps 6–8 on the copy leave no trace as long as cast and the Spell constructor change nothing
else. For the three copy-castable ids that is what the code does: SpellCyclone_ctor
(0x2d17c8) and SpellAncestralCall_ctor (0x2e09b4) both test the owner's 0x20000 flag before
their notice, target gathering and light-effect allocation (Observed). One exception found
since: `SpellCyclone_ctor` writes event slot 0 of the shared spin clip's header (0x2d1978,
0x2d197c) *before* its copy test at 0x2d19c4, so the copy's cast does leave a trace there
(finding S1 in `docs/spec/skills-35-68.md` section 4). Executed, and seen on the running
game: two players of the same class who both use the spin go out of sync (6 of 6 linked
pairs), and moving the two stores behind a copy test removes it (0 of 6) — FINDINGS SB1,
V19; `docs/issues/live-rig.md` 9.4.

Passive skills are not cast; other code asks them for a number (see "helpers" below).

### Monster (Observed in Horsemen_run 0x272aac–0x272c30, Bubo run 0x248ee8, Cazic run 0x24b980)

The monster's own state machine calls slot 2 directly on a fixed table entry:
`cast(level, self, &pos, facing)` with level = Creature slot 35 (base 0x118c50: the global
difficulty scale 0x4f714c × 0.3 — the float other documents call the monster level,
`g_levelMonsterLevel`), then `creature_addSpell(target, result)`. Exceptions read since
(`docs/spec/skills-35-68.md` section 4.6, `docs/spec/skills-69-101.md`): for Healing the
monster passes the wounded ally as the *caster* argument, and Orc then attaches the spell to
itself (0x2a2998); Bubo casts Disease Blade with one of its allies as the caster argument and
attaches the result to that ally (0x249014); Cazic casts Frost Armor with the whole monster
level, not slot 35 (0x24bbe8); and the arrow constructors of the bow-carrying monsters are
given `(int)g_levelMonsterLevel` unscaled (0x25c7d8, 0x2a7274). There is no mana,
no recast counter and, except where a monster calls it explicitly (SummonSkeleton), no
canUse. Many monsters skip the Skill altogether and call the effect's constructor (marked *
in the table below), or only borrow a statistic through slot 11.

### Weapon effect (Observed, damage function 0x1e8ea8–0x1e8fa0)

The damage function takes an optional effect block (four 8-byte entries at +0x24; for a
melee hit it comes from the weapon). An entry of type 0x29 carries a skill id, a percentage
and a level. When the attacker is a creature the function rolls the shared generator and calls
`g_skillTable[id]->cast(level, attacker, &attackerPos, facing)`; the returned Spell is not
attached to anything. **This is a third way into every cast function with an arbitrary
attacker**, so "only players have this skill" is not a guarantee by itself. Which ids occur in
item data is Unknown (needs the item tables from the disc).

### Helpers called from other areas

Passive and reactive skills are implemented as small functions that the damage function
(0x1e8230), Player_processDamage, Player_recalcDamage and the creature movement code call
with a fixed table entry: Riposte counter-attack 0x2ddccc, CriticalHit aura query 0x2e76c4
(only when the attacker is a player, test at the call site), UndeadShield reflection
0x2eaec0 / 0x2eb5b4, Retribution heal 0x314790, SpiritShield 0x315888 (the absorb roll,
`SpellSpiritShield_rollAbsorb`: one shared-generator draw per qualifying hit, returns whether
the hit is absorbed), FrostArmor 0x318264,
StunningStrike 0x308c10 / 0x308cb4, StrongStance 0x30851c / 0x308578, LifeTap 0x2f8e78 (its
two callers are the death branch of `Creature_processDamage`, 0x111f40, and, in PvP mode A,
`Player_processDamage`, 0x1b3614; it is not called from melee code),
BloodLust multipliers 0x3047b0 / 0x30481c, Drowsy slow factor 0x30ef08, and the percentage
getters for Archery, Throwing, BattleMage, Dodge, NaturalResistance, AxeBandolier,
LightQuiver, PenetratingArrows.

## Skill id table

Kind, recast and "copy" are skill+0x08, +0x0c and bit 0 of +0x04. "Cast creates" is what slot
2 allocates (light effects omitted; hex = object size). Mana: literal formula, or "stat4" =
statistic 4 through slot 15; "base (1.0)" = the base slot, never used because the skill is
not cast. "Monsters" lists the classes whose run function calls slot 2 on this id; * means
the run function does not call slot 2 but builds the effect itself (calling the effect's
constructor, usually passing this Skill for its statistics). Monster use was collected from
references to the table entries and to the constructors and may be incomplete.

| Id | Name string | Class | Table | Kind | Recast | Copy | Cast creates | Mana | Monsters |
|---|---|---|---|---|---|---|---|---|---|
| 1 | wizardbeam | SkillWizardBeam | 51a528 | 1 channelled | 30 | 0 | SpellWizardBeam (0x380) | 26 + 2 x (level-1) |  |
| 2 | dodge | SkillDodge | 519d98 | 3 passive | 30 | 0 | nothing (base cast) | 0 (passive) |  |
| 3 | resistpoison | SkillResistPoison | 5126f8 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 4 | diseasebolt | SkillDiseaseBolt | 518468 | 0 active | 30 | 0 | DiseaseBolt (0x7c) | 9 + 2 x (level-1) | Bubo, Horsemen, Mummy* |
| 5 | diseaseshield | SkillDiseaseShield | 518638 | 0 active | 30 | 0 | SpellDiseaseShield (0x1b0) | 43 + 4 x (level-1) | Bubo, Mummy* |
| 6 | diseasetrail | SkillDiseaseTrail | 518580 | 0 active | 30 | 0 | SpellDiseaseTrail (0x30) | 36 + 3.504 x (level-1) |  |
| 7 | firestorm | SkillFireStorm | 518d28 | 0 active | 30 | 0 | FireStorm (0xb4) | 43 + 11 x (level-1) | Cazic, Horsemen, Goblin, Demon*, Mummy*, RedDragon* |
| 8 | fireflares | SkillFireFlares | 519470 | 0 active | 30 | 0 | SpellFireFlares (0x78) | 17 + 11 x (level-1) |  |
| 9 | riposte | SkillRiposte | 519528 | 3 passive | 30 | 0 | no object in cast | base (1.0) |  |
| 10 | blessed | SkillBlessed | 519668 | 0 active | 30 | 0 | SpellBlessed (0xfc) | stat4 |  |
| 11 | summonskeleton | SkillSummonSkeleton | 519890 | 0 active | 30 | 0 | Skelight (creature, 0x468), SpellSummonSkeleton (0x1c) | 86 + 5 x (level-1) | Cazic, Horsemen, FemaleDarkElf |
| 12 | lightningweapons | SkillLightningWeapons | 519948 | 0 active | 30 | 0 | SpellLightningWeapons (0x24) | 20 + 7.001 x (level-1) |  |
| 13 | fireweapons | SkillFireWeapons | 519a00 | 0 active | 30 | 0 | SpellFireWeapons (0x60) | 35 + 11 x (level-1) | Goblin |
| 14 | coldweapons | SkillColdWeapons | 519ab8 | 0 active | 30 | 0 | SpellColdWeapons (0x24) | 25 + 9.001 x (level-1) | Goblin |
| 15 | undeadshield | SkillUndeadShield | 519f90 | 0 active | 30 | 0 | SpellUndeadShield (0x64) | 41 + 4 x (level-1) |  |
| 16 | holystrike | SkillHolyStrike | 51a108 | 0 active | 30 | 0 | HolyStrike (0x80) | 7 + 3 x (level-1) |  |
| 17 | hammerofwrath | SkillHammerOfWrath | 51a330 | 0 active | 30 | 0 | HammerOfWrath (0xe8), SpellHammerOfWrath (0x1c) | 75 + 7.001 x (level-1) |  |
| 18 | coneoffire | SkillConeOfFire | 51a3e8 | 1 channelled | 30 | 0 | SpellConeOfFire (0x58) | 51 + 1 x (level-1) | Mummy* |
| 19 | regeneration | SkillRegeneration | 51a4a0 | 3 passive | 30 | 0 | no object in cast | base (1.0) |  |
| 20 | blindinglight | SkillBlindingLight | 51a670 | 0 active | 180 | 0 | BlindingLightEffect (0x54) | 45 + 7.001 x (level-1) |  |
| 21 | repulseundead | SkillRepulseUndead | 51a728 | 0 active | 30 | 0 | LostSoul (0xb0) | 59 + 3 x (level-1) |  |
| 22 | dismissundead | SkillDismissUndead | 51a7b0 | 0 active | 30 | 0 | HolyBolt (0xc0) | 70 + 2.001 x (level-1) |  |
| 23 | shockoffrost | SkillShockOfFrost | 51a958 | 0 active | 30 | 0 | ShockOfFrost (0xd0) | 7 + 3 x (level-1) | Goblin, Tormentor*, Ulthork*, Mummy* |
| 24 | poisonrain | SkillPoisonRain | 51aaf8 | 0 active | 30 | 0 | PoisonRain (0x6c) | 222 + 12 x (level-1) | FemaleDarkElf, Mummy*, Orc* |
| 25 | diseaseweapons | SkillDiseaseWeapons | 512560 | 0 active | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 26 | poisonweapons | SkillPoisonWeapons | 51c1f0 | 0 active | 30 | 0 | SpellPoisonWeapons (0x24) | stat4 | FemaleDarkElf |
| 27 | hatebeam | SkillHateBeam | 5124d8 | 1 channelled | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 28 | hatebeam (sic) | SkillBallOfHate | 512450 | 1 channelled | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 29 | diseaseeffect | SkillDiseaseEffect | 5125e8 | 1 channelled | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 30 | hateeffect | SkillHateEffect | 5123c8 | 1 channelled | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 31 | clericroot | SkillRoot | 519ba0 | 0 active | 30 | 0 | SpellRoot (0x34) | stat4 |  |
| 32 | rangerroot | SkillRoot | 519ba0 | 0 active | 30 | 0 | SpellRoot (0x34) | stat4 |  |
| 33 | rangercriticalhit | SkillCriticalHit | 519c58 | 0 active | 30 | 0 | SpellCriticalHit (0x5c) | stat4 |  |
| 34 | shieldbash | SkillShieldBash | 51ada0 | 0 active | 30 | 0 | SpellShieldBash (0x28) | stat4 |  |
| 35 | charge | SkillCharge | 518320 | 0 active | 30 | 0 | SpellCharge (0x88) | stat4 |  |
| 36 | darkness | SkillDarkness | 5188a0 | 0 active | 30 | 0 | DarknessProjectile (0xb0) | stat4 |  |
| 37 | shock | SkillShock | 518210 | 0 active | 30 | 0 | ShockProjectile (0x198) | stat4 | FemaleDarkElf, Goblin, Hag, Orc |
| 38 | groundpound | SkillGroundPound | 518298 | 0 active | 30 | 0 | no object in cast | stat4 | Cazic*, Zek* |
| 39 | convertenemy | SkillConvertEnemy | 518928 | 0 active | 600 | 0 | SpellConvertEnemy (0x78) | stat4 |  |
| 40 | convertundead | SkillConvertUndead | 5189e0 | 0 active | 300 | 0 | SpellConvertUndead (0x78) | stat4 |  |
| 41 | cyclone | SkillCyclone | 518ac8 | 0 active | 30 | 1 | SpellCyclone (0x7c) | stat4 |  |
| 42 | harmtouch | SkillHarmTouch | 518b80 | 7 | 300 | 0 | SpellHarmTouch (0x1c) | stat4 |  |
| 43 | firearrow | SkillFireArrow | 518e70 | 8 weapon | 30 | 0 | FireArrowProjectile (0xb0) | stat4 | MaleDarkElf*, Goblin*, Gremlin*, Orc*, Skeleton* |
| 44 | coldarrow | SkillColdArrow | 518f88 | 8 weapon | 30 | 0 | ColdArrowProjectile (0xb0) | stat4 | MaleDarkElf*, Froglock*, Goblin*, Gremlin*, Orc*, Skeleton* |
| 45 | poisonarrow | SkillPoisonArrow | 5190a0 | 8 weapon | 30 | 0 | PoisonArrowProjectile (0xb0) | stat4 | MaleDarkElf*, Froglock* |
| 46 | multifire | SkillMultiFire | 5191b8 | 8 weapon | 30 | 0 | MissileWeapon (0x1c8) | stat4 | MaleDarkElf* |
| 47 | explodearrow | SkillExplodeArrow | 5192d0 | 8 weapon | 30 | 0 | ExplodeArrowProjectile (0x74) | stat4 | Goblin*, Gremlin*, Orc*, Skeleton* |
| 48 | archery | SkillArchery | 519358 | 3 passive | 30 | 0 | nothing (base cast) | stat4 |  |
| 49 | bash | SkillBash | 5195e0 | 0 active | 30 | 0 | SpellBash (0x28) | stat4 |  |
| 50 | minorhealing | SkillMinorHealing | 519750 | 0 active | 30 | 0 | SpellMinorHealing (0x24) | stat4 |  |
| 51 | ancestralcall | SkillAncestralCall | 519808 | 0 active | 30 | 1 | SpellAncestralCall (0x84) | stat4 |  |
| 52 | root | SkillRoot | 519ba0 | 0 active | 30 | 0 | SpellRoot (0x34) | stat4 |  |
| 53 | criticalhit | SkillCriticalHit | 519c58 | 0 active | 30 | 0 | SpellCriticalHit (0x5c) | stat4 |  |
| 54 | holyshield | SkillHolyShield | 519d10 | 0 active | 30 | 0 | SpellHolyShield (0x28) | stat4 |  |
| 55 | healing | SkillHealing | 519e50 | 0 active | 30 | 0 | SpellHealing (0x24) | stat4 | Bubo, FemaleDarkElf, Kobold, Orc |
| 56 | coneoffrost | SkillConeOfFrost | 519f08 | 1 channelled | 30 | 0 | SpellConeOfFrost (0x58) | stat4 | Tormentor |
| 57 | shockoffire | SkillShockOfFire | 51a190 | 0 active | 30 | 0 | Sparks (0xb8) | stat4 | Goblin, Demon*, Mummy* |
| 58 | froststorm | SkillFrostStorm | 51a218 | 0 active | 30 | 0 | FrostStormSpell (0xac) | stat4 | Cazic, Mummy, Goblin, Minion*, Ulthork* |
| 59 | lifetap | SkillLifeTap | 51a9e0 | 3 passive | 30 | 0 | no object in cast | 0 (passive) |  |
| 60 | Blunt | SkillBlunt | 512808 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 61 | Slashing | SkillSlashing | 512780 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 62 | strongstance | SkillStrongStance | 51b528 | 3 passive | 30 | 0 | no object in cast | 0 (passive) |  |
| 63 | naturalresistance | SkillNaturalResistance | 51b5b0 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 64 | stunningstrike | SkillStunningStrike | 51b638 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 65 | giantgrowth | SkillGiantGrowth | 51b6f0 | 0 active | 30 | 0 | SpellGiantGrowth (0x138) | stat4 |  |
| 66 | planarwind | SkillPlanarWind | 51b7a8 | 0 active | 30 | 0 | SpellPlanarWind (0xac) | stat4 | Marr |
| 67 | shadowstep | SkillShadowStep | 51bd78 | 0 active | 30 | 0 | SpellShadowStep (0x34) | stat4 |  |
| 68 | resurrect | SkillResurrect | 51be30 | 0 active | 30 | 0 | SpellResurrect (0x70) | stat4 |  |
| 69 | retribution | SkillRetribution | 51bfa0 | 0 active | 30 | 0 | SpellRetribution (0x5c) | stat4 |  |
| 70 | unspokenword | SkillUnspokenWord | 51ae88 | 0 active | 30 | 0 | SpellUnspokenWord (0x38) | stat4 |  |
| 71 | berserkerrage | SkillBerserkerRage | 51af40 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 72 | summonaxe | SkillSummonAxe | 51afc8 | 0 active | 30 | 0 | SpellSummonAxe (0x20) | stat4 |  |
| 73 | axebandolier | SkillAxeBandolier | 51b080 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 74 | lightquiver | SkillLightQuiver | 51b108 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 75 | summonarrows | SkillSummonArrows | 51b190 | 0 active | 30 | 0 | SpellSummonArrows (0x20) | stat4 |  |
| 76 | roar | SkillRoar | 51b248 | 0 active | 30 | 0 | SpellRoar (0x50) | stat4 |  |
| 77 | battlecry | SkillBattleCry | 51b300 | 0 active | 30 | 0 | SpellBattleCry (0x58) | stat4 |  |
| 78 | bloodlust | SkillBloodLust | 51b3b8 | 0 active | 30 | 0 | SpellBloodLust (0x4c) | stat4 |  |
| 79 | throwing | SkillThrowing | 51b470 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 80 | pusstorm | SkillPusStorm | 51b950 | 0 active | 30 | 0 | PusStorm (0xc0) | stat4 | FemaleDarkElf |
| 81 | berserkercriticalhit | SkillCriticalHit | 519c58 | 0 active | 30 | 0 | SpellCriticalHit (0x5c) | stat4 |  |
| 82 | berserkerriposte | SkillRiposte | 519528 | 3 passive | 30 | 0 | no object in cast | base (1.0) |  |
| 83 | berserkerdodge | SkillDodge | 519d98 | 3 passive | 30 | 0 | nothing (base cast) | 0 (passive) |  |
| 84 | berserkercyclone | SkillCyclone | 518ac8 | 0 active | 30 | 1 | SpellCyclone (0x7c) | stat4 |  |
| 85 | shamanroot | SkillRoot | 519ba0 | 0 active | 30 | 0 | SpellRoot (0x34) | stat4 |  |
| 86 | shamanhealing | SkillHealing | 519e50 | 0 active | 30 | 0 | SpellHealing (0x24) | stat4 |  |
| 87 | tagarsinsects | SkillTagarsInsects | 51b9d8 | 0 active | 30 | 0 | SpellTagarsInsects (0x94) | stat4 | Horsemen |
| 88 | drowsy | SkillDrowsy | 51bac0 | 0 active | 30 | 0 | SpellDrowsy (0x34) | stat4 |  |
| 89 | poisonbolt | SkillPoisonBolt | 51bc08 | 0 active | 30 | 0 | PoisonBolt (0xb8) | stat4 |  |
| 90 | summonbadger | SkillSummonBadger | 51bc90 | 0 active | 30 | 0 | CastBadger (creature, 0x3d0), SpellSummonBadger (0x20) | stat4 |  |
| 91 | raisearmy | SkillRaiseArmy | 51beb8 | 0 active | 30 | 0 | SpellRaiseArmy (0x34) | stat4 |  |
| 92 | battlemage | SkillBattleMage | 51c028 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 93 | penetratingarrows | SkillPenetratingArrows | 51c0b0 | 3 passive | 30 | 0 | nothing (base cast) | base (1.0) |  |
| 94 | spiritshield | SkillSpiritShield | 51c138 | 0 active | 30 | 0 | SpellSpiritShield (0x24) | stat4 | FemaleDarkElf, Marr |
| 95 | waveofflame | SkillWaveOfFlame | 51c2a8 | 0 active | 30 | 0 | SpellWaveOfFlame (0x2c) | stat4 | Cazic |
| 96 | frostarmor | SkillFrostArmor | 51c360 | 0 active | 30 | 0 | SpellFrostArmor (0x1c) | stat4 | Cazic, Kobold |
| 97 | diseaseblade | SkillDiseaseBlade | 51c418 | 0 active | 30 | 0 | SpellDiseaseBlade (0x24) | stat4 | Bubo |
| 98 | fireaxe | SkillFireAxe | 51c4d0 | 8 weapon | 30 | 0 | playerProjectile (0x1d0) | stat4 |  |
| 99 | coldaxe | SkillColdAxe | 51c558 | 8 weapon | 30 | 0 | playerProjectile (0x1d0) | stat4 |  |
| 100 | lightningstrike | SkillLightningStrike | 51c670 | 0 active | 30 | 0 | LightningStrikeSpell (0xbc) | stat4 | Hag |
| 101 | coneofshock | SkillConeOfShock | 51c728 | 1 channelled | 30 | 0 | SpellConeOfShock (0x58) | stat4 | Hag |

Notes on the table:

- Ids 31, 32, 52, 85 are one class (`SkillRoot`) under four names, likewise CriticalHit
  (33, 53, 81), Cyclone (41, 84), Dodge (2, 83), Riposte (9, 82) and Healing (55, 86): one
  variant per character class.
- Ids 27 and 28 both carry the name string "hatebeam"; 28's class is `SkillBallOfHate`.
- Ids 25 and 27–30 (DiseaseWeapons, HateBeam, BallOfHate, DiseaseEffect, HateEffect) have no
  cast of their own; monsters, traps and the two script built-ins hornOmen / planarSteel use
  them only as statistic tables for effects they construct themselves.
- SummonSkeleton and SummonBadger allocate a full creature (`Skelight`, `CastBadger`) and
  store the caster's player index at creature+0x5a when the caster is a player; arena kill
  credit reads that byte (0x3056cc).
- `PoisonRain` (run 0x2f9254, constructor 0x2f8f48) has its virtual table at 0x51aa68,
  directly after `SkillLifeTap`'s. (The earlier version gave 0x51aa60, which is the zero
  entry that ends the `SkillLifeTap` table, and said `vtables.txt` showed the two merged
  as a 34-entry SkillLifeTap table; the regenerated list has `PoisonRain` on its own
  line.)
- Ids 7 and 58, Goblin: the earlier version marked Goblin with * (statistics only) for both.
  `Goblin_run` casts both through slot 2 with the level from its own slot 35
  (0x26c4f4–0x26c53c; `docs/spec/skills-35-68.md` section 4.6).
- Id 17: every statistic of the hammer is read at level + 1, and the `HammerOfWrath`
  constructor makes one extra shared-generator draw for the item variant (0x2edefc, through
  `item_randomizeVariant` 0x1046e0; `docs/spec/skills-01-34.md` section 17).
- Id 21: the `LostSoul` objects are purely visual; the effect is the `damage_radial` call in
  the cast function 0x2f4d34.
- Id 46: the cast builds plain `MissileWeapon` objects (0x2d9fc4). `MultiFireProjectile` is
  another class (table 0x519128, 0x78 bytes), built only by MaleDarkElf (0x25cab4).
- Ids 96 and 97, "Monsters" column: Cazic casts Frost Armor with the whole monster level
  rather than slot 35 (0x24bbe8); Bubo casts Disease Blade with an ally as the caster
  argument and attaches the spell to that ally (0x249014) (`docs/spec/skills-69-101.md`).
- Ids 33 and 53: the earlier version had the two name strings the other way round.
  `SkillCriticalHit_ctor` gives id 53 the string `criticalhit` and id 33
  `rangercriticalhit` (0x2e72a0–0x2e72fc); the statistics rows below were already under
  the right ids.
- "Cast creates" for ids 21, 46, 57, 98 and 99 read `Projectile@0x50e7e8`,
  `Projectile@0x50e5a0`, `Projectile@0x50e998` and `Projectile@0x50e470` in the earlier
  version, and id 22 an invented `DismissUndeadProjectile`; the old `vtables.txt` labelled
  all five tables `Projectile`. Their classes are `LostSoul`, `MissileWeapon`, `Sparks`,
  `playerProjectile` and `HolyBolt` (table 0x50e908); see `docs/issues/vtable-labels.md`.

## Statistics set by slot 9

Extracted by tracking constant stores in each initStats function (the six id-dependent
classes were transcribed by hand). `sN: a +b/lv from lv L` reads: statistic N is a at level L
and grows by b per level; without "from" L is 1. Per-level steps are stored as floats that
are slightly off round numbers (9.00891 for 9); they are shown rounded. The meaning of each
index was only established for the skills read by hand: DiseaseBolt s0 damage (Observed in
the hit handler 0x2caec8; the earlier version had it Inferred from the ±20 % range its
description prints. The type-0x26 entry the bolt passes with it is not a damage: the disease
it starts ticks for 1 unless Bubo started it, 0x2d5854 — `docs/spec/skills-01-34.md`); Healing s0 percent of maximum hit points, s1
radius in 12-unit steps (0x2e8ec8, 0x2e90b8); Cyclone s0 attack damage percent, s1 number of
spin-animation loops, s2 movement speed percent (0x2d17c8, 0x2d1a94); s4 is the mana cost
wherever the Mana column says stat4. Tier 2 applies to non-player casters; an empty tier 2
cell means those casters get tier 1.

| Id | Name | Tier 1 (players) | Tier 2 (others) |
|---|---|---|---|
| 1 | wizardbeam | s0: 135 +11/lv; s1: 8 +0.333/lv; s2: 1 +0.333/lv from lv 5; s3: 4 +0.2/lv from lv 5 |  |
| 2 | dodge | s0: 20 +3/lv | s0: 5 +5/lv |
| 4 | diseasebolt | s0: 30 +9/lv; s1: 1 +0.333/lv from lv 5 | s0: 2 +2/lv; s1: 1 +0.1/lv |
| 5 | diseaseshield | s0: 20 +2/lv; s1: 2 +0.25/lv; s2: 5 +0.25/lv | s0: 1 +2/lv; s1: 5 +0.05/lv; s2: 1 +0.1/lv |
| 6 | diseasetrail | s0: 10 +2/lv; s1: 3 +0.333/lv |  |
| 7 | firestorm | s0: 108 +2/lv; s1: 2 +0.333/lv; s2: 2 +0.333/lv | s0: 5 +2.5/lv; s1: 2 +0.1/lv; s2: 2 +0.1/lv |
| 8 | fireflares | s0: 95 +5/lv; s1: 32 +1/lv from lv 7; s2: 8 +1/lv; s3: 1 +0.333/lv |  |
| 9 | riposte | s0: 20 +4/lv (min lv 0); s1: 10 | s0: 2 +2/lv; s1: 15 |
| 10 | blessed | s0: 90 +10/lv; s1: 30; s2: 1 +0.333/lv; s4: 1 +1/lv |  |
| 11 | summonskeleton | s0: 13 +1/lv; s1: 5 +5/lv | s0: 10 +1/lv; s1: 5 +3/lv |
| 12 | lightningweapons | s0: 10 +7/lv; s1: 10 +0.502/lv; s2: 8 +1/lv from lv 6; s3: 21 +1/lv from lv 6 | s0: 2 +2/lv; s1: 15 +2/lv |
| 13 | fireweapons | s0: 21 +7/lv; s1: 10 +0.503/lv; s2: 2 +0.333/lv from lv 6; s3: 15 +1/lv from lv 6 | s0: 2 +2/lv; s1: 15 +2/lv |
| 14 | coldweapons | s0: 14 +7/lv; s1: 10 +0.501/lv; s2: 12 +1/lv from lv 6; s3: 25 +1/lv from lv 6 | s0: 2 +2/lv; s1: 15 +2/lv |
| 15 | undeadshield | s0: 50 +4/lv; s1: 10 +1.25/lv; s2: 25 +2/lv |  |
| 16 | holystrike | s0: 18 +7/lv; s1: 35 +10/lv; s2: 1 +0.25/lv from lv 5 |  |
| 17 | hammerofwrath | s0: 40 +2/lv; s1: 15 +0.2/lv; s2: 5 +2.5/lv |  |
| 18 | coneoffire | s0: 380 +11/lv; s1: 30 +0.2/lv | s0: 2 +2/lv; s1: 30 +0.05/lv |
| 19 | regeneration | s0: 10 +5/lv |  |
| 20 | blindinglight | s0: 50 +1/lv; s1: 35 +2/lv; s2: 3 +0.2/lv; s3: 2 +0.25/lv |  |
| 21 | repulseundead | s0: 200 +10/lv; s1: 6 +0.5/lv |  |
| 22 | dismissundead | s0: 350 +10/lv; s1: 80 +8/lv; s2: 3 +0.25/lv |  |
| 23 | shockoffrost | s0: 30 +8/lv; s1: 3 +0.25/lv from lv 5; s2: 27 +4/lv from lv 5 | s0: 3 +3/lv; s1: 1 +0.1/lv from lv 10; s2: 14 +2/lv from lv 10 |
| 24 | poisonrain | s0: 0; s1: 0; s2: 0 | s0: 2 +2/lv; s1: 2 +0.1/lv; s2: 3 +0.05/lv |
| 25 | diseaseweapons |  | s0: 4 +2/lv |
| 26 | poisonweapons | s0: 40 +6/lv; s1: 15 +2/lv; s2: 2 +0.334/lv from lv 5; s3: 25 +2/lv; s4: 70 +10/lv | s0: 2 +2/lv; s1: 15 +2/lv |
| 27 | hatebeam |  | s0: 2 +2/lv |
| 28 | hatebeam (sic) |  | s0: 2 +2/lv |
| 29 | diseaseeffect | s0: 3 +1/lv | s0: 1 +1/lv |
| 30 | hateeffect |  | s0: 2 +2/lv |
| 31 | clericroot | s0: 1 +0.333/lv; s1: 5 +0.333/lv; s2: 50 +2/lv; s4: 55 +4/lv |  |
| 32 | rangerroot | s0: 1 +0.333/lv; s1: 5 +0.333/lv; s2: 50 +2/lv; s4: 30 +3/lv |  |
| 33 | rangercriticalhit | s0: 10 +2/lv; s1: 6 +0.301/lv from lv 10; s2: 8 +0.251/lv; s4: 35 +4/lv |  |
| 34 | shieldbash | s0: 30 +5/lv; s1: 20 +2/lv; s2: 4 +0.5/lv; s3: 1 +0.25/lv; s4: 27 +4/lv |  |
| 35 | charge | s0: 120 +10/lv; s1: 55 +3/lv from lv 10; s2: 3 +1.33/lv from lv 10; s3: 1 +0.333/lv from lv 8; s4: 35 +3/lv |  |
| 36 | darkness | s0: 50 +2/lv; s1: 35 +3/lv; s2: 1 +0.333/lv; s3: 3 +0.251/lv; s4: 33 +4/lv |  |
| 37 | shock | s0: 77 +9/lv; s1: 1 +0.333/lv from lv 5; s4: 19 +3/lv | s0: 2 +2/lv; s1: 1 +0.1/lv from lv 10 |
| 38 | groundpound | s0: 70 +10/lv; s1: 6 +1/lv; s2: 10 +3/lv from lv 10; s3: 2 +0.25/lv from lv 10; s4: 28 +3/lv | s0: 20 +5/lv; s1: 12 +12/lv |
| 39 | convertenemy | s0: 1 +0.2/lv; s1: 15 +1/lv; s2: 40 +2/lv; s4: 97 +7/lv |  |
| 40 | convertundead | s0: 1 +0.2/lv; s1: 15 +1/lv; s2: 60 +1/lv; s4: 104 +5/lv |  |
| 41 | cyclone | s0: 30 +3/lv; s1: 1 +0.2/lv; s2: 40 +2/lv; s4: 24 +3/lv |  |
| 42 | harmtouch | s0: 420 +12/lv; s1: 5 +0.333/lv; s4: 135 +6/lv | s0: 5 +5/lv; s1: 4 |
| 43 | firearrow | s0: 41 +5/lv; s1: 395 +22.4/lv; s2: 8 +0.415/lv; s4: 25 +3/lv | s0: 2 +2/lv |
| 44 | coldarrow | s0: 40 +5/lv; s1: 498 +5.6/lv; s2: 6 +5/lv; s3: 3 +0.332/lv; s4: 14 +3/lv | s0: 2 +2/lv |
| 45 | poisonarrow | s0: 45 +5/lv; s1: 366 +30.7/lv; s2: 1 +0.6/lv; s3: 3 +0.251/lv; s4: 37 +3/lv | s0: 2 +2/lv |
| 46 | multifire | s0: 120 +10/lv; s1: 478 +7.29/lv; s2: 2 +0.201/lv; s4: 5 +2/lv | s0: 2 +2/lv; s1: 450 +4/lv; s2: 2 +0.1/lv |
| 47 | explodearrow | s0: 150 +9/lv; s1: 417 +12.8/lv; s2: 38 +3/lv; s4: 55 +3/lv | s0: 2 +2/lv; s1: 400 +5/lv; s2: 45 +1/lv |
| 48 | archery | s0: 15 +5/lv; s4: 1 +1/lv |  |
| 49 | bash | s0: 50 +10/lv; s1: 20 +2/lv; s2: 4 +0.5/lv; s3: 1 +0.25/lv; s4: 16 +3/lv |  |
| 50 | minorhealing | s0: 30 +3.5/lv; s4: 100 +8.5/lv |  |
| 51 | ancestralcall | s0: 125 +5/lv; s1: 110 +2/lv; s2: 10 +0.501/lv; s3: 4 +0.507/lv; s4: 85 +4/lv |  |
| 52 | root | s0: 1 +0.333/lv; s1: 5 +0.333/lv; s2: 50 +2/lv; s4: 88 +8/lv |  |
| 53 | criticalhit | s0: 10 +2/lv; s1: 6 +1/lv; s2: 8 +0.251/lv; s4: 25 +4/lv |  |
| 54 | holyshield | s0: 5 +3/lv; s1: 10 +0.25/lv; s4: 24 +6/lv |  |
| 55 | healing | s0: 30 +3.5/lv; s1: 5 +0.334/lv; s2: 20 +4/lv; s4: 55 +6/lv | s0: 15 +5/lv; s1: 5 +0.4/lv; s2: 10 +4/lv |
| 56 | coneoffrost | s0: 350 +11/lv; s1: 1 +4/lv; s2: 20 +1/lv; s4: 48 +1/lv |  |
| 57 | shockoffire | s0: 162 +11/lv; s1: 45 +2/lv from lv 5; s2: 2 +1.3/lv from lv 5; s3: 243 +5.88/lv; s4: 31 +2/lv | s0: 3 +2.5/lv; s1: 5 +1/lv from lv 5; s2: 2 +0.1/lv from lv 10; s3: 243 +1/lv |
| 58 | froststorm | s0: 28 +2/lv; s1: 2 +0.201/lv; s2: 2 +0.251/lv; s3: 31 +1.25/lv; s4: 40 +8/lv | s0: 20 +4/lv; s1: 4 +0.8/lv; s2: 3 +0.35/lv; s3: 31 +1/lv |
| 59 | lifetap | s0: 10 +0.749/lv; s1: 15 +5/lv |  |
| 62 | strongstance | s0: 5 +5/lv |  |
| 63 | naturalresistance | s0: 3 +3/lv |  |
| 64 | stunningstrike | s0: 5 +2.25/lv |  |
| 65 | giantgrowth | s0: 50 +2.5/lv; s1: 5 +0.5/lv; s4: 75 +7.5/lv |  |
| 66 | planarwind | s0: 200 +10/lv; s1: 40 +3.54/lv; s2: 631 +35/lv; s3: 20 +2/lv from lv 10; s4: 75 +3/lv | s0: 40 +10/lv; s1: 40 +3/lv; s2: 631 +35/lv; s3: 20 +2/lv from lv 10 |
| 67 | shadowstep | s0: 60 +20/lv; s1: 1 +0.501/lv from lv 5; s4: 64 +5/lv |  |
| 68 | resurrect | s0: 10 -0.5/lv; s1: 25 +3.75/lv; s2: 3 +0.5/lv; s3: 10 +3.75/lv; s4: 90 +8/lv |  |
| 69 | retribution | s0: 4 +0.333/lv; s1: 20 +3/lv; s4: 75 +8/lv |  |
| 70 | unspokenword | s0: 20 +5/lv; s1: 7 +0.5/lv; s2: 25 +2/lv; s3: 3 +0.334/lv; s4: 51 +8/lv |  |
| 71 | berserkerrage | s0: 10 +3/lv; s1: 30 +2/lv |  |
| 72 | summonaxe | s0: 10 +5/lv; s4: 26 +6/lv |  |
| 73 | axebandolier | s0: 20 +3/lv |  |
| 74 | lightquiver | s0: 15 +3/lv |  |
| 75 | summonarrows | s0: 20 +2/lv; s4: 38 +5/lv |  |
| 76 | roar | s0: 6 +0.251/lv; s1: 40 +9/lv; s4: 16 +3/lv |  |
| 77 | battlecry | s0: 20 +2/lv; s1: 125 +3/lv; s2: 15 +0.501/lv; s3: 4 +0.503/lv; s4: 60 +7/lv |  |
| 78 | bloodlust | s0: 10 +1/lv; s1: 30 +2/lv; s2: 40 -0/lv; s4: 30 +3/lv |  |
| 79 | throwing | s0: 15 +5/lv |  |
| 80 | pusstorm | s0: 2 +0.201/lv; s1: 85 +5/lv; s2: 2 +0.251/lv; s3: 32 +0.752/lv; s4: 55 +6/lv | s0: 2 +0.33/lv; s1: 50 +5/lv; s2: 2 +0.33/lv; s3: 10 +1/lv |
| 81 | berserkercriticalhit | s0: 10 +2/lv; s1: 6 +0.751/lv from lv 5; s2: 8 +0.251/lv; s4: 35 +4/lv |  |
| 82 | berserkerriposte | s0: 10 +4/lv (min lv 0); s1: 10 | s0: 2 +2/lv; s1: 15 |
| 83 | berserkerdodge | s0: 20 +3/lv | s0: 5 +5/lv |
| 84 | berserkercyclone | s0: 50 +3/lv; s1: 2 +0.201/lv; s2: 45 +2/lv; s4: 51 +4/lv |  |
| 85 | shamanroot | s0: 1 +0.333/lv; s1: 5 +0.333/lv; s2: 50 +2.2/lv; s4: 100 +8/lv |  |
| 86 | shamanhealing | s0: 30 +3.5/lv; s1: 5 +0.334/lv; s2: 20 +4/lv; s4: 72 +7/lv | s0: 15 +5/lv; s1: 5 +0.4/lv; s2: 10 +4/lv |
| 87 | tagarsinsects | s0: 1 +0.251/lv; s1: 20 +2/lv; s2: 3 +0.335/lv; s4: 30 +13/lv | s0: 1 +0.25/lv; s1: 10 +2/lv; s2: 2 +0.25/lv |
| 88 | drowsy | s0: 2 +0.502/lv; s1: 4 +0.251/lv; s2: 50 +1.5/lv; s3: 60 -0/lv; s4: 21 +4/lv |  |
| 89 | poisonbolt | s0: 26 +5/lv; s1: 1 +0.251/lv; s2: 12 +2/lv; s3: 2 +0.251/lv; s4: 8 +2/lv |  |
| 90 | summonbadger | s0: 1 +1/lv; s4: 120 +8/lv | s0: 1 +1/lv |
| 91 | raisearmy | s0: 5 +0.501/lv; s1: 2 +0.175/lv; s2: 10 +1/lv; s4: 160 +7/lv |  |
| 92 | battlemage | s0: 80 +4/lv |  |
| 93 | penetratingarrows | s0: 45 +2/lv; s1: 35 +2/lv |  |
| 94 | spiritshield | s0: 10 +1/lv; s1: 10 +2/lv; s4: 85 +10/lv | s0: 10 +1/lv; s1: 20 +1/lv |
| 95 | waveofflame | s0: 5 +0.334/lv; s1: 210 +20/lv; s4: 60 +5/lv | s0: 5 +0.33/lv; s1: 20 +2/lv |
| 96 | frostarmor | s0: 10 +0.502/lv; s1: 20 +2/lv; s2: 20 +1/lv; s4: 41 +5/lv | s0: 15 +1/lv; s1: 30 +1/lv; s2: 20 +1/lv |
| 97 | diseaseblade | s0: 21 +2/lv; s1: 15 +2/lv; s2: 3 +0.501/lv from lv 5; s3: 15 +1/lv; s4: 50 +6/lv | s0: 21 +2/lv; s1: 15 +2/lv |
| 98 | fireaxe | s0: 300 +20/lv; s1: 50 +6/lv; s4: 25 +3/lv |  |
| 99 | coldaxe | s0: 300 +20/lv; s1: 150 +6/lv; s4: 70 +3/lv |  |
| 100 | lightningstrike | s0: 2 +0.33/lv; s1: 50 +5/lv; s2: 2 +0.33/lv; s3: 32 +1/lv; s4: 1 +1/lv | s0: 5 +0.33/lv; s1: 20 +2/lv; s2: 2 +0.33/lv; s3: 32 +1/lv |
| 101 | coneofshock | s0: 275 +5/lv; s1: 1 +0.2/lv; s2: 30 +0.2/lv; s4: 42 +2/lv | s0: 2 +2/lv; s1: 1 +0.2/lv; s2: 30 +0.2/lv |

## Functions that matter

| Address | Name | Why |
|---|---|---|
| 0x16ac74 | (outside range) start-up initialiser | constructs the 101 static Skill objects in id order |
| 0x41b170 | g_skillTable | link-time pointer table, id → Skill |
| 0x1a42b8 | (player area) player skill-cast helper | the only place that pays mana, starts the recast counter and attaches the Spell |
| 0x1e8ea8 | (gameplay area) weapon-effect cast inside the damage function | casts any id for any attacker |
| 0x11a868 | (creature area) Creature slot 17 | runs every attached Spell |
| 0x3c85fc / 0x3c8690 / 0x3c87f0 | base Skill slots 10 / 11 / 12 | the statistic formula and the player / non-player split |
| 0x2cb0e0 … 0x2cb368 | SkillDiseaseBolt_* | the smallest complete example of a skill file |
| 0x2c9eb0, 0x2ca1a8, 0x2caec8 | DiseaseBolt_ctor / _run / _onHit | projectile pattern |
| 0x2e8ec8, 0x2e90b8 | SpellHealing_ctor / _run | the cleanest example of a Spell with separate player and creature branches |
| 0x2d17c8, 0x2d1a94 | SpellCyclone_ctor / _run | a copy-castable, pad-driven movement spell |
| 0x2e18a4 | SkillSummonSkeleton_cast | summons a creature; guarded for non-player casters |
| 0x304c4c, 0x306b78, 0x307284 | arena_init / _runTask / _drawTask | arena mode entry points |
| 0x305580, 0x305650 | arena_onPlayerKilled / arena_loseLife | arena score, skipped for the prediction copy |

## Per-machine state

Background facts used below (Observed unless marked):

- `net_isLocalSlot` (0x13e150) and the helper 0x13e180 are per-machine by construction.
  0x13e180 takes an object and returns it unchanged, except that for a player object in a
  local slot of a net game it returns the prediction copy (`g_ghost`) when one exists.
- There is a **fourth generator at 0x404468** (the third global seed word, after 0x404460
  and 0x404464; "fourth" counts the per-object generators). This sentence used to say the
  overview did not mention it; `docs/OVERVIEW.md` now lists it as a further cosmetic
  generator. It has the same
  constants as the others and is used only for effects (particle spread, decals, the variant
  number in a sound name). Player_run draws from it at 0x1aa8ac–0x1aa9ac to pick a swing
  sound, with no test for the prediction copy in that block; since prediction restores only
  0x404464, its value should be treated as different on every machine (Inferred — not
  checked whether that block can run for the copy).
- The frame counter 0x44fdcc is set to the lockstep frame number for the duration of the
  simulated tick and put back afterwards (net_frameLoop, stores at 0x13af98 and 0x13b28c);
  prediction advances it separately. So `counter % n` timing in spell run code is shared
  state, and the same expression in draw code is not.
- **0x44fdc0 is a user option** (written by config_setDefaults 0x1e62f8 and the options
  screen 0x222d5c — both addresses are the stores; the functions are `config_setDefaults`
  0x1e6238 and `memcard_optionsScreen` 0x222b40, and other documents call the option
  `g_decalDetail`; it gates decals and gut chunks, so presumably the gore level). Whether a
  net game forces it to the same value on every machine was not checked (Unknown). One
  function in this range reads it from simulation code — item 2 below. Outside the range
  Creature_processDamage (0x1113fc, 0x1116bc, 0x1116f8), Player_processDamage (0x1b31f4)
  and the GutChunk constructors read it too; a GameObject created or not created depending
  on it would be a sync problem, which the owners of those areas should check.
- In a net game `0x13e0c8(slot)` returns a per-slot facing from the table at 0x5d0bc0 instead
  of the camera yaw; whether that table is filled from the input records was not checked
  (Unknown; it belongs to netcode). SpellCyclone_run steers with it.

### (a) Player index used without the is-player test

`caster+0x3c8` is only meaningful when flag 0x40 is set at +0xc. The scan covered every load
at displacement 0x3c8 and every reference to the player record table in the range (about 120
sites in 70 functions).

Guarded — the test is in the same function ahead of the read (Observed): SkillSummonSkeleton
canUse 0x2e2368 and cast 0x2e18a4; SkillSummonBadger 0x310690, 0x3106f4; SkillFireStorm
canUse 0x2d532c; SkillGroundPound canUse 0x2c7140; the five bow canUse functions; the arrow
hit handlers 0x2d685c, 0x2d7aac, 0x2d932c, 0x2da610; SkillMultiFire_cast 0x2d9a90;
SpellHealing 0x2e8ec8, 0x2e90b8; the weapon-buff spells (Lightning, Fire, Cold, Poison,
DiseaseBlade) in both constructor and run; SpellConvertEnemy / ConvertUndead run;
SpellCharge_run 0x2c8f2c; SpellDrowsy_run 0x30e6f0; SpellResurrect constructor and
destructor; SpellRetribution_healOwner 0x314790; arena_addKill 0x3056cc. The CriticalHit aura
query 0x2e76c4 has no test of its own but its only caller tests the attacker first
(0x1e8230, just before the three calls).

Not guarded (Observed). None of these is called by a monster run function that was found, so
each is a hazard only through the weapon-effect cast or a caller not yet read:

| Address | Function | What it does with the index |
|---|---|---|
| 0x2d19d8 | SpellCyclone_ctor | passes it to `player_voice` (0x2d19dc; the earlier version said "posts a player notice") |
| 0x2d1d94, 0x2d1dfc, 0x2d1efc, 0x2d2190 | SpellCyclone_run | reads the slot's analog stick from g_pads, the per-slot facing, calls the player move function, tests net_isLocalSlot |
| 0x2de848, 0x2deda0 | SpellBash_run | passes g_pads[index] to the player move function; net_isLocalSlot |
| 0x2faeec, 0x2fb450 | SpellShieldBash_run | same |
| 0x2e04a8, 0x2e053c | SpellMinorHealing ctor / run | reads maximum and writes current hit points of record[index] |
| 0x2e0a5c | SpellAncestralCall_ctor | reads the weapon-style byte |
| 0x2fecb8–0x2fed68 | SpellSummonAxe_ctor | adds an item to the inventory, changes mana |
| 0x2ff9b0–0x2ffa60 | SpellSummonArrows_ctor | same |
| 0x30023c, 0x30043c, 0x30048c | SpellRoar ctor / run | weapon-style byte; net_isLocalSlot; writes mana |
| 0x3017d0, 0x301abc, 0x301b10 | SpellBattleCry ctor / run | same |
| 0x303308, 0x303570, 0x3035b8 | SpellBloodLust ctor / run | same |
| 0x3093a8, 0x309640 | SpellGiantGrowth dtor and helper 0x309524 | writes record +0x4c20. Listed here by mistake: the guard is one level up, in the cast, which returns for a non-player before it allocates the spell (0x308fc0) |
| 0x312e10, 0x312ea4 | SpellResurrect_run | reads the object pointer of record[index], writes hit points. The index read at both sites is the *target* player's, not the caster's (`docs/spec/skills-35-68.md` section 4.6) |
| 0x313d74 | SpellRaiseArmy raise step (`SpellRaiseArmy_raiseInRing` 0x313bd4) | reads the caster's index with a byte load, which the scan for word loads at displacement 0x3c8 missed (`docs/spec/skills-69-101.md` SC8) |
| 0x31992c … 0x319d50 | SkillFireAxe_cast | decrements the thrown-axe stack, removes the item, writes two per-slot HUD arrays (0x41b844, 0x41b8c4) |
| 0x31a260 … 0x31a684 | SkillColdAxe_cast | same |

For the two axe skills canUse returns 1 for a non-player, so canUse would not stop one.

### (b) Other per-machine inputs

| # | Where | What | Kind |
|---|---|---|---|
| 1 | SkillMultiFire_cast 0x2d9e08–0x2d9ec8 | When the caster is **not** a player, the second damage figure handed to each projectile constructor (stack argument stored at 0x2d9fb4) is base + base × 0.2 × a value drawn from the **cosmetic** generator 0x404460 (two draws). The player branch uses the weapon record instead. If this branch ever runs, projectile damage differs between machines | Observed code; reachability Unknown. No monster was found calling this slot (MaleDarkElf builds MultiFireProjectile itself); the weapon-effect cast could |
| 2 | SpellBloodLust_run 0x3034dc (0x13e180 call, then the test at 0x303e24) | The number of `Spell_rand` draws per frame (0–3 bursts of four or more per hand) depends on (i) how far the attachment points of the object returned by 0x13e180 moved — the prediction copy on the owner's machine, the real player elsewhere — and (ii) the user option 0x44fdc0 being above 0. The spell's private generator therefore diverges between machines. In this spell it feeds particles only (the function makes no damage call and no allocation, and no creature write uses a drawn value), so the divergence is contained | Observed |
| 3 | 0x13e180 in SkillCharge_cast 0x2c8864, SpellCharge_run 0x2c8f2c, SpellCyclone_run 0x2d1a94 | Writes the action state (+0x58c) or starts an animation on the returned object as well as on the real player. On the owner's machine the extra write lands on the copy only. For `SpellCyclone_run` that is not the whole of it: on a machine where the owner is remote, `net_objOrGhost` returns the real player, so there the animation is started on the real player a second time (0x2d1b04, 0x2d1d1c–0x2d1d38; FINDINGS G22, `docs/issues/prediction-copy.md` 3.3; the earlier version said "on the copy only" for all three) | Observed; harmless direction for the Charge pair; for Cyclone the effect of the doubled start on the simulation is Unknown |
| 4 | 0x13e180 in 0x2dedec, 0x2fb49c, SpellAncestralCall_run 0x2e0d10, SpellCriticalHit_run 0x2e7acc, SpellHealing_run 0x2e90b8, SpellSummonAxe_run 0x2feddc, SpellSummonArrows_run 0x2ffad4, SpellBattleCry_run 0x301a34, SpellBloodLust_ctor 0x303254 | Particle and light positions follow the copy on the owner's machine. Loop counts and `Spell_rand` counts in these functions do not depend on the returned object (read for each). SpellBattleCry_run later uses `Spell_rand` for a gameplay roll (percent chance per creature in range, decomp line 534), so it matters that its earlier draws are position-independent — they are | Observed |
| 5 | SkillRiposte_counterAttack 0x2ddccc, SkillSummonSkeleton_cast 0x2e18a4, SkillStrongStance_trigger 0x308578 | Cosmetic generator used for particle placement only; the damage roll in the riposte uses the shared generator | Observed |
| 6 | GroundPoundEffect_run 0x2c7808, HammerOfWrath_run 0x2ee068 (0x2ef4c0, 0x2ef5e8), 0x308578 | Generator 0x404468 used for particles, decals (0x19f110) and water ripples (0x189514) only | Observed |
| 7 | StaticFire_run 0x2c595c (test at decomp line 157) | Everything after `isNearView(941, pos)` (the constant is 941.0, word 0x446b4000; the earlier version said 940) — particle draws from the object's own generator, the 12-frame damage tick, a draw from the shared generator per player hit — is skipped when the fire is not "near view". In a net game that means near any player, except while a cutscene is active when it means near the camera focus (D6). Shared only as long as D7 holds | Observed; depends on D7 |
| 8 | SmokeGen_run 0x31c898 | Also gated by isNearView, and since read (`docs/issues/rescan.md` R2, FINDINGS D35): the particle step and the damage tick — shared-generator draws, hit points, disease — run only when `isNearView(1000)` holds (0x31c8c0, 0x31ca8c). Same family as item 7 and D6. Which levels place a `SmokeGen` with damage is Unknown | Observed (was Unknown) |
| 9 | arena_pickSpawnPoint 0x3050a4 | Reads the camera focus and the camera object, but only when g_networkMode is 0; the net branch draws from the shared generator | Observed; guarded |
| 10 | arena_respawnPlayer 0x305784 | The screen effect 0x322954 is started only when the slot is the local one; shared → local only | Observed |
| 11 | SpellShadowStep_run 0x311e3c | Calls 0x1b3d90 on the stepping creature only when g_networkMode is 0 — offline and online behave differently, but every machine in a net game takes the same branch | Observed |
| 12 | Draw functions | All 18 GameObject slot-5 functions and the 3 Spell slot-3 functions in the range were checked for stores, allocations and generator draws: none writes anything but locals and two one-time "resource looked up" flags (0x50378c, 0x503790) | Observed |
| 13 | arena_drawTask 0x307284 and its three helpers | Write only the prompt fade value 0x8e735c | Observed |
| 14 | arena_onPlayerKilled 0x305580, arena_loseLife 0x305650 | Called from Player_processDamage, which also runs for the copy; both return at once when the player-table entry for that slot is the copy. This narrows finding G9: the arena life and kill counters are protected, whatever else that tail does | Observed |

No function in the range calls `net_getLocalPlayerSlot` other than item 10, reads the raw
pads, the local-menu flag from simulation code, an audio position, or a hardware timer
(checked by name against every decompiled function in the range; unnamed engine helpers that
read the camera would not have been caught — the 250 external callees were listed and the
camera-area ones, 0x189438, 0x189514 and 0x18a5c0, were opened: the first two are water-patch
queries, the third was not read).

### (c) Writers of 0x402797 (force the prediction copy to be rebuilt)

| Address | Function | Value | When |
|---|---|---|---|
| 0x2c90c8, 0x2c9570 | SpellCharge_run | 1 | every frame of a charge and when it ends, for any owner |
| 0x2d21a0 | SpellCyclone_run | 0x78 | each frame while spinning, only if the owner's slot is local |
| 0x2dedb0 | SpellBash_run | 0x3c | while the bash is active, local slot only |
| 0x2fb460 | SpellShieldBash_run | 0x3c | same |
| 0x30044c | SpellRoar_run | 1 | every frame in a net game, local slot only |
| 0x301acc | SpellBattleCry_run | 1 | same |
| 0x303580 | SpellBloodLust_run | 1 | same |
| 0x30ecf8 | SpellDrowsy_run | 1 | while the victim is held, when the victim is a player in a local slot |
| 0x311f20 | SpellShadowStep_run | 1 | every frame of the step, for any owner |
| 0x312edc | SpellResurrect_run | 1 | while the revive animation is driven |

All ten are spells that move the player, lock the player into an animation, or change the
action state at +0x58c outside the player's own input handling, which the copy cannot
predict. The table lists the spell stores only. Five more stores of 1 are outside this
area: `Player_processDamage` (0x1b2ef4, 0x1b352c, 0x1b3824), `Player_move` (0x1b5098) and
`player_respawn` (0x1bd1e8).

The byte is not a plain flag: two writers store 0x78 and 0x3c (120 and 60). The earlier
version inferred that the reader treats it as a frame count; the reader has since been
read and that is nearly right — it is a count of forced re-clones. `net_frameLoop`
subtracts one from the byte at each rebase while it is positive (0x13b25c–0x13b26c), so
after the last store 0x78 and 0x3c force a re-clone on each of the next 120 and 60 ticks
on which a rebase is allowed (`docs/issues/claims-audit.md` rows 45 and 79). Writing it is
harmless for sync: the copy is per-machine state already.

## Corrections to earlier notes

- `0x248598` is the run function of **Bubo** (slot 4 of the table at 0x513fe0), not of Cazic.
  Cazic's run is **0x24aaf0** (table 0x514128). FINDINGS ("Ruled out": "Horsemen_run 0x27236c
  and 0x248598 read none…") and the Cazic line in names.tsv should be re-read with that in
  mind: the Cazic function has not been checked by this pass either. (Since done: both
  now give 0x24aaf0, and `docs/monsters.md` §4 reads that function in full.)
- Cazic casts more than FireStorm and SummonSkeleton: also FrostStorm (58), WaveOfFlame (95)
  and FrostArmor (96) through slot 2, and GroundPoundEffect directly (0x24b0c8).
  `docs/monsters.md` §4 adds the condition: the states that make the slot-2 casts (0xc,
  0xd, and 10/0xb for the two shock helpers) are entered only when
  `Cazic_isNonAvatarAboveHalfHp` 0x24c564 is true, so the `cazicavatar` variant uses only
  the ground pound, and for ids 7, 11, 58, 95 and 96 the "Monsters" column above means
  the `cazicthule` variant.
- `g_skillTable` is not filled at start-up; the objects it points at are constructed then.
- A Skill table has 15 real slots and a Spell table 4; the counts 16 and 5 that the old
  `vtables.txt` gave include the terminating null entry (the regenerated list gives 15
  and 4).

## Open questions

1. Which skill ids appear in weapon item effects of type 0x29, and can a monster's weapon
   carry one? That decides whether the unguarded functions in (a) and item 1 in (b) are
   reachable. Needs the item tables.
2. Who calls slot 9 (initStats)? No direct or virtual call site was found; the statistics are
   presumably filled once at start-up (an offset-0x48/0x4c call on each table entry).
   (Answered since: exactly that call is in `skills_callVslot9All` 0x1ebca0, reached from
   `main` through `game_initCamera`; see the slot table.)
3. Is the table at 0x5d0bc0 (per-slot facing used by Cyclone and the player move function)
   part of the input record?
4. Can the Player_run block at 0x1aa8ac run for the prediction copy, making generator
   0x404468 per-machine as inferred above?
5. The reader of 0x402797 and the meaning of the values 0x3c and 0x78. (Answered since:
   `net_frameLoop` counts the byte down by one per rebase, 0x13b26c; see (c) above and
   `docs/issues/claims-audit.md` row 79.)
6. What statistic indices 1–3 mean for the skills not read by hand (the describeRank
   functions format them and would settle each one).
7. Slot 14's second argument (1, 2, 10, 20): dead in this build, purpose unknown.
8. Arena waves, scoring, the overlay and `SpellArena`'s flag and tint are in
   `docs/arena-modes.md`. The monster build at 0x3065fc was seen only as the call
   `arena_startWave` makes. `Boat` / `SkulBoat` slots 28–29 and everything from 0x31d2a0
   up (`SmokeGen`, listed here in the earlier version, is now read: `docs/issues/rescan.md`
   R2) were not read.
9. Not read at all: most projectile run functions (ShockProjectile, HolyStrike,
   HammerOfWrath, FrostShard, ShockOfFrost, PusStorm, Pustule, PoisonBolt,
   LightningStrikeSpell, DarknessProjectile, DiseaseTrail, DiseaseCloud), SpellWizardBeam_run
   (7.9 KB), the weapon-buff spell run functions beyond their guards, and SpellUnspokenWord,
   SpellPlanarWind, SpellRaiseArmy, SpellWaveOfFlame, SpellFrostArmor, SpellSpiritShield.
   They were covered only by the scans described in "Per-machine state" (player-index reads,
   named per-machine calls, the two effect generators, draw-function writes).
