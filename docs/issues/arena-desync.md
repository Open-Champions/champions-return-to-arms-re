# The Drundar arena (DRUNARE) desync: each candidate worked through

Level `drunare`, evil path. The ledger (`FINDINGS.md`) lists several candidate causes for the
"… IS OUT OF SYNC!" message in this level; none was proven. This document takes each one as
far as static reading allows and ranks them.

Everything here was read from the executable and from the level's unpacked files; nothing
was run. Claims are **Observed** (read at the address given), **Inferred** or **Unknown**.
Patch proposals at the end are **untested**. All of that still holds. The project can run
the game now — in the Play! emulator, which is not a PlayStation 2 and not PCSX2,
on one machine (`FINDINGS.md`, "Run on the live game" (rows V1–V8) and `docs/issues/live-rig.md`)
— but the arena has not been reached on it, a desync needs two machines, and no test patch
has been run on a live game.

## Result in one table

| Candidate | Ledger rows | Static answer | Rank |
|---|---|---|---|
| Player dies first in prediction, alive list stale | G11–G13 | Possible, but in this level only for a player whose object was re-made after the monsters woke up (Resurrect skill); the kill plane route does not exist in any level | 1 |
| Activity decided by the camera during cutscenes | D6, D7 | Camera focus and the cull flag are the same on every machine during a cutscene as far as every writer found; creatures other than actors do not run at all in this level's cutscenes | 2 |
| Pool occupancy | D21 | No size class comes near its limit; the one per-machine difference left in this level is the prediction copy's 3000-byte block | 3 |
| Knight 3 re-summons its skeleton | D22, D23 | The skeleton's removal frame is fixed by lockstep state only. D22 turns an existing difference into a visible one; it cannot start one | 4 |
| Speaker animation nudged by local audio | D8, D10, D19 | The nudged values cannot reach `g_randSeed` or a player position in this cutscene | 5 |

**None of the five explains a desync that happens on every run.** Each is either closed or
needs a specific, uncommon event. If the arena goes out of sync with no player death, no
resurrection and before the last cutscene's first voice line, the cause is not on this list.
"What to record on two machines" at the end says which observation separates the cases.

## The level in facts

**Observed** from `objects.ob`, `script.scr` and the three `.cut` files of `drunare.lmp`.

- 39 object records: four `UndeadKnight1`…`4` (class `Horsemen`, variants 0–3, each with
  `wait`, a `deathscript` and a `dropitem` property, all named `knight`), one `CazicAvatar`
  (named `avatar`, `wait`, `deathscript`), one `RalosZek` (named `rallos`, `wait`), four
  `arenadoor`, fourteen animated flag props (`autoprop`), two `Trigger`, one `PushTrigger`,
  one `Player1`, light markers. No save point, no jump gate, no torch, no water spout.
