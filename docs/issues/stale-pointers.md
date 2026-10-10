# Stale pointers and address-dependent behaviour

Scope: simulation code whose result could depend on where an object sits in memory — plain
object pointers kept across frames, pointers to the prediction copy kept by simulation
objects, and behaviour that depends on address values or allocation order.

Everything here was read from the executable (SLUS_209.73, v2.00); **nothing was run, and
every patch proposal is untested.** Each statement is **Observed** (read at the address
given), **Inferred** or **Unknown**. The scanner is `tools/rawptr.py`; what it can and
cannot see is in section 7. New names are in `symbols/staleptr.tsv`. `FINDINGS.md` and
`patches/` were not edited; proposed ledger rows and corrections are in section 10.

## 1. Result in short

- **The object pool is the same on every machine except for one block.** The only
  per-machine allocation found is the prediction copy: one 0x590-byte block, so always in
  the 3000-byte size class, and once it exists it is always freed and re-made back to back,
  which hands it the same block again (section 2). No draw function allocates from the pool
  and prediction leaves the free lists as it found them (section 5.1). In the two smaller
  size classes — every monster, projectile, prop, effect and spell — a stale pointer
  therefore reads the same bytes on every machine: wrong behaviour, but the same wrong
  behaviour everywhere. The premise "a freed block is reused by different objects on
  different machines" does not hold for those classes in a level without a one-machine
  object creation (D16, D28, D29, K1 are the known ones).
- **Resurrect (SB3) does read through a pointer to a freed `Player`, on every revival, and
  the read gives the same answer on every machine**: `player_respawn` frees the old object
  and allocates the new one with nothing between, the free list is last-in-first-out, so the
  new object is at the old address and the slot number read is the new object's (section 3).
- **One route from a stale pointer to a per-machine result exists that needs no per-machine
  pool: `handle_link` through a stale pointer** (section 6.5). `Creature_takeDamage` links
  the attacker it is given; if that attacker is a freed block, the link overwrites the
  block's free-list word with the address of a handle node, the pool later hands that node
  address out as an object block, and handle-node addresses do differ between machines. It
  needs an attacker object that was destroyed and *not* re-made at the same address: not a
  respawned player, so not an ordinary arena fight.
- **No simulation object keeps the address of the prediction copy** within reach of direct
  calls; all 17 `net_objOrGhost` results are used on the spot (section 4).
- **No ordering, hashing or keying by object address** was found, nothing walks the pool in
  address order, and the pool reaper picks victims by list position, not pool position
  (section 5).
- For the every-run arena desync this class of bug is therefore **not a candidate that
  static reading supports**. Section 8 ranks what is left and says what to record.

Counts: 478 virtual tables were scanned. 1,720 (class, offset) pairs hold a word that some
member function loads and then uses as a base; merged across inheritance that is about 490
distinct fields, of which about 173 are handles, 63 are `Skill` pointers (static objects),
and 168 passed the "used as an object" tests. 61 of those were read in the decompile for
this document (every field of the arena classes, every `Spell` field that is not owner or
skill, and the object classes of section 6.3); the rest are listed with the scanner's
verdict only and marked so.

## 2. Pool facts the rest depends on

| Fact | Kind | Where |
|---|---|---|
| `pool_free` pushes the block on its class's free list and overwrites only its first word (the object's "who refers to me" head, +0). Everything else stays as the destructor left it: flags, position, hit points, slot number | Observed | 0x150470 |
| `pool_new` pops the head of the first class that is big enough and has a free block, zero-fills it, and passes it to `pool_noteLastBlock`, which stores it in a word nothing reads | Observed | 0x14fdb8; 0x1a1850, 0x4d8a24 |
| The class tables 0x403a10–0x403a4c and the pool memory 0x5f88c0 are referenced only by `pool_init`, `pool_new`, `pool_free`, `pool_countFree`; the handle-node array 0x847268 only by its initialiser and its debug walk | Observed (`tools/gxref.py`) | 0x14fcd8, 0x14fdb8, 0x150470, 0x150410; 0x1a17d0, 0x1a14f0 |
| Requests above 0x500 bytes, i.e. the 3000-byte class: `Player` 0x590 (level load 0x3213f8, `player_respawn` 0x1bd138 / 0x1bd168, cutscene stand-ins 0x19af54 / 0x19afd0, `arena_startWave` 0x306030, `Player_clone` 0x11e894), CloudGiant 0x538, WaveMaker 0x768, boats 0x938 (`world_objectFactory`), `WaveMaker_clone` | Observed: constant size argument at 758 of the 761 `pool_new` call sites; 0x2f7048, 0x2f81e0 and 0x3124b0 were not resolved by the scanner | — |
| `Player_clone` makes exactly one allocation, the 0x590 block; its other calls are `light_link`, the animation-state copies and `handle_initEmpty` | Observed (direct-call reach of 0x11e870) | 0x11e894 |
| A rebase is "destroy the old copy, clone a new one" with nothing between, at the end of `net_frameLoop`, when (more than 30 frames unconfirmed or the force counter is set) and the local player has an object and the game is not paused and the local pause menu is closed | Observed | 0x13b204–0x13b558 (destroy 0x13b330, clone 0x13b540) |
| `g_ghost` is otherwise written only with 0: at net start and by `net_clearGhost`, whose one caller is the main loop after a level load (the pool has just been rebuilt) | Observed | 0x139868, 0x13dcd8, call 0x322e98 |

Consequences (Inferred):

- Once a machine has a copy, re-making it never changes which block it occupies, and never
  changes the order of the rest of the free list.
- Two machines can disagree about the 3000-byte class only if their *first* copy after a
  level load is made on opposite sides of another allocation in that class. The first copy
  is made 1–31 ticks in (E6), later while the local pause menu is open. In `drunare` the
  only other allocation in that class is the stand-in `Player` of the `cazic` cutscene,
  minutes later, so both machines have: players in blocks 0 and 1, the copy in block 2, the
  stand-in in block 3 while that cutscene runs.
