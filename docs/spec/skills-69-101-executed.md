# Skills 69–101: what execution confirmed

Companion to `docs/spec/skills-69-101.md`, which was written from reading only. Here the
same rules are code — `tools/ref_skills_c.py` — and that code is compared with the
original machine code by `tools/difftest_skills_c.py`, which runs the original functions
under `tools/ee_emu.py`. The specification itself is not rewritten; where it turned out
wrong or incomplete, the item is in "Corrections" below.

## What "executed" means here

`tools/ee_emu.py` is an instruction interpreter for single functions. It is not a console
and not the live game (`docs/issues/dynamic-tests.md`); nothing in this file was observed
on a PlayStation 2 or in the live rig. A function is run on objects the test builds in the
interpreter's memory — the 33 skill objects by the game's own constructors and statistics
initialisers — and everything it calls outside the model is a recording stub answered by a
seeded script.

"Matched" means: for every call the test made, the model and the original

- made the same calls to the outside, in the same order, with the same arguments
  (stack-passed arguments included where a callee takes them);
- stored the same bytes outside the stack, with the same final values — which includes a
  spell's own generator (+0x10) and an object's own generator (+0x44);
- left the shared seed 0x404464 the same, advanced exactly as often as the model counted;
- returned the same value.

Floats are compared as 32-bit patterns. Both sides run under the interpreter's
floating-point model, so "bit for bit" means bit for bit under that model, which is an
approximation of the console's unit; the quick run also passes under the interpreter's
three other adder settings (`--fpu ps2g1 | chop | nearest`), i.e. the model follows the
original's order of operations and does not depend on one rounding rule.

Real, besides the skill code: the Skill base slots, `Spell_rand`, `GameObject_rand`,
`Creature_getVisualPos`, the three angle functions, the C library (soft double arithmetic,
`atan2f`), three small matrix functions, and the handle-list functions on lists that live
in objects. Stubs: `damage_apply`, the world queries, the pool, object and effect
constructors, sound, particles, animation, the inventory, and every creature virtual slot
(is-enemy, stun, team, model). The rules behind those stubs are other models' subjects
(`tools/ref_combat.py`, `ref_world.py`, `ref_objects.py`, `ref_anim.py`, `ref_items.py`,
`ref_player.py`).

Numbers of the full run (default seed 6911; `--quick` runs a fifth of the scenarios):
119 properties, 0 failed; 241,689 calls compared; 153 of 154 functions executed and 1,361 of
1,414 basic blocks entered. (The one function not reached inside a compared call is
`handle_clear` on a list that lives in an object: only destructors do that, and they are
stubs; the test driver uses the original for tear-down.) About nine minutes on an idle
machine.

## Status per skill

"Blocks" are basic blocks of the functions listed, covered out of total. The blocks never
entered are named under the table.

