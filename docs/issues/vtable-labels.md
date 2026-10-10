# Virtual-table list: wrong labels, missing tables, wrong lengths

Scope: `tools/vtab.py`, `vtables.txt`, and the symbol names that were derived from them.
Everything below was read from the executable (SLUS_209.73); nothing was run on a console
or emulator. Statements are **Observed** unless marked **Inferred** or **Unknown**.
No patch and no `FINDINGS.md` row is proposed: this is a correction of the project's own
tables, not a finding about the game.

## 1. Summary

| | Before | Now |
|---|---|---|
| Lines in `vtables.txt` | 399 | 478 |
| Tables with a wrong class | 24 | 0 |
| Tables missing | 3 with type information, 76 without | 0 |
| Wrong lengths | 398 of 399 (395 one too long, 3 far too long) | 0 |
| Symbols renamed | | 11 rows in `symbols/gameplay.tsv`, `player.tsv`, `skills.tsv` |

The list in `docs/runtime.md` section 4.2 (24 mislabelled tables, 3 missing, SmokeGen
running on) was reproduced exactly; nothing in it had to be corrected. Two of its
explanations were incomplete, see section 2.

Slot numbers did not change. Slot *n* of a table is still the entry at table offset
*n* × 8, so every existing statement of the form "slot 4 of the table at 0x…" stays true.
What changed is which class a table is said to belong to, and where a table stops.

## 2. What was wrong

All four faults were reproduced with the old tool (its output was byte-identical to the old
`vtables.txt`) and with a separate script that does not share code with it (section 3.4).

| # | Fault | Cause in the old `tools/vtab.py` | Effect |
|---|---|---|---|
| 1 | Wrong class | The class was taken from the first class-name string found for the type-info getter. 26 getters also initialise the descriptors of their base classes inline, so they hold two or three names, and the first one found was a base | 24 tables labelled `WorldPart`, `Projectile`, `Prop` or `FireBeetle` |
| 2 | Getter rejected as too long | A getter longer than 0x100 bytes was ignored. The length came from the heuristic function table in `tools/ps2elf.py`, which did not see the unreferenced code that follows two getters: 0x3c1e28 was measured as 0x1a0 bytes and 0x3c22b0 as 0x130. Both are 0x9c bytes | `Weapon2` and `WeaponShield` missing |
| 3 | Getter cut short | The same function table treats any data word that looks like a code address as a function start. The value 0x003d0000 occurs as data at 0x3ea5a8, 0x55e3cc and 0x55f23c, so the getter at 0x3cffd4 (0x50 bytes) was cut at 0x3d0000, before its name reference | `PoisonRain` missing |
| 4 | Table end | Entries were read through single null entries until two nulls in a row, then cut at the next *recognised* header minus one entry | every count included the null terminator; a table followed by an unrecognised one swallowed it |

Fault 4 in numbers:

| Table | Old count | Real | What the old count contained |
|---|---|---|---|
| 395 tables | n + 1 | n | the functions and the null terminator |
| `Creature` 0x50cc58 | 92 | 39 | 39 + null + the whole `WeaponShield` table (header, 24, null) + the whole `Weapon2` table (header, 24, null) |
| `SkillLifeTap` 0x51a9e0 | 34 | 15 | 15 + null + the whole `PoisonRain` table (header, 16, null) |
| `SmokeGen` 0x51c7b0 | 748 | 16 | 16 + null + all 731 entries of 0x51c840–0x51df17, the 76 tables without type information |
| `bad_alloc` 0x51e0e8 | 2 | 2 | correct by accident: it is the last table and trailing nulls were stripped |

Corrections to the earlier explanations:

- `docs/objects.md` ("Reading the virtual tables") says the scanner runs on "when the next
  table's type-info function is too large for it to recognise". That is fault 2 and covers
  `WeaponShield` and `Weapon2` only, and the getters are not large: they were *measured*
  as large. `PoisonRain` was lost through fault 3, and the tables after `SmokeGen` have no
  type-info function at all.
