# `hideMonster`, `showMonster` and the level objects they and `generateMonster` reach

US `SLUS_209.73` v2.00. This note is the contract for the script commands `hideMonster`
(0x144c00) and `showMonster` (0x144db8) with their real callees, what a port needs to
know about an object to run them, and a disc census (counts only) of the objects the
commands name and of the `ScriptGenerator` objects that `generateMonster` reaches.
It follows `docs/script-items.md` (section 10, "which objects on the disc are
`ScriptGenerator`s") and the native client's report that `hideMonster` refuses 119 times in
its 111-level sweep because the objects it finds are unbuilt stubs.

| File | What |
|---|---|
| `tools/ref_hide_monster.py` | model: both handlers on the object world of `tools/ref_objects.py` |
| `tools/difftest_hide_monster.py` | runs the originals in `tools/ee_emu.py` on a world built by the original constructors and compares everything after every step |
| `tools/test_ref_hide_monster.py` | 15 synthetic tests, no game file needed |
| `tools/objects_census.py`, `tools/test_objects_census.py` | disc counts (counts only); 3 synthetic tests of the record reader |

"Executed" means run in `tools/ee_emu.py` against the model by the difftest. Nothing here
was seen on a running game.

## 1. The handlers (Executed)

Both are entered as the dispatcher enters every command, `(machine, params)`, and both have
the same shape:

1. `scr_getAddr(machine, params[1], &cell)` 0x1414a8, then `scr_getString(buffer, cell)`
   0x141650. The buffer is the first 0xa0 bytes of the handler's 0x8d0-byte frame; the
   cell word follows at +0xa0 and the result array at +0xb0 (Observed: frame layout at
   0x144c00–0x144c3c). A name of 0xa0 bytes or more runs into those two, both of which are
   written again before use. Not executed.
2. `world_findObjectsByName(buffer, array, 0x200)` 0x14bf58 (limit at 0x144c30 and
   0x144de8). The array is 0x800 bytes. The name table stops after 0x1ff objects, so the
   terminator always fits (`ref_objects.NameTable.find`). The match ignores case and the
   objects come in the table's probe order.
3. For each object of the array, in that order:

| | `hideMonster` 0x144c00 | `showMonster` 0x144db8 |
|---|---|---|
| call | `obj_moveOffGrid(obj)` 0x14ef48: the grid node is unlinked and pushed at the **front** of `g_offGridList` 0x5f76f0 | `obj_updateGridCell(obj)` 0x14f028: unlinked and pushed at the front of the list for its current position: grid B 0x5e95f0 if flag 0x800, else grid A 0x5db4f0, else (outside 0..119) the off-grid list |
| +0x0c (u32 flags) | re-read after the call, `|= 0x8000` (0x144c74) | re-read after the call, `&= 0xffff7fff` (0x144e28–0x144e34) |
| +0x231 (u8) | only when the new flag word has 0x20: `|= 8` (0x144c84–0x144c8c) | only when it has 0x20: `&= 0xf7` (0x144e44–0x144e4c) |

4. Return 0.

Nothing else is read or written: no other object field, no player record, no
per-machine state. **No seed draw** (the shared seed 0x404464 is compared after every step).
Callees seen while the handlers ran: the two argument fetches, `world_findObjectsByName`,
the grid call and two C-library routines (0x3b81a0, 0x3b8dc4) inside the name lookup. A
call to any other address fails the case.

Cases, all executed:

| Case | Result |
|---|---|
| name finds nothing (no object, or the empty name) | nothing, returns 0 |
| several objects with the name, any case | every one, in name-table order |
| already hidden (hide twice) | node pushed to the front of the off-grid list again; flag and byte unchanged |
| show an object that is not hidden | node unlinked and pushed at the front of its own cell: **the order inside the cell changes** (the box query's result order, `docs/spec/object-system.md` 4.2) |
| show an object outside the grid | stays on the off-grid list (front) |
| show an object with flag 0x800 | goes to grid B, so the box query still does not return it |
| flag 0x8000 set by other means | `showMonster` clears it anyway |
| non-creature (no flag 0x20) | grid and flag only; +0x231 never touched |
| object deleted (`obj_delete`) but not yet flushed | still in the name table, so found and handled; after the flush it is gone |
| hidden object | not returned by `world_collectObjectsInBox` (it walks grid cells only) |

The model assumes every object found has a grid link; the original would follow a null
pointer inside `obj_moveOffGrid` / `obj_updateGridCell` otherwise. Every object built by
`GameObject_ctor` has one from construction until its destructor, and destruction removes
it from the name table first (`ref_objects.World.destroy`), so the handlers cannot reach an
object without a link.

## 2. What the flags mean to the rest of the game

| State | Read by | Effect |
|---|---|---|
| flag 0x8000 | `runObjects` before every slot-4 call (`docs/objects.md`, flag table) | the object does not run |
| on the off-grid list | the box query and the grid draw walk | not found by area queries, not drawn |
| +0x231 bit 3 | `Creature_moveBy` 0x113ca4, `Weapon2_update` 0x1180f0 / 0x1181d0, `Weapon1` slots 21 and 22 (0x11b33c, 0x11b46c), 0x11adc0, 0x11aee0, `cut_regridHiddenCreature` 0x198fa0, `cut_ungridHiddenCreature` 0x198ff4 (flagxref, certain hits) | the creature is inert: `docs/creatures.md` gives +0x231 as "inert bits" whose non-zero value stops target picking |

`Creature_hide` 0x11a538 and `Creature_show` 0x11a4f0 do the same three steps for one
creature, without the flag-0x20 test (Observed).

## 3. What a port must know per object (the native refusal)

The native client refuses `hideMonster` / `showMonster` when any object the name finds is
an unbuilt stub, because it cannot tell whether to write +0x231. The handlers need
exactly this per object, and nothing else:

1. **Whether the object is a creature (flag 0x20).** The only certain setter is
   `Creature_ctor` 0x109d68 (`|= 0x20` at 0x109e5c; `tools/flagxref.py`, the other hits are
   possible-only register masks). So the answer is a property of the class: the class's
   constructor chain reaches `Creature_ctor` or it does not. `tools/objects_census.py`
   decides this per class by running the original factory and constructor chain (section
   4). A stub needs no built creature to answer it.
2. **Its grid list and position in it.** A freshly constructed object is at the front of
   its grid-A cell, or of the off-grid list when outside the grid (`GameObject_ctor` step 3,
   `docs/spec/object-system.md` 2.2). The base constructor never hides a fresh object: it
   looks `hide` up before storing the property list (`docs/objects.md`).
   `Creature_ctor` and `Catapult_ctor` 0x24d598 hide at load themselves.
3. **The flag word** (bit 0x8000 only changes).
4. **For a creature, byte +0x231.** The handlers only set or clear bit 3 and keep the other
   bits. `Creature_ctor` starts it at 0 (0x109e88), sets bit 0 when the `wait` property
   (string 0x52f9f0) is non-zero (0x109ef0–0x109f08), and when `hide` (string 0x52f9f8) is
   non-zero sets bit 3, moves the object off the grid and sets flag 0x8000
   (0x109f14–0x109f3c). What derived constructors do to the byte afterwards was not
   traced (Unknown); it does not change what hide and show write.

So a stub whose class is known can run both commands. Only a stub whose class's creature
status is unknown needs to stay refused.

## 4. On the disc (counts only)

`python3 tools/objects_census.py --disc <private copy> --elf <SLUS_209.73>` over the read-only
private disc copy. Output in `local/census/objects-census.txt` (untracked). Each of the
120 level lumps holds both an `objects.ob` and a `script.scr`. Records are read with the
layout of `docs/objects.md`.

How classes were decided. For each distinct class name the original
`world_objectFactory` 0x159c94 runs with `pool_new` stubbed. A name that no test matches is
probed again with the record's own property list, because properties then decide the
class. The constructor chain then runs for real on the block, with three rules:

- entering `Creature_ctor` with the block means creature;
- entering `GameObject_ctor` 0x14cb10 first means non-creature;
- any other call that receives the block runs, and every other call returns 0.

The level-world pointer 0x44fdc8 is 0 in the image. The factory reads +0x70 of it for
`PushTrigger`, so the probe points it at a zeroed block. The constructors found agree with
the table in `docs/objects.md` (for example `ScriptGenerator` 0x265f54, `Orc` 0x2a0954,
`Skeleton` 0x2a5af4).

| What | Count |
|---|---:|
| level records | 18,675 |
| ... creature / non-creature | 6,307 / 10,795 |
| ... no object (the factory makes none, so no name-table entry) | 1,113 |
| ... undecided: `Line` (a 0x18-byte block, not a GameObject) | 144 |
| ... undecided: the factory stopped before `pool_new` (`ArenaPlayerStart` / `Alternate`, and 53 property-decided cases) | 316 |
| distinct class names: creature / non-creature / no object / undecided | 134 / 40 / 117 / 3 |

### 4.1 `ScriptGenerator` objects

| What | Count |
|---|---:|
| records whose class reaches `ScriptGenerator`'s constructor 0x265f54 | **105**, in **11** levels |
| ... with a `name=` property | 105 |
| ... with a `hide` property | 0 |
| ... property count 2 / 3 / 4 / 5 / 6 | 19 / 9 / 49 / 21 / 7 |
| records of the autonomous generator constructor 0x2657a0 (`AntMaker`, or `Generator` by properties) | 15 (not reached by `generateMonster`) |
| `generateMonster` calls | 136 |
| ... whose literal generator name finds exactly one `ScriptGenerator` in the same level | **133** |
| ... whose generator name is not a literal | 3 |
| ... whose generator name finds none, or several | 0 |

`ScriptGenerator_spawn` passes the generator's own property list (word +0x2c) to
`world_createObject` (`docs/script-items.md` 5.1, Executed). The spawned object's
`GameObject_ctor` enters every `name=` property of that list in the name table
(`docs/spec/object-system.md` 2.2 step 7, Executed). So every spawned monster carries its
generator's name (Inferred from the two executed contracts; not run together). No literal
`hideMonster` / `showMonster` name is a generator's name (count 0).

### 4.2 What `hideMonster` and `showMonster` find

A name is matched against the `name=` properties of the same level's records, as the name
table matches (case ignored, quotes stripped). Records whose class makes no object are left
out.

| | `hideMonster` | `showMonster` |
|---|---:|---:|
| calls (all names literal) | 373 | 52 |
| finds only creatures | 100 | 22 |
| finds only non-creatures | **262** | 22 |
| finds both | 6 | 3 |
| finds no level-file object | 5 | 5 |
| finds an undecided class | 0 | 0 |
| objects found, all calls / creatures among them | 1,492 / 1,066 | 457 / 428 |

Every one of the 368 hide calls and 47 show calls that reach a level-file object reaches
only classes whose creature status is decided. 262 hide and 22 show calls never need the
creature byte at all. The 5 + 5 names with no level-file object would find only objects
created during play. Which ones, if any, is Unknown, and the original does nothing when
none exists.

## 5. What the native client should do

1. **Run hide and show on stubs.** Decide flag 0x20 from the record's class, using the
   creature / non-creature table that the factory probe gives (section 4: 134 creature
   classes, 40 non-creature). Keep the refusal only for a class that is undecided. On the
   disc no hide or show target is undecided.
2. Model the off-grid list as a list with front insertion, not as a boolean. Box-query
   order and drawing depend on it. Also model that `showMonster` relinks an object that was
   never hidden.
3. Set or clear flag 0x8000 (the object stops running). For a creature, set or clear only
   bit 3 of +0x231, keeping the other bits, which `Creature_ctor` seeds from `wait` and
   `hide`.
4. Draw nothing from the seed.
5. Generators: the 105 `ScriptGenerator` records are the only targets `generateMonster`
   reaches (133 of 136 calls, one generator each). Building them needs only the 0x4c-byte
   base object (constructor 0x265f54) and their property list, which the spawn hands on.
   The spawned monster inherits the generator's `name=`, so later name lookups find both
   the generator (a non-creature) and its spawn.

## 6. Runs

- `python3 tools/difftest_hide_monster.py --cases 200`, seed 20973: 2 suites, 0 failed.
  `mixed`: 200 handler calls inside 636 compared operations, 819 objects handled, 359 of
  them creatures, 18 names finding nothing. `edges`: 27 fixed steps.
- `python3 tools/difftest_hide_monster.py --cases 100 --seed 7`: 2 suites, 0 failed (100
  handler calls, 391 operations, 341 objects, 112 creatures).
- Harness check: a model with the wrong hidden bit, and a `hideMonster` that relinks into
  the cell instead of the off-grid list, both fail.
- `python3 -m unittest tools/test_ref_hide_monster.py tools/test_objects_census.py`: 18
  tests.

## 7. Open

- What derived creature constructors write to +0x231 after `Creature_ctor`.
- Which play-time objects the 5 + 5 names with no level-file object refer to.
- `Line` records (144) and the 316 records whose factory call stopped in the probe. None
  of them is a hide, show or generator target.
- The 53 property-decided probes that stopped before `pool_new`. Their classes are
  Unknown.
