# Touch handlers and the prediction copy

Follows FINDINGS rows G25, G26, V18 and V22 and `docs/issues/live-rig.md` section 10. The
question: which code is run with a machine's **prediction copy** (object flag 0x20000 at
+0xc; it also carries the player flag 0x40) as "the thing that touched me", what that code
changes, and how to stop it in one place.

Evidence marks, as in the rest of the project: **Observed** (read in the executable at the
address given), **Executed** (run in `tools/ee_emu.py`, one function at a time, on state
built by a script), **Ran** (seen in a log of the two-machine rig of
`docs/issues/live-rig.md`), **Inferred**, **Unknown**. "Ran" means Play!, two copies of one
build on one host, the developer LAN start. It is not a PlayStation 2 and it is not PCSX2.
The patch below has **not** been run on PCSX2 or on a console.

## 1. Summary

- Virtual slot 6 ("something touched me", table offset 0x30, function pointer at 0x34) has
  **38 implementations** over the 232 object tables. Two test the toucher for the
  prediction copy (`Gold`, `OniBall`). `Player_onTouch` tests *itself*. Two are empty.
  The other 33 do not look at 0x20000, and 30 of them (three by passing the toucher on to
  another handler) change something every machine simulates when the toucher is a player
  or, for several, any creature (section 2).
- The game's own code calls the slot at **nine places** (section 3). Eight cannot hand a
  handler the prediction copy: one is guarded by the game (`obj_moveWithCollision`,
  0x14d9ac), the rest pass objects that come out of the box query, which never returns the
  copy, or pass a projectile or a prop. **One can: `Creature_moveBy`, the call at
  0x114220.**
- The copy gets into `Creature_moveBy` through `Player_run`'s scripted-control exit:
  `Player_run` 0x1a5030 → (call at 0x1a5604) `Creature_moveToDest` 0x119f38 → (0x119f6c)
  `Creature_moveTo` 0x114510 → (0x114bb0) `Creature_moveBy`. That exit is taken when the
  player's inert byte +0x231 is non-zero and its action state +0x58c is 1. **Ran**: in the
  pair that found G25 this was a cutscene that freezes everything (it leaves inert bit 4 on
  the players) starting while both players were in action state 1; for the 958 ticks of the
  cutscene the real players were not run at all, and each machine's copy ran the monsters'
  walk routine from where its player stood, 31 ticks at a time (section 3.2). An ordinary walk with the stick does
  not get there: it goes through the guarded routine (**Ran**, section 6.1).
- The fix is one changed word at the call site and eight words in unused code: the call at
  0x114220 goes through a stub that returns without calling the handler when the toucher
  has 0x20000 (section 4).
- **Executed**: unpatched, the copy as the mover reaches `Creature_onTouch` and
  `SmallSpider_onTouch`, the creature is flagged and the spider is told to die; patched,
  neither handler runs for a copy and for every other mover the function makes the same
  calls and stores as before (`tools/touchfix_test.py`, 20 checks).
