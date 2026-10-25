# Binding a level script to a play session

What a native host must give a level's script so that it runs as it does in the original:
the random seed `getRand` draws from, the player count and difficulty of a single-player
game, and the level objects the script finds by name. RTA US v2.00 (`SLUS_209.73`).

Builds on `docs/script-composition.md` ("The seam", research-script 9649e6b),
`docs/startup.md` (session start), `docs/issues/arena-entry.md` 1.4 (what the load does to
shared state), `docs/objects.md` ("The object factory"), `docs/spec/object-system.md` 2.2
(`GameObject_ctor`) and `docs/spec/monsters-1.md` (the five ported creature classes).

Tools: `tools/ref_level_factory.py` with `tools/difftest_level_factory.py`, and
`tools/ref_creature_init.py` with `tools/difftest_creature_init.py`; their unit checks are
in `tools/test_ref_level_factory.py`. Disc figures below are counts only.

## 1. The seed `getRand` draws from, and how it is seeded

`getRand` (`script_getRand` 0x146570) draws once from `g_randSeed` 0x404464: `seed = seed ×
0x19660d + 0x3c6ef35f`, the answer is from the high 16 bits (`docs/script-composition.md`,
executed in `difftest_natives`). That is the one shared generator of the simulation:
combat, effects, item generation, object constructors and `world_findFreeSpot` all draw
from it (`tools/gxref.py SLUS_209.73 404464` lists 232 stores in 125 functions).

Nothing seeds it at level start. The stores that are not draws are (Observed, the
`gxref` listing read store by store):

| Store | Where | Value |
|---|---|---|
| 0x322a04 | `mainloop_runSession` 0x322998, once per session, offline only | COP0 Count, the CPU cycle counter (`docs/startup.md` step 4) |
| 0x13dd0c | `net_startSync` 0x13dce0, net launch | 0 |
| 0x132ccc, 0x13b56c | `net_predictLocalPlayer`, `net_frameLoop` | the value saved before the prediction copy ran (FINDINGS G1) |

`game_loadLevel` copies the shared seed into the cosmetic one (0x1e59b4) and does not
write the shared seed. So in an offline game the seed a level's `start` sees is the
session's cycle-counter value advanced by every draw since: the first level's item loader
(223 draws, only while `hud.lmp` is not loaded), then in each level the load's draws in
file order: one in every `GameObject_ctor` (0x14cd5c-0x14cd80), whatever the derived
constructors draw, `Player1_ctor`'s four `world_findFreeSpot` searches and four single
draws (`docs/issues/arena-entry.md` 1.4), and in play everything else that draws.

