# Combat runtime, round 6

US `SLUS_209.73` v2.00. Round 6 of `docs/combat-runtime.md`. It is the prose of
`tools/ref_combat_round6.py`. Round 1 through round 5 APIs, pinned vectors and bodies
are unchanged. New behaviour is a method on a subclass of `tools/ref_skills_a.py`.

Evidence labels as in round 1. **Executed** means `tools/difftest_combat_round6.py` ran
the original in `tools/ee_emu.py` and the model agreed. **Observed** means read at the
address. Nothing here was run on a console, in PCSX2 or on the live rig.

## 1. What was already executed

Skills 1–34, 35–68 and 69–101 already have cast, constructor and run comparisons in
`tools/difftest_skills_a.py`, `tools/difftest_skills_b.py` and `tools/difftest_skills_c.py`
(`docs/spec/skills-01-34-executed.md`, `docs/spec/skills-35-68-executed.md`,
`docs/spec/skills-69-101-executed.md`). Combat rounds 1–5 already execute the player
tick, melee, projectiles, DiseaseCloud, potions, Holy Shield, block sparks, and
`MultiFireProjectile_run` `0x2da2bc` (165 of 165). Those modules are not edited here.

The skill difftests left these handlers as call-outs. This round executes them.

## 2. Poison gas

`poisonGasSpell_run` `0x1fd0f0` (*Executed*, 296 of 303). While `g_simFrame` is strictly
below the signed end `+0x5c`:

- the float radius `+0x64` grows by one half when it is strictly below the integer
  target `+0x60`;
- `target / 10`, toward zero, particles spawn when that count is positive (definition
  `0x871088`, a unit-ball point times the radius, a second point times 5, backdate 0);
- on a frame divisible by 30, and only when the owner handle `+0x4c` is set, each object
  in the box position ± `trunc(radius)` whose owner slot 20 returns nonzero takes
  `damage_apply` with flags `0x01000040` and entry `(0x17, low 16 of +0x6c, the same, 0)`.
  Both damage floats are 0. The box capacity argument is `0x40`.

At the end frame, slot 1 with 3 destroys the cloud. A frame that is not the end does not.
An owner handle of 0 skips the damage and does not destroy the cloud.

The seven instructions that do not run are the search for a later descriptor slot. Slot 0
is initialised empty, so the search fills it and the later-slot path is dead. The flags
are `lui 0x100` / `ori 0x40`, which is `0x01000040`.

## 3. Disease corpses

`DiseaseCorpse_run` `0x2ce4a4` (*Executed*, 91 of 91). One box, position ± the integer at
`+0x54` converted to float, capacity `0x40`. An empty box destroys the corpse without
reading `+0x50`. Otherwise half is `+0x50 / 2` toward zero, and half ≤ 0 destroys it the
same way.

A candidate is `(flags & 0x28) == 0x28` with the owner handle set. Skips do not consume
the half. A candidate counts even when `pool_new(0x64)` returns 0. A block is
`DiseaseCloud_ctor(block, victim position, the word +0x50, the owner object)`, and that
owner word may be 0. The walk stops at the end of the list or once the count reaches
half, then slot 1 with 3 destroys the corpse. `DiseaseCloud_ctor` `0x2ce610` stays the
round-3 body; this run only calls it.

## 4. Multi-fire hits

`MultiFireProjectile_onHit` `0x2da610` (*Executed*, 198 of 198) and
`MultiFireProjectile_end` `0x2da928` (*Executed*, 73 of 73). The cast in
`tools/ref_skills_b.py` is a different calculation. The hit recomputes the damage.

