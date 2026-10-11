# Corrections applied to the first-round area documents

Scope: the fifteen area documents `docs/{player,startup,creatures,monsters,skills,gameplay,
objects,runtime,engine,netcode,script,ui,audio-save,mainloop,netlib}.md` and the note
column of `symbols/*.tsv`. Later passes (`docs/data-tables.md`, `docs/issues/vtable-labels.md`,
`docs/monsters.md`, `docs/script.md`) reported errors in the first-round text; this pass
applied them, and then compared the documents with each other.

A second pass, made after more reports had come in, is recorded at the end of this file
under "Second pass", a third under "Third pass", a fourth under "Fourth pass", a fifth
under "Fifth pass" and a sixth under "Sixth pass"; sections 1 to 7 describe the first pass
only. The fourth pass is the first that applies results from the running game; the fifth
is the first that applies results from two linked instances of it; the sixth is the first
in which a result from two linked instances overturns one from an earlier run (the arena
with real characters against the arena with placeholder ones).

Everything below was checked in the executable (SLUS_209.73, v2.00) before it was written
into a document: the decompile, `tools/dis.py`, `tools/gxref.py`, the data words, and the
regenerated `vtables.txt`. Nothing was run. **Observed** = read at the address given;
**Inferred** and **Unknown** are marked. No patch and no `FINDINGS.md` row is proposed.

How the edits were made: the smallest change that fixes the statement, in place, in the
document's own table or paragraph. Where a statement was wrong (not just incomplete) the
new text keeps one clause saying what the earlier version said. No section was rewritten,
no address or name in a symbol file was changed. `netcode.md`, `audio-save.md`,
`mainloop.md` and `netlib.md` needed no edit.

## 1. Summary

| | Count |
|---|---|
| Reported corrections checked | 23 |
| … confirmed and applied | 23 (two with narrower wording than reported, see section 5) |
| … not confirmed | 0 |
| Further differences between documents settled from the code (section 3) | 33 |
| Symbol notes changed (section 4) | 5 rows in 4 files |
| Differences found and not settled, or outside the files of this pass (section 6) | 9 |

`python3 -I -B tools/symtab.py check` after the edits: 5,567 symbols, 0 conflicts,
0 malformed lines.

## 2. Reported corrections

"Said" is the earlier text in short; "Says now" the new text in short. Addresses in the
evidence column were read in this pass.

| # | Document, section | Said | Says now | Evidence (Observed unless marked) |
|---|---|---|---|---|
| 1 | `player.md`, record table, +0xcc | damage type passed to the damage function | attack rating = level (+0x58) × 20 + strength / 4 (dexterity / 4 with a bow or thrown weapon) + the weapon's rating; passed to the damage function as `attack` | `Player_recalcDamage` 0x1b71b8–0x1b7270 builds it; `Player_meleeHit` 0x1b6a98 passes it in the third integer argument of 0x1e8230, which compares it with victim +0xe4 |
| 2 | `startup.md`, item definition, +0x1a (and open question 2) | summed into record +0xcc, meaning Unknown | the weapon's attack rating | `item_getModifiedField1a` 0x103f88 (definition +0x1a raised by modifier 0x23), called at 0x1b721c and added to record +0xcc |
| 3 | `creatures.md`, layout, +0xd4 and +0xe4 | "scaled stat, Unknown" (both) | attack rating; armour | `Creature_setStats` 0x10a620 stores both; `Creature_hitTargetInArc` 0x119938 forwards its eighth argument as `attack`; `Amphian_run` 0x23483c passes +0xd0, +0xd2, +0xd4 then the flag word; 0x1e8230 reads victim +0xe4 as armour |
| 4 | `monsters.md`, §1.3 (hit helpers) and §2.1 (+0xd0…+0xd4) | damage min / max / **type** | damage min / max / **attack rating**; the damage class is in the flag word that follows | same as 3 |
| 5 | `skills.md`, id table and statistics table, ids 33 and 53 | 33 `criticalhit`, 53 `rangercriticalhit` | the other way round; statistics rows unchanged | `SkillCriticalHit_ctor` 0x2e72a0–0x2e72fc: id 0x35 takes the string at 0x550220, id 0x21 the one at 0x550248; `SkillCriticalHit_initStats` 0x2e730c confirms each row's numbers belong to its id |
| 6 | `skills.md`, slot table, slot 9 (and open question 2) | "Who calls it was not found" | `skills_callVslot9All` 0x1ebca0, from `game_initCamera` 0x1e6b68, from `main` | loop over `g_skillTable` calling table offset 0x48/0x4c at 0x1ebcc4–0x1ebcec; calls at 0x1e6bac and 0x323e48 |
| 7 | `gameplay.md`, §2.2 (and §9) | "Kind 0x12 is Unknown" | Inferred "bug" (insects) | effect types 0x19 / 0x1a are the item tokens `bugzapper` / `bugexploder` (token table in `startup.md`); constructors 0x235418, 0x24587c, 0x2ab450 store 0x12 at +0xb4. The name is **Inferred** from the tokens |
| 8 | `startup.md`, "The other tables", 0x3e9c18 | 10 × 3 floats | 12 rows, 10 selectable | rows 10 and 11 at 0x3e9c90–0x3e9ca7 are copies of row 9; the row argument is clamped to 0…9 at 0x100e64–0x100e88 |
| 9 | `objects.md`, "Reading the virtual tables" | scanner runs on "when the next table's type-info function is too large"; tool reports 17 and 92 | the two getters are 0x9c bytes and were *measured* as 0x130 and 0x1a0; `PoisonRain` was lost because its getter 0x3cffd4 is cut at a false function start 0x3d0000; the tool now reports 16 and 39 | `ghidra_funcs.tsv` bounds of 0x3c22b0, 0x3c1e28, 0x3cffd4; `tools/ps2elf.py func` output for the three; data words 0x3ea5a8, 0x55e3cc, 0x55f23c hold 0x003d0000; `vtables.txt` |
| 10 | `runtime.md`, §4.1 | one secondary table, 0x51c918 (delta −8), "class with two bases" | also 0x51cc08 (delta −4 in the header and slots 1–3, 0 in slots 4–5); both go with 0x51c8d8 | table words at 0x51cc08; the same three functions (0x324920, 0x3285a8, 0x3d26b0) load all three addresses |
| 11 | `skills.md`, notes after the id table, `PoisonRain` | table at 0x51aa60, merged with `SkillLifeTap` in `vtables.txt` | table at 0x51aa68; 0x51aa60 is the zero entry ending `SkillLifeTap`'s table | words at 0x51aa60–0x51aa74; `PoisonRain_ctor` loads 0x51aa68 at 0x2f8fc4 |
| 12 | `gameplay.md`, §4, row for table 0x50ea28 | class `Projectile` | `DummyDamager` (base `Projectile`) | getter 0x3c5b08 names `Projectile` then `DummyDamager`; `tools/vtab.py show DummyDamager` |
| 13 | `skills.md`, id table, "Cast creates" of ids 21, 46, 57, 98, 99 | `Projectile@0x50e7e8`, `@0x50e5a0`, `@0x50e998`, `@0x50e470` | `LostSoul`, `MissileWeapon`, `Sparks`, `playerProjectile` | getters 0x3c5f48, 0x3c62c0, 0x3c5c18, 0x3c64d8; the casts 0x2f4d34, 0x2d9a90, 0x2ed4e4, 0x31979c, 0x31a0d8 allocate 0xb0 / 0x1c8 / 0xb8 / 0x1d0 and call 0x2931bc, 0x150ee4, 0x28f880, 0x1bef58 |
| 14 | `skills.md`, id table, id 22 | `DismissUndeadProjectile` | `HolyBolt` (table 0x50e908) | getter 0x3c5d28; `SkillDismissUndead_cast` 0x2f645c allocates 0xc0 and calls 0x2f5248 |
| 15 | `player.md`, "Not read" | `Projectile_runThrown` 0x1ba940 | `playerProjectile_run` 0x1ba940 | slot 4 of table 0x50e470 |
| 16 | `engine.md`, per-machine P4 | "constructors of FireBeetle (0x24587c, 0x24726c)" | 0x24726c is the `FireFly` constructor | getter 0x3c40f0 (`FireBeetle`, then `FireFly`); 0x24726c is the only non-clone function loading table 0x5108c8 |
| 17 | `startup.md`, "Fields of other structures" | "Item prop (0x248 bytes, vtable 0x511ba8)" with no class | the class is `PhProp`; `ItemProp` is 0x511c38, 0x190 bytes | getter 0x3c3030; 0x155a0c (`PhProp_ctor`) loads 0x511ba8; 0x159458 loads 0x511c38 |
| 18 | `monsters.md`, §2.1 (+0x50), §7.10, open question 4 | "weapon helper" at table 0x50cda0, no class name, for Horsemen, Skelight and UndeadKnight | `WeaponShield` (base `Weapon1`) for Horsemen and UndeadKnight; plain `Weapon1` (0x50cf40) for Skelight | getter 0x3c22b0; last helper table loaded by each constructor: 0x271d94 (0x50cda0), 0x2b3f64 (0x50cda0), 0x2a87e8 (0x50cf40, and no 0x50cda0 in `Skelight_ctor`) |
| 19 | `creatures.md`, "Virtual slots: 39, not 92"; `skills.md`, corrections | present tense about the tool's counts (92; 16 and 5 with the null entry) | past tense; the regenerated list gives 39, 15 and 4 | `vtables.txt` |
| 20 | `runtime.md`, §4.2 | "`vtables.txt` has 24 such labels", "also lacks three tables", "lists SmokeGen with 748 entries" | all three in the past tense, with what the regenerated list has | `vtables.txt` (478 lines; `SmokeGen` 16) |
| 21 | `monsters.md`, §8 | 13 tables "that `vtables.txt` lists as" base classes; Cazic and `names.tsv` notes "should" be fixed | listed; FINDINGS and `names.tsv` have since been corrected | `vtables.txt`; `FINDINGS.md` "Ruled out"; `names.tsv` row 0x24a670 |
| 22 | State 0x14 is the death state | no area document still called it a cutscene state; `script.md` listed "AI state 0x14" as an open meaning | `script.md` field table and open question 8 say death state; `monsters.md` §1.4 notes D19 was reworded | `Creature_filterState` 0x10a9c0 clears all timers on a request for 0x14; `script_killMonster` 0x144a84 requests it with flags 0x2009 and hit points 0 |
| 23 | `symbols/netcode.tsv`, `scr_load` note (and `script.md` §7) | "checks magic 0xf1e0 and version 0x18, unpacks the relocation list" | 0x18 is the name-record size at header +0xa; the loop expands the optional compact encoding (flag bit 2) | decompile of 0x13e8f8: the two header tests, the byte at +7 compared with 4, the loop under `flags & 4` |

Also changed, from the note in `docs/issues/vtable-labels.md` §8: `monsters.md` §3.2 gives
the `LostSoul` constructor as 0x2931bc instead of 0x293228 (prologue at 0x2931bc, both
callers 0x2f4e2c and 0x2f6364 go there, 0x293228 is mid-function; `symbols/monsters.tsv`
already had the new address).

## 3. Consistency sweep: differences between documents, settled from the code

Each row is a field, function or constant that two documents described differently (or
one gave as Unknown and another explained). The document named first was edited.

| # | Document, section | Said | Says now | Other document | Evidence |
|---|---|---|---|---|---|
| 1 | `gameplay.md` §2.1, `$a2` | melee passes "the player's record value at 0x4d8bbc" | adds: that is record +0xcc, the attack rating; monster melee passes creature +0xd4 | `player.md`, `creatures.md` | as section 2, rows 1 and 3 |
| 2 | `creatures.md`, +0x5c | per-kind resistances, three of five Unknown | fire, cold, poison, disease, lightning | `gameplay.md` §2.3 | 0x1e8230 uses +0x5c / +0x60 / +0x64 / +0x68 / +0x6c with the fire, cold, poison, disease and lightning effects |
| 3 | `creatures.md`, +0xb4 | Unknown | creature kind (0x10 undead, 0x12 insects, names Inferred) | `gameplay.md` §2.2–2.3 | constructors store it (0x2a5af4: 0x10; 0x235418: 0x12); 0x1e8230 tests it |
| 4 | `creatures.md`, +0xcc | Unknown | damage accumulated by hits flagged 0x800000 | `gameplay.md` §2.3–2.4 | 0x1ea6f0–0x1ea790 |
| 5 | `creatures.md`, +0x2f8 | Unknown | obstacle-avoidance side | `startup.md` | `Creature_computeAvoidanceOffset` 0x108a60 |
| 6 | `creatures.md`, +0x348, +0x34c | "second visual-effect timer"; "two damage-over-time timers" | +0x348 shock, +0x34c poison; +0x350 setter not traced | `gameplay.md` §2.3 | `Creature_setEffectTimer` 0x118950 index 2 → +0x348, 3 → +0x34c; the calls in 0x1e8230 |
| 7 | `creatures.md`, slot 35 | purpose Unknown | the level a monster passes to a skill it casts (Inferred in `monsters.md`) | `monsters.md` §1.2, `skills.md` | 0x118c50 |
| 8 | `creatures.md`, "AI state"; `monsters.md` §1.4 and §2.1 | two lists with different words (1 "charmed creature touched" / "walk back"; 5 "held in place" / "between attacks"; timers "A, B, C" / root, cooldown, stun) | each points at the other and says they are the same states and timers | each other | `Creature_filterState` 0x10a9c0: +0x314 forces 5, +0x31c forces 0x13, +0x318 forces 0x10; 0x1195e0, 0x1195f0, 0x119608 |
| 9 | `monsters.md` §1.2, slots 23 / 25 / 26 / 28 and open question 6 | Unknown | pick target, can see target, turn toward a point, on death | `creatures.md` slot table | table offsets 0xbc, 0xcc, 0xd4, 0xe4 are the function words of slots 23, 25, 26, 28 |
| 10 | `monsters.md` §1.2, Skill table offsets 0x44 and 0x64 | Unknown | slots 8 and 12 (with 0x0c, 0x14, 0x5c = slots 1, 2, 11) | `skills.md` slot table | offset = slot × 8 + 4 |
| 11 | `monsters.md` §2.1, +0xec | "frame from which hits register", citing 0x15153c and 0x1ba940 | caution: those two are `MissileWeapon_run` and `playerProjectile_run` and test the missile's own +0xec; only the constructor store is established for creatures | `creatures.md` (+0xec Unknown) | in both functions the tested object is the first argument, the missile; e.g. `Horsemen_ctor` store at 0x271dd8. Meaning for creatures stays Unknown (section 6) |
| 12 | `engine.md`, "Dialog lines and voice" and open question 8 | creature +0x3c4 "meaning Unknown" | the activity radius | `creatures.md` | `Creature_ctor` stores 600; `Creature_updateActive` 0x10c0f0 passes max(+0x3c4, +0x3ac, +0x3ae) to `obj_updateActive` |
| 13 | `player.md`, +0x58 (and open question) | "second level-like byte", meaning Unknown | level acknowledged in the level-up screen; feeds the attack rating | `ui.md` | set in `invmsg_dispatch` 0x1bfdb0, compared with +0x59 at 0x1d9cd4 and 0x1db870, read at 0x1b71b8 |
| 14 | `player.md`, +0xec–0xee | meaning Unknown | +0xec stat points; +0xe8 skill points | `ui.md`, `script.md` | `player_giveExp` 0x1d3150 |
| 15 | `player.md`, +0x41d0 and +0x43d0 | Unknown | quest list (8 × 0x40) and quest count | `ui.md`, `script.md` | `quest_add` 0x1d386c |
| 16 | `player.md`, +0x4c18 bits 32–36; `script.md`, +0x4c1c | "difficulty index" / "status" | a character-kind value: init stores its ninth argument, 1 when −1; only `playerSel_task`'s lobby branch passes 2 | each other, `audio-save.md` ("type value") | init 0x1b1de8–0x1b1e60; the six call sites 0x134b74, 0x1e17a4, 0x218484, 0x2248ac, 0x228618, 0x323cf4 (only 0x228618 stores 2, after a `lobby_stateIsMenu` test); readers 0x146c34, 0x1ec62c; `g_difficultyIdx` is saved separately (0x221a34, 0x2220dc) |
| 17 | `player.md`, per-machine item 3 and open question | which skills have flag bit 0: Unknown | Cyclone (41, 84) and AncestralCall (51) | `skills.md` | both constructors store a non-zero word at skill +4 (0x2d1480, 0x2e06a8); "only these" is `skills.md`'s scan, not repeated |
| 18 | `player.md`, open question on 0x1186d8 | does the copy call other objects' "touched" slot: open | no, test at 0x14d9ac | `objects.md` | 0x1186d8 calls 0x14d4b8; flag 0x20000 test at 0x14d9ac |
| 19 | `player.md` and `gameplay.md`, users of 0x404468 | 0x2eec08; 0x1a9678 | `HammerOfWrath_run` 0x2ee068; `Player_run` 0x1a5030 | `monsters.md` §2.3, `skills.md` | both old addresses are false function starts inside those functions (`ghidra_funcs.tsv` bounds); `tools/gxref.py 404468` lists seven users |
| 20 | `monsters.md` §2.3, `skills.md`, `engine.md` P15, `runtime.md` §7 and P1 | 0x404468 is "a fourth generator"; `libc_rand` is "a fourth random generator"; "the three in OVERVIEW" | each "fourth" now says what it counts: 0x404468 is the third global seed word (`player.md` and `gameplay.md` call it the third), the C library generator is a different thing, and `OVERVIEW.md` lists both | `OVERVIEW.md`, each other | seed words 0x404460, 0x404464, 0x404468; `libc_rand` 0x3b70f0 |
| 21 | `skills.md`, per-machine background | 0x44fdc0 "written by config_setDefaults 0x1e62f8 and the options screen 0x222d5c" | those are the store addresses; the functions are 0x1e6238 and `memcard_optionsScreen` 0x222b40 | `objects.md` O2 (0x1e6238) | `tools/gxref.py 44fdc0` |
| 22 | `skills.md`, "Monster" cast | 0x4f714c "the global difficulty scale" | adds: the float other documents call the monster level, `g_levelMonsterLevel` | `gameplay.md` §7, `monsters.md` §2.3 | `game_loadLevel` 0x1e5b98–0x1e5c94 sets it from the level table and the difficulty |
| 23 | `skills.md`, corrections | Cazic's function "has not been checked"; Cazic casts five skills | since read in full in `monsters.md`; the slot-2 casts are made only by the `cazicthule` variant above half hit points | `monsters.md` §4 | `Cazic_isNonAvatarAboveHalfHp` 0x24c564; the cast calls of 0x24aaf0 are in states 0xc and 0xd |
| 24 | `gameplay.md` §2.1, `$t3` | "the thorns skill" (throughout) | one note: this is helper 0x2ddccc of skills 9 and 0x52, named `Riposte` in `skills.md` | `skills.md` | the calls of 0x2ddccc at 0x1ea568 and 0x1ea5c8 load their first argument from 0x41b194, which is `g_skillTable[9]` |
| 25 | `gameplay.md` §2.4, bits 0x1 / 0x4 / 0x8 | damage class, names open | melee takes them from item definition +0x20, for which `startup.md` infers blunt, pierce, slash | `startup.md` | `Player_meleeHit` 0x1b6a98 builds the flag word from definition +0x20 (1 when unarmed) |
| 26 | `objects.md`, flags 0x400000 / 0x800000 (and open question) | meaning Unknown | menu-state bits of game message 2 | `ui.md`, `netcode.md`, `player.md` | handler 0x1d8d84–0x1d8dec; `Player_run` 0x1ac6f0–0x1ac724 |
| 27 | `ui.md`, open question "who clears 0x400000" | open | `Player_run`'s tail, when record +0x4bc8 reaches 0 | `player.md` | 0x1ac6f0–0x1ac724 (mask 0xffbfffff) |
| 28 | `ui.md`, +0x4434…+0x443c | "ranged weapon / ammunition, Inferred" | primary weapon of weapon set 0 and 1, and the second weapon when dual wielding | `player.md`, `skills.md`, `audio-save.md` | `inventory_equipItem` 0x1c27c0 and `Player_weaponSwapInput` 0x1bb718 index +0x4434 with the byte +0x4a7c (0 or 1) |
| 29 | `ui.md`, +0x50 | "skill table 0x4ef530" | same table as `g_classPassiveTables` 0x4ef510; 0x4ef530 is 0x20 into each row | `data-tables.md` | 0x1d436c; `symbols/tables.tsv` |
| 30 | `script.md`, +0x54 | "race (0 tested)" | character model index | `player.md` | `script_activePlayerIsDwarf` 0x1465a0 reads record +0x54, the model argument of init |
| 31 | `script.md`, +0xc0 / +0xc4 | i32 | float | `player.md`, `ui.md` | float load and store at 0x1424c8–0x1424d0; `player_recalcStats` |
| 32 | `script.md`, +0x4460 + k × 0x68 | "effect type of ability record k" | skill id (ability record +0x20) | `player.md`, `skills.md` | `Player_castSkill` 0x1a42b8 indexes `g_skillTable` with it |
| 33 | `script.md`, creature fields +0xd0…+0xe4, +0x3ac…+0x3c4, open question 8 | unnamed "stats" and "values" | damage low / high, attack rating, experience value, armour; point-blank range, visual range, visual arc, activity radius | `creatures.md` | `Creature_scaleStats` 0x1185d8; `Creature_ctor` 0x109d68 |

## 4. Symbol notes

Only the note column was edited; addresses and names are unchanged.

| File | Row | Note said | Note says now |
|---|---|---|---|
| `symbols/netcode.tsv` | 0x13e8f8 `scr_load` | "version 0x18, unpacks the relocation list" | name-record size 0x18 at header +0xa; expands the optional compact encoding |
| `symbols/startup.tsv` | 0x103f88 `item_getModifiedField1a` | "meaning of the field not established" | the weapon's attack rating |
| `symbols/skills.tsv` | 0x2f8f48 `PoisonRain_ctor`, 0x2f9254 `PoisonRain_run` | "table at 0x51aa60", "vtables.txt merges it into SkillLifeTap" | table at 0x51aa68; listed separately |
| `symbols/player.tsv` | 0x1b1d70 `player_initNewCharacter` | ninth argument "difficulty" | "kind", stored in bits 32–36 of record +0x4c18 (section 3, row 16) |

## 5. Corrections not confirmed

None of the reported corrections failed its check. Two were applied with narrower wording
than reported:

- **Creature kind 0x12 = "bug".** The code shows which item effects test the kind and
  which constructors store it; the word comes from the token names. `gameplay.md` and
  `creatures.md` carry it as **Inferred**.
- **The weapon helper is `WeaponShield`.** True of the table 0x50cda0, but
  `monsters.md` had attributed that table to Skelight as well. `Skelight_ctor` installs
  only `Weapon1` (0x50cf40). The text now names both.

One explanation was repeated from `docs/issues/vtable-labels.md` without an independent
check and is attributed there: *why* `tools/ps2elf.py` measures the two getters too long
(unreferenced code after them). The lengths themselves were checked.

## 6. Differences found and not settled

| # | What | Where | Why it is still open |
|---|---|---|---|
| 1 | `docs/data-tables.md` §5 says `g_difficultyIdx` "is also bits 32–36 of record +0x4c18" | `data-tables.md` (not one of the files of this pass) | Section 3, row 16 shows those bits are a character-kind value. `player.md`, `script.md` and `symbols/player.tsv` were corrected; `data-tables.md` still has the old statement and needs its owner |
| 2 | Creature +0xec | `monsters.md` §2.1 and §7.9 ("hits register from") against `creatures.md` (Unknown) | The cited evidence is about missiles (section 3, row 11). Creature-side readers exist (for example 0x245d60 in `FireBeetle_draw`, 0x249574, 0x251dd4, 0x257048) and were not read. **Unknown** |
| 3 | Creature +0x350 (status timer index 4) | `creatures.md` | Setter not traced; four callers of 0x118950 outside the damage function (0x2d7e84, 0x2d9588, 0x30a360, 0x3101a8) were not read |
| 4 | What the character-kind value 2 means in play | `player.md`, `script.md`, `audio-save.md` | Established: who writes 2 and who tests it. Not established: the intent (an online-only character is **Inferred** from the lobby test) |
| 5 | The name of the generator at 0x404468 | third (`player.md`, `gameplay.md`, `symbols/copyfix.tsv`), fourth (`monsters.md`, `skills.md`, `engine.md`), "further cosmetic one" (`OVERVIEW.md`), "second cosmetic generator" (`symbols/monsters.tsv`) | The documents now explain each count instead of being renumbered. One project-wide name would be better; that is a decision, not a fact to check |
| 6 | The name of the option 0x44fdc0 | "gore option" (`gameplay.md`, `skills.md`) against `g_decalDetail` (`engine.md`, `symbols/engine.tsv`) | Same global, two names. Only cross-referenced |
| 7 | The name of the float 0x4f714c | "difficulty scale" (`skills.md`, `symbols/skills.tsv` note on `arena_startWave`), "level scale" (`creatures.md`), "monster level" (`gameplay.md`, `monsters.md`, `symbols/tables.tsv`) | Same global; only `skills.md` was cross-referenced |
| 8 | `FINDINGS.md` D20 still calls the writer at 0x22fa34 "a mission-menu reset" | `FINDINGS.md` (not edited here) against `script.md` §7 (`dialog_free` 0x22f99c) | Reported as done; the row still has the old wording |
| 9 | `README.md` "399 are tied to their virtual tables" | `README.md` (not edited here) | Listed in `docs/issues/vtable-labels.md` §7; still to be changed by its owner |

Not attempted: a line-by-line comparison of every address in the fifteen documents. The
sweep covered the player record, the creature layout and slots, the damage function's
arguments and flag bits, AI state numbers, virtual-table counts and class names, the
random generators, and the few globals that several documents name.

## 7. Re-checking

```
python3 -I -B tools/symtab.py check                              # 0 conflicts, 0 malformed
python3 -I -B tools/vtab.py SLUS_209.73 show DummyDamager         # table 0x50ea28
python3 -I -B tools/gxref.py SLUS_209.73 404468                   # the seven users
python3 -I -B tools/gxref.py SLUS_209.73 50cda0 50cf40            # who installs which weapon table
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 1b1d70             # the six init call sites
python3 -I -B tools/dis.py SLUS_209.73 2285bc:228620              # the one call that passes 2
python3 -I -B tools/dis.py SLUS_209.73 2e72a0:2e7300              # critical-hit name by id
```

## Second pass

Scope: the corrections that later documents reported after the first pass and that were
collected for this pass — from `docs/issues/arena-desync.md`, `prediction-copy.md`, `lag.md`,
`sync-breakers.md`, `kill-loot-xp.md`, `arena-entry.md`, `float-divergence.md`, `rescan.md`,
`docs/formats/{world,model-texture,anim-audio}.md`, `docs/monsters-2.md` section 9,
`docs/issues/dynamic-tests.md` (stick figures) and the specifications
`docs/spec/{movement-camera,render-pipeline,skills-01-34,skills-35-68,skills-69-101}.md`.
Targets were the area documents, `docs/formats/`, four issue documents, `docs/FORMATS.md`,
the note column (and one name) in `symbols/*.tsv`, and the labels of `tools/localstate.py`.
`FINDINGS.md`, `names.tsv`, `patches/` and the documents still being written were not
edited; what they need is listed in section S5.

Method, as in the first pass: the smallest change that fixes the statement, in place; where
a statement was wrong the new text keeps a clause saying what the earlier version said;
where an *Unknown* or an open question has been answered, the answer and a pointer to the
document that established it stand beside the original question. Nothing was run. The last
column of the table says how each row was checked: **code** = the address given was read in
this pass (`tools/dis.py`, the decompile, `tools/ps2elf.py xref`, a data word); **report** =
taken from the reporting document without an independent reading. A row marked code with a
qualification was checked only as far as the qualification says.

### S1. Summary