- A machine that keeps its pause menu open from the load until `cazic` gets the stand-in in
  block 2 and its copy in block 2 afterwards. Addresses then differ for the length of the
  cutscene; nothing was found that could notice.

## 3. The Resurrect path (SB3), traced

### 3.1 Who calls `SkillResurrect_isSlotBeingRaised` (0x31270c)

| Caller | Runs in | What the result decides |
|---|---|---|
| `SkillResurrect_findTarget` 0x312384, from `SkillResurrect_canUse` 0x3121d0 and `SkillResurrect_cast` 0x312458 | simulation, and for the prediction copy too: the can-use slot is called from `Player_castSkill` 0x1a4358 and from `Player_run` 0x1a5d54, 0x1a7088, 0x1ab618 | whether a dead player's slot is skipped as a target because a living player is already raising it |
| `Player_startSpawnProtection` 0x1b8fbc, called only from `player_respawn` 0x1bd1d4 | simulation | when the answer is 0 the new `Player` gets object flag 0x2 (0x1b8fcc) |

No draw function calls it. Observed (`ps2elf.py xref 31270c`, `xref 312240`).

What it reads (Observed, 0x312734–0x31277c): for each entry of `g_alivePlayers` it takes
that player's object from the table, finds a `SpellResurrect` in its spell list, loads the
spell's target pointer (+0x18) and reads the word at +0x3c8 of the target — the player slot.
It returns 1 on the first match with the slot asked about. Nothing is written.

For the prediction copy the table entry of the local slot is the copy, whose spell list is
empty (G2), so the copy never reaches the read through +0x18; its result only gates the
copy's own cast attempt, and the copy may not cast this skill. No leak. Inferred from G2
and the skill's flag word (skills specification, section 68).

### 3.2 The respawn frame, step by step

All Observed in `SpellResurrect_run` 0x312b30 and `player_respawn` 0x1bd040.

| Step | What happens | Where |
|---|---|---|
| 1 | The spell's run, in the caster's `Player_run`, calls `player_respawn(slot of target, &target.pos, target.facing, -1, -1)`. The position pointer points into the old object | 0x312e40 |
| 2 | `player_respawn` copies the position to its stack **before** anything is destroyed | 0x1bd040 prologue (decompile lines for the 12 bytes at the pointer) |
| 3 | Countdown reset; on the owner's machine only, `net_closeLocalMenus(1)` | 0x1bd0a8, 0x1bd0b8 |
| 4 | The old `Player` is destroyed with "free the block" set. `Player_dtor` clears the table entry, rebuilds the alive list, destroys the attached spells (smaller size classes) and frees the 0x590 block last | 0x1bd0f0; 0x1a1bb8 |
| 5 | `pool_new(0x590)`, then `Player_ctor` at the saved position. No call between step 4 and this one | 0x1bd138, 0x1bd154 |
| 6 | `Player_startSpawnProtection(new object)` calls 0x31270c with the new object's slot. The caster is alive (his spells only run while his hit points are above 0) and is in the alive list rebuilt in step 4; his spell's +0x18 still holds the **old** address | 0x1bd1d4, 0x1b8fbc |
| 7 | Back in the spell: +0x18 is replaced by the table's new object | 0x312e7c |

Why step 6 reads the right thing on every machine (Inferred from section 2): the block freed
in step 4 is the head of the 3000-byte free list, and step 5 pops that head. Nothing a
machine does on its own can come between — the copy is only re-made at the end of
`net_frameLoop`, and step 3 is before the free. So the new object is at the old address, the
read at +0x3c8 returns the slot `Player_ctor` has just stored, the answer is 1 and flag 0x2
is not set. The spell's owner pointer (+0x0c, also the old target) is valid again for the
same reason.