- `docs/runtime.md` section 4.1 mentions one secondary table (0x51c918, delta −8). There
  is a second: 0x51cc08, whose header and first three entries have delta −4.

## 3. The rules now used

### 3.1 Which class a table belongs to

Entry 0 of a table of a class compiled with type information is `{0, getter}`. A getter
tests the first word of a static descriptor, fills the descriptor on first use by calling
one of four initialisers, and returns the descriptor's address:

| Initialiser | Call sites | For |
|---|---|---|
| 0x3b12d8 | 7 | class with no base |
| 0x3b12b8 | 422 | class with one base |
| 0x3b1290 | 5 | class with a base list |
| 0x3b25c8 | 3 | pointer type |

The second argument of every call is the mangled name (decimal length, then the name).

**Rule: the class of a getter is the name passed to the last initialiser call before the
getter returns.**

Evidence, over all functions that call an initialiser:

- There are 406 such functions and each has exactly one return. 380 make one initialiser
  call, 21 make two, 5 make three (26 with more than one: the 24 of fault 1 plus the
  `Weapon2` and `WeaponShield` getters).
- In all 406 the descriptor address returned is the first argument of the **last** call.
  The earlier calls fill other descriptors: those of the base classes.
- Across all 437 calls no descriptor is ever given two different names (406 descriptors,
  406 names), so an inlined base initialiser and the base's own getter agree.
- 402 of the 406 getters head exactly one table each. The other four head none:
  `WeaponCommon` (0x3c27f0, a class without virtual functions) and the three pointer types
  (0x3c7d20, 0x3c7d70, 0x3c7dc0).
- No getter address appears anywhere in a table except in entry 0.

How the tool applies it, in outline (my wording, not program output):

```
class_of(getter):
    read instructions from the entry up to the first jr or j
    track lui / addiu so the value of $a1 is known
    at each jal to one of the four initialisers, remember the string $a1 points to
    answer: the last string remembered, without its length prefix
```

The instructions are read directly rather than through the function table of
`tools/ps2elf.py`, because that table is what produced faults 2 and 3. Stopping at the
first `j` as well as the first `jr` matters: 33 skill classes have a slot-7 function that
ends in a tail jump and is followed directly by another class's getter. Reading on would
give each of them that class's name and produce 33 false tables inside real ones.

### 3.2 Where a table ends

**Rule: a table is entry 0, then the functions (slot 1 first), then one all-zero entry.
It ends at the first entry whose function pointer is null. The next table starts on the
following 8 bytes.**

Evidence:

- Starting at 0x50cc58 and applying the rule repeatedly gives 478 tables that cover
  0x50cc58–0x51e107 without a gap or an overlap and stop exactly at the end of `.data`
  (0x51e108).
- Every header found independently by scanning `.data` for `{0, getter}` (402 of them, all
  8-byte aligned) falls exactly on a table start of that walk.
- No table has a null function pointer before its end. A slot without an implementation
  holds 0x3ad348, the pure-virtual handler: 25 slots in tables with type information, 115
  in tables without.

**Inferred**, from how GCC 2.9x builds these tables and not from the executable: the zero
entry is not a deliberate terminator but one spare array element the compiler allocates.
The practical consequence is the same.

Slot counts that follow from the rule: `GameObject` 16, `Creature` 39, `Skill` 15, `Spell`
4, `WeaponInterface` / `Weapon1` / `Weapon2` / `WeaponShield` 24, `WeaponObject` 25. This
confirms `docs/objects.md` (16 and 39) and `docs/runtime.md` (15 for Skill).

By slot count, the 386 game tables are: 131 with 16, 8 with 17, 14 with 19, 3 with 29 and
76 with 39 (the `GameObject` family, 232 tables); 93 with 15 (`Skill`); 56 with 4
(`Spell`); 4 with 24 and 1 with 25 (weapons).

