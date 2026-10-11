# Monster classes, batch 1: the small common enemies

This document is the prose of `tools/ref_monsters_1.py`, a reference model of ten monster
classes of `SLUS_209.73` (US v2.00), written on top of the creature base class
(`docs/spec/creature-tick.md`, `tools/ref_creature.py`) and following the conventions of
`docs/spec/arena-monsters.md` section 0, which are not repeated here.

**Status: work in progress.** Section 1 is the choice of classes. A class's section says
"executed" only once `tools/difftest_monsters_1.py` has run its original constructor, run
and set-state functions under `tools/ee_emu.py` against the model; until then what is
written about a class is a reading (`docs/monsters-2.md`) and is marked so.

## 1. The classes of this batch

The rule: the monsters a player meets most — the common melee and ranged enemies of the
early and middle levels (undead, the orc and goblin kind, spiders and insects, animals, and
their archer variants) — and among those the ones whose run and set-state functions are
smallest first. Not taken: `Horsemen`, `Skelight`, `Zek` (done in
`docs/spec/arena-monsters.md`), bosses, mounts and vehicles, and the friendly or summoned
creatures (`CastBadger`, `Mermaid`, `Gnome`, …).

Sizes are bytes of code from the function index (`ghidra_funcs.tsv`); "run + set" is the
sorting key.

| # | Class | Factory type names | Table | Object size | Constructor | Run | Set-state | Other functions of the class | run + set |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `SmallSpider` | `SmallSpider` | 0x50fd40 | 0x3c8 | 0x2ab450 (320) | 0x2ab5d8 (300) | 0x2ab704 (476) | slot 6 touch 0x2ab8e0 (120) | 776 |
| 2 | `Gnaw` | `Gnaw` | 0x515038 | 0x3c8 | 0x26741c (488) | 0x267654 (952) | 0x267a0c (744) | — | 1696 |
| 3 | `Mosquito` | `Mosquito*` | 0x516a08 | 0x3c8 | 0x297788 (652) | 0x297b30 (1060) | 0x297f54 (888) | lose a part 0x2982cc (332) | 1948 |
| 4 | `Scorpion` | `Scorpion` | 0x50fe88 | 0x3d0 | 0x2a4d68 (712) | 0x2a5068 (1412) | 0x2a55ec (1028) | sever a part 0x2a59f0 (260) | 2440 |
| 5 | `Badger` | `Badger*`, `SnoBadge` | 0x510f30 | 0x3d0 | 0x244018 (776) | 0x244380 (1820) | 0x244aa4 (936) | slot 11 0x244a9c (empty) | 2756 |
| 6 | `Vampire` | `Vampire` | 0x50f968 | 0x3c8 | 0x2b69d0 (516) | 0x2b6bfc (1548) | 0x2b7208 (1244) | — | 2792 |
| 7 | `Ogre` | `Ogre` | 0x517220 | 0x468 | 0x29fad0 (740) | 0x29fe50 (1980) | 0x2a060c (840) | — | 2820 |
| 8 | `WarBoar` | `WarBoar*` | 0x517cf0 | 0x3d8 | 0x2ba03c (772) | 0x2ba3a0 (2232) | 0x2bac60 (852) | slot 11 0x2bac58 (empty) | 3084 |
| 9 | `Gremlin` (archer) | `Gremlin` | 0x515358 | 0x460 | 0x26e08c (896) | 0x26e4c4 (2516) | 0x26ee98 (648) | — | 3164 |
| 10 | `Ghoul` | `Ghoul*`, `GhulBlue*` | 0x5104f0 | 0x3d8 | 0x266088 (880) | 0x266420 (1932) | 0x266c68 (1676) | slot 12 nearby event 0x266bac (188) | 3608 |

The draw functions (0x2ab590, 0x267604, 0x297a14, 0x2a5030, 0x244320, 0x2b6bd4, 0x29fdb4,
0x2ba340, 0x26e40c, 0x2663f8) are presentation and are not part of the model.

The next classes by the same rule, left for a later batch, are in the last section.
