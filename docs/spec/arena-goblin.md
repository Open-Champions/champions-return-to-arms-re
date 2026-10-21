# Arena index 3: Goblin

US `SLUS_209.73` v2.00. The arena class table `0x5037f0 + 3×4` names the plain
`goblin` type. **Executed** on 2026-10-21 in
`tools/difftest_arena_match_classes.py` against
`tools/ref_arena_match_classes.py`, seeds 20973 and 7: 53 comparisons per seed
cover its constructor, each requested set-state and run switch value `0x00`–
`0x18`, and two virtual slot identities. There were no mismatches. The
comparison world has no target, zero animation events, no class resource
payload, and stubbed Creature and engine services. The constructor's own
`GameObject_rand` calls run; its `Creature_ctor` call is a base fixture that
performs the already documented one shared seed draw. Calls, own seed, shared
seed, state and selected direct fields are compared. The full branch model is
**Unknown** from this test. The older `docs/monsters-2.md` Goblin section is
**Observed** prose for roles and attacks, not a new execution claim.

## Addressed contract

| Item | Address or value | Evidence |
|---|---|---|
| arena class entry | `0x5037fc`, index 3 | Executed lookup |
| object factory | `0x159c94`, size `0x498`, constructor `0x26a624` | Executed factory row, `tools/difftest_monster_build.py` |
| class definition | `0x500298` | Observed constructor; fixture selects family 0 |
| virtual table | `0x510260` | Executed constructor and slot check |
| run / set-state | `0x26b27c` / `0x26ccfc` | Executed every neutral switch value |
| base takeDamage / onDeath | `0x116638` / `0x10beb8` (slots 2 / 28) | Executed slot check; base behavior in `tools/difftest_creature.py` |
| destructor | `0x3c4478` (slot 1) | Observed virtual table; not executed here |
| holder | object `+0x3e8`, table `0x50cda0` | Executed constructor pointer; holder service stubbed |
| pre-base / own generator | `GameObject_rand` `0x1509d0`, seed at `+0x44` | Executed, real body |
| base constructor / init | `0x109d68` / `0x10a230` | Recording fixtures; their own prior difftest is `tools/difftest_creature.py` |
| animation event writer | `0x118378` | Five recorded constructor calls |

The plain type selects role 0 at `+0x3d4` and family 0 at `+0x490`.
The constructor stores radius `18.0` at `+0x1c`, turn rate `1.2` at
`+0xb0`, speed `60.0` at `+0xb8`, frame at `+0xec`, state 0 at `+0x232`,
and a holder pointer at `+0x50`. These constants are in the constructor
`0x26a624`–`0x26b1cf` and are compared in the fixture. The role draw sets
the hide mask at `+0xe8`; the model checks `0x82` for seed 20973 and `0x02`
for seed 7 after the base draw. The fixture starts from a zeroed pool block:
one own draw occurs **before** `Creature_ctor`; that base fixture reseeds
`+0x44` with **one shared draw**. Role 0 then uses two own draws, with an
extra own draw when the role roll's bit 0 is set. The total own draws are
4 for seed 20973 and 3 for seed 7. The class's direct path makes no other
shared draw in these two cases; holder element branches are not selected.

## State and death path

The neutral run head calls, in order: `Creature_processDamage` `0x110d30`,
`Creature_run` `0x112948`, `Creature_updateActive` `0x10c0f0`, the holder
update (slot 21 at table `+0xa8`), `Creature_stepAnim` `0x1162b0`,
`Creature_applyKnockback` `0x115eb8`, then pick target (slot 23,
`0x10ded0`). The fixture answers active, no target and no event. Every
switch arm through `0x18` returned or made the reference-modelled service
calls without a seed draw. The no-target arms of 3–8 and 0x17 request
`Goblin_setState`; state 0x14 calls `Creature_deadUpdate` `0x1108a0`.

Every set-state request first calls `Creature_filterState` `0x10a9c0`,
which the fixture accepts unchanged. For this plain recruit: state 0 makes
one own draw and sets `+0xf4 = age + 120 + draw % 60`; state 0x11 sets
`+0xf4 = age + 120` and creature flag `0x200`; state 0x12 makes one own
draw; state 0x17 makes one own draw and sets
`+0xf4 = age + 240 + draw % 240`. The difftest compares these fields and
the resulting `+0x232` state for every request.

State `0x14` executes the class death branch: property lookups
`0x14c880`, world box query `0x14a928`, holder drop slot 11 for both hands,
animation start `0x16cfe0`, `Creature_dropLoot` `0x10f2c8`, and virtual
slot 28 `Creature_onDeath` `0x10beb8`, in the compared order. The external
bodies are stubs here. The separately executed `ref_combat_monsters.py`
`goblinDeath` model covers more of this branch; its observed corpse behavior
is in `docs/spec/combat-monster-death.md` §3.3. `Goblin_run` on a corpse was
entered with state 0x14 and reached `Creature_deadUpdate`, but this fixture
does not model sinking or deletion.

The existing `goblinDeath` model was rerun on seeds 20973 and 7 with
`--quick -k goblinDeath`: 248 and 259 comparisons, zero mismatches; it
refused 52 and 41 inputs outside its declared death-branch domain.

The base take-damage slot is `Creature_takeDamage` `0x116638`, whose
reference-model comparison passed on seeds 20973 and 7 in
`tools/difftest_creature.py --quick`. This class has no damage override.
The holder, cast, melee, bow, variant, animation-event, and interacting
death branches remain unexecuted in this new class difftest. The full
Observed branch inventory is in `docs/monsters-2.md` §Goblin.
