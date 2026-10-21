# Arena index 1: Mummy

US `SLUS_209.73` v2.00. The arena table entry `0x5037f0 + 1×4` is the
plain `mummy` type, variant 0. **Executed** on 2026-10-21 in
`tools/difftest_arena_match_classes.py` with reference
`tools/ref_arena_match_classes.py`: constructor, requested set-state and run
values `0x00`–`0x18`, and virtual slot identities on seeds 20973 and 7,
53 comparisons per seed, no mismatches. This is a neutral fixture with no
target, no animation event, a recording holder, and stubbed Creature and
engine services. It compares calls, own/shared seed progression, state and
key direct fields. The observed variant, cast, attack, save and load
behavior in `docs/monsters-2.md` §Mummy is not established by this test.

## Addressed contract

| Item | Address or value | Evidence |
|---|---|---|
| arena class entry | `0x5037f4`, index 1 | Executed lookup |
| factory | `0x159c94`, size `0x480`, constructor `0x298418` | Executed row in `tools/difftest_monster_build.py` |
| class definition | `0x501838` | Observed constructor; fixture variant 0 |
| virtual table | `0x516e48` | Executed constructor and slot check |
| run / set-state | `0x298d18` / `0x29a6f4` | Executed every neutral switch value |
| base takeDamage / onDeath | `0x116638` / `0x10beb8` (slots 2 / 28) | Executed slot check; base difftest |
| destructor | `0x3cbf34` (slot 1) | Observed virtual table; not executed here |
| holder | object `+0x3d0`, Weapon1 table `0x50cf40` | Executed constructor pointer; holder service stubbed |
| base constructor / init | `0x109d68` / `0x10a230` | Recording fixtures, prior base difftest |
| own generator | `GameObject_rand` `0x1509d0`, state `+0x44` | Original body executed |
| animation event writer | `0x118378` | Twelve recorded constructor calls |

In the plain variant the constructor stores `+0x3c8 = 0`, radius
`+0x1c = 15.0`, turn rate `+0xb0 = 1.2`, initial speed `+0xb8 = 0`,
kind byte `+0xb4 = 0x10`, frame `+0xec`, and state 0. These values come
from `Mummy_ctor` `0x298418`–`0x298c7b` and the fixture compares the
listed key fields. The own hide-mask draw sets `+0xe8` to one bit among
bits 0–2; the second own draw tests for a rare weapon modifier. The
tested seeds miss that 10% branch. The base fixture performs one shared
draw to seed `+0x44`; the Mummy constructor makes two own draws and no
further shared draw on either tested seed. `+0x468`, `+0x46c`, and `+0x470`
start at zero.

## State and death path

The active run head follows the same base sequence as Goblin: process
damage `0x110d30`, base run `0x112948`, active check `0x10c0f0`, holder
slot 21, animation step `0x1162b0` when `+0x468` is clear, knockback
`0x115eb8`, and target pick slot 23 `0x10ded0`. The neutral fixture has
no target and no event. Every state switch arm `0x00`–`0x18` executes its
neutral branch with no own or shared draw. States 3, 6–8, 0x12, 0x17 and
0x18 can request `Mummy_setState`; corpse state 0x14 calls
`Creature_deadUpdate` `0x1108a0`. Event-triggered cast, revive, teleport,
and melee arms are outside the comparison.

Each set-state request calls `Creature_filterState` `0x10a9c0`, then the
cone-spell cleanup `0x3cf87c` and `0x11a6d0`. The fixture accepts the
request unchanged. State 0 draws once and stores
`+0xf4 = age + draw % 120`; state 5 draws once and stores
`+0xf4 = age + 60 + draw % 120`; state 7 draws twice for its animation
and delay and stores `+0xf4 = 240 + trunc(secondDraw × 120 / 65536)`;
state 0x17 stores `+0x470 = age + 600`. States 6 and 8 draw once for
their attack clip. State 0x14 draws once for one of the two death clips.
The test compares the draw count, own seed, direct timer fields and
`+0x232` for every requested state.

State `0x14` executes the ordinary corpse branch on this fixture:
`Creature_dropLoot` `0x10f2c8`, animation start `0x16cfe0`, holder
drop slot 11, and `Creature_onDeath` `0x10beb8`, in that order after
the filter and cone cleanup. Their external bodies are recording stubs.
The summoned-Mummy instant-delete branch under creature flag `0x1000000`
is **Observed** in `docs/monsters-2.md` and was not run here. The base
take-damage slot is `Creature_takeDamage` `0x116638`, whose reference-model
difftest passed on seeds 20973 and 7 in `tools/difftest_creature.py --quick`.
Mummy has no damage override. The class destructor and a full corpse
tick/delete path remain unexecuted in this test.