So SB3 as worded ("a freed block's contents depend on pool history, which is not the same
on every machine") does not apply to this read. It is a use-after-free that always lands on
the replacement object.

### 3.3 When the target pointer can be stale in a way that matters

| Situation | Needs | Result |
|---|---|---|
| The body is re-made by another route during the channel: save-point revival (`Savepoint_run` 0x28d618), the leave-request raise (`hud_onMsg` 0x1d8f4c), the arena-mode respawn (0x305830) | a save point near a living player, a leaving player, or the PvP arena mode. None exists in `drunare` with two players | The new object is again at the old address, so the spell now animates and flashes a *living* player every frame and, at the end of the channel, destroys and re-creates him where he stands with stat-1 percent hit points. Same on every machine: a rule bug, not a desync |
| The caster dies during the channel | — | His spells stop running; the frozen spell stays on his object and dies with it at his own revival (`Creature_dtor` 0x117128). A dead caster is not in the alive list, so 0x31270c does not look at his spell |
| A third route frees the body without re-making it (the player leaves the game) | a player leaving mid-channel | +0x18 points at a free block that keeps the old slot number; the run function keeps writing flash colours into it (+0x90…+0x9e, harmless: `pool_new` zero-fills) and calls `Player_animStep` on it. At the end `player_respawn` is called for a slot that has no player. Not traced further; same on every machine as long as the leave is processed on the same tick |

## 4. Pointers to the prediction copy

Question: can a simulation object, or static memory the simulation reads, come to hold the
copy's address beyond the prediction call?

| Source of the address | Checked how | Result |
|---|---|---|
| `g_ghost` 0x4027bc | every reader and writer (`gxref`) | read only by `net_predictLocalPlayer`, `net_frameLoop`, `net_objOrGhost`. Observed |
| The player table entry, pointed at the copy during prediction | store 0x132ba8, restore 0x132ce4 | restored before the call returns (G3). Observed |
| `net_objOrGhost` 0x13e180, 17 call sites in 15 functions | the scanner followed each result: stores of it, stores of values read through it, writes through it, calls it is passed to | **No site stores the pointer.** Writes through it: `SpellCharge_run` 0x2c9004 (action state, to the copy on the owner's machine and to the real player elsewhere; idempotent, G23). Passed on only to `Creature_getVisualPos` (0x2fef08, 0x2ffc00, 0x30346c, 0x3036f8). Observed; agrees with G23 |
| The `this` of code running for the copy: `Player_run` and the 114 (function, argument) pairs its `this` reaches through direct calls | every `handle_link` / `handle_addNode` / `handle_insertNode` whose object is that `this`, every word store of it, every virtual call it is passed to | see the next table |
| Objects found by a world query while the mask lets copies through | — | `world_collectObjectsInBox` skips 0x20000 unconditionally (0x14aa54); every `iter_begin` walk of a grid or run list passes `g_excludeMask`; `world_findObjectsByClass` has one caller, a script built-in (0x142b2c), which runs with the simulation mask. The reaper walks grid B without a mask (0x14b9f0 on), and the copy is not in grid B. Observed |

Where the copy's own address goes (all Observed):

| Site | What is linked or passed | Outlives the call? | Reaches the simulation? |
|---|---|---|---|
| `sound_playOnObject` 0x214334 | a handle to the object in the sound table `g_soundObjHandles` 0x871a90 | yes, until the sound ends or the copy is destroyed (a handle, so it is emptied) | no: audio only |
| `obj_runEveryFrame` from `Creature_run` 0x112ef0 | the copy on the active run list | yes | no: run walks skip it by mask (G6) |
| `obj_moveWithCollision` 0x14d9d0, slot 6 of the touched object | the mover | — | suppressed for the copy (test at 0x14d9ac) |
| `Player_run` 0x1a8f44, slot 12 of the target with kind 2 ("you are being swung at") | the player | — | **guarded**: the call sits inside the `flags & 0x20000 == 0` block. Matters because `Skeleton`, `Orc`, `Goblin`, both dark elves and `Marr` change AI state on kind 2 (0x2a7688, 0x2a2ec8, 0x26c9f4, 0x25aa30, 0x25cfc0, 0x28453c) |
| `Player_run` 0x1aa5b8, slot 12 with kind 3 | the player | — | unguarded but latent: none of the 17 slot-12 bodies acts on kind 3 (the creature bodies test for kinds 0 and 2, the weapon bodies for kinds below 2 and for 2; each read) |
| `damage_apply` → the victim's take-damage slot (0x1e84a8, 0x1ea788, 0x1ea7e0, 0x1eac64), which links the attacker at 0x116740 | the attacker | would | not reached: `damage_apply` returns for a copy attacker (G16) |
| `Projectile_ctor` 0x150ec8, `playerProjectile_ctor` 0x1bf074, `LightEffect_ctor` 0x201d70, `UnholyAura_ctor` 0x2948f4, `GroundPoundEffect_ctor` 0x2c761c, `poisonGasSpell_ctor` 0x202e9c, `StrongStancePhantom_ctor` 0x161a20: owner handles | the creator | would | the `pool_new` sites of `Player_run` that create projectiles are inside `flags & 0x20000 == 0` tests (decompile of 0x1a5030, lines 920–954, 1189–1229 and 2315); the six of the older ability paths are not (prediction-copy.md O1–O6, reachability D16) |
| path requests 0x184ed8 … | requester handle | would | scripted walk only; not reachable for the copy (prediction-copy.md 3.1) |

Not covered: the 206 virtual call sites reachable from `Player_run` were followed only where
`this` is an argument (above) and where prediction-copy.md 3.2 followed them.

**Result: no simulation object was found that keeps the copy's address.** The copy's
address lives in `g_ghost`, in handle nodes (its grid link, its run-list link, sound
handles), and for the length of the call in the player table.

## 5. Address values and allocation order

### 5.1 Does any machine allocate what the others do not?

| Candidate | Check | Result |
|---|---|---|
| Draw code | direct-call reach of the draw slot of all 166 distinct draw functions (slot 5 of every object table, slot 3 of every `Spell` table): 583 functions | one `pool_new`, in `fx_spawn` case 5 (0x1f0bd0), reached through `fx_modelStatusEffects`, which only passes type 0x11 (0x1f6ac8, decompile line 932). **No draw-side allocation.** Observed for direct calls; draw tasks that are not object draw functions (HUD, inventory, cutscene) were covered only by the name check below |
| Prediction | direct-call reach of `Player_run`: 9 functions call `pool_new` | all guarded or unreachable for the copy (section 4, last rows), plus the transient spell of the copy's cast, which is popped and pushed back within `Player_castSkill` (0x1a4598 → 0x1a45d0), leaving the free list unchanged |
| Code that tests the local slot, the camera, an option or a cosmetic seed and also allocates | all 368 functions that call `pool_new`, intersected with `net_isLocalSlot`, `isNearView`, `net_objOrGhost`, the camera globals, `g_decalDetail`, both cosmetic seeds | 19 functions. Read: `damage_apply` (camera read at 0x1e832c is before and unrelated to its six allocations), 0x1c2120 and `inventory_dropItem` (the local-slot test does not enclose the allocation), `player_respawn` (section 3). `FireBomb_run` / `FireBomblet_run` are D29. `Creature_processDamage` / `Player_processDamage` are B8. The rest use the cosmetic seed for effects next to a shared allocation; not re-read |
| Menus | every site that allocates 0x590 | none in menu code; the inventory's player model does not use the pool |

So the pool sequence in the two smaller classes is lockstep state. Inferred from the checks
above; the residual risk is an allocation behind a virtual call from draw or HUD code.

### 5.2 Ordering compares, arithmetic and keys on addresses

`rawptr.py ptrmath` reports signed and unsigned compares and differences of two values that
the same function uses as bases, and shifts, masks, multiplies and divides of a value the
function treats as an object.

| What | Result |
|---|---|
| Ordering compares of two pointers, game code 0x100000–0x323000 | 28 candidates. Real pointer compares: `pool_free` (which class an address belongs to, 0x150480, 0x15049c) and `mem_free` (heap coalescing, 0x1501f4, 0x150238). The rest are loop bounds or timers in a reused register (read: `cut_advance`, `player_packRecord`, `AutoPropLP_run`, `CloudGiant_run`, `FemaleDarkElf_run`, `WoodElfSoldier_run`). **None orders objects by address.** Observed for what the tracker can see |
| Shifts, masks, multiply/divide on an object pointer | 159 hits in the whole executable (with the compares), all display-list arithmetic, flag tests on a mis-typed flag word, or null tests. None hashes an object address |
| Pointer used as a key | (a) `SpellTag` (+0x18 = caster, +0x1c = skill id): `creature_findSpell` 0x11a788 matches by equality, so a tag left by a caster that has been destroyed matches whatever object is later built at that address. (b) `FrostShard` +0x78: "the creature the parent bolt already hit", compared for equality in `FrostShard_onHit` 0x2f71e4. (c) the name table stores object pointers under a hash of the *name* (0x14bce0). Equality only; aliasing after reuse is the same on every machine |
| Stored handle-node pointers | none: no result of `handle_link`, `handle_addNode` or `handle_insertNode` is stored or passed on anywhere; all 20 `handle_removeNode` calls take the current value of a list head. Observed |
| `libc_qsort` | one call, a total order on scores (runtime.md P7); not re-read |

### 5.3 Iteration in pool or free-list order; the reaper

- Nothing outside the four pool functions reads the pool tables or walks the pool memory
  (section 2). Observed.
- The reaper (`runObjects` 0x14b9b0–0x14bb18, decompile lines 32–73), Observed: when the
  sampled free count is below 300 it visits 16 cells of grid B chosen from the frame
  counter, walks each cell's list **from the head, directly, without an iterator and without
  the exclude mask**, and destroys the first object with flag 0x1000 on the spot. The victim
  is decided by list position — link order, which is the order of movement calls — not by
  pool position. Link order is lockstep state; the copy is never in grid B.
- The only per-machine input is the trigger: `pool_countFree` counts the copy's block, so a
  machine without a copy is one block ahead (D21, objects.md O1). No new finding.
- The reaper frees immediately, so an object reaped in step 3 of `runObjects` is a freed
  block for every object that runs in the same tick. Holders of plain pointers to grid-B
  props are the risk; none was found among the fields read (section 6).

### 5.4 "First free slot" searches whose result the simulation can see

Not scanned systematically; the tracker does not recognise table searches. Known ones:

| Table | Visible to the simulation? | Kind |
|---|---|---|
| Beam table (`beam_create` 0x193088) | yes: CloudGiant tests a beam handle (D28); `Cazic_deathEffects` stores three (0x24cc20, 0x24cc8c, 0x24ccf8) and was not read for a test of them | Observed stores; D28 |
| Handle-node free list 0x864ea8 | node addresses differ per machine (draw-side light links D31, the copy's links, sound handles); visible only through 6.5 or exhaustion | Inferred |
| Sound-object handles 0x871a90 | audio only | Observed |
| Path queue 0x7d43a8 (ring, not a search) | requester by handle; the output buffer is a plain pointer into the requester, protected by the handle test when a search starts (0x184798). In a net game every search finishes in the pass that starts it (D5), so the buffer cannot go stale; offline a time-sliced search can outlive its requester | Observed; offline hazard Inferred |
| `WoodElfSoldier` archer handles 0x503370, `GnawSpawn` child handles, the wraith list 0x503680 | filled by simulation code in lockstep order | from monsters-2.md, not re-read |

## 6. Raw object pointers

### 6.1 What a stale pointer can do

| Use through the pointer | What happens when the pointee was destroyed | Per machine? |
|---|---|---|
| Read from a block that is still free | the dead object's last state: flags (often with the dead bit), position, hit points, slot. +0 is the free-list link | no |
| Read from a block that has been handed out again | the new object's state; the holder now follows or damages an unrelated object | no (same pool sequence everywhere), except a pointer into the 3000-byte class on machines whose copy sits in a different block (section 2) |
| Virtual call | on a free block the table pointer is the base `GameObject` table (0x5122a8, left by the destructor chain): slots up to 16 are the defaults, a higher slot runs off the table | no |
| Write | lost when the block is zero-filled at the next allocation, or lands in the new object | no |
| Equality compare | may match the new object | no |
| **`handle_link` with it as the object** | section 6.5 | **yes** |

### 6.2 The arena classes

Every word store of a non-constant value into `this`, and every word of `this` used as a
base, in the own functions of each class and everything their `this` reaches (Observed with
the scanner, then read).

| Class | Handles (offsets) | Plain object pointers | Notes |
|---|---|---|---|
| `Player` | +0x234, +0x238, +0x2e4, +0x360, +0x364, +0x3d8…+0x438 (step 0x18), +0x4b8, +0x588 | **+0x540** the vehicle the player rides: set by `Vehicle_board` 0x20903c; virtual call in action state 0xd (0x1a5ee8), also read by `Player_takeDamage` 0x1b5398, `Player_interact` 0x1b2674, two script built-ins and the camera | +0x544…+0x558 are resources (`res_find`). No vehicle in `drunare`. `Player_clone` copies +0x540 (0x11f12c / 0x11f140), so the copy can call through it for up to 30 ticks after the vehicle is gone; how a vehicle's destruction clears its riders was not read — vehicle levels only |
| `Horsemen` (knights) | +0x234, +0x238, +0x2e4, +0x360, +0x364, +0x3c8 | none | +0x470 variant, +0x474 timer are numbers |
| `Skelight` (summoned skeleton) | +0x234, +0x238, +0x2e4, +0x360, +0x364 | none | +0x460 is a float (saved and loaded as one, 0x2a9154) |
| `Zek` (Rallos) | the same plus +0x460 | none | |
| `Cazic` (avatar) | the same | none | +0x3d8…+0x3e0 are beam handles (5.4) |
| `DiseaseBolt` | +0x4c owner, +0x54, +0x58 | none | +0x5c is the `Skill` |
| `FireStorm`, `FireStormFlare` | +0x4c owner | none | remaining stores are numbers; no field is used as a base |
| `SpellSummonSkeleton` | +0x18 the skeleton | owner +0x0c = the knight | attached to the knight (variant 2) or to nothing (variant 3, D22: never run, never read) |
| `SpellTagarsInsects` | +0x18 (eight victim handles), +0x34 | owner +0x0c = the caster, who holds it | safe |
| `SpellTag` (insect marker on each victim) | — | +0x18 caster, **equality key only** (5.2) | attached to the victim |
| `Trigger`, `PushTrigger`, `Arenadoor`, `AutoProp` | — | `Trigger` +0x6c ↔ `TriggerParams` +0x4c: on its first run a trigger looks for a `TriggerParams` object by box query and the two store each other's address (0x1ecf3c, decompile lines 46–49); `TriggerParams_setActive` writes the trigger's +0x64 through it (0x1ecde4) | both are level objects that live as long as the level; `drunare` has no `TriggerParams` record, so +0x6c stays 0 there (Inferred from the object list in arena-desync.md). `Trigger_run` also sets the script's "selected object", for the length of the call only |

**No arena monster or knight skill keeps a plain pointer to another object.** What players
bring is section 6.3.

### 6.3 `Spell` classes

A spell is destroyed with the creature whose list holds it (`Creature_dtor` 0x117128), so a
pointer to the holder is safe. Holders (Observed, all 26 callers of `creature_addSpell`
0x11a838): the caster for everything returned to `Player_castSkill` (0x1a45e0) and for a
monster's own casts; the **victim** for effect spells (`SpellRoot` 0x2e6728, `SpellDrowsy`
0x30e464, `SpellHateEffect` 0x278000 / 0x27806c / 0x278a68, `SpellBlindingLight` 0x2f414c,
`SpellDiseaseEffect` 0x1e9e34 / 0x2d5d08, `SpellTag` 0x30d034, `SpellSecondaryUndeadShield`
0x2eae44, `SpellArena` 0x3061c8 / 0x30693c, the two script effects 0x14669c / 0x146774) —
and in each of those the owner word +0x0c is the victim too.

Fields other than +0x08 (`Skill`, static) and +0x0c (owner):

| Class | Field | Pointee | Holder | Verdict | Stored | Used | Notes |
|---|---|---|---|---|---|---|---|
| `SpellResurrect` | +0x0c, +0x18 | the dead player | the caster | **RAW** | 0x312884, 0x312908, 0x312e7c | run 0x312b30, draw 0x312f48, 0x31270c | section 3 |
| `SpellResurrect` | +0x68 | the caster | the caster | safe | 0x312958 | run, destructor | |
| `SpellBlindingLight` | +0x1c | the caster | the **victim** | **RAW** (SA1) | 0x2f4518 | `damage_apply` attacker every 30 frames, 0x2f46a4 | section 6.5 |
| `SpellBash`, `SpellShieldBash` | +0x24 | nearest creature in the arc | the caster | **RAW** (SA3, SB3) | 0x2de78c / 0x2de7b8; 0x2fae30 / 0x2fae5c | position read every frame of the bash (0x2faf3c–0x2faf44), passed to the caster's turn-toward slot (0x2faf58) | about a second; reads only |
| `SpellHealing` cast by an `Orc` | +0x0c | the wounded ally | the Orc | **RAW** (skills spec section 55) | Orc cast near 0x2a2998 | run re-tests the ally's dead flag | 68 frames; not re-read here |
| `SpellAncestralCall`, `SpellRoar`, `SpellBattleCry`, `SpellBloodLust`, `SpellMinorHealing`, `SpellUnspokenWord` | +0x18 | the caster (constructor argument 2; for `SpellUnspokenWord` a copy of +0x0c) | the caster | safe | 0x2e0a34, 0x3001f4, 0x3017f0, 0x303328, 0x2e0420, 0x2fd454 | run | holder taken from the cast path; the weapon-effect path was not followed |
| `SpellShadowStep` | +0x2c | the caster | the caster | safe | 0x311750 | run, destructor | |
| `SpellDiseaseEffect` | +0x0c, +0x19c | the victim | the victim | safe | 0x2d560c, 0x2d56a0 | run | the attacker is a handle (+0x18, 0x2d5690) |
| `SpellCyclone` | +0x78 | animation resource | — | not an object | 0x2d1910 | | |
| `SpellTagarsInsects` | +0x18 | handle array | — | handle | | | |
| the other 38 `Spell` classes | +0x0c only | owner | owner | safe where the class is attached by one of the callers above; scanner verdict otherwise | | | not read one by one |

### 6.4 Other classes

| Class | Field | Pointee | Verdict | Stored | Used | Notes |
|---|---|---|---|---|---|---|
| `HolyBolt` (Dismiss Undead) | +0x64 | homing target: nearest creature from a box query | **RAW** (SA2) | 0x2f563c | run: position 0x2f57f4–0x2f581c (steers the bolt's own facing), dead flag 0x2f5868 | cleared when the dead bit is read; a deleted target's free block still has the bit, so the bolt usually drops it one tick late. Reads only |
| `StaticFire` (ShadowStep rank 5+) | +0x4a8 | the caster | **RAW** (SB3) | 0x2c53a0 | run: creature flag 0x2c64d8, the caster's slot 20, `damage_apply` attacker 0x2c6534 | up to 360 frames; null is handled (bomb fires use the other constructor, which stores 0 at 0x2c5604); section 6.5 |
| `FireFlare` | +0x4c | the caster | safe by ownership | 0x2dbda0 | run: `damage_apply` attacker, virtual calls | the flares belong to `SpellFireFlares`, whose destructor deletes them and which dies with the caster (skills spec, not re-read) |
| `FrostShard` | +0x78 | creature the parent bolt hit | equality key | 0x2f69dc from `ShockOfFrost` +0xcc (0x2f86fc) | 0x2f71e4 | 5.2 |
| `Root` | +0xb0 | nearest creature | **RAW** | 0x293704 (decompile line 107) | run 0x293ae0: follows its position, calls its model slot, writes +0x388 and +0xf0 in the constructor | made only by the older ability path (0x1ac02c), reachability D16 |
| `FireBomb` | +0x58 | the bomb it holds | RAW (monsters-2.md) | — | — | not re-read; wood-elf levels |
| `FireBomblet` | +0xac | a counter byte inside its launcher | RAW into another object | 0x262408 | read and written at bounce, 0x263054–0x2630fc | a write through a stale pointer into whatever now occupies the launcher's block; same on all machines |
| `Catapult` | +0x58 | its bomb | owned: cleared in run and take-damage (0x24db50, 0x24dba8, 0x24e060), destroyed in the destructor 0x24d864 | | | scanner plus stores; not read further |
| `ParticleMorphEffect` | +0x54, +0x58 | two creatures | **RAW** | 0x160af0, 0x160af8 | run 0x160b20: virtual calls, flash-colour writes, grid relink of the second | made only by script `particleMorph`; no level script on the disc calls it |
| `VehicleBodySphere` | +0x4c | its vehicle | owned child | 0x28f318 | forwards touch 0x28f34c | vehicle levels |
| `Wheel` | +0x18c | its vehicle | owned child | 0x20ee14 | 0x20efb4 | vehicle levels |
| `Vehicle` wheel array | +0xc… | wheels it creates | owned | 0x209600 | | |
| `NPC` | +0x474 | vehicle it drives | RAW | `Vehicle_attachNpcDriver` 0x208b00 | run 0x29eaa8 (virtual call) | vehicle levels; not read further |
| `AutoEmitter` +0x4c…+0x58, `AutoPropLP` +0x198…+0x1a4, `AutoChestLP` +0xf8, `AutoContainerLP` +0x148, `AutoContainer` +0x140 / +0x144 | | `AddParticle` helpers made in the constructor | owned children | 0x240e64…, 0x24177c…, 0x2414dc, 0x242610 | owners' run and draw | helpers are never made by the factory (monsters-2.md 9); whether a helper is linked into the world was not re-read |
| `WaveMaker` +0x764 | | point list | not an object | 0x15edd0 | | |
| `Vehicle` / `Boat` +0x41c, +0x804…+0x914; `Orc` +0x480; `CloudGiant` / `FemaleDarkElf` +0x300; `BlackWidow` +0xa8; `MissileWeapon` +0x12c; `PhProp` / `ItemProp` +0x148; `AntTrap` +0x198; `RingPortal` +0x1a8 | | tables, resources, numbers in a reused register, or a helper of the same object | not object pointers | | | scanner tier "other"; judged from the store source and the offsets read through, not read line by line |
| Creature base +0x24, +0x2c, +0x48, +0x4c, +0x50 (about 100 classes) | | class definition, property list, virtual table, resources | not object pointers | | | |
| 63 tables without a class name (0x51c918–0x51d8d8: menu and lobby windows) | | windows | outside the simulation | | | not read |

### 6.5 The one per-machine consequence: `handle_link` through a stale pointer

Chain (each step Observed unless marked):

1. `SpellBlindingLight_run` 0x2f4538 calls `damage_apply(victim = +0x0c, attacker = +0x1c)`
   every 30 frames while the victim lives (0x2f46a4). `StaticFire_run` does the same with
   +0x4a8 (0x2c6534). Neither field is a handle.
2. `damage_apply` 0x1e8230 tests the attacker for null at every use and otherwise reads its
   flags, and for a player its slot and record; then it calls the victim's take-damage slot
   with the attacker (0x1e84a8 and three more).
3. `Creature_takeDamage` 0x116638, for a living victim and a non-null attacker: reads the
   attacker's position for the hit direction (0x1166e8), empties the victim's last-attacker
   handle, and calls `handle_link(victim + 0x2e4, attacker, attacker)` (0x116740). The
   second argument is the attacker's "who refers to me" head, its word +0.
4. `handle_link` 0x1a1738 takes two nodes A and B from the node free list `g_handleFreeList`
   0x864ea8, sets `B.next = *(attacker + 0)` and `*(attacker + 0) = B`.
5. If the attacker's block is free, its word +0 is the pool's free-list link (section 2).
   After step 4 the pool's list reads "… → attacker block → **B** → the block that used to
   follow". Inferred from steps 4 and the layout.
6. A later `pool_new` of that class pops the attacker block; the next one pops B — a 20-byte
   node inside the node array 0x847268 — zero-fills 0x180, 0x500 or 3000 bytes from there and
   returns it as an object. Inferred.
7. Which node B is depends on the order of the node free list, which is not lockstep state:
   draw code links lights (D31), the copy links itself into grid and run lists and to its
   target, sounds link to objects, all on per-machine schedules. Inferred.

What it needs: a caster that is **destroyed and not re-made at the same address** while its
Blinding Light is still ticking on a living victim, or its ShadowStep fire is still burning
(up to 360 frames), and whose block is still free at the next tick. A respawned player does
not qualify (same address, section 3). A player who leaves the game does. A monster caster
whose corpse is deleted would (no monster call site for either skill is known).

In an ordinary two-player arena fight: **not triggered.**

## 7. The scanner

`python3 -I -B tools/rawptr.py SLUS_209.73 <command>`:

| Command | Output |
|---|---|
| `fields [Class] [--all]` | per class, words of `this` that are loaded and used as an object and never appear as the first argument of a handle function; `--all` adds every other word used as a base |
| `stores` | stores of a value the function treats as an object into a field or a global |
| `globals` | globals loaded and then used as an object |
| `ptrmath` | ordering compares, differences and arithmetic on pointers |
| `keeps <entry>` | stores of arguments and call results into memory that outlives the call, in everything reachable from a function |
| `func <entry>` | the raw events of one function |

It reads instruction words from the executable and function bodies from `ghidra_funcs.tsv`.
Each function is walked once in address order with a small value tracker; `this` is
followed through direct calls. Limits: no control flow (a register reused on another path
gives a false hit), values taken from stack arrays lose their origin (the stores of
`HolyBolt` +0x64 and `SpellBash` +0x24 show as "unknown"), virtual calls are not followed,
and "used as an object" means a virtual call through +0x48, or the flag word together with
a position word, or being passed to a function that does one of those; a field that is only
compared or only has its position read is in the weaker tiers. Validation: it finds every
plain pointer the earlier passes had found by reading (SA1–SA3, SB3, the `FireFlare`,
`FireBomblet` and `VehicleBodySphere` notes).

## 8. Ranking for the arena, and what to record

| Rank | Finding | Triggered by an ordinary two-player fight in `drunare`? | Per machine? |
|---|---|---|---|
| 1 | Resurrect reads and writes through the freed target (section 3) | yes, on every revival | no: always the replacement object |
| 2 | Pool trigger of the reaper counts the copy (5.3, D21) | no: far from 300 free blocks (arena-desync.md) | only at the threshold |
| 3 | `handle_link` through a stale attacker (6.5) | no: needs a caster destroyed without being re-made | yes |
| 4 | `HolyBolt`, `SpellBash`, `SpellShieldBash` follow a deleted skeleton or its successor in the same block | yes if a cleric or a shield user fights the skeletons: a bolt in flight or a bash in progress when the skeleton's object is destroyed (the tick after its death) | no |
| 5 | `SpellTag` caster key matches a new object at the same address | needs a knight to die and its block to be reused by something that casts insects; knights keep their corpses until `reapEnemies` | no |
| 6 | First copy made on the other side of a 3000-byte allocation (section 2) | no in this level, unless a pause menu stays open from the load to the `cazic` cutscene | addresses differ; no reader found |

**None of these explains a desync on every run.** The stale-pointer class is the same on
every machine wherever it can be triggered in this level.

Two-machine observations that would confirm or refute the basis of that statement (memory
reads, no patch needed):

1. At a few marks during the fight — first tick, after the `knights` cutscene, after each
   revival, at the first mismatch — read on both machines: the three free-list heads
   (0x403a1c, 0x403a2c, 0x403a3c), the four player object pointers (0x4dcec8 + n × 0x4c30)
   and `g_ghost` 0x4027bc. Expected: all equal on both machines, including `g_ghost`
   (same block, different contents). A difference in the first two heads would refute
   section 5.1 and make every RAW row of section 6 a desync candidate; a difference in the
   third head or in `g_ghost` means the first-copy case of section 2.
2. Across a Resurrect: the target's object pointer in the table before and after the
   respawn tick. Expected: unchanged.
3. `g_handleFreeList` 0x864ea8 on both machines at the same tick. Expected: different. That
   is the per-machine ingredient of 6.5.

### Test patches

Untested. Each removes one stale read or one stale link; none is expected to change an
ordinary arena fight, so they are for ruling the class out, after observation 1. Words are
32-bit instructions as PCSX2 `word` patches take them; originals were read from the
executable.

| ID | Address | Original | New | What it changes | What could go wrong | Every player |
|---|---|---|---|---|---|---|
| SP1 | 0x001B8FBC | 0C0C49C3 | 24020001 | `Player_startSpawnProtection` no longer calls 0x31270c; it behaves as if a living player were raising the slot, so flag 0x2 is never set at a respawn. For a Resurrect revival that is what happens today | Save-point, leave and arena-mode respawns change: the new player is no longer given flag 0x2 for the protection time. The delay slot (8C44B280, a load) is kept and harmless | Yes |
| SP2 | 0x002F4518 | AE11001C | AE00001C | `SpellBlindingLight_ctor` stores no caster; the damage ticks have no attacker, so nothing is linked and nothing stale is read | No kill credit, no caster-based modifiers on the ticks; anything that relies on the attacker of a Blinding Light tick changes | Yes |
| SP3 | 0x002F563C | AE620064 | AE600064 | `HolyBolt_ctor` stores no target: Dismiss Undead flies straight instead of homing | Weaker skill | Yes |
| SP4 | 0x002C53A0 | AE7104A8 | AE6004A8 | `StaticFire_ctor` stores no caster: ShadowStep fires behave like bomb fires | With no caster the fire's friend test is skipped (0x2c64cc on), so it also burns the caster's side | Yes |

No one-word change exists for `SpellBash` / `SpellShieldBash` (two stores each) or for the
`SpellResurrect` target, and none is proposed for 6.5 itself: the right fix is a handle in
place of the plain pointer, which is a rebuild matter.

## 9. Not determined

- The triage of the remaining scanner hits. Two helper passes that were to read every
  `Spell` class and every other class field by field did not complete; rows marked "scanner
  verdict" or "not re-read" in section 6 rest on the scanner and on earlier documents.
- Whether any monster casts Blinding Light, and every caller of the `StaticFire`
  constructor that stores a caster.
- Plain pointers held in stack-array-fed fields the tracker could not type, and anything
  stored only through a virtual call.
- Allocation behind virtual calls from HUD, menu or cutscene draw tasks (5.1).
- "First free slot" searches in general (5.4), and what `Cazic_deathEffects` does with its
  three beam handles.
- What follows `player_respawn` for a slot whose player has left (3.3, last row).
- Static holders not reached by the scanner's "used as an object" test. Those found:

| Holder | Holds | How it is invalidated | Kind |
|---|---|---|---|
| Player table, object word (0x4dcec8 + n × 0x4c30) | each player's object | cleared by `Player_dtor` 0x1a1c10 unless the copy is being torn down; set by `Player_ctor` 0x1a221c | Observed |
| `g_alivePlayers` 0x4f8440, `g_scriptActivePlayer` 0x4d8ae4 | slot numbers, not pointers | rebuilt (G11); a stale slot number reads the table | Observed |
| Boss meter 0x41b6a0, 0x41b6a4, 0x41ba40 | copied hit points and name, not a pointer | — | from symbol notes |
| `g_scriptSelectedObj` 0x4039f8 | the object a script runs for | set and zeroed around each script call (0x14dcf4 / 0x14de50, 0x10a5f0 / 0x10a5f4, 0x10bf0c / 0x10bf10, 0x10c0d4 / 0x10c0d8, 0x1ed154 / 0x1ed194) | Observed |
| Name table 0x5f7ef8 | object per name slot | zeroed in `GameObject_dtor` (arena-desync.md F4) | not re-read |
| `g_cutActors` 0x83d184 | bound and created cutscene actors | written at `cut_setup` 0x19a76c, released in `cut_end` 0x19a1d0 on; plain pointers for the length of the cutscene. In `drunare` `reapEnemies` runs in the script task before the cutscene task binds actors, so it cannot delete a bound one | Observed writers; order Inferred |
| `g_cutSpeaker` 0x83d18c | speaking creature | set from a name lookup at the dialog key 0x196a60, zeroed at 0x196a4c / 0x196a6c, by `cut_start` 0x19b588 and `cut_end` 0x19a5f4 | Observed |
| `g_dialogFocusObj` 0x4fdcc0 | creature a dialog is with | `dialog_setFocusObj` 0x231028; zeroed by `dialog_free` 0x22fa24 | Observed writers |
| 0x86a6ac | item-list filter object (menu) | 0x1c8d24, 0x1cea04, 0x1cea60 | not read |
| 0x4f88b8 | written with `this` by `Vehicle_ctor` 0x207af0 | Unknown | not read |
| 0x871548 | path objects from `paths_add` 0x20f8cc | level data | not read |
| Arena-mode monster table 0x50388c | objects of the current wave | `arena_startWave`, 0x306adc; PvP arena mode only | not read |
| Camera | reads the player table each update; no object pointer found by the scanner | — | not read |

## 10. Proposed ledger rows and corrections

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| ST1 | The only per-machine pool allocation is the prediction copy: one 0x590 block in the 3000-byte class, re-made by free-then-allocate with nothing between, so it keeps its block. No draw function allocates from the pool; prediction leaves the free lists unchanged. The two smaller size classes are therefore lockstep state, and a stale pointer into them reads the same bytes on every machine | Observed (each check), Inferred (conclusion); virtual calls from HUD and menu draw tasks not covered | 0x13b330, 0x13b540, 0x11e894; draw-reach scan and `pool_new` caller scan in docs/issues/stale-pointers.md 5.1 |
| ST2 | `player_respawn` frees the old `Player` and allocates the new one with no call between, so the new object has the old address on every machine. The read through the stale `SpellResurrect` target in `SkillResurrect_isSlotBeingRaised` (SB3) therefore always sees the new object's slot and returns 1 | Observed (order), Inferred (same address) | 0x1bd0f0, 0x1bd138, 0x1bd1d4, 0x1b8fbc, 0x312778–0x31277c |
| ST3 | `Creature_takeDamage` links whatever attacker it is given. With a destroyed attacker (plain caster pointers of `SpellBlindingLight` +0x1c and `StaticFire` +0x4a8) the link overwrites the free block's pool link with a handle-node address, which the pool later hands out as a block; handle-node addresses differ per machine. Needs a caster destroyed without being re-made at the same address | Observed steps, Inferred outcome; not reachable in an ordinary arena fight | 0x2f46a4, 0x2c6534, 0x116740, 0x1a1738, 0x150470 |
| ST4 | No simulation object keeps the prediction copy's address: none of the 17 `net_objOrGhost` call sites stores its result, and the copy's `this` is linked only into its own grid and run lists and the sound table. The kind-2 "being swung at" notification, which several monsters act on, is inside the copy test; the kind-3 one is unguarded and unhandled | Observed for direct calls | 0x13e180 sites; 0x214334, 0x112ef0, 0x1a8f44, 0x1aa5b8 |
| ST5 | No code orders, hashes or indexes by object address; object addresses are used as equality keys in `SpellTag` (+0x18) and `FrostShard` (+0x78). Nothing walks the pool in address order. The pool reaper walks grid-B cell lists from the head without the exclude mask and destroys the first flag-0x1000 object: victim by link order | Observed for what `tools/rawptr.py` tracks | 0x11a788, 0x2f71e4; 0x14b9f0–0x14bb18 |
| ST6 | Besides SA1–SA3 and SB3: `Root` +0xb0 (older ability path only), `ParticleMorphEffect` +0x54 / +0x58 (script command no level uses), `NPC` +0x474 and `Player` +0x540 (vehicle), `FireBomblet` +0xac (a byte inside its launcher), an Orc-cast `SpellHealing` owner are plain pointers. No arena monster class or knight skill has one | Observed | docs/issues/stale-pointers.md 6.2–6.4 |

Corrections to earlier documents:

- **FINDINGS SB3 and docs/spec/skills-35-68.md section 68** ("the result is right only
  because the freed block either still holds the slot number or has just been reused …
  reuse Inferred, not traced in `pool_new`"): traced here. The block is always reused by
  the new `Player`, on every machine (ST2). The clause "a freed block's contents depend on
  pool history, which is not the same on every machine (D21)" should be limited to the
  3000-byte class and to the case of section 2.
- **FINDINGS SA1** ("pool contents are not identical between machines (the prediction copy
  and gore-dependent objects are per-machine allocations)"): the copy is one block in the
  largest class; gore objects are not per machine in a net game (B8). For a monster caster
  the stale read is the same everywhere; what makes SA1 dangerous is the link, not the read
  (ST3).
- **docs/issues/prediction-copy.md 3.1** ("Node and block *addresses* differ per machine
  already"): node addresses do; block addresses do not, apart from the first-copy case.
- **docs/objects.md, `runObjects` step 3**: add that the reaper walks the cell lists
  directly, without an iterator and without `g_excludeMask`.
- **The brief for this pass** assumed that a freed block is reused by different objects on
  different machines. That was not found to be so outside the 3000-byte class.