| Id | Name | Status | Functions executed (blocks) |
|---|---|---|---|
| all 33 | statistics | matched | slots 8, 10, 11, 12, 13, 14, 15, the default can-use / cast / mana cost, and each skill's own mana-cost function: every id, levels 0–40 and 41, 42, 60, 100, 127, −1, −3, statistics 0–4, caps 0 / 10 / 20 / 25, player / monster / null caster; made-up tables for negative values (53/53) |
| 69 | retribution | matched | can-use, cast, constructor, run to its end, the heal (14/14) |
| 70 | unspokenword | matched | cast, constructor, run through its 30 frames, the hit ring and its stun rolls (57/58) |
| 71 | berserkerrage | matched (helpers) | swing factor, damage factor (10/10). The callers are `Player_run` and `Player_recalcDamage` |
| 72 | summonaxe | matched | cast, the item builder, constructor (room and no room), run (52/54). The inventory functions are stubs |
| 73 | axebandolier | matched (helper) | the weight complement (2/2) |
| 74 | lightquiver | matched (helper) | the weight complement (2/2) |
| 75 | summonarrows | matched | can-use, cast, constructor, run (30/30) |
| 76 | roar | matched | can-use, cast, constructor, run with events, wave, interruption and refund, the hit ring (79/81) |
| 77 | battlecry | matched | can-use, cast, constructor, run with its three events, streamers, cry, stun rolls and aura, the tint, the "affects" query (100/103) |
| 78 | bloodlust | matched | can-use, cast, constructor, the whole run including the particle half, both getters (78/79) |
| 79 | throwing | matched (helper) | the fraction (1/1). The thrown-weapon rule itself is in `Player_recalcDamage` (`tools/difftest_combat.py`) |
| 80 | pusstorm | matched | cast (players and monsters), constructor, run to the last frame, the blob constructor (48/50). `Pustule_run` (the falling blob, presentation) not run |
| 81 | berserkercriticalhit | matched | can-use, cast, constructor, run, tint, the bonus query — also with the class's other two objects, ids 33 and 53 (58/61) |
| 82 | berserkerriposte | matched | cast (returns 0), the counter-attack (17/17) |
| 83 | berserkerdodge | matched (helper) | the fraction, the mana cost (4/4) |
| 84 | berserkercyclone | statistics only | the class code (that of id 41) is not run here; `tools/ref_skills_b.py` models it |
| 85 | shamanroot | matched | can-use, cast, constructor, run through roll and hold (43/45) |
| 86 | shamanhealing | matched | cast, constructor, run for its 68 frames, player and monster owners (52/52) |
| 87 | tagarsinsects | matched elsewhere | `tools/difftest_arena_monsters.py`; here only its statistics |
| 88 | drowsy | matched | cast, constructor, run through all three phases, the fraction (49/49) |
| 89 | poisonbolt | matched | cast, constructor (with and without owner), run with homing, the touch handler, the burst (68/70). `obj_moveAndCollide` and the gas cloud (`poisonGasSpell`, 0x202de8 / 0x1fd0f0) are stubs |
| 90 | summonbadger | matched | can-use, cast (players and monsters), constructor, run (46/47). The badger's own constructor is a stub |
| 91 | raisearmy | matched | can-use, cast, constructor, run, the raisable test, the raise step (77/80). The factory is a stub |
| 92 | battlemage | matched (helper) | the fraction (1/1) |
| 93 | penetratingarrows | matched (helper) | the two fractions (1/1) |
| 94 | spiritshield | matched | can-use, cast, constructor, run through all four phases, both particle helpers, the absorb roll (45/45) |
| 95 | waveofflame | matched | can-use, cast, constructor, run to its end, the hit test (55/57) |
| 96 | frostarmor | matched | can-use, cast, constructor, run to its end, the on-hit function (31/33) |
| 97 | diseaseblade | matched | can-use, cast (players and monsters), constructor, run with the aura and the expiry (118/124) |
| 98 | fireaxe | matched | can-use, cast with and without target, last axe of a stack, prediction copy (34/35). The projectile's flight and hit are `tools/ref_objects.py`'s |
| 99 | coldaxe | matched | the same (34/35) |
| 100 | lightningstrike | matched | cast (players and monsters), constructor, run to the last frame (47/50) |
| 101 | coneofshock | matched | cast, constructor, run (25/27) |

31 of the 33 ids have their own code matched here, one (87) is matched by another test,
one (84) has only its statistics here. No mismatch is left unresolved.

Blocks never entered, and why:

- the "no free slot" and "slot holds another code" arms of the loops that put one entry
  into an all-empty descriptor built on the stack (0x3183f4, 0x318420, 0x31777c,
  0x3177a8, 0x31b744, 0x31b770, 0x30ba84, 0x30bab0, 0x31c128, 0x31c154, 0x2fea84,
  0x2feab0): unreachable, the descriptor has just been emptied;
- the negative arm of round-half-away where the value cannot be negative (0x318d7c,
  0x318ec0, 0x31932c, 0x31947c, 0x319bd8, 0x31a50c) and the full-slot exits beside them
  (0x318de0, 0x318f2c);
