# Numeric delivery for IDs 16, 23, 49 and 55

Status: **Executed, partial**. Original functions ran in `tools/ee_emu.py` on seeds
20973 and 7. `tools/difftest_spell_numeric_r3.py` reports PASS, 869 assertions, 0
failures: 26 `damage_apply` calls, 22 creature `takeDamage` calls, 12 player
`takeDamage` calls, 34 `Player_processDamage` calls, 24 `Creature_processDamage`
calls, 8 `Creature_applyKnockback` calls, 8 stun calls, 4 heal checks and 160
cast-helper payments. No reference API or existing vector changed in this probe.
This is not a playable session.

The family probes still supply the hit arguments. This note adds what those
arguments do in the original damage, heal, stun, payment, player-slot, death
and knock-back functions.

## What was compared

From the worktree root, with unittest imported first:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["tools/difftest_spell_numeric_r3.py"]; runpy.run_path(sys.argv[0], run_name="__main__")'
```

One process runs both seeds. The ignored receipt
`local/spells-r3/numeric-counts.json` stores counts only. A missing or unexpected
private executable exits 2.

| Step | Original function | Comparison |
|---|---|---|
| Hit arguments | ID 16 `0x2ecae8`, ID 23 `0x2f84e4`, child `0x2f71ac`, ID 49 `0x2de7dc` | Existing family rig against its reference, then the numeric fields are kept |
| Damage | `damage_apply` `0x1e8230` | `tools/ref_combat.py`, ps2 arithmetic, events and status words |
| Creature HP | `Creature_takeDamage` `0x116638` | Independent subtraction of the handed amount |
| Stun store | `Creature_stun` `0x118a58`, state body `0x3c2688` | Timer, state and flash colours |
| Heal product | ID 55 constructor store and one `0x2e90b8` add | Grouped float product below |
| Payment | `Player_castSkill` `0x1a42b8` plus the real cost getters | One subtract of the getter's float, and recast 30 |
| Player slot | `Player_takeDamage` `0x1b5330` | Add to pending damage and OR the flags, or drop the hit |
| Player result | `Player_processDamage` `0x1b2cc0` | Record hit points, death, and the player knock-back speed |
| Creature result | `Creature_processDamage` `0x110d30` | Knock-back speed from the flag bits; hit points already set |
| Knock-back step | `Creature_applyKnockback` `0x115eb8` | Zero a player in a net game or PvP mode B; otherwise subtract 2 |

`damage_apply` and `takeDamage` use the combat harness: real modelled bodies, and
recording stubs for sounds, particles, text, the pool and virtual calls. Both-sided
disagreement fails. `Creature_takeDamage` is not used for a victim whose flags
include `0x40`; that object uses the player slot, which this probe does not enter.

## Damage and creature HP

**Executed.** Captured payloads for ID 16 rank 1, ID 16 rank 20 with kind byte
`0x10`, ID 23 rank 1, the ID 23 child, and ID 49 rank 5 were each replayed on both
seeds. Every replay matched the combat reference: return value, take-damage events,
status words and the shared seed. A creature victim then ran `0x116638`. Hit points
at `+0x228` became the previous value minus the handed amount, pending `+0xc8`
stored that amount, and `+0x2dc` stored the flag word.

**Executed boundaries**, same on both seeds:

- An equal direct range of 40, attack 100000, empty descriptor and armour 0 hands
  40 to take-damage. Flag `0x80000` and flag 0 hand the same amount. The amount does
  not change between the two seeds.
- A victim with both creature and player flags (`0x60`) and armour 3000 floors that
  same range to 20. The armour cut is larger than half of 40, so the handed amount
  is the half. This is the amount `damage_apply` passes onward. The player slot
  is the next section, not this creature subtraction.
- Descriptor type `0x16` with both cold values 30 and no direct damage hands 30 when
  cold resistance is 0. With hit points 100 the cold timer is `30 * 60 / 100`. With
  hit points 0 the timer is 60. Cold resistance 1 hands 0 and leaves the timer 0.
  The timer is status word 1, written by `damage_apply` before take-damage.
- Creature flag `0x800` returns 0 and does not change hit points.
- Hit points equal to the handed 40 become 0 after `0x116638`.

**Unknown:** any resistance or armour combination not listed here. Kill credit
inside `Creature_processDamage` is executed in `docs/spec/combat-r6.md` section 3.
Attack 100000 with the armour values
above did not miss; that is not a claim about every armour value. The player
slot, the player death test and the knock-back speeds are the following sections.

## Bash stun

**Executed.** The rank-5 strike's slot-30 argument equals statistic 2 times 60.
`Creature_stun` `0x118a58` stores that frame count at `+0x31c` and calls
`0x3c2688`, which stores state `0x13`. Flash 1 writes `0x3a, 0x9b, 0x9a` at
`+0x90`, `+0x98` and the following pairs, and `0x48` at `+0x96`. Flash 0 leaves
the colours unchanged. Boss rank 1 and a corpse state `0x14` store nothing. The
boss-rank callee is stubbed to the tested rank; the rest of `0x118a58` is original.

**Unknown:** a derived slot 27 that filters the state, and the later stun countdown.

## Healing product

**Executed.** For ID 55 ranks 1 and 20, on both seeds, the owner amount stored at
spell `+0x1c` equals this grouping, and one run adds that same pattern to record
`+0xac`:

`float32(float32(maximum * 0x3c71aa2e) * float32(float32(percent) * 0x3c23d70a))`

`maximum` is the owner record `+0xb0`. `percent` is statistic 0 from the original
getter. The shared seed was set to each test seed before construction; the product
did not change. This is the cached owner amount. The earlier support probe still
holds the recipient, tint and 68-call lifetime results.

## Mana debit and recast

**Executed.** IDs 16, 23, 49 and 55, ranks 1, 2, 5 and 20, both seeds. The skill
metadata read at payment time is kind 0, recast 30 and flag bit 0 clear. The cost
getter (`0x2ed1e4`, `0x2f8af8`, `0x2de60c`, `0x2e8e94`) runs original. The cast slot
is replaced with a stub that returns 0, which is the case the helper still pays.
`Player_castSkill` then:

- subtracts that float from record `+0xc0` when mana is exactly the cost, one
  pattern below it, or 1000;
- stores 30 at player `+0x4ae`;
- leaves mana and a recast of 1 unchanged when recast is already positive;
- leaves mana unchanged for the prediction-copy flag `0x20000`.

Below-cost mana becomes negative. The helper does not refuse it. Aim and rank
answers are scripted; can-use for ID 49 has a shield pointer and a class byte other
than 4. No unknown call was accepted.

**Unknown:** the animation wait before the helper, and mana regeneration on the
following ticks. Those remain the player-tick contract, not a new measurement here.
Payment with the real cast body in the same call is executed in
`docs/spec/combat-r6.md` section 5.

## Player damage slot

**Executed.** `Player_takeDamage` `0x1b5330` is player virtual slot 2
(`docs/player.md`). `strcmp` `0x3b8534` and `net_isLocalSlot` `0x13e150` run.
Every other callee is stubbed, so the holy-shield search returns 0 and no mana
split is claimed. Pending damage `+0xc8` starts at `0x3f800000` and the flag
word `+0x2dc` starts at `0x11`. Amount 40 (`0x42200000`) with flag `0x80000`
stores `fadd` of that sentinel and 40, and stores `0x11 | 0x80000`. Amount 0
stores the same sum again; the word is written, not left over from the previous
call. Object hit points `+0x228`, record hit points `+0xac`, action state
`+0x58c` and knock-back speed `+0x2e8` stay at the values this call found. The
shared seed does not change.

The same sentinels remain, and the write log is empty, when any one of these
is set: `g_recallCountdown` `0x41b51d` = 1, `g_menuInputLockout` `0x41b4fc` = 60,
`g_exitCountdown` `0x4f694a` = 1, or `0x27dd68` stubbed to return 1. That return
is the jump-gate query this caller already tests. It is not a run of the
jump-gate body.

This probe passes no attacker. The hit direction at `+0x2e0` is executed in
`docs/spec/combat-r6.md` section 1.

## Player death

**Executed.** `Player_processDamage` `0x1b2cc0`, every callee stubbed. A
zero-filled block stands in for `+0x24` and the vtable `+0x48`, so presentation
calls from a knock-back bit do not fault; those calls are stubbed. The record
is slot 0 at `0x4d8af0`.

Pending 40 and record hit points 100 store `fsub(100, 40)` in the record.
Object `+0x228` stays 100. Pending damage and the flag word, both nonzero on
entry, are stored as 0. Object flags become `0x160` (`0x60 | 0x100`). State
stays 2. The shared seed advances one `Seed.draw` step.
`game_rebuildAlivePlayers` `0x1e72f8` is not called.

Pending one pattern below 100 (`0x42c7ffff`) leaves a positive record and state
2. Pending equal to the record stores 0, state 4 and object flags `0x169`
(`0x60 | 0x109`), clears pending damage and the flag word, calls `0x1e72f8`
once, and does not draw the seed. The knock-back sentinel is not written.

Pending 0 while the record is already 0 does not kill. State stays 2. The
record address `0x4d8af0+0xac` is absent from the write log and stays 0.
Object flags stay `0x60`, the flag word `0x11` is stored as 0, and the seed
does not change.

## Knock-back

**Executed**, both seeds. The first set bit of `0x40000`, `0x80000`, `0x100000`
and `0x200000` selects the speed stored at `+0x2e8`. `0x40000 | 0x80000` stores
the `0x40000` speed. Each destination starts at `0x3f800000`, so a later 0 is a
store.

`Player_processDamage` uses one table for a survived hit, a killing hit and a
tick with no pending damage: 100, 150, 200, 250 (`0x42c80000`, `0x43160000`,
`0x43480000`, `0x437a0000`). A pending hit still debits the record as above.
No pending damage leaves the record unchanged. State becomes 3, except a
killing hit ends at 4. The seed advances one step. Without one of those bits
the sentinel is not written, and on these two seeds a survived hit leaves state
2. Which draws stagger is executed in `docs/spec/combat-r6.md` section 2.

`Creature_processDamage` `0x110d30` does not subtract hit points. The same four
bits store:

- pending damage while hit points are still above 0: 100, 150, 225, 375
  (`0x42c80000`, `0x43160000`, `0x43610000`, `0x43bb8000`); object flags become
  `0x120`
- no pending damage: 50, 75, 100, 156.25 (`0x42480000`, `0x42960000`,
  `0x42c80000`, `0x431c4000`); object flags stay `0x20`; the flag word is stored
  as 0
- hit points already 0 and pending damage positive: 100, 150, 200, 312.5
  (`0x42c80000`, `0x43160000`, `0x43480000`, `0x439c4000`); object flags become
  `0x2129`

The shared seed does not change. Slot 27 is the zero stand-in here. Kill credit
and the death path with a real slot 27 are in `docs/spec/combat-r6.md` sections 3
and 4.

`Creature_applyKnockback` `0x115eb8` starts from 30 (`0x41f00000`) at scale 1.
`math_cos16` `0x166630` and `math_sin16` `0x1666e0` run. `Creature_moveBy`
`0x113c48` returns 3. A player in a net game, and a player offline in PvP mode
B, stores 0 and does not call move. A player offline, and a creature in a net
game, calls move and stores 28 (`0x41e00000`).

## What a client can implement from this note

- Apply the captured ID 16, 23 and 49 hit arguments through the existing
  `damage_apply` contract, then subtract the handed amount from a creature's hit
  points and pending-damage word.
- For an ID 23 cold descriptor, set status word 1 from the cold amount, hit points
  and cold resistance as bounded above.
- For ID 49, store `statistic 2 * 60` with `Creature_stun` unless the target is a
  boss or a corpse.
- For ID 55, add the grouped heal product once per call, using the cached owner
  amount.
- After a zero cast return, debit the original slot-5 float and set recast to 30,
  including when mana is below the cost. Do not debit when recast is already
  positive or the caster is the prediction copy.
- For a player victim, add the handed amount to pending damage and OR in the
  flags, unless recall, the menu lockout, the exit countdown or a nonzero
  jump-gate query drops the hit. Do not subtract object hit points in that slot.
- On `Player_processDamage`, subtract pending damage from the record. Store 0
  and state 4, store object flags `0x169`, and rebuild the alive list when the
  record result is 0 or below. Leave a zero pending amount, even at 0 hit
  points, unkilled.
- Store the player knock-back speed 100 / 150 / 200 / 250 from the first of
  those four flag bits, including on a killing hit and on a tick with no
  pending damage. For a creature, use the three tables above and do not subtract
  hit points again.
- Step `Creature_applyKnockback` by 2 offline. Store 0 for a player in a net
  game or in PvP mode B.

Do not treat this as campaign combat. Spatial queries and the holy-shield
split are still open. The hit direction, the stagger rules, creature kill credit
and the real cast body inside the helper are in `docs/spec/combat-r6.md`.