### 3.3 Tables without type information

**Rule: a table that follows another table's zero entry and whose entry 0 is
`{delta, 0x3ad348}` belongs to a class compiled without type information. It is listed as
`vt<table address in hex>`, for example `vt51c840`.**

Evidence:

- 76 such tables lie between `SmokeGen` and the first table of the C++ runtime,
  0x51c840–0x51df17, back to back under rule 3.2.
- The executable holds 216 data pointers to 0x3ad348: these 76 headers plus the 140 slots
  counted above. There is none outside the table range, so there is no further table of
  this kind elsewhere.
- 75 of the 76 addresses are loaded by code (constructors and destructors), which is
  independent confirmation that they are table starts. The exception is 0x51d6f8
  (section 8).
- Two are secondary tables of a class with several bases: 0x51c918 (delta −8 in every
  entry) and 0x51cc08 (delta −4 in the header and slots 1–3, 0 in slots 4–5). Both are
  installed by the same functions as 0x51c8d8.

The name `vt<address>` was chosen because `symbols/runtime.tsv` already names 68 functions
of these tables `vt<address>_slotN` / `_dtor`; all 68 agree with the new list (same table,
same slot). **Inferred**: that the compiler puts the pure-virtual handler in entry 0 when
type information is switched off is GCC 2.9x behaviour; the executable only shows that
these 76 headers hold it.

### 3.4 How the result was checked

A second script, written for this check and kept outside the repository, takes function
bounds from `ghidra_funcs.tsv`, runs a fuller constant propagation over each function that
calls an initialiser, names each getter by the descriptor it **returns**, and walks the
tables as in 3.2. Its list and the output of the corrected `tools/vtab.py` are identical
for all 478 tables (address, name, slot count). The tool's getter test also returns the
right name for the four getters that head no table, and no name for any of the other
7,326 functions in `ghidra_funcs.tsv`.

## 4. What changed in the tool and the list

`tools/vtab.py`: the command line (`list`, `show <Class|hexaddr>`) and both output formats
are unchanged. `find_vtables()` still returns `{address: (name, [(delta, function), …])}`
for `tools/localstate.py`.

| Output | Change |
|---|---|
| `list` | 478 lines instead of 399. `N entries` is now the number of virtual functions (slots 1..N); it used to include the null entry |
| `show X` | no final row with a null function; `show Projectile`, `show WorldPart`, `show Prop`, `show FireBeetle` print one table each (they printed 12, 7, 7 and 2); `show vt51c840` or `show 51c840` prints a table without type information |
| "shared with" | class lists use the corrected names |
| `localstate.py` | a class named on its command line now selects only its own table |

`vtables.txt` was regenerated with `python3 -I -B tools/vtab.py SLUS_209.73 list`. The
line format is the same (`0xADDRESS ClassName   N entries`).

Not changed: `show` still takes its `size=` column from the heuristic function table, and
still needs the address without leading zeros (`show 50cf40` or `show 0x50cf40`; the form
`0x0050cf40` printed by `list` matches nothing). Both are older behaviour.

## 5. Tables

### 5.1 Relabelled (24)

"Calls" is the number of initialiser calls in the getter; the class is the last.