An empty owner handle returns. A player owner (object flag `0x40`) returns when the
other object's flags meet `0x01000040`, and when the other has flag `0x20` and the word
at `+0xa8` has bit `0x04000000` (`lui 0x400`). Otherwise the player bounds are slot 13
(stat 0, the level word `+0x68`, the handle address, cap 10) times `0x3c23d70a`, divided
by slot 10 (stat 2, level). Each weapon word of the player record, `+0xd0` and `+0xd4`,
is an integer, multiplied by that scale and rounded half away from zero. The record is
`g_players + slot * 0x4c30`, and the slot is the word at the owner `+0x3c8`. Slot 0 is a
valid record. A stat-2 result of 0 is not exercised.

Any other owner returns when its slot 20 on the victim is 0. Otherwise the minimum is
that same slot 13. Two draws of the bolt's own generator follow. Both are fractions in
`[0, 1)`. The first chooses only the sign of the `0.2` spread; the second is the
magnitude. A positive stat therefore always takes the `+0.5` side. The maximum is the
minimum plus that rounded spread.

The damage is `damage_apply(other, owner, 100000, 0, 0, flags 0x40000, no descriptor, 0;
min, max)`, then `MultiFireProjectile_end(bolt, 2)`. There is no already-ended test in
the hit. The end itself returns immediately when `+0x60` is nonzero, so a second hit
still damages and then the end does nothing.

The end releases the trail at `+0x74` even when that pointer is 0. Reason 0 deletes the
bolt and stores 1. Any other reason draws once: level flag `0x40000` at `0x44fe08`
selects format `0x54f598` and `fx_spawn` 8; its absence selects format `0x54f5b0` and
`fx_spawn` 2. The printed integer is `(draw & 3) + 1`. `res_find` receives the lump
`0x54f560` and the text buffer, not the lump's other name. The sound plays on the bolt
at volume 1, then the same delete and store. The format text is not copied into this
repository.

## 5. Smoke

`SmokeGen_run` `0x31c898` (*Executed*, 132 of 139). `isNearView(position, 1000)`
returning 0 does nothing else. Otherwise `SmokeGen_stepParticles` `0x31cac8` runs; that
step stays a stub. A signed word at `+0x48c` that is ≤ 0, or a frame whose low three bits
are not clear, stops there. The frame test is the unsigned word, not a signed remainder.

Otherwise the box is position ± (the float at `+0x478` times 3), capacity `0x40`. Every
object except the generator, except one whose flag bit 0 is set, and except one without
flag `0x20`, takes `damage_apply` from the generator with flags `0x0100c040` (`lui 0x100`
/ `ori 0xc040`) and entry `(0x26, 1, 1, 0)`. Both amounts are the integer `+0x48c`. The
generator does not delete itself. The same seven later-slot descriptor instructions do
not run.

## 6. Pus Storm

`Pustule_run` `0x30bde0` (*Executed*, 435 of 435). The timer `+0x64` and the burst flag
`+0x6c` are the whole gate. A burst whose timer, as a float, exceeds `0x420eccfb`
destroys the blob. A timer ≥ 301 destroys it. Until the burst, vertical velocity `+0x60`
gains `0xbe4ccab3`, the position steps by the velocity, and three particles of `0x8e7548`
are laid back along that step. Reaching the floor float `+0x54` clears the timer, sets
the burst, plays the sound from `res_find(0x552328, 0x552388)` at volume 1, and plants
ten drops from `terrain_height` of `g_world` plus `0x41400000`, using the blob's own
generator and `cos16` / `sin16`. The burst tick, including the landing tick, then moves
each drop, adds `0xbee1c9f7` to its vertical velocity, and spawns one particle of
`0x8e74f8`. The timer increments. The generator is the object's own word `+0x44`.

## 7. Arena, horn omen and planar steel

`SpellArena_run` `0x305bbc` (*Executed*, 184 of 184). The signed halfword at `0x5038c8`
clears object flag 2 on the creature at spell `+0xc` when the counter is below 61, and
sets it otherwise. Below 30 that is the whole call. From 30, `f = 1 - (counter - 30) ×
0x3bda740d` and `int(23 f)` particles are laid. Every fourth uses `0x8e71e0`; the rest
use `0x8e7190`. Each is a sample of the creature's model, index = the spell draw modulo
the sample count, moved back along `(cos, sin, 0)` of a second draw times `(1 - f) × 10`.
Both tint words, `+0x90` and `+0x98`, become `(0x56, 0x35, 0x21, 0x3d)`. The position
argument is copied onto the stack and not read again. A non-positive particle count still
writes the tint.