**For a port.** `getRand` must draw from the session's shared generator, the one combat
and the objects use; a generator of its own would give the script numbers the simulation
also gives elsewhere. An offline session's starting value is a clock reading, so no fixed
value is "the original's": a port's session seed stands in for it. What a port can match
exactly is the order of draws on that one generator from the session's start. Where the
load makes draws the port does not make (constructors it does not run, the first level's
item loader, `Player1_ctor`'s searches), the script's numbers are still draws of the
session generator but at a different position than the original would reach from the same
starting value. A net game starts from 0 after `net_startSync`, so there every load draw
must be made for the peers to agree.

## 2. Player count and difficulty of a single-player game

| Global | Single-player value | Evidence |
|---|---|---|
| `g_numPlayers` 0x4d8ae0 | 1 | the executable image holds 1 (read); `mainloop_setupOfflinePlayersFromArguments` 0x323a3c stores 1, or 4 with the four-player switch (0x323a98, 0x323a9c); offline front-end setup stores the "number of players" choice + 1 (`frontend_run` 0x1e18a4-0x1e18b0, `docs/ui.md`) |
| `g_difficultyIdx` 0x4f719c | 1 | the executable image holds 1 (read); research-items `docs/script-items.md` section 3: mission row 0 is never used, a port must start at 1, not 0 |

The other stores of `g_numPlayers` are the net launch (0x1e0b5c, the settings block
+7), `save_load` (0x221eb8), the arena path when 0x4f7124 is set (0x1e1990, 1),
`frontend_start` (0x1e1f78), the LAN debug lobby and 0x229e14. A host whose memory starts
at zero, as a script binder's does, must store both image values before `preStart`:
`mission_setAvailable`, `quest_add`, `getMissionAvailable` and the gold commands walk the
first `g_numPlayers` records and index the mission row by `g_difficultyIdx`.

## 3. Which level records become objects

`world_loadRecords` 0x14e808 hands every `objects.ob` record's class string and property
list to `world_objectFactory` 0x159c94 in file order. `tools/ref_level_factory.py` is the
factory as a contract, with every string named by its address (read from your executable
at run time):

- **206 name tests** in the order the original makes them (captured by running the
  factory on a class string no test accepts). 201 build one object: `pool_new(size)`, then
  one constructor. The `Orc` prefix row calls `save_getAct` 0x217edc between the two.
- **No object:** `clearColor` (stores `g_backgroundColor` 0x506044), `customVars`
  (`levelSettings_parse` 0x22e714), `ArenaPlayerStart` / `ArenaPlayerAlternate` (0x30503c
  with 0 / −1), and `Line` (`paths_add` 0x20f844). A `Line` whose `name` property is
  strcasecmp-equal to `wave` also builds a WaveMaker (0x768, 0x15ecf8).
- **The Skeleton prefix** is followed by two more prefix tests, `red` and `blue`, of the
  *same* class string (0x15b514, 0x15b55c), which a string starting with `Skeleton` cannot
  pass. Every Skeleton-prefixed record takes `Skeleton_ctor` variant 0 (0x15b5c8);
  variants 2 and 3 are unreachable from the factory. (`docs/objects.md` lists them as
  "red / blue / other".)
- **Property fall-backs**, tried when no name matched: `CreatureContainer`,
  `AutoContainer`, `AutoChest`, `AutoProp` (props_getInt 0x14f730 non-zero), `AutoEmitter`,
  `AutoDoor`, `AutoSwitch`, `Critter`, then `Generator` and `SmokeGen` (props_getStr
  0x14f850 non-null). The three `Auto*` light variants are chosen by
  `propList_hasAnyLight` 0x23a2b4 (three keys, then three formatted keys for 0..3).
  Otherwise the factory returns 0.
- **Comparisons.** Name tests lower a character by adding 0x20 when bit 0 of its C-library
  class byte (0x5628e1 + signed character) is set; equality includes the terminator.
  The property getters lower their *key* the same way, in place, and compare it
  case-sensitively with the entries, which must continue with `=`; getInt is `libc_atoi`,
  that is newlib `strtol` base 10 with a 64-bit long, then the low 32 bits.
- **Not modelled:** a `pool_new` that fails returns 0 with no constructor call
  (`docs/spec/object-system.md` 2.1).

**Executed** (`python3 tools/difftest_level_factory.py --disc DIR`): the chain (206 + 2
nested tests), 1,117 name cases (every test string in three cases, prefixes with
suffixes, near misses), 552 property cases (every key with 13 values, alone, after another
entry, with light keys, capitalised) and every record of the disc's level files: 111
levels, 17,398 records, 1,795 distinct class-and-property pairs. 0 mismatches. The disc's
records:

| Outcome | Records |
|---|---|
| builds an object (96 constructors) | 15,901 |
| calls a function and builds none (`Line`, `customVars`, the two arena points) | 496 |
| sets the clear colour | 111 |
| builds nothing (no test and no fall-back matched) | 890 |

So 1,497 records are never objects: a script that looks one of them up by name finds
nothing. Records of the constructors the native client has ported (section 4): `Gnaw`
0x26741c 168, `Mosquito` 0x297788 70, `Badger` 0x244018 64, `Scorpion` 0x2a4d68 15,
`SmallSpider` 0x2ab450 12; also `Horsemen` 0x271c70 8 and `Zek` 0x2c1f94 4.

## 4. `Creature_init` 0x10a230

Every creature constructor ends with it (69 callers). `tools/ref_creature_init.py` is the
whole function, Observed instruction by instruction:

1. MiniBoss bit (creature flags +0xa8 bit 0): virtual slot 18 (this).
2. Slot 16, the model getter; when it answers a model: slot 16 again,
   `model_getBounds` 0x179400 (model, −1, six outputs); height +0x20 = float(out5 − out2),
   raised to 84.0 when below; draw byte +0x29 = int(height) + 1.
3. `dead` property: creature flags |= bit 32; slot 27 (this, 0x14), the class's
   set-state into death; `anim_snapTopToEnd` (this + 0x114).
4. `change0`..`change31`: +0xe8 = the mask; +0x220 = `model_buildHideMask` (model, mask).
5. Seven weapon-element keys (`FireWeapons` .. `NoMagicWeapons`, getInt): the weapon at
   +0x50, when there is one, gets its slot 2..8.
6. Unless `g_cutsceneActive` (0x44fcd0): `initScript` property: `g_scriptSelectedObj`
   0x4039f8 = this, `script_runByName` 0x1ed694 (text), then 0.

It never stores the object flags +0x0c, the hit points +0x228 or the byte +0x231 itself.
Only slot 18, slot 27 and the script `initScript` names can change them.

**Executed** (`python3 tools/difftest_creature_init.py --cases 400`, seeds 20973 and 7):
the original on a creature block with its own table, every call-out a recording stub;
the property list, flags, model, bounds, weapon and cutscene byte random. Compared: the
calls in order with their first arguments and every store to the block and to
`g_scriptSelectedObj`. 400 cases per seed, 0 mismatches; each of the six paths entered
99-202 times. A changed constant in the reference (the 84.0 floor, the dead bit) fails.

## 5. What a host needs to build a creature the script can read

The script commands that look at an object read, besides its name and position: the
object flags +0x0c, the creature flags +0xa8, the byte +0x231 and the hit points +0x228
(`docs/script-composition.md`; research-script 52984db `docs/script-effects.md`). For a
creature built by `GameObject_ctor`, `Creature_ctor` 0x109d68 (`docs/spec/monsters-1.md`
2) and one of the five class constructors of `docs/spec/monsters-1.md`:

- +0x0c, +0xa8 and +0x231 are the stores of those constructors and of the class's
  set-state 0, provided `Creature_init` takes none of the paths that call the class
  (no MiniBoss bit, no `dead`, no `initScript` outside a cutscene).
- +0x228 is not known: `Creature_setStats` 0x10a620 replaces it (`docs/data-tables.md`
  3.2) from the monster level, the balance row, the player count, the difficulty and one
  draw of the object's own generator.
- The load order is the file order. Each built object draws once from the shared seed in
  `GameObject_ctor`; `Creature_setStats` draws from the object's own generator, not the
  shared one; of the five classes only their own generators are drawn besides
  (`docs/spec/monsters-1.md`).