| Table | Old label | Class | Base | Getter | Calls | Slots |
|---|---|---|---|---|---|---|
| 0x50de28 | WorldPart | FallPlatform | WorldPart | 0x3c6e70 | 2 | 16 |
| 0x50deb8 | WorldPart | FloorSwitch | WorldPart | 0x3c6d80 | 2 | 16 |
| 0x50df48 | WorldPart | Switch | WorldPart | 0x3c6c90 | 2 | 16 |
| 0x50dfd8 | WorldPart | DoorSecret | WorldPart | 0x3c6ba0 | 2 | 16 |
| 0x50e068 | WorldPart | RollDoor | WorldPart | 0x3c6ab0 | 2 | 17 |
| 0x50e100 | WorldPart | DoorSwing | WorldPart | 0x3c69c0 | 2 | 17 |
| 0x50e3d8 | Projectile | beetleProjectile | MissileWeapon | 0x3c6600 | 3 | 17 |
| 0x50e470 | Projectile | playerProjectile | MissileWeapon | 0x3c64d8 | 3 | 17 |
| 0x50e508 | Projectile | AnimatedMissile | Projectile | 0x3c63d0 | 2 | 17 |
| 0x50e5a0 | Projectile | MissileWeapon | Projectile | 0x3c62c0 | 2 | 17 |
| 0x50e638 | Projectile | IceBall | Projectile | 0x3c6238 | 2 | 16 |
| 0x50e758 | Projectile | Root | Projectile | 0x3c6058 | 2 | 16 |
| 0x50e7e8 | Projectile | LostSoul | Projectile | 0x3c5f48 | 2 | 16 |
| 0x50e878 | Projectile | OniBall | Projectile | 0x3c5e38 | 2 | 16 |
| 0x50e908 | Projectile | HolyBolt | Projectile | 0x3c5d28 | 2 | 16 |
| 0x50e998 | Projectile | Sparks | Projectile | 0x3c5c18 | 2 | 16 |
| 0x50ea28 | Projectile | DummyDamager | Projectile | 0x3c5b08 | 2 | 16 |
| 0x50f328 | Prop | LooseIceChunk | PhProp | 0x3c4ed0 | 3 | 16 |
| 0x50f3b8 | Prop | GutChunk | PhProp | 0x3c4db0 | 3 | 16 |
| 0x5108c8 | FireBeetle | FireFly | FireBeetle | 0x3c40f0 | 2 | 39 |
| 0x511b18 | Prop | PhIce | PhProp | 0x3c3120 | 3 | 16 |
| 0x511ba8 | Prop | PhProp | Prop | 0x3c3030 | 2 | 16 |
| 0x511c38 | Prop | ItemProp | Prop | 0x3c2f40 | 2 | 16 |
| 0x511cc8 | Prop | ParticleProp | Prop | 0x3c2e50 | 2 | 16 |

The tables that really belong to the four old labels are unchanged: `WorldPart` 0x511de8,
`Projectile` 0x5120b8, `Prop` 0x511d58, `FireBeetle` 0x510a10.

### 5.2 Added, with type information (3)

| Table | Class | Base | Getter | Slots | Was hidden inside |
|---|---|---|---|---|---|
| 0x50cda0 | WeaponShield | Weapon1 (base list) | 0x3c22b0 | 24 | `Creature`, old entries 41–65 |
| 0x50ce70 | Weapon2 | Weapon1 (base list) | 0x3c1e28 | 24 | `Creature`, old entries 67–91 |
| 0x51aa68 | PoisonRain | GameObject | 0x3cffd4 | 16 | `SkillLifeTap`, old entries 17–33 |

### 5.3 Added, without type information (76)

Name and number of slots. All were inside the old `SmokeGen` line.

