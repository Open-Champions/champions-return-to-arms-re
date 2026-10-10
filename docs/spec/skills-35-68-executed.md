# Skills 35–68: what was executed

Companion to `docs/spec/skills-35-68.md`. That document was written from reading only. This
one says which parts of it have since been **executed**: the original machine code of the
skill functions was run, function by function, under `tools/ee_emu.py` (an instruction
interpreter, not a console, and not a running game), beside a Python model written from the
specification, `tools/ref_skills_b.py`, and the two were compared by
`tools/difftest_skills_b.py`. Nothing here was seen on a PlayStation 2 or in an emulator of
one; no skill was cast in a live game.

"Matched" below means: for every call the test made, the model and the original made the
same calls to everything outside the model, in the same order with the same arguments;
stored the same bytes with the same final values (the spell's and the object's own
generator state, the two per-machine generators 0x404460 / 0x404468 and the handle-node pool
included); left the shared seed 0x404464 at the same value, advanced exactly as often as
the model counts; and returned the same value. Floats are compared as 32-bit patterns, bit
for bit, under the interpreter's default floating-point model (`ps2`: add, subtract and
multiply truncate; `docs/issues/dynamic-tests.md` gives its limits). A match is a statement
about the inputs the test covers and nothing more; section 2 says what those are.

Reproduce (needs your own SLUS_209.73; exits 0 without it):

```
python3 tools/difftest_skills_b.py            # everything, about 12 minutes
python3 tools/difftest_skills_b.py --quick    # a tenth of the scenarios, about 3 minutes
python3 tools/difftest_skills_b.py -k cyclone -v
python3 tools/test_ref_skills_b.py            # the model's own logic, no game files
```

## 1. Status per skill

| Id | Name | Status | What was executed |
|---|---|---|---|
| 35 | charge | not run | statistics and mana cost only (see below the table) |
| 36 | darkness | not run | statistics and mana cost only |
| 37 | shock | not run | statistics and mana cost only |
| 38 | groundpound | not run | statistics and mana cost only |
| 39 | convertenemy | not run | statistics and mana cost only |
| 40 | convertundead | not run | statistics and mana cost only |
| 41 | cyclone (and 84) | **matched** | can-use, cast, `SpellCyclone_ctor`, `_run`, `_updateFx`; player, prediction-copy and monster casters; offline and net game; the spin ended by the status bits, by the action state and through the stop clip |
| 42 | harmtouch | **matched** | can-use, cast, constructor, the countdown, `SpellHarmTouch_applyToHit` |
| 43 | firearrow | **matched** | can-use, cast, both constructors, run, hit handler, end; player and monster owners |
| 44 | coldarrow | **matched** | as 43 |
| 45 | poisonarrow | **matched** | as 43 (the gas cloud it leaves is a call-out) |
| 46 | multifire | matched in part | can-use and cast. The arrows are plain `MissileWeapon` objects: the seventeen constructor arguments are compared, their run and hit handler (`docs/spec/skills-35-68.md` S.8) were not modelled. `MultiFireProjectile` (MaleDarkElf only) not run |
| 47 | explodearrow | **matched** | as 43; the explosion with its box query |
| 48 | archery | **matched** | `SkillArchery_getStat0Fraction` at every level; base can-use and cast |
| 49 | bash | **matched** | can-use, cast, constructor, run (wind-up, strike, stun roll, prop fallback, end), `SpellBash_windupFx` |
| 50 | minorhealing | **matched** | cast, constructor, run to the end |
| 51 | ancestralcall | not run | statistics and mana cost only |
| 52 | root | not run | statistics and mana cost only |
| 53 | criticalhit (and 33, 81) | **matched** | can-use, cast, constructor, run, `SkillCriticalHit_critBonusFor` |
| 54 | holyshield | **matched** | cast, constructor, run, `SpellHolyShield_absorb` |
| 55 | healing (and 86) | **matched** | cast, constructor, run for player and non-player owners, PvP mode A on and off |
| 56 | coneoffrost | not run | statistics and mana cost only |
| 57 | shockoffire | not run | statistics and mana cost only |
| 58 | froststorm | not run | statistics and mana cost only |
| 59 | lifetap | **matched** | cast (returns nothing), `SkillLifeTap_getStat0Fraction`, `_getStat1`. The pending-pool logic lives in the damage and player code and is outside this range |
| 60 | Blunt | **matched** | no function of its own: every slot is the base's |
| 61 | Slashing | **matched** | as 60 |
| 62 | strongstance | **matched** | cast, `SkillStrongStance_getStat0`, `SkillStrongStance_trigger` (the phantom it creates is a call-out) |
| 63 | naturalresistance | **matched** | `SkillNaturalResistance_getStat0Fraction` |
| 64 | stunningstrike | **matched** | `SkillStunningStrike_getStat0ForTarget`, `_spawnEffect` |
| 65 | giantgrowth | not run | statistics and mana cost only |
| 66 | planarwind | not run | statistics and mana cost only |
| 67 | shadowstep | not run | statistics and mana cost only |
| 68 | resurrect | **matched** | can-use, target search, `_isSlotBeingRaised`, cast, constructor, run in both modes, `SpellResurrect_onOwnerDeath` |