| | Count |
|---|---|
| Rows in the table below | 112 |
| … corrections applied | 107 |
| … of those, re-checked against the code (wholly or for the part named) | 51 |
| … of those, taken from the reporting document | 56 |
| … already in the text before this pass | 3 (rows 16, 50, 101) |
| … follow-ups of symbol renames made before this pass | 2 (rows 92, 93) |
| Reported corrections found wrong or applied differently (section S4) | 6 |
| Reported items not applied (section S4) | 5 groups |
| Symbols renamed / symbol notes changed (section S3) | 1 / 11 (the renamed row's note included), plus the labels of one tool |

`python3 -I -B tools/symtab.py check` after the edits: 0 conflicts, 0 malformed lines.

### S2. Corrections

| # | Document, section | Said | Says now | Evidence | Checked |
|---|---|---|---|---|---|
| 1 | `player.md`, per-machine item 1 | the copy can die ahead of the real player through the kill plane (0x1a5b38–0x1a5b8c) | that route does not exist: the plane is −100000 in all 90 rows of the level table; what remains is cloned pending damage (G12, G14, G15) | level table 0x4f7210 + n × 0x30 + 8; `docs/issues/prediction-copy.md` section 8, `docs/issues/arena-desync.md` | code: the 90 words were read, all 0xc7c35000 |
| 2 | `player.md`, per-machine item 4 | "0x1ac400 does area damage (0x161270)", listed as an unguarded change | harmless for the copy: `damage_apply` returns for an attacker with flag 0x20000; the object creations on those paths remain | 0x1e828c–0x1e82a4; `prediction-copy.md` 3.2 | code (the test in `damage_apply`); that 0x161270 passes the copy as attacker is from the report |
| 3 | `player.md`, open question on state 0xd | whether the vehicle's slot 17 changes the vehicle "is not established" | answered: the slot is `Vehicle_getRiderPose` 0x2088a0, a getter | 0x1a5efc; `prediction-copy.md` 3.2 | report (call site and symbol read; the getter's body not re-read) |
| 4 | `player.md`, "Checked and found guarded against the copy" | potion use is guarded (G8) | still guarded against the copy, but the removal of the potion has a per-machine branch on the local inventory screen (K2) | 0x1b9fcc, 0x1ba3ac in `Player_usePotion`; `docs/issues/kill-loot-xp.md` K2 | report |
| 5 | `player.md`, open question on 0x1186d8 | already answered in the first pass (test at 0x14d9ac) | adds that `docs/spec/movement-camera.md` read the same test (0x14d9b0–0x14d9b8) | 0x14d9ac–0x14d9b8 | code |
| 6 | `player.md`, ability record +0x25, object +0x480 and +0x484 | kind 8 "toggle"; +0x484 "a running toggle ability"; +0x480 kinds 1–6 "special arrows" | kind 7 casts at once; kind 8 parks the record at +0x484 for the next ranged release; +0x480 values 1–6 are stored only by the older inline ability ids | 0x1a7034–0x1a709c, 0x1a74f8–0x1a7544; `docs/spec/skills-35-68.md` 4.6 | code (the two blocks); the release sites 0x1a837c / 0x1a9174 from the report |
| 7 | `creatures.md`, slot 26 | "turn toward a point (mode 1 = away)" | also returns the signed angle before the turn; move helpers halve speed and root motion above 16000 | 0x10bb9c–0x10bbb4; `docs/spec/movement-camera.md` 6.3 | code (the subtraction and sign extension); the 16000 rule from the report |
| 8 | `creatures.md`, flag 0x2000000 | "animation root motion not applied to the position" | the bit makes `Creature_stepAnim` pass no sound position to `anim_advance`; root motion is applied regardless | 0x116330–0x116348 | code |
| 9 | `creatures.md`, flag 0x1000000 and C5 | corpse "sinks and is deleted once inactive" with no condition; C5 speaks of a finished corpse | the rule needs the flag; setters listed; no arena class sets it | tail of `Creature_run` (flag and state 0x14 tested together, decompile of 0x112948); `docs/issues/arena-desync.md` | code (the test); the setter list and "no arena class" from the report |
| 10 | `creatures.md`, attached-spell list | every spell has "caster at +0x18, skill id at +0x1c" | that is `SpellTag` only; a `Spell` has its Skill at +0x08 and owner at +0x0c, the rest is per class | `creature_findSpell` 0x11a788 (class test before the two reads); skills specs | code |
| 11 | `monsters.md`, §1.2 slot 38 and §2.1 +0x24 | class block has "model at +0xc, second model at +0x14"; slot 38 returns the "second model" | +0x14 is the model's texture; slot 38 returns the texture `Creature_draw` passes to `model_draw` | `docs/formats/model-texture.md` "Corrections"; `docs/monsters-2.md` (slot-38 overrides return `.tex` resources) | report |
| 12 | `monsters.md`, §2.1 +0xe8 | "bit mask of hidden model parts", +0x220 a hide mask | +0xe8 holds model variant bits; +0x220 is a show mask (set bit draws the mesh) | 0x179550: returns the complement of model +0x08, then ORs and clears per variant record | code (decompile of 0x179550) |
| 13 | `monsters.md`, §4 Innoruuk | "takeDamage ignores all damage while the handle at +0x3e0 is set"; death makes four `HateSoul` | +0x3e0 is an integer set once from the `invulnerable` property and never cleared; death detail points to monsters-2 | 0x276a58; ctor 0x2735dc (string 0x5476f0 referenced at 0x2737a0) | code (+0x3e0); the death sequence from the report |
| 14 | `monsters.md`, §4 SpiderQueen | "States 8–9: jump (0x2afc28)" | 0x2afc28 launches a web strand (state 8); state 9 reels the victim in | `docs/monsters-2.md` 9.2 | report |
| 15 | `monsters.md`, §3.2 LavaBomb | constructor 0x281194, size `?` | no constructor function: built inline at 0x2813c8–0x28149c; 0x281194 is the state-8 case label of `LavaMonster_run`; size 0x1d8 | jump-table word at 0x548470; Ghidra bounds of 0x280b44; no call reference | code (address is a jump-table target inside 0x280b44–0x28225f); the inline range from the report |
| 16 | `monsters.md`, §3.2 LostSoul | constructor 0x293228 | already 0x2931bc since the first pass | — | already applied |
| 17 | `monsters.md`, §3.2 SpellHateEffect | 0x279420 in the TakeDamage column | Run column: slot 2 of a Spell table, the per-frame update | `tools/vtab.py show 515b70` | code |
| 18 | `monsters.md`, §5 AutoChest family | `autoobject_dropLoot` "called from AutoChest_run, AutoProp_run and 0x23d2ec" | `AutoChest_dropLoot`, one caller (`AutoChest_run`, call at 0x23b674) | `tools/ps2elf.py xref 23ba3c` | code |
| 19 | `monsters.md`, §4 Horsemen, state 0x14 | "0x14 dead" | case 0x14 also sends the summoned skeleton to state 0x14 for variant 3 and drops both held weapon parts (K8) | 0x273260–0x2732ac | code (the variant test, name lookup and slot call); the weapon drop from the report |
| 20 | `monsters.md`, §6 Goblin rows 7 and 58 | FireStorm and FrostStorm "pointer passed to an object constructor or helper" | cast through table offset 0x14 with the level from slot 35 | 0x26c4f4–0x26c53c | code |
| 21 | `monsters.md`, §1.2 slot 35 | the level handed to a skill, without exception | true for slot-2 casts; arrow constructors get `(int)g_levelMonsterLevel` unscaled | 0x25c7d8, 0x2a7274; `skills-35-68.md` 4.6 | report |
| 22 | `monsters.md`, §7.1 JumpGate | drawn flag can shift the travel menu between machines | adds: not reachable with the shipped levels — only a gate with `hurt` opens by itself and no gate on the disc has `hurt` or `destination` | ctor 0x27c848–0x27c860; `docs/issues/sync-breakers.md` §5, B7 | code (the property copy); the disc scan from the report |
| 23 | `monsters.md`, §7.6 Savepoint | interact skip matters for save points with `action`; `Savepoint_run` clears +0x84 "from `memcard_getState()`" | no Savepoint on the disc has `action`; the card-state test clears +0x84 only for state 0 | 0x28ce40–0x28ce4c; sync-breakers B7 | code (the state test); the disc scan from the report |
| 24 | `skills.md`, opening | constructors and statistics functions of "eight skill classes (ids 3, 25, 27–30, 60, 61)" at 0x16a98c–0x16ac74 | five classes (25, 27–30); ids 3, 60, 61 are built inline in the static initialiser | `skills-35-68.md` 4.6; `skills-01-34.md` section 3 | report |
| 25 | `skills.md`, Skill +0x08 | "What tests 7 and 8 was not looked for" | kind copied to the ability record; kind 7 casts at once (0x1a7048), kind 8 parks the record at player +0x484 for the ranged release | 0x1a7034–0x1a709c; `skills-35-68.md` 4.6 | code (0x1a7034–0x1a709c); `hud_onAssignSpell` and the release sites from the report |
| 26 | `skills.md`, statistics rule | tier 1 for players, tier 2 for everything else | only where slots 11–13 are used; Root, ConvertEnemy, ConvertUndead, HolyShield call slot 10; ShockOfFire's direct damage slot 8 | `skills-35-68.md` 4.6 | report |
| 27 | `skills.md`, slot 9 | base `initStats` "zeroes tier 1" | writes first level 0, value 1, step 2.0 for the five tier-1 statistics | 0x3c85b0–0x3c85f0 | code |
| 28 | `skills.md`, Spell +0x08 | "the skill that made it" for every spell | `SpellDiseaseEffect` and `SpellSecondaryUndeadShield` leave it null; the former keeps its Skill at +0x1ac | 0x2d5594, 0x2eb050 | report |
| 29 | `skills.md`, Spell slot 2 | run through Creature slot 17 "which Creature_run and Player_run call" | `Creature_run` calls it for non-players only; a player's spells run from `Player_updateCast` 0x1a3f70 (call at 0x1ac6a8) | decompile of 0x112948 (is-player test before the slot-17 call); `xref 1a3f70` | code (both); "only while hit points are above 0" from the report |
| 30 | `skills.md`, projectiles | all effects "ordinary GameObjects (slot 4 run, 5 draw, 6 touched)" | `DarknessProjectile` and `ShockProjectile` call `GameObject_ctor` directly, hit-test in run, empty slot 6 | 0x2cf4d8, 0x2c4050 | report |
| 31 | `skills.md`, record +0x4c20 | "written 1.0 / 0.75 × by GiantGrowth and Resurrect" | GiantGrowth writes max(1, 0.75 × scale); Resurrect writes 0.5; they overwrite each other | 0x312a28 (store to record +0x4c20) | code (the Resurrect store address); values from the report |
| 32 | `skills.md`, "How a cast happens", steps 1 and 3 | "+0x25 = 7 for a skill"; cost must be available; no cast point given | +0x25 is the kind byte; a kind-1 skill needs half its cost to start; the cast fires at blend weight 1.0, or 0.5 in a net game | 0x1a6f84–0x1a6f90; 0x1ab6f4–0x1ab7dc | code (the half-cost test); the blend-weight threshold from the report |
| 33 | `skills.md`, "How a cast happens", step 8 (reported against `player.md`) | cost / 60 "per frame while held" in the helper | the helper charges cost / 60 once; the per-frame charge is in `Player_run` cast phase 2 | `skills-01-34.md` section C | report. The statement is in `skills.md`, not `player.md` |
| 34 | `skills.md`, cast path | copy-castable ids "leave no trace" | `SpellCyclone_ctor` writes the shared clip header before its copy test | 0x2d1978, 0x2d197c, 0x2d19c4 (S1) | report |
| 35 | `skills.md`, "Monster" cast | cast with slot-35 level, then attach to the target | exceptions: Healing (ally as caster; Orc attaches to itself), Bubo's Disease Blade, Cazic's Frost Armor (whole monster level), arrow constructors (unscaled level) | 0x2a2998, 0x249014, 0x24bbe8, 0x25c7d8, 0x2a7274 | report |
| 36 | `skills.md`, helpers list | LifeTap helper among functions "the damage function … and the creature movement code call" | callers are the death branch of `Creature_processDamage` and, in PvP mode A, `Player_processDamage` | `xref 2f8e78`: 0x111f40, 0x1b3614 | code |
| 37 | `skills.md`, helpers list | "SpiritShield 0x315888" | the absorb roll, `SpellSpiritShield_rollAbsorb` | decompile of 0x315888 | code |
| 38 | `skills.md`, id table, ids 7 and 58 (and `monsters.md` §6) | Goblin marked * (statistics only) | Goblin casts both through slot 2 | 0x26c4f4–0x26c53c | code |
| 39 | `skills.md`, id table notes, ids 17, 21, 46, 96, 97 | no note; 21 and 46 had only class names | 17: statistics at level + 1, extra shared draw; 21: `LostSoul` is visual, effect is `damage_radial`; 46: plain `MissileWeapon`, `MultiFireProjectile` is MaleDarkElf's; 96 / 97: Cazic and Bubo cast details | 0x2edefc, 0x1046e0; 0x2f4d34; 0x2d9fc4, 0x25cab4; 0x24bbe8, 0x249014 | report |
| 40 | `skills.md`, statistics note | DiseaseBolt s0 damage "Inferred" | Observed (hit handler); the 0x26 entry is not a damage | 0x2caec8, 0x2d5854 | report |
| 41 | `skills.md`, (a) not guarded | 0x2d19d8 "posts a player notice"; GiantGrowth and Resurrect rows; no RaiseArmy row | `player_voice` call; GiantGrowth guarded in cast (0x308fc0); Resurrect reads the target's index; new row 0x313d74 | 0x2d19dc; 0x308fc0–0x308fc4; 0x313d74 (`lbu` at +0x3c8) | code (three of four); the Resurrect statement from the report |
| 42 | `skills.md`, (b) 3 | the extra write of `SpellCyclone_run` "lands on the copy only" | on non-owner machines it lands on the real player a second time (G22) | 0x2d1d1c–0x2d1d38 (two `anim_startBlendInOut` calls) | code (the two calls); which object the second gets, from the report |
| 43 | `skills.md`, (b) 7 | `isNearView(940, pos)` | 941.0 | word 0x446b4000 in the decompile of 0x2c595c | code |
| 44 | `skills.md`, (b) 8 and open question 8 | `SmokeGen_run` "not read further", Unknown | read: particle step and damage tick only when `isNearView(1000)` holds (D35) | 0x31c8c0–0x31c8c8; `docs/issues/rescan.md` R2 | code (the gate); what is behind it from the report |
| 45 | `gameplay.md`, §2.2 elemental rows | v1, v2 are "min, max" | amount = v1 + (draw rem (v2 − v1 + 1)) in integers, no guard; two skills pass v2 < v1 | 0x1e98c8–0x1e9914 | code (the divide and remainder); the two skills from the report |
| 46 | `gameplay.md`, §2.2 type 0x26 | v2 and v3 "–" | `damage_apply` reads only v1, but `item_getDamageRange` adds v1 / v2 to min / max for elemental damage and the weapon buffs write v2 = round(1.2 × v1), v3 = frames left | 0x104100; `skills-69-101.md` | report |
| 47 | `gameplay.md`, §9 open question | which structure the descriptor is embedded in | for a melee hit it is the weapon's item record itself; effect slots = the item's modifier slots | `docs/issues/kill-loot-xp.md` section 2 | report (the 0x48-byte sizes agree with `player.md`) |
| 48 | `gameplay.md`, §8 item 14 | camera-gated emitters "by text scan" only | the three reached from simulation code are checked by callee list; the other three are draw-side or uncalled | `docs/issues/rescan.md` 4.2; `symbols/gameplay.tsv` rows 0x1f5890–0x1f5e18 | report. The correction said all six; rescan lists three |
| 49 | `gameplay.md`, §5 / §10 and `symbols/gameplay.tsv` 0x204fe0 | `Camera_followCollide` "keeps the view clear with world ray casts" (the sentence is in the symbol note, not in `gameplay.md`) | raises the pitch until the players are visible; never shortens the distance | decompile of 0x204fe0: one store to +0x6a, none to +0x8c; `movement-camera.md` 7.6 | code |
| 50 | `symbols/gameplay.tsv`, 0x3278f0 helper | `net_notify3278f0` | already `lobby_sendCharacter` (in `symbols/syncbreakers.tsv`) and `game_sendCharacterToLobby` 0x1eb5c8 before this pass; no use of the old name is left | grep | already applied |
| 51 | `engine.md`, `.anm` header and `anim_advance` step 1 | event slots described as file data; "the animation file and the caller's state handler define" the bits | the four slots are zero in every clip on the disc; `creature_setDefEntryParams` 0x118378 (59 callers) and `anm_setEventSlots` 0x1183d0 fill them | `docs/formats/anim-audio.md` 2.7 | report (the two writers exist under those names in the symbol files; the disc scan was not repeated) |
| 52 | `engine.md`, "Pose" | did not say where the joint matrix is computed; "values do not depend on which buffer" | adds: built by the VU0 microprogram `g_vu0PoseProgram` (F6); cached per state, so a query may get a pose drawing built (D34) | 0x16f594, 0x16f5f4, 0x3e5c40; `float-divergence.md`, `rescan.md` R1 | report |
| 53 | `engine.md`, models, and `symbols/engine.tsv` 0x179550 | `model_buildHideMask` → "64-bit mesh hide mask" | returns a show mask (set bit draws the mesh); name unchanged | decompile of 0x179550 | code |
| 54 | `engine.md`, terrain element flags | 4 = "tested by ray casts" | 4 = the height field has flagged samples, so mask-passing callers must test it even when it lies below | `docs/formats/world.md` (0x18a5c0, 0x185a40) | report |
| 55 | `engine.md`, cutscene key 10; `symbols/engine.tsv` 0x19b694 | "screen darken ramp" | the kept value is the FIX alpha of the present pass (new image mixed with the previous one); no darkening by itself | `render-pipeline.md` 8 and 13 | report |
| 56 | `engine.md`, P3 | Critter start phase differs per machine, no condition | only for objects with a `path` property (115 `Shark`, 4 `vulture` placements); critters spawned in play skip the branch | `sync-breakers.md` section 8 | report |
| 57 | `engine.md`, P4 | consequence Unknown: "harmless only if those animations carry no events" | answered class by class: no file carries events and no listed constructor puts any on the randomised entry, **except** `AutoProp_ctor` for `pipepistona` props, which writes four event slots inline into the loop it randomises (D27, D30) | decompile of 0x23c44c (the `anim_randomizeTopTime` call, then the four {seconds, mask} stores); `sync-breakers.md` section 8; `monsters-2.md` M5 | code. The correction as reported ("they carry none", B6) is wrong for this one class — see "Not applied or changed" |
| 58 | `engine.md`, P5 | `rigidbody_init` orientation from the cosmetic seed for all three callers; effect Inferred | `PhProp_initPhysics` overwrites it (0x155310); `PushPhysicsProp` slot 8 overwrites it; the crate constructor keeps it, crates exist only from level load (D36) | 0x1551f0 (`rigidbody_init`) then 0x155310 (`quat_fromMat3`), 0x155318; `rescan.md` R4 | code (the PhProp call order); the two `PushPhysicsProp` callers from the report |
| 59 | `engine.md`, P11 | "Values do not depend on the buffer" | true of one build; whether a build happens depends on drawing (D34) | `rescan.md` R1 | report |
| 60 | `symbols/engine.tsv`, `ui_drawRect` 0x17bd30 | "(x, y, w, h, color, ...)" | (x0, y0, x1, y1, layer, color): two corners | 0x17be38–0x17be74: all four coordinates get the screen origin added | code |
| 61 | `symbols/engine.tsv`, `ui_drawSpriteImpl` 0x17b590 | fourth argument "?" | the sort layer | 0x17b888; `render-pipeline.md` 13 | report |
| 62 | `netcode.md`, receiver steps 3–5 | acknowledgement, sync record and messages read as if from every packet | read only from a packet that brings a new frame and starts no later than newest + 1; otherwise only the peer's frame, lead and the silence counter are taken | 0x13b7a4–0x13b7a8, 0x13b7f4–0x13b804; `docs/issues/lag.md` C2 | code (the two early exits); the consequence from the report |
| 63 | `netcode.md`, codec | spring written as "velocity = …, value += velocity"; "so all machines agree" | value first, then velocity from the new value; factor is 1 − √0.2; agreement needs bit-identical float arithmetic (F5) | 0x13cdb0–0x13cdd8; `lag.md` C6; `float-divergence.md` | code (the order); the rest from the reports |
| 64 | `netcode.md`, codec consequences | 0.8 threshold "after 6" frames; nothing on the settled value | 7th simulated frame by the model (dead zone first); held toward 255 settles at 0.943, toward 0 at −1.000; speed scales linearly with the stick | `lag.md` C7; `docs/issues/dynamic-tests.md` b9; `movement-camera.md` 4.1 | report |
| 65 | `netcode.md`, "Input delay is not a constant" | lead "at least 2" | 2 at the ready scan; floor 1 at the end of a call | `lag.md` 2.2, C1 | report |
| 66 | `netcode.md`, hold table, cap | measured against the lowest simulation frame | against *reported* frames; real allowance 38 minus the report lag | `lag.md` C3 | report |
| 67 | `netcode.md`, hold table, trim | "every 62nd call, if the smallest ready count … was > 2" | adds: needs all 62 calls with 3 or more ready; often cannot fire; never on a machine limited by another's input | `lag.md` C4 | report |
| 68 | `netcode.md`, "When a packet is lost" | a machine below 30 frames per second stalls the others | threshold is 60 until the display has gone to half rate (32 late pictures in a row) | 0x19e3a8, 0x19da78; `lag.md` C5; FINDINGS L5 | report |
| 69 | `netcode.md`, per-machine row 6 | 0x1e4c1c one of 17 call sites "in simulation code"; ten sites not classified | 0x1e4c1c is in `minimap_draw` (draw code); all 17 classified in `prediction-copy.md` 3.3 | `tools/ps2elf.py func 1e4c1c` → 0x1e42e0 `minimap_draw` | code |
| 70 | `issues/lag.md`, §8 | "Whether movement speed scales with that value is Unknown" | it does, linearly; and the 0.94 limit is one-sided (+0.943 / −1.000) | `movement-camera.md` 4.1 (c), (g); `docs/issues/dynamic-tests.md` b9 | report |
| 71 | `mainloop.md`, §5 step 8 | fade wait "darkens the screen (`gfx_setScreenDarken(0x40)`)" | the value is the FIX alpha of the present pass; no darkening by itself | `render-pipeline.md` 8 | report |
| 72 | `mainloop.md`, §6 net game | nothing on the slow-machine threshold | 60 pictures per second until the display has gone to half rate, then 30 (L5) | 0x19e3a8, 0x19da78; `lag.md` C5 | report |
| 73 | `mainloop.md`, §7 step 5 | camera reset skipped when "the memory-card state is 8 with flag 0x4f8f2b clear" | that condition is never true: no `memcard_setState` call passes 8 | `docs/issues/arena-entry.md` corrections, item 5 | report |
| 74 | `mainloop.md`, §7 step 6 | did not mention the test after `save_storeLevelState`; flag 0x4f8f28 unexplained | the early return after the call is dead (function returns 0 on every path); 0x4f8f28 is `g_cardXferLatch`, stuck after a save ending in the card-error state | 0x320f44–0x320f4c; decompile of 0x21777c (both returns are 0); `sync-breakers.md` 4c, B10 | code (the return value and the caller's test); the latch from the report |
| 75 | `mainloop.md`, P4 and open question | "whether the inputs can differ is Unknown" | they cannot, in one retail game | `sync-breakers.md` 6a | report |
| 76 | `mainloop.md`, P5 | readers of the HUD timer: "the boss-meter draw and one camera function" (0x207dc4) | 0x207dc4 is a call inside `Vehicle_run` 0x207c3c (driver help text) | `tools/ps2elf.py func 207dc4` → 0x207c3c | code |
| 77 | `mainloop.md`, P9 and open question | `cut_setup` runs in the first pass "on every machine"; `cut_evalCamera` accumulation Unknown | only for a cutscene started during the load; `cut_evalCamera` keeps one latch (0x44fd00) and is otherwise a function of the clock | `arena-entry.md` 3.2 | report |
| 78 | `ui.md`, inventory channel, messages 4 and 10 | listed with no remark on who sends them | 10 has no sender (0x1c55e0 is unreferenced); 4 is sent only for a second local player | `tools/ps2elf.py xref 1c55e0` (no reference); `kill-loot-xp.md` | code (message 10); message 4 from the report |
| 79 | `ui.md`, game channel, messages 7 and 11 | senders named, no condition | each has one call site, in the pause menu's level-warp list, hidden unless `g_debugCheats`; the normal pause menu has no save entry | `xref 1d9250` → 0x18dd5c; `xref 1de598` → 0x18dd70; `sync-breakers.md` section 7 | code (the single call sites); the menu facts from the report |
| 80 | `ui.md`, P1 and open question | *Unknown* whether the cosmetic seeds differ at stock generation | answered: `drawWorld` cannot reach its cosmetic-seed users during the load (pieces not drawn, scenery table empty) | 0x44f054 (0x322e2c, 0x323140); `sync-breakers.md` section 2 | report |
| 81 | `ui.md`, P4 | checksum coverage of +0xed, +0xee, +0x4a58 *Unknown*; "everything else … goes through the message tables" | `player_checksum` does not cover them; `stats_screen` and `skills_screen` call `player_recalcStats`, `stats_screen` calls `Player_recalcDamage` (K3, K4) | `xref 1b6458` → 0x1d2e7c, 0x1d5950; `sync-breakers.md` section 1; `kill-loot-xp.md` | code (the two `player_recalcStats` calls); checksum coverage and the `Player_recalcDamage` calls from the reports |
| 82 | `ui.md`, P9 | checksum exchange described as always on | only while `net_allPlayersState2()` holds (lobby game, every character of kind 2); three of the four A1 cases cannot occur then | `sync-breakers.md` section 1 | report |
| 83 | `ui.md`, open question on `script_playerAdjustStat` | "Not followed" | all 27 script calls pass slot −1 (direct path); the message path is never used by a script | 0x146348; `sync-breakers.md` section 3 | report |
| 84 | `audio-save.md`, "When saves are made" | `save_armAutosave` tests card state 8 (not remarked) | the test for 8 is never true, nor the ones at 0x322ddc and in `game_loadPlayerLumps`: no `memcard_setState` call passes 8 | 27 call sites of 0x21f238; `arena-entry.md` corrections | code (25 of the 27 sites pass a constant that is not 8; the other two from the report) |
| 85 | `audio-save.md`, sound calls and slot +0x3c; `symbols/audio-save.tsv` 0x213438 | `sound_release`: "let it play out"; +0x3c "release requested" | for a sequence handle it sets +0x3c, clears flag 4, sets flag 1; the update then skips the end test and restarts the sequence past its duration — it repeats | decompile of 0x213438 and of `soundSeq_updateAll` 0x2147c0 (the +0x3c branch) | code (re-read, as the report asked); the six callers still not traced |
| 86 | `audio-save.md`, Streams; `symbols/audio-save.tsv` `g_streams` | stream 0 "not established" (symbol note: 0 = ambience, Inferred) | ambience one-shots go to stream 2; stream 0 seen only for the intro soundtrack | `docs/formats/anim-audio.md` 3.4 | report |
| 87 | `audio-save.md`, Streams | index is a `dialog.bin` table (no remark on the name) | adds: it is the stream directory, not dialog; dialog is `.dbin` | `anim-audio.md` 3.4, 4.2 | report (`docs/FORMATS.md` already said so) |
| 88 | `audio-save.md`, A1 | how often `net_allPlayersState2` holds *Unknown*; four cases listed without condition | exchange only in a lobby-launched game with all characters of kind 2; card save, failed write and reload cannot occur while it is on; the autosave case stands | 0x146c04, 0x28da7c; `sync-breakers.md` section 1, B1, B3 | report |
| 89 | `script.md`, §2.3 "Active player" | every writer is unconditional simulation code | the `Player_interact` write depends on the object's slot 13, and the Savepoint's slot 13 reads local card state (B9) | 0x28da6c, 0x1b2b70; `sync-breakers.md` B9 | report |
| 90 | `script.md`, §2.4 | the deferred queue is cleared at teardown (nothing on the post action) | the post action is not cleared at teardown; `game_loadLevel` runs a left-over one (E10) | 0x1e60b8; `arena-entry.md` | report |
| 91 | `script.md`, §2.5 | post action run "from two places in `help_task`" | `help_task` is a draw task; the call at 0x1dcf60 is offline-only, the one at 0x1dd1f0 has no network test (E9) | 0x1dcf48–0x1dcf60 (`g_networkMode` test), 0x1dd1f0 | code |
| 92 | `script.md`, §2.2 table | `AutoPropLP_interactPrompt` 0x23d068 | `AutoProp_interactPrompt` (name already changed in `symbols/monsters.tsv`) | symbol file | rename follow-up |
| 93 | `runtime.md`, §5 | `Weapon1_slot2`, `Weapon2_slot2` | `Weapon1_setFireWeapons`, `Weapon2_setFireWeapons` (old names kept once, as history) | `symbols/runtime.tsv` | rename follow-up |
| 94 | `startup.md`, per-machine item 1 and open question 4 | *Unknown* whether `hud.lmp` can stay loaded on one peer only | no flow leaves it loaded on one peer only | `sync-breakers.md` section 6b | report |
| 95 | `objects.md`, O2 and first open question | "a local display option changes how long gib objects live"; equality across machines Unknown | the test is "below 2" and the menu stores 0 or 1, so the bit is set everywhere; only `Creature_processDamage` chunks depend on the option at all, the `Player_processDamage` chunk always has the bit | 0x1a01d0, 0x2019e0; `sync-breakers.md` B8; `arena-desync.md` | report |
| 96 | `objects.md`, open questions | bodies of `MissileWeapon`, `UserParamProp`, `CosmeticProp*`, `PushPhysicsProp`, `WaveMaker` "not read" | read in `docs/issues/rescan.md` (section 4, R3, R4); `AnimatedMissile`, `Gold`, `ItemProp` still unread | rescan.md | report |
| 97 | `engine.md`, "Tasks and frame" | nothing on when queued packets are rasterised | packets queued in frame N are rasterised at `gfx_beginFrame` of frame N+1 | `render-pipeline.md` 8, 13 | report (new fact, added) |
| 98 | `formats/world.md`, chunk flags 0x200 / 0x400 and 0x10000 | `ALPHA_1` = 1 instead of 2 (2 unexplained); 0x48 "(I: additive)" | 2 is `src × (1 − As)`, not a blend with the frame buffer; 0x48 is `dst + src × As`, confirmed | `render-pipeline.md` 6, 13 | report |
| 99 | `formats/world.md`, chunk header list | "the lights (entry 0x34)" | lights are loaded by entries 0x0e and 0x04; entry 0x34 only stores a word nothing reads | `render-pipeline.md` 4.6 | report |
| 100 | `formats/world.md`, "Still unknown" | axes relative to the screen; the world microprograms | world right-handed, z up; camera x right, y down, z forward; microprograms read in render-pipeline 4.6 (compass still open) | `render-pipeline.md` 3 | report |
| 101 | `formats/world.md`, strip rows 0 and 1 | reported as unexplained | the text already says they are placeholders of the two-row pipeline (Inferred for the world programs) | `formats/world.md` "Strip table" | already applied |
| 102 | `formats/model-texture.md`, "Where the data is" | level textures are in `<LEVEL>.TEX`, `WCACHE.DAT` | `WCACHE.DAT` is not a level texture container; its strings are referenced only from the equipment cache code | `tools/ps2elf.py strxref wcache` → 0x1a2680, 0x1a2d48 only | code |
| 103 | `formats/model-texture.md`, "Units and axes" | handedness and screen axes left open | right-handed, z up; camera x right, y down, z forward | `render-pipeline.md` 3 | report |
| 104 | `formats/model-texture.md`, entry 0x30 | "one screen-facing quad per sample point (shadow)" | draws into an off-screen surface through its own joint matrices at 0x100 (entries 0x2c / 0x2e), not to the screen | `render-pipeline.md` 4.9 | report |
| 105 | `formats/model-texture.md`, flag 0x10 and `.etex` | texture of context 2 "not traced"; who loads `.etex` Unknown | context 2 holds the level's `envtex.etex`; the main loop loads it through 0x19e440 | 0x19c77c, 0x19e440 | report |
| 106 | `formats/model-texture.md`, open questions | wrap / filter modes inherited; program 0x46 row registers unknown | pointer to render-pipeline section 6; 0x175950, which would set program 0x46 up for a model, has no caller — how the one sky dome is drawn stays Unknown | `tools/ps2elf.py xref 175950` (no reference) | code (no caller); the rest from the report |
| 107 | `issues/arena-desync.md`, "Other ways out of the world" | two ways listed | adds the third: `Horsemen_setState` case 0x14 kills the summoned skeleton for variant 3 (K8) | 0x273278, 0x2732ac | code (as for the `monsters.md` row) |
| 108 | `issues/arena-desync.md`, "Camera-driven activity" | callers of `Camera_reset`: respawn, camera-state load, spectator change, session start | also the main loop at every level change (0x322dfc); "session start" is `Camera_init`; conclusion stands for net games | 0x322dfc (`jal Camera_reset`); `arena-entry.md` | code (the call); the reasoning from the report |
| 109 | `issues/arena-desync.md`, "Not done" and both "weakest link" notes | `fx_modelStatusEffects` and the weapon helper not read | read in rescan.md section 6: presentation only (D37) | 0x11b2a8, 0x11b3e8, 0x118058, 0x1f6ac8 | report |
| 110 | `issues/prediction-copy.md`, 3.1 scripted walk | "the freeze callback skips players" | true of `creatures_freezeAll` only; with header flag 8 real players get inert bit 4 and a cloned copy inherits it; the row stands because the walk also needs action state 1 | 0x1a55ac–0x1a5604; `arena-entry.md` | report |
| 111 | `FORMATS.md`, `objects.ob` | "record layout not written down" | layout added: count, string table, per-object class name, size, angle, position, property-string offsets | `sync-breakers.md` corrections | report (not checked against the loader) |
| 112 | `tools/localstate.py`, labels and docstring | "particle seed", "audio busy"; "this under-reports" | "cosmetic seed", "disc busy (cd_isBusy)"; docstring says it also over-reports (hardware-timer false positives, D33) and points to rescan.md section 9 | `symbols/engine.tsv` 0x172be8 `cd_isBusy`; rescan.md 9 | code (the symbol); file still parses |

Three lines of `docs/monsters-2.md` outside its own rename and correction tables used
names that have since changed (`autoobject_dropLoot` twice, `SpellHateEffect_takeDamage`
once); they now give the new names. `docs/spec/skills-69-101.md` (two places) and
`docs/issues/sync-breakers.md` (section 8 and row B6, see S4 item 1) were edited for the
same kind of reason and nothing else in them was touched.

### S3. Symbol files

One rename; everything else is the note column.

| File | Row | Was | Is now |
|---|---|---|---|
| `symbols/skills.tsv` | 0x315888 | name `SpellSpiritShield_playHitEffect`, note "plays spel_is_spirithit" | name `SpellSpiritShield_rollAbsorb`; note: the absorb roll (one `g_randSeed` draw, returns 1 when the hit is absorbed), the sound is a side effect |
| `symbols/monsters.tsv` | 0x23ba3c `AutoChest_dropLoot` | "shared by AutoChest_run, AutoProp_run and AutoPropLP_vslot17" | one caller, `AutoChest_run` (call at 0x23b674) |
| `symbols/monsters.tsv` | 0x279420 `SpellHateEffect_update` | "vtable 0x515b70 slot 2" | adds: a Spell table's per-frame update, not a take-damage function |
| `symbols/monsters.tsv` | 0x281194 `LavaBomb_ctor` | "constructor; installs vtable 0x516038" | not a function entry: the state-8 case label inside `LavaMonster_run`; the bomb is built inline at 0x2813c8–0x28149c. Name kept (S5) |
| `symbols/engine.tsv` | 0x179550 `model_buildHideMask` | "-> 64-bit mesh hide mask" | returns a show mask; name kept |
| `symbols/engine.tsv` | 0x17b590 `ui_drawSpriteImpl` | "(tex, x, y, ?, color)" | fourth argument is the sort layer |
| `symbols/engine.tsv` | 0x17bd30 `ui_drawRect` | "(x, y, w, h, color, ...)" | (x0, y0, x1, y1, layer, color): two corners |
| `symbols/engine.tsv` | 0x19b694 `gfx_setScreenDarken` | "keeps the darkest request of the frame" | adds: the value is the FIX alpha of the present pass |
| `symbols/gameplay.tsv` | 0x204fe0 `Camera_followCollide` | "keeps the view clear with world ray casts" | raises the pitch; never shortens the distance |
| `symbols/audio-save.tsv` | 0x213438 `sound_release` | "lets a sequence or looping voice finish" | for a sequence handle it makes the sequence repeat; name kept (S5) |
| `symbols/audio-save.tsv` | 0x876c10 `g_streams` | "0 ambience, 1 voice, 2 music (Inferred roles)" | 0 seen only for the intro soundtrack; ambience one-shots on 2 |
| `tools/localstate.py` | label table, docstring | "particle seed", "audio busy"; "this under-reports" | "cosmetic seed", "disc busy (cd_isBusy)"; also over-reports (D33) |

The 77 `Class_vslotN` renames proposed in `docs/monsters-2.md` section 8.1 were already in
the symbol files when this pass started (their notes carry "(was …)"). Outside
`monsters-2.md` the old names survived in three places, now changed: `docs/monsters.md`
(row 18), `docs/script.md` (row 92), `docs/runtime.md` (row 93). No old name occurs in
`FINDINGS.md` or `names.tsv`.

### S4. Corrections found wrong, applied differently, or not applied

Found wrong or applied differently:

1. **`engine.md` P4, "answered: no animation file carries events" (sync-breakers B6).**
   Half right. No file carries events, but B6's second sentence — no constructor that
   randomises a start time puts events on the randomised entry — fails for one class:
   `AutoProp_ctor` 0x23c44c calls `anim_randomizeTopTime` on the prop's loop and, for a
   type starting with `pipepistona`, then writes four event slots into that same animation
   with inline stores (0.25 s, 1.0 s, 1.85 s, 2.6 s; masks 1, 2, 1, 2). The scan behind B6
   followed only callers of `creature_setDefEntryParams`. `docs/monsters-2.md` (M5),
   `docs/formats/anim-audio.md` 2.7 and FINDINGS D27 / D30 already say this. `engine.md` P4
   carries the answer with the exception (row 57); a note was added to section 8 and row
   B6 of `docs/issues/sync-breakers.md`. FINDINGS B6 needs the same amendment (S5).
2. **"`player.md`, cast step 8" (skills-01-34 section C).** The sentence about cost / 60 per
   frame is step 8 of "How a cast happens" in `skills.md`, not in `player.md`. Applied
   there (row 33).
3. **"`gameplay.md` §5, `Camera_followCollide` keeps the view clear with world ray casts"
   (movement-camera section 9).** `gameplay.md` never said it; the sentence is the note of
   `symbols/gameplay.tsv` row 0x204fe0. The note was corrected and `gameplay.md` §10 got a
   pointer (row 49).
4. **"`gameplay.md` 8.14: camera-gated emitters now checked by callee list" (rescan).**
   `rescan.md` 4.2 lists three of the six addresses of item 14 (0x1f5210, 0x1f61c0,
   0x1fc150). The text says so; of the other three, one is draw-side and two have no
   caller according to their symbol notes (row 48).
5. **"`mainloop.md` section 7 step 6: the early return is dead" (arena-entry).** The
   document did not mention that return. The fact was added, not a statement corrected
   (row 74).
6. **"`objects.md` O2" from two reporters.** arena-desync (the option matters only for
   `Creature_processDamage` chunks) and sync-breakers (the option cannot reach the bit at
   all, because the menu stores 0 or 1 and the test is "below 2") do not contradict each
   other, but the second makes the first moot for menu-set values. Both are in the row,
   in that order of weight (row 95).

Not applied:

- **Tagar's Insects, divide at 0x30cee8 (float-divergence).** No area document states the
  premise ("divides a distance by a time difference that can reach zero"); FINDINGS F3
  already says the quotient is overwritten before use.
- **`names.tsv`, `save_game` note (sync-breakers)** and **`symbols/gameplay.tsv`
  `net_notify3278f0`.** Both already read as the correction asks; `names.tsv` is not a
  file of this pass in any case.
- **`docs/monsters-2.md` section 9.1 rows that were not in the list handed to this pass**
  (`monsters.md` 7.7: 0x4f8450 holds a pointer to the camera object; Zek state 0xe;
  MummyKing state 9; VampireLord, RedDragon and Nightmare details; state 0x17 "rise" only
  for Skeleton and Skelight; `creatures.md` slot 36 = level for the Dodge skill against
  missiles) and the per-group lists of section 9.2. Not applied, not checked.
- **`docs/formats/anim-audio.md` section 5 rows not in the list**: `.anm` header +0x0c /
  +0x10 (bind offsets and depth list), the sound-event byte meanings at +0x0a…+0x0e, and
  the queue-entry parameters and status words in `audio-save.md` "Streams" (only a pointer
  was added there).
- **General caveats with no single statement to change**: sync-breakers' note that
  `tools/gxref.py` misses accesses whose `lui` is more than 64 instructions back (so "no
  writer" / "only reader" claims resting on it alone want a recheck), `lag.md` C8 (send
  cycle and game messages are tied), and rescan's note on old scan output.

Still open after this pass, noticed while editing: the notes of the 77 renamed symbols
still read "purpose not established (was …)" although `monsters-2.md` section 8.1 gives the
evidence for each name; `sound_release`'s six callers; whether a configuration file can
carry a blood option of 2 or more (O2).

### S5. For the owners of files this pass does not edit

`FINDINGS.md`:

| Row | What it needs |
|---|---|
| B6 | Amend as in S4 item 1: a few classes write event slots inline, and `AutoProp_ctor` for `pipepistona` props puts events on the loop it randomises (0x23c44c). As it stands B6 contradicts D27 and D30 in the same ledger |
| L6 | "at most 0.94" is one-sided: held toward 255 the decoded value settles at +0.943, toward 0 at −1.000 (`docs/issues/dynamic-tests.md` b9, proposed there as "L6 (add)"). That proposal ends "whether movement speed scales with the value is Unknown"; `docs/spec/movement-camera.md` 4.1 answers it: linearly |
| G8 | Optional: a pointer to K2, since "potion use is guarded against the copy" is true but the removal of the potion has a per-machine branch |
| D34, D36 | No change needed; `engine.md` P11 and P5 now point at them |

Nothing else on the ledger was found to disagree with the corrected text: D14, D20, D21,
D23, G9–G12, L4 and L5 already carry the amended wording.

`names.tsv`: no line needs changing for this pass. `save_game` (0x218128) already has the
corrected callers, and none of the renamed symbols lives there.

Decisions left to the owner of the symbol files:

- `LavaBomb_ctor` 0x281194 is not a function. The note says so; the row could be dropped
  or renamed to something that does not claim a constructor.
- `model_buildHideMask` 0x179550 returns a show mask, and the `…_getSecondModel` overrides
  of creature slot 38 return a texture. The notes and documents say so; the names were
  kept because `docs/monsters-2.md` uses them throughout.
- `sound_release` 0x213438 makes a sequence repeat. A name such as `sound_setRepeat` would
  fit the sequence branch; the voice branch (bit 0 of the voice flags) was not read, so
  the name was kept.

### S6. Re-checking

```
python3 -I -B tools/symtab.py check                               # 0 conflicts, 0 malformed
python3 -I -B tools/dis.py SLUS_209.73 13cdb0:13cde0              # spring: value first, then velocity
python3 -I -B tools/dis.py SLUS_209.73 13b79c:13b808              # receiver: the two early exits
python3 -I -B tools/dis.py SLUS_209.73 116320:116350              # flag 0x2000000 selects the sound position
python3 -I -B tools/dis.py SLUS_209.73 1a7030:1a70a4              # ability kinds 7 and 8
python3 -I -B tools/dis.py SLUS_209.73 3c85b0:3c85fc              # base initStats: 0, 1, 2.0
python3 -I -B tools/dis.py SLUS_209.73 26c4f0:26c544              # Goblin casts ids 7 and 58
python3 -I -B tools/dis.py SLUS_209.73 273254:2732b4              # knight 3 kills its skeleton
python3 -I -B tools/dis.py SLUS_209.73 1dcf40:1dcf64              # help box: offline only
python3 -I -B tools/dis.py SLUS_209.73 17be38:17be78              # ui_drawRect: four absolute coordinates
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 23ba3c             # one caller of AutoChest_dropLoot
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 1c55e0             # no sender of inventory message 10
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 1d9250             # message 7: one call site
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 2f8e78             # LifeTap helper: two callers
python3 -I -B tools/ps2elf.py SLUS_209.73 strxref wcache          # equipment cache only
grep -n "0x14) =\|0x1c) =\|0x24) =\|0x2c) =\|FUN_0016d0b8" decomp/all/0023c44c.c   # S4 item 1
```

## Third pass

Scope: the corrections reported after the second pass's hand-over list was closed — from
`docs/issues/claims-audit.md` (section 4), `docs/issues/draw-sim-leaks.md` ("Corrections to
earlier documents"), `docs/issues/pose-cache.md` (section 11), `docs/spec/items.md`
(section 13), `docs/spec/core.md` (section 14), `docs/issues/dynamic-tests.md` (section 3),
`docs/issues/stale-pointers.md` (section 10), `docs/spec/script-machine.md` (section 12) and
`docs/spec/combat.md` (section 12) — plus the two groups the second pass listed as not in
its hand-over list: `docs/monsters-2.md` sections 9.1 and 9.2, and
`docs/formats/anim-audio.md` section 5.

Method as in the two earlier passes: the smallest change that fixes the statement, in
place, keeping a clause that says what the earlier version said; an answered *Unknown* or
open question keeps the question and gets the answer and a pointer beside it. Nothing was
run in this pass. Four of the reporting documents (`docs/spec/items.md`, `core.md`,
`combat.md`, `script-machine.md`) and `docs/issues/dynamic-tests.md` /
`docs/issues/pose-cache.md` executed the original code; where a row says **executed** the
corrected statement is their executed result, which wins over an earlier reading. The last
column: **code** = the address given was read in this pass (`tools/dis.py`, the decompile,
`tools/ps2elf.py xref`); **report** = taken from the reporting document without an
independent reading; a qualification after "code" says how far the check went.

`FINDINGS.md`, `names.tsv`, `patches/`, `tools/` and the documents still being written were
not edited; what they need is in section T5. The summary (T1) is at the end of the table
it counts.

### T2. Corrections

| # | Document, section | Said | Says now | Evidence | Checked |
|---|---|---|---|---|---|
| 1 | `spec/movement-camera.md`, 4.1 (b) | the record speed multiplier (+0x4c20) "is written only by" GiantGrowth and Resurrect code | also by the arena set-up function 0x307c80 (store 0x307d04: 1.25 in a net game, 1.75 offline, for every player) and by character import and creation (1.0); "normally 1.0" holds for the campaign only | 0x307cd0–0x307d04 (constants 0x3fa00000 / 0x3fe00000 on the two sides of the `g_networkMode` test); `xref 307c80` → 0x304dd0, 0x305f20; 0x1bdb0c; `claims-audit.md` row 99 | code (the arena store, its two callers, the import store); `player_initNewCharacter` from the report |
| 2 | `issues/dynamic-tests.md`, row b5, section 3 item 2 and the proposed "G5 (reword)" row | only 0x41bfc0 named as having a writer | 0x41c138 has one too: `pad_updateRumble` subtracts one every tick and stores the result clamped at 0; neither word is ever set to a non-zero value | 0x174780–0x174790; `claims-audit.md` row 12 | code. `docs/engine.md` and `docs/mainloop.md` §11 already said so; the note of `pad_apply` is in `names.tsv` (T5) |
| 3 | `mainloop.md`, P5 | second reader of the HUD message timer is in `Vehicle_run` (second pass, row 76); "its effect on the vehicle was not followed here" | followed: the timer gates the one-time driver help text and the latch at vehicle +0x408, which nothing else reads | 0x207dac–0x207dd4; `claims-audit.md` row 72 | code (the block); "nothing else reads +0x408" from the report |
| 4 | `mainloop.md` §9 (task table, `Script`) and `script.md` §2.1 | 0x4f8694: "no reader of that word found" / "which nothing reads" | read by its own writer: `script_runByName` compares it with the display-frame counter and renews the stamp only when it has passed | 0x1ed6f0–0x1ed708; `claims-audit.md` row 73 | code |
| 5 | `skills.md`, (c) and open question 5 | ten writers listed; "the reader probably treats it as a frame count (Inferred)"; reader an open question | five more stores of 1 (`Player_processDamage` ×3, `Player_move`, `player_respawn`); the reader is `net_frameLoop`, which subtracts one per rebase while the byte is positive: a count of forced re-clones | 0x13b25c–0x13b26c; 0x1b2ef4, 0x1b352c, 0x1b3824, 0x1b5098, 0x1bd1e8; `claims-audit.md` rows 45, 79 | code (all six stores) |
| 6 | `player.md`, per-machine item 8 | whether 0x4f694a, 0x41b4fc, the recall countdown and the jump-gate state can differ: **Unknown** | 0x4f694a cannot (set by game message 8, decremented unconditionally in `hud_run`: lockstep, U5); 0x41b4fc can, inside a tick (D26, U3); the other two as before | 0x1d907c, 0x1db8ec–0x1db8f0; `draw-sim-leaks.md` U3, U5; `claims-audit.md` row 87 | code (the set and the decrement); the D26 / U3 routes from the report |
| 7 | `player.md`, aura globals and hint timers | writers not listed beyond the copy | more writers named (`player_recallTick`, `Player_updateCast`, `player_resetAuraLights`; `Player_usePotion`, `Player_weaponSwapInput`, the two axe skills); no simulation reader, statement stands | `claims-audit.md` row 86 | report |
| 8 | `creatures.md`, C2 and open question | effect of the spell slot-3 calls from `Creature_draw` **Unknown**; bodies not checked | three Spell classes override slot 3 (`SpellDrowsy`, `SpellSummonBadger`, `SpellResurrect`); all three only draw | 0x30ed24, 0x311034, 0x312f48; `draw-sim-leaks.md` U6 | report |
| 9 | `creatures.md`, C10 and open question | whether local UI code clears the menu latch 0x4fe53c: **Unknown** | not in a net game: `menu_openInventory` acquires and `inventory_close` releases only when `g_networkMode` is 0; other writers listed | 0x1c1600–0x1c1608, 0x1c52a8–0x1c52b0; `draw-sim-leaks.md` | code (both tests); the list of other writers from the report |
| 10 | `issues/sync-breakers.md`, §7 options table ("controls") and advice | button tables "installed at launch from each owner's data"; "option settings do not matter" | `config_commitOptions` rewrites all four per-slot tables from this machine's rows whenever the option list is left with a change; advice now: do not change options during an online game if anyone has remapped buttons | 0x1e6a60–0x1e6b0c; `symbols/drawsim.tsv` 0x1e6650; FINDINGS U1 | report (the loop start was looked at; the copy was not traced) |
| 11 | `mainloop.md`, run-task table, `missionmenurun` | `net_isLocalSlot` at 0x231a4c listed as a local test without remark | with `pauseMenu_isOpen` it is an early return before the pad test on the chooser's machine: a per-machine branch in a lockstep menu (U2) | 0x231a4c–0x231a78 | code |
| 12 | `netcode.md`, per-machine row 4 | "None was identified" (a handler that reads a pad) | one identified: `inventory_unequipItem` (inventory message 2) passes the message slot's own lockstep pad to `Player_weaponSwapInput`; consistent, because that pad is already applied | 0x1c2ffc (`g_pads` pointer formed); `draw-sim-leaks.md` | code (the pointer); that it is the sender's slot from the report |
| 13 | `script.md`, §2.3 "Active player" | writers: trigger volumes, interact, NPC talk, `dialog_free`, `setBestActivePlayer`, `playGotItemSound` | adds `dialog_runTask` 0x22ff48, which flips the value between 0 and 1 on an offline-only path (`playGotItemSound`'s clamp was already there as P7) | 0x2301a4–0x2301b8 (the flip and the store); `claims-audit.md` row 5; `draw-sim-leaks.md` U6 | code (the store); the offline condition from the reports |
| 14 | `issues/arena-desync.md`, "Camera-driven activity" | mode word written by `Camera_setMode` and its callers; engine camera by `camera_setView`; address-taken references in drawing code "not read to confirm they only read" | adds `Camera_updateFree` (mode word, 0x20440c) and `Camera_loadState` (position and matrix, from `save_load`); the open point is closed for position and focus, still open for four possible matrix writes | 0x20440c, 0x203a68; `claims-audit.md` rows 3, 8 | code (the two stores); the classification of the drawing-code hits from the report |
| 15 | `issues/kill-loot-xp.md`, "Is every piece the same", +0x4a74 / +0x4a78 | "no reader found outside that function" | list changed: the unreferenced HUD function 0x1de8c4 reads and writes both; the two character set-up functions store them; still no simulation reader | `claims-audit.md` row 59 | report |
| 16 | `data-tables.md`, §5 | "two constructors that swap it temporarily" | four functions: `Skelight_ctor`, `Skelight_loadState`, `CastBadger_ctor`, `CastBadger_loadState` | `claims-audit.md` row 80 | report |
| 17 | `issues/sync-breakers.md`, Background and §2 | `g_lobbyLaunch` written at 0x1e2258 / 0x1e2270; `g_worldPiecesDrawn` cleared 0x322e2c, set 0x323140 | two more stores of 0 to the first (0x1e2050, 0x1e6bd8); two more setters of the second, called only from the lobby screens. No argument changes | `claims-audit.md` rows 47, 51 | report |
| 18 | `issues/lag.md`, §7 | the peer-table sweep "also lists lighting and script functions … stale-register artefacts" | with the corrected scan the artefacts are gone: 32 functions, all netcode but two non-accesses | `claims-audit.md` rows 21, 40 | report |
| 19 | `issues/rescan.md`, R1, "What was checked" (the ten set-state functions) | debris start positions "are presentation, apart from pool occupancy" | wrong: a debris prop's start position is shared state — the settling `PhProp` constructs a `Prop`, whose constructor draws `g_randSeed` (D39); in the death cases the query comes before the track call or after an `anim_start` only | `PhProp_run` 0x155fcc, `Prop_ctorRes` 0x153c88, `Prop_ctorNamed` 0x153ac0; `pose-cache.md` sections 5, 6 | report |
| 20 | `issues/rescan.md`, R1, the `Player_run` item | "`Player_run` uses only `anim_start` / `anim_startBlendInOut`"; the cast position comes "from a possibly draw-built pose" | `Player_move` writes track weights directly after stepping; the pose the cast position reads was built by `Player_updateCast` at the end of the previous tick, on every machine, not by drawing | 0x1b498c, 0x1b499c (stores to track 1 weight and life), 0x1b4bb8–0x1b4bc4; `pose-cache.md` sections 2, 4.1 | code (the two stores at 0x1b498c / 0x1b499c); the rest from the report |
| 21 | `engine.md`, P11 | whether a build happens depends on drawing (second pass, row 59) | adds: the draw stamp is written by `anim_emitPose` only, so a simulation-built pose is short-lived on a machine that does not draw the object; pointer to the D34 answer and D40 | 0x16f8dc–0x16f8e4; `pose-cache.md` section 2 | code (the stamp store); "never by `anim_buildPose`" from the report |
| 22 | `data-tables.md`, §1.3 (parser) | "the first format that converts at least one value wins" | the first format for which `sscanf` returns non-zero; the library returns −1 when the piece ends before the first value, so empty pieces, cut words and bare words match with value 0 (**executed**) | 0x106b9c–0x106ba4 (`beqz` on the result: only 0 is "no match"); `spec/items.md` §3.1 | code (the test); the −1 behaviour of `sscanf` is the executed result of `spec/items.md` |
| 23 | `data-tables.md`, §1.3 and §10 | `requiredclass`: index or index plus one **Unknown**; who tests the `required…` codes not traced | index plus one; all are tested by `inventory_checkEquipAllowed` 0x1c4948, which also applies class rules by subtype, damage type and cloth (**executed**) | tail of the decompile of 0x1c4948 (record class compared with value − 1, reason 1); `spec/items.md` §6 | code (the class test); the rest from the report |
| 24 | `startup.md`, Item table | +0x22 "zeroed by copy; use Unknown"; modifiers at +0x24 with no end given | +0x22 is not written at creation, `inventory_giveItem` later stores the bag index there; slots end at +0x44, +0x44…+0x47 is padding; +0x06, +0x22, empty-slot values and the padding come from the parser's stack frame (**executed**) | 0x1069f8–0x106a94; `spec/items.md` §2 | report |
| 25 | `startup.md`, `item_generateWithAffixes`; `symbols/startup.tsv` 0x104ca4 | "the first try is the plain item, later tries build one candidate per eligible prefix" | try 0 parses the plain item once per fitting prefix row; later tries cover only the first N prefix rows (N = number of fitting rows), so up to 10 fitting prefixes are out of reach at caps 1–18 (**executed**) | `spec/items.md` §7.2 | report |
| 26 | `startup.md`, function table, and `symbols/startup.tsv` 0x104758 | `item_generateFromSpecialTable`: "10 random picks" | the pick is off by one: the first eligible row is twice as likely, the last is never picked (**executed**) | 0x104a3c–0x104a44; `spec/items.md` §7.1 | code (the countdown: decrement, then continue while positive); the consequence from the report. The sentence was in the symbol note, not in `startup.md` |
| 27 | `startup.md`, `loot_generateDrops` step 6 (and 4, 5) | equipment: "the caller's chance", ×2 with more than one player | also halved for everyone; fixed 0.25 in PvP mode B; the preset branch multiplies the budget by 1.7 (by 7 at 3 or less); reagent and figurine generators get half the level (**executed**) | `spec/items.md` §8 | report |
| 28 | `startup.md`, `item_getValue` | "by about 8 for the jewellery slots"; power "fixed", constants "not all transcribed" | × 8.009912 only for category 2 with slot 5, 6, 7, 14 or 15; power 1.95; an armour `armorbonus` slot falls into the code-0x1a term (**executed**) | `spec/items.md` §5 | report |
| 29 | `startup.md`, display names and open question 6 | language 4 German, 1 and 3 Romance: Inferred | supported by the tag shapes in the disc's text files; which of 1 and 3 is French and which Spanish still Unknown | `spec/items.md` §9 | report |
| 30 | `runtime.md`, §1 "Below the range", row 0x3ae688–0x3afc80 | 0x3aef58 / 0x3af4d0 / 0x3afb90 "Inferred from shape"; 0x3aef58 has "58 callers, mostly float arguments to `libc_sprintf`" | **executed**: float→double exact, multiply and double→float truncating, no denormals, no NaN / infinity handling on the way in; 58 calling functions is right but of the 97 call sites only 5 feed `libc_sprintf` (40 a comparison, 19 a multiply, 14 an add, 6 `libm_fmod`) | `spec/items.md` §11; `spec/core.md` §9 and §14 | report |
| 31 | `issues/float-divergence.md`, "The machine" | double arithmetic is integer code, "so it cannot differ between machines" | true between originals only: the routines truncate and have no denormals, so a rebuild using host doubles differs in about half of all results (**executed**) | `spec/core.md` §9, §14 | report |
| 32 | `engine.md`, Math table; `symbols/engine.tsv` 0x166630 | `math_cos16` "polynomial on the half angle" | correct; adds that neither function ever returns 0 — the quarter-turn values are ±2⁻²² (**executed**, all 65,536 angles) | `spec/core.md` §4, §14 | report |
| 33 | `objects.md`, handle recap | "An iterator is itself a node spliced into the list (object field 0)" | correct; adds the two cases where the iterator's `prev` is not a node carrying an object, and the two uses of `handle_clear` that corrupt the node pool (**executed** for the second) | `spec/core.md` §12, §14; 0x1a1698 | report |
| 34 | `objects.md`, `runObjects` step 3 | reaper described without saying how it walks | walks each cell's list from the head, with no iterator and without `g_excludeMask`: victim by link order | 0x14b9cc–0x14bb1c (no call to the iterator functions, no reference to the mask; one indirect call, the destructor); `stale-pointers.md` 5.3, ST5 | code |
| 35 | `spec/skills-35-68.md`, section 68 (Resurrect, respawn order) | the stale read is right "only because the freed block either still holds the slot number or has just been reused … reuse Inferred, not traced in `pool_new`" | traced: `player_respawn` frees the old `Player` and allocates the new one with no call between, and the free lists are last-in-first-out, so the block is always reused by the new `Player` on every machine (ST2) | 0x1bd0f0 (destructor call) … 0x1bd138 (`pool_new`), no other call in between; `stale-pointers.md` section 3 | code (the call order); the pool rule from `spec/core.md` section 11 |
| 36 | `issues/prediction-copy.md`, 3.1 (allocator row) | "Node and block *addresses* differ per machine already" | node addresses do; block addresses do not, apart from the first-copy case (the copy keeps its one block in the 3000-byte class; the two smaller classes are lockstep) | `stale-pointers.md` 5.1, ST1 | report |
| 37 | `issues/kill-loot-xp.md`, section 2 ("Nothing in steps 5–9 reads …") and the proposed kill-chain row | experience reads the player count, record hit points, level and class, and the handle | also the level-step table and the killer's skill list (**executed**, k19); all lockstep | `dynamic-tests.md` section 3 (smaller notes) | report |
| 38 | `issues/kill-loot-xp.md`, section 2, `player_giveExp` | sound and level-up text "on the owner's machine only" | only the sound is behind the local-slot test; the level-up message call is made on every machine with the slot as argument (**executed**, k22) | `dynamic-tests.md` section 3 (smaller notes) | report |
| 39 | `spec/movement-camera.md`, 4.6 | counter 7: ramp for 30 frames, "then the counter value up to 60" | after the ramp the byte is 60 for any counter value above 30, and the counter itself only at 30 or below (**executed**, z6) | 0x113774–0x1137d8 (counter under 31: the byte is the counter; otherwise the constant 0x3c) | code |
| 40 | `script.md`, 1.2 (machine +0x18) and 1.4 (entry STK) | "restored to its entry value on every exit" / "written back … on every exit path" | RETN stores the current stack pointer; RET, HALT and run-time errors store the entry value; the entry, STACK and HEAP error returns store nothing (**executed**) | word at 0x13fc24 is 0xaef60018 (the current STK register stored at machine +0x18); `spec/script-machine.md` 4.3 | code (the RETN store); the other exits from the report |
| 41 | `script.md`, 1.5 (errors 7 and 3) | "error 7 when STK passes the top" | at entry the comparison is with the header's stack-top field, which is the data start too high; error 3 at entry comes after the entry cells are written (**executed**) | 0x13ed90–0x13edac (the field is loaded through the header pointer); `spec/script-machine.md` 4.1 | code (which field is compared); the error-3 order from the report |
| 42 | `script.md`, 1.5 (address check) | indirect loads and stores check the address | the compares are signed, so negative addresses pass; the check exists in six opcodes only (**executed**) | `spec/script-machine.md` section 3 | report |
| 43 | `script.md`, 1.6 | entry index −1 means `main` | adds: index −2 is accepted (the record two places before the table is read); PRI is uninitialised on entry (**executed**) | `spec/script-machine.md` 4.1 | report |
| 44 | `script.md`, 1.7 | `scr_getAddr`: "bounds check"; a packed string is recognised "by its first cell being above 0xff" | both tests are signed: `scr_getAddr` accepts negative addresses; a packed string whose first character is 0x80 or above is read as unpacked (**executed**) | `spec/script-machine.md` section 7 | report |
| 45 | `script.md`, 1.9 opcode table | SIGN "sign-extend the low byte"; UMUL "unsigned multiply"; CASETBL data only; ALIGN "byte-order adjustment" | SIGN only sets bits 8–31 when bit 7 is set; UMUL is the same signed multiply as SMUL; CASETBL has an executable handler that crashes; ALIGN is `^= 4 − n` for n < 4 (**executed**) | 0x1405b8–0x1405cc (SIGN.pri: an OR with 0xffffff00 behind a test of bit 7, nothing on the other side); `spec/script-machine.md` section 5 | code (SIGN.pri); the other three from the report |
| 46 | `script.md`, built-in table, `activateStore` and `givePlayerItem` | argument lists as declared | some shipped scripts call them with fewer pushed arguments than declared; the run then leaves the saved stack pointer 4 too high | `spec/script-machine.md` section 9 (`HUB.scr` 0xfbc–0xfd8, `INNOVAT1.scr` 0x7e0–0x80c) | report |
| 47 | `data-tables.md`, §3.2 (`Creature_setStats`) | hit points "double arithmetic, then to float"; `pow` | `powf` (single precision) for every power; only `(r + 15.5) × power` goes through the library doubles, which truncate; `powf(L, 1.0)` is exactly `L` (**executed**) | 0x10a78c (`libm_powf`), then 0x10a79c–0x10a7d8 (int→double, add, float→double, multiply, double→float); `spec/combat.md` 1.2, 4.2 | code (the call sequence); truncation from the executed result |
| 48 | `data-tables.md`, §3.2 | damage scaling unless the type name is "droid" | also skipped when the object has no type name; the compare ignores case (**executed**) | 0x10a71c–0x10a734 (null test, then `libc_strcasecmp`) | code |
| 49 | `data-tables.md`, §3.2 | `Dead` property: hp = 0 (inside the rolled case by layout) | also when hit points were not rolled (last argument 0); maxHp keeps its value (**executed**) | 0x10a980; `spec/combat.md` 4.2 | report |
| 50 | `data-tables.md`, §3.5; `issues/kill-loot-xp.md`, step 8 | class 0: "the killer also gains mana" | with one player the mana gain needs no killer; with several it is the killer only; applied after `player_giveExp` (**executed**) | 0x112200 (class test with no killer test in the one-player branch), 0x112100 (killer compare in the loop); `spec/combat.md` section 5 | code (the two branches) |
| 51 | `data-tables.md`, §4.3 | effective statistics are base plus item modifiers 7–10 | plus figurines (bag 2, flag bit 45), added by `player_recalcArmor` between the bonus bytes and the maxima (**executed**) | `spec/combat.md` sections 7, 8 | report |
| 52 | `data-tables.md`, §4.5 and §11 | multiplier half of `Player_recalcDamage` "read from the decompile only" | executed; the thrown branch raises the maximum by the share of the new minimum; the dual-wield passive multiplies only the type-1 or type-8 factor | 0x1b7478; `spec/combat.md` section 9 | report |
| 53 | `data-tables.md`, §5, first row | monster level "3.0 in PvP mode B" | only on difficulty 1: the difficulty 2–5 lines are computed from the level byte after the PvP store and overwrite it (**executed**) | 0x1e5ba4–0x1e5c48 (the 3.0 store, then the four difficulty branches all ending in the store at 0x1e5c48) | code |
| 54 | `data-tables.md`, §8 and §11 | `player_recalcArmor` "not read here"; `item_getValue` "not fully transcribed" | both read and executed since (`spec/combat.md` section 8, `spec/items.md` §5); modifiers 5 and 6 are added by `player_recalcArmor` and overwritten by its caller | 0x1b5790; 0x1b69bc, 0x1b69c4 | report |
| 55 | `gameplay.md`, §2.5 steps 4 and 10 | base roll "in double precision" | the span is single precision; the doubles are the truncating library routines; a zero span gives 0x7f800000 (**executed**) | `spec/combat.md` 3.4 | report |
| 56 | `gameplay.md`, §2.5 step 16 | Frost Armor strikes the attacker (amount not given) | the strike is a cold slot of `trunc(dmg − factor)` — the amount minus the factor, not the absorbed part (**executed**) | 0x318364–0x318378 (subtract, then convert to integer) | code |
| 57 | `gameplay.md`, §2.5 step 18 | crit bonus is the largest of "three skill values" | the attacker's own rank counts only while a `SpellCriticalHit` is attached to it (**executed**) | 0x2e76f8–0x2e7714; `spec/combat.md` 3.2 | report |
| 58 | `gameplay.md`, §2.5 step 20, type 0x29 | "draw; success casts the skill" | the test is draw < v2 × 655, so 100 % is 65500 / 65536 (**executed**) | 0x1e8ebc–0x1e8ed8 (constant 0x28f, compare with the 16-bit draw) | code |
| 59 | `gameplay.md`, §2.5 step 27 | flag 0x800000: "possibly deliver" | delivery only on `frame & 31 == 0`; the amount is whole and at least 1; take-damage is then called again with 0 (**executed**) | 0x1ea700–0x1ea708 (the frame test); `spec/combat.md` section 3 steps 25, 26 | code (the frame test); the rest from the report |
| 60 | `gameplay.md`, §2.2 elemental rows | "min, max", with the upward range for v2 < v1 noted in the second pass | exact rule for v2 < v1 − 1 (v1 + draw mod (v1 − v2 − 1)); v2 = v1 − 1 divides by zero, console result not established (**executed** under one assumption about the remainder) | `spec/combat.md` 3.1 | report |
| 61 | `issues/dynamic-tests.md`, §1 | floating point is "the one place the interpreter approximates" | adds: the double routines are integer code, so they are executed exactly — and they truncate | `spec/combat.md` 1.2; `spec/core.md` section 9 | report |
| 62 | `issues/lag.md`, §8, last paragraph | 20 spring passes bring every row forward "by exactly one frame" | the first movement and the digital direction come one frame earlier, but the values are not the shipped row shifted by one (**executed**, b11) | `dynamic-tests.md` section 3 item 7 | report |
| 63 | `issues/sync-breakers.md`, §1 (and B2) | the first active machine also sends "player left" (message 4) | the "first active" test comes after the peer is marked dropped, so a machine that has just dropped every slot in front of its own also sends it (**executed**, s4) | 0x13dec0 (dropped byte stored), 0x13decc (`net_localIsFirstActive` called) | code |
| 64 | `creatures.md`, "The 16 status counters" | `Creature_draw` decrements the first non-zero counter unless that is index 12; counter 7 "becomes the slow amount, ramping at 2 per frame" | adds: while counter 12 is the first non-zero one, counters 13–15 are not decremented either (**executed**, i2); after the ramp the slow amount is 60 for any counter value above 30 (**executed**, z6) | `dynamic-tests.md` section 3 items 6, 11; 0x113774–0x1137d8 | code (the slow byte, as row 39); the counter loop from the report |
| 65 | `monsters.md`, §7.7 | "the structure at 0x4f8450 has 1 at +0x34" | 0x4f8450 (`g_localCamera`) holds a pointer to the camera object; the test is camera mode == 1, a per-machine value, 0 while a menu, shop, dialog camera or cutscene holds the local camera; `NPC_draw` also has a distance test | `symbols/entry.tsv` 0x4f8450; `monsters-2.md` 9.1, 9.2 | code (the symbol; the pointer is the one `claims-audit.md` row 8 followed); the rest from the report |
| 66 | `monsters.md`, §4 Zek | "state 0xe finds an enemy and links a handle" | state 0xe launches a ground wave that travels 5 units a frame, homes on that enemy and explodes for half melee damage in a 180 radius | `monsters-2.md` sections 3, 9.1 | report |
| 67 | `monsters.md`, §4 MummyKing | "state 9 creates two SpawnMummy objects" | one per player slot at one-second steps, then a shaman; the type depends on his hit points | `monsters-2.md` sections 3, 9.1 | report |
| 68 | `monsters.md`, §4 VampireLord | "States 7–0xb: melee chain with a ColdWeapons rider"; Critter objects "with four own draws" | only state 7 (and 0x18) carries the rider, on the second hit, at twice the value, and heals him 8 %; six bats per state; draws are per bat and a minimum; 0x14 deletes after the flee timer; the forced 0x19 can be lost | `monsters-2.md` 9.1, 9.2 | report |
| 69 | `monsters.md`, §4 RedDragon | breath: "helper 0x261328 twice plus arc tests"; 0xf "creates a FireStorm spell object"; 0x1b "four range tests" | the helper is effects only, the breath damage is a 15-frame tick in run; the FireStorm is constructed directly at the farthest player within 600, with no "nobody found" check; 0x1b uses cone tests and the last-attack memory | `monsters-2.md` 9.1, 9.2 | report |
| 70 | `monsters.md`, §4 Nightmare | "7 charge" | the charge does its damage in the slot-11 override 0x271484, not in run; 6 / 0x17 / 0x18 are the same four-hit kick | `monsters-2.md` 9.2 | report |
| 71 | `monsters.md`, §4 SpiderQueen | bites with a rider; spit "three own draws"; leg thresholds | adds: 7, 10 and 0xb are grab attacks that drag the target; two projectiles per event, three events; thresholds are absolute hit points (the web-strand correction was applied in the second pass, row 14) | `monsters-2.md` 9.2 | report |
| 72 | `monsters.md`, §4 Skeleton and UndeadKnight | swings "chosen … with three own draws"; "0x17 emits particles"; Skeleton state 8 "with four own draws"; 0x2bfe2c "a Wraith helper" | one draw per decision; state 8 unreachable; 0x17 emits only when +0x3cc is linked, i.e. never; three draws per rejection attempt plus one; 0x2bfe2c is the state-0x17 code inside `Wraith_run` | `monsters-2.md` 9.2 | report |
| 73 | `monsters.md`, §4 "Others", AntQueen | "bites carry a PoisonWeapons rider" | the bite (state 6) carries none; the rear attack (7) and the sting (9 / 10) do; no requester of state 0x19 found | 0x23747c; `monsters-2.md` 9.2 | report |
| 74 | `monsters.md`, §1.4, state 0x17 | "usually rise / appear" | only for Skeleton and Skelight; other uses listed | `monsters-2.md` 9.1, 9.2 | report |
| 75 | `monsters.md`, §1.2 slots 11, 17–19, 20 | 11 "Observed for Cazic only"; 17–19 Unknown; 20 "4 overrides here" | WarBoar's slot 11 is empty, Nightmare's does the charge damage; 17 next state, 18 set state, 19 set passable (AddParticle: place light, emit, empty); Skeleton overrides slot 20 too, and the two wraith overrides have a side effect | 0x2bac58 (a bare return); `symbols/monsters.tsv` rows 0x23d2ec–0x23d7ac; `monsters-2.md` 9.2 | code (the empty WarBoar body, the symbol names); the rest from the report |
| 76 | `monsters.md`, §1.3 | every run function returns when `Creature_run` is non-zero; 0x80 is "animation ended" | `NPC_run` ignores the result, and `NPC_run` / `GnomeNavigator_run` do not call `Creature_processDamage`; for Ant, Arenabeast and Amphian 0x80 is an event-marker mask placed on the death clips | `monsters-2.md` 9.2 | report |
| 77 | `monsters.md`, §2.2 and §7.8, UndeadKnight +0x3c8 | "never linked anywhere" (field search up to 0x2b5370) | a linker exists at 0x2b5370 but nothing calls it; the same for a second handle +0x3cc; conclusion stands | `tools/ps2elf.py xref 2b5370` (no reference); `monsters-2.md` 9.2 | code (no reference); that 0x2b5370 links the handle from the report |
| 78 | `monsters.md`, §3 catalogue | sizes `?` for AntWave, beetleProjectile, PoisonProjectile; Wraith creates Weapon1 | 0x3d8, 0x1d0, 0xa8; the Weapon1 is WarWraith's. A notes block under the tables lists the unreachable skills and states (Tormentor, Kobold, Mummy, Ulthork, UndeadKnight, AntQueen), the missing "Creates", the Skeleton red / blue variants, SmallSpider's states, FireFly's empty set-state, `SnowballSpell` never built | 0x237668, 0x24683c (`pool_new` arguments); 0x24787c (a bare return); `xref 26d884` (no reference); `monsters-2.md` 9.2 | code (the two sizes, the empty function, no caller of the constructor); PoisonProjectile's size and the rest from the report |
| 79 | `monsters.md`, §5 AutoChest family, CreatureContainer | `random` items "same parameter scheme as Chest"; constructor "also references AutoContainer" | worth × 300, doubled from act 1 on, zero in act 0, category table 0x4fece8; AutoContainer has its own inline loot code; CreatureContainer creates and shadows an AutoContainer | `monsters-2.md` sections 6, 9.2 | report |
| 80 | `monsters.md`, §5 Teleporter and open question 7 | where the teleport happens: **Unknown**, "probably the creature interact path or a level script" | confirmed: nothing in the class; only the base `dialogScript` paths exist | `monsters-2.md` 9.1 | report |
| 81 | `monsters.md`, §6, MaleDarkElf MultiFire (46) and Mummy DiseaseShield (5) | "value query (+0x5c)" / "value query (+0x64)" | the MultiFire query result is the number of `MultiFireProjectile` objects created, not a rider; DiseaseShield is also constructed | 0x25c984; 0x2ccfc8; `monsters-2.md` 9.2 | report |
| 82 | `monsters.md`, §7.5 AntWave | hazard described as reachable | no requester of AntQueen state 0x19 was found, so it looks unreachable | `monsters-2.md` 9.2 | report |
| 83 | `monsters.md`, §7.9 (two rows) and open question 8 | draw-time stores to position / facing: **Unknown**; AutoObject draw flag: "Unknown which flag; not read" | FireBeetle, FireFly, AntQueen undo their stores; Mosquito saves and restores; Critter unresolved. The flag is 0x100: `AutoObject_draw` only clears it, the LP draws' set is unreachable, nothing reads it | 0x297a3c–0x297a54, 0x297afc–0x297b14; `monsters-2.md` 9.2 | report |
| 84 | `monsters.md`, §10 | Root, LostSoul, LightningRod among monster projectiles not read | read in `monsters-2.md`; Root is not a monster projectile (its only creator is `Player_run`) | `monsters-2.md` 9.2 | report |
| 85 | `creatures.md`, slot 36 | "0, 4 or 10 by boss rank; purpose Unknown" | the level for the Dodge skill against missiles: `MissileWeapon_onTouch` asks a non-player creature for slot 36 and passes it to skill 2's value query; Marr and IronGuardian override it | 0x152eec–0x152f50 (indirect call at table offset 0x120, then the skill-table entry 0x41b178 = skill 2); `monsters-2.md` 2.1, 9.1 | code |
| 86 | `engine.md`, `.anm` header +0x0c / +0x10 | "use *Unknown*" | bind offsets (8 bytes per joint) and depth list (one byte per joint), read at the end of `anim_buildPose` | 0x16f58c, 0x16f590 (the two loads); `formats/anim-audio.md` 2.1, 2.2 | code (the loads); the record layouts from the report |
| 87 | `engine.md`, `.anm` sound event +0x0a…+0x0e | "volume/pitch/delay jitter amounts", Inferred | +0x0a pitch, +0x0b pitch variation, +0x0c volume, +0x0d volume variation, +0x0e delay | `formats/anim-audio.md` 2.7c (0x16d360) | report |
| 88 | `audio-save.md`, Streams | "three driver parameters" in a queue entry; status "word 3 is the position" | rate (unused by the driver), stereo flag, loop restart; status words are write position, read position, volume, bytes played | `formats/anim-audio.md` 3.4 | report |
| 89 | `symbols/engine.tsv`, `anim_start` 0x16cfe0 | "the first track of an empty state starts at full weight" | the track always starts at weight 0; for the first track of an empty state the blend time is forced to 0, i.e. a rate of 1 per tick, so it is at full weight after the next step (`docs/engine.md` already had it right) | decompile of 0x16cfe0: weight field stored 0, rate 1.0 when the state was empty; `pose-cache.md` section 11 | code |
| 90 | `symbols/player.tsv`, `handle_validatePool` and `handle_initPool`; `symbols/staleptr.tsv`, `g_handleNodes` | "6095 handle nodes" | 6,096 (**executed**: the free list after `handle_initPool` has 6,096 nodes) | 0x1a17d4–0x1a17ec: the last node is at array + 0x1dc2c = index 6095; 0x847268 + 6096 × 20 = 0x864ea8, the free-list head; `spec/core.md` section 14 | code |
| 91 | `symbols/ui.tsv`, `inventory_checkEquipAllowed` 0x1c4948 | "Inferred: class/race test" | the full requirement test, the only reader of the `required…` modifiers; returns a reason code 0–9 (**executed**) | decompile of 0x1c4948; `spec/items.md` §6 | code (the class test at the tail, as row 23); the reason codes from the report |
| 92 | `symbols/engine.tsv`, `math_buildNoiseTable` 0x1646c8 | no hazard noted | reads three stack words it never initialised (**executed**); harmless to sync — the table is per machine and all `math_noise` callers are light or draw code. The second hazard of the same report, `handle_clear` 0x1a1698, is in `objects.md` (row 33); its symbol row is in `names.tsv` (T5) | `spec/core.md` sections 7, 14 | report |

### T1. Summary

| | Count |
|---|---|
| Rows in the table above | 92 |
| … corrections applied | 92 |
| … of those, re-checked against the code (wholly or for the part named) | 40 |
| … of those, taken from the reporting document | 52 |
| … whose corrected statement is, wholly or in part, an executed result of the reporting document | 38 |
| Reported corrections found wrong | 0 |
| Reported corrections applied differently from the way they were reported (T4) | 6 |
| Reported items not applied (T4) | 7 |
| Symbols renamed / symbol notes changed (T3) | 0 / 20 |

`python3 -I -B tools/symtab.py check` after the edits: 0 conflicts, 0 malformed lines.

Where each group of rows came from: claims audit 1–5, 7 (part of 6), 13–18; draw / sim leaks
6, 8–12; pose cache 19–21, 89; items 22–29, 91 (and half of 30); core 31–33, 90, 92 (and
half of 30); patch execution 37–39, 62–64; stale pointers 34–36; script machine 40–46;
combat 47–61; `monsters-2.md` 9.1 / 9.2 65–85; `anim-audio.md` section 5 86–88.

### T3. Symbol files

No rename; all changes are in the note column.

| File | Row | Was | Is now |
|---|---|---|---|
| `symbols/engine.tsv` | 0x16cfe0 `anim_start` | "the first track of an empty state starts at full weight" | starts at weight 0 with a rate of 1 per tick (row 89) |
| `symbols/engine.tsv` | 0x1646c8 `math_buildNoiseTable` | fills the table from the cosmetic seed | adds the three uninitialised stack words (row 92) |
| `symbols/engine.tsv` | 0x166630 `math_cos16` | "half-angle polynomial" | adds: never returns 0, quarter-turn values are ±2⁻²² (row 32) |
| `symbols/player.tsv` | 0x1a14f0 `handle_validatePool`, 0x1a17d0 `handle_initPool` | "6095 handle nodes"; no count | 6096, with the arithmetic (row 90) |
| `symbols/staleptr.tsv` | 0x847268 `g_handleNodes` | "array of 6095 handle nodes" | 6096 (row 90) |
| `symbols/ui.tsv` | 0x1c4948 `inventory_checkEquipAllowed` | "Inferred: class/race test …" | the full requirement test with its reason codes (row 91) |
| `symbols/startup.tsv` | 0x104758 `item_generateFromSpecialTable` | "10 random picks" | adds the off-by-one pick (row 26) |
| `symbols/startup.tsv` | 0x104ca4 `item_generateWithAffixes` | "with every eligible prefix … tried" | the loop covers the first N prefix rows; try 0 parses the plain item once per fitting row (row 25) |
| `symbols/creatures.tsv` | 0x118c78 `Creature_slot36` | values only | adds the purpose: level for the Dodge skill against missiles (row 85) |
| `symbols/monsters.tsv` | 0x23d2ec, 0x23d680, 0x23d7ac (`AutoProp_nextState`, `_setState`, `_setPassable`) | "purpose not established" | next state / set state / set passable (row 75) |
| `symbols/monsters.tsv` | 0x240800, 0x240b64, 0x240da8 (`AddParticle_…`) | "purpose not established" | places the light and halo / emits / empty (row 75) |
| `symbols/monsters.tsv` | 0x271484 `Nightmare_onTouchList`, 0x2bac58 `WarBoar_onTouchList` | "purpose not established" | the charge damage of state 7 / an empty body (rows 70, 75) |
| `symbols/monsters.tsv` | 0x24787c `FireFly_setState`, 0x26d884 `SnowballSpell_ctor` | slot and vtable only | an empty function / no caller, the class is never instantiated (row 78) |

No document used a name that changed, because none changed. The suggested names for
addresses nobody has named (`docs/spec/core.md` section 14, 40 addresses) are new symbols,
not corrections, and were not added: this pass was given no symbol file of its own.

### T4. Applied differently, not applied, and noticed while editing

No reported correction was found to be wrong against the code. Six were applied in a
different place or form than reported:

1. **"`docs/startup.md`, `item_generateFromSpecialTable`: '10 random picks'" (items).** That
   sentence was the note of `symbols/startup.tsv` row 0x104758; `startup.md` only named the
   function in a table. Corrected in both (row 26).
2. **"symbols note on `pad_apply`" (claims audit).** The row of `pad_apply` is in
   `names.tsv`, which this pass does not edit (T5). `symbols/engine.tsv` already said, on
   `pad_updateRumble`, that it counts 0x41c138 down. Only `dynamic-tests.md` was changed
   (row 2).
3. **"`mainloop.md` P5: the timer's second reader is `Vehicle_run`" (claims audit).** Already
   applied by the second pass (its row 76). This pass replaced the remaining "its effect on
   the vehicle was not followed here" with what the audit followed (row 3).
4. **"K6: what experience reads also includes the record's class, the level-step table and
   the killer's skill list" (patch execution).** `kill-loot-xp.md` already named the class;
   the other two were added (row 37). FINDINGS K6 lacks all three (T5).
5. **"`data-tables.md` §3.2, `Dead`: also when hit points were not rolled" (combat).** The
   pseudo-code already had the `Dead` line outside the rolled block; the correction is a
   clarification of something that could be misread, not a changed statement (row 49).
6. **"`creatures.md` C10 and slot 12 note: `world_notifyObjectsNear` has one caller, when
   there is a single player — confirmed" (`monsters-2.md` 9.1).** A confirmation; the
   sentence is the note of `symbols/creatures.tsv` row 0x11a2b8, not in `creatures.md`.
   Nothing was changed.

Rows that go beyond the hand-over list but come from the same sections of the reporting
documents: 7 and 13–18 (`claims-audit.md` section 4, items 4, 6, 8, 11–14), 38 and 62–64
(`dynamic-tests.md` section 3, items 6, 7, 10 and the "smaller notes"). They are marked
"report" unless an address was read.

Not applied:

- **`tools/fieldxref.py` and `tools/flagxref.py`: the limits and fixes of
  `claims-audit.md` section 6.** `tools/` is not edited by this pass. The limits are
  documented there; the fixes are described in words and not written.
- **`tools/gxref.py` output labels (draw / sim leaks).** Same reason. The caveat stands:
  hits are labelled with the heuristic function table, and a `lui` kept across a call gives
  certain-looking hits at round addresses.
- **`tools/localstate.py` and `tools/ps2elf.py func` cut a function at its first switch
  label (`monsters-2.md` 9.1, first row).** Same reason; this is FINDINGS D32.
- **"New tools must append `tools/` to `sys.path`, not prepend" (items).** A rule for tool
  authors (`tools/dis.py` shadows the standard library's `dis` when the directory is put
  first). No document of this pass states a tool convention; it belongs in
  `CONTRIBUTING.md` or the agent brief (T5).
- **Suggested symbol names in `docs/spec/core.md` section 14.** New symbols, see T3.
- **Hag: two forms and a guard state; slot 12 overrides of Orc and Skeleton
  (`monsters-2.md` 9.2).** Additions with no statement in `monsters.md` to correct;
  `monsters-2.md` has them.
- **Every row of every reporting document that is addressed to `FINDINGS.md`.** Listed in
  T5.

Noticed while editing, not reported by anyone and not changed:

- `docs/issues/pose-cache.md` section 2 lists "`anim_stop` with no blend time" among the
  calls that change the pose at once *without* detaching it. In the decompile of 0x16d1a0
  the zero-time branch calls `anim_releaseCaches` 0x171118 first, which clears the state's
  pose pointer and the buffer's owner — it detaches. The branch *with* a blend time only
  sets a negative rate and clamps two weights, which is what `rescan.md` R1 says ("`anim_stop`
  with a blend time" changes the tracks without clearing the pointer). `anim_stop` has one
  caller. For the owner of `pose-cache.md` to confirm.
- FINDINGS D12 and D20 each carry the same executed addition twice in a row (an editing
  slip, T5).

### T5. For the owners of files this pass does not edit

`FINDINGS.md`:

| Row | What it needs |
|---|---|
| G9 | Evidence column still says the mode flags are "written only by game setup 0x1e15f8, 0x1e1888". Replace with the list of `claims-audit.md` row 15: `frontend_run` (0x1e1664, 0x1e18dc, 0x1e1938; 0x1e1670, 0x1e18e4, 0x1e1984), `net_launchUpdate` (0x1374a8–0x1374d8, from the host's mode byte), boot-argument code 0x323f34 / 0x323f38, and for mode B `arena_runTask` 0x307160 and session exit 0x3234f4. All shared or outside play |
| D20 | Writers of the active player: add `playGotItemSound` (clamps to 0…1, 0x146508, 0x146518) and, offline only, `dialog_runTask` (0x2301b8). The row also carries the "two or more players" addition twice |
| D13 | Mask writers: add the two save / set / restore brackets — `Creature_pickTarget` 0x10ded0 (stores 8 at 0x10e060, restores at 0x10e044) and `Vehicle_collideObjects` (stores 1; 0x20e410, 0x20e690) |
| D7 | "not checked against every draw-phase camera writer" can be closed for position and focus (`claims-audit.md` row 3): the position is also written by `Camera_loadState` 0x203a20 (from `save_load` only), the focus only by `camera_updateFocus`; the hits in drawing code are stack stores. Four possible matrix writes are still unclassified |
| D24 | The mode word has one more writer, `Camera_updateFree` 0x20440c (fly camera of modes 3–5, cannot run in mode 0); conclusion unchanged |
| B10 | Fourth reader of the latch: `Camera_computeTarget` 0x206778 (camera code, per machine anyway) |
| K4 | +0x4a74 / +0x4a78 are also read and written by the unreferenced HUD function 0x1de8c4 (0x1dee1c–0x1def78) and stored by the two character set-up functions |
| K6 | "experience uses only the player count, record levels, record hit points and the last-attacker handle" is short by the record's class, the level-step table and the killer's skill list (`dynamic-tests.md` k19; all lockstep) |
| D26 | Already names the medal countdown; `draw-sim-leaks.md` U3 has a third route, an automatic jump gate (0x27da8c), and says which closes do not count (message handlers, `player_respawn`, `cut_start`) |
| D12 | The executed addition about counters 13–15 appears twice in the row |
| "Tools added" paragraph | The corrected `gxref` is described as complete; `claims-audit.md` 6.1 lists seven ways it still misses or mislabels an access (a hit without `?` can carry the wrong address). `ghostreach.py`'s "563 globals written" is a lower bound |
| new rows proposed and not yet on the ledger | `spec/core.md` section 14: `sin16` / `cos16` never return 0; `math_buildNoiseTable` reads three uninitialised stack words; `handle_clear` corrupts the node pool in two cases. `spec/combat.md` section 12: `healthbonus` / `manabonus` are summed and then overwritten in `player_recalcStats`; a range with v2 = v1 − 1 in an elemental slot divides by zero inside lockstep code. `spec/script-machine.md` section 9: the unbalanced native calls of `HUB`, `HUB2`, `INNOVAT1`, `ISLGNOME` (patch SM1). `pose-cache.md` section 10: X5. (I1, R1, D39, D40, ST1–ST6, U1–U7, X8 are already there.) |

Rows checked and found already amended: G5, MV6, B2, B6, B9, D1, F4, K2, L6, SA1, SB3.

`names.tsv`:

| Row | What it needs |
|---|---|
| 0x174410 `pad_apply` | the note ends "0x41bfc0 and 0x41c138 are never written". Both are written: `pad_apply` decrements the first (0x174464) and `pad_updateRumble` counts the second down every tick (0x174790). Should read "never set to a non-zero value" |
| 0x1a1698 `handle_clear` | the note is empty. Worth saying: removes every node of a list with its partner; corrupts the node pool when an iterator stands in the list or the list holds both nodes of one link (`spec/core.md` section 12) |

`CONTRIBUTING.md` or the agent brief: a tool that imports the project's modules must
append `tools/` to `sys.path`, not put it first, because `tools/dis.py` would otherwise
shadow the standard library's `dis` (`spec/items.md`).

`tools/`: the fixes of `claims-audit.md` 6.2 and 6.3 for `fieldxref.py` and `flagxref.py`.

### T6. Re-checking

```
python3 -I -B tools/symtab.py check                               # 0 conflicts, 0 malformed
python3 -I -B tools/dis.py SLUS_209.73 307cb0:307d08              # arena set-up: 1.25 net, 1.75 offline into record +0x4c20
python3 -I -B tools/dis.py SLUS_209.73 174780:174794              # pad_updateRumble counts 0x41c138 down, clamped at 0
python3 -I -B tools/dis.py SLUS_209.73 13b250:13b270              # net_frameLoop counts the force byte down
python3 -I -B tools/dis.py SLUS_209.73 207da0:207dd8              # Vehicle_run: HUD timer gates the help text and +0x408
python3 -I -B tools/dis.py SLUS_209.73 1ed6e8:1ed70c              # script_runByName reads its own stamp
python3 -I -B tools/dis.py SLUS_209.73 1db8d8:1db8f4              # hud_run decrements the exit countdown
python3 -I -B tools/dis.py SLUS_209.73 1c15f8:1c160c              # menu_openInventory: latch only offline
python3 -I -B tools/dis.py SLUS_209.73 231a40:231a80              # mission menu: early return on the chooser's machine
python3 -I -B tools/dis.py SLUS_209.73 1b4988:1b49a0              # Player_move writes track 1 weight and life
python3 -I -B tools/dis.py SLUS_209.73 16f8dc:16f8e8              # the draw stamp, in anim_emitPose
python3 -I -B tools/dis.py SLUS_209.73 106b90:106ba8              # parser: any non-zero sscanf result is a match
python3 -I -B tools/dis.py SLUS_209.73 104a2c:104a48              # preset pick: off by one
python3 -I -B tools/dis.py SLUS_209.73 1a17d0:1a1800              # handle_initPool: last node is index 6095
python3 -I -B tools/dis.py SLUS_209.73 14b9cc:14bb1c | grep jal   # reaper: no iterator call, one indirect call
python3 -I -B tools/dis.py SLUS_209.73 1bd0e8:1bd140 | grep jal   # player_respawn: destroy, then pool_new, nothing between
python3 -I -B tools/dis.py SLUS_209.73 113774:1137dc              # slow byte after the ramp: counter or 60
python3 -I -B tools/dis.py SLUS_209.73 13ed78:13edb8              # scr_interpret entry: header stack top compared
python3 -I -B tools/dis.py SLUS_209.73 1405b8:1405d0              # SIGN.pri only sets bits
python3 -I -B tools/dis.py SLUS_209.73 10a710:10a738              # setStats: null type name and strcasecmp
python3 -I -B tools/dis.py SLUS_209.73 10a784:10a7dc | grep jal   # setStats: powf, then the soft-double sequence
python3 -I -B tools/dis.py SLUS_209.73 1e5b98:1e5c50              # monster level: PvP 3.0 overwritten on difficulty 2-5
python3 -I -B tools/dis.py SLUS_209.73 1e8eb8:1e8edc              # type 0x29: draw < v2 * 655
python3 -I -B tools/dis.py SLUS_209.73 318360:31837c              # Frost Armor strike: trunc(dmg - factor)
python3 -I -B tools/dis.py SLUS_209.73 13deb0:13ded4              # net_disconnectPlayer: drop, then "first active"
python3 -I -B tools/dis.py SLUS_209.73 152eec:152f54              # slot 36 feeds skill 2
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 307c80             # two callers of the arena set-up
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 2b5370             # no reference: UndeadKnight mount linker
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 26d884             # no reference: SnowballSpell constructor
tail -20 decomp/all/001c4948.c                                    # requiredclass compared with class + 1
sed -n 20,30p decomp/all/0016d1a0.c                               # T4: anim_stop with time 0 calls anim_releaseCaches
```

## Fourth pass

Scope: the corrections reported after the third pass — `docs/spec/net-wire.md` section 19
(W1–W12 and the open question on the two pressure fields), `docs/spec/animation.md`
section 13, `docs/issues/live-rig.md` section 5, `docs/spec/player-tick.md` section 12 and
`docs/issues/field-claims-audit.md` section 5 — and one sweep no earlier pass made: every
document that said, at its head or in its "not done" list, that nothing in the project had
been run on a game.

Method as before: the smallest change, in place, keeping a clause that says what the
earlier version said; an answered *Inferred* or open question keeps its wording and gets
the answer beside it. Nothing was run in this pass.

Three kinds of evidence now stand behind a corrected statement, and the last column of F2
says which:

- **running game** — the corrected statement is a **Ran** result of
  `docs/issues/live-rig.md`: seen in a log of the game running in the Play! emulator (commit
  83700b2c, high-level BIOS, one disc image, one machine). That is not a PlayStation 2 and
  not PCSX2. These are the first corrections of that kind; where one contradicts an older
  reading it wins, and the older *Inferred* or *Unknown* now reads **Ran** for exactly the
  part that was seen;
- **code** — the address given was read in this pass (`tools/dis.py`, the decompile, a data
  word); a qualification says how far the check went. Where the reporting document also
  executed it in `tools/ee_emu.py`, the row says **executed** and that result wins over an
  earlier reading;
- **report** — taken from the reporting document without an independent reading.

`FINDINGS.md`, `names.tsv`, `patches/`, `tools/` and the documents still being written
(`docs/issues/live-rig.md`, `docs/spec/world-queries.md`, `docs/spec/creature-tick.md`) were
not edited; what they need is in F5.

### F2. Corrections

| # | Document, section | Said | Says now | Evidence | Checked |
|---|---|---|---|---|---|
| 1 | `netcode.md`, input packet | "The first frame of an input packet is the frame the addressee last acknowledged" | the same, with the point made explicit: it is the acknowledged frame itself, not the one after, so that frame is sent again in every packet and the receiver skips it (**executed**) | `spec/net-wire.md` section 8, W1 | report (a confirmation, not a changed statement) |
| 2 | `netcode.md`, packet table, sync word | "0xbd40 followed by a 12-byte sync record, or 0xffffffff" | adds: the receiver compares with 0xbd40 only, any other word means no record; up to two padding bytes in front of the word are the sender's uninitialised stack (**executed**: 590 of 1,200 packets) | 0x13be68 (the constant 0xbd40 is the only compare); `spec/net-wire.md` 7.3, W2 | code (the compare); the padding from the report |
| 3 | `netcode.md`, "How often packets go out" | sync records: "at most one per simulation frame for the whole machine (not per peer), never repeated" | adds: with more than one remote peer each record reaches one of them; a raw relay uses up the relayer's record for that frame and carries the entry at index `g_netFrame` & 0xff of the *relayed* peer's sync ring instead (**executed**) | 0x1391dc–0x139240 (the once-per-frame test, then an entry indexed by the low byte of `g_netFrame` in a ring chosen by the peer index); `spec/net-wire.md` 12.1, W3 | code (the index and the once-per-frame test); "the relayed peer's ring" from the report |
| 4 | `netcode.md`, Sync check | "In a two-player game both sides flag each other and each ends alone. *Inferred* … not seen running" | one possible outcome, not the rule: the machine that flags first changes its active mask, the others then ignore its packets, sync records included, and may never flag back; one flag is enough to stop the session (**executed**, three interpreter instances, three runs with three outcomes). Still not seen on the live game | `spec/net-wire.md` section 11, W4; FINDINGS L7 | report |
| 5 | `netcode.md`, Drop, "Negotiation" | "When all have answered, the drop frame … becomes newest received frame + 1" | adds: a machine answers only for a peer that is not local and that it has not already dropped, so a request that arrives after the answering machine executed the drop is never answered; the requester never drops the peer and both machines stop (**executed**; 7 of 160 kicks in a model run) | 0x13c2e4 and 0x13c2f0 (two byte tests, +0x44d4 local and +0x44d5 dropped, each skipping the answer); `spec/net-wire.md` 12.3, W5 | code (the two tests); the consequence from the report |
| 6 | `netcode.md`, receiver step 3 and the paragraph after the list | "A packet that starts later is discarded"; and, added by the second pass, that such a packet's acknowledgement is not read either | its frames, sync record and messages are discarded, but its acknowledgement has been taken before the test. The second pass's sentence was right for a packet that brings no new frame and wrong for one that starts with a gap; both cases are now stated separately (**executed**) | 0x13b7c4–0x13b7f0 (the store to +0x44c0) comes before 0x13b7f4–0x13b804 (the gap test); the no-new-frame exit at 0x13b7a8 comes before both; W6 | code |
| 7 | `netcode.md`, "Limits" under the message table, and per-machine row 9 | bytes of one frame "counted in one byte on the wire"; risk "Inferred": more than 255 bytes "between two send turns" | the mis-parse is **executed** (304 bytes: count byte 0x30, the receiver walks out of the datagram). The window is per input frame, not per send turn: at two input frames per call two attaches add up on one frame; the game adds its own 4-byte "player left" message on top. Two buffer sizes added: 5008 bytes of stack for the datagram being built, with no length check, and 1984 bytes for a received one | `spec/net-wire.md` 7.5 and section 10, W7; FINDINGS L15 | report (the 0x7c0 receive size was already in the constants table) |
| 8 | `netcode.md`, Launch | packet table without size limits | a launch datagram under 16 bytes is ignored, so a DATA chunk under 4 bytes could not be delivered; the checksum loop masks with 0x8f37 when sending and 0x148f37 when receiving, the same in the low 16 bits (sender **executed**, receiver read) | `spec/net-wire.md` section 15, W8 | report |
| 9 | `issues/lag.md`, 2.4 | `engine_frameStep` is "1 while `g_displayRateModeInv` is non-zero" | abbreviated, not wrong: on that branch the code returns the signed byte at 0x44fd50 plus one, clamped to 1…2, and the byte has no writer (**executed**, 50 input combinations) | 0x19e3b0 (branch on the mode word), 0x19e3f4–0x19e3fc (the byte at 0x44fd50 is loaded there); W9 | code (that the branch reads the byte); the clamp from the report |
| 10 | `issues/lag.md`, 2.2 step 6 | "store the sample as record number lif, message count 0" | adds: the record's message-start word is a leftover stack word until bytes are attached; it is read only when the count is non-zero (**executed**) | `spec/net-wire.md`, W10 | report |
| 11 | `issues/draw-sim-leaks.md`, "The real ones", input delay | "simulated in call c + L − 1 … **Inferred**" | confirmed by execution with two interpreter instances, with L defined as `g_localInputFrame − g_netFrame` after the sample is stored and before the tick, one tick per call, plus one per call without a tick | `spec/net-wire.md` section 14, W11 | report |
| 12 | `issues/dynamic-tests.md`, row a12 | the two console-style adders agree on all 600 frames, both differ from the truncated sum on 30 | adds the refinement over 20,000 frames: the two console-style adders and round-to-nearest give the same stick bytes on all but one frame; only plain truncation of the exact sum stands apart (11.4 %). A **Model** figure, not executed | `spec/net-wire.md` 5.4, W12 | report. FINDINGS L13 already carries it |
| 13 | `netcode.md`, per-machine row 1a and the open question on pad +0x38 / +0x50 | "No exhaustive search for other readers was made"; open question | a search has been made: 0x174d80 (`pad_buttonValue`) uses the button bits in a net game and no other reader was found; that the two fields differ on every machine in every frame is **executed**. The row stays "Inferred harmless": a search is not a proof | FINDINGS L16; `spec/net-wire.md` section 14 | report |
| 14 | `engine.md`, "Root motion in a creature" | "multiplies delta and yaw by (60 − slow)/60" | the delta is; the yaw is multiplied by the integer part of that factor, which is 0 for every slow amount of 1…60 — a slowed creature gets no root yaw (**executed**) | 0x116478–0x116498: the factor is converted to an integer at 0x11648c, and that integer goes into the product stored to +0xc4 at 0x116498 (the multiply itself, at 0x116494, is an instruction `tools/dis.py` does not decode) | code |
| 15 | `engine.md`, track flag 0x0040 and `anim_advance` step 2 | "advance exactly one tick" / "one tick with flag 0x40" | the step is 0.99999994, the same constant the speed is multiplied by, not 1.0 (**executed**) | 0x16d8cc–0x16d8d0 (constant 0x3f7fffff on the flag-0x40 side) | code |
| 16 | `engine.md`, `anim_advance` step 1 | event window `time/60 ≤ s < (time+step)/60` | as computed: `time×(1/60) ≤ s < time×(1/60) + step×(1/60)`, with `step` also for paused and fixed-step tracks (**executed**) | 0x16d838–0x16d888; `spec/animation.md` sections 5, 7.3 | report |
| 17 | `engine.md`, `anim_advance` step 5 | a 0x0002 track at full weight "removes the tracks under it" | and the loop over the tracks ends there: surviving lower tracks (0x1000) are not stepped on that tick, and stay frozen while the 0x0002 track sits above them at full weight (**executed**) | 0x16e0b8 (an unconditional branch out of the loop after the purge) | code (the branch); the freeze from the report |
| 18 | `engine.md`, track table, `anim_start` and `anim_startBlendInOut` | "the first track of an empty state reaches full weight on the next tick"; `anim_startBlendInOut` "as `anim_start`" | the rule is for cell 0 in general (also a full state of capacity 1 whose only track is replaced); `anim_startBlendInOut` does not have it (**executed**) | `spec/animation.md` section 4 | report |
| 19 | `engine.md`, `anim_advance` step 6 | root-motion change "times the track's effective weight" | two weights: before the weight update for the part up to the clip's end, after it for the rest; a track removed by the update gets no second part; the yaw is not weighted (**executed**) | `spec/animation.md` section 5, notes 3 and 5 | report |
| 20 | `symbols/engine.tsv`, `anim_pushWithWeights` 0x1708c0 | "(w, dw, w2, dw2, state, anm, flags)" | the four values are f13…f16; f12 is set by callers and not read | 0x170920–0x17092c (the four stores are of f13, f14, f15, f16; no use of f12 in the function) | code |
| 21 | `symbols/engine.tsv`, `AnimState_copy` 0x16ffe8 | "0x100 bytes" | 0x108 bytes; the slot's yaw baseline (+0x18) is not copied | 0x170024–0x1700cc (a loop over 0x100 bytes, then eight more); 0x170130–0x170154 (slot words +0, +4, +8, then from +0x1c) | code |
| 22 | `symbols/engine.tsv`, `anim_start` 0x16cfe0 | the forced blend time "for the first track of an empty state" (third pass) | adds: the rule is for cell 0 in general, and `anim_startBlendInOut` does not have it | `spec/animation.md` section 4 | report |
| 23 | `symbols/creatures.tsv`, `Creature_stepAnim` 0x1162b0 | root motion "scaled by slow amount and +0xdc" | the displacement only; the yaw is multiplied by int((60 − slow)/60) = 0; steps only while bit 63 of +0xa8 is set | as row 14; 0x116320–0x116324 (the 64-bit word tested for its sign) | code |
| 24 | `formats/anim-audio.md`, 2.5; `engine.md`, "Pose" | "the VU0 microprogram that the executable carries at 0x3e5c40" | 0x3e5c40 is the DMA / VIF packet that loads it, the first instruction is at 0x3e5c50; bind offsets and depth list are those of the top track's clip | `spec/animation.md` 8.3 and section 13; `symbols/fmt-anim.tsv` 0x3e5c40 already described the packet | report |
| 25 | `formats/anim-audio.md`, 2.6 | the displacement is added "times the track's weight" | two weights, as row 19 | `spec/animation.md` section 5, note 3 | report |
| 26 | `player.md`, open questions | "Which button is the health potion and which the mana potion" | answered: potion A (mask 0x2, R2 by default) is health, potion B (mask 0x1, L2) is mana; nothing is consumed at full health. **Ran** | `issues/live-rig.md` 4c; FINDINGS V5 | running game |
| 27 | `player.md`, record +0x78 | strength, intelligence, dexterity, stamina — "order Inferred from those uses" | the order is **Ran**: a new character read 46, 37, 24, 28, the creation screen's four rows in that order, and the load limit read 171 = 46 + 125 | `issues/live-rig.md` 4b | running game |
| 28 | `netcode.md`, input record +0x04 | button bit layout "*Inferred* from the usual libpad layout" | **Ran** for eleven of the sixteen bits (L2, R2, L1, R1, select, L3, R3, four directions); the four face buttons and start were not pressed alone and stay *Inferred* | `issues/live-rig.md` 4b; FINDINGS V2 | running game |
| 29 | `mainloop.md` §7 step 3; `netcode.md` function table; `spec/net-wire.md` sections 1 and 13; `symbols/netcode.tsv` `net_debugLanLobby` | developer LAN launch "only when flag 0x402792 is set", read as a debug flag that is off in the shipped game | the byte ships set; what the retail game lacks at that point is `g_networkMode`, which the boot argument `--net` supplies. **Ran** on one machine: the lobby announces by broadcast every 64 frames and starts on the confirm button | word at 0x402790 is 0x00010000; tests at 0x322d38 (`g_networkMode`), 0x322d44 (the byte), 0x322d54 (the latch); `issues/live-rig.md` 4d; FINDINGS V6 | running game, and code (the data word and the three tests) |
| 30 | `netcode.md`, Drop, last bullet; `symbols/netcode.tsv` `net_endIfAlone` | `net_fewerThanTwoActive`, `net_endIfAlone`, `net_dropAllRemotes` "handle being the last one left"; `net_endIfAlone` "no callers" | consistent with "no callers": on a lone machine the function was never entered and patching it changed nothing; the game ended through a caller of `net_fewerThanTwoActive` (which of the four was not determined). **Ran** | `issues/live-rig.md` 4d | running game |
| 31 | `netcode.md`, codec consequences; `issues/lag.md` section 8 and the last row of section 11 | stick response "*Inferred* (model), not measured" / "the numbers are Model" | the main figures are **Ran** on one machine in a net game: four dead frames, 0.38 / 0.68 / 0.82 of full speed on the 5th to 7th samples, a ceiling of 0.9426 toward 255, five frames to die away after release, no dead frames offline. The flick, reversal and short-push rows stay Model | `issues/live-rig.md` 4c, 4d; FINDINGS V4 | running game |
| 32 | `netcode.md`, constants table and per-machine row 7; `objects.md`, flag table; `issues/prediction-copy.md`, head | re-clone "more than 30 frames"; flags 0x20000 on the copy and 0x200000 on the real local player — Observed | all three **Ran**: `g_ghostRebaseFrame` stepped by 31 eight times, the copy's flag word read 0x00024060 and the real player's 0x00204060 | `issues/live-rig.md` 4d; FINDINGS V7 | running game |
| 33 | `player.md`, "Two net-game differences"; `spec/movement-camera.md`, head | movement speed 0.861945 offline, 0.75 in a net game — Observed | **Ran**: 2.585831–2.585844 units per tick offline against 2.585835 computed, from the first tick; 2.25000 in a net game; linear in the stick value | `issues/live-rig.md` 4c, 4d; FINDINGS V3 | running game |
| 34 | `player.md`, record +0xb4 / +0xb8 / +0xbc / +0xc8 | pending potion healing and mana and their per-frame amounts — Observed | **Ran**: after a health potion +0xb4 read 22.698 and fell by +0xb8 per tick; after a mana potion +0xc8 read 30.82 and fell by +0xbc | `issues/live-rig.md` 4c | running game |
| 35 | `symbols/player.tsv`, `g_btnPotionA` 0x41ba10, `g_btnPotionB` 0x41ba20 | "Player_usePotion kind 0" / "kind 1" | kind 0 is the health potion (default R2), kind 1 the mana potion (default L2). **Ran** | `issues/live-rig.md` 4c | running game |
| 36 | `player.md`, "Two net-game differences" | "the melee hit is applied on frame 1 of the swing" | on frame 1 only when +0x55c is 0; that word is 16 after a tick in state 8 or 0xb and falls by one per melee tick in a net game, so nothing hits for 16 melee ticks after a block (**executed**) | 0x1aa6ec (the word loaded for the test), 0x1aa728–0x1aa738 (counted down while positive); `spec/player-tick.md` state 1 step 7 | code (the load and the countdown); the 16 from the report |
| 37 | `player.md`, "Order of work in `Player_run`" | a list that ends with `Player_updateCast` and the record countdowns, with no early exit | three exits skip the tail: scripted control (+0x231 non-zero), which also skips regeneration, the kill plane and damage; state 0xb while `g_recallCountdown` is non-zero; record +0x4a60 outside {0, 1} while the aura light is on (**executed**) | 0x1a55a4, 0x1a6588, 0x1ac4c0 (a test stands at each); `spec/player-tick.md` sections 1, 6, 7 | code (that the three tests exist); what each skips from the report |
| 38 | `issues/dynamic-tests.md`, row m6 | state 1: move mode 3 | the blank-player case only: a fresh swing gets mode 4 first and 3 after, as `movement-camera.md` 4.4 says | `spec/player-tick.md` section 12, item 3 | report |
| 39 | `spec/movement-camera.md`, 4.5 | the zero-pad conditions as a list | the list is in test order and the tests short-circuit, which decides the calls made on a tick; the hit-points test is last (**executed**) | `spec/player-tick.md` section 2 | report |
| 40 | `spec/skills-35-68.md`, S.2 step 3 | level-flag bit 0x10000000 as a veto of ability starts | also vetoes the block request, the block move and the weapon swap, but not the plain attack (**executed**) | 0x1a5e58, 0x1a7ff0 (the flag word tested in front of the block request); `spec/player-tick.md` section 12 | code (the two block tests); block move, swap and the plain attack from the report |
| 41 | `spec/skills-35-68.md`, S.4 step 2 | the lead point is an "**Observed** dead value" | dead for the bow only; the throw uses it (**executed**) | `spec/player-tick.md` state 0 step 2 | report |
| 42 | `spec/skills-35-68.md`, S.4 step 4; `symbols/engine.tsv` `world_collectObjectsInArc` 0x1614f0 and `particle_spawn` 0x18f3f8 | the arc query's third argument written as an integer 0; "?" in both symbol notes | a float in both: three floats (f12–f14) and four integer arguments for the arc query; f12 for `particle_spawn` (**executed** for the first) | 0x16152c (f14 saved), 0x18f420 (f12 saved) | code |
| 43 | `player.md`, record +0xb4 row | (no statement) | adds: `Player_usePotion` rewrites both per-tick rates on every call, before any test but "real player, alive" (**executed**) | `spec/player-tick.md` section 12, item 9 | report (an addition, not a correction) |
| 44 | `issues/sync-breakers.md`, §5, jump-gate row | creature +0xf0 "is read only in the counter-7 branch of `Creature_run`" | wrong: also read by `Creature_draw` and by `Player_run`, which in action state 0xc creates a `LightEffect` when +0xf0 is 30 frames old; one more consequence of D16, not a route of its own | 0x1a66ec–0x1a66f8 (+0xf0 compared with the frame counter minus 30); `field-claims-audit.md` 4.2 row 33 | code (the `Player_run` read); `Creature_draw` 0x10b76c from the report |
| 45 | `issues/prediction-copy.md`, 3.2, scavenger row | bit 63 of the creature flag word "is set only in the charm branch of `Creature_run`" | wrong: it is the "active" bit, set and cleared by `Creature_updateActive`, so players have it; the conclusion stands because the spawn also needs AI state 0x14 at +0x232, which no Player code stores | 0x10c1fc–0x10c210 (bit 63 set on one side, cleared on the other), 0x116320–0x116324 (tested by `Creature_stepAnim`); `field-claims-audit.md` 4.2 row 35 | code (set, clear and one test); the +0x232 argument from the report |
| 46 | `creatures.md`, "The 16 status counters" | "No code in this range writes any counter except through whole-object copies (clone)" | wrong as worded: `Creature_draw` 0x10b8d4 and `Creature_run` 0x113744 / 0x113758 write; what holds is that nothing in the range sets a counter to a non-zero value | `field-claims-audit.md` 4.2 row 7; the two bullets above the sentence already described both writes | report |
| 47 | `objects.md`, flag table, 0x100 | "set 0x110de8" | also set by `Player_processDamage` 0x1b336c and the three `…LP_draw` functions; `net_frameLoop` moves it to the copy; still no simulation reader | 0x1b3364–0x1b336c (flag word OR 0x100); `field-claims-audit.md` 4.2 row 17 | code (the `Player_processDamage` store); the rest from the report |
| 48 | `issues/pose-cache.md`, section 2 | direct stores into track fields: `Player_move`, `SpellRaiseArmy_raiseInRing`, `cut_advance` | adds `Player_run`, `Player_updateCast`, `Player_idleFidget`, `player_resetIdleAnim`, `AntQueen_fadeBankTracks`; the argument for the player is unaffected | `field-claims-audit.md` 4.2 row 30 | report |
| 49 | `player.md`, "What was not done" | of `ghostreach`'s reachable functions "the player-record writers" were checked | that tool does not print indexed stores; the record writers it misses among functions the copy can reach are named, with what the audit did and did not re-read | `field-claims-audit.md` 6.3 | report |

### F3. The sweep: statements that nothing was run on a game

Until the live rig, every document could say that nothing in the project had been run on
a game. That is no longer true of the project and is still true of most documents. Each
statement of that kind was reworded to say three things: what the document's own content
rests on (reading, or single functions executed in `tools/ee_emu.py`); that a live game now
exists, in the Play! emulator and not on a PlayStation 2 or in PCSX2, with its runs listed
in `FINDINGS.md`, "Run on the live game" (rows V1–V8) and `docs/issues/live-rig.md`; and
what, if anything, of that document was seen there. No document was upgraded beyond what
`live-rig.md` reports for it, and every one that proposes patches still says they are
untested — no test patch has been run on a live game.

| Documents | What of them the live game touched, as now stated at their head |
|---|---|
| `netcode.md` | eleven button bits, the stick response, the 31-tick re-clone, the two object flags, the developer-lobby packets, how a lone machine's game ends — each marked **Ran** in place; everything else reading only, two machines never joined |
| `player.md` | the record fields read back, the potion buttons, the pending-heal fields, the two run speeds |
| `mainloop.md` | `tasks_run` once per simulated frame, the two frame counters, the developer LAN launch of §7 step 3; also the note under P1–P12, none of which was exercised |
| `engine.md` | call rates of five pad and frame functions, two pad fields, the cosmetic seed following the frame counter under a cutscene |
| `objects.md` | flags 0x20000 and 0x200000; `runObjects` once per simulated frame |
| `creatures.md` | names and call counts only (`Creature_run`, `Player_clone`) |
| `ui.md` | the front-end states 0–4 (also the open question that "needs a running game": one exists, with one machine, and the comparison was not made) |
| `data-tables.md` | the load limit of a new character; no table compared |
| `netlib.md` | the eleven network modules load and start; the ten entries the netcode calls were seen called, with the library replaced at those entries; lobby client, UdpLibrary and sign-in not run |
| `audio-save.md` | the boot passes the card check and creates save data; no statement checked; no sound |
| `startup.md`, `script.md` (two places), `skills.md`, `monsters.md`, `monsters-2.md`, `gameplay.md`, `runtime.md` | nothing |
| `lobby-protocol.md` (three places) | nothing: the one net game run used the developer LAN path, which has no lobby |
| `online-setup.md` (four places) | nothing on the page; the head now names the developer LAN start (V6) as the one live result that bears on it, and says it bypasses every step described |
| `formats/world.md` (two places), `formats/model-texture.md`, `formats/anim-audio.md` | nothing: the rig has no video or sound |
| `spec/net-wire.md` (three places) | the developer-lobby packets and the local pass through the codec; no input packet was sent, there being no remote peer |
| `spec/player-tick.md` | `Player_run` entered once per frame offline and twice in a net game; the potion buttons |
| `spec/animation.md` (two places) | `Player_animStep` once per simulated frame |
| `spec/core.md` | the shared generator's step (one LCG step on 311 of 399 idle frames, none on the others) |
| `spec/movement-camera.md` (two places) | the run speed of 4.1 |
| `spec/render-pipeline.md` | nothing of its output (null video); `gfx_endFrame` once per frame |
| `spec/skills-01-34.md`, `spec/skills-35-68.md`, `spec/skills-69-101.md`, `spec/items.md`, `spec/combat.md`, `spec/script-machine.md` (two places) | nothing |
| `issues/lag.md` (three places) | the stick response of section 8; the pacing rules need two machines |
| `issues/prediction-copy.md` | two entries of `Player_run` per frame, the 31-tick re-clone, the two flags |
| `issues/kill-loot-xp.md` | offline, a potion button removes one potion and nothing at full health |
| `issues/dynamic-tests.md` | bears out check b9 and the L6 figures; its first paragraph (no full emulator available) is now history |
| `issues/float-divergence.md` | Play! is a third arithmetic implementation; its movement distances agree with the constants to seven digits, which settles none of the last-bit questions |
| `issues/vtable-labels.md` | the Player table address 0x511308 |
| `issues/draw-sim-leaks.md`, `issues/pose-cache.md` (two places), `issues/sync-breakers.md`, `issues/arena-desync.md`, `issues/arena-entry.md`, `issues/claims-audit.md`, `issues/field-claims-audit.md`, `issues/rescan.md`, `issues/stale-pointers.md` | nothing |

49 documents. Not changed: `docs/OVERVIEW.md` (already reworded); `docs/FORMATS.md` (it has
no such statement; its ".anm … not yet compared against the game on screen" is still
true, the rig having no video); the statements further down in documents whose head now
carries the pointer and which are still true as they stand (`data-tables.md` section 9,
`skills-35-68.md` 4.1 and 4.4, `skills-69-101.md` "Proposed ledger rows", `arena-entry.md`
and `sync-breakers.md` "Not done", `monsters.md` 7.x "Not confirmed on a running game").

### F1. Summary

| | Count |
|---|---|
| Rows in table F2 | 49 |
| … corrections applied | 49 |
| … from the running game (**Ran**, `live-rig.md`) | 10 (rows 26–35; row 29 was also read in the code) |
| … re-checked against the code, wholly or for the part named | 18 (rows 2, 3, 5, 6, 9, 14, 15, 17, 20, 21, 23, 36, 37, 40, 42, 44, 45, 47) |
| … taken from the reporting document | 21 |
| … whose corrected statement is, wholly or in part, an executed result of the reporting document | 25 |
| Documents whose "nothing was run" statement was reworded (F3) | 49 |
| Reported corrections found wrong | 0 |
| Reported corrections applied differently from the way they were reported (F4) | 5 |
| Reported items not applied (F4) | 8 |
| Symbols renamed / symbol notes changed | 0 / 10 |

`python3 -I -B tools/symtab.py check` after the edits: 5817 symbols, 0 conflicts, 0
malformed lines.

Where each group of rows came from: wire format 1–13; animation 14–25; live rig 26–35;
player tick 36–43; field and flag audit 44–49.

Symbol notes changed (no rename): `symbols/engine.tsv` `world_collectObjectsInArc`,
`anim_start`, `AnimState_copy`, `anim_pushWithWeights`, `particle_spawn`;
`symbols/netcode.tsv` `net_endIfAlone`, `net_debugLanLobby`; `symbols/player.tsv`
`g_btnPotionA`, `g_btnPotionB`; `symbols/creatures.tsv` `Creature_stepAnim`.

### F4. Applied differently, not applied, and noticed while editing

No reported correction was found to be wrong against the code. Five were applied in a
different place or form than reported:

1. **W6 (wire format).** Reported against receiver step 3. The sentence that actually
   contradicted it was one the second pass of this file had added below the list ("reads
   neither the acknowledgement, nor the sync record, nor the message blocks" for both the
   no-new-frame case and the gap case). Both places were changed (row 6).
2. **W1, W9, W11 (wire format).** Reported as "correct, and worth stressing", "not wrong,
   only abbreviated" and "confirmed". Applied as additions that keep the original
   sentence (rows 1, 9, 11).
3. **"`FINDINGS.md` L6: add that the movement takes five frames to die away" (live rig).**
   `issues/lag.md` section 8 already said so, as a Model figure ("Letting go, the
   character keeps moving for 5 frames"); it is now marked **Ran** there (row 31). The
   ledger row itself still lacks it (F5).
4. **"`symbols/netcode.tsv`, `net_endIfAlone` ('no callers')" (live rig).** Reported as
   consistent. The note was kept and the run added to it and to `netcode.md` (row 30).
5. **"`docs/formats/anim-audio.md` 2.5: the VU0 program is at 0x3e5c40" (animation).**
   `docs/engine.md` gave the same address in "Pose" and was changed with it;
   `symbols/fmt-anim.tsv` already described 0x3e5c40 as the loading packet and was left
   alone (row 24).

Rows that go beyond the hand-over list but come from the same sections of the reporting
documents: 19 and 25 (one statement in two documents), 23 (the symbol note that repeats
row 14), 32–35 (the "confirmed and worth marking" paragraph of `live-rig.md` section 5,
applied to the documents; the ledger is F5), 39, 43 and 49. They are marked "report" or
"running game" as the rest.

Not applied:

- **`tools/ee_emu.py`: no catch-all stub hook; stub returns are not sign-extended;
  stack-passed arguments are not recorded (player tick).** `tools/` is not edited by this
  pass.
- **`tools/ghostreach.py` under-reports record writers (field audit 6.3).** Same reason.
  The one document that leaned on its list, `player.md`, now carries the caveat (row 49).
- **Player tick, item 8: the 16-bit facing is passed sign-extended to
  `GroundPoundEffect_ctor`, `Root_ctor` and `model_getAttachPoint`; the dead state's decal
  angle is a signed 16-bit draw.** A new detail with no statement in an earlier document to
  correct; `spec/player-tick.md` has it.
- **Live rig, "the brief for this work: Play!'s network adapter is a stub".** Not a
  repository document.
- **Field audit 4.2, the rows marked "stands, list changed" whose lists live only in the
  ledger (rows 2, 3, 4, 8, 15, 20, 21, 23).** Their documents either already carry the
  longer list (rows 15 and 21: `creatures.md` C3, third pass row 15) or do not state the
  list at all. For the ledger, F5.
- **`docs/spec/world-queries.md`, lines saying nothing there was seen on a console or a
  console emulator.** Still being written by its author; for its owner (F5).
- **Every row of every reporting document that is addressed to `FINDINGS.md`.** F5.
- **Proposed names for the four functions without a caller in `spec/animation.md` section
  4** (0x170b08, 0x170e00, 0x170ee8, 0x170fc8). New symbols, not corrections; this pass has
  no symbol file of its own.

Noticed while editing, not reported by anyone:

- `issues/lag.md` section 8: the ramp logged on the live game goes on past 0.943 (0.954 on
  the eleventh sample), so it is the push toward 0, while the model's table row is the push
  toward 255. The two agree to a hundredth up to the seventh sample, which is what L6
  states; after it they are different rows. `live-rig.md` 4d does not say which direction
  its ramp table is; the document now says so as an inference from the numbers.
- `issues/draw-sim-leaks.md`: the live game showed `g_localInputFrame` = `g_netFrame` + 1 on
  one machine alone. That agrees with W11's L ≥ 2 only if the reading was taken after the
  call's tick; the rig's log does not say when. Stated as such, not as a confirmation.
- `FINDINGS.md` L7 has the executed result in its text and "Inferred from the flag's uses"
  in its kind column (F5).

### F5. For the owners of files this pass does not edit

`FINDINGS.md`:

| Row | What it needs |
|---|---|
| L6 | Add: after release the movement takes five frames to die away. The kind column reads "Observed (code), Inferred (model numbers)"; the four dead frames, the 0.8 on the seventh frame and the 0.943 / 1.000 ceilings are **Ran** now (row V4), the flick figure is still Model |
| L7 | Kind column still "Inferred from the flag's uses" although the text reports the executed sessions; should read "Executed (three interpreter instances); frequency Model". The evidence column does not name `docs/spec/net-wire.md` 11 and 12.3 |
| MV6 | The two speeds are **Ran** (row V3); the row's kind is "Observed" |
| G1 (and D13, G6 where they name the flags) | The 31-tick re-clone and the flags 0x20000 / 0x200000 are **Ran** (row V7) |
| D15 | Setters it does not list (`field-claims-audit.md` 4.2 rows 3, 4): `Player_run` 0x1abda0 (counter 11 = 41), `OniBall_onTouch` 0x294800 (counter 8) and 0x294844 (counter 10); and the zero stores 0x1a5b0c (counter 2), 0x1ac068 (counter 12), 0x113744 / 0x113758 (counter 7). "Sets" in the row means "sets to a non-zero value" |
| E11 | Says "nothing else reads the bit" and, in the next sentence, names another reader (the script helper 0x1445fc). Should read "its only other reader is the script creature-flag helper 0x1445fc, which resets the boss meter" |
| G2 | Has the five handles at +0x3d8 + 0x18·n; still lacks the object's own list heads +4 and +8, which the clone also empties (0x11e8c0, 0x11e8cc) |
| "Ruled out", the hit-flash flag 0x100 | The setter list behind it is longer: `Player_processDamage` 0x1b336c and the three `…LP_draw` functions also set it. The statement itself stands |
| "Tools added" | `fieldxref.py` and `flagxref.py` are described as before their rewrite (`field-claims-audit.md` section 2); "the player-record writers in that set have been read" should carry the caveat of 6.3 there: `ghostreach.py` does not print indexed stores, and whether each copy test guards each of those stores was not re-read |
| new rows proposed and not found on the ledger | `spec/net-wire.md` section 19, last proposed row: two padding bytes of about four in ten input packets and the tail of every 0x200-byte launch packet are uninitialised stack (the pressure bytes are L16, the builder's missing length check is L15). `spec/player-tick.md` section 12: three exits of `Player_run` skip `Player_updateCast` and the record countdowns (0x1a55a4, 0x1a6588, 0x1ac4c0); `Player_usePotion` rewrites both delivery rates on every call |

Rows checked and found already amended: L13, L15, L16, D14, D16, K3, K6, R6, AN1–AN5, V1–V8.

`names.tsv`:

| Row | What it needs |
|---|---|
| 0x13dd88 `net_fewerThanTwoActive` | the note is empty. Worth saying: four callers (0x1db904, 0x1dbe9c in `hud_netStatusDraw`, 0x1e3e10, 0x1e74c4); **Ran**: a lone machine's net game ends through one of them about 100 frames after the level starts, not through `net_endIfAlone` (`docs/issues/live-rig.md` 4d) |
| 0x1b9cb8 `Player_usePotion` | add: kind 0 is the health potion (default R2), kind 1 mana (default L2) — **Ran**; rewrites record +0xb8 and +0xbc on every call for a living real player (executed, `docs/spec/player-tick.md`) |
| 0x10c0f0 `Creature_updateActive` | add: sets (0x10c204) and clears (0x10c210) bit 63 of the creature flag word at +0xa8, the "active" bit that `Creature_stepAnim` and the scavenger spawn test |
| 0x1a5030 `Player_run` | optional: three exits skip the tail (0x1a55a4, 0x1a6588, 0x1ac4c0); reads creature +0xf0 at 0x1a66f0 (state 0xc) |
| 0x132e90 `net_main` | "calls net_frameLoop" is thin; **Ran**: entered once per rendered frame in a net game and never offline |

`docs/spec/world-queries.md` (its author): the head and the "not done" list say nothing was
seen on a console or a console emulator; when the document is finished it should point to
`FINDINGS.md` "Run on the live game" like the others, and say that none of it was checked
there.

`tools/`: the three `ee_emu.py` gaps of `spec/player-tick.md`; indexed stores in
`ghostreach.py` (`field-claims-audit.md` 6.3).

### F6. Re-checking

```
python3 -I -B tools/symtab.py check                               # 0 conflicts, 0 malformed
python3 -I -B tools/dis.py SLUS_209.73 13be5c:13be78              # receiver: sync word compared with 0xbd40 only
python3 -I -B tools/dis.py SLUS_209.73 1391bc:139260              # builder: once per frame; entry indexed by g_netFrame & 0xff
python3 -I -B tools/dis.py SLUS_209.73 13c2d8:13c300              # kick request: no answer for a local or dropped peer
python3 -I -B tools/dis.py SLUS_209.73 13b7a0:13b808              # receiver: acknowledgement stored before the gap test
python3 -I -B tools/dis.py SLUS_209.73 19e3a8:19e400              # engine_frameStep: the byte 0x44fd50 on the mode branch
python3 -I -B tools/dis.py SLUS_209.73 116470:1164a0              # stepAnim: factor converted to an integer before the yaw
python3 -I -B tools/dis.py SLUS_209.73 116318:116330              # stepAnim: bit 63 of +0xa8
python3 -I -B tools/dis.py SLUS_209.73 16d8c0:16d8d4              # flag 0x40: step 0x3f7fffff
python3 -I -B tools/dis.py SLUS_209.73 16e0a8:16e0c4              # purge: branch out of the track loop
python3 -I -B tools/dis.py SLUS_209.73 1708f4:170938 | grep swc1  # pushWithWeights stores f13..f16
python3 -I -B tools/dis.py SLUS_209.73 170020:1700d0              # AnimState_copy: 0x100 in the loop, 8 after it
python3 -I -B tools/dis.py SLUS_209.73 170118:170158              # slot copy skips +0x18
python3 -I -B tools/dis.py SLUS_209.73 322d30:322d64              # developer LAN launch: three tests
python3 -I -B -c "import sys; sys.path.insert(0,'tools'); from ps2elf import Elf; e=Elf('SLUS_209.73'); print('%08x' % e.u32(0x402790))"   # 00010000: byte 0x402792 is 1
python3 -I -B tools/dis.py SLUS_209.73 1aa6ec:1aa740              # melee hit frame: +0x55c tested and counted down
python3 -I -B tools/dis.py SLUS_209.73 1a5598:1a55b0              # scripted-control exit
python3 -I -B tools/dis.py SLUS_209.73 1a6578:1a6590              # state 0xb and the recall countdown
python3 -I -B tools/dis.py SLUS_209.73 1ac4b0:1ac4c8              # tail: early return on record +0x4a60
python3 -I -B tools/dis.py SLUS_209.73 1a5e44:1a5e68              # block request: level flag 0x10000000
python3 -I -B tools/dis.py SLUS_209.73 1614f0:161600 | grep f14   # arc query reads a third float
python3 -I -B tools/dis.py SLUS_209.73 18f3f8:18f470 | grep f12   # particle_spawn reads f12
python3 -I -B tools/dis.py SLUS_209.73 1a66e0:1a6700              # Player_run reads +0xf0
python3 -I -B tools/dis.py SLUS_209.73 10c1fc:10c214              # Creature_updateActive: bit 63 set / cleared
python3 -I -B tools/dis.py SLUS_209.73 1b3364:1b3370              # Player_processDamage sets flag 0x100
```

## Fifth pass

Scope: the corrections reported after the fourth pass by three reference models —
`docs/spec/world-queries.md` section 12, `docs/spec/creature-tick.md` section 16 (thirteen
items; also the null read of its section 4.3) and `docs/spec/object-system.md` section
10.1 — and what `docs/issues/live-rig.md` section 7 (phase 2: two linked instances of the
running game) changes in five older documents: `docs/issues/kill-loot-xp.md`,
`docs/issues/draw-sim-leaks.md`, `docs/issues/arena-desync.md`,
`docs/issues/arena-entry.md` and `docs/online-setup.md`.

Method as before: the smallest change, in place, keeping a clause that says what the
earlier version said; an answered *Inferred*, *Unknown* or "not read" keeps its wording
and gets the answer and a pointer beside it. Nothing was run in this pass.

The last column of Q2 says which kind of evidence stands behind the corrected statement:

- **running game** — a **Ran** result of `docs/issues/live-rig.md` section 7: two
  instances of the game in the Play! emulator, joined through the developer LAN start and
  compared tick by tick. They are two copies of one emulator build on one host — not a
  PlayStation 2 and not PCSX2 — so a divergence seen there is a difference in the game's
  logic, and the absence of one says nothing about machines that compute differently.
  These are the first corrections that rest on two machines; where one contradicts an
  older reading it wins;
- **code** — the address given was read in this pass (`tools/dis.py`, `tools/vtab.py`,
  `tools/ps2elf.py xref` / `ptrs`); a qualification says how far the check went. Where the
  reporting document also ran the original instructions in `tools/ee_emu.py`, the row says
  **executed**, and that result wins over an earlier reading;
- **report** — taken from the reporting document without an independent reading.

`FINDINGS.md`, `names.tsv`, `patches/`, `tools/`, the top-level documents of other
contributors and the documents still being written (`docs/issues/live-rig.md`,
`docs/spec/arena-monsters.md`, `docs/spec/script-builtins.md`) were not edited; what they
need is in Q5. The three reporting documents were not edited either.

### Q2. Corrections

| # | Document, section | Said | Says now | Evidence | Checked |
|---|---|---|---|---|---|
| 1 | `engine.md`, Pathfinding | `path_search` is "a breadth-first wave … stopping when a cell passes the request's goal test or after 80 rounds" | not breadth-first: continuing straight costs 2 rounds and any other move 3; a round is finished after a hit and the **last** hit of the round is taken; five empty rounds also end the search; a node that finds its ring full is marked and lost (**executed**) | `spec/world-queries.md` 10.5; FINDINGS R10 | report |
| 2 | `engine.md`, Pathfinding, cell word; `formats/world.md`, path grid bits 8–15 | "bits 8–15 = search mark (direction it was reached from)" | the direction plus one; the start node carries 15 (**executed**) | 0x184bec (the start node's word gets 0xf00); `spec/world-queries.md` 10.1 | code (the start mark); "plus one" from the report |
| 3 | `engine.md`, cell word; `formats/world.md`, path grid bits 16–31 | "upper 16 bits non-zero = blocked"; "non-zero blocks the node at run time" | the effect, not the coding: a counter, 0–16, that 0x18b6c0 raises and 0x18b584 lowers over a rectangle of nodes, for torches and fires; a node with a non-zero counter is never entered | callers from `ps2elf.py xref`: 0x2b200c (`Torch_ctor`), 0x2c58e4 (`StaticFire_initCommon`), 0x2c57cc (`StaticFire_dtor`); `spec/world-queries.md` 10.1 | code (the three call sites); the range and the rectangle from the report |
| 4 | `engine.md`, goal tests; `symbols/engine.tsv` `path_goalTestClearLine` 0x1844f0 | type 1: "within the radius and `world_raycast` to the goal is clear" | within the radius and the ray returns **more than 0.98**; a ray that hits nothing returns −1.0, so a completely clear line fails the test (**executed**) | 0x18452c (the radius test), 0x184594–0x1845a8 (0.98 compared below the ray's result) | code |
| 5 | the same; `path_goalTestRanged` 0x1845bc | type 2: "within the radius, at least 120 away when the radius is larger than that, and `terrain_raycast` clear (ranged attackers)" | every node **outside** the radius passes; inside it, unless the radius is above 120 and the node nearer than 120, a node passes when the ray returns less than 0.98, hitting nothing included. Requested by `Creature_requestPath` mode 1, which `spec/movement-camera.md` 6.3 describes as fleeing (**executed**) | 0x1845f8–0x184600 (outside the radius: result 1), 0x184604–0x184620 (the pair of tests against 14400), 0x18467c–0x184690 | code (the three tests); the requester from the report |
| 6 | the same; `path_goalTest3` 0x1846a4 | type 3: "not read"; "(body not read)" | as type 2 with `world_raycast` (requester ignored) and the limit 0.75 (**executed**) | 0x1846e0–0x184704, 0x18476c–0x184780 (the call, then a compare with 0x3f400000) | code |
| 7 | `engine.md`, World table; `symbols/engine.tsv` `terrain_testFlag1` 0x183b48 | "… -> 1" | the result is the float 1.0 or 0.0 in `$f0`, which its callers compare with a float (**executed**) | 0x183db4 and 0x183e10 (the two values moved into `$f0`), 0x14aeec (a caller's float compare) | code |
| 8 | `engine.md`, World table; `symbols/engine.tsv` `terrain_raycast` 0x18a5c0 | "first terrain hit along a ray, marching 240 units at a time" | elements are collected per 240-unit segment and each is marched one 4-unit sample at a time; the first segment with a hit decides; a vertical ray returns a distance; the height carried from one segment to the next is advanced four times too far; each flag bit in the mask adds 65536 to a sample's height (**executed**) | 0x18a5c4 (0.25), 0x18a738 (240.0), 0x18a714 (the 1001-step bound); `spec/world-queries.md` 9.1 | code (the three constants); the march and the height error from the report |
| 9 | `formats/world.md`, "How the engine uses the samples", Ray | "marches 240 units at a time against the same samples" | as row 8; flags do not block the ray, they raise the sample (**executed**) | `spec/world-queries.md` 9.1 | report |
| 10 | `engine.md`, World table; `symbols/engine.tsv` `world_movePiece` 0x182c98 | one of three functions that "change the terrain element of a moving piece"; "moves a piece and its terrain element" | it stores only into the piece's chunk record (+0x28, +0x2c, +0x30, +0x36, +0x38); the terrain element of a piece never moves or turns — only its flag 2 and its height offset change, through the other two functions. Observed, **not executed** | 0x182ea0–0x182ed8 (every store of the function that is not to the stack) | code |
| 11 | `engine.md`, open question 6 and the address-range table | "Path request type 3 goal test (0x1846a4) and the two routines at 0x185448 and 0x1857e4"; "two unread routines" | answered: the goal test is row 6; 0x1857e4 is a straight-line walk probe and 0x185448 walks the path grid calling `terrain_height` and a particle routine; neither has a caller or a stored pointer, so neither runs | `ps2elf.py xref` and `ptrs` return nothing for both addresses; `spec/world-queries.md` section 12 | code (no caller, no pointer); what the two bodies do from the report |
| 12 | `formats/world.md`, Path grid | "a position is snapped to the nearest node" | only the start of a search is; the goal is used as a point with a radius (**executed**) | `spec/world-queries.md` 10.3, 10.4; FINDINGS R10 | report |
| 13 | `formats/world.md`, terrain element +0x10, flag 4 | with the flag "the 'everything here is lower' shortcut must not be taken" | adds: that is all the bit does — in the sweep always, in the ray only when the ray was given a flag mask (**executed**) | `spec/world-queries.md` sections 6, 9.1, 12 | report (a refinement) |
| 14 | `spec/movement-camera.md`, section 5 | 5.2 and 5.10 marked *(dec)*; "The exact loop bounds of the back-off were read from the decompile only" | at the head of the section: 5.2, 5.3, 5.4, the ground and gravity lines of 5.5, 5.8 and the terrain part of 5.10 are **executed**, with no error found. Four additions in place: a zero-length sweep over a blocking sample returns −0x7fffffff and the slide then asks for a step of about 10^35 units (5.3); an unrotated element's cosine is 0x3f7fffff, not 1.0 (5.3); `normalOut` receives an uninitialised stack slot when no sweep was blocked (5.4, Observed); the back-off makes at most 20 tries (5.10) | `spec/world-queries.md` sections 4.1, 7, 8.3, 12; FINDINGS R8, R9 | report |
| 15 | `spec/movement-camera.md`, section 10, "Not reached" | `Creature_run` beyond the slow amount, the avoidance offset's side selection, `creature_findClearHeading`, the wander helpers, the two ray casts, `world_findFreeSpot` and the path search, all listed as not reached | each bullet says where it was reached since: `spec/creature-tick.md` sections 4, 10, 11; `spec/world-queries.md` sections 9, 10; `spec/object-system.md` 4.8 | the three reporting documents | report (pointers, not corrections) |
| 16 | `monsters.md`, 1.3 step 3 | "`Creature_run(this, model)`; a non-zero result ends the function" | the caller's test is there, but the exit is dead: `Creature_run` has one return and it loads 0. It has no entry test for dead, inert or inactive creatures either, and does no damage or target work (**executed**) | 0x113c10 (the result set to zero in front of the only return), 0x2a8bc8 (one caller's test); `spec/creature-tick.md` section 1; FINDINGS R13 | code |
| 17 | `creatures.md`, "How the pieces fit" | "Its run calls `Creature_updateActive`, then usually `Creature_run` …, `Creature_processDamage`, a state switch …" | that is not the order of the calls: `Creature_processDamage`, `Creature_run`, `Creature_updateActive`, the weapon holder, `Creature_stepAnim`, `Creature_applyKnockback`, slot 23, then the state switch, as `monsters.md` 1.3 has it | `Skelight_run`: calls at 0x2a8bb0, 0x2a8bc0, 0x2a8bd4, 0x2a8c54, 0x2a8c6c | code (one class) |
| 18 | `creatures.md`, helper catalogue, `Creature_pickTarget`; `symbols/creatures.tsv` 0x10ded0 | "Keeps the current target while it is alive and still an enemy. Every 32nd frame … or when forced: box query …" | between scans it keeps a target that is still an enemy; a scan **starts from nothing** and drops a target the query does not return; `force` with a current target takes any other candidate whatever its score; a dead target leads to set-state 0 and the base class does not clear the handle (**executed**) | `spec/creature-tick.md` section 6; FINDINGS R13 | report |
| 19 | `creatures.md`, "Pending damage" | knock-back speed "(100 / 150 / 200 / 312.5)", given for the death sequence and for nothing else | those four are the death table only: a hit the creature survives stores 100 / 150 / 225 / 375 and a tick without pending damage 50 / 75 / 100 / 156.25. Also new there: a corpse's pending amount is cleared but its flags are kept; the burn test in the death branch can never hold (**executed**) | `spec/creature-tick.md` 3.1, 3.4 | report (a search of the function for the constants as immediates found none and was not taken further) |
| 20 | `creatures.md`, creature flag table, 0x400000 / 0x800000 | "following a player, standing ahead / behind" | adds: the bits act only while the charm timer +0x312 is non-zero, and the tick the timer reaches 0 clears both (**executed**) | 0x112d68 (timer 0: the whole block is skipped), 0x112d88–0x112da0 (the clear), 0x112da8–0x112db0 (the bits tested inside the branch) | code |
| 21 | `creatures.md`, "Second timers" | "float seconds, −1/60 per `Creature_run`" | not for the chill timer +0x344: it loses 1/15 per tick, and 1/30 more on a player (**executed**) | 0x113618–0x113624 (0x3d888888 subtracted); `spec/creature-tick.md` 4.7 | code (the 1/15); the player's extra 1/30 from the report |
| 22 | `creatures.md`, C3 and flag 0x80000000; `issues/arena-entry.md`, E11 | the boss-meter bit is written from one per-machine input, the local alive list | from two: the block looks for a player only while the creature's active bit 63 is set, and that bit is written from `obj_updateActive` (**executed**) | 0x113980 (a sign test of the 64-bit flag word in front of the block) | code |
| 23 | `spec/movement-camera.md`, 6.3, `Creature_moveToDirect` | "a non-zero offset replaces the aim point by position + offset" | only when the offset's x **and** y are both non-zero; the ray length is min(distance, radius + 10) (**executed**) | 0x115778–0x11577c and 0x115788–0x11578c (x, then y, compared with zero; either being zero skips the offset) | code (the two tests); the ray length from the report |
| 24 | `spec/movement-camera.md`, 6.4 step 3; `symbols/startup.tsv` `Creature_computeAvoidanceTarget` 0x109280 | "a point 1200 units along the straight line when the probes are clear or the obstacle is more than two radii away" | `pos + (p − pos) × 1200` — 1200 times the vector; "more than two radii away" is the test `t × \|D\|² < (2 radius)²` failing, with `t` not squared (**executed**) | 0x109344–0x109380 (three components times 1200.0, added to the position), 0x1093b0–0x1093c8 | code |
| 25 | `spec/movement-camera.md`, 6.4, `Creature_computeAvoidanceOffset` | side selection and exact length "[U] for the exact rule"; "the `PathName` follower and the `followPlayer` logic … were not read" | answered: the offset is 2 × radius long along facing ∓ 12000, the side chosen from three forward rays and two side rays by the rules of `spec/creature-tick.md` section 10; the follower and `followPlayer` are in 4.3 and 4.5 there (**executed**) | `spec/creature-tick.md` sections 4, 10 | report |
| 26 | `spec/movement-camera.md`, 6.3, `Creature_fleeFrom` | (not stated) | adds: the avoidance offset is refreshed on every staggered 8th frame, and the aim is written back as the flee point (**executed**) | `spec/creature-tick.md` 9.4 | report (an addition) |
| 27 | `spec/movement-camera.md`, 6.4 step 6 | "When a side-step ends with still no progress for 300 ticks: `world_findFreeSpot` … and teleport there" | "ends" is exact: the teleport can happen only on the one tick on which the clock equals the side-step deadline (**executed**) | `spec/creature-tick.md` 9.5 | report |
| 28 | `monsters.md`, 1.3 helper table, `Creature_isAttackReady` 0x1195f0 | "test timers +0x314 / +0x318 / +0x31c for zero" | not only a test: for a creature without a target it first stores zero to the cooldown +0x318 (**executed**) | 0x1195f0–0x1195f8 | code |
| 29 | `monsters.md`, 1.4, `Creature_filterState`; `symbols/creatures.tsv` 0x10a9c0 | "it redirects requests to 5, 0x13 or 0x10 while timers A, C or B are running" | one chain, not three tests: the root redirect applies to requests other than 0, 5 and 6–15, gives 5 only with a target (0 without), and then skips the stun and cooldown tests (**executed**) | `spec/creature-tick.md` 12.3 | report |
| 30 | `symbols/creatures.tsv` `Creature_takeDamage` 0x116638; `creatures.md`, "Pending damage" | (the brief for the reporting work located slot 2 at 0x116740, and FINDINGS ST3 cites that address beside the function's name) | slot 2 is 0x116638; 0x116740 is the `handle_link` call inside it that records the attacker. Both files already had 0x116638; the note and the paragraph now say what 0x116740 is | `vtab.py show Creature`: slot 2 is 0x116638; 0x116740 is a call of `handle_link` inside that function's range | code |
| 31 | `creatures.md`, C4 | the `PathName` follower's teleport, without its end-of-list case | adds: within 48 units of its point the follower fetches the next point of the list and copies from it without a null test — a read through a null pointer at the end of a list; whether a shipped path ends that way under a follower is Unknown | 0x112b58 (the fetch), 0x112b68 (the first load through the result, no test between); `spec/creature-tick.md` 4.3, where the original and the model both fault | code |
| 32 | `objects.md`, "Properties", and flag 0x8000 | "A `hide` property moves the object to the off-grid list" (said of the base constructor); 0x8000 "set by hide" | the base constructor looks `hide` up before it has stored the property list, so for a pool block the test never fires; hiding at load is done by `Creature_ctor` and `Catapult_ctor`, and a class that does not test the property ignores it (**executed**) | 0x14ccf0 (the lookup) comes before 0x14cd64 (the store to +0x2c); 0x109f10–0x109f3c (`Creature_ctor`: off-grid, bit 3 of +0x231, flag 0x8000) | code (the order, and `Creature_ctor`); `Catapult_ctor` 0x24d598 from the report |
| 33 | `objects.md`, grid table and flag 0x2; `symbols/objects.tsv` `obj_linkToGrid` 0x14f120 | "new flag-2 objects" are linked to the off-grid list | only in `obj_linkToGrid`, whose single caller is the prediction-copy clone; `GameObject_ctor` zeroes the flag word before it links, so no constructed object starts off-grid or in grid B because of a flag (**executed**) | `ps2elf.py xref`: one call, 0x13b58c; 0x14cb94 (flags zeroed) comes before 0x14cc34–0x14cc7c (the two flag tests) | code |
| 34 | `objects.md`, `runObjects` step 1 and row O6 | "Destroy every object on `g_deleteList`"; the exclude mask listed for box queries, run walks and grid walks | the flush is an iterator walk that is given `g_excludeMask` too: a deleted object with a masked flag is skipped and stays on the list (**executed**) | 0x14b928 (the mask loaded), 0x14b94c–0x14b950 (`iter_begin` on the delete list); FINDINGS R15 | code |
| 35 | `objects.md`, "Run lists" | "The slow lists are filled round-robin" | true; adds that the cursor is stepped before it is used, so after teardown the first slow object goes to list 1 (**executed**) | `spec/object-system.md` 5.1 | report (an addition) |
| 36 | `objects.md`, movement helpers; `symbols/objects.tsv` `world_findFreeSpot` 0x14acf8; `issues/arena-entry.md`, section 2 | "three draws per try"; "clear of blocking objects"; the height "within 6 of the centre's" | three draws per *sample*, a try repeating samples until one is inside the unit ball; "clear" is `dx² + dy² > radius² + r²`, the sum of the squares; the height test is one-sided (**executed**) | 0x14ae58–0x14ae5c (the branch back to the draws), 0x14b094–0x14b0ac (the two squares added, then the compare); FINDINGS R14 | code (the loop and the sum); the one-sided height from the report |
| 37 | `spec/skills-35-68.md`, 1.4 | an object created from a slow-list walk "is also first run on the next frame" | right for the every-frame list; two cases added: an object that joins this frame's slow list during an earlier walk runs in the same tick, and one that `obj_updateActive` moves onto this frame's 60-list runs twice in that tick (**executed**) | `spec/object-system.md` 2.3, 5.2; FINDINGS R14 | report |
| 38 | `OVERVIEW.md`, "Time and tasks" | "object visibility (-1)" | priority 0, registered after the water task, which is also 0 — as `mainloop.md` already had it. Read, **not executed** | 0x322a8c (the priority argument is zero) | code |
| 39 | `mainloop.md`, section 2 | "a task added at or before the cursor waits for the next pass" | adds the case that goes the other way: after the running task has removed itself the cursor is one lower, and a task inserted at its old index is called in the same pass (**executed**) | `spec/object-system.md` 6.1; FINDINGS R14 | report |
| 40 | `symbols/objects.tsv` `world_createObject` 0x14f6c8 (reported against `names.tsv`, which has no such row) | "(className, Vec3 *pos, angle)" | four arguments: the property list in the fourth register goes through to the factory untouched | 0x14f6c8–0x14f70c (the fourth argument register is not written before the indirect call) | code |
| 41 | `symbols/objects.tsv` `world_findObjectsByClass` 0x14c0b8 (reported against `names.tsv`, likewise) | "comparing the type-info name" | adds: in its length-prefixed form, and only objects on a run list are found (**executed**) | `spec/object-system.md` 4.6 | report (a confirmation with detail) |
| 42 | `objects.md`, "Deleting"; `symbols/objects.tsv` `world_flushDeleteList` 0x14f3a8 | one of the places where the delete list is flushed | no call of it and no stored pointer to it exists; the flushes that happen are the inline copies in `runObjects`, `world_loadRecords` and `world_deleteAllObjects` | `ps2elf.py xref` and `ptrs` return nothing for 0x14f3a8 | code |
| 43 | `issues/kill-loot-xp.md`, head, result table, section K1, ranked list | K1 "Observed"; in `drunare` "a silent bag difference rather than an immediate mismatch"; "no test patch has been run on a live game" | **Ran**: reproduced on two linked instances. At a level exit the machine that does not own the player ran the exit's script and changed level, the owner's did not, and each flagged the other out of sync within four ticks. P1 on both machines removes it; the lockout patch in its place does not. The ticks are tabulated in the section; "silent" is no longer assumed for the arena | `issues/live-rig.md` 7.3 (run base4, `pair-k1.rig`); FINDINGS V10, K1 | running game |
| 44 | `issues/kill-loot-xp.md`, result table, section K2, ranked list | K2 "Observed"; the window "*Inferred* from F2"; a two-machine test described as still to be made | **Ran**: at a lead of 14 the owner's menu flag rose 11 ticks before the potion press reached the tick; the other machine removed the potion and the owner did not; hit points agreed and no out-of-sync byte was set to the end of the run. P2a with P2b on both machines removes it | `issues/live-rig.md` 7.3 (run base3, `pair-k2.rig`); FINDINGS V11, K2, U4 | running game |
| 45 | `issues/kill-loot-xp.md`, "What to record on two machines"; "Patch proposals (all untested)" | a table of observations to make; four untested patches | a dated note says which rows were seen (the third and the fourth) and a row is added for K1 at an exit; heading and lead say that P1, P2a and P2b were run on the linked pair, P3 was not, and none in PCSX2 or on a console | `issues/live-rig.md` 7.3 | running game |
| 46 | `issues/draw-sim-leaks.md`, head, result table, "K1, K2 (known)" | the live game "has run one machine only"; "no test patch has been run on a live game"; K1 and K2 "Both **silent**" | a dated result at the head; K1 and K2 are **Ran**; K1 at a level exit is not silent | `issues/live-rig.md` section 7; FINDINGS V9–V13 | running game |
| 47 | `issues/draw-sim-leaks.md`, "Ranking" | 1 K2, 2 K1 ("Silent, usually repaired …"), 3 D26 | the order is kept — it is by likelihood in the fight, on which the runs gave nothing that changes it — and each of the three says what was run: K2 real and silent; K1 real, and by severity the first of the two, since an exit ends the session; D26 tried once and not settled. A paragraph gives the twelve arena runs, among them the one with K1's and K2's inputs unpatched | `issues/live-rig.md` 7.3, 7.5 | running game |
| 48 | `issues/draw-sim-leaks.md`, "Ranking", last paragraph | "a large lead plus K2 … but nothing here proves it" | kept, and followed by where it stands: the mechanism is confirmed, the link to the arena is not. The arena stayed in sync with K1 and K2 available and with both patched out; no arena run combined a large lead with the inventory button; the rig cannot stall | `issues/live-rig.md` 7.3, 7.5 | running game |
| 49 | `issues/draw-sim-leaks.md`, "Patch proposals (all untested)", proposed row U4, "Not done" | the first three proposals "are not in `patches/` yet"; U4 "Inferred"; the arena question "needs two running copies" | P1, P2a, P2b run on the linked pair and P5 once as a control; the three are in the patch file now; U4 has one **Ran** case; two running copies exist and the arena question is still open | `issues/live-rig.md` 7.3; the patch file (read, not edited) | running game |
| 50 | `issues/arena-desync.md`, head | "the arena has not been reached on it, a desync needs two machines, and no test patch has been run on a live game" | a dated result: twelve arena runs between two linked instances stayed in sync, 68,685 ticks — what was varied, and what that does and does not say (identical machines, placeholder characters without skills, the level name written directly) | `issues/live-rig.md` 7.4–7.5; FINDINGS V12, D25 | running game |
| 51 | `issues/arena-desync.md`, "What to record on two machines"; "Noticed on the way", the lockout bullet | a table of observations to make | a dated note: the message never appeared, so no row was observed, "knight fight, nobody has died" included; which phases the runs reached. The lockout bullet has the one D26 attempt: the menu closed in the death tick and no damage call fell into the rest of it | `issues/live-rig.md` 7.3, 7.5 | running game |
| 52 | `issues/arena-entry.md`, head, timeline row 19, section 3.1, proposed row E4 | the live game "has not entered `drundar` or `drunare`"; the remainder 2 "**Inferred** from Observed pieces"; "E ≈ S + 1,270" | a dated result at the head; the opening cutscene started on tick 1022 (remainder 2 modulo 15) and lasted 1,268 ticks, in all twelve runs — **Ran**; and what was not exercised, the way in from `drundar` | `issues/live-rig.md` 7.4–7.5; FINDINGS E4, V12 | running game |
| 53 | `issues/arena-entry.md`, "What to record on two machines"; "Not done" | a table of thirteen readings; "Nothing here was run" | the two readings that were taken are marked **Ran** in their rows (S and S mod 15; E − S); a dated note says that no run had a first mismatch at all and names the rows that were not read out | `issues/live-rig.md` 7.2, 7.5 | running game |
| 54 | `online-setup.md`, head; "Settings every player must match" and its K1 / K2 item; "Not checked" | "rows V1–V8 … and two machines have not been joined"; "nothing in this list has been tested on a running game; the live game … is a single machine"; "until the patches for them are tested"; the rig "has shown only that one machine reaches and runs a lockstep net game" | brought into line with the paragraph of the same page that already reported the two confirmed patches: two instances have been joined (V9–V12), K1, K2 and their patches are confirmed on that pair, and the pair says nothing about machines that differ | `issues/live-rig.md` section 7 | running game |

### Q1. Summary

| | Count |
|---|---|
| Rows in table Q2 | 54 |
| … corrections applied | 54 |
| … from the running game (**Ran**, `live-rig.md` section 7) | 12 (rows 43–54) |
| … re-checked against the code, wholly or for the part named | 26 (rows 2–8, 10, 11, 16, 17, 20–24, 28, 30–34, 36, 38, 40, 42) |
| … taken from the reporting document | 16 (rows 1, 9, 12–15, 18, 19, 25–27, 29, 35, 37, 39, 41) |
| … whose corrected statement is, wholly or in part, an executed result of the reporting document | 32 |
| Reported corrections found wrong | 0 |
| Reported corrections applied in a different place or form (Q4) | 8 |
| Reported items not applied (Q4) | 6 |
| Symbols renamed / symbol notes changed | 0 / 15 |

`python3 -I -B tools/symtab.py check` after the edits: 5817 symbols, 0 conflicts, 0
malformed lines.

Where each group of rows came from: world queries 1–15; creature base 16–31; object system
32–42; live rig, phase 2, 43–54.

### Q3. Symbol files

No address or name was changed. Notes changed, all to match a row of Q2:

| File | Symbol | Row |
|---|---|---|
| `symbols/engine.tsv` | `path_goalTestClearLine` 0x1844f0, `path_goalTestRanged` 0x1845bc, `path_goalTest3` 0x1846a4 | 4, 5, 6 |
| `symbols/engine.tsv` | `terrain_testFlag1` 0x183b48, `terrain_raycast` 0x18a5c0, `world_movePiece` 0x182c98 | 7, 8, 10 |
| `symbols/creatures.tsv` | `Creature_pickTarget` 0x10ded0, `Creature_filterState` 0x10a9c0, `Creature_takeDamage` 0x116638 | 18, 29, 30 |
| `symbols/startup.tsv` | `Creature_computeAvoidanceTarget` 0x109280 | 24 |
| `symbols/objects.tsv` | `obj_linkToGrid` 0x14f120, `world_findFreeSpot` 0x14acf8, `world_createObject` 0x14f6c8, `world_findObjectsByClass` 0x14c0b8, `world_flushDeleteList` 0x14f3a8 | 33, 36, 40, 41, 42 |

0x116740 was given no row of its own: it is a call site inside `Creature_takeDamage`, not
an entry, and the note of 0x116638 now says so.

### Q4. Applied differently, not applied, and noticed while editing

No reported correction was found to be wrong against the code. Eight were applied in a
different place or form than reported:

1. **`names.tsv`, `world_createObject` and `world_findObjectsByClass` (object system).**
   `names.tsv` has no row for either; both are rows of `symbols/objects.tsv`, which this
   pass may edit, and were corrected there (rows 40, 41).
2. **"Slot 2 is at 0x116638, not 0x116740" (creature base, item 13).** No document or
   symbol file of the repository put slot 2 at 0x116740: `symbols/creatures.tsv` and
   `creatures.md` name 0x116638, and `issues/stale-pointers.md` cites 0x116740 as the link
   call, which it is. Applied as a note that says what 0x116740 is (row 30). The one place
   that sets the address beside the function's name is the ledger (Q5).
3. **Knock-back speeds (creature base, item 4).** `creatures.md` gave the four speeds
   inside the death sequence, where they are right; the correction was applied as an
   addition of the two tables it lacked (row 19).
4. **Order of calls (creature base, item 2).** Reported as "not the order in the class
   read here", which is one class. Applied with that qualification (row 17).
5. **Boss-meter bit (creature base, item 6).** Reported against `creatures.md` C3 and
   FINDINGS E11; `issues/arena-entry.md` carries the same statement in its own E11 and was
   changed with it (row 22).
6. **World queries.** The hand-over list had five statements of `engine.md` and one of
   `formats/world.md`; section 12 of the reporting document has eleven and four, and all
   were applied (rows 1–3, 9, 11 and 13 are the ones beyond the list). "Section 5 can be
   marked Executed" was applied at the head of the section, for the sub-sections the
   reporting document names and no further (row 14).
7. **`world_findFreeSpot` (object system).** Reported against `objects.md`, with a remark
   that `issues/arena-entry.md` section 2 says "within 6"; that sentence was corrected too
   (row 36).
8. **`draw-sim-leaks.md`, the ranking (live rig).** The order was not changed. The ranking
   is by likelihood in an arena fight and the runs carry no evidence on that; what they
   change is the severity of K1 and the status of all three, which is what the list now
   says (row 47).

Rows that go beyond the hand-over list but come from the same sections: 15 and 25
(answered "not reached" and "not read" statements), 31 (the null read of
`creature-tick.md` 4.3, listed in the hand-over without a target document), 35 and 41
(additions to statements that were right), and in row 54 three sentences of
`online-setup.md` — see the next paragraph.

`online-setup.md` was to be changed only if it still said that no patch had been run on a
live game. That sentence was gone: the "Suggested patch set" section had been brought up
to date. But the same page still said in three other places that two machines had never
been joined, that the live game was a single machine and that the K1 and K2 patches
awaited testing, in contradiction with its own updated paragraph. Those sentences were
changed (row 54) and nothing else on the page.

Not applied:

- **`tools/ee_emu.py`: an unaligned `sdl` / `sdr` / `swl` / `swr` is logged as a store of
  the whole aligned word (creature base, section 17).** `tools/` is not edited by this
  pass. It joins the three gaps listed in F4.
- **The names proposed in `spec/world-queries.md` section 13** (`path_blockNodes`
  0x18b6c0, `path_unblockNodes` 0x18b584, `path_goalTestRadius` 0x1844a4 and ten globals).
  New symbols, not corrections; this pass has no symbol file of its own. The two functions
  are named by address in rows 3 and 11.
- **Every proposed ledger row** of the three reporting documents and of `live-rig.md` 7.6.
  Q5.
- **The "confirmed by execution" paragraph of `spec/object-system.md` 10.1** (the box
  query, the reaper, the pool sample, teardown order, the start marker, `tasks_run`).
  Confirmations of statements that stand; the documents were not marked up one by one.
- **"The brief for this work located slot 2 at 0x116740" (creature base, item 13).** Not a
  repository document.
- **The sentence "no test patch has been run on a live game", and "rows V1–V8", at the
  head of every other document.** The fourth pass put that wording into 49 documents
  (F3). It is out of date for the project as a whole: two test patches have been run, on
  two linked instances, and the live-game rows go to V13. This pass changed it only in
  the five documents of its work list; 34 others still carry it (the search is the
  first line of Q6; this file is the 35th hit), and `netcode.md` also still says in its
  head that "two machines have not been joined". It is still true of each of those documents' *own*
  patches, none of which has been run, so no statement about a document's own content is
  wrong — but the sweep should be repeated.

Noticed while editing, not reported by anyone:

- `issues/kill-loot-xp.md`, K2: the verdict says the drop message "removes one of whatever
  sits in the first cell" on every machine. In the scripted run the three logged
  quantities changed only by the direct removal on the other machine (2, 2, 2 against
  2, 1, 2 to the end), so the message removed nothing visible on either. That fits the
  executed result on the ledger (the message's last byte is −1 and is used as a panel
  index) better than the verdict's wording. Stated in the section as seen and not
  followed.
- `issues/kill-loot-xp.md`, K1: what the arena's own exit trigger does on a use press was
  read by neither that document nor `draw-sim-leaks.md` ("one usable trigger whose
  predicate only reads"). After the `strife` run it decides whether K1 in the arena is
  silent or ends the session; both documents now say it is open.
- `issues/draw-sim-leaks.md`: one `strife` run had a bus delay of 25 with jitter 10 and
  K1's inputs and did not diverge; `live-rig.md` does not give its lead. The document
  cites the run by its bus settings only.
- `objects.md`, flag 0x800: the evidence column cites 0x14cc78, which is the constructor's
  test that row 33 shows can never succeed. The row's statement stands on its other
  address (0x14f094) and was left.
- `symbols/engine.tsv` `terrain_raycast` says "23 callers"; `spec/world-queries.md` counts
  28 call sites. Functions against sites, probably; not re-counted.

### Q5. For the owners of files this pass does not edit

`FINDINGS.md`:

| Row | What it needs |
|---|---|
| ST3 | Names `Creature_takeDamage` and gives 0x116740 in its evidence column. 0x116740 is the `handle_link` call inside the function; the function, slot 2 of `Creature`, is 0x116638. Should read "0x116638 (the link is its call at 0x116740)" |
| E11 | Add the second per-machine input: the boss-meter block runs only while the creature's active bit 63 is set (0x113980), and that bit comes from `obj_updateActive` (`spec/creature-tick.md` 4.10, 14) |
| D26 | `live-rig.md` 7.6 proposes: still not run to a divergence — the menu does close in the death tick on the owner's machine, but no damage call fell into the rest of that tick. The row has nothing of it yet |
| D5 (and engine P13) | `spec/world-queries.md` section 13: a search suspended on T0 and resumed gives the same result, path, marks and globals as one run in a single call (executed); between T0 = 7513 and 9000 a non-blocking `path_service` keeps calling `path_search`, one round per call (0x184830–0x184838, 0x184de4) |
| D6 | `spec/object-system.md` 10.2: the switch `g_cullByCamera` is "mode is not 1" of this machine's camera object (0x1e4da8–0x1e4ddc), so during a net cutscene the choice between camera and players is itself per machine if camera modes can differ then (Unknown) |
| D29, D35 | R15 carries the fact that `isNearView` is a square in x and y read from the player table; the two rows that depend on it still say "near the view" without it, and an open dialog (D38) narrows `obj_updateActive` but not `isNearView` |
| D21 (and `objects.md` O1) | The reaper works from a sample: `g_poolFreeCount` changes only on frames divisible by 64 and teardown forces it to 100000, so the reaper is off from a level load to the next such frame (0x14b9ac–0x14b9c8, 0x14c4b4) |
| R15 | Could add the consequence stated in `spec/object-system.md` 10.2: while the mask is 0x20000, an object with that flag that was `obj_delete`d stays on the delete list, in the grid and in the name table; whether anything deletes a prediction copy that way is Unknown |
| new rows proposed and not found on the ledger | `spec/creature-tick.md` section 14: the `followPlayer` warp in `Creature_run` runs only while active bit 63 is clear, so a charmed follower can be moved to its leader on one machine and not another during a net cutscene — a position write in the D6 family (0x112f7c–0x113130). `spec/creature-tick.md` 4.3: the null read at 0x112b68 at the end of a `PathName` list, reachability Unknown. `spec/world-queries.md`: 0x185448 and 0x1857e4 have no caller |

Rows checked and found already amended: K1, K2, E4, U4, D25, D34, V9–V13, R8–R10, R13–R15.

`names.tsv`:

| Row | What it needs |
|---|---|
| `world_createObject` | Nothing: the hand-over names `names.tsv`, but the file has no such row. The row is `symbols/objects.tsv` 0x14f6c8 and now has the four arguments |
| 0x112948 `Creature_run` | "common creature run; … burn tick draws g_randSeed". Worth adding: returns 0 on every path and has no entry tests (R13); and the burn draw is made for a burning *player* only, on every 32nd frame, not for a monster (`spec/creature-tick.md` 4.8) |
| 0x1e4d48 `gameSetObjectVis` | "first run task": it is the second of two run tasks with priority 0, registered after `runwater` (0x322a3c, 0x322a90) |
| 0x14cb10 `GameObject_ctor` | optional: zeroes the flag word before the grid link, so its tests of 0x2 and 0x800 never succeed; looks `hide` up before the property list is stored |

`tools/`: the fourth `ee_emu.py` gap (unaligned stores logged as whole words), with the
three of F5.

`docs/` as a whole: the head sentences of the fourth pass's sweep (last item of "Not
applied" above).

### Q6. Re-checking

```
grep -rln 'no test patch has been run\|V1–V8' docs/               # documents still carrying the fourth pass's head sentence
python3 -I -B tools/symtab.py check                               # 0 conflicts, 0 malformed
python3 -I -B tools/dis.py SLUS_209.73 184be4:184bf0              # path_service: the start node's mark 0xf00
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 18b6c0             # two callers (torch, fire); 18b584: one
python3 -I -B tools/dis.py SLUS_209.73 1844f0:1845bc              # goal test 1: inside the radius, 0.98 < ray
python3 -I -B tools/dis.py SLUS_209.73 1845bc:1846a4              # goal test 2: outside passes; ray < 0.98
python3 -I -B tools/dis.py SLUS_209.73 1846a4:184798 | grep -E 'jal|3f40|c\.olt'   # goal test 3: world_raycast, 0.75
python3 -I -B tools/dis.py SLUS_209.73 183da8:183e18 | grep mtc1  # terrain_testFlag1 returns a float
python3 -I -B tools/dis.py SLUS_209.73 14aee4:14aef4              # a caller compares it as a float
python3 -I -B tools/dis.py SLUS_209.73 18a5c0:18a740 | grep -E '3e80|4370|0x3e9'   # raycast: 0.25, 240.0, 1001
python3 -I -B tools/dis.py SLUS_209.73 182e98:182ee0              # world_movePiece: stores into the chunk record only
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 185448             # nothing; the same for 1857e4 and for ptrs
python3 -I -B tools/dis.py SLUS_209.73 113c08:113c48              # Creature_run: one return, result 0
python3 -I -B tools/dis.py SLUS_209.73 2a8ba0:2a8c70 | grep jal   # Skelight_run: processDamage, run, updateActive, stepAnim, knockback
python3 -I -B tools/dis.py SLUS_209.73 112d64:112db4              # charm timer 0 skips the follow block; bits cleared at expiry
python3 -I -B tools/dis.py SLUS_209.73 113608:113630              # chill: 0x3d888888 per tick
python3 -I -B tools/dis.py SLUS_209.73 113960:1139a4              # boss meter: sign test of the flag word (bit 63)
python3 -I -B tools/dis.py SLUS_209.73 115770:115790              # moveToDirect: offset x and y each compared with zero
python3 -I -B tools/dis.py SLUS_209.73 109340:1093cc              # avoidance target: D x 1200; t x |D|^2 against (2r)^2
python3 -I -B tools/dis.py SLUS_209.73 1195f0:119608              # isAttackReady zeroes +0x318 without a target
python3 -I -B tools/vtab.py SLUS_209.73 show Creature | head -3   # slot 2 = 0x116638
python3 -I -B tools/dis.py SLUS_209.73 11673c:116748              # 0x116740: a call of handle_link
python3 -I -B tools/dis.py SLUS_209.73 112b50:112b70              # follower: next point fetched and read, no null test
python3 -I -B tools/dis.py SLUS_209.73 14cce4:14cd68              # GameObject_ctor: hide looked up before +0x2c is stored
python3 -I -B tools/dis.py SLUS_209.73 109f10:109f40              # Creature_ctor: its own hide test
python3 -I -B tools/dis.py SLUS_209.73 14cb90:14cb98              # GameObject_ctor zeroes the flag word
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 14f120             # obj_linkToGrid: one call, 0x13b58c
python3 -I -B tools/dis.py SLUS_209.73 14b924:14b954              # runObjects: the flush is given g_excludeMask
python3 -I -B tools/dis.py SLUS_209.73 14ae50:14ae60              # findFreeSpot: sample rejected, back to the draws
python3 -I -B tools/dis.py SLUS_209.73 14b088:14b0b0              # findFreeSpot: radius^2 + r^2
python3 -I -B tools/dis.py SLUS_209.73 322a84:322a98              # gameSetObjectVis registered with priority 0
python3 -I -B tools/dis.py SLUS_209.73 14f6c8:14f720              # world_createObject: fourth argument untouched
python3 -I -B tools/ps2elf.py SLUS_209.73 xref 14f3a8             # world_flushDeleteList: nothing; ptrs likewise
```

## Sixth pass

Scope: the corrections reported after the fifth pass by six reference models that ran the
original code — `docs/spec/arena-monsters.md` section 14, `docs/spec/game-messages.md`
section 12, `docs/spec/script-builtins.md` section 9, and the three executed skill
companions `docs/spec/skills-01-34-executed.md` section 3,
`docs/spec/skills-35-68-executed.md` section 5 and `docs/spec/skills-69-101-executed.md`
("Corrections to …") — and what `docs/issues/live-rig.md` sections 8 and 9 (phases 3 and
4: unattended fuzzing, a float mismatch, a measured outage, and the arena with real
characters) change in eight older documents. While the pass was being made, section 10 of
that document (phase 5) and ledger rows V21–V23 arrived; they name the caller of the
touch handler, confirm its patch, trace the item bytes to loot creation and to the
prediction copy, and give the result with every published section on. They were folded
in wherever they overtook a sentence this pass had just written ("not known", "not yet
run", "not traced") and nowhere else. The eight documents: `docs/issues/arena-desync.md`,
`docs/issues/arena-entry.md`, `docs/issues/prediction-copy.md`,
`docs/issues/float-divergence.md`, `docs/issues/lag.md`, `docs/issues/kill-loot-xp.md`,
`docs/issues/draw-sim-leaks.md` and `docs/online-setup.md`.

Method as before: the smallest change, in place, keeping a clause that says what the
earlier version said; an overturned paragraph of an issue document is kept and followed by
what overturned it, and each of `arena-desync.md` and `arena-entry.md` has a dated part
"What the live rig showed" in front of its earlier result. A corrected statement that
rests on a run of the original instructions says **executed**; one that rests on the
running game says **Ran**. Nothing was run in this pass.

The last column of X2 says which kind of evidence stands behind the corrected statement:

- **running game** — a **Ran** result of `docs/issues/live-rig.md` sections 8, 9 and 10: two
  instances of the game in the Play! emulator, joined through the developer LAN start and
  compared tick by tick, in section 9 with level-25 characters that have skills. Two
  copies of one emulator build on one host — not a PlayStation 2, not PCSX2. Where such a
  result contradicts an earlier reading or an earlier run with placeholder characters, it
  wins;
- **code** — the address given was read in this pass (`tools/dis.py`, a word read from
  the executable, or `decomp/all/<entry>.c` where the row says "decompile"); a
  qualification says how far the check went. Where the reporting document ran the
  original instructions in `tools/ee_emu.py` the corrected text says **executed**, and
  that result wins over the earlier reading;
- **report** — taken from the reporting document without an independent reading.

`FINDINGS.md`, `names.tsv`, `patches/`, `tools/`, the top-level documents of other
contributors and `docs/issues/live-rig.md` were not edited; what they need is in X5. The
six reporting documents were not edited either. `patches/` was read for the two sections
named in rows 80 and 81.

### X2. Corrections

| # | Document, section | Said | Says now | Evidence | Checked |
|---|---|---|---|---|---|
| 1 | `monsters.md`, Horsemen, states 6, 7, 10, 0xb | "on the hit event a full-damage arc test …, on event bit 1 a second test with a third of the damage", for all four states | the two are alternatives on one tick: only state 10's clip has a bit-1 event and it has no bit-0 event, so state 10 is the one-third hit (flags 0x100001, no descriptor) and nothing else; 6, 7 and 0xb are two, three and three full hits (**executed**) | `spec/arena-monsters.md` 3.3, 14 item 2 | report |
| 2 | `monsters.md`, Horsemen, state 5 | "two draws … choose between states 10, 7 and 6"; "otherwise one own-generator draw in 60 per frame returns to chase" | first draw odd **and** blocked → 10, otherwise a second draw, odd → 6, even → 7; the return to chase also needs no ally near the target (**executed**) | decompile of 0x27236c, case 5: the `& 1` test with `Creature_isBlockedByTarget`, the remainder by 60, then `Creature_countAlliesNearTarget` | code (decompile) |
| 3 | `monsters.md`, 1.4, state 1 | "walk back / wander" in a table whose state 0 leaves "to 3 with a target" | leaving state 1 is per class: the skeleton and Zek go to 3, a knight goes to **0** and chases a tick later (**executed**) | decompile of 0x27236c, case 1: the seen branch ends in set-state 0 | code (decompile) |
| 4 | `monsters.md`, Horsemen (new bullet); `symbols/monsters.tsv` `Horsemen_setState` 0x272f4c | (not stated anywhere) | a mounted knight returns for every request below 0x19, death 0x14 included, after the filter and the clearing of flag 0x200; a request without a case runs a nested set-state 3 and then stores the **requested** number; `Skelight_setState` and `Zek_setState` store 0 (**executed**) | decompile of 0x272f4c: the mount-handle test in front of the switch; the default case and the store behind it | code (decompile) for `Horsemen`; the other two classes from the report |
| 5 | `monsters.md`, 1.3 step 1 | "optional: update the embedded weapon helper", as the first step | first only in `Horsemen_run`; `Zek_run` does it after the activity test, `Skelight_run` after it and through slot 22 with an item model (**executed**) | `spec/arena-monsters.md` 3.3, 4.3, 5.3 | report |
| 6 | `monsters.md`, Skelight, and the layout row +0xf4 | "+0xf4 counts the swing down"; "Skelight: attack frames left"; states as in the shared table of 1.4 | state 0x13 leaves to 0; set-state 0x12 is ignored; states 2, 4, 7–0xf, 0x11, 0x15, 0x16 have no case in the run and a request for them becomes state 0; +0xf4 is the constant 1, taken off once the clip has stopped (**executed**) | `spec/arena-monsters.md` 4.3, 4.4, 14 item 7 | report |
| 7 | `monsters-2.md`, Zek, the ground wave | "0.43 % of the angle to the reverse bearing is subtracted each frame" (**Inferred**) | the size is right; the direction is away from the point where that angle is zero, toward the enemy's bearing, and there the heading alternates by ±140 units a tick (**executed**) | `spec/arena-monsters.md` 5.4 | report |
| 8 | `monsters-2.md`, Zek | (not stated); the tail "runs in any state" | set-state 5 synchronises its clip to the frame counter; an inactive Zek runs nothing after the activity test, the ground wave included; an unknown set-state stores 0 and starts no clip (**executed**) | `spec/arena-monsters.md` 5.3–5.6 | report |
| 9 | `creatures.md`, "Predicates on the target"; `symbols/creatures.tsv` `Creature_isTargetCharging` 0x118f90; `monsters.md`, Horsemen state 3; `monsters-2.md` (the one place that defined it) | "target faces this creature and moves faster than 100 units/s"; "faces me and moves faster than 100/s" | as coded: faster than 100, and the target's facing within ±0x3ffe of the bearing from the creature **to** the target — a fast target facing away (**executed**) | 0x118fb0–0x118fc4 (the bearing: target minus creature), 0x118fd4–0x118fe4 (compared with the target's own facing), 0x119004–0x119018 (100.0) | code |
| 10 | `spec/skills-01-34.md`, section 11, and its row in the status table | `Creature_setStats(1.33, 1.2, 1.2, 1.0, …, rollHp = 1)`; the draws inside "not traced here"; "the `Skelight` class … not read" | the fifth factor is the experience factor (0.0 in one level, else 1.0); one own draw; the cast and the summon chain confirmed as written (**executed**) | `spec/arena-monsters.md` 4.2, 14 item 9 | report |
| 11 | `spec/skills-69-101.md`, section 87, cast step 1 | "Level through slot 14 (no-op)" | the level stored in the spell is slot 14's result; a no-op only because the base slot returns its argument (**executed**) | `spec/arena-monsters.md` 7.1, 14 item 10 | report |
| 12 | `issues/arena-desync.md`, "The level in facts" and the row "Second deferred counter"; `issues/arena-entry.md`, head part | "counts 300 un-paused frames"; "at 250 it plays a sound"; "about 875 frames after the avatar dies" | `getScaledTime(n)` is n − 1 for every count reached, so: the 302nd counted frame after the fourth knight's death tick; count 252; 877 frames after the avatar's | 0x14412c–0x144154: count × 60.0 × 0x3c888888, truncated — the multiplier is just under 1/60 | code (the formula); the three counts from the report, whose script part was read, not executed |
| 13 | `issues/arena-desync.md`, "The level in facts", the summon table's "Decision" row and the head part; `issues/arena-entry.md`, head part | four `UndeadKnight1`…`4` — neither document said "three" or "mounted", the brief of the reporting work did; "knight 3" used without saying it is a variant number | made explicit: four knights on foot, the mounted form is not in the level; "knight 3" is variant 3, object type `UndeadKnight4`; `UndeadKnight3` casts the insects (**executed**) | `spec/arena-monsters.md` section 1, 14 item 1; FINDINGS D3, D22 | report |
| 14 | `ui.md`, game messages 11 and 7; `netcode.md`, message 3 / 11; `symbols/ui.tsv` `hudmsg_sendLoadLevel` 0x1de598, `hud_onMsg` 0x1d8ca0 | "pending level ← string"; "three filler bytes, level name" | the message is sent with length 4: the name is copied behind the header but left out of the length, so it is not on the wire; its only caller is the offline branch of the level-warp list, message 7 being the net form (**executed**) | 0x1de5ac–0x1de5d4 (type 0xb, three zero bytes, name copied to +4, length = 4); 0x18dd4c–0x18dd70 (the network-mode branch between the two senders) | code |
| 15 | `ui.md`, game message 13; `netcode.md`, message 3 / 13; `symbols/ui.tsv` `hud_onQuickCastWarn` 0x1de340, `hudmsg_sendQuickCastWarn` 0x1de0a4, `hud_onMsg` | "HUD text"; "quick-cast warning" | a warning only for an ability of kind 1; any other kind is queued — object +0x488 = the ability record — when the action state is 2 and no cast is queued (**executed**) | 0x1de388–0x1de38c (+0x488 already set: return), 0x1de394–0x1de3ac (kind 1: the text), 0x1de3d0–0x1de3d8 (state 2: the store) | code |
| 16 | `ui.md`, inventory message 0 and shop message 1; `symbols/ui.tsv` `inventory_dropItem` 0x1c4310 | "slot, u16, item index u32, u16, bag, 2 bytes"; "(slot, index, bag, count, ...)" | slot, column, index, row, bag, panel, mode; mode 0 ground, 1 sold, 2 and up silent (**executed**) | `spec/game-messages.md` section 2 | report |
| 17 | `ui.md`, inventory message 8; `symbols/ui.tsv` `inventory_combineGems` 0x1ceeb8 | "slot, 3 × u32" | bag, descriptor address, item address (**executed**) | `spec/game-messages.md` section 2 | report |
| 18 | `ui.md`, "Shop", buying; `symbols/ui.tsv` `shop_buy` 0x1d1240 | "charges price × 0.6 … if the player has the gold, and calls `inventory_giveItem`" | the gold is taken whether or not the item is received: the store is in the delay slot of the call and the result is not tested; a bag holds 64 (**executed**) | 0x1d1300–0x1d1310 | code |
| 19 | `ui.md`, shop message 0 | "address of a record in the sender's stock table" | adds: the last record of the three lists that is the same item as the chosen grid copy; nothing is sent when it matches none (**executed**) | `spec/game-messages.md` section 4 | report |
| 20 | `issues/kill-loot-xp.md`, section 4 | "bag for the item's category already holds 63 items → refuse" | kept, with: that is the pick-up's own limit; `inventory_giveItem` fills a bag to 64 (**executed**) | `spec/game-messages.md` 5.1, section 12 | report |
| 21 | `issues/kill-loot-xp.md`, K2 verdict and the end of its **Ran** paragraph; `issues/draw-sim-leaks.md`, "K1, K2" | the message "removes one of whatever sits in the first cell of its potion list"; the last byte "*Inferred* out of range"; "not followed further" | settled: the cell is that of the panel numbered like the owner's slot; the wording holds for slot 0; for slots 1–3 in a net game the grid was never built and the message does not touch the potions; the panel byte −1 addresses memory in front of the grids (**executed**) | `spec/game-messages.md` section 10; FINDINGS M1, K2 | report |
| 22 | `player.md`, layout row +0x43f0 | slots 0, 2, 3, 5, 6, 8, 14, 15 | adds slot 1 (the second weapon; executed in equip) and slot 7 (a single category-2 slot; Observed in unequip) | `spec/game-messages.md` 5.3, section 12 | report |
| 23 | `script.md`, 1.7; `symbols/script.tsv` `scr_getAddr` 0x1414a8 | "bounds check, result ignored by callers" | adds the consequence: on a refusal the pointer is not written, so the handler converts the string its stack slot still points at; a shipped script relies on it (**executed**) | 0x1414d8–0x1414dc (the refusal returns 5 with no store), 0x1414e0–0x1414f0 (the store is on the other path only); FINDINGS N1 | code |
| 24 | `script.md`, `addQuest`; `symbols/ui.tsv` `quest_add` 0x1d386c | "appends the pair to every player's quest list unless already present (max 8)" | the loop over the players ends at the first player whose list is full or has the title (**executed**) | 0x1d38c0–0x1d38c4 and 0x1d38e8 (both tests branch into the function's epilogue at 0x1d3940 / 0x1d3944, not to the next player) | code |
| 25 | `script.md`, `removeQuest`; `symbols/ui.tsv` `quest_remove` 0x1d3968 | "Wraps `quest_remove`" | every match becomes a placeholder; only the entries behind the last match move up; the count drops by one (**executed**) | `spec/script-builtins.md` section 9; FINDINGS N3 | report |
| 26 | `script.md`, `playGotItemSound` | "switches to the other of 0/1 if that player has no hit points, and calls `player_voice(slot, 9)`" | the stored active player is clamped, but the voice is played for the unclamped slot and the hit-point test indexes with it (**executed**) | `spec/script-builtins.md` section 9; FINDINGS N8 | report |
| 27 | `script.md`, `runMedalSuccess` | "Draws the result box and the reward lines directly" | adds: lines in the order 3, 2, 1; every text drawn twice (a measuring pass first); offline also returns 0 while the card is busy (**executed**) | `spec/script-builtins.md` section 9 | report |
| 28 | `script.md`, `lightEffect` | "ref pos[3], i unused, i x8" | the second argument is used (× 0.01) and ten values follow: twelve arguments (**executed**) | `spec/script-builtins.md` section 9 | report |
| 29 | `script.md`, `sound` | `sound_playSample(1.0, 1.0, 0, res, 0)` | three floats (1.0, 1.0, 0.0) and two integers (**executed**) | `spec/script-builtins.md` section 9 | report |
| 30 | `script.md`, `clearAllSkills` | "three fields at +0x4a80.." cleared | +0x4a80 and +0x4a84 are cleared; the byte +0x4a85 is set to 1 (**executed**) | 0x145950–0x145960 (a register stored to +0x4a85, zero to the other two) | code (the three stores); the value 1 from the report |
| 31 | `script.md`, `getManaUsed`, `getHealthUsed`, `helpMessageActive` | "Returns the 16-bit counter"; "Returns `g_helpMessageOpen`" | sign-extended loads (**executed**) | 0x142204, 0x142210 (`lh`); 0x1433c4 (`lb`) | code |
| 32 | `script.md`, `checkPlayerAlive`, `restorePlayer` | "the countdown 0x4f7194" | a 16-bit value, read and written as such (**executed**) | `spec/script-builtins.md` section 9 | report |
| 33 | `script.md`, `getPlayerVPosition` | "returns a vehicle float × 128" | compares vehicle +0x90c but keeps vehicle +0x34c (**executed**) | `spec/script-builtins.md` section 9 | report |
| 34 | `script.md`, `getPlayerVDir` | "Returns 1, −1 or 0" | 1 or −1 for the first qualifying vehicle; the 0.707 test never passes the scan on (**executed**) | `spec/script-builtins.md` section 9 | report |
| 35 | `script.md`, `hornOmen`, `planarSteel` | allocate and link | `creature_addSpell` is also called with a null spell when the allocation failed (**executed**) | `spec/script-builtins.md` section 9 | report |
| 36 | `script.md`, `startDialog` | "Preloads the level lump, clears 0x4fdce8, then calls `dialog_start`" | the clear is inside `dialog_start`, after a `Camera_update` on the local camera; a name is formatted into a buffer nothing reads (**executed**) | `spec/script-builtins.md` section 9 | report |
| 37 | `script.md`, `setPlayerFlag` | "bit of record +0x4c28" | bit number mod 32, one byte: bits 8–31 change nothing (**executed**) | `spec/script-builtins.md` section 9 | report |
| 38 | `script.md`, `saveEndConfig` | "sets the completion bit for the difficulty" | 0x08–0x40 for difficulty 1–4; difficulty 0 sets none (**executed**) | `spec/script-builtins.md` section 9 | report |
| 39 | `script.md`, `removeAllItems`, `removeAllWeapons` | "Empties" the bags | as many remove calls for index 0 as the bag's count at the start, each only if the first entry is then non-zero (**executed**) | `spec/script-builtins.md` section 9 | report |
| 40 | `script.md`, `generateMonster` | "Interns the class name in a table of 24-byte names" | the call-out gets a pointer into the table; the count is raised before the copy; neither has a limit (**executed**) | `spec/script-builtins.md` section 9 | report |
| 41 | `script.md`, head | the interpreter "has been executed opcode by opcode" | adds that all 190 built-in handlers have been too, and where their corrections went | `spec/script-builtins.md`; FINDINGS X19 | report (a pointer) |
| 42 | `spec/skills-01-34.md`, section 21, Repulse Undead | soul velocity `(cos16(a), sin16(a), 50.0)` | `(cos16(a) × 450, sin16(a) × 450, 50.0)` (**executed**) | 0x2f4d8c (0x43e10000 = 450.0), 0x2f4da0 and 0x2f4db8 (both products) | code |
| 43 | `spec/skills-01-34.md`, 0.6, projectile step | a water impact makes "one draw from the object's own generator (splash sound variant)" | the draw is made and thrown away; the clip number is the constant 1 (**executed**) | 0x150c14 (the draw), 0x150c24 (the constant 1 as the format argument) | code |
| 44 | `spec/skills-01-34.md`, 0.2; `skills.md`, Skill layout +0x38; `symbols/runtime.tsv` `Skill_default_slot11` 0x3c8690 | tier 2 absent when its first level "is 0xffff" | the test is the sign: any negative first level means "use tier 1"; the constructors store −1 (**executed**) | 0x3c86d4–0x3c86d8 (a signed halfword load, then `bltz`) | code |
| 45 | `spec/skills-01-34.md`, section 7 and the status table; `symbols/skills.tsv` `FireStorm_ctor2` 0x2d4048 | "argument order of the second constructor only as far as the stored fields" | (object, owner, position, radius, damage, duration in frames, flare period; flare scale); variant word 1 = straight flares, no looping sound (**executed**) | `spec/skills-01-34-executed.md` section 3, row 4 | report |
| 46 | `spec/skills-01-34.md`, section 24, Poison Rain | three statistic reads in the constructor | four: the duration is read again for the light's last number (**executed**) | `spec/skills-01-34-executed.md` section 3, row 5 | report |
| 47 | `spec/skills-01-34.md`, section 31, Root cast | "attach new SpellRoot …; count += 1" | when `pool_new` gives nothing, `creature_addSpell` is still called with 0 and the count still rises; the level goes through slot 14 first (**executed**) | 0x2e6700–0x2e672c (the null test skips only the constructor) | code (the call order); slot 14 and the count from the report |
| 48 | `spec/skills-01-34.md`, section 33, Critical Hit | `return level ? slot10(0, level) × 0.01 : 0` | the level goes through slot 14 (level, 20) first; ranks asked in the order 53, 81, 33 (**executed**) | `spec/skills-01-34-executed.md` section 3, row 7 | report |
| 49 | `spec/skills-01-34.md`, section 12, weapon buffs | one level for all constructor reads | the first duration read uses the level argument as passed, every later one the signed level byte of the spell; they differ above level 127 (**executed**) | `spec/skills-01-34-executed.md` section 3, row 8 | report |
| 50 | `spec/skills-01-34.md`, section 15, Undead Shield | "if o carries neither …" | both look-ups are always made (**executed**) | 0x2eadb8–0x2eade8 (two type-info calls and two list walks before either branch) | code |
| 51 | `skills.md`, Spell layout | (not stated) | the light fields left by `FireStorm` (+0x70, +0x78) and `SpellUndeadShield` (+0x40, +0x48) hold 0x7fffffff, computed as 1 / (0 × 0); the decompile shows the IEEE infinity as a constant (**executed**) | `spec/skills-01-34-executed.md` section 3, row 10 | report |
| 52 | `spec/skills-35-68.md`, section 68, timing table | run calls 61, 121, 181, 241 for 1–4 s and 721 for 12 s; respawn call 47, 107, 167, 227 | 60 N for every N; respawn on call 60 N − 14; the old figures were the round-to-nearest ones (**executed**) | `spec/skills-35-68-executed.md` sections 3 and 5 | report |
| 53 | `spec/skills-35-68.md`, section 54, lifetime | "600th for 10 s, 660th for 11 s" | 601st and 661st: 60 N + 1 for N from 10 to 20 (**executed**) | `spec/skills-35-68-executed.md` sections 3 and 5 | report |
| 54 | `spec/skills-35-68.md`, section 53, duration | both variants given | the truncating one: 720 and 780 for 12 and 13 s (**executed**) | `spec/skills-35-68-executed.md` sections 3 and 5 | report |
| 55 | `spec/skills-35-68.md`, sections 43, 44, 45, 47 | "lifetime 600 moving frames"; range "600 x speed / 60" | the age test follows the move, so an arrow that meets nothing has moved 601 times: range 601 steps (**executed**) | 0x2d66f8 (the move), 0x2d6724 (the compare with 601 behind it) | code (FireArrow); the other three from the report |
| 56 | `spec/skills-35-68.md`, section 41, wind-down | "clip2.event1.mask (clip2+0x28) …; clip2.event1.time (clip2+0x24)" | the offsets are right, the name is not: that is event slot 2 (**executed**) | 0x2d1d04, 0x2d1d0c (the two stores) | code (the stores); the slot numbering from the report |
| 57 | `spec/skills-35-68.md`, sections 42, 49, 54, 62 | the sample point is "draw mod n" | n is the model's point count and is not tested: a divide by zero for a model without sample points (**executed**) | 0x3086b8 (a `div` whose divisor is the count) | code (that one divide); the missing test and the other three sites from the report |
| 58 | `spec/skills-35-68.md`, section 68, "not determined" | the allocation-failure path of `player_respawn` | adds the spell's side: the run stores the tint through the target pointer with no null test, and re-reads the pointer after the respawn (**executed**) | `spec/skills-35-68-executed.md` section 5 | report |
| 59 | `spec/skills-35-68.md`, S.1 | "identical bodies apart from the text key" | the five keys given; nothing else differs (**executed**) | `spec/skills-35-68-executed.md` section 5 | report |
| 60 | `spec/skills-35-68.md`, 1.8 | the two timer rules and eleven tier-2 differences, computed | confirmed exactly by execution | `spec/skills-35-68-executed.md` section 3 | report (a confirmation) |
| 61 | `spec/skills-35-68.md`, section 41, "Per-machine state"; `skills.md`, cast path | "the shared-clip condition is **Inferred** …; not tested" | executed (9 of 9 cases) and **Ran**: 6 of 6 same-class pairs diverged, 0 of 6 with the patch | `spec/skills-35-68-executed.md` section 4; `issues/live-rig.md` 9.4; FINDINGS SB1, V19 | running game |
| 62 | `spec/skills-69-101.md`, sections 72 / 75 | "quantity (+4)"; that it survives the parser Inferred | the quantity is a halfword; the halfword at +6 is never written by the constructor; the Inferred stands (**executed**) | `spec/skills-69-101-executed.md`, correction 1 | report |
| 63 | `spec/skills-69-101.md`, section 76, event 2 | `water_test(8.0, world, centre)` | asked with the ground height just found as z (**executed**) | `spec/skills-69-101-executed.md`, correction 2 | report |
| 64 | `spec/skills-69-101.md`, section 76 and the draw table | no draws while an interrupted spell lingers | one own draw a frame and a second below 0.170987 (**executed**) | `spec/skills-69-101-executed.md`, correction 3 | report |
| 65 | `spec/skills-69-101.md`, section 77 and the draw table | (not listed) | an interrupted spell lays ten pairs of a second kind of streamer every frame and clears the streamer flag; a ground particle is drawn for always and spawned only within 72 of the copy's height (**executed**) | `spec/skills-69-101-executed.md`, corrections 4 and 5 | report |
| 66 | `spec/skills-69-101.md`, storm layout, +0x7c | "fall time 48.990772 frames [0x4243f68d]" as a stored constant | computed at run time as the square root of 2400.096 (**executed**) | 0x30b14c (the word 0x46040104, `sqrt.s`) | code |
| 67 | `spec/skills-69-101.md`, section 90, `SpellSummonBadger` run | "particles on the badger's model sample points (own generator)" | the points are the fixed sequence 0, 8, 16, …; the generator supplies only the ball point; an empty handle destroys the spell, a handle without an object only returns (**executed**) | `spec/skills-69-101-executed.md`, correction 7 | report |
| 68 | `spec/skills-69-101.md`, statistic lookup; `skills.md`, slot 8; `symbols/runtime.tsv` `Skill_default_slot8` 0x3c82e4 | "two shared draws per bound"; "each bound advances the shared generator twice" | adds: the first only chooses the direction of the rounding, the second sets the value (**executed**) | `spec/skills-69-101-executed.md`, correction 8 | report |
| 69 | `spec/skills-69-101.md`, section 70 | (not stated) | the particle step is a division with no zero test; at level 0 the divisor is 0 and the quotient unused (**executed**) | 0x2fd9b8 (the `div`) | code (the divide); the missing test from the report |
| 70 | `spec/skills-69-101.md`, sections 81, 85, 86 | class behaviour | confirmed, with additions: Critical Hit's light unlinked after 2.0 s, and two reads of alive-list players without a null test; Healing's association; Root's two cleared lists and unused draws (**executed**) | `spec/skills-69-101-executed.md`, correction 10 and "Per-machine state" | report |
| 71 | `skills.md`, slot 5 | "or 0 for passives" | only Dodge's own function returns 0; the default, which the other passives and Riposte use, returns 1.0 (**executed**) | 0x3c82a8–0x3c82b0 (the constant 0x3f800000 returned) | code |
| 72 | `issues/arena-desync.md`, head | "**Result of 2026-10-10: the arena desync was not reproduced on the running game**" as the document's live result | a new dated part in front of it, "What the live rig showed": with real characters the arena does diverge — 3 of 12 fights with K1, K2 and LAG-1 on, 7 of 12 without — with the causes seen (K1 / K2; a pet touched by its owner's prediction copy; stale bytes in a picked-up item; the spin skill for two same-class players), the float result and the knights; and 2 of 12, both silent, none flagged, with the spin and touch sections on as well | `issues/live-rig.md` 9.2–9.4, 8.3, 10.3; FINDINGS V15, V17–V23, G25, SB1, D25 | running game |
| 73 | `issues/arena-desync.md`, the earlier result | "an arena fight between two machines that compute identically stays in sync"; the search "moves … to what the set-up did not contain" | kept under "Earlier result: placeholder characters" and followed by what overturned it and which of the missing things have been run since | `issues/live-rig.md` section 9 | running game |
| 74 | `issues/arena-desync.md`, "Result in one table" and "Ranked list" | "If the arena goes out of sync with no player death, no resurrection … the cause is not on this list" | that is what happened; a paragraph ranks what was seen above the five candidates, none of which was seen | `issues/live-rig.md` 9.2, 9.3 | running game |
| 75 | `issues/arena-desync.md`, summon table, "Prediction copy"; `creatures.md`, slot 6 row; `symbols/creatures.tsv` `Creature_onTouch` 0x11a418 | "Monsters do not run during prediction; box queries skip the copy"; "a player touching sets cflag bit 59" | adds the route missed: the touch handler flags a creature for any toucher with the player flag, the copy included, the call coming from `Creature_moveBy`; `Creature_run` acts on it only for a creature in state 0 or 5 with a non-zero charm timer — a pet or a charmed monster, not the knights or their skeleton | 0x11a418–0x11a43c (only 0x40 is tested); 0x113b48–0x113b64 (state 0 or 5, charm timer), 0x113b74–0x113bc0 (set-state 1, the bit cleared); 0x114220 (the unguarded call); `issues/live-rig.md` 9.2, 10.1; FINDINGS G25, V18, V22 | running game; the setter, the reader and the call site also code |
| 76 | `issues/arena-desync.md`, "What to record on two machines", "Test patches", "Not done" | "the message never appeared"; the last cutscene and the avatar fight "not reported as reached" | a later note: ten divergent pairs in 24 fights, all "none of the five"; nine fights won; T1 and T3–T5 still not run; `hideMonster` does hide all four | `issues/live-rig.md` 9.2, 9.3, 8.5 | running game |
| 77 | `issues/arena-entry.md`, head, "Result in short", the recording note | the twelve runs with placeholder characters as the live result; "there was no M" | a new dated part: the arena does diverge with real characters, every time after E by the tick numbers (Inferred from them); the float mismatch fails before S; the level's knights and later timing | `issues/live-rig.md` 9.2, 9.3, 8.3 | running game |
| 78 | `issues/arena-entry.md`, E6, X1 and "Test patches (all untested)" | the copy "cannot reach shared state" resting on the G-series audit; "X1–X4 were not used" | the audit is incomplete in two places (rows 79–81); what that means during the cutscene (Inferred); X1 has been used once, on the pet pair, and removed the divergence | `issues/live-rig.md` 9.2; FINDINGS V18 | running game; the cutscene reasoning is this pass's and Inferred |
| 79 | `issues/prediction-copy.md`, head and section 1 | "what the copy can change in shared state needs a second machine to show"; the virtual calls: "None changes shared state" | a dated result: the copy reaches shared state by two routes the audit did not have; the bullet says where it is overturned | `issues/live-rig.md` section 9; FINDINGS G25, SB1, V18, V19 | running game |
| 80 | `issues/prediction-copy.md`, 3.2 (the move row, the skill-cast row) and a new 3.5 | "The other object's slot 6 is skipped for the copy"; Cyclone's constructor "tests the owner's 0x20000 … and for the copy skips …" | 3.5 has both routes step by step — setter, reader, who is affected, what was seen, the control, the caller, the fix, what is not known — and a third trace, the item bytes; the two rows say what they missed, and two more rows (the scripted walk of 3.1, the knock-back of 3.2), which had concluded that the copy does not go through `Creature_moveBy`, are marked overturned: the running game entered the touch handler from its call at 0x114220 with the copy as toucher 164 times. The guard of the move row is sound for its own function | 0x11a418–0x11a43c; 0x113b48–0x113bc0; 0x2d1978, 0x2d197c in front of 0x2d19c4–0x2d19d0; 0x14d7dc, 0x14d938, 0x14d984 (the register the guard at 0x14d9b0 tests is the mover's flag word on every path); 0x114200–0x114224 (`Creature_moveBy`: the touched object's slot 6 called with the mover, no test); `issues/live-rig.md` 9.2, 9.4, 10.1, 10.2; FINDINGS V22, V23 | running game; the five code sites also code |
| 81 | `issues/prediction-copy.md`, new 5.6, the ranking of section 7, sections 8 and 9; `symbols/skills.tsv` `SpellCyclone_ctor` 0x2d17c8 | six ranked leaks; "every patch below is untested" | the two test patches that exist for the routes and their status (both **Ran** on the linked pair and remove their divergence; with them and K1, K2, LAG-1 on, 2 of 12 arena pairs differ, silently, and none is flagged); three rows added to the ranking; "not done" items for the caller of `Creature_moveBy` and the source of the item value | the patch file (read, not edited): sections "predicted spin cast leaves the shared animation alone" and "creatures ignore being touched by the prediction copy"; `issues/live-rig.md` 9.4, 10.1, 10.3; FINDINGS V19, V21, V22 | running game; the patch words read |
| 82 | `issues/float-divergence.md`, head, result table, stick decoder, "Reading the table", advice, proposed row D25, "Not done" | "no two machines or settings have been compared"; a mismatch "would normally drift in every level, and the arena … is where it would show"; "how quickly is **Unknown**" | a dated result with its table: positions differ on the first tick of movement and the out-of-sync flag follows in 7–113 ticks, in the first level; with no input nothing shared differs; so a machine-wide mismatch is not an arena cause, and a float cause would have to be confined to particular operations (not tested) | `issues/live-rig.md` 8.3; FINDINGS V15, F9 | running game |
| 83 | `issues/lag.md`, head, the Model marker, 5.2, sections 9, 10, 11, 12 | "The pacing rules … have not [been seen]: they need two machines, the rig has one"; "No test patch has been run on a live game"; "**All untested**" | the outage case and LAG-1 measured on two linked machines: lead 6 → 34 and about 35 s to drain; with LAG-1 a peak of 11 and normal within 10 s — the model's figures; what is still Model only | `issues/live-rig.md` 8.4; FINDINGS V16, L11, L12 | running game |
| 84 | `issues/kill-loot-xp.md`, head, the paragraph under the result table, K1 verdict, ranked list, the recording note | K1 and K2 tripped "neither in twelve arena runs"; in `drunare` K1 "a silent bag difference" (Inferred); "None of these happens on every run" | with real characters and no patches, bag differences of the K1 / K2 kind in 5 of 12 arena fights, one followed 96 ticks later by the out-of-sync flag; none with the sections on | `issues/live-rig.md` 9.3; FINDINGS V17 | running game |
| 85 | `issues/kill-loot-xp.md`, section 4 and item 8 of the ranked list | "computed by every machine from shared state" | adds what was seen: the same item picked up in the same tick with one unwritten 16-bit field differing between the machines; silent. Traced since: made at loot creation, 191 ticks before the pick-up; gone without the prediction copy; not a leftover of the parser's output record; no reader found — the two candidates the first note named are out | `issues/live-rig.md` 9.2, 10.2 (pairs 402, 410); FINDINGS V20, V23, I1 | running game |
| 86 | `issues/draw-sim-leaks.md`, head, "K1, K2", "Ranking", "Not done" | "neither is needed for, nor produced by, a fight as such"; "with the mechanism available and unpatched the arena stayed in sync"; the stall "cannot happen on the rig at all" | each kept and followed by what overturned it: 5 of 12 unpatched fights; 3 of 12 patched, from causes that are not of this document's kind; an outage imposed on the bus gave a lead of 34; what the unattended runs reached and did not (U1, U2); with every section on, only the silent item bytes remain | `issues/live-rig.md` 8.2, 8.4, 9.2, 9.3, 10.3; FINDINGS V14, V16, V17, V21 | running game |
| 87 | `online-setup.md`, head, "Settings every player must match", "Not checked" | "they stay in sync under ordinary play"; "Of this list only the K1 and K2 item has been seen on a running game"; "the only divergences found were K1 and K2"; rows "V1–V13" | four sentences made true: with real characters the arena diverges even with the K1 and K2 patches; the arithmetic item has been seen too (forced rounding mode); with the whole patch set on, no fight is flagged and two keep a silent two-byte difference; rows V1–V23. (Another contributor updated the patch table of the same page for V21 and V22 while this pass was running; those lines were left as found) | `issues/live-rig.md` sections 8–10 | running game |

### X1. Summary

| | Count |
|---|---|
| Rows in table X2 | 87 |
| … corrections applied | 87 |
| … from the running game (**Ran**, `live-rig.md` sections 8 and 9) | 17 (rows 61, 72–87); rows 75 and 80 were also read in the code |
| … re-checked against the code, wholly or for the part named | 23 (rows 2–4, 9, 12, 14, 15, 18, 23, 24, 30, 31, 42–44, 47, 50, 55–57, 66, 69, 71) |
| … taken from the reporting document | 47 (rows 1, 5–8, 10, 11, 13, 16, 17, 19–22, 25–29, 32–41, 45, 46, 48, 49, 51–54, 58–60, 62–65, 67, 68, 70) |
| … whose corrected statement is, wholly or in part, an executed result of the reporting document | 70 (rows 1–71 except 41) |
| Reported corrections found wrong | 0 |
| Reported corrections applied in a different place or form (X4) | 7 |
| Reported items not applied (X4) | 8 |
| Symbols renamed / symbol notes changed | 0 / 18 |

`python3 -I -B tools/symtab.py check` after the edits: 5817 symbols, 0 conflicts, 0
malformed lines.

Where each group of rows came from: arena monsters 1–13; game messages 14–22; script
built-ins 23–41; skills 1–34, 42–51; skills 35–68, 52–61; skills 69–101, 62–71; live rig,
phases 3 and 4, 72–87.

### X3. Symbol files

No address or name was changed. Notes changed, all to match a row of X2:

| File | Symbol | Row |
|---|---|---|
| `symbols/monsters.tsv` | `Horsemen_setState` 0x272f4c | 4 |
| `symbols/creatures.tsv` | `Creature_isTargetCharging` 0x118f90, `Creature_onTouch` 0x11a418, `Creature_moveBy` 0x113c48 | 9, 75, 80 |
| `symbols/ui.tsv` | `hudmsg_sendLoadLevel` 0x1de598, `hud_onMsg` 0x1d8ca0, `hud_onQuickCastWarn` 0x1de340, `hudmsg_sendQuickCastWarn` 0x1de0a4 | 14, 15 |
| `symbols/ui.tsv` | `inventory_dropItem` 0x1c4310, `inventory_combineGems` 0x1ceeb8, `shop_buy` 0x1d1240 | 16, 17, 18 |
| `symbols/ui.tsv` | `quest_add` 0x1d386c, `quest_remove` 0x1d3968 | 24, 25 |
| `symbols/script.tsv` | `scr_getAddr` 0x1414a8 | 23 |
| `symbols/runtime.tsv` | `Skill_default_slot11` 0x3c8690, `Skill_default_slot8` 0x3c82e4 | 44, 68 |
| `symbols/skills.tsv` | `FireStorm_ctor2` 0x2d4048, `SpellCyclone_ctor` 0x2d17c8 | 45, 81 |

Two notes were wrong rather than short: `Creature_isTargetCharging` ("target faces this
creature") and `quest_add` ("every player's quest list"); `inventory_dropItem` named its
fourth argument "count". `Skill_default_slot5` 0x3c82a8 already said "returns the float
1.0" and was left.

### X4. Applied differently, not applied, and noticed while editing

No reported correction was found to be wrong against the code. Seven were applied in a
different place or form than reported:

1. **"Three mounted knights" (arena monsters, item 1; the hand-over names
   `issues/arena-desync.md` and `issues/arena-entry.md`).** Neither document, and no other
   document of the repository, says three or mounted — the reporting document says so
   itself: the phrase is from the brief of that work. `arena-desync.md` already had four
   `UndeadKnight1`…`4`. Applied as two clarifications (row 13): "on foot", and that the
   document's "knight 3" is the variant number, object type `UndeadKnight4`.
2. **`Creature_isTargetCharging` (arena monsters, item 11; the hand-over names
   `creatures.md`).** `creatures.md` only listed the address. The wrong definitions were in
   `symbols/creatures.tsv` and at one place in `monsters-2.md`; all three, and the
   Horsemen paragraph of `monsters.md`, now carry the coded rule (row 9). The other thirty
   uses of the word "charging" in `monsters-2.md` describe what each class does with the
   answer and were left.
3. **State 1 "leave to 3 with a target" (arena monsters, item 4).** `monsters.md` 1.4 has
   that phrase in the row of state 0, not of state 1, whose row gave no exit. Applied in
   the row of state 1 (row 3).
4. **Game message 11 and 13 (game messages).** Reported against `ui.md`; `netcode.md` has
   its own message table with the same two entries, and both were corrected (rows 14, 15).
5. **Inventory message 0 (game messages).** Shop message 1 in `ui.md` repeats the layout
   and was corrected with it (row 16).
6. **Script built-ins.** The hand-over list had seven of them; section 9 of the reporting
   document has eighteen rows with content, and all were applied (rows 23–40).
7. **Skills, "mark each corrected statement executed".** Where the statement sits inside
   a block of the specification's own pseudo-code, the correction is a comment in that
   block beside the line it corrects, and the line itself was changed only where it was
   wrong (the soul velocity, the tier-2 test, the event-slot name, the timing table of
   section 68, whose old figures are kept in the paragraph under it).

Rows that go beyond the hand-over list but come from the same sections: 5–8 (arena
monsters items 6–8 and the unstated Zek facts), 19 (shop message 0), 41 (a pointer at the
head of `script.md`), 59 and 60 (a confirmation and the five text keys), 70 (the class
sections 81, 85, 86), and in rows 61, 75 and 81 the notes in `skills.md`,
`spec/skills-35-68.md`, `creatures.md` and two symbol files that say what the running
game showed for SB1 and G25, so that the statement and its live result are found
together.

Not applied:

- **`docs/issues/live-rig.md` 7.3 (game messages).** The reporting document asks for the
  same correction there as in `kill-loot-xp.md` K2 — what the stray drop message removes
  depends on the owner's slot. `live-rig.md` is another agent's document and was not
  edited. X5.
- **Every proposed ledger row** and every amendment of an existing one. X5. (M1–M5,
  N1–N8, X17–X22, V14–V20, G25 and SB1 were found on the ledger already.)
- **Proposed names for unnamed addresses**: `particle_define` 0x18f118 and
  `profile_append` 0x222a44 (`spec/script-builtins.md` section 11), the grid builder
  0x1cbbe8 (`itemGrid_build`), the load-level handler body 0x18cb80 and the empty shop
  helper 0x1bf5a0 (`spec/game-messages.md` section 12). New symbols, not corrections; this
  pass has no symbol file of its own.
- **The lists of "confirmed as written"** in the three skill companions and in
  `spec/arena-monsters.md` section 14 items 9 and 10. Confirmations of statements that
  stand; the specifications were not marked up sentence by sentence. Rows 10, 60 and 70
  are the exceptions, where the confirmation answers a "not traced" or comes with an
  addition.
- **`docs/skills.md` from the skills 35–68 companion.** It reports "no new correction".
- **The shared state table of `monsters.md` 1.4 for states 0x12 and 0x13.** The executed
  classes differ from it (a knight leaves 0x13 to 3, the skeleton to 0 and ignores 0x12);
  the table says "State numbers are per class", so the differences are recorded in the
  class sections (rows 3, 6) and the table's other rows were left.
- **The sentence "no test patch has been run on a live game" and "rows V1–V8" / "V1–V13"
  at the head of other documents.** Still the item the fifth pass left open, and further
  out of date now: four test sections have been run on the linked pair (K1, K2, LAG-1 and
  the spin patch) and one diagnostic (no prediction copy), and the live rows go to V20.
  This pass changed it in the eight documents of its live work list only; `script.md`,
  whose head was touched for another reason (row 41), still has it. 33 documents still
  carry one of those phrases (the search is the first line of X6; this file and `lag.md`,
  where the phrase is now followed by its correction, are the 34th and 35th hits).
- **Patch words for the two prediction-copy routes.** `prediction-copy.md` 5.6 describes
  the two patch-file sections and points at `live-rig.md` 9.4 for the words; it does not
  repeat them as a proposal table, because they are not proposals of that document and
  `patches/` is not this pass's to restate.

Noticed while editing, not reported by anyone:

- **The reader of the touched bit has two conditions the ledger row does not give.**
  FINDINGS G25 says `Creature_run` "calls set-state 1 unless the creature is dead" and
  clears the bit. The block is entered only in state 0 or 5 and only with a non-zero charm
  timer +0x312 (0x113b48–0x113b64); otherwise it is skipped whole, the clearing included
  (`spec/creature-tick.md` 4.13 has the two conditions). That is why the divergence showed
  on a pet and why the arena's knights are not exposed; and it means a creature without a
  charm timer keeps the bit, set on one machine only, with no reader found. The edited
  documents state it; the ledger row should (X5).
- **The guard in `obj_moveWithCollision` is sound.** G25 says the guard at 0x14d9b0 "does
  not cover" the route. Read here: the register it tests is the mover's flag word on every
  path into it (loaded at 0x14d7dc, reloaded after the slide at 0x14d938 or 0x14d984), so
  that function does not call another object's slot 6 for a copy. The caller that does is
  `Creature_moveBy`, whose slot-6 call at 0x114220 has no test — read here as the nearest
  candidate and confirmed by the running game while this pass was being written (V22).
  That overturns two rows of `prediction-copy.md` which had concluded that the copy never
  runs `Creature_moveBy` (the scripted walk "not reachable", the knock-back "returns at
  once for any player in a net game"); both are marked. How the copy gets there is still
  open: one of those two readings is wrong, or there is a third caller.
- **Two wordings about the pet pair differ.** FINDINGS V18 has the bit "set 60 ticks
  before anything else differed"; `live-rig.md` 9.2 has the flag word differing from tick
  7481, the pet's animation from 7523, its position from 7524 and the shared seed at 7541.
  So 60 ticks is to the first *shared* value; the pet's own animation differed after 42.
  The documents edited here say "before the first logged shared value differed".
- **`issues/arena-entry.md`, E6.** With the two new routes the question "can an un-frozen
  copy reach shared state during the cutscene" is open again in one place: a copy that
  casts the spin within its 30 ticks after S resets the shared clip slot while another
  same-class player is frozen in mid-spin. Written there as Inferred; not run.
- **`issues/lag.md` and `draw-sim-leaks.md` described the outage as something the rig
  cannot do.** It cannot stall a machine, but the bus between the machines can drop
  everything for a chosen number of frames, which is how V16 was measured. Both documents
  now say so.
- **`issues/kill-loot-xp.md`, "The chain itself is lockstep".** V20 is the first observed
  exception inside the chain, and it is not a branch: the same item, the same tick, the
  same cell, different bytes. V23 moves it from the pick-up step to the loot step and
  ties it to the prediction copy; the first note written in this pass had guessed "an
  unused field never initialised when the loot is made", which the record-clearing test
  shows is not the whole of it. The unwritten halfword at +6 of the summoned axe and arrow
  records (row 62, proposed row SC12) is the same kind of thing found by execution; the
  two are cross-referenced in `spec/skills-69-101.md`.
- `spec/arena-monsters.md` writes the event of state 10's clip as "bit 1" in section 14
  and as "bit 2" in the table of 3.3; the test is `ev & 2` in both. Row 1 uses "event
  bit 1", as `monsters.md` did.

### X5. For the owners of files this pass does not edit

`FINDINGS.md`:

| Row | What it needs |
|---|---|
| G25 | The reader's conditions: `Creature_run` acts on the bit only in state 0 or 5 with a non-zero charm timer +0x312 (0x113b48–0x113b64), and skips the clearing otherwise — so the creatures exposed are pets and charmed monsters, and any other creature keeps a per-machine bit that nothing reads. The row was amended with V22 while this pass ran and now names `Creature_moveBy`; it still carries, in front of that, "has not been identified" and "the guard … does not cover it" — the guard itself is sound (the mover's flag word on every path: 0x14d7dc, 0x14d938, 0x14d984) |
| G16 and `prediction-copy.md` rows it rests on | "nothing calls its take-damage slot" stands, but the audit behind the G rows had the copy never running `Creature_moveBy`; V22 shows it does. Worth a row of its own: by which caller, and which other slot-6 handlers that call can reach with the copy as the mover (`live-rig.md` 10.4) |
| V18 | "set 60 ticks before anything else differed": before the first shared value (the seed, tick 7541); the pet's animation differed from tick 7523 and its position from 7524 (`live-rig.md` 9.2) |
| D17 | "300 frames after the fourth knight … a message at 250 and the ending at a count of 1500 — reached after about 875 frames": exactly the 302nd counted frame, count 252, and 877 frames, because `getScaledTime(n)` is `int((n × 60.0) × 0x3c888888)` = n − 1 (0x14412c); "multiplies by 60 × 1/60" hides the truncation that makes it so |
| F9 | The status column still reads "Inferred (emulator behaviour from general knowledge, nothing run)" while the text now cites the run of V15; the mismatch case is **Ran** |
| K8 | Could add from `spec/arena-monsters.md` 3.4: the lookup of the skeleton is by name only, so it returns whatever object holds that name whoever summoned it; and a mounted knight ignores set-state 0x14 altogether |
| E6 | The copy "is on no run list, so a flag-8 cutscene neither freezes nor unfreezes it": with G25 and SB1 the un-frozen copy has two routes to shared state; during the cutscene the first looks closed (frozen creatures are off the grid), the second is not (`arena-entry.md` E6, Inferred). X1 was run once (V18) |
| G16, G23 | Both end in "none can change shared state" / "nothing can damage the copy"; true as worded, but written before G25 and SB1 — a cross-reference would keep them from being read as "the copy is contained" |
| I1 | The Summon Axe / Summon Arrows constructors hand the inventory an item record whose halfword at +6 they never write (0x2feb88, 0x2ff87c; `spec/skills-69-101-executed.md`, proposed SC12, not on the ledger). I1 has +0x06 as a byte "the parser never writes"; this is the same field seen from the caller, with a value that differed between two runs of the test |
| K1, K2, D25, V17 | Checked, nothing needed: they carry the 5-of-12 figure and M1 |
| proposed rows, and reported facts, that have no ledger row | `spec/skills-69-101-executed.md`: SC12 (above). SC11 is covered by the sentence added to SA5, and SC10 by X22. `spec/skills-35-68-executed.md`: the unchecked divide by the sample-point count at 0x3086b8 and three sibling sites (a divide by zero for a model without sample points; whether such a model exists is disc data) has no row. `spec/skills-01-34-executed.md` row 6: a failed `pool_new` in the Root cast still uses up a target (0x2e6700–0x2e6728) — a D21-family consequence with no row. `spec/arena-monsters.md` 3.4: `Horsemen_setState` stores an unknown state number after a nested set-state 3 |

Rows checked and found already amended: D22 (four knights on foot), D25, D41 (Zek), SA5,
SB1, I1 (V20, V23), K2 (M1), L11, L12, E4, V13–V23, M1–M5, N1–N8, X17–X22.

`names.tsv` — no line is wrong; these are short and could carry what was learned:

| Row | What it could add |
|---|---|
| 0x14412c `script_getScaledTime` | returns `int((n × 60.0) × 0x3c888888)`: n − 1 for the counts scripts reach |
| 0x1464e8 `script_playGotItemSound` | stores the active player clamped to 0..1 but plays the voice for the unclamped slot (N8) |
| 0x143720 `script_lightEffect` | twelve arguments; the second is used (× 0.01) |
| 0x1458e0 `script_clearAllSkills` | sets record +0x4a85 to 1 while clearing +0x4a80 and +0x4a84 |
| 0x1433c8 `script_addQuest` | `quest_add` stops at the first player whose list is full or has the title (N2) |
| 0x112948 `Creature_run` | acts on the "touched by a player" bit 59 for a creature in state 0 or 5 with a non-zero charm timer (0x113b48) — the reader of G25 |
| 0x27236c `Horsemen_run` | state 1 leaves to 0 on sight; state 10 is the one-third hit only |
| 0x2c2440 `Zek_run` | returns right after the activity test when inactive, the ground wave included (D41) |

`docs/issues/live-rig.md` (another agent's): 7.3 should say, as `kill-loot-xp.md` K2 now
does, that what the stray drop message removes depends on the owner's slot (M1) — in the
scripted run the owner was in slot 1, so the potions were not touched by it.

`docs/` as a whole: the head sentences of the fourth pass's sweep (the item of "Not
applied" above).

### X6. Re-checking

```
grep -rln 'o test patch has been run\|V1–V8\|V1–V13' docs/        # documents still carrying a head sentence of the fourth pass
python3 -I -B tools/symtab.py check                               # 0 conflicts, 0 malformed
python3 -I -B tools/dis.py SLUS_209.73 118f90:119038              # isTargetCharging: bearing creature -> target against the target's facing; 100.0
grep -n 'case 1:' -A 9 decomp/all/0027236c.c                      # Horsemen_run state 1: seen -> LAB_00272eec, which sets state 0
grep -n '0x3c\|FUN_00119258\|FUN_00118f08' decomp/all/0027236c.c  # state 5: blocked test, remainder by 60, allies near the target
sed -n '18,28p' decomp/all/00272f4c.c; tail -9 decomp/all/00272f4c.c   # Horsemen_setState: mounted return; default stores the requested state
python3 -I -B tools/dis.py SLUS_209.73 14412c:144160              # getScaledTime: n x 60.0 x 0x3c888888, truncated
python3 -I -B tools/dis.py SLUS_209.73 1de5a0:1de5dc              # message 11: length 4, the name left out
python3 -I -B tools/dis.py SLUS_209.73 18dd4c:18dd78              # net game -> sendNewWorld, offline -> sendLoadLevel
python3 -I -B tools/dis.py SLUS_209.73 1de340:1de3ec              # message 13: +0x488 queued for a kind other than 1
python3 -I -B tools/dis.py SLUS_209.73 1d12f8:1d1314              # shop_buy: gold stored in the delay slot of the give call
python3 -I -B tools/dis.py SLUS_209.73 1414a8:1414f4              # scr_getAddr: no store on the error-5 path
python3 -I -B tools/dis.py SLUS_209.73 1d38bc:1d3968              # quest_add: both tests leave the function
python3 -I -B tools/dis.py SLUS_209.73 145948:145964              # clearAllSkills: +0x4a85 stored from a register, +0x4a80 / +0x4a84 zeroed
python3 -I -B tools/dis.py SLUS_209.73 1421fc:142214              # getManaUsed / getHealthUsed: lh
python3 -I -B tools/dis.py SLUS_209.73 1433bc:1433c8              # helpMessageActive: lb
python3 -I -B tools/dis.py SLUS_209.73 2f4d8c:2f4ddc              # Repulse Undead: 0x43e10000 times cos and sin
python3 -I -B tools/dis.py SLUS_209.73 150c10:150c30              # water splash: a draw, then the constant 1 into the name format
python3 -I -B tools/dis.py SLUS_209.73 3c86d0:3c86dc              # slot 11: lh, bltz
python3 -I -B tools/dis.py SLUS_209.73 3c82a8:3c82b8              # default slot 5 returns 1.0
python3 -I -B tools/dis.py SLUS_209.73 2e6700:2e6730              # Root cast: null block skips only the constructor
python3 -I -B tools/dis.py SLUS_209.73 2eadb0:2eadf0 | grep jal   # Undead Shield: both look-ups before either branch
python3 -I -B tools/dis.py SLUS_209.73 2d66f0:2d6730              # FireArrow run: move, then age against 601
python3 -I -B tools/dis.py SLUS_209.73 2d1cfc:2d1d10              # Cyclone wind-down: stores at clip +0x28 and +0x24
python3 -I -B tools/dis.py SLUS_209.73 3086a8:3086c0              # StrongStance trigger: div by the sample-point count
python3 -I -B tools/dis.py SLUS_209.73 2fd9a8:2fd9c0              # Unspoken Word: div for the particle step
python3 -I -B -c "import sys; sys.path.insert(0,'tools'); from ps2elf import Elf; e=Elf('SLUS_209.73'); print('%08x' % e.u32(0x30b14c))"   # 46040104 = sqrt.s
python3 -I -B tools/dis.py SLUS_209.73 11a418:11a444              # Creature_onTouch: only 0x40 tested; bit 59 set
python3 -I -B tools/dis.py SLUS_209.73 113b48:113bc8              # Creature_run: state 0 or 5, charm timer, bit 59 -> set-state 1, bit cleared
python3 -I -B tools/dis.py SLUS_209.73 2d1970:2d1984              # SpellCyclone_ctor: the two clip-header stores
python3 -I -B tools/dis.py SLUS_209.73 2d19c0:2d19d8              # … and the copy test that comes after them
python3 -I -B tools/dis.py SLUS_209.73 14d7d8:14d7f0              # obj_moveWithCollision: $6 = the mover's flag word
python3 -I -B tools/dis.py SLUS_209.73 14d930:14d9f4              # … reloaded after the slide; guard at 0x14d9b0; the two slot-6 calls
python3 -I -B tools/dis.py SLUS_209.73 114200:114228              # Creature_moveBy: touched.slot6(mover) with no test (the caller of V22)
grep -n 'predicted spin cast\|touched by the prediction copy\|no prediction copy' patches/*.pnach   # the three patch-file sections named in rows 78, 80, 81
```