| | | | |
|---|---|---|---|
| `vt51c840` 1 | `vt51cf88` 9 | `vt51d730` 8 | `vt51d9c8` 12 |
| `vt51c858` 1 | `vt51cfe0` 9 | `vt51d780` 8 | `vt51da38` 8 |
| `vt51c870` 1 | `vt51d038` 9 | `vt51d7d0` 1 | `vt51da88` 12 |
| `vt51c888` 1 | `vt51d090` 14 | `vt51d7e8` 1 | `vt51daf8` 5 |
| `vt51c8a0` 5 | `vt51d110` 9 | `vt51d800` 1 | `vt51db30` 5 |
| `vt51c8d8` 6 | `vt51d168` 9 | `vt51d818` 1 | `vt51db68` 1 |
| `vt51c918` 92 (delta −8) | `vt51d1c0` 9 | `vt51d830` 1 | `vt51db80` 1 |
| `vt51cc08` 5 (delta −4) | `vt51d218` 9 | `vt51d848` 1 | `vt51db98` 1 |
| `vt51cc40` 9 | `vt51d270` 1 | `vt51d860` 1 | `vt51dbb0` 1 |
| `vt51cc98` 9 | `vt51d288` 9 | `vt51d878` 1 | `vt51dbc8` 5 |
| `vt51ccf0` 1 | `vt51d2e0` 9 | `vt51d890` 1 | `vt51dc00` 1 |
| `vt51cd08` 1 | `vt51d338` 9 | `vt51d8a8` 1 | `vt51dc18` 10 |
| `vt51cd20` 9 | `vt51d390` 1 | `vt51d8c0` 1 | `vt51dc78` 10 |
| `vt51cd78` 9 | `vt51d3a8` 1 | `vt51d8d8` 1 | `vt51dcd8` 10 |
| `vt51cdd0` 9 | `vt51d3c0` 1 | `vt51d8f0` 1 | `vt51dd38` 10 |
| `vt51ce28` 9 | `vt51d3d8` 1 | `vt51d908` 1 | `vt51dd98` 10 |
| `vt51ce80` 9 | `vt51d3f0` 1 | `vt51d920` 5 | `vt51ddf8` 10 |
| `vt51ced8` 9 | `vt51d408` 92 | `vt51d958` 5 | `vt51de58` 10 |
| `vt51cf30` 9 | `vt51d6f8` 5 | `vt51d990` 5 | `vt51deb8` 10 |

`docs/netlib.md` names the classes behind six of them from assertion strings, not from
type information: `SRSClient` (0x51c8d8, with 0x51c918 and 0x51cc08 for its other two
bases), `UdpConnection` (0x51d920), the PS2 socket driver (0x51d9c8) and `UdpManager`
(0x51db30). The slot numbers quoted in `symbols/netlib.tsv` for these tables agree with
the new list. They keep their artificial names in `vtables.txt`.

### 5.4 Length corrected

`Creature` 92 → 39, `SkillLifeTap` 34 → 15, `SmokeGen` 748 → 16; the other 395 older lines
are one lower each; `bad_alloc` stays 2.

## 6. Renamed symbols

How they were found: for every symbol in `names.tsv` and `symbols/*.tsv`, (a) if its
address is held by a table, the class in the name must be one of the holders and a slot
number in the name must be the slot it occupies; (b) every function that loads the address
of a relabelled or added table (constructors, destructors, copy functions) was listed with
its name; (c) every function in every slot of the 27 tables of 5.1 and 5.2 was listed with
its name and read by eye. 1,939 symbols sit on table-held functions; 11 rows were wrong
(five found by (a), three by (b), three by (c)).

