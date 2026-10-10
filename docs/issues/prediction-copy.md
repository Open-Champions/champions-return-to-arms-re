# The prediction copy: what it can change, and proposed fixes

Scope: every way the local-player prediction copy (object flag 0x20000, made by
`Player_clone` 0x11e870, run by `net_predictLocalPlayer` 0x131d88) can change state that all
machines are supposed to share. Everything here was read from the executable
(SLUS_209.73, v2.00); **nothing was run, and every patch below is untested.** Since then
three basic facts about the copy have been seen on the live game — one machine in a net
game in the Play! emulator, which is not a PlayStation 2 and not PCSX2
(`docs/issues/live-rig.md` 4d; `FINDINGS.md`, "Run on the live game", row V7): `Player_run`
is entered twice per frame, once for the copy; the copy is re-made every 31 ticks
(`g_ghostRebaseFrame` stepped 394, 425, 456 … 611, `Player_clone` entered each time); and
the copy carries object flag 0x20000 (flag word 0x00024060) while the real player carries
0x200000 (0x00204060). Nothing else here was re-checked there: what the copy can change in
shared state needs a second machine to show, and the only test patches run on a live game are the two for K1 and K2 (FINDINGS V10, V11).
Each statement is **Observed** (read at the address given), **Inferred** or **Unknown**.

New names used here are in `symbols/copyfix.tsv`. Proposed ledger rows and corrections to
earlier documents are at the end; `FINDINGS.md` and `patches/` were not edited.

## 1. Result in short

- One leak is confirmed: the copy's death rebuilds the alive-player list
  (`Player_processDamage` 0x1b3504). It has exactly one trigger in this build: the copy is
  cloned with the real player's *pending damage* (0x11ea84–0x11ea8c) and processes it one
  tick before the real player does. The kill plane, the other trigger named in G12, is
  switched off in all 90 levels (section 4.2).
- Smallest fix, one word, per machine: do not clone the pending damage (**P1**). A second,
  independent fix keeps the copy from ever rebuilding the list (**P2**, one word plus a
  nine-word routine in an unused function). Neither changes what a real player does, so
  neither has to match between players.
- The existing test patch (0x1b3504 → nop) also stops the leak but changes real deaths:
  a party heal that lands later in the same tick can give a dead player hit points, and the
  save-point revival then skips that player (section 6). It should be replaced by P1/P2.
- The ten unclassified `net_objOrGhost` call sites are classified (section 3.3). One is
  draw code. One (`SpellCyclone_run`) applies an animation start twice to the real player
  on every machine *except* the owner's; whether that reaches the simulation is Unknown
  (**P3**, optional).
- The virtual calls `Player_run` makes on the copy were followed: animation step,
  move/collide, all 50 "can use" functions, the two copy-castable skill casts, the damage
  function. None changes shared state (section 3.2).