Twenty of the 34 ids are matched (46 in part). The fourteen marked "not run" were not
reached for lack of time, in the priority order given for this pass; nothing was found that
prevents them. For them only the statistic getters and the mana-cost slot were executed.

Not modelled for any id: `describeRank` (slot 4, menu text), the icon slot, the static
initialisers that build particle definitions, the draw slots, and the destructors (a spell
ending itself is the recorded call of its slot 1).

## 2. What the comparison covers

**Statistics, all 34 ids** — exhaustive: slots 10, 11 (caps 0, 10, 20, −1), 12 (no caster,
player, monster; caps 0 and 10), 13 (empty handle, player, monster) for statistics 0–4 at
levels 0–40, 41, 60 and −1; slot 8 with and without the random spread (spreads 0.1–1.5,
random seeds); slots 5, 14, 15 per level: 109,208 calls, no mismatch. The Skill objects are
the executable's own: the test runs the static initialiser 0x16ac74 and the statistics
set-up 0x1ebca0 first, so no table is embedded in the model or the test.

**Shared machinery** — the Skill base on a synthetic object (negative steps, both tiers);
`handle_link`, `handle_clear`, `handle_removeNode`, `list_push` and the list iterator on
random lists (objects destroyed, nodes linked and removed during a walk);
`creature_addSpell` and `Creature_updateSpells` (newest spell first); `Spell_rand`,
`GameObject_rand`; `Projectile_ctor`; `obj_moveAndCollide` (terrain back-off, the water
splash, overlaps).

**Per skill** — seeded random scenarios: player and monster casters (and the prediction
copy for Cyclone), levels 1–40, the pool refusing a block (5 % of allocations), targets in
and out of range, owners destroyed in flight, the spell or arrow run to its natural end.

What is a stub: every virtual call on a creature, player or prop; `damage_apply`; world
queries; animation; object constructors other than `Projectile_ctor`; the pool; particles,
lights, sound, text. Their answers are scripted; the calls and arguments are compared.
Three things follow from that:

- `GameObject_ctor` and the constructors built on it (`LightEffect`, `GlowingShaft`,
  `poisonGasSpell`, `MissileWeapon`, `StrongStancePhantom`) are stubs whose script makes the
  one shared draw the specification says the real constructor makes. The draw **count** of
  each skill function is therefore executed only up to those call-outs; the draw inside
  them rests on `docs/spec/object-system.md`.