| Address | Old name | New name | File | Why |
|---|---|---|---|---|
| 0x1ee330 | `Projectile_run` | `DummyDamager_run` | `symbols/gameplay.tsv` | slot 4 of 0x50ea28 only |
| 0x1ee7b0 | `Projectile_onTouch` | `DummyDamager_onTouch` | `symbols/gameplay.tsv` | slot 6 of 0x50ea28 only |
| 0x201e78 | `Projectile_ctor` | `DummyDamager_ctor` | `symbols/gameplay.tsv` | calls the real `Projectile_ctor` (0x150e48), then stores table 0x50ea28 |
| 0x201fa0 | `Projectile_draw` | `DummyDamager_draw` | `symbols/gameplay.tsv` | slot 5 of 0x50ea28 only |
| 0x1ba730 | `Projectile_drawThrown` | `playerProjectile_draw` | `symbols/player.tsv` | slot 5 of 0x50e470 only |
| 0x1ba940 | `Projectile_runThrown` | `playerProjectile_run` | `symbols/player.tsv` | slot 4 of 0x50e470 only |
| 0x1bef58 | `Projectile_ctorThrown` | `playerProjectile_ctor` | `symbols/player.tsv` | calls `MissileWeapon_ctor` (0x150ee4), then stores table 0x50e470 |
| 0x2f5248 | `DismissUndeadProjectile_ctor` | `HolyBolt_ctor` | `symbols/skills.tsv` | calls `Projectile_ctor`, then stores table 0x50e908 |
| 0x2f57b0 | `DismissUndeadProjectile_run` | `HolyBolt_run` | `symbols/skills.tsv` | slot 4 of 0x50e908 only |
| 0x2f5ddc | `DismissUndeadProjectile_draw` | `HolyBolt_draw` | `symbols/skills.tsv` | slot 5 of 0x50e908 only |
| 0x2f5fb4 | `DismissUndeadProjectile_onHit` | `HolyBolt_onHit` | `symbols/skills.tsv` | slot 6 of 0x50e908 only |

Each row's note now gives the table address and the former name. Only the class part of a
name was changed; the wording after the underscore is the original author's (which is why
slot 6 is `_onTouch` in one file and `_onHit` in another).

Two things this fixed on the side: `Projectile_ctor` was the name of two different
functions (0x150e48 in `symbols/objects.tsv`, the real one, and 0x201e78); and
`DismissUndeadProjectile` was an invented class name for a table that has a real one.

`names.tsv`: **no correction needed.** None of its names carries a class that the corrected
list changes. (`clone_50d590` at 0x1309f0 is slot 15 of `Teleporter`, whose label was
already right; `docs/player.md` and `docs/creatures.md` already say so.)

Everything else was already right. In particular the 406 type-info getters in
`symbols/runtime.tsv` are all named for the correct class, and the first-round names for
the doors, the other projectile classes, the prop classes, `FireFly`, `Weapon2`,
`WeaponShield` and `PoisonRain` were taken from each author's own reading, not from the old
list. `python3 -I -B tools/symtab.py check` reports 5,241 symbols, 0 conflicts, 0 malformed
lines, as before.

## 7. Documents whose text is now wrong or out of date

Not edited here; listed for their owners.

Text that names the wrong class:

| File, section | Says | Correct |
|---|---|---|
| `docs/gameplay.md`, "4. Effect objects", table row for 0x50ea28 | class `Projectile` | `DummyDamager` (base `Projectile`); constructor 0x201e78, run 0x1ee330, touch 0x1ee7b0 |
| `docs/skills.md`, "Skill id table", rows 21, 46, 57, 98, 99 | `Projectile@0x50e7e8`, `Projectile@0x50e5a0`, `Projectile@0x50e998`, `Projectile@0x50e470` (twice) | `LostSoul`, `MissileWeapon`, `Sparks`, `playerProjectile` |
| `docs/skills.md`, "Skill id table", row 22 | `DismissUndeadProjectile` | `HolyBolt` (table 0x50e908) |
| `docs/skills.md`, notes after the skill id table, `PoisonRain` item | table at 0x51aa60, merged with `SkillLifeTap` in `vtables.txt` | the table is at 0x51aa68 (0x51aa60 is `SkillLifeTap`'s zero entry); the list now has it separately |
| `docs/player.md`, "Not read" | `Projectile_runThrown` 0x1ba940 | `playerProjectile_run` |
| `docs/engine.md`, "Per-machine state", row P4 | "constructors of FireBeetle (0x24587c, 0x24726c)" | 0x24726c is the `FireFly` constructor (table 0x5108c8); only 0x24587c is `FireBeetle`'s |
| `docs/startup.md`, "Fields of other structures used here" | "Item prop (0x248 bytes, vtable 0x511ba8)" | table 0x511ba8 is `PhProp` (0x155a0c is `PhProp_ctor`); `ItemProp` is a different class, table 0x511c38 |

Text that left a class unnamed and can now name it:

| File, section | Says | Class |
|---|---|---|
| `docs/monsters.md`, 2.1 (field +0x50), 7.10, and open question 4 in section 9 | "weapon helper" object or class "at table 0x50cda0" | `WeaponShield` (base `Weapon1`) |

Text that describes the old tool or the old list:

| File, section | Says | Now |
|---|---|---|
| `docs/objects.md`, "Reading the virtual tables: 16 slots, not 17" | `tools/vtab.py` reports 17 for `GameObject` and 92 for `Creature` | it reports 16 and 39; the explanation of the over-run is incomplete (section 2) |
| `docs/runtime.md`, 4.2 | "`vtables.txt` has 24 such labels", "also lacks three tables", "lists SmokeGen with 748 entries" | all corrected |
| `docs/runtime.md`, 4.1 | one secondary table, 0x51c918 | two: also 0x51cc08 |
| `docs/monsters.md`, "8. Corrections to earlier notes" | 13 tables that `vtables.txt` lists as `Projectile`, `WorldPart` or `FireBeetle` | corrected; the 13 are part of the 24 in 5.1 |
| `README.md`, "Where it stands" | "399 are tied to their virtual tables" | 402 classes have a table (386 game classes and 16 of the C++ runtime). Of the 403 classes with a type descriptor only `WeaponCommon` has none |

## 8. Not resolved, and things noticed on the way

- **0x51d6f8 (`vt51d6f8`, 5 slots, functions 0x37c730–0x37c79c).** Listed because it has
  the shape of a table and sits between two tables that are confirmed by code. **Unknown**
  whether anything uses it: no instruction pair loads its address and no data word holds
  it. A base class whose constructor the compiler never emitted would look like this
  (**Inferred**).
- **Class names of the 76 tables without type information.** Not recoverable from type
  information. Six have names from assertion strings (5.3); the constructors that load the
  other table addresses are the way to name the rest.
- **`tools/ps2elf.py` function table** (not in my files, not changed). Faults 2 and 3 come
  from it and it affects other tools: a data word that happens to look like a code address
  becomes a function start. Two cases seen: 0x3d0000 (splits the `PoisonRain` getter
  0x3cffd4), and 0x293228 (data word at 0x558958), which is in the middle of the
  `LostSoul` constructor. That constructor starts at 0x2931bc (its prologue, and the two
  calls to it at 0x2f4e2c and 0x2f6364 go there), but `symbols/monsters.tsv` and the
  `LostSoul` row of `docs/monsters.md` section 3.2 give 0x293228. This is a wrong address,
  not a wrong class, so the row was left alone. 0x2931bc has no name.
- **`rtti_classes.txt`** (not in my files) has 403 lines, of which 6 are not class names
  (strings that only look like mangled names), and it lacks 6 classes that have a
  descriptor: `Cazic`, `Creature`, `RedDragon`, `Weapon2`, `WeaponShield`, `Wheel`. All
  six are in `vtables.txt`.
- **Notes in symbol rows.** Only rows with a wrong name were edited. A scan of all notes
  for "vtable 0x… slot N", "slot N of Class" and "Class (vtable 0x…)" found no other note
  that contradicts the corrected list.
- **Meaning of slots** was not part of this work. Renamed functions keep the descriptions
  their authors gave.

## 9. Re-checking

```
python3 -I -B tools/vtab.py SLUS_209.73 list | diff - vtables.txt     # no output
python3 -I -B tools/vtab.py SLUS_209.73 show Creature                 # 39 rows
python3 -I -B tools/vtab.py SLUS_209.73 show DummyDamager             # table 0x50ea28
python3 -I -B tools/symtab.py check                                   # 0 conflicts, 0 malformed
python3 -m unittest discover -s tools -p 'test_*.py'                  # 39 tests, OK
```