- G9/G10 (PvP mana gift and orb from the copy's death) are not reachable for the copy
  (section 4.4). The "old and new copies overlap" part of D21 is not what the code does
  (section 2).

## 2. Facts about prediction that the rest depends on

All Observed unless marked.

| Fact | Where |
|---|---|
| The copy's run is one virtual call (slot 4) inside the prediction loop; afterwards hp, mana, `g_randSeed` and the table pointer are stored back | call 0x132c68; stores 0x132cbc, 0x132cc4, 0x132ccc, 0x132ce4 |
| `g_inGhostOp` 0x402795 and byte 0x4027a2 are 1 during each predicted frame and during a rebase | set at the top of each predicted frame and at 0x13b298, 0x13b2a0 (rebase); cleared 0x132ce8, 0x132cf0, 0x13b594, 0x13b598 |
| A rebase destroys the old copy **first** (slot 1 with argument 3, immediate free) and only then clones. There is never a moment with two copies | destroy 0x13b330, clone 0x13b540 |
| `g_forceGhostRebase` 0x402797 is a counter: each rebase subtracts one, and while it is above zero every `net_frameLoop` call rebases | 0x13b254–0x13b26c |
| A rebase is skipped while the *local* pause menu is open. Inferred from that: right after a level load one machine can be without a copy while another has one | 0x13b234 |
| `Player_dtor` 0x1a1bb8 calls `game_rebuildAlivePlayers` outside its `g_inGhostOp` test. Every rebase therefore rebuilds the alive list from the real players (the table pointer is the real one at that moment) | 0x1a1c68 |
| `Player_clone` is referenced only from the `Player` table (slot 15, 0x511384). The only slot-15 call through an object's +0x48 table in the whole executable is the rebase. So a change inside `Player_clone` affects the prediction copy and nothing else | scan of every `addiu r, r, 0x78` call sequence: 1 through +0x48 (0x13b534–0x13b540), 47 through a sub-object table at +0, 52 through a `Skill` table at +0x60 |
| `Player_clone` copies the pending-damage fields: amount +0xc8, flags +0x2dc, direction +0x2e0, push +0x2e8. It empties the attacker handle +0x2e4 | 0x11ea84/0x11ea8c, 0x11ebfc/0x11ec04, 0x11ebe8/0x11ebf0, 0x11ec08/0x11ec14; 0x11ebb0 |
| The active run list is last-in-first-out: `obj_runEveryFrame` 0x14f248 links at the head, `runObjects` walks from the head. `Player_ctor` links a new player there (0x1a2340). An object therefore runs *before* everything that was linked earlier | `handle_link` 0x1a1738 inserts at the head; walk in 0x14b910 |
| At level entry the level's objects are created first and the players after them (docs/mainloop.md, section 6 of its level-change list) | Inferred from that document, not re-read |

Consequence of the last two rows (Inferred): a hit is processed in the same tick when the
attacker runs before the victim, and stays *pending over the tick boundary* when the
attacker runs after the victim. A monster that became active after the player object was
made runs before it. Hits stay pending when they come from (a) an object that was already
on the active list when the player object was made — in particular everything, after that
player has been revived, because revival makes a new object (`player_respawn` 0x1bd040);
(b) a level script (`hitPlayers` 0x1424dc runs in the script task, after `runObjects`;
used by three level scripts: ISLC1, WATBONUS, WATMEDAL); (c) objects on the slow run lists.

## 3. Inventory

### 3.1 What the copy's `Player_run` reaches

"Restored" = undone by the four stores in section 2. "Own" = written to the copy's own
object. "Local" = per-machine presentation that no simulation code reads.

| What | Class | Evidence |
|---|---|---|
| `g_randSeed` draws; hp and mana changes | Restored | player.md; `Player_processDamage`, `Player_castSkill` |
| Position, animation, action state, timers, handles held by the copy | Own | — |
| **Alive list** (`g_alivePlayerCount`, `g_alivePlayers`, and the three local-list globals) rebuilt when the copy dies | **Leak** | 0x1b3504; section 4 |
| Game message 3/2 (menu state 0) sent by `net_closeLocalMenus(1)` when the copy dies | Goes through lockstep; every machine executes it on the same frame. Early by one tick, harmless | 0x1b351c → 0x1eb040 |
| Local menus closed, `g_forceGhostRebase`, HUD message, aura and prompt globals, rumble, voice, sounds, particles, decals, lights, trails, water ripples | Local | player.md list; `fx_spawn` 0x1ef270 draws `g_randSeed` only in its case 5, which the copy's call sites (types 0, 0x10, 0x11, 0x12) do not use; its 24 stores at 0x4f87bc–0x4f8818 are one-time initialisation flags |
| `g_unsyncedSeed2` 0x404468 (swing sound variant, 0x1aa8ac) | Already per machine by construction: the frames on which those sounds play depend on `net_isLocalSlot` (0x1aa6f4), so the copy's draws add nothing new | seven functions use it; docs/skills.md read three of them (effects only), the other four were not read |
| Record +0x4a5c | Written, no reader (G8) | — |
| Record +0x120 (carried load) | Recomputed from the bags; same value whoever computes it | `player_recalcLoad` 0x1bec10, called 0x1a9578 |
| Handle nodes, one object-pool block per transient spell, the copy's own grid link | Allocator state. Node *addresses* differ per machine already; block addresses do not, apart from the first-copy case — the copy is one 0x590 block in the 3000-byte class, re-made by free-then-allocate with nothing between, so it keeps its block, and the two smaller size classes are lockstep state (`docs/issues/stale-pointers.md` 5.1, ST1; the earlier version said node and block addresses both differ). No code orders by address (docs/runtime.md P7, docs/objects.md O8). A transient spell is freed before the cast helper returns, which puts the same block back on top of its free list | `handle_link`; 0x1a4598 → 0x1a45d0 |
| Six object creations, one record store, one target notification and one script hook on the *older ability paths* | Leak **if reachable** — needs an ability record whose name is not the `Skill` marker (D16, Unknown) | section 5.4 |
| Scavenger spawn at the end of `Creature_run` | Needs creature state 0x14 at +0x232 and creature flag bit 63. Inferred not reachable for a player: `Player` has its own state setter (slot 27, 0x1b5d68) and bit 63 is set only in the charm branch of `Creature_run`. The second reason is wrong (`docs/issues/field-claims-audit.md` 4.2, row 35): bit 63 is the "active" bit — `Creature_updateActive` sets it at 0x10c204 and clears it at 0x10c210, eight constructors set it, `Creature_stepAnim` tests it — so players have it set. The conclusion stands for another reason: the spawn (`Creature_spawnScavenger` 0x112660, which wants bit 63 set and bit 62 clear) also needs AI state 0x14 at +0x232, and in the Player table the only stores to +0x232 are `Creature_loadState` and the clone's copy | 0x1125e0 |
| Scripted walk (`Creature_moveToDest` 0x1a5604: path requests, and `Creature_moveBy` 0x113c48 calling slot 6 of touched objects with no test for the copy at 0x114220) | Not reachable for the copy: needs inert bits at +0x231, which only cutscene stand-ins get; the freeze callback skips players. (Corrected by docs/issues/arena-entry.md: "skips players" holds for `creatures_freezeAll` only. With cutscene header flag 8 the real players get inert bit 4, and a copy cloned from them inherits it. The row's conclusion stands for a different reason: the walk also needs action state +0x58c = 1, 0x1a55ac–0x1a5604) | docs/engine.md (stand-ins made with `Player_ctor`); `creature_unfreezeOne` note (Inferred) |

### 3.2 Virtual calls made on or by the copy

`Player_run` has 21 virtual call sites; `Creature_run` (5), `obj_moveWithCollision` (2),
`Player_castSkill` (7), `Player_updateCast` (2) and `Player_processDamage` (2) add 18.
`Player_move` has none.

| Call | Target for the copy | Result |
|---|---|---|
| Animation step: `Player_animStep` 0x1b9520 → `anim_advance` 0x16d748 | writes the copy's own layer stack and root motion; `g_animCueThrottle` 0x7b8fe0 (sound cap per rendered frame); the decode cache | No shared state. The cache holds accumulated root motion only for layers with flags 0x4800, and `animcache_alloc` never evicts those (0x16e3a0–0x16e3a8); every other entry is a pure cache |
| Move: `Player_move` 0x1b4020 → `creature_moveSimple` 0x1186d8 → `obj_moveWithCollision` 0x14d4b8 | moves and pushes only the mover; relinks the copy's grid node | The other object's slot 6 is skipped for the copy (0x14d9ac–0x14d9b0); the copy's own slot 6 is `Player_onTouch`, guarded. Other objects' moves cannot see the copy (box query skips 0x20000) |
| Knock-back: `Creature_applyKnockback` 0x115eb8 | returns at once for any player in a net game | so `Creature_moveBy` is not used for players online |
| Deadly water in `Player_move` (0x1b4490), timed damage in `Creature_run`, area damage of the older paths (`world_damageInRadius` 0x161270, called 0x1a6950 and 0x1ac400), melee | all go through `damage_apply` 0x1e8230 with the copy as attacker | `damage_apply` returns 0 before reading or drawing anything when the attacker has flag 0x20000 (0x1e828c–0x1e82a4). `Player_meleeHit` 0x1b6a98 also returns at its first test. So nothing the copy does can damage anything, itself included |
| Take damage (slot 2) on the copy | never called: nothing obtains the copy as a victim (box queries, run walks and handle iterators skip it; none of the 17 `net_objOrGhost` sites passes its result to a damage call) | Inferred from the sites read |
| Skill "can use" (slot 1), called 0x1a4358, 0x1a5d54, 0x1a7088, 0x1ab618 | 50 distinct functions serve the 101 ids | Scanned every one for calls and stores: they call only spell-list lookups, `player_getSkillRank`, box and name queries, trigonometry, `terrain_height`, and `text_lookup` + `hud_showMessage` (local HUD text). No store outside the stack frame. For the copy the "already active" tests always pass because its spell list is empty; that only affects the copy |
| Skill rank (Player slot 39), mana cost (Skill slot 5) | getters | — |
| Skill cast (slot 2) for the copy: only ids 41, 84 (Cyclone) and 51 (AncestralCall) (flag bit 0; docs/skills.md, not re-read) | `SkillCyclone_cast` 0x2d161c, `SkillAncestralCall_cast` 0x2e0750 → constructors 0x2d17c8, 0x2e09b4 | Each tests the owner's 0x20000 (0x2d19cc, 0x2e0b80) and for the copy skips the voice line, target gathering, handle links and object creation. Before the test Cyclone links the spell's light and starts an animation on the owner; AncestralCall plays a sound and starts an animation. The spell is destroyed at 0x1a45d0; destructors 0x3cd964 and 0x3ce95c only unlink |
| Spells of the copy (Creature slot 17 from `Player_updateCast`) | the copy's spell list is empty (G2) and the cast helper never attaches one | nothing runs |
| Turn toward a point (slot 26), "is enemy" (slot 20) | called on the copy itself | own state / pure |
| Vehicle seat pose in state 0xd (0x1a5efc) | `Vehicle_getRiderPose` 0x2088a0, a getter | closes the open question in player.md |
| Target notification, kind 3 (0x1aa5b8), no test | no class handles kind 3 (player.md) | latent |

### 3.3 `net_objOrGhost` 0x13e180 — all 17 call sites

The function returns the copy only for a player in a local slot of a net game with a copy
present; otherwise it returns its argument. On every machine but the owner's, "the result"
is therefore the real player itself.

| Call site | Function | What the result is used for | Class |
|---|---|---|---|
| 0x113284, 0x113550 | `Creature_run` | burn visuals only when result == self | cosmetic (known) |
| **0x1e4c1c** | `minimap_draw` 0x1e42e0 | list of objects to draw as blips | **draw code, not simulation** |
| 0x2c88e4 | `SkillCharge_cast` | action state 9 written to the result too | same write twice on other machines; idempotent |
| 0x2c8fe0 | `SpellCharge_run` | action state 2 or 3 written to both | idempotent |
| **0x2d1b04** | `SpellCyclone_run` | `anim_startBlendInOut` on the owner (0x2d1d1c) and again on the result (0x2d1d38) when the result is not null (0x2d1d24) | **not idempotent**: see below |
| 0x2dee18 | Bash particle helper 0x2dedec | attach-point positions for 203 particles | position only; the spell-generator draws do not depend on it |
| 0x2e1144, 0x2e1214 | `SpellAncestralCall_run` | ring position, height test before a particle | position only |
| 0x2e7cf8 | `SpellCriticalHit_run` | ring position; draw count is level-based | position only |
| 0x2e95cc | `SpellHealing_run` | ring position; draw count is level-based | position only |
| 0x2fb4c8 | ShieldBash particle helper 0x2fb49c | as 0x2dee18 | position only |
| 0x2feed8, 0x2ffbd0 | `SpellSummonAxe_run`, `SpellSummonArrows_run` | emitter transform; draw count is time-based | position only |
| 0x302650 | `SpellBattleCry_run` | ring position; draw count is level- and time-based | position only |
| 0x303454 | `SpellBloodLust_ctor` | two hand positions of the result stored in the spell (+0x34, +0x40) | spell state becomes per machine |
| 0x3036e4 | `SpellBloodLust_run` | compares them with the result's current hands; the number of `Spell_rand` draws depends on the distance and on option 0x44fdc0 | the spell's private generator diverges, but in this spell it feeds particles only (docs/skills.md; re-checked: no damage call, allocation or creature write uses a drawn value) |

`SpellCyclone_run`, Observed: each `anim_startBlendInOut` call pushes a layer unless the
stack is full (0x16ceb0). On the owner's machine the real player gets one new layer and the
copy one; on every other machine the real player gets two. `anim_advance` removes all lower
layers once a layer with flag 2 reaches full weight (the spin layer has flags 0x32 and a
blend-in of zero), so at normal speed the extra layer disappears at the next animation step
and the returned event bits are the same. While it exists it changes the weights of the
layers below, which matters only if one of them carries root motion (flag 0x800) and the
step takes more than one frame to reach full weight — that is, when the owner's animation
is slowed (slow amount +0x2fc, or Drowsy). Whether that reaches a position is **Unknown**.

### 3.4 Outside the copy's run

- The copy is in the world grid and can be on a run list; box queries skip it by a
  hard-coded test and run walks by the exclude mask (G6). Not re-checked here.
- `objNames_remove` is called by the base destructor with the object pointer; the clone is
  never registered, so destroying it removes nothing (Inferred from the symbol note).
- Pool occupancy: the copy is a 0x590-byte object, which only fits the largest of the three
  size classes (32 blocks of 3000 bytes). Each machine holds one, so counts match except
  when one machine has no copy (pause menu, section 2). D21 otherwise stands.
- Drawing (D12, D13) was not revisited.

## 4. The confirmed leak: the alive list

### 4.1 Mechanism (Observed)

`Player_processDamage` runs for the copy (0x1a5b90). If the damage it processes takes the
shared hit points to zero it marks the copy dead and calls `game_rebuildAlivePlayers`
(0x1b3504). The rebuild looks at the object pointer in each record, which during prediction
is the copy for the local slot, so the local slot is dropped from `g_alivePlayers`, and
`g_localAliveCount` becomes 0. Hit points are stored back; the list is not.

The list is next rebuilt (a) on the spot when the real player dies, (b) at the end of the
next simulated tick (`tasks_run`, 0x3227dc), (c) by the copy's destructor at the next
rebase (0x1a1c68) — which happens *after* that tick. So the list is wrong on that one
machine from the start of the next tick until (a) or (b). (A rebase in a call that runs no
tick does repair the list, but the fresh copy is cloned with the same pending damage and
dies again in that call's prediction. Inferred.)

### 4.2 The only trigger: cloned pending damage

- Nothing can damage the copy during prediction (section 3.2).
- **The kill plane is off.** `Player_run` compares the height with `g_killPlaneZ` only when
  the plane is above −90000 (0x1a5b38). The value is loaded from the level table
  (`g_levelTable` 0x4f7210, 90 rows of 0x30 bytes, height at +8; store at 0x1e5de8) and all
  90 rows hold −100000. The table is referenced only by `game_loadLevel`, and nothing else
  writes `g_killPlaneZ`. Observed. So the first half of G12 does not happen in this build.
- That leaves damage that was already waiting on the real player when the copy was cloned.
  The copy subtracts it from the real hit points, so the copy dies exactly when the real
  player is going to die at its next `Player_run` — one tick later — unless a heal, a
  cutscene or a dialog intervenes first. Which hits are still waiting at a rebase is
  decided by run order (section 2): script damage always; monster hits when the monster
  runs after the player, which is the normal case for a player who has been revived in
  this level and the exception before that. Inferred.

### 4.3 What reads the list inside the window

The window is the part of one tick before the local player's own `Player_run`: the game
message handlers, the tasks ahead of `runObjects`, and every object that runs before the
local player (objects linked later). Read for this document:

| Reader | What it does with the list | Effect of the local slot missing on one machine |
|---|---|---|
| `Player_run` state 1, every player, every frame of a swing (0x1aa018–0x1aa0d0) | asks the AncestralCall (helper 0x2e1470) or BattleCry (helper 0x302c04) spell of every *listed* player for a factor and uses the largest as the swing animation rate | another player's swing advances at a different rate for that tick if the dying player carries the spell |
| `Player_recalcDamage` (0x1b7810–0x1b7888) | same scan (AncestralCall only); scales record +0xcc, +0xd0, +0xd4 | another player's damage figures differ |
| `SpellHealing_run` (0x2e9158 on), `SpellCriticalHit_run` (0x2e7e58 on), `SpellBattleCry_run`, `SpellAncestralCall_run` | heal or buff every listed player in range | the dying player is healed on the other machines and not on its own; it can survive there and die here |
| `Prop_run` 0x154850, `PhProp_run` 0x156d24 | delete the prop when it is 120 units below the *first listed* player (they read slot entry 0 without looking at the count) | a falling prop is deleted on a different tick; `PhProp_run` otherwise creates a resting prop, whose constructor draws `g_randSeed` |
| The leave-request branch of `hud_onMsg` (0x1d8f5c on; list read at 0x1d8f84–0x1d8f9c; message 3/6 by its role) | revives somebody when the leaving player is the only one listed | different decision |
| `Player_run` 0x1a5284 | light radius when the count is 2 | local |
| `Savepoint_scanPlayers` 0x28d720 (every 8th frame), `Savepoint_run` 0x28d544, `JumpGate_run`, `OniBall_run`, scripts (`countPlayersAlive`, `hitPlayers`, `closestPlayerDist`, `givePlayerItem` …) | — | not read in detail; scripts run after `runObjects`, by which time the real death has normally repaired the list |

No creature targeting function references the list (no reference found in 0x100000–0x131a40),
so monsters themselves do not react. 53 functions reference the list; about 40 were not
read (camera, HUD and menus among them; two table-called functions at 0x27a750 and
0x27a7d0).

### 4.4 What else the copy's death does

- The PvP tail of `Player_processDamage` (G9) needs the attacker handle +0x2e4. The clone
  starts with it empty (0x11ebb0) and only take-damage links it (`Player_takeDamage`
  0x1b5728, `Creature_takeDamage` 0x1166d4), which nothing calls on the copy. So the mana
  gift and the orb cannot run for the copy (Inferred); `arena_loseLife` is guarded
  (docs/skills.md). G10 reduces to the alive list.
- `fx_disintegrateModel` 0x1f4340: particles and a sound only (calls checked).
- Blood prop and the StrongStance trigger: guarded (0x20000 tests in the same function).

## 5. Fix proposals

All untested. One row per changed word; "Every player" says whether machines must agree.
Words are the 32-bit instruction in hex, as PCSX2 `word` patches take them. Original words
were read from the executable.

| ID | Address | Original | New | What it changes | What could go wrong | Every player |
|---|---|---|---|---|---|---|
| P1 | 0x0011EA8C | E60000C8 | AE0000C8 | `Player_clone` stores zero instead of the copied pending-damage amount (+0xc8). The copy then never loses hit points and never dies in prediction (section 3.2), so the alive list is never rebuilt from it; the early game message and menu close of section 3.1 go too | The copy no longer flinches or dies one tick ahead of the real player; the forced rebase caused by the real hit corrects it. A missed path that damages the copy would not be covered (P2 covers it). Real players are untouched: `Player_clone` runs only for the copy (section 2) | No. Changes only the copy on the machine that applies it; a mixed game is no worse than an unpatched one |
| P2 | 0x001B3504 | 0C079CBE | 0C0C85C0 | `Player_processDamage` calls the routine R1 (5.2) instead of `game_rebuildAlivePlayers`. R1 returns without rebuilding when the dying object is the copy and otherwise jumps to the original function | R1 reads `$16` (a saved register holding the object; the store in the call's delay slot does not change it) and clobbers `$2`/`$3`, as the original call does. Needs the nine words of R1 in place first. Collides with any other patch that uses 0x321700–0x321723 | No, as P1 |
| P3a | 0x002D1B14 | 0000802D | 02C0802D | `SpellCyclone_run`, offline branch: the "copy" register is set to the owner instead of null. **Only together with P3b** | Alone it makes the offline game start the animation twice | Not required (see 5.3) |
| P3b | 0x002D1D24 | 12000006 | 12160006 | The second animation start is skipped when the result of `net_objOrGhost` is the owner itself (was: when it is null). **Only together with P3a** | Alone it would start an animation on a null object when offline. If something relies on the doubled start, behaviour changes | Not required |
| O1 | 0x001A6700 | 0C053F6E | 0C0C85C9 | Older ability path, state 0xc: `pool_new` replaced by routine R2 (5.4), so the `LightEffect` is not created for the copy | For the copy the effect is not shown ahead of time. Needs R2 in place first | No |
| O2 | 0x001ABDB8 | 0C053F6E | 0C0C85C9 | Same, `LightEffect` built at 0x1abe68 | as O1 | No |
| O3 | 0x001AC008 | 0C053F6E | 0C0C85C9 | Same, object built by 0x293704 at 0x1ac02c | as O1 | No |
| O4 | 0x001AC070 | 0C053F6E | 0C0C85C9 | Same, `LightEffect` built at 0x1ac120 | as O1 | No |
| O5 | 0x001AC128 | 0C053F6E | 0C0C85C9 | Same, `UnholyAura` built at 0x1ac164 | as O1 | No |
| O6 | 0x001AC2C4 | 0C053F6E | 0C0C85C9 | Same, `LightEffect` built at 0x1ac378 | as O1 | No |

### 5.1 P1 — do not clone pending damage (recommended first)

`Player_clone` copies the fields one by one; the pair at 0x11ea84/0x11ea8c loads the
amount from the real player and stores it in the new object. P1 replaces the store. The
cloned damage flags (+0x2dc, stored at 0x11ec04, original word AE0302DC) can still make the
copy play a stagger from the flags alone; that is cosmetic and is left as it is.

### 5.2 P2 — the copy never rebuilds the alive list

The routine R1 is placed in `splash_ubiLogo` (0x321700–0x321787, 34 words), an unused
boot-screen callback: no call, jump or branch from outside, no address formed by a `lui`
pair, and no data word in any loaded segment points into it (scan of the whole file;
docs/mainloop.md lists it as unused too). The scan cannot exclude an address computed at
run time. R1 can be moved by changing only the call word of P2.

R1 (my own code; `$16` = the object):

```
0x321700  lw   $2, 0xc($16)      ; object flags
0x321704  lui  $3, 0x2           ; 0x20000
0x321708  and  $2, $2, $3
0x32170c  bnez $2, 0x32171c      ; the copy: skip
0x321710  nop
0x321714  j    0x1e72f8          ; real player: game_rebuildAlivePlayers, returns to the caller
0x321718  nop
0x32171c  jr   $ra
0x321720  nop
```

| Address | Original | New |
|---|---|---|
| 0x00321700 | 3C040055 | 8E02000C |
| 0x00321704 | 3C050055 | 3C030002 |
| 0x00321708 | 27BDFFF0 | 00431024 |
| 0x0032170C | 24A54340 | 14400003 |
| 0x00321710 | FFBF0000 | 00000000 |
| 0x00321714 | 0C05CD97 | 08079CBE |
| 0x00321718 | 24844330 | 00000000 |
| 0x0032171C | 0000282D | 03E00008 |
| 0x00321720 | 3C088080 | 00000000 |

Each new word that has an identical instruction elsewhere in the executable was compared
with it (for example 8E02000C at 0x10af38, 3C030002 at 0x113834, 14400003 at 0x1006f0); the
jump word was checked by re-encoding an existing jump.

P1 removes the only known trigger; P2 closes the write whatever the trigger. They are
independent and can be tested one at a time.

Considered and not proposed: saving the list before the copy's run and restoring it after
(a wrapper around the call at 0x132c68). It needs roughly 25 words and is equivalent to P2
for every reader outside the copy's own run.

### 5.3 P3 — `SpellCyclone_run`: start the animation once (optional)

With both words, the spin animation is started once on the real player wherever the result
of `net_objOrGhost` is the owner itself (the owner is remote, or no copy exists). That is
what the owner's own machine already does. Offline nothing changes: one start before and
after. `$16` (the result) and `$22` (the owner) were checked from 0x2D1B10 to 0x2D1D30:
`$22` is loaded in the delay slot at 0x2D1B00 on both paths and `$16` has no other use
before it is reused at 0x2D1DA4.

Every player: not required. A patched machine does what every owner's machine already
does; an unpatched one behaves as today. Only worth testing if a desync is seen when
another player uses Cyclone, especially while slowed.

### 5.4 O1–O6 — older ability paths (optional; reachability Unknown)

Six places in `Player_run` create an object with no test for the copy (player.md item 4).
They are reached only through an ability record that is not a `Skill` (D16). If one is
reachable, the object exists on one machine only. Each site calls `pool_new` and already
skips the constructor when it returns null, so one shared routine "return null for the
copy" fixes each with one word. `$fp` holds the object throughout `Player_run` (set at
0x1a5040, restored only in the epilogue). For a real player R2 jumps to `pool_new` with the
size argument untouched.

R2, at 0x321724, directly after R1 in the same unused function:

```
0x321724  lw   $2, 0xc($fp)
0x321728  lui  $3, 0x2
0x32172c  and  $2, $2, $3
0x321730  bnez $2, 0x321740      ; the copy: return null
0x321734  nop
0x321738  j    0x14fdb8          ; pool_new, size still in $4
0x32173c  nop
0x321740  jr   $ra
0x321744  move $2, $zero
```

| Address | Original | New |
|---|---|---|
| 0x00321724 | 0040202D | 8FC2000C |
| 0x00321728 | 0000302D | 3C030002 |
| 0x0032172C | 24070003 | 00431024 |
| 0x00321730 | 0C05FEDA | 14400003 |
| 0x00321734 | 35088080 | 00000000 |
| 0x00321738 | 3C020042 | 08053F6E |
| 0x0032173C | 2444BFD8 | 00000000 |
| 0x00321740 | 3C020045 | 03E00008 |
| 0x00321744 | 8C43FDCC | 0000102D |

Not covered by O1–O6: the store of 1 to record +0x4a7c at 0x1A74B0 (original word
A0824A7C) on the same older paths, which needs a test of its own, and the two latent calls
(0x1AA5B8, 0x1A90F0).

### 5.5 Proposed patch text

```
[Net fix: prediction copy is cloned without pending damage]
description=Untested. Player_clone (only used for the local prediction copy) stores zero instead of the real player's pending damage, so the copy cannot die ahead of the real player and rebuild the alive-player list on one machine. Affects only the machine that applies it.
// was: E60000C8
patch=1,EE,0011EA8C,word,AE0000C8

[Net fix: prediction copy never rebuilds the alive list]
description=Untested. Player_processDamage calls a 9-word routine placed in the unused splash_ubiLogo (0x321700) that skips game_rebuildAlivePlayers when the dying object is the prediction copy. Real players are unchanged. Affects only the machine that applies it.
// was: 0C079CBE; routine words were 3C040055 3C050055 27BDFFF0 24A54340 FFBF0000 0C05CD97 24844330 0000282D 3C088080
patch=1,EE,00321700,word,8E02000C
patch=1,EE,00321704,word,3C030002
patch=1,EE,00321708,word,00431024
patch=1,EE,0032170C,word,14400003
patch=1,EE,00321710,word,00000000
patch=1,EE,00321714,word,08079CBE
patch=1,EE,00321718,word,00000000
patch=1,EE,0032171C,word,03E00008
patch=1,EE,00321720,word,00000000
patch=1,EE,001B3504,word,0C0C85C0
```

The routine words are listed before the call word so that the call never points at
unpatched code.

## 6. The existing test patch (0x1B3504 → nop)

It removes the rebuild for the copy *and* for real players, so a real death is only noticed
by the list at the end of the tick. For the rest of that tick every later reader still sees
the dead player as listed. The object still exists, so nothing reads freed memory, and with
the patch on every machine all of them see the same thing. But behaviour changes:

- **A dead player can be given hit points.** `SpellHealing_run` adds hit points to every
  listed player in range and has no test of the dead flag; it relies on the list
  (0x2e9158 on). A healer whose object runs after the dying player's in the same tick heals
  the corpse. Observed code, Inferred outcome.
- **That player is then not revived at save points.** `Savepoint_run` revives the last
  active slot whose hit points are ≤ 0 (0x28d564–0x28d590). A corpse with hit points above
  zero never qualifies. Inferred. (The Resurrect skill's target search, 0x31270c, reads the
  list rather than hit points; it was not read further.)
- Group buffs (CriticalHit aura, BattleCry, AncestralCall) are applied to the corpse for
  one tick; the swing-rate and damage scans count its buffs for one more tick; scripts in
  the same tick count it as alive; the two other callers of `Player_processDamage` (the
  kick path 0x13aeb8 and a game-message handler, 0x1d8ef0) lose their immediate rebuild
  too. One tick each, same on all machines.
- It must be on every machine: with it on one side only, the two machines disagree about
  the list for the rest of every tick in which a real player dies.

`game_checkAllDead` runs directly after the end-of-tick rebuild and is not affected.
Recommendation: withdraw this patch in favour of P1 (and P2), which leave real deaths
exactly as shipped.

## 7. Ranking for ordinary co-operative play

| Rank | Leak | How often the condition occurs | Does it change shared state |
|---|---|---|---|
| 1 | Alive list rebuilt by the copy (4.1) | Whenever the local player's killing blow is still pending at a rebase: script damage always; monster hits after that player has been revived once in the level; rarely before | Yes on that machine for part of one tick; a visible desync also needs one of the readers of 4.3 to run inside the window |
| 2 | Cyclone animation started twice on non-owner machines (3.3) | Every Cyclone cast | Unknown; at normal animation speed probably not |
| 3 | Pool occupancy (D21) | One machine without a copy, or pools nearly full | Only at the pool limits |
| 4 | BloodLust private generator (3.3) | Every BloodLust cast | Contained in particles |
| 5 | Older ability paths (5.4) | Only with a non-`Skill` ability record | Yes if reachable |
| 6 | Kind-3 target notification, arrow-shot script hook, record +0x4a5c | Latent | No handler, no script, no reader |

What a two-machine test should try first: the alive list, and first as a *measurement*, not
as a hunt for the out-of-sync message.

1. No patches. Player A dies and is revived at a save point, then fights monsters that were
   already active. On A's machine watch `g_alivePlayerCount` 0x4f8420 for a write while
   `g_inGhostOp` 0x402795 is 1 and the return address is 0x1b350c (every rebase also
   writes it with the flag set, from 0x1a1c68). Expected: the count drops during
   prediction just before A's next death, and only on A's machine. A level whose script
   uses `hitPlayers` (ISLC1) should show it without the revival.
2. Same scene with P1 on A's machine only: no such write.
3. Only then look for a desync: the dying player carrying AncestralCall or BattleCry while
   a player whose object is newer is swinging, or a party heal running on the dying player.
   This may take many attempts; step 1 is the reliable observation.

## 8. Proposed ledger rows and corrections

Proposed rows (prediction section):

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| G14 | `Player_clone` runs only for the prediction copy; it copies pending damage (+0xc8, +0x2dc, +0x2e0, +0x2e8) and empties the attacker handle | Observed | 0x511384; slot-15 scan; 0x11ea84–0x11ec14, 0x11ebb0 |
| G15 | The kill plane is disabled in all 90 levels (−100000 in every row of the level table), so the copy cannot die from it. G12's first route is withdrawn | Observed | 0x4f7210 + n × 0x30 + 8; 0x1e5de8; 0x1a5b38 |
| G16 | Nothing can damage the copy during prediction: `damage_apply` and `Player_meleeHit` return for a copy attacker, and nothing calls its take-damage slot. Cloned pending damage is the only way it loses hit points | Observed (each part), Inferred (completeness) | 0x1e828c–0x1e82a4; 0x1b6a98; section 3.2 |
| G17 | The active run list is last-in-first-out, so a hit stays pending over a tick boundary only when the attacker was linked before the victim, or comes from a script | Observed (list), Inferred (consequence) | 0x14f248, 0x1a1738, 0x1a2340 |
| G18 | After the copy dies the list is wrong on that machine for the first part of exactly one tick; every rebase and every end of tick repairs it | Observed | 0x1b3504, 0x3227dc, 0x1a1c68, 0x13b330 |
| G19 | Readers inside that window that change shared state: swing-rate and damage scans for AncestralCall/BattleCry, group heal and buff spells, prop clean-up by the first listed player's height, the leave-request message handler | Observed (the readers), Inferred (the effect) | 0x1aa018, 0x1b7810, 0x2e9158, 0x154850, 0x156d24, 0x1d8f84 |
| G20 | The PvP tail of `Player_processDamage` (G9) cannot run for the copy: its attacker handle is always empty. G10 reduces to G11 | Inferred | 0x11ebb0, 0x1b5728, 0x1166d4 |
| G21 | Removing the rebuild at 0x1b3504 for real players lets a same-tick party heal give a corpse hit points, after which save-point revival skips it | Inferred from Observed code | 0x2e9158 on; 0x28d564–0x28d590 |
| G22 | `SpellCyclone_run` starts its animation twice on the real player on every machine but the owner's | Observed; effect on the simulation Unknown | 0x2d1b04, 0x2d1d1c–0x2d1d38, 0x16ceb0 |
| G23 | All 17 `net_objOrGhost` call sites are classified; apart from G22 and the contained BloodLust case none can change shared state | Observed | section 3.3 |

Corrections to earlier documents:

- **netcode.md, per-machine row 6:** 0x1e4c1c is in `minimap_draw` (draw code), not in
  simulation code. The other nine "not classified" sites are in section 3.3.
- **FINDINGS G12 / player.md item 1:** the kill-plane route does not exist in this build
  (G15). The deadly-water damage in `Player_move` does not hurt the copy either (copy as
  attacker).
- **FINDINGS G9, G10:** see G20.
- **FINDINGS G11:** "prediction does not restore the list" is right, but the copy's
  destructor rebuilds it at every rebase (0x1a1c68).
- **FINDINGS D21:** old and new copies do not overlap; the old one is freed before the
  clone is made (0x13b330, 0x13b540).
- **player.md item 4:** the area damage at 0x1ac400 is harmless for the copy
  (`damage_apply` returns for a copy attacker). The object creations on those paths remain.
- **player.md open question on state 0xd:** the vehicle call is a getter (0x2088a0).
- **skills.md (b) item 3:** for `SpellCyclone_run` the extra write does not land "on the
  copy only": on machines where the owner is remote it lands on the real player a second
  time (G22).
- **patches, "alive list only rebuilt at end of frame":** see section 6.

## 9. Not done, not known

- `Player_run` itself was not re-read line by line; its direct statements are taken from
  player.md and were spot-checked only where this document cites an address. Its record
  writes were re-listed from the decompile and match player.md.
- Which skills carry flag bit 0 is taken from skills.md.
- About 40 of the 53 functions that reference the alive list were not read.
- Whether any character has an ability record that is not a `Skill` (D16) — decides 5.4.
- Whether the doubled Cyclone animation layer can change a position (3.3).
- How many deaths in real play have the killing blow pending at a rebase; section 2 gives
  the rule, not the proportion.
- Whether `splash_ubiLogo` is safe to overwrite on a running game (static scan only).
- Whether another proposal claims the same unused words.
- The readers of the *local* alive lists inside the simulation (`Vehicle_run` 0x207d28,
  `Creature_run` 0x11399c, `player_pollRecallButton` 0x1bce88) are per machine by
  construction, with or without the copy; they were not followed.
- Drawing of the copy and the status counters (D12–D16), exhaustion of the handle-node
  pool, and the grid and run-list presence of the copy were not re-examined.
