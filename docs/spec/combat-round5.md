# Combat runtime, round 5

US `SLUS_209.73` v2.00. Round 5 of `docs/combat-runtime.md`. It is the prose of
`tools/ref_combat_round5.py`. Round 1 through round 4 APIs, pinned vectors and bodies
are unchanged. New behaviour is a new function or a method on a subclass.

Evidence labels as in round 1. **Executed** means `tools/difftest_combat_round5.py` ran
the original in `tools/ee_emu.py` and the model agreed. **Observed** means read at the
address. Nothing here was run on a console, in PCSX2 or on the live rig. The live-fight
names below are the native client's names for those calls.

## 1. AntQueen, Skeleton and Soul

The playable session runs Critter, Gnaw, GnomeNavigator, Mermaid, NPC, Natasla and
Skelight. It stops AntQueen on the call it names `aq_ground`, Skeleton on "slot 25
force argument is not in this class contract", and Soul on the call it names `demon`
at tick 9. The client's slot-25 hook throws that message for every class other than
Gnaw, before it reads the argument. Its decision hook throws "`<Class>` decision call
is not re-executed in the combat world: `<name>`" for a name it has no body for.

### 1.1 AntQueen

`AntQueen_run` `0x236f78`. State 0 calls `AntQueen_fadeBankTracks` `0x2385dc` from
`0x237028`. State 1 calls `AntQueen_updateBank` `0x238448` from `0x2370c0`. Those
two targets are the calls the client names `aq_ground` and `aq_air` (*Executed*,
the run reaches the jal; the bodies are the entries below).

Slot 25's argument is 0. State 0 calls it twice, from return addresses `0x23704c`
and `0x237088`, unless the first call returned nonzero and the signed track count
at `+0x118` is below 4: then the second sight is replaced by a request for state 3.
A count of 4 or more still makes the second call, again with 0. State 1 calls it
once, from `0x2370e4`, and a nonzero return requests state 3. Force 0 is the same
value Gnaw's call passes. The refusal is the class check.

`Creature_updateActive` returning 0 does not stop this run. State 0 still reaches
the fade and both sights (*Executed*). `Skeleton_run` and `Soul_run` do stop: the
same return leaves them before the switch (*Executed*).

`AntQueen_fadeBankTracks` is 30 instructions, all of them executed. The signed
count at `+0x118` selects the tracks. A count at or below 0, including `0xff`,
writes nothing. A track whose clip equals any of the four class-definition words
`+0xb4`, `+0x44`, `+0xbc` or `+0x4c` gets the rate `0xbd088888`. The weight is
left alone.

`AntQueen_updateBank` is 101 instructions. Seed 20973 executes all of them; seed 7
executes 100. Both seeds match. The halfword at `+0x110` becomes a float, times
`0x3b000000`, and is clamped to the closed range from -1 to 1. With `vel` at
`+0x3e0` and `pos` at `+0x3dc`:

```
delta = (w - vel) * 0x3db851eb
pos   = pos + delta
vel   = vel + pos
pos   = pos - pos * 0x3f75c28f
+0x3e4 = int(2*vel * 0x45081000)     toward zero, stored as a halfword
```

The halfword is stored before the track loop, including when the count is not
positive. While `2*vel` is strictly above +0, clips equal to class `+0xb4` or
`+0x44` receive `2*vel` and clips equal to `+0xbc` or `+0x4c` receive integer 0.
Otherwise the first pair receives integer 0 and the second receives `neg.s` of
`2*vel`. The four words are tested in that order and the first match wins. A zero
input takes the second path, and the second pair is stored as -0 (`0x80000000`).
The weight lives at track `+0x08`. The fade writes the rate at track `+0x0c`.

### 1.2 Skeleton

`Skeleton_run` `0x2a6864`, states 0 and 1 (*Executed*). The first slot 25 passes 0
(return addresses `0x2a69d8` in state 0 and `0x2a6a64` in state 1). When that call
returns 0 and the kind word at `+0x3d0` is 4, a second call passes 1 (`0x2a6a0c`,
`0x2a6a98`). Any other kind never makes the second call. A nonzero return from the
first call requests state 3 and skips the second. The melee argument is the same 0
Gnaw passes. The 1 belongs to the bow's second sight.

### 1.3 Soul

`Soul_run` `0x2a9870` calls `Soul_isDemonNear` `0x2ab2b4` when the low nibble of
`g_simFrame` (`0x44fdcc`) XOR the byte at `+0x230` is 0 (*Executed*). The load is
sign-extending; the nibble is the byte's own. State 0 calls from `0x2a99dc`. State
24 (`0x18`) calls from `0x2a9a38`. Frame 9 with that byte equal to 9 is the first
such frame when the byte's low nibble is 9, which is the live session's tick 9.
The word at `+0x44` is the object's own generator. Frame 9 with that word equal to
9 and the byte equal to 0 does not call.

`Soul_isDemonNear` is 58 instructions, all executed. The box is the creature's
position ± 300 (`0x43960000`) on each axis, capacity 128. An empty list returns 0.
Each entry is tested with virtual slot 0, then `Demon_typeinfo` `0x3ca81c`, then
`rtti_typeInfoEquals` `0x3b1250`. The first entry whose type compares equal and
whose object flag 8 is clear returns 1. Flag 8 and a failed compare both move on.
The slot-0 call does not receive the object. On the first entry `a0` is still the
box minimum. On each later entry `a0` is still the previous entry's type word.
The list entry is what the walk loaded. Nothing is stored outside the stack.

## 2. The four angles in Creature_processDamage

