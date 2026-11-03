# Numeric delivery for IDs 16, 23, 49 and 55

Status: **Executed, partial**. Original functions ran in `tools/ee_emu.py` on seeds
20973 and 7. `tools/difftest_spell_numeric_r3.py` reports PASS, 757 assertions, 0
failures: 26 `damage_apply` calls, 22 creature `takeDamage` calls, 8 stun calls,
4 heal checks and 160 cast-helper payments. No reference API or existing vector
changed. This is not a playable session.

The family probes still supply the hit arguments. This note only adds what those
arguments do in the original damage, heal, stun and payment functions.

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
  is the half. This is the amount `damage_apply` passes onward. The player damage
  slot is not called.
- Descriptor type `0x16` with both cold values 30 and no direct damage hands 30 when
  cold resistance is 0. With hit points 100 the cold timer is `30 * 60 / 100`. With
  hit points 0 the timer is 60. Cold resistance 1 hands 0 and leaves the timer 0.
  The timer is status word 1, written by `damage_apply` before take-damage.
- Creature flag `0x800` returns 0 and does not change hit points.
- Hit points equal to the handed 40 become 0 after `0x116638`.

**Unknown:** the player damage slot, `Creature_processDamage` `0x110d30` (death,
knock-back and kill credit), and any resistance or armour combination not listed
here. Attack 100000 with the armour values above did not miss; that is not a claim
about every armour value.

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

**Unknown:** payment with the real cast body in the same call, the animation wait
before the helper, and mana regeneration on the following ticks. Those remain the
player-tick contract, not a new measurement here.

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

Do not treat this as campaign combat. Spatial queries, the player damage slot,
death, knock-back and the real cast body inside the helper are still open.