- 0x31b3a4 (Lightning Strike's light fade after the spawn end): dead, the spawn end and
  the last frame are the same word there;
- null-`this` exits around a self-destroy (0x2fdec8, 0x301024, 0x3036ac, 0x300eb4,
  0x2e6f50, 0x313c9c) and a few rare combinations the random scenarios did not hit
  (0x30f894, 0x30f8a4 the bolt's hard turn; 0x301b64, 0x3020b4, 0x302818; 0x310820;
  0x313fe4, 0x314048; 0x2e78dc; 0x2e7cac, 0x2e7cbc an id that is none of 33, 53, 81;
  0x2e6a0c).

## Corrections to `docs/spec/skills-69-101.md`

None changes a rule a player would notice; they are what a rebuild needs to get the same
bytes.

1. **72 / 75, the item record (constructors 0x2feb88, 0x2ff87c).** The quantity is a
   **halfword** at record +4; the halfword at +6 is not written by the constructor and
   holds whatever the stack held when the record is handed to `item_parseDescriptor`,
   `player_itemWeight` and `inventory_giveItem`. (Seen as a difference between two runs
   of the test; whether the parser or the inventory code reads +6 is theirs to say.) The
   specification's "quantity (+4)" does not give the width, and its remark that the
   parser keeping the quantity is Inferred still stands — the parser is a stub here.
2. **76 Roar, event 2 (0x300600–0x300640).** `water_test` is asked at the centre **with
   the ground height just found as z**, not at the attach point's height.
3. **76 Roar, after an interruption (the branch at 0x3009f0).** While an interrupted spell
   lingers (0.5 s), each frame makes one own-generator draw and, below 0.170987, a second
   one for a mouth particle. The specification lists no draws there. Presentation.
4. **77 Battle Cry, after an interruption (the branch at 0x3020b4).** An interrupted spell
   lays ten pairs of streamer particles of a second kind every frame until it ends (two
   ball points and two more own draws per pair), and the interruption also clears the
   "streamers on" flag (+0x34). The specification's listing has neither. Presentation —
   no stun roll can follow, the cry never comes.
5. **77 Battle Cry, ground particles.** One own draw is made per particle whether or not
   it is spawned; a particle is *spawned* only where the ground under it is within 72 of
   the copy's height (0x302750–0x302768). The draw count is as specified.
6. **80 Pus Storm, the fall time.** +0x7c is not a stored constant: the constructor
   takes the square root of 2400.096 [0x45160189] at 0x30b14c. Truncated or rounded to
   nearest the result is the 0x4243f68d the specification gives.
7. **90 Summon Badger, the run (0x310cd0).** The particles sit on model sample points
   0, 8, 16, … modulo the point count — a fixed sequence, not drawn; the own generator
   supplies only the ball point (3 draws per try). And the spell is destroyed when its
   handle is **empty**; a handle whose node carries no object makes the run return
   without doing anything.
8. **Shared machinery, slot 8 with "randomise".** Of the two shared draws per bound the
   first only decides the direction of the rounding (through the sign of the value it
   would give); the bound itself uses the second (0x3c8354–0x3c840c).
9. **70 Unspoken Word, level 0.** The particle step `0x10000 / (statistic 1 × 6)` is a
   division with no zero test (0x2fd9b8); at level 0 the divisor is 0. The quotient is
   then not used (the loop runs zero times), so this is harmless — but it is a second
   divide-by-zero site beside SC3's.
10. **81, 85, 86 (class sections).** Confirmed as written, with these additions: Critical
    Hit's run unlinks its light every frame once the spell is older than 2.0 s
    (0x2e7c78) and fades it during the second before; Healing's amount is
    `(max hp × 0.014750047) × (percent × 0.01)` in that association (0x2e9094–0x2e909c);
    Root's cast clears two local lists and its hold phase draws a ball point per particle
    that it then does not use (0x2e6e3c–0x2e6ec8).

Confirmed without change, among the points the specification marks as surprising: the
tier-1-for-everyone lookups (slot 10 / slot 8) in 69, 70, 76–78, 88, 89, 91; the truncated
±20 % for non-player casters in 95 and 100; the stun roll behind the particle draws in 70
and 77, the success roll behind 31 frames of particles in 88, the range draw behind the
decoration draw in 101; the reversed candidate list in 91 and the restored order in 70,
76, 95; the 2 × stat 2 + 1 damage ticks of the storms; Blood Lust's 0.6 armour factor only
while active; Summon Axe's refund path; Fire / Cold Axe taking the modifiers of the
primary weapon into a record inside the skill object.

## Corrections to `docs/skills.md`

1. Skill slot 5, "or 0 for passives": the default mana-cost function 0x3c82a8, which the
   six passives of this range and Riposte use, returns **1.0**; only Dodge's own function
   (0x2e8a88) returns 0.0. (The id table's "base (1.0)" for Riposte is right.) Nothing
   asks a passive for its cost.
2. Slot 8: see correction 8 above — "each bound advances the shared generator twice" is
   right; add that only the second draw sets the value.

## The rule quirks: does execution confirm them?

| Ledger row | Quirk | Result |
|---|---|---|
| SC4 | Frost Armor strikes back with `trunc(damage − factor)` | **Confirmed.** `SpellFrostArmor_onHit` 0x318264 executed 1,602 times with and without attacker, levels up to 127; the descriptor handed to the nested `damage_apply` carries that amount in both value fields. (`tools/difftest_combat.py` reaches the same code through the damage function.) |
| SC5 | Pus Storm's damage comes from the player table for every caster | **Confirmed.** `SkillPusStorm_cast` 0x30aaa8 with monster casters matches a model that asks slot 8 (tier 1) whoever casts; radius, duration and speed come from slot 12 with cap 10 |
| SC6 | thrown-weapon maximum raised by the share of the *new* minimum; Battle Mage's fraction 0 at rank 0 | The fractions are confirmed here (0x304b54, 0x314a78: 0.0 at rank 0). The arithmetic that uses them is in `Player_recalcDamage`, outside this range; `tools/difftest_combat.py` executes it (FINDINGS X10) |
| SC7 | Disease Blade compares the old disease *value* with a frame count | **Confirmed.** Constructor 0x318ad4 and run 0x319068 executed on weapons whose old value lies on both sides of the limit; with the aura's limit 31 an old value of 31 or more refuses the write |
| SC3 | the storms' decoration interval is a divisor that reaches 0 at level 40 | **Confirmed as far as an interpreter can.** Casts at levels 40 and 41 store interval 0; the runs then execute the `div` at 0x31b5ac (Lightning Strike) and 0x30b8ec (Pus Storm) with a zero divisor — no test, no trap. `tools/ee_emu.py` continues with the dividend in the remainder, "as the R5900 is reported to"; the model copies that rule and matches. What a console leaves there is **not** established by this test. Levels 42 and 60 (negative interval) also match |
| SC8 | `SpellRaiseArmy`'s raise step reads `caster + 0x3c8` with no is-player test | **Confirmed** (a byte load, stored to the raised creature's +0x5a) |
| SC2 | gameplay decisions from a generator shared with particle draws | **Confirmed** for 70, 77, 88, 101 (the own seed at +0x10 matches after every run, rejection loops included) and for 80, 100 (the object's seed and the number of decoration objects match). 87 is `tools/difftest_arena_monsters.py`'s |
| SC1 | Tagar's Insects | not repeated here |

## Per-machine state

No read of per-machine state turned up that the ledger does not already have. What the
test exercised both ways, for the record:

- **78 Blood Lust.** The option `g_decalDetail` and the hand positions of
  `net_objOrGhost(owner)` decide how many own-generator draws the run makes, and the
  constructor stores hand points of the copy in the spell (+0x34, +0x40). Run with the
  option 0 / 1 / 2 and with and without a copy standing elsewhere: nothing but particle
  calls, the two stored points and the spell's own seed differs (FINDINGS G23, "a
  contained BloodLust case").
- **77, 81, 86.** `net_objOrGhost` places the ground particles and decides which are
  spawned; the number of draws does not depend on it. 72 / 75 use it for the particle
  group's position only.
- **76, 77, 78, 88.** `net_isLocalSlot` only writes the force-rebase byte 0x402797.
- **82.** The counter-attack's 200 particle steps draw from the presentation generator
  0x404460 only; the two shared draws around them do not depend on it.

One hazard in a shared class, **new as far as this range's documents go** (the class
belongs to ids 33 / 53 / 81): `SpellCriticalHit_run` (0x2e7ecc) and
`SkillCriticalHit_critBonusFor` (0x2e7788) read the player object of **every slot in the
alive list without a null test** — Battle Cry's loop over the same list tests the pointer
(0x3027f8); Healing's player branch (in 0x2e90b8) reads it untested as well. With a listed
slot whose record has no object the test's interpreter faults at those two addresses, in
the original and in the model alike (the test counts that as agreement and prints a note). Whether the live game can have such a slot is Unknown here; FINDINGS G11–G13 are
about that list being stale.

## Proposed ledger rows

For `FINDINGS.md`; the test is an interpreter run, not a live one.

| Proposed id | Claim | Kind | Evidence |
|---|---|---|---|
| SC10 | The skills with ids 69–101 are reimplemented in `tools/ref_skills_c.py` and agree with the original code run in the interpreter — calls, bytes stored, both seeds, results — for 31 ids (87 through the arena test, 84 statistics only); statistics of all 33 ids exhaustively | Observed (interpreter) | `tools/difftest_skills_c.py`; this document |
| SC11 | Critical Hit's run and bonus query dereference the player object of every alive-list slot with no null test | Observed (code and interpreter); reachability Unknown | 0x2e7ecc, 0x2e7788 |
| SC12 | Summon Axe / Summon Arrows hand the inventory an item record whose halfword at +6 was never written | Observed (interpreter: the value differs with what ran before) | 0x2feb88, 0x2ff87c |

## Patches

None proposed.

## Not done

- 84 Cyclone's class code (canUse 0x2d1484, cast 0x2d161c, constructor 0x2d17c8, run
  0x2d1a94, helper 0x2d21e0) with this range's object; its statistics are covered.
- `Pustule_run` 0x30bde0 and the draw functions (0x30bc88, 0x30ed24, 0x30f6b4, 0x311034):
  presentation.
- Every `describeRank` function and the static initialisers.
- Whatever sits behind the stubs: the damage function's use of the descriptors handed to
  it, the inventory's handling of the summoned item, the factory in Raise Army, the
  projectile of the thrown axes, `obj_moveAndCollide`.