`Creature_processDamage` `0x110d30` already matches `tools/ref_creature.py`. These
entries record the register `math_cos16` `0x166630` and `math_sin16` `0x1666e0`
receive, after the delay slot. The sine is given the same register as the cosine.
`cos16` consumes the low 16 bits. The register itself is the full sum (*Executed*).

1. Hit-effect offset, `0x110e60` and `0x110e80`. The sign-extended hit halfword
   `+0x2e0` plus `0x7fff`. Hit 0 gives `0x7fff`. Hit 1 gives `0x8000`. Hit
   `0x8000` gives `0xffffffff`. The pair runs when the radius at `+0x1c` is at
   least 25 (`0x41c80000`) and the pending flags have a bit of `0xd`. These cases
   make no other sine call. 168 of 1515 instructions.

2. Metal sparks, `0x11110c` and `0x11111c`. The sign-extended facing halfword
   `+0x38`, with no add. Facing `0x1234` gives `0x1234`. Facing `0x8000` gives
   `0xffff8000`. The velocity scale is 10 (`0x41200000`). A radius below 25 makes
   no hit-effect pair beside it. 288 of 1515 instructions.

3. First gib pair, `0x111b44` and `0x111b64`, two chunks. Each chunk draws three
   times from the object's own generator: the chunk variant, the push, then the
   angle. The angle is the sign-extended hit halfword plus the sign-extended sum
   of bias `0xe0c0` and `draw mod 16000`.

4. Second gib pair, `0x111ce4` and `0x111d04`, four chunks. The same, with bias
   `0xb1e0` and `draw mod 40000`. The twelve calls are those two sites twice and
   these two sites four times, and the generator word afterwards is the word those
   eighteen draws produce. 304 of 1515 instructions. The push uses an earlier draw
   and is the creature model's existing formula.

## 3. The angle passed to Player_blockSparks

`Player_blockSparks` `0x1b9658`, silent 0. The cosine at `0x1b97dc` and the sine
at `0x1b9800` receive the sign-extended facing halfword `+0x38`, the same register
as the metal sparks (*Executed*, 198 of 408 instructions). Facing `0xc000` gives
`0xffffc000`. These cases make no other sine call. Silent other than 0 is the
round-4 body and does not call either function. Both static callers still pass 0.
Who passes a nonzero silent is unknown.

## 4. Holy Shield's sample points

`SpellHolyShield_absorb` `0x2e8534` is the round-4 body with
`model_getSamplePoint` `0x178e18` and `model_getSamplePointCount` `0x1799c8`
followed instead of stubbed (*Executed*, 206 of 206 instructions of the absorb;
the sample point and `anim_getJointMatrix` `0x16f720` run underneath). Scale is 1.
The state argument is the caster's animation state at `+0x114`, whose first word
is the pose. Position and facing are the caster's. The matrix output is null.
Each of the 241 particles takes `Spell_rand` modulo the sample count and reads
that point. The pose in these cases is not the identity: a missed pose would move
the particle. A pose word of 0 would build a pose (`0x16ed40`); that build is not
this body, and a count of 0 is still refused because the original divides by it.
The light, the group and the slot-10 result stay the round-4 contract. The round-4
entry still stubs the sample point, and its pins are unchanged.

## 5. MultiFireProjectile_run

`MultiFireProjectile_run` `0x2da2bc` is the MaleDarkElf volley, 165 instructions,
all executed. The player-facing MultiFire skill builds `MissileWeapon` objects;
that path is already executed elsewhere. This class is table `0x519128`.

Once `+0x60` is set, the run returns and the age stays. Otherwise, in order: one
trail point at the position (`+0x74` and `+0x10`), the age at `+0x6c` increases
by 1, and `obj_moveAndCollide` is called with the velocity at `+0x54`. Bit 0 of
that result ends the bolt with reason 1, so a result of 1 or 3 both pass 1.
A signed age of 601 (`0x259`) or more ends it with reason 0. An age of 600 becomes
601 and ends. Otherwise ten particles of definition `0x8e5910`. Each one draws a
unit ball from the object's own generator, three draws a try, again while the
squared length is strictly above 1, then one further draw `F`. The velocity is
the ball times 8 (`0x41000000`). The position is the object's position plus that
velocity times `F`. The speed argument is 0. `MultiFireProjectile_end` is the
call the run decides to make; its body is the description in
`docs/spec/skills-35-68.md` and is not re-executed here. `onHit` `0x2da610` is
that same description.

## 6. What was run

`python3 -u tools/difftest_combat_round5.py --seed 20973` and the same with
`--seed 7`. Every entry above, 0 mismatches. The bank's random cases are what
move seed 7 from 101 instructions to 100. The absorb follows the sample point,
the joint matrix and `Spell_rand`. The volley follows `GameObject_rand`.
Everything else recorded is a stub answered the same way on both sides.

`python3 -m unittest tools.test_ref_combat_round5` is the fixtures only.
`python3 -m unittest discover -s tools -p 'test_*.py'` from the repo root: 863
tests.

## 7. Still open

Deflection inside the combat runtime, the bow release composed into that runtime,
and further monster death states. Who passes a nonzero silent to
`Player_blockSparks`. Skeleton's arrow release and the states past 1. AntQueen's
states past 0 and 1. Soul's thrown-state hits. `MultiFireProjectile_onHit`, and
the runs still absent from the difftests: `DiseaseCorpse_run` `0x2ce4a4`,
`SpellPlanarSteelEffect_run` `0x2fb9b4`, `SpellHornOmenEffect_run` `0x2fc684`,
`SpellArena_run` `0x305bbc`, `Pustule_run` `0x30bde0`, `SmokeGen_run` `0x31c898`.
Whether haze drawing is kind 3 only, and which screen axis gets its sine, stay
with the FX work.