- `start` hides Rallos, the avatar and the knights.
- A trigger volume runs `incoming`: the first time it starts the cutscene `knights` (post
  action sets the save inhibit and the avatar's MiniBoss bit).
- Each knight's death script sets a variable; when all four are set a deferred call counts
  300 un-paused frames and starts the cutscene `cazic`.
- The avatar's death script starts a second deferred counter; at 250 it plays a sound, later
  it starts the cutscene `bossdefeated` with post action `levelChange`, then `reapEnemies`.
- All three cutscenes have header flag 8. `knights`: four bound knight actors that walk.
  `cazic`: a bound door, the bound avatar, and a created `Player` stand-in. `bossdefeated`:
  a bound door and bound Rallos; three dialog lines, three wait keys.
- Level table row (`g_levelTable` 0x4f7210, row 6): kill plane −100000.

## Facts several candidates depend on

### F1. Run order: in this level monsters run before players

- `handle_link` pushes at the head of a list and `runObjects` walks the active list from the
  head, so the most recently linked object runs first. **Observed** (docs/objects.md;
  0x14b910).
- Level objects are created by `game_loadLevel`; the `Player` objects are constructed after
  it and link themselves into the active list in their constructor (`obj_runEveryFrame`,
  decompile of 0x1a1d28). **Observed** (order: docs/mainloop.md step 6).
- `Horsemen_ctor` and `Cazic_ctor` put the monster on a 60-frame list
  (`obj_runEvery60`). The first `Creature_updateActive` that finds it active re-links it at
  the head of the active list (`obj_updateActive` 0x14db08). For the knights that happens
  inside the `knights` cutscene, for the avatar inside `cazic`; both are after the players
  were linked. **Observed** for each step; the conclusion is **Inferred**.
- Everything created during the fight (skeleton, DiseaseBolt, FireStorm and flares, ground
  pound) is linked later still.
- Consequence: every hostile hit in this level lands **before** the victim's own
  `Player_run` in the same tick, so the pending damage (+0xc8) is consumed in that tick and
  is zero at the end of it. The exception is a `Player` object constructed after the
  monsters woke up: `player_respawn` 0x1bd040, whose callers are the Resurrect spell
  (0x312e40), the "raise someone" branch of the disconnect message (0x1d8f4c), save points
  and PvP respawn.
- Objects on the 15- and 60-frame lists run after the active list. A creature is on one
  only while no player is inside its activity radius, so it has nobody in reach
  (**Inferred**).
- Not checked: every one of the 155 callers of `obj_runEveryFrame` for a path that re-links
  a live player.
- `docs/issues/prediction-copy.md`, written in parallel, states the same run-order rule and
  the same kill-plane result; the two were reached independently.

### F2. A flag-8 cutscene freezes every creature, players included

**Observed** in `cut_setup` 0x19a6cc and `cut_end` 0x19a0dc.

- `cut_setup` first walks every run list (`world_forEachRunObject`) with callback 0x198f7c:
  a creature hidden by script (inert bit 8) is put back on the grid and marked with inert
  bit 2 so the actor search can find it. Actors are then bound by a box query of ±240 units
  around the actor record's position, matching the type name; a bound object gets object
  flags 0x88000 (not run by `runObjects`, activity radius 44000), a creature also inert
  bit 1 and the serial byte +0x230 from the actor record. A second walk (0x198fd0, call
  0x19b3a4) undoes the first.
- With header flag 8 a third walk (callback 0x199024, call 0x19b3c0) takes **every creature
  whose inert byte +0x231 is 0** — monsters, corpses, summoned skeletons and the real
  players — and gives it inert bit 4, flags 0x88000, and moves it off the grid. Without
  flag 8 `creatures_freezeAll` runs instead, which skips players.
- The walks use `g_excludeMask`, which is 0x20000 inside a tick, so the prediction copy is
  not touched.
- `cut_end` clears 0x88000 and inert bit 1 on bound actors, destroys created actors, and
  with flag 8 walks again (callback 0x199074, call 0x19a554): a creature whose inert byte is
  **exactly 4** gets it cleared, loses 0x88000 and is re-linked to the grid.
- So during these cutscenes the only creatures that run are the actors, called from
  `cut_advance` once per tick, always "active" because of the 44000 radius. Players do not
  run, so their positions do not change and the hash can only change through `g_randSeed`.

### F3. The cutscene task runs in the tick that starts it, and ends in the tick its keys run out

- `task_add` 0x19e4a0 inserts by priority and only bumps the walk cursor when the new entry
  lands at or before it. `cut_start` is called from a trigger (run task 10) or a script
  (125); the cutscene task has priority 300, so it is reached in the same pass.
  **Observed.**
- `cut_runFrame` 0x199944 calls `cut_setup` on its first call, so creatures are frozen in
  the tick of `cut_start`. When the key list is exhausted it calls `cut_end`, sets the
  camera mode to 1 and runs the post action (0x199f44–0x199f6c), all in that tick.
  **Observed.**
- In `bossdefeated` the post action calls `newWorld` with the gate skipped (post-action flag
  0x4f8698, docs/script.md), which fills the pending level name; `net_frameLoop` then runs
  no further tick (0x139fb4). **Observed.** So nothing runs un-frozen after the last
  cutscene.

### F4. Name lookup

**Observed** in `objNames_add` 0x14bce0, `objNames_remove` 0x14be58,
`world_findObjectsByName` 0x14bf58.

- The table is 512 open-addressed slots: key pointers at 0x5f76f8, object pointers at
  0x5f7ef8. A name is added in `GameObject_ctor` (call 0x14cf4c) and its object pointer is
  zeroed in `GameObject_dtor` (call 0x14d19c). Nothing else writes the table. The key stays
  behind and the slot is reused by the next object of the same name.
- The lookup compares names and returns objects whose pointer is non-zero. It does not look
  at flags, grids or lists. So `world_findObjectByName` **does** see an object that is
  hidden, dead, in grid B, off the grid, or queued on the delete list — until its
  destructor has run.
- Queued objects are destroyed in the first loop of `runObjects`, before any object runs.

## Candidate: knight 3 re-summons (D22, D23)

### The skeleton's life, step by step

All **Observed** unless marked.

| Step | What happens | Where |
|---|---|---|
| Decision | `Horsemen_run` state 3, variant byte +0x470 = 3: after the three melee tests fail (target within 36; target within 36 and charging; target within 400 with allies near it) it calls slot 1 of skill 11 and, if true, enters state 0x17. The timer +0x474 is not consulted for this variant | 0x2726f0–0x27271c |
| Can use | For a caster without the player flag: true when no object is registered under the monster skeleton name (pointer at 0x503788) | 0x2e2368 → 0x14f498 |
| Cast | State 0x17, on animation event bit 0 and only with a target handle: slot 2 of skill 11 at the knight's own position. Nothing re-tests "can use" here. The returned spell is dropped (variant 2 links its spell, variant 3 does not) | 0x272c70; compare 0x272bfc |
| Inside the cast | Tint on the caster; particles from the cosmetic seed; spawn point 72 units ahead at terrain height, replaced by `world_findFreeSpot` (shared seed) only when the height differs by more than 24; one `g_randSeed` draw; `pool_new(0x468)`; on success `Skelight_ctor` with the property list at 0x503770 and object flag 0x4000; a second shared draw picks a weapon element when the first draw is under a skill statistic; a sound; `pool_new(0x1c)` and `SpellSummonSkeleton_ctor` (one more shared draw, a handle to the skeleton) | 0x2e18a4: 0x2e1f80, 0x2e2020, 0x2e2040, 0x2e221c, 0x2e223c |
| Construction | `Creature_ctor` (the object's own seed is drawn from `g_randSeed`, the name is registered); stats computed under a temporarily replaced monster level; state 0x17 (rise); linked at the head of the active list; active bit set | 0x2a8770 |
| Each frame | `Creature_processDamage` unless the state is 0x17; `Creature_run`; `Creature_updateActive`; weapon helper slots 15 and 22; `Creature_stepAnim`; knockback; target pick; state switch. State 0x17 emits effect 7 and waits for the animation to end; 3 chases; 6 swings and hits on event bit 0 | 0x2a8b84 |
| Death | `Creature_takeDamage` lowers hit points at once. The next `Skelight_run` whose state is not 0x17 runs `Creature_processDamage`, which at hit points ≤ 0 sets flags 9 and calls slot 27 with 0x14. `Skelight_setState` case 0x14 sets flag 2, clears a static, emits effect 2, and calls `obj_delete` | 0x110d30; 0x2a91b8, call 0x2a9414 |
| What death does not do | No loot (`Creature_dropLoot` is not called), no death script (slot 28 is not called), no corpse phase. No gib objects: in a net game the gib branch needs body-material bits 0x1000 or 0x2000 and `Skelight_ctor` sets 0x10000 | 0x2a91b8; 0x110d30 gib branch; 0x2a8770 |
| Destruction | Start of the next `runObjects`: destructor, name removed, handles to it emptied, block freed | 0x14b910 first loop; 0x14cf90 |
| Re-summon | Same tick, when the knight's turn comes and it reaches the test in state 3 | as "Decision" |

Frame arithmetic (**Inferred** from F1 and the table): the skeleton is newer than the
players, so it runs before them. A player's killing blow in tick N is processed by the
skeleton in tick N+1 and the object is gone at the start of tick N+2. Hits taken while it
is still rising wait until the rise animation ends. If no player is within its activity
radius (the largest of +0x3c4, +0x3ac, +0x3ae: 600 by default) it sits on a 60-frame list
and the death is processed when that list comes round.

Other ways out of the world: `Cazic_setState` case 0x14 sends every object of that name to
state 0x14 (docs/monsters.md); `reapEnemies` destroys dead non-player creatures directly.
Neither happens while knight 3 is alive. A third, found since
(docs/issues/kill-loot-xp.md, FINDINGS K8): when knight 3 itself dies, case 0x14 of
`Horsemen_setState` looks the skeleton up by name and sends it to state 0x14 in the same
tick (0x273278, 0x2732ac), and drops both held weapon parts.

### Does any step read something that differs between machines?

| Input asked about | Answer | Kind |
|---|---|---|
| Camera | Only the effect gate in `fx_spawn` (types 2 and 7, particles) and the weapon helper's `isNearView` test in front of `fx_modelStatusEffects` 0x1f6ac8. `isNearView` uses the players when no cutscene is active | Observed calls; that 0x1f6ac8 writes only cosmetic state is taken from docs/gameplay.md (scan, not a line reading) |
| What was drawn | `Skelight_draw` 0x2a8a64 calls `Creature_draw` and the weapon helper's draw. `Creature_draw` changes a status counter only when one is non-zero (D12); nothing on this path sets one | Observed |
| Activity during cutscenes (D6) | Not applicable to the re-summon: the first cutscene after the fight starts is `cazic`, and it starts only after all four knights are dead. A skeleton alive at that point is frozen and off the grid for the whole cutscene (F2) | Observed |
| Corpse rules | The "sinks and is deleted once inactive" rule needs creature flag 0x1000000. Its setters are `Creature_loadState`, the generator spawners (0x265938, 0x265e08, 0x265fc4), 0x29cea8 and 0x2bf538. No arena class sets it, and the skeleton has no corpse | Observed (pattern search over the decompile) |
| Pool reaper (D21) | The reaper destroys only objects in grid B with flag 0x1000. A `Skelight` is in grid A and never has that flag | Observed 0x14b9cc–0x14bb18 |
| Pool exhaustion | A failed `pool_new(0x468)` skips the constructor's draw and leaves "can use" true. See the pool section for why that does not happen | Observed mechanism |
| Local option | None on this path in a net game | Observed |
| Cosmetic seed | Particles in the cast only | Observed 0x2e194c–0x2e1e40 |
| Prediction copy | Monsters do not run during prediction; box queries skip the copy | G6 |
| Alive-player list | Not read by `Horsemen`, `Skelight` or the skill. The experience loop in `Creature_processDamage` uses `g_numPlayers` and hit points | Observed |

**Answer to D23:** given the same damage input, the frame on which the skeleton's object
disappears is the same on every machine. **Inferred** from the Observed steps above.

**A side effect found:** the spell object returned by the cast is never linked to anything
when a `Horsemen` casts, so nothing ever calls its run or destructor. Each summon by knight 3
leaks one block of the smallest pool class until the level is unloaded. It is the same on
every machine. **Observed** (0x272c70 drops the result; `SpellSummonSkeleton_run` 0x2e177c
is reached only through an attached-spell list).

- **Weakest link:** 0x1f6ac8 and the weapon helper's draw (slots 19, 20 of table 0x50cf40)
  were not read line by line. (0x1f6ac8 and the weapon holder's per-frame update have
  since been read in docs/issues/rescan.md section 6: presentation only — they write
  nothing but a per-weapon effect block that only they read, FINDINGS D37.)
- **If it were the cause:** the first mismatch would fall in the knight phase, while
  knight 3 is alive, within a couple of seconds of a skeleton dying, and the two seeds
  would differ by the handful of draws one cast makes.
- **Test:** patch T1 below removes the summon. If the desync is unchanged, D22 is out.

## Candidate: the prediction copy dies first (G11–G13)

### What has to happen

1. The copy must process lethal damage in prediction. `Player_clone` copies the pending
   damage, so the copy needs to be cloned at the end of a tick in which damage was still
   pending on the real player (G12).
2. By F1 that is never the case in this level for a player object that dates from level
   load. It needs a player object re-made in the level, which here means the Resurrect
   spell or the disconnect "raise". **Inferred.**
3. The other route in G12, the kill plane, does not exist: all 90 rows of `g_levelTable`
   and its default row hold −100000 at +8, and `Player_run` ignores the plane unless the
   value is above −90000 (0x1a5b38–0x1a5b4c). The only writer of `g_killPlaneZ` is
   `game_loadLevel` (0x1e5de8). **Observed.**
4. When the copy does die, the list is wrong on that machine from the start of the next
   tick until the real player's own `Player_run` processes the same damage and rebuilds
   the list — a part of one tick. Only code that runs before that player in that tick sees
   the difference. If the real player survives (regeneration and potions run for the real
   player but not for the copy) the list is wrong for the whole tick. **Inferred.**

### Readers of the list that run during this fight

`python3 -I -B tools/gxref.py SLUS_209.73 4f8420 4f8440`, each use read. **Observed** for
what each does; whether it matters is **Inferred**.

| Reader | Use | Effect of one player missing for a tick |
|---|---|---|
| `Player_run` 0x1a5284 | count = 2 scales the player's light radius | drawing only |
| `Player_run` 0x1aa018–0x1aa0d0 (melee state) | best attack-speed bonus among alive players carrying an Ancestral Call or Battle Cry spell | another player's swing advances at a different rate — only if the missing player carries one of those spells |
| `Player_recalcDamage` 0x1b7810 | same loop for Ancestral Call; the result is stored in the attacker's record (+0xd0, +0xd4) | weapon damage differs — same condition |
| CriticalHit aura query 0x2e76c4 (from `damage_apply`) | aura from alive players | critical chance differs — same kind of condition |
| `SpellHealing_run`, `SpellAncestralCall_run`, `SpellCriticalHit_run`, `SpellBattleCry_run` (0x3027c8) | group effects walk the list | the missing player is skipped by a group effect that tick |
| `OniBall_run` 0x2941e4 | nearest alive player with a rank in skill 0x3b | the orb may steer elsewhere; needs that skill |
| `Prop_run` 0x154850, `PhProp_run` 0x156d24 | deletes the prop when it is 120 below the **first** alive player | none on a flat floor |
| `Player_move` 0x1b4f6c and one later use | both uses require network mode off | none |
| `newWorld_netGate` 0x143d50 | "more than one alive" | only at the exit trigger |
| `net_closeLocalMenus` 0x1eb07c | ejects alive players from vehicles | no vehicles here |
| `game_checkAllDead`, `deathTask` | run after the end-of-tick rebuild | none |
| camera, HUD, spectator functions | per machine by design | none on shared state |

No function of `Horsemen`, `Cazic`, `Skelight` or of the three skills the knights cast reads
the list. Script built-ins that read it are not used by this level's script.

Also **Observed**: `Player_dtor` calls `game_rebuildAlivePlayers` outside its "not a copy
operation" test (0x1a1c68), so the list is rebuilt from the real objects every time the
copy is destroyed at a rebase. That happens after the ticks of a call, so it does not close
the window in step 4.

- **Weakest link:** step 2 (needs a resurrection) and then a reader from the table that
  actually changes something (needs particular skills in the party).
- **If it were the cause:** the mismatch appears in the tick after a death, the machine
  that owns the dying player is the one that disagrees, and that player had been
  resurrected earlier in this level. A desync with nobody dying rules it out.
- **Test:** the "alive list" section already in `patches/` (0x1b3504).

## Candidate: pool occupancy (D21)

Pool classes (**Observed**, table 0x403a10): 512 × 0x180, 512 × 0x500, 32 × 3000 bytes;
1056 blocks. The reaper starts below 300 free, i.e. above 756 in use.

| What | Size → class | Count and lifetime | Evidence |
|---|---|---|---|
| Knights, avatar, Rallos | 0x478, 0x3e8, 0x480 → 1 | 6 for the whole level | factory table, docs/objects.md |
| Doors, flag props | 0x198, 0x448 → 1 | 18 | same |
| Triggers, markers | ≤ 0x70 → 0 | about 10 | same |
| Players, prediction copy, cutscene stand-in | 0x590 → 2 | players + 1 (briefly 2) + 1 during `cazic` | `Player_ctor` callers; G1 |
| Summoned skeleton | 0x468 → 1 | at most one (the "can use" test) | above |
| Leaked summon spell | 0x1c → 0 | one per summon, never freed | above |
| DiseaseBolt | 0x7c → 0 | one per cast; a knight casts at most every 480–600 frames | 0x2cb1c0; `Horsemen_run` state 0x17 |
| FireStorm | 0xb4 + one light effect 0xbc → 0 | one per cast; monster casts start 40 frames late and last a few seconds | 0x2d4f7c, 0x2d4480 |
| FireStorm flares | 0x6c → 0 | one every 15 frames, each lives 120 frames: at most 8 | 0x2d41f8 (+0xa8 = 15), 0x2d3184 |
| Tagar's Insects | 0x94 + one 0x20 marker per victim → 0 | one spell, up to one marker per player | 0x30c708, 0x30cbc8 |
| Damage numbers | 0x98 → 0 | one per hit, 30 frames | docs/gameplay.md |
| Player blood chunk | 0x268 → 1 | one hit in eight; destroyed at its first landing | 0x1b3284 onward |
| Loot, orbs | ≤ 0x248 → 0 or 1 | a few per kill | `Creature_processDamage`, `dropitem` |

Three things reduce what could differ between machines in this level:

- Creature gib chunks are not created at all: in a net game the branch needs body-material
  bits 0x1000 or 0x2000, and the arena classes have 0x20000 (`Horsemen`, which also has the
  "no gibs" bit 0x20000000), 0x40000 (`Cazic`, `Zek`) and 0x10000 (`Skelight`).
  **Observed** in the four constructors and at the gib branch of 0x110d30.
- The blood chunk a hit player can spawn is constructed with bit 0 of +0x248 already set
  by the caller (0x1b3284 block), so it disappears at its first landing whatever the local
  gore option says. The option only decides particles and decals there. **Observed**
  (constructor 0x201958 ORs the option in; the argument is already 1).
- `GutChunk_run` 0x1edb18 draws from its own generator before it looks at the option, so
  the number of draws does not depend on it. **Observed.**

That leaves the prediction copy's block in the largest class (one or two of 32) as the only
per-machine occupancy. For it to matter the two smaller classes would both have to be full.
A generous peak for a four-player fight is under 150 blocks in class 0 and under 80 in
class 1. The leak adds one class-0 block per summon; reaching 512 would take several hundred
summons, and it is identical on every machine anyway. **Inferred:** D21 cannot be the cause
here.

- **Weakest link:** objects made by player skills were not counted class by class.
- **If it were the cause:** `g_poolFreeCount` (0x403a04) would read below 300 on at least
  one machine before the mismatch.
- **Test:** read 0x403a04 a few times during the fight. Patch T3 switches the reaper off,
  but it only tests the reaper half.

## Candidate: the speaker during `bossdefeated` (D8, D10, D19)

What Rallos is while he is the speaker: a bound actor with flags 0x88000 and inert bits
(his `wait` bit plus the actor bit; the hidden bit is cleared by a show key). He is run
once per tick by `cut_advance`, in AI state 0. **Observed.**

What `Zek_run` 0x2c2440 then does each tick, in order:

| Call | With these inputs | Can it touch `g_randSeed` or a player? |
|---|---|---|
| `Creature_processDamage` | no pending damage: `Creature_takeDamage` ignores an inert creature | no |
| `Creature_run` | timers; attached spells (none); the MiniBoss block is skipped for an inert creature; the scavenger call needs state 0x14 | no |
| `Creature_updateActive` | radius 44000 | always active |
| weapon helper slot 21 | `isNearView` then the effect routine | effects only |
| `Creature_stepAnim` | **this is where the nudged track times are read**; it returns event bits and writes root motion into +0xbc, +0xc0, +0xc4 | see below |
| `Creature_applyKnockback` | no knockback speed | no |
| slot 23, target pick | returns at once for an inert creature (0x10ded0, first test) | no |
| state 0 | "can see target" is false without a target; a request for state 1 is refused for an inert creature (`Creature_filterState` 0x10a9c0) | no |
| tail of the function | only when +0x464 is set, which only state 0xe sets | no |

The event bits are not used in state 0. The root-motion fields are consumed only by
`Creature_moveBy`, which state 0 does not call, and the talk, lip-sync and idle tracks are
started without the root-motion flags (0x26 and 3, docs/engine.md). The animation status
word +0x11a is read by other states only. Cutscene keys do not wait on animation state.
After the last key the level change is already pending (F3), so Rallos never runs as a live
monster. **Observed** for each row; the conclusion is **Inferred**.

Two more details:

- The nudge only exists on the lip-sync path. The generic talk loop is started without
  track flag 0x20, and `cut_advance` looks for that flag (0x199454). Which path a machine
  takes depends on a local disc read (engine P6), so machines can show different
  animations; by the table above that is cosmetic too. **Observed.**
- The three wait keys are safe: each machine sends message 0 once when its own stream ends,
  messages execute on the same tick everywhere (docs/netcode.md), and the count is reset
  when the key passes. **Observed** 0x199214; handler 0x198f64.

**Answer to D19 and D10:** no route. If the desync were here it would start after the first
dialog key, 13.4 s into the last cutscene, and never when the cutscene is skipped early.

- **Weakest link:** the weapon helper's effect routine 0x1f6ac8 (not read line by line).
  (Read since: presentation only, FINDINGS D37, docs/issues/rescan.md section 6.)
- **Test:** the audio section already in `patches/`, or patch T4, which removes both the
  nudge and the lip-sync choice with one word.

## The cutscenes and the deferred calls

### Camera-driven activity (D6, D7)

- `g_cullByCamera` is set every tick by `gameSetObjectVis` 0x1e4d48 to "camera mode word
  (camera object +0x34) is not 1", and in a net game cleared again unless a cutscene is
  active (0x1e4dac–0x1e4ddc). The camera object is per machine. **Observed.**
- Writers of the mode word (`Camera_setMode` 0x2072e8 and its ten callers): `cut_start`
  (0), `cut_runFrame` at the end (1), inventory open (0) and close (1), shop open and close,
  dialog, front end. `cut_start` calls `net_closeLocalMenus` first and then sets 0; `hud_run`
  refuses to open the inventory while a cutscene is active or the mode is not 1
  (0x1db870). So the mode is 0 on every machine for the whole cutscene. **Observed** for
  the callers read; **Inferred** that no other path sets it. (One other store to the mode
  word exists: `Camera_updateFree` 0x2043d8, the fly camera of modes 3–5, sets mode 1 on a
  button of pad 0, at 0x20440c. It cannot run while the mode is 0, so the conclusion
  stands; `docs/issues/claims-audit.md` row 8.)
- The engine camera is written by `camera_setView` 0x18a2b0. During a cutscene the callers
  that can run are `cut_runFrame` (every tick) and `Camera_apply`. `Camera_update` reaches
  `Camera_apply` only in mode 1 or while the transition word +0x48 is non-zero; +0x48 is set
  only by `Camera_reset`, whose callers are player respawn, loading a camera state, a
  spectator-slot change and session start. `drawWorld` only recomputes the focus from the
  stored camera. **Observed.** (Caller list corrected by docs/issues/arena-entry.md: the
  main loop also calls `Camera_reset` at every level change, 0x322dfc, and the "session
  start" caller is `Camera_init`. The conclusion stands for a net game:
  `Camera_computeTarget` can fail only offline, 0x2065e8–0x2065f4, so the first
  `Camera_update` of the load warm-up loop reaches the end of the follow routine and
  clears the word, 0x204fb0, before any tick.)
- A spectator-slot change (`Camera_cycleSpectated` with step 0, called from the HUD draw for
  a dead local player, 0x1e01b8) resets the camera only when the spectated slot leaves the
  alive list. Players do not run during these cutscenes (F2), so the list does not change.
  **Inferred.**
- What still calls `obj_updateActive` or `isNearView` from `runObjects` during this level's
  cutscenes: the flag props and doors (`AutoProp_run` 0x23cc0c) and any player arrows in
  flight (`MissileWeapon_run`). With a shared focus these are lockstep. If the focus ever
  differed, the visible damage would come through the shared round-robin cursor
  `g_runList60Cursor`, which moves every time an object turns inactive.

**Answer:** D7 holds for every writer found. Left open: address-taken references to the
camera position and matrix in drawing code (0x1762e8, 0x1887b8, 0x189df0 and others in the
`gxref` output) were not read to confirm they only read. **Closed since for the position
and the focus** (`docs/issues/claims-audit.md` row 3, with the corrected scan and the
decompile): the position is stored by `camera_setView` and by `Camera_loadState` 0x203a20
(0x203a68–0x203a88; called only from `save_load`, so it puts each machine's own saved
camera back on a party-wipe reload, when no cutscene is running); the focus only by
`camera_updateFocus` 0x18a520; the possible stores in drawing code are stack stores. The
matrix is written by the same two functions; four possible writes of it (`line_draw`,
`Camera_updateFree`, `Camera_updateFollow`, `DragonGoldPile_run`) were not classified one
by one.

- **If it were the cause:** the mismatch would start one tick after a cutscene begins, or
  later when an object on a shifted 60-frame list wakes; it would change with where each
  player's camera was.
- **Test:** patch T5.

### Other things checked

| Item | Finding | Kind |
|---|---|---|
| Second deferred counter | On the frame the counter passes 250 the entry queues itself (source line 98) and then falls through to the second test and queues itself again (line 103). Two copies run from then on and the counter rises by 2 per frame. The last cutscene therefore starts about 875 frames after the avatar dies, not 1500. Same on every machine | Observed: no jump opcode between the two statements in `script.scr` |
| `cazic` stand-in | Created only if slot 0's hit points are above 0. An inert player object only steps its animation in `Player_run` (0x1a5030, inert test), so it stays where the actor record put it | Observed |
| End of `cazic` | Slot 0 is moved to the stand-in; each other living player is placed by `world_findFreeSpot` (three shared draws per try) around it. All inputs are shared | Observed 0x19a0dc |
| Stand-in side effects | `Player_ctor` recomputes slot 0's statistics and clears that record's two weapon-trail blocks and one countdown byte; `Player_dtor` zeroes five record words at +0x43dc. Both run inside a tick on every machine | Observed 0x1a1d28, 0x1a1bb8 |
| Skip | Reads the pressed word of the lockstep pads. Skipping runs `cut_advance` to the end in one tick, with wait keys not waiting | Observed 0x199944 |
| `g_loadscreenActive` test in `cut_runFrame` | Returns before the skip and end handling while the loading screen is up. That is only during a level change, when no tick runs | Observed; docs/mainloop.md |
| Input lockout 0x41b4fc | Set to 60 by `cut_start` and every cutscene tick; zeroed at the start of every net tick. `Player_takeDamage` returns while it is set, with no network test | Observed 0x1b53d4; see "Noticed" |
| Corpses | `Creature_spawnScavenger` 0x1125e0 draws `g_randSeed` whenever a finished, drawn corpse turns from inactive to active, **before** it looks at the scavenger kind 0x402768 (0 in this level). Knight corpses stay for the rest of the level. Activity is decided by players outside cutscenes and corpses are frozen inside them | Observed 0x1126ac, 0x112738 |
| Doors | The door's state animation advances only while the door is active; passability follows the end of the animation. Its constructor does not randomise the phase | Observed 0x23c44c, 0x23cb54 |
| Flag props | Their idle animation starts at a phase taken from the cosmetic seed (0x23c95c). Their event bits are used only by props whose lump name starts with `pipepistona` | Observed |
| Script built-ins used | All lockstep according to docs/script.md; `setInfo` and `soundSequence` are presentation | docs/script.md |

## Ranked list

1. **G11–G13.** The only candidate with an Observed route from per-machine state to shared
   state inside the fight. In this level it needs a resurrected player, a rebase on the
   right tick and a party skill that reads the list. Not a candidate for "every time".
2. **D6/D7.** Closed for every writer found; a small unread remainder (drawing-side
   references to the camera globals).
3. **D21.** Occupancy is an order of magnitude below the limits, and the per-machine part
   is one block.
4. **D22/D23.** Fully traced; no per-machine input. Keep D22 as an amplifier.
5. **D8/D10/D19.** Fully traced; no route.

## What to record on two machines

One run, no patches, noting on both machines: the phase when the message appears (first
cutscene, knight fight, second cutscene, avatar fight, the wait after the avatar, last
cutscene before or after the first voice line), whether any player had died or been
resurrected, and whether the last cutscene was skipped.

| Observation | Points to |
|---|---|
| Knight fight, nobody has died | none of the five |
| Right after a death of a resurrected player, on that player's machine | G11–G13 |
| One tick after a cutscene starts | D6/D7 |
| Knight fight, shortly after a skeleton dies, knight 3 alive | D22 as amplifier of something else |
| Last cutscene, after the first voice line, not when skipped | D8 |
| 0x403a04 below 300 on either machine | D21 |

## Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| D19 (replace) | The speaker's run function cannot reach the sync hash while he is a cutscene actor: in state 0 with inert bits nothing consumes the animation's event bits, root motion or status word, and the level change is pending in the tick the cutscene ends | Inferred from Observed steps | `Zek_run` 0x2c2440; 0x10ded0; 0x10a9c0; 0x199f44–0x199f6c |
| D23 (replace) | The summoned skeleton has no corpse phase: `Skelight_setState` case 0x14 queues it for deletion and it is destroyed at the start of the next `runObjects`. Nothing on the path reads per-machine state | Observed | 0x2a91b8 (call 0x2a9414), 0x14b910 |
| D22 (add) | When a `Horsemen` casts Summon Skeleton the returned spell object is never linked or freed: one 0x180-byte pool block per summon until level unload | Observed | 0x272c70; 0x2e221c |
| D17 (correct) | The second delay runs at double rate after the 250 mark because the entry queues itself twice on that frame | Observed | `script.scr`, entry `bossDefeatedDelay`, source lines 98 and 103 |
| new | Cutscenes with header flag 8 freeze every creature with inert byte 0, players included (inert bit 4, flags 0x88000, off the grid), and restore those whose inert byte is exactly 4 | Observed | 0x199024 (call 0x19b3c0), 0x199074 (call 0x19a554) |
| new | The name table is written only by the object constructor and destructor; a lookup finds hidden, dead, grid-B and delete-queued objects | Observed | 0x14bce0, 0x14be58, 0x14bf58 |
| new | `g_cullByCamera` is derived from the per-machine camera mode word; during a cutscene every local writer of the mode is shut out | Observed / Inferred | 0x1e4d48; 0x2072e8 callers; 0x1db870 |
| new | A finished corpse that turns active draws `g_randSeed` once, whatever the scavenger setting | Observed | 0x1125e0 (0x1126ac before 0x112738) |
| G12 (correct) | The kill plane is disabled in every row of the level table. The clone route needs an attacker that runs after the victim; monsters that woke after the player object was linked run before it | Observed (table); Inferred (order) | 0x4f7210 +8; 0x1a5b3c; 0x14db08 |
| G (add) | `Player_dtor` rebuilds the alive list unconditionally, also when the copy is destroyed | Observed | 0x1a1c68 |
| D21 (answer) | In DRUNARE no creature gib chunk is created in a net game, the player blood chunk's lifetime does not depend on the gore option, and peak occupancy is far below both limits | Observed / Inferred | 0x110d30 gib branch; 0x1b3284; 0x201958 |

## Test patches (all untested)

One change each. PCSX2 form: `patch=1,EE,<address>,word,<new>`.

| # | Address | Original | New | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| T1 | 0x002726f4 | 1462000d | 1000000d | The variant test before the Summon Skeleton "can use" call always branches away: knight 3 never summons (it has no other route into its cast state) | Changes the fight; a mix of patched and unpatched machines desyncs at the first summon | yes |
| T2 | 0x001b3504 | 0c079cbe | 00000000 | Already in `patches/`: no immediate alive-list rebuild at a player's death | See that file | yes |
| T3 | 0x0014b9cc | 2842012c | 28420000 | The reaper's "fewer than 300 free" test becomes "fewer than 0": expendable objects are never reaped | If the pool really runs low, allocations fail and objects silently do not appear | yes |
| T4 | 0x00196aa0 | 0062102a | 00001021 | The "lip-sync animation ready" comparison always reads false: every machine uses the generic talk loop, no track carries flag 0x20, so the audio nudge never runs either | Lips no longer follow the voice. The preload still runs | yes, for a clean test |
| T5 | 0x001e4dd4 | 8043fcd0 | 00001821 | The load of the cutscene flag in `gameSetObjectVis` becomes zero: in a net game activity is always judged from player positions, never from the camera | Props near the cutscene camera but far from the players stop animating during cutscenes; actors are unaffected (radius 44000) | yes |

## Noticed on the way, not traced

- `Player_takeDamage` drops damage for **any** player while `g_menuInputLockout` is
  non-zero (0x1b53d4). `inventory_close` and `shop_close` set it to 60 only on a machine
  that has that menu open (0x1c52dc, 0x1d0b48), and they are reached inside a tick through
  `net_closeLocalMenus` when the local player dies (0x1b351c). For the rest of that tick
  the machine drops player damage. By F1 nothing that damages players runs after the
  players here, so it should not matter in this level; elsewhere it may.
- Trap props whose lump name starts with `pipepistona`: their damage window is switched by
  animation event bits (0x23cc70–0x23ce10) of a loop whose start phase comes from the
  cosmetic seed (0x23c95c). This is engine.md P4 with a concrete consumer. Not in this
  level; which levels use that lump is Unknown.
- `hud_run` opens the inventory inside the tick on the owner's machine and
  `menu_openInventory` 0x1c15c8 writes two player-record bytes (+0xed, +0xee) there before
  its message is processed elsewhere. Readers not traced.

## Corrections to earlier documents

- FINDINGS G12 and docs/player.md item 1: the kill plane cannot kill the copy, because no
  level enables it.
- FINDINGS D17: see the double-rate counter above.
- FINDINGS D23 and docs/creatures.md C5: the corpse rule quoted there needs creature flag
  0x1000000, which no arena class has.
- docs/engine.md P5: `PhProp_initPhysics` 0x155110 overwrites the orientation that
  `rigidbody_init` took from the cosmetic seed (it calls `quat_fromMat3` on the prop's
  matrix at 0x155310, then normalises). For that caller the physics start state is shared.
- docs/objects.md O2: the per-machine gib lifetime applies to chunks made by
  `Creature_processDamage`; the chunk made by `Player_processDamage` always has bit 0 set.
- docs/mainloop.md P5 calls 0x207dc4 a camera function; the address is a call inside
  `Vehicle_run` (the driver help text, which also clears vehicle +0x408).

## Not done

- `fx_modelStatusEffects` 0x1f6ac8, the weapon helper draw, the experience award 0x1d3150
  and `Creature_dropLoot` were not read. (Since read elsewhere: `fx_modelStatusEffects`
  and the weapon holder update in docs/issues/rescan.md section 6 — presentation only,
  D37; the experience award and loot in docs/issues/kill-loot-xp.md.)
- The avatar's own fight was taken from docs/monsters.md, not re-read.
- Where a player's attached spells get their per-frame call was not located.
- Whether `hideMonster` with a name shared by four objects hides all four.
- DiseaseBolt's exact lifetime; pool use of player skills.
- Whether a party can cast Resurrect in this level in practice.
