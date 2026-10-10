# Corrections applied to the first-round area documents

Scope: the fifteen area documents `docs/{player,startup,creatures,monsters,skills,gameplay,
objects,runtime,engine,netcode,script,ui,audio-save,mainloop,netlib}.md` and the note
column of `symbols/*.tsv`. Later passes (`docs/data-tables.md`, `docs/issues/vtable-labels.md`,
`docs/monsters.md`, `docs/script.md`) reported errors in the first-round text; this pass
applied them, and then compared the documents with each other.

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