- The order in which a world query returns objects is scripted, not executed.
- A null or stale pointer the original does not test stops both sides (counted as "stopped
  on both"); what the console would do with it is not modelled.

Coverage of the original as executed (basic blocks entered / basic blocks of the function
bodies; full run, seed 3568):

| Part | Functions | Basic blocks | Instructions |
|---|---|---|---|
| shared machinery (Skill base, lists, iterator, spell walk, generators, projectile base) | 23 | 160 of 161 | 1009 of 1016 |
| 41 cyclone | 6 | 62 of 63 | 1063 of 1066 |
| 42 harmtouch | 6 | 24 of 24 | 399 of 399 |
| 43 firearrow | 8 | 49 of 53 | 691 of 699 |
| 44 coldarrow | 8 | 76 of 78 | 1363 of 1369 |
| 45 poisonarrow | 8 | 48 of 48 | 848 of 849 |
| 46 multifire | 3 | 25 of 27 | 394 of 409 |
| 47 explodearrow | 8 | 47 of 47 | 802 of 803 |
| 48 archery | 2 | 2 of 2 | 42 of 42 |
| 49 bash | 6 | 67 of 67 | 707 of 708 |
| 50 minorhealing | 4 | 15 of 15 | 214 of 214 |
| 53 criticalhit | 7 | 58 of 61 | 611 of 617 |
| 54 holyshield | 5 | 22 of 22 | 401 of 401 |
| 55 healing | 4 | 52 of 52 | 617 of 618 |
| 59 lifetap | 4 | 4 of 4 | 76 of 76 |
| 62 strongstance | 4 | 12 of 12 | 255 of 255 |
| 63 naturalresistance | 1 | 1 of 1 | 29 of 29 |
| 64 stunningstrike | 2 | 15 of 15 | 149 of 149 |
| 68 resurrect | 8 | 67 of 67 | 838 of 838 |
| mana-cost slot of the 14 ids not run | 14 | 14 of 14 | 182 of 182 |
| **all** | 131 | **820 of 833** | **10690 of 10739** |

235,931 calls were compared in that run (669 s); none mismatched.

The thirteen blocks never entered: rounding branches that need a negative product
(Cyclone's effect, MultiFire's damage share); the "slot already in use" tails of the
descriptor loops in the FireArrow and ColdArrow hit handlers (the descriptor is always
fresh); in CriticalHit the paths for a negative rank and for a Skill object whose id is not
33, 53 or 81; the free branch of `iter_end`.

## 3. Frame counts settled by execution

Section 1.8 of the specification says most quoted counts assume round-to-nearest and shift
by one frame under the console's arithmetic. Executed under the interpreter's default model
(`ps2`), number of run calls until the thing ends itself:

| What | Executed | Specification |
|---|---|---|
| Skill arrow (43, 44, 45, 47) that meets nothing | ends in run 601, **after moving 601 times** | "age ≥ 601: end"; range quoted as 600 steps |
| HarmTouch unused (0.661 s) | 40 | 40 |
| MinorHealing | 90 | 90 |
| Healing | 68 | 68 |
| HolyShield, N = 10 … 20 s | 60 N + 1 for every N: 601, 661, 721, 781, 841, 901, 961, 1021, 1081, 1141, 1201 | section 54 quotes 600, 660, 721, 781, 841, 901 …; section 1.8 predicts 601, 661, 721 |
| CriticalHit, N = 8 … 13 s | 60 N: 480, 540, 600, 660, 720, 780 | section 53 gives both variants; the truncating one holds |
| Resurrect, N = 1 … 13 s, total | 60 N: 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720, 780 | table in section 68: 61, 121, 181, 241, 300 … 600, 660, 721 |
| Resurrect, call that respawns the target (several players) | 60 N − 14: 46, 106, 166, 226, 286 … 586 | 47, 107, 167, 227, 286 … 586 |

Both rows of the table in section 1.8 are confirmed for every N tried. The statistic table
of section 1.8 was also executed: tier 1 (ranks 1–20) gives the same integer under the
console arithmetic and under round-to-nearest for every statistic of ids 35–68, and tier 2
(levels 1–40) differs in exactly the eleven places listed there, the console value one
lower.

## 4. SB1 — confirmed

FINDINGS row SB1 says `SpellCyclone_ctor` writes a shared animation-clip header before its
prediction-copy test. Executed, three parts (`difftest_skills_b.py -k sb1`):

1. **The stores.** `SkillCyclone_cast` run for a caster with object flag 0x20000: the only
   stores into the clip header are 0x2d1978 (mask byte +0x18 = 1) and 0x2d197c (time +0x14
   = 0.05 s, 0x3d4ccccc); the branch at 0x2d19d0 then skips the voice line, the sound and
   the target list. The clip is what `res_find(class lump, "cyclone1.anm")` returns, so every
   object of that class - the real player, its copy, another player of the same class -
   gets the same header (read, not executed: `res_find` is a stub here).
2. **The reader.** The executable's `anim_advance` 0x16d748 run on a state playing that
   clip reads the four slot times at 0x16d874 and the mask at 0x16d898, and returns the mask
   only on the tick whose window contains the slot time. `SpellCyclone_run` gets that mask
   through `Player_animStep`; on bit 1 it takes 0.05 s off the spin time and moves the slot
   time 0.05 s on **in the header** (0x2d1b64–0x2d1b84).
3. **The consequence.** One player's Cyclone was run from the cast to the tick its stop clip
   starts, the event bits coming from the real `anim_advance` on the shared header, once
   undisturbed and once with a prediction copy of the same class casting Cyclone in between
   (the copy's spell is destroyed at once; only the constructor's stores remain). The spin
   ended later in 9 of 9 cases: clip of 20 ticks, level 1: tick 19 without, 30 or 36 with
   the copy; 30 ticks, level 1: 28 against 49 or 55; 30 ticks, level 12: 88 against 109 or
   115. The clip lengths are stand-ins (the real clip is disc data); the mechanism does not
   depend on them.

So the route is real under execution: on the machine that owns the copy, and only there,
another same-class player's spin lasts longer. Its `Player_move` calls, hits and the end of
action state 6 then fall on different frames on that machine. Still not shown: that two
players of one class do spin within those frames of each other in a real game, and what
the live game does (no skill has been cast on the rig).

G22 (`SpellCyclone_run` starts the stop clip a second time on the "object or copy") was
executed as well: with `g_networkMode` set the second `anim_startBlendInOut` call is made
on whatever `net_objOrGhost` returns - the owner again when that is the owner.

## 5. Corrections to `docs/spec/skills-35-68.md`

Every other rule of the sections listed as matched held as written, constants included.
What execution changes:

| Where | It says | Executed |
|---|---|---|
| Section 68, timing table | run calls 61, 121, 181, 241 for 1–4 s and 721 for 12 s; respawn call 47, 107, 167, 227 | 60 N for every N (60, 120, 180, 240 … 720, 780); respawn on call 60 N − 14 (46, 106, 166, 226). Countdown at 0x312ee0–0x312f00, respawn test at 0x312ddc. The quoted numbers are the round-to-nearest ones |
| Section 54, "Lifetime in run calls" | 600th call for 10 s, 660th for 11 s | 601st, 661st: 60 N + 1 for every N from 10 to 20 (0x2e8428). Section 1.8 already has this right |
| Section 53, duration | both variants given | the truncating one: 60 N (720 and 780 for 12 and 13 s, not 721 and 781) (0x2e7acc) |
| Sections 43, 44, 45, 47, lifetime and range | "600 moving frames", range 600 × speed / 60 | the age test follows the move (FireArrow: move 0x2d66f8, test 0x2d6724; the others alike), so an arrow that meets nothing is moved 601 times before run 601 ends it: range 601 steps |
| Section 41, wind-down | "clip2.event1.mask (clip2+0x28) = 4; clip2.event1.time (clip2+0x24)" | the offsets are right, the name is not: +0x24 / +0x28 is event slot 2 (slot k is at +0x14 + 8k), stores 0x2d1d04 and 0x2d1d0c |
| Sections 42, 49, 54, 62 (particles on model sample points) | the sample point is "draw mod n" | n is the model's sample-point count and is not tested: for a model without sample points the code divides by zero (0x3086b8 in the StrongStance trigger; the same pattern in `SpellHarmTouch_applyToHit`, `SpellHolyShield_absorb`, `SpellBash_windupFx`). The R5900 does not trap; the index is then undefined. Whether any player model has no sample points is disc data, not examined |
| Section 68, run | not stated | the run stores the tint through the target pointer +0x18 with no null test (0x312c88 on). After the respawn the pointer is re-read from the slot's record (0x312e70); a record without an object leaves it null. This is the "allocation-failure path of `player_respawn`" the section lists as not determined, seen from the spell's side |
| Part 2, S.1 | can-use text keys not given | the five bow skills pass different text keys to `text_lookup` (0x54f278, 0x54f360, 0x54f448, 0x54f550, 0x54f648 for ids 43–47); nothing else differs between the five bodies - confirmed |

Confirmed by execution and worth saying because other sections lean on them: the four
shared draws of slot 8 with the first of each pair only choosing the rounding direction
(1.2); HarmTouch's 204 own draws before the damage spread (section 42); the FireArrow hit
handler's missing "already hit" guard - every object overlapped in one frame is damaged,
while the end function runs once (section 43); ExplodeArrow's own draw per object of its
box query, creature or not (SB8); MultiFire's two draws of the presentation generator for a
non-player caster (SB7); the Bash constructor storing the list head, not the entry it
found, as its target (section 49); Resurrect's write of 0.5 to the caster's record +0x4c20
(0x312a28) and of 0x402797 = 1 on every machine every tick; Healing reading
`g_alivePlayers` 0x4f8440 with the count 0x4f8420 re-read each iteration.

### `docs/skills.md`

No new correction. Executed and consistent with its current text: the base slot 5 returns
1.0 (0x3c82a8), LifeTap's and StrongStance's slot 5 call slot 14 and return 0.0; the base
cast (and the casts of 59 and 62) copies the position into its frame and returns 0; the
MultiFire cast builds `MissileWeapon` objects through 0x150ee4; slot 14 returns its level
argument whatever the second argument is.

## 6. Per-machine state

No read of per-machine state was found in the executed functions that the ledger does not
already have. The ones met, by address:

| Read | Where | Ledger |
|---|---|---|
| `g_alivePlayers` / `g_alivePlayerCount` | `SpellHealing_run` 0x2e9158, 0x2e9180; `SkillCriticalHit_critBonusFor` 0x2e7724, 0x2e7744; `SpellCriticalHit_run` 0x2e7e58 (tint only); `SkillResurrect_isSlotBeingRaised` 0x312718, 0x312748 | G18, G19, SA5; `docs/issues/prediction-copy.md` |
| `net_objOrGhost` | `SpellCyclone_run` 0x2d1b04 (G22); `SpellHealing_run`, `SpellCriticalHit_run`, `SpellBash_windupFx`: where particles go and whether a ring particle is kept - the number of own draws does not depend on it | G22, G23 |
| `net_isLocalSlot` → 0x402797 | `SpellCyclone_run` 0x2d218c (120), `SpellBash_run` (60) | `docs/skills.md` (c) |
| presentation generator 0x404460 | `SkillMultiFire_cast` for a non-player caster (damage figure) | SB7 |
| generators 0x404460 and 0x404468 | `SkillStrongStance_trigger` (particles only) | presentation; no row needed |
| the shared clip header | `SpellCyclone_ctor` / `_run` | SB1 (section 4) |

`SpellCyclone_run` reads the two stick values straight from `g_pads[slot]` (+0x14, +0x18,
0x2d1e3c). Inside a lockstep tick that array holds the frame's agreed input
(`docs/netcode.md`, `net_frameLoop` step 2), so this is not a per-machine read; it is noted
because it bypasses the pad pointer `Player_run` uses.

No ledger row and no patch is proposed by this pass.

## 7. Files

- `tools/ref_skills_b.py` - the model. `FUNCTIONS` lists every original function it
  mirrors with its address range; `SKILLS` groups them by id.
- `tools/difftest_skills_b.py` - the comparison; prints, per skill, the functions executed,
  the basic blocks covered and the calls with a mismatch, and the frame counts of section 3.
- `tools/test_ref_skills_b.py` - twelve unit tests of the model's own logic (no game files).