`SpellHornOmenEffect_ctor` `0x2fc574` (*Executed*, 39 of 39) and
`SpellHornOmenEffect_run` `0x2fc684` (*Executed*, 514 of 514). The constructor inlines one
shared draw into `+0x10`, stores vtable `0x51ae58`, takes its group from
`particleGroup_create`, and sets the end to the simulation frame plus 600. Until that
end, `a` is `frame - end + 600`. Below 140 the creature tint is `int(a × 0x3bea0ea0 ×
(225, 20, 0, 100))` and the particle count is `int(150 × a × 0x3bea0ea0)`. From 140 the
tint is `(225, 20, 0, 100)` and the count is 150. The group matrix is whatever
`mat34_setPosRotZ` `0x163b30` left on the stack. Each particle is a sample of the
creature's model at the origin with facing 0, plus `0x40400ce4` times a ball point; the
velocity is `0x41f00099` times a second ball point; the definition is `0x8e6c40`. A sample
count of 0 lays none. At the end, spell slot 1 with 3 destroys it.

`SpellPlanarSteelEffect_ctor` `0x2fb728` (*Executed*, 127 of 127) and
`SpellPlanarSteelEffect_run` `0x2fb9b4` (*Executed*, 638 of 638). The constructor inlines
one shared draw, stores vtable `0x51ae28`, and fills the light at `+0x30`: the creature's
position, colour `(0x4b, 0x4b, 200, 0xff)` twice, and `1` divided by a zero radius. The
end is the frame plus 240. The countdown `+0x1c` is `int(the float at creature +0x20 ×
3)`. The orbit angles start at 0 and `0x7fff`. A sound from `res_find(0x551320,
0x551328)` plays at the creature.

Until the end, with `s = sin16(frame × 1000)`, the light follows the creature. The radius
is `(the kind byte + 0x42) + 10 s`. The tint at `+0x90` and `+0x98` is the four rounded
channels in the method. The countdown loses one. The first time that halfword is negative
and `+0x20` is still 0, sixty particles of `0x8e6ba0` spawn 18 above the creature and the
burst sound plays. Two orbit points, 40 out, each get a glow and ten sparks (`0x8e6b00`
six times, `0x8e6b50` four times). Ten sparks of `0x8e6bf0` fall within 40 of the
position argument, and ten sit 5 above `terrain_heightAtPoint`.

## 8. Still open

These are not executed by this round's difftest.

- `StaticFire_run` `0x2c595c`, its two constructors, and `StaticFire_draw` `0x2c65e8`.
  The skill difftest still leaves the constructor as a call-out. The same functions are
  executed on `t3/research-fx` by `tools/difftest_fx_skills.py`; they were not re-run here.
- Spell destructors other than the ones `difftest_skills_a.py` already follows. The
  giant-growth destructor is one of them. Hammer of Wrath states 1 and 2 still have no
  writer.
- Deflection inside the combat runtime, and the bow release composed into that runtime.
  The release itself remains the player difftest.
- Further monster death states. Skeleton states past 1, including the arrow release.
  AntQueen states past 1. Soul's thrown-state hits. Who passes a nonzero silent argument
  to `Player_blockSparks`: the two static callers still pass 0.
- Whether haze drawing is kind 3 only, and which screen axis gets its sine, stay with
  the FX work.

`python3 -m unittest tools.test_ref_combat_round6` is the fixtures only.
`python3 -m unittest discover -s tools -p 'test_*.py'` from the repo root needs stdlib
`dis` loaded first, because `tools/dis.py` shadows it: 877 tests.
