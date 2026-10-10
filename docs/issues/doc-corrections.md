# Corrections applied to the first-round area documents

Scope: the fifteen area documents `docs/{player,startup,creatures,monsters,skills,gameplay,
objects,runtime,engine,netcode,script,ui,audio-save,mainloop,netlib}.md` and the note
column of `symbols/*.tsv`. Later passes (`docs/data-tables.md`, `docs/issues/vtable-labels.md`,
`docs/monsters.md`, `docs/script.md`) reported errors in the first-round text; this pass
applied them, and then compared the documents with each other.

A second pass, made after more reports had come in, is recorded at the end of this file
under "Second pass", and a third under "Third pass"; sections 1 to 7 describe the first
pass only.

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