- **Ran**: in a level with small spiders, with every fix section of `tools/rig/fuzz.py` on,
  a player in the scripted walk has its spider killed early on its owner's machine by the
  copy — first difference at tick 1530 (the spider's state, flags and own seed), positions
  from 1543, out-of-sync flags at 1550 and 1554, each machine dropping the other by 1560. With the patch on both machines the same
  script has no shared difference (section 6).

## 2. Survey: every implementation of slot 6

How it was made. `vtables.txt` lists 478 tables; the object family is the 232 with 16, 17,
19, 29 or 39 entries (`GameObject` 16; doors, `Trigger` and the missile classes 17; the
animated props 19; `Vehicle` 29; `Creature` 39). The function pointer at table + 0x34 was read for each;
38 distinct functions result. `tools/touchfix_test.py` checks s1 and s2 repeat this from
the executable. Each function was read in the decompile, the tests named below also in the
disassembly. All rows **Observed**; rows 1 and 24 also **Executed** and **Ran**.

"Shared" means: state that every machine simulates (an object in the world, a handle, an
object's own generator at +0x44). A draw of the shared seed made inside a prediction call
is put back by the prediction loop, which restores the seed, hit points, mana and the
player-table pointer after each call (FINDINGS G3), so a seed draw is not counted here.
Damage "to the toucher" goes through `damage_apply` 0x1e8230 with the toucher as victim;
when the toucher is a copy the damage lands on the copy.

| # | Function | Classes | What it does (a player as toucher unless said) | Tests the toucher for 0x20000 | Shared state changed for a copy |
|---|---|---|---|---|---|
| 1 | `Creature_onTouch` 0x11a418 | 72: `Creature`, `NPC`, the summoned pets and every monster class without a handler of its own | sets bit 59 of the flag word +0xa8 ("touched by a player") when the toucher has 0x40 | no | **yes** — G25 |
| 2 | `MissileWeapon_onTouch` 0x152a18 | `MissileWeapon`, `playerProjectile` | a creature the owner counts as an enemy and that is not on its hit list: chance draws from the shared seed (0x152bec, 0x152f58), then either a deflect effect and the missile deletes itself, or damage to the toucher; state byte +0xcc, hit list +0x124. A player hit by a player's missile only in PvP | no | **yes** — the missile |
| 3 | `AnimatedMissile_onTouch` 0x153900 | `AnimatedMissile` | any toucher whose class is not the owner's: one draw of the missile's own generator, the toucher's take-damage slot, +0x54 = 1 | no | **yes** |
| 4 | `Gold_onTouch` 0x157a9c | `Gold` | sound, the amount +0x80 added to the toucher's record, amount cleared, the pile deletes itself | **yes**, first test (0x157aa0–0x157ab8) | no |
| 5 | `PushPhysicsProp_onTouch` 0x15df4c | `PushPhysicsProp` | adds 1% of the player's velocity (+0x4bc, +0x4c0) to the prop's (+0x7c, +0x80); sets the timer +0xfc of every prop of the class in a box around it | no | **yes** |
| 6 | `Player_onTouch` 0x1beaf0 | `Player` | only when *this* player is not a copy (0x1beb08) and is in action state 9: hands the toucher (a visible creature within 60 units of height) or nothing to its active spell's hit routine 0x2c95f4 | no (it tests itself) | **Inferred yes** — a real player in state 9 would be given the copy as its target; 0x2c95f4 not read |
| 7 | `DummyDamager_onTouch` 0x1ee7b0 | `DummyDamager` | unless the toucher is a creature that does not count the damager's owner an enemy (the toucher's slot 20): damage to the toucher; clears its own amount +0x68 | no | **yes** — its amount |
| 8 | `LooseFire_onTouch` 0x1fcb70 | `LooseFire` | every 20th frame: fire damage to the toucher (by difficulty for a player) | no | nothing of its own |
| 9 | `FireEffect_onTouch` 0x202de0 | `FireEffect` | empty | — | — |
| 10 | `Vehicle_onTouch` 0x208528 | `Vehicle`, `SkulBoat`, `Boat` | links its handle +0x858 to the toucher, unless the toucher is a player whose +0x540 is set | no | **yes** — a handle to the copy |
| 11 | `AutoContainer_onTouch` 0x23e358 | `AutoContainer`, `AutoContainerLP` | unless flagged 8 at +0x124 or the player's +0x47c is set: adds 0.52 × the player's velocity to its own (+0x128, +0x12c) and puts itself on the every-frame list | no | **yes** — the container slides |
| 12 | `beetleProjectile_onTouch` 0x247e1c | `beetleProjectile` | unless the toucher is of one class: row 2 | no | as row 2 |
| 13 | `DiseaseProjectile_onTouch` 0x24a3a8 | `DiseaseProjectile` | if its owner counts the toucher an enemy: damage; +0x88 = 1 on a hit | no | **yes** |
| 14 | `Critter_onTouch` 0x255f7c | `Critter` | **any** toucher: state 0x17 → 0x18; in state 0 or 1 with +0x430 set, target handle +0x234 linked to the toucher and state 0x10 | no test of the toucher at all | **yes** |
| 15 | `Gnome_onTouch` 0x26998c | `Gnome` | reacts to a toucher of one class (another gnome); then calls row 1 | no | as row 1 |
| 16 | `SnowballSpell_onTouch` 0x26de54 | `SnowballSpell` | owner and enemy rules, damage, +0x6c = 1 | no | **yes** |
| 17 | `JunkProjectile_onTouch` 0x27c5e8 | `JunkProjectile` | if its owner counts the toucher an enemy: damage; +0x60 = 1 on a hit | no | **yes** |
| 18 | `LavaBomb_onTouch` 0x283214 | `LavaBomb` | unless already spent or the toucher is of the owner's class: damage; state byte +0xcc | no | **yes** |
| 19 | `FireTrail_onTouch` 0x28c2c4 | `FireTrail` | every 12th frame, unless the toucher is the trail's owner or both are players: fire damage | no | nothing of its own |
| 20 | `VehicleBodySphere_onTouch` 0x28f340 | `VehicleBodySphere` | calls slot 6 of its vehicle (+0x4c) with the same toucher (call at 0x28f35c) | no | as row 10 |
| 21 | `Sparks_onTouch` 0x2900c8 | `Sparks` | while armed (+0x54) and its owner counts the toucher an enemy: allocates an effect object, sound, damage, disarms | no | **yes** — pool block, own state |
| 22 | `Container_onTouch` 0x290da8 | `Container` | as row 11 with the flag at +0x68 and the velocity at +0x6c, +0x70 | no | **yes** — the container slides |
| 23 | `OniBall_onTouch` 0x2946f8 | `OniBall` | a player with skill 0x3b: restores hit points or mana in the record, stamps the ball | **yes**, first test (0x2946fc–0x29471c) | no |
| 24 | `SmallSpider_onTouch` 0x2ab8e0 | `SmallSpider` | not already in state 0x14 and the toucher has 0x40 (0x2ab90c–0x2ab914): set-state 0x14, the spider's death; then row 1 | no | **yes** — G26 |
| 25 | `PoisonProjectile_onTouch` 0x2b1c4c | `PoisonProjectile` | unless the toucher is of its owner's class: +0x98 = 1 when the toucher is not of its own class | no | **yes** |
| 26 | `Torch_onTouch` 0x2b2860 | `Torch` | unless its state byte +0x8a is 2 or 3, every 12th frame: one draw of the shared seed written in line (0x2b295c), fire damage to the toucher | no | nothing of its own (the draw is put back for a copy) |
| 27–37 | the hit handlers of `DiseaseBolt` 0x2caec8, `FireArrowProjectile` 0x2d685c, `ColdArrowProjectile` 0x2d7aac, `PoisonArrowProjectile` 0x2d932c, `MultiFireProjectile` 0x2da610, `ExplodeArrowProjectile` 0x2db4f0, `HolyStrike` 0x2ecae8, `HolyBolt` 0x2f5fb4, `FrostShard` 0x2f71ac, `ShockOfFrost` 0x2f84e4, `PoisonBolt` 0x310028 | one class each | owner and enemy rules through the owner's slot 20, draws of the projectile's own generator, damage to the toucher, a "spent" field of the projectile (the explosive arrow calls its explode routine 0x2db50c) | no | **yes** — the projectile |
| 38 | `GameObject_default_slot6` 0x3c7ea8 | 120: triggers, doors, switches, chests, props, lights, `ItemProp`, `Fire`, `WebTrap`, … | empty | — | — |

So: 38 implementations; 2 empty (rows 9, 38); 2 that exclude the copy as toucher (rows 4,
23); 1 that tests itself and probably matters all the same (row 6); **33 with no test, of
which 30 change shared state** — rows 1–3, 5, 7, 10–18, 20–22, 24, 25 and the eleven of
27–37, three of them (12, 15, 20) by handing the toucher to another handler — and 3 that
only pass damage to the toucher (rows 8, 19, 26). Triggers, chests and item props have no
touch handler of their own: they act through other slots.

Three handlers call another directly, with the toucher they were given: rows 24 and 15
call row 1 (0x2ab93c, 0x269a98) and row 12 calls row 2 (0x247e7c). No handler has any other
direct caller.

## 3. Who calls slot 6

### 3.1 The call sites

Found by scanning the text section for the call shape (the table loaded from +0x48, 0x30
added, the delta and the function loaded, `jalr`); `tools/touchfix_test.py` check s3
repeats the scan. It finds 21 sites: nine in the game's code and twelve in the lobby
window library (0x335b2c–0x34694c), whose window classes happen to keep a table of their
own at +0x48 (9 and 14 entries; not objects). The other slot-6 calls in the executable go
through tables at other offsets (a creature's weapon at +0x50, skills, the network
classes). **Observed.**

| Call | In | Whose handler, who is passed as toucher | Can the toucher be the copy? |
|---|---|---|---|
| 0x114220 | `Creature_moveBy` 0x113c48 | each overlapping object from the box query; **the mover** | **yes, and nothing tests for it** — whenever the mover is the copy (3.2) |
| 0x14d9d0 | `obj_moveWithCollision` 0x14d4b8 | each overlapping object; the mover | no: skipped when the mover has 0x20000 (0x14d9ac–0x14d9b4) — the game's own guard, sound for this routine |
| 0x14d9ec | the same | the mover's own handler; the object it overlapped | no: that object comes from the box query. (For the copy as mover this is `Player_onTouch`, which returns at its own test) |
| 0x150ddc | `obj_moveAndCollide` 0x1509f8 | each overlapping object; the projectile | no: its 26 callers are run functions of projectile and effect classes, each moving itself |
| 0x150df8 | the same | the projectile's handler; the object it overlapped | no: box query |
| 0x15ebc8 | `PushPhysicsProp_run` 0x15e244 | each overlapping object; the prop | no |
| 0x15ebe4 | the same | the prop's handler; the object it overlapped | no: box query |
| 0x18c6e0 | `pauseDebug_hitObject` 0x18c660 | the object under the debug pause sweep; the pointer at 0x4dcec8 (slot 0's player object) | debug pause code (its only reference is from `pauseDebug_sweepObjects`); not reached in play (**Inferred**) |
| 0x28f35c | `VehicleBodySphere_onTouch` 0x28f340 | its vehicle; whatever it was given | only if one of the above gave it the copy |

"Box query" is `world_collectObjectsInBox` 0x14a928, which skips every object with
0x20000 whatever the exclude mask says (0x14aa54; `docs/objects.md`). So an object is
never *found* touching the copy; the copy is a toucher only as the mover of a move
routine, and of the two routines that move a player one is guarded and one is not.

### 3.2 How the copy gets into `Creature_moveBy`

Open since V22. **Observed** first: `Creature_moveBy` is called from 83 places. 75 are in
the run functions of creature classes, which move the creature they are run for; the other
eight are in `Creature_moveTo` (0x114bb0), an unreferenced function at 0x114da0 (0x1153e4),
`Creature_moveToDirect` (0x1158e4), `Creature_fleeFrom` (0x115e74), `Creature_settle`
(0x119e6c), `Creature_applyKnockback` (0x115fc4) and `Skeleton_followLeader` (two). Walking
the direct calls back three levels from there, everything that arrives is one of those
helpers, a creature class's run function — or `Player_run`, twice:

| From `Player_run` | Through | In a net game |
|---|---|---|
| 0x1a5254 | `Creature_applyKnockback` 0x115eb8 → 0x115fc4 | closed: the routine returns at once for any object with 0x40 when `g_networkMode` is set (0x115ef4–0x115f0c) |
| 0x1a5604 | `Creature_moveToDest` 0x119f38 → `Creature_moveTo` 0x114510 → 0x114bb0 | **open**: taken when the inert byte +0x231 is non-zero (test at 0x1a55a0) and the action state +0x58c is 1 (0x1a55ac–0x1a55b8) |

A player's ordinary movement is `Player_move` 0x1b4020 → `creature_moveSimple` 0x1186d8 →
`obj_moveWithCollision`, the guarded routine.

**Ran** (pair 406 of `docs/issues/live-rig.md` 9.2 on the sections it had then — K1, K2,
LAG-1 — first 7,400 frames, with a break point at 0x1a5604 and one on `Creature_onTouch`):

| | Machine A (owns player 1 and the pet) | Machine B |
|---|---|---|
| Cutscene flag 0x44fcd0 | up in ticks 872–2139 and 6514–7471 | the same |
| Players' action state in the first cutscene | 2 on both | the same |
| … in the second | 1 on both, on all 958 ticks | the same |
| Entries at 0x1a5604 in the first cutscene | 0 | 0 |
| … in the second | 992, ticks 6521–7481, **every one with the copy's flag word** (0x000ac060; 31 with 0x040ac060, catching up); inert byte 4; stack pointer 0x01ffc560 | 1,085, ticks 6527–7487, all the copy |
| Entries at 0x1a5604 by a real player | 0 | 0 |
| `Creature_onTouch` with a copy as toucher | 164: 163 on one creature in ticks 7132–7463 (the arena's `Cazic`, by its table in the run of 6.2), 1 on the pet in tick 7481; return address 0x114228; stack pointer 0x01ffc130 | 0 |
| First shared difference | the seed at tick 7541, out-of-sync flag at 7543 — as in section 9.2 there | |

The stack pointers close the chain: 0x01ffc560 less the frames of `Creature_moveToDest`
(0x60), `Creature_moveTo` (0x160) and `Creature_moveBy` (0x270) is 0x01ffc130. The same
0x01ffc130 is in every one of the 164 entries logged in phase 5.

What this says about the game, beyond the caller:

- The second cutscene is one that freezes every creature whose inert byte is 0, players
  included (`cut_freezeCreatureFlag8`: inert bit 4, object flags 0x88000, off the grid).
  Flag 0x8000 means "not run", so the **real** players stand still for the whole cutscene
  (**Ran**: not one entry at 0x1a5604 by a real player, which any run of `Player_run` with
  that inert byte and state would have made).
- The prediction loop runs the copy's run slot directly, whatever its flags. The copy was
  cloned from a frozen player, so it has the inert bit, and `Player_run` takes the
  scripted-control exit. In that exit action state 1 does not mean what it means in play
  (a melee swing, `docs/player.md`); it means "walk to the destination at +0x104 with the
  monsters' helper". Both players were in state 1 when the freeze came.
- So for sixteen seconds each machine's copy ran the walk routine from where its own player
  stood, was thrown away and cloned again every 31 ticks, and touched what was near that
  player — on that machine only. (How far it moved was not measured.) `docs/issues/prediction-copy.md` (row "Scripted walk") and
  `docs/issues/arena-entry.md` (correction 2) had this path as needing state 1 and left it
  there; it is reached.
- In the first cutscene the players were in state 2 and nothing of this happened: whether
  a pair is hit depends on what the players were doing in the tick the cutscene began.

## 4. The fix

One change: **the call at 0x114220 does not call the handler when the toucher is a
prediction copy.** It mirrors the guard the game already has at 0x14d9ac: only the call is
left out; the mover is still pushed out of what it overlaps, the object still goes on the
list handed to the mover's slot 11 and the result still has bit 2.

There is no room in place: the eight words from 0x114208 to the delay slot can be folded
into seven at best, and the test needs three. So the `jalr` becomes a `jal` to a
stub of eight words in the unused function `Cyclops_dropClub` (0x257ab4–0x257b9f), after
the 31 words (0x257ab4–0x257b2f) that sections of the patch file already use there.
Original words read from the executable.

| Address | Original word | New word | Meaning of the new word |
|---|---|---|---|
| 0x114220 | 0060F809 | 0C095ECC | `jal 0x257b30` (was `jalr v1`); the delay slot 0x114224, `addu a0, s0, a0`, stays |
| 0x257B30 | 26080114 | 8CA1000C | `lw at, 0xc(a1)` — the toucher's object flags |
| 0x257B34 | 6A030017 | 00010B80 | `sll at, at, 14` — bit 0x20000 becomes the sign bit |
| 0x257B38 | 6E030010 | 04200003 | `bltz at, 0x257b48` — a prediction copy |
| 0x257B3C | 8E070018 | 00000000 | `nop` |
| 0x257B40 | B0A30007 | 00600008 | `jr v1` — anyone else: the handler, entered exactly as before, returning to 0x114228 |
| 0x257B44 | B4A30000 | 00000000 | `nop` |
| 0x257B48 | ACA70008 | 03E00008 | `jr ra` — for a copy: straight back to 0x114228 |
| 0x257B4C | 3C013F80 | 00000000 | `nop` |

```
patch=1,EE,00114220,word,0C095ECC
patch=1,EE,00257B30,word,8CA1000C
patch=1,EE,00257B34,word,00010B80
patch=1,EE,00257B38,word,04200003
patch=1,EE,00257B3C,word,00000000
patch=1,EE,00257B40,word,00600008
patch=1,EE,00257B44,word,00000000
patch=1,EE,00257B48,word,03E00008
patch=1,EE,00257B4C,word,00000000
```

- **What it changes.** A handler of section 2 is no longer entered with a prediction copy
  as the toucher from `Creature_moveBy`. With the guard at 0x14d9ac and the box query's
  skip, no call site is then left that can do it (section 3.1). The handlers themselves
  are untouched, and a real player — or a monster — as the mover reaches them as before.
- **What could go wrong.**
  - `$at` is used as scratch. It cannot be live: the instruction replaced is a call, and
    the code after 0x114228 reloads what it needs (**Observed**, 0x114228–0x114258 and the
    loop head 0x1140a0).
  - The handler is entered by `jr` with `ra`, `a0`, `a1` and the stack as the `jalr` left
    them; a break point on a handler still shows the return address 0x114228.
  - The copy no longer has done to *it* what a handler does to its toucher: fire, torch
    and damager handlers do not damage it, a gnome or a critter does not react to it. That
    is what already happens on the copy's ordinary walk. The copy's hit points are
    restored after every prediction call anyway (G3).
  - A container or a physics prop is no longer shoved by the copy. Seen from the owner's
    machine nothing is lost that the other machines had.
  - If `Cyclops_dropClub` is called after all, the game runs these words instead of it.
    No jump, call, branch or stored pointer in the image leads into the function
    (`tools/touchfix_test.py` p2).
  - The words 0x257b30–0x257b4f must not be given to another section.
- **Does every player need it?** Each machine that has it stops making changes only it can
  see; a machine without it still makes them and the session can still part there. It adds
  no difference between a machine with it and one without. So: every machine should use it.
- **The section "creatures ignore being touched by the prediction copy"** (the base
  handler rewritten in place, 0x11a41c–0x11a440) covers row 1 of section 2 only. With this
  patch on, that handler is never entered with a copy, from any of the three places it is
  called from; the two can be on together (they were, in the runs of 6.1 and the first
  four of 6.2), and the older one becomes redundant: **Ran** without it for 8,000 frames of
  the pet pair (6.2).
- **Tested** as sections 5 and 6 say: an interpreter on built state, and Play! on the
  developer start. Not on PCSX2, not on a console.

## 5. Executed: `tools/touchfix_test.py`

`python3 -I -B tools/touchfix_test.py` — needs the executable, says so and exits 0 without
it. `Creature_moveBy`, `Creature_onTouch` and `SmallSpider_onTouch` are the game's own
code; the mover and the two overlapped objects (one with the `Creature` table, one with
the `SmallSpider` table) are built by the script; the box query is replaced by one that
returns the two objects, the terrain, water and grid calls return 0, and the spider's
set-state call is recorded instead of run. 20 checks, all pass:

| Check | Mover | Unpatched | Patched |
|---|---|---|---|
| u1–u3, f1–f3 | a prediction copy (flag words 0x00024060, 0x000ac060, 0x040ac060 — all three were seen on the rig) | both handlers run; bit 59 set in both objects; set-state 0x14 called on the spider | **neither handler runs**; nothing is stored in either object; no set-state call; the mover's own stores, the list given to its slot 11 (both objects) and the result (6) are as unpatched |
| u4, u5, f4, f5 | a real player, this machine's (0x00204060) or another's (0x00004060) | the same as for a copy — which is the bug | both handlers run; **every call and every store equals the unpatched run** |
| u6, f6 | a monster (0x20) | both handlers run and change nothing | the same calls and stores |
| s1–s4 | — | the survey: 232 tables, 38 functions; nine call sites; the guard words at 0x14d9ac | |
| p1–p4 | — | the nine original words; the stub lies in `Cyclops_dropClub` and nothing leads there; the delay slot is unchanged; no section of the patch file writes these addresses | |

One function, state built by the script, no second machine: this shows what the code does
with such a mover, not that the state occurs.

## 6. Ran: the rig

Limits as in the header. Everything below was started from the phase-4 states (two
characters with levels and skills, `docs/issues/live-rig.md` 9.1) with the ten sections of
`FIXES` in `tools/rig/fuzz.py` on both machines — the base-handler touch section among
them — and, where it says "patched", the nine words of section 4 as well, applied at the
first frame.

### 6.1 A level with small spiders

`SmallSpider` appears in the object list of one level archive on the disc, `disbonus`
(twelve of them; none of the other 119 archives contains the class name). Both machines
go there by the pending-level write in tick 700. Bus: delay 4, jitter 3, loss 5%; the lead
(`g_localInputFrame` − `g_netFrame`) was 14–15 on machine A and 10–11 on machine B. Break
points on `SmallSpider_onTouch`, `SmallSpider_setState` and 0x1a5604; the state, flags and
own seed of four spiders added to the tick log.

**(a) Walking through them with the stick: no difference, with or without the patch.**
In tick 800 each player is put 20 units from a spider and both controllers then push the
stick out and back in eight directions.

| | Machine A | Machine B |
|---|---|---|
| Spider of player 1 | touched in tick 822 by the real player (return address 0x14d9d8, `obj_moveWithCollision`), set-state 0x14 in tick 822 | the same tick, the same toucher |
| Spider of player 0 | tick 822, real player | the same |
| A third spider (player 0, later) | tick 1212, real player | the same |
| Entries with a copy as toucher | 0 | 0 |

That is the guard at 0x14d9ac doing its work: the copy walks ahead through
`obj_moveWithCollision` and no handler is called for it. A predicted player that merely
brushes a small spider does **not** kill it early. (FINDINGS G26 does not say otherwise,
but the sentence in `docs/spec/monsters-1.md` section 10 about "the copy's own move step"
needs the qualification of section 3.2.)

**(b) The scripted walk, both players walking: diverges without the patch, not with it.**
In tick 1500, identically on both machines, each real player is given what a cutscene's
walk key leaves in a creature — action state 1, walk speed 80 at +0xb8, a destination at
+0x104, inert bit 1 — and a position from which the walk passes through a spider about 55
ticks later. (Written by hand: the animation a real walk key starts is not started, and no
cutscene runs. The walker turns toward its destination as it goes, so the path curves; a
first attempt aimed straight at the spider passed it at more than touching distance on
both machines and showed nothing.) The real players then walk in the tick on both
machines; each machine's copy, cloned at the next rebase, walks the same path ahead of its
player.

| Tick | Machine A | Machine B |
|---|---|---|
| 1530 | **A's copy of player 1 touches the spider at 0x6391c0** (toucher flags 0x00024060, return address 0x114228); set-state 0x14: state 20, flags 0x29, own seed 0x0e4d6465 | spider alive: state 0, flags 0x20, own seed 0x990f148c |
| 1535 | the spider at 0x6396c0 alive | **B's copy of player 0 touches it**; set-state 0x14 |
| 1543 | the real player 0 touches 0x6396c0 and kills it; the real player 1 walks through the spider that is already dead here | the real player 1 touches 0x6391c0, is pushed out of it and kills it; the real player 0 walks through its dead one |
| 1543 | player 1 at x −1198.373 | at x −1197.338; all four position columns differ from here on |
| 1550, 1554 | raises its out-of-sync flag for the other machine (1550) | the same for machine A (1554) |
| 1556, 1560 | drops machine B (1556) | drops machine A (1560) |
| 1691 | the shared seed differs | |

Patched, the same script: **no shared column differs in 1,159 ticks.** Both spiders are
touched in tick 1543 on both machines, by the real players (toucher flags 0x00204060 /
0x00004160), and die there. The copies still take the walk branch (the break point at
0x1a5604 counts them); the stub returns for them.

**(c) Frozen as a cutscene freezes a player: the copy alone kills, and it stays silent.**
In tick 1500 each real player is given object flag 0x8000 (not run), inert bit 4 and
action state 1 — what section 3.2 found in the arena — standing 22 units from a spider
with the destination behind it. The real players never move; only copies arrive at
0x1a5604 (254 and 230 entries, flag word 0x0002c060).

| | Machine A | Machine B |
|---|---|---|
| Unpatched | its copy of player 1 kills the spider at 0x6391c0 in tick 1519; the one at 0x6396c0 lives | its copy of player 0 kills 0x6396c0 in tick 1531; 0x6391c0 lives |
| … to the end of the run | each spider is dead on one machine and alive on the other for 280 and 268 ticks; **no other column differs and no out-of-sync flag is raised** | |
| Patched | no spider is touched; **no shared column differs in 1,139 ticks** | |

So the small spider's handler does what G26 feared, in the two situations in which the
copy reaches `Creature_moveBy`, and the caller patch removes it in both. In (c) nothing
the game compares between machines sees it.

To repeat (rig script commands, the same on both machines; `P` is a player object, found
through `g_players + slot × 0x4c30 + 0x43d8`, and the spiders are found by their table
0x50fd40 at +0x48 in a memory dump taken after the level change): `ontick 700 poke
g_pendingLevel:str16 disbonus`; in tick 800 the positions (+0x10, +0x14, +0x18) of (a);
for (b), in tick 1500, the spider's position plus (63.2, 17.0), the destination (+0x104,
+0x108, +0x10c) 120 lower in x than that, `P+0xb8:f32 80`, `P+0x58c:s32 1`, `P+0x231:u8
1`; for (c) the spider's position plus (22, 3), the destination 82 lower in x, the same
speed and state, `P+0x231:u8 4` and the byte `P+0xd` set to 0xc0. The offsets of (b) were
taken from the path of the first attempt and hold for this script only.

### 6.2 Two of the arena pairs again

Pairs 406 and 402 of `docs/issues/live-rig.md` 9.2 and 10.3 (the arena from the entrance
through the fight, 14,000 frames of seeded random input, no bus delay), each run twice on
the same day from the same script: with the ten sections, and with the ten sections and
the patch. Break points at 0x1a5604 (counted) and at 0x257b48, the stub's "copy" exit
(logged with the touched object's table).

| Pair | Sections | Ticks compared | Machine A against machine B | Level column |
|---|---|---|---|---|
| 406 | ten | 15,330 | no shared column differs | `strife`, `drunare`, `hub2`: fight won |
| 406 | ten and the patch | 15,330 | no shared column differs | the same |
| 402 | ten | 15,320 | bag 2 of player 1 from tick 4932 — the item bytes of 10.2 there, whose section is not among the ten | the same three |
| 402 | ten and the patch | 15,320 | the same column from the same tick | the same |

Nothing else changed, tick for tick: **machine A's log with the patch equals machine A's
log without it in all 45 shared columns on every tick, and so does machine B's, in both
pairs** (15,330 and 15,320 ticks). The logs without the patch also equal the ones kept
from phase 7 (`p7r406`, `p7r402`), so the rig repeats across days.

What the stub did in those runs:

| Pair | Machine | Entries at 0x1a5604, whole run (counted only) | Handler calls the stub left out |
|---|---|---|---|
| 406 | A | 4,524 | **164**, ticks 7132–7481: 163 on the object with table 0x514128 (`Cazic`), 1 on the one with 0x513e08 (`CastBadger`, the pet) in tick 7481; toucher flag words 0x000ac060 and 0x040ac060 |
| 406 | B | 4,980 | 0 |
| 402 | A / B | 4,968 / 4,624 | 0 / 0 |

The 164 are the 164 entries of phase 5 and of section 3.2, now not made. The cutscene flag
was up three times in each pair (in 406: ticks 872–2139, 6514–7471, 10326–13771). In pair
402 the walk branch was taken as often and nothing was within reach.

**The patch in place of the base-handler section.** Pair 406 once more with nine sections —
the ten without "creatures ignore being touched by the prediction copy" — and the patch,
first 8,000 frames: no shared column differs in 7,802 ticks (660–8461), which is past
tick 7541, where the pair parts on shipped touch code (section 3.2). `Creature_onTouch`
was entered 3,171 times on each machine and never with a copy as toucher; the stub left
out the same 164 calls on machine A and none on B; and both machines' logs equal the
ten-section run's on every tick. So the caller patch alone does for the pet what the
base-handler section did (V22).

## 7. For the ledger and the other documents

Proposed, for whoever edits `FINDINGS.md` (this document does not):

| Row | What to record |
|---|---|
| G25 | The open question is answered. The copy reaches `Creature_moveBy` through `Player_run`'s scripted-control exit (call at 0x1a5604 → `Creature_moveToDest` → `Creature_moveTo`, 0x114bb0), taken when the inert byte +0x231 is non-zero and the action state is 1. Ran: in pair 406 that was a cutscene that freezes the players (inert bit 4, object flag 0x8000) beginning while both were in state 1; for its 958 ticks only the copies ran, 992 and 1,085 times through 0x1a5604 |
| G26 | Ran, with its fix. Slot 6 has 38 implementations; 33 do not test the toucher for the copy and 30 of those change shared state. One call site can pass the copy: 0x114220. `SmallSpider_onTouch` killed a spider on the copy's machine only in two forced forms of the scripted walk (first difference tick 1530; in the frozen form silent for 280 ticks); with the call routed through a stub that skips a copy (one word at 0x114220, eight at 0x257b30) neither differs. An ordinary walk does not do it: guarded at 0x14d9ac |
| new (V) | The caller patch on the rig (section 6 of this document): the spider level with and without it; pairs 406 and 402 equal tick for tick with and without it (15,330 and 15,320 ticks), 164 handler calls left out in pair 406; pair 406 in step past tick 7541 with the patch in place of the base-handler section |

Corrections to earlier documents:

- `docs/objects.md` O7 and the symbol note of `Creature_moveBy`: "not used for players'
  own movement as far as read" — it is, in the scripted-control exit (0x1a5604).
- `docs/issues/prediction-copy.md`, rows "Scripted walk" and "Not known" of 3.5, and
  `docs/issues/live-rig.md` 10.4: the caller is the one above; the walk's two conditions
  are met in play.
- `docs/issues/arena-entry.md` correction 2: its "the row's conclusion stands for a
  different reason" does not stand — state 1 is an ordinary state for a player to be in
  when a cutscene begins.
- `docs/spec/monsters-1.md` section 10: "the copy's own move step is what calls slot 6" is
  true of `Creature_moveBy` only; the ordinary step is guarded.

## 8. Not done, not known

- PCSX2, a console, the lobby path, four machines.
- A soak; the patch without the base-handler section beyond the 8,000 frames of 6.2.
- The scripted walk was forced by writing fields. No cutscene was found and run in which a
  player beside a small spider is frozen in state 1; in the arena the thing beside the
  player was a creature and a pet.
- Which destination a frozen copy walks toward (+0x104 of a player is whatever was left
  there) and how far it gets in one cycle were not measured in the arena.
- Rows 2–23 and 25–37 of the survey were read, not executed, and none of them was seen
  entered with a copy on the rig. Row 6's hit routine 0x2c95f4 was not read.
- Other things a copy in the scripted walk does besides touching — `Creature_moveTo`
  asks for routes (`docs/issues/route-marks.md`) — are outside this document.
- The unreferenced function at 0x114da0, which also calls `Creature_moveBy`, was not
  identified.
