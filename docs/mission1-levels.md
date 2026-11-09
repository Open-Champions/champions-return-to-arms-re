# Mission 1 levels: strife, drundar, drunarm, drunare (SLUS-20973 US v2.00)

2026-11-09. **Research handoff for a client, not a played route.** This covers
the two story levels the `blood1` choice leads to (`strife`, good; `drundar`,
evil) and their arenas (`drunarm`, good; `drunare`, evil). `blood1` is covered
elsewhere. Mission completion itself (the arena grants, the avatar death chain,
the `shardofwar` count, the Rallos chain) was audited in
`t3/research-mission-unlocks` `2ab82b2`, `docs/spec/mission-unlocks.md` lines
279–546. It is cited here, not redone. This document fills what that audit left
**Unknown** at its lines 534–537: how play reaches the avatar death and the
Rallos trigger, the cutscenes, each level's objects and encounters, every exit,
and the good path's return to a hub.

Labels follow `CONTRIBUTING.md`. **Observed**: read in the bytes at the address
given. **Executed**: run in `tools/ee_emu.py` by
`tools/difftest_mission1_levels.py`. **Inferred**: follows from those, not seen
directly. **Unknown**: not established. Nothing here was **Ran** on a game.

## 1. What was run, and what was stubbed

`tools/difftest_mission1_levels.py` (lines 169–372, `Host`) loads each level's
`script.scr` from the private disc through the original `scr_load` 0x13e8f8
and `scr_registerNatives` 0x141310. It then runs entries through
`script_runByName` 0x1ed694, frames through `script_runDeferred` 0x1ed5a0, and
post actions through `script_runPostAction` 0x1edac0. The campaign natives keep
their original bodies: `getv`/`setv`, `addDeferedCall`, `postAction`,
`callScript`, `newWorld`, `getScaledTime`, `gamePaused`, `grantMission`,
`playerHasItem`, `onePlayerHasItem`, `removePlayerItem`, `removeQuest`,
`demoRunning`, `sin1000`, `cos1000`. Each one gets a recording hook at its
first instruction. These are **stubbed**, and only record their decoded
arguments: the `STUB_NAMES` set at lines 85–92, which covers monster
show/hide/kill/delete/values/flags, auto-prop state, save inhibit, cutscenes,
sounds, notices, help, busts, dialog, particles, `getHitPoints`, `addQuest`,
`trigger`, `preloadResource` and `setParticle`. So are
`inventory_countItemByName` 0x1c5880 (it returns the test's counts),
`inventory_findItemBySubstring` 0x1c5a70 and `inventory_removeItem` 0x1c1cb0.
Text-key arguments are recorded only as `<text>` (lines 95–107, 216–232). A
*frame* is one `script_runDeferred` call. A cutscene's length is synthetic: the
test sets `g_cutsceneActive` 0x44fcd0 for a stated number of frames, then runs
the post action.

`tools/ref_mission1_levels.py` `Model` (lines 262–987) is the four scripts
rewritten in Python from the listings. `Pair` (difftest lines 402–486) runs
each step on both. After **every** step and frame it compares the following:
the ordered native list with arguments, the entries started, the
return value, all quest variables, the post action, the pending level
0x41b6d0, both deferred halves, the mission-1 byte and the script globals
named in `CELLS` (lines 391–396). Before the first step, every compared global
holds a sentinel 0x5a + cell (`plant`) in the strife, drundar and drunare runs,
in drunarm's runs `q` (cells 0x4, 0xc, 0x10), `r` and the eight `start` states,
so a store of 0 that the model makes and the original does not (or the reverse)
shows as a state divergence. drunarm's runs `p`, `x` and `w` start from the
`scr_load` state (all 0). For `p` that is on purpose: it is the state the
misspelled `prestart` leaves. `x` and `w` store only cells whose stores are
proven elsewhere: 0x4 and 0x10 by run `q`'s sentinels, 0x8 by value in `p`. Five **controls** must make the two disagree (lines
1208–1251): drunarm's `endDelay` literal 275 changed to 276, drundar's `A == 8`
changed to 7 (both in the in-memory image), the model's `getScaledTime` changed
to `n`, and the model without one zeroing store each in strife `step2pause`
(0x154) and drundar `preStart` (0x28). All five are rejected by a log or state
divergence. The register seed changes only the factory's record order and the
seed word 0x404464.

## 2. strife (good story level)

**Objects (Observed, Executed in `t3/research-strife-drundar` `0d42d46`):**
283 records. The class counts and constructors are in `docs/strife-drundar.md`
lines 15–129. The hostiles are 69 Orc2 placements: 43 Soldier, 20 Archer,
2 Leader, 2 Leader1, 2 Shaman. The scripted pieces are 4 NPC scouts, 2
Catapults, 15 `kelethinBomb` droppers, 3 `dbridge` bridges, 3 save points, one
Portal, 2 PushTriggers, 2 Triggers and 2 `Player1` markers (one has
`from=drunarm`).

**Scripted encounters (Observed links, Executed run).** The links are pinned in
`LINKS["strife"]` (ref lines 58–123) and checked at difftest lines 825–852:

- *Stage 1, orcs.* Thirteen Orc records (8 Archer, 5 Soldier) carry
  `initscript` `callScri52e` and `deathscript` `callScria77e`. `preStart` sets
  global 0x140 to 1 and `start` clears it (ref lines 600–623). An init script
  that runs during object load adds one to 0x144; a death subtracts one; both
  only while `sfe_step1Complete` is clear. **Executed:** after `preStart`, the
  13 + 2 init scripts and `start`, global 0x144 is 13 and 0x148 is 2 (difftest
  lines 636–650).
  The counter starts when the first scout's dialog action `setv176d` sets
  `sfe_talkedtofirstscout`, calls `showOrcCounter` and adds the quest.
  `showOrcCounter` (ref 635–647) polls every frame with a bust until 0x144 is
  0. It then sets `sfe_step1Complete` and queues `step1delay`. **Executed:**
  `step1com` is requested 102 frames after `step1delay` is queued, because
  `getScaledTime(n)` is `n − 1` and the test is `> 100`. Its post action
  `hideElf1` shows `we_scout_2` and hides `we_scout`.
- *Stage 2, shamans.* The two `Orc2Shaman` records (`miniboss=1`) carry
  `callScri9f82` / `callScri4980`. The second scout's action `setv23a8` calls
  `trigger('bridge1', 1)` and starts `showShamanCounter`. When 0x148 reaches 0:
  `sfe_step2Complete`, `step2pause`, then `step2complete` after 102 frames,
  then post action `hideElf2`.
- *Stage 3, catapults.* Both Catapults' `deathscript` `callScri8d4a` raises
  global 0x14c and persists it as `sfe_step3counter`; `preStart` reloads it.
  The third scout's action `setv8921` calls `trigger('bridge2', 0)` and starts
  `showCatCounter`. When 0x14c is 2: `sfe_step3Complete`, `setSaveInhibit(1)`,
  then `step3complete` after 102 frames, then post action `hide3` (hides
  `we_scout_3`, `setSaveInhibit(0)`).
- *Bombardment.* The 15 `kelethinBomb` records' `script` `return8821` returns
  `!sfe_step3complete`. **Executed:** it returns 1 before stage 3 and 0 after.
  A dropper whose script returns 0 skips its drop (`docs/monsters-2.md`
  line 7989), so the bombs stop at stage 3. Strife's Catapults have
  `script` `return523c`, which always returns 1, so they fire
  (`docs/monsters-2.md` lines 7976–7982).
- *Fourth scout.* `setv70e6` calls `trigger('bridge3', 0)` and removes the
  stage quest.
- *Scouts.* `start` shows exactly one scout according to the three stage flags
  (ref 609–623). Each NPC's `exclamation` predicate (`returne210`, `return1e8e`,
  `returnadae`, `returnc3ef`) is 1 until that scout's talked flag is set. The
  dialog actions `setv176d`, `setv23a8`, `setv8921`, `setv70e6` and the
  predicates `if70a4`, `iff29`, `if3e90`, `if40b3` are named by **no** record.
  They are named in the bytes of `we_scout.dbin` … `we_scout_4.dbin` in the same
  lump (`DIALOG_ENTRIES`, ref lines 126–133; asserted at difftest 838–843).
  Which dialog node calls each is **Unknown**: dialog was not executed. Trigger
  `if9d85` starts the first scout's dialog once (`sfe_metscout1`).

The order is forced. Each later scout is hidden until the previous stage's post
action or cutscene shows them: `hideElf1` shows `we_scout_2`, and the show keys
of `step2complete` and `step3complete` show `we_scout_3` and `we_scout_4`
(section 6). **Executed** as one 469-frame run, difftest lines 636–720.

**Exits:** see section 7. `exitzone` requests `drunarm` (with `demoRunning` 0),
and `newWorld5d32` requests `blood1`.

## 3. drundar (evil story level)

**Objects:** 270 records (`docs/strife-drundar.md` lines 15–129). There are 85
hostiles: 39 GoblinSoldier, 23 GoblinArcher, 9 GoblinRecruit and 14 Ogre, one of
them named `ogreminiboss` with `miniboss=1`. The scripted pieces are 8
`uwswitch`, 4 `arenadoor` (all named `door`), one `UWStair` (`stairs`), 13
PushTriggers (8 with only a clock icon), 6 Triggers, one Portal and one
`Player1`.

**Scripted encounter (Executed, difftest lines 723–767):**

- `start` (ref 891–908) sets three values on `ogreminiboss` (which 4 = 3000,
  1 = 500, 5 = 1000; `docs/spec/script-builtins.md` line 659: which 4 is slot
  34, 1 and 5 are +0x3ac/+0x3c4), sets the intro flag, and restarts the pillar
  loops of switches already on, counting them into global 0.
- The two Triggers `callScri28d3` run `arenaMessage` once: help, quest,
  `drun_arenaMess`, and they queue `showSwitchCount`, which polls with a bust.
- Each `uwswitch` has `key` `returnXXXX` = `!pillarNon` and `action1`
  `switchcoXXXX`. The action raises global 0, sets `pillarNon` and starts
  `switchNeffect`, a particle loop that requeues itself each frame
  (`R.Model.PILLAR`; links in ref lines 82–104).
- At global 0 = 8, `showSwitchCount` calls `setSaveInhibit(1)` and queues
  `doorsdelay`. 102 frames later `doors` calls `setSaveInhibit(0)` and requests
  the `doors` cutscene, which triggers the four doors and the stairs (section
  6). It then sets `drun_sawdoors`. The persistent-flag predicate at 0xa78 was
  executed in `3216e7b` (`docs/strife-drundar.md` lines 214–237).
- **Executed quirk:** `switchNeffect` skips its own requeue on a paused frame
  (ref 931–943). The `doors` cutscene therefore stops all eight particle loops
  until the next `start` (the test pauses five frames and compares).
- **Executed:** the exit key `return56e0` is `global0 == 8`. Before the eighth
  switch it is 0; after it, 1.
- The Ogres and Goblins have no script link. Their fight is **not** part of any
  script condition here.

## 4. drunarm (good arena)

**Objects (Observed counts; Executed factory, difftest lines 790–822,
`COUNTS`/`FACTORY` ref lines 14–49):** 302 records, 230 of which make an
object.

| Class | Count | Pool / constructor | Notes |
|---|---:|---|---|
| `GladiatorBare` | 82 | 0x480 / 0x2bafb4 (Warrior, kind 1) | no properties at all (all 82 asserted), no script link |
| `RalosZek` | 2 | 0x480 / 0x2c1f94 (Zek) | `rallos` (drop `shardofwar`, no `wait`), `rallos2` (`wait`, no drop); asserted by name |
| `Catapult` | 4 | 0xfc / 0x24d440 | `script` `return25eb` |
| `PowderKeg` | 25 | 0x84 / 0x290c24 | |
| `weaprack` | 24 | 0x148 / 0x23d93c (AutoContainer) | |
| `orkbox` | 3 | 0xf8 / 0x23ad18 (AutoChest) | |
| `Torch` / `Blocker` | 46 / 32 | 0x8c / 0x2b1e80, 0x4c / 0x28f15c | |
| `Savepoint` | 3 | 0x118 / 0x28cb90 | |
| `Portal` | 1 | 0x164 / 0x27c694 (JumpGate) | keys `lump` and `script` (`if6896`) only, so no destination |
| `Trigger` / `PushTrigger` | 3 / 1 | 0x70 / 0x1ecdf4, 0x4c / 0x1ec900 | the third Trigger's `t` is the placeholder `<empty>`, which names no entry |
| `Crate` | 63 | none | no properties, so the factory returns 0 |

Also one `Player1`, one `TestLocation`, three character lights and five no-object
lights/metadata. The property facts in this table are asserted from the records
(`record_facts`, against `RECORD_FACTS`, `CLASS_KEYS`, `CLASS_VALUES` and `DROPS` in
the ref).

**How play reaches the Rallos trigger (Observed links; Executed run, difftest
lines 489–586):**

1. **Load.** The loader runs the fixed names `preStart` then `start`.
   **Observed:** `level_loadScriptAndObjects` loads `a0 = 0x53f000` = `preStart`
   before `jal 0x1ed694` at 0x217acc, and `0x53f020` = `start` at 0x217bac
   (`LOADER_NAMES`, asserted at difftest 1118–1126). Entry lookup is
   case-sensitive (`docs/spec/script-builtins.md` lines 267–285), and this
   level's entry is spelled `prestart`. **Executed:** `script_runByName('preStart')`
   returns −1, so the zeroing body never runs at load. It is harmless here:
   **Executed**, every global in `CELLS` is 0 straight after `scr_load`.
2. **`start`** (ref 347–358) hides `rallos` until `war_triggeredonce`, hides
   him again once `war_foundShard`, always hides `rallos2`, queues
   `removeRallos` after `war_killedRallos`, stores `playerHasItem('shardofwar')`
   in global 0xc and queues `shardCheckLoop`. **Executed** for all eight flag
   states.
3. **Gauntlet. Observed (asserted):** the 82 `GladiatorBare` records have no
   properties, so no `wait` or `hide`, and **Executed:** the script hides only
   `rallos` and `rallos2`. **Inferred:** the gladiators are live from load (the
   Warrior constructor's default state was not executed). The four Catapults never fire, because
   `return25eb` returns 0 (**Executed**) and a Catapult fires only on a
   nonzero `script` (`docs/monsters-2.md` line 7981). Which gladiators a
   player must pass is geometry, and **Unknown**.
4. **The Rallos trigger** is the walk-in Trigger whose `t` is `callScric1d7`.
   It calls `trippedTrigger`. The first time: `setSaveInhibit(1)`,
   `showMonster('rallos')`, cutscene `rallosintro`, post action `setFlag`,
   queue `rallosHPcheck`, set `war_triggeredonce`. On re-entry it calls only
   `setFlag` (`setCFlag('rallos', 0, 1)`: MiniBoss bit and boss music,
   `docs/spec/script-builtins.md` line 661). Triggers fire on a change of
   inside/outside (lines 292–315).
5. **The fight.** `rallosHPcheck` polls `getHitPoints('rallos')` every frame,
   paused or not (ref 377–384). At 0 or below it zeroes global 0x10 and queues
   `endDelay`. **Executed:** with no shard pickup, `rallosruns` is requested
   277 frames after `endDelay` is queued (the test is `> 275`). `playRallosRuns`
   then shows `rallos2`, sets `war_killedRallos`, removes the Rallos quest and
   posts `removeRallos`. After that cutscene, `removeRallos` kills, hides and
   deletes `rallos` and `rallos2`. This agrees with `2ab82b2` lines 452–471.
6. **The drop. Executed** `Creature_onDeath` 0x10beb8 on `rallos`'s own
   properties, picked by record name (`deaths`, `DEATHS_BY_NAME`): with quiet 0
   it calls `loot_spawnNamedItem` 0x100ba0 with `shardofwar` and starts no
   script; with quiet 1 it drops nothing. The same on `rallos2` drops nothing.
   **Observed (asserted, `DROPS`):** `rallos` is the only `shardofwar` record in
   the four levels. **Observed:** Zek's death state calls slot 28 with quiet 0
   (`docs/spec/arena-monsters.md` lines 647–672, death paragraph), and slot 28 is
   `Creature_onDeath` 0x10beb8 (`docs/creatures.md` line 75). `killMonster` in
   `removeRallos` acts only on a creature that is not already dead
   (`docs/spec/script-builtins.md` line 667). **Inferred:** in a straight play
   the shard comes from the fight death. A reload can reach the same drop
   through `removeRallos` (section 10, not executed).
7. **The grant.** With the shard picked up, `shardCheckLoop` grants on its next
   25-count check (**Executed:** 16 frames after the pickup in this run), as
   audited in `2ab82b2` lines 404–451.

**New Executed interactions:**

- **The grant restarts the outro timer.** `shardCheckLoop`'s grant also stores
  0 into global 0x10 (ref line 426), and global 0x10 is `endDelay`'s counter.
  A shard picked up during the 277-frame outro delay therefore restarts it.
  In the main run `rallosruns` comes 303 frames after the kill and 277 after
  the grant; there `endDelay` runs before `shardCheckLoop` in the grant frame.
  In the no-shard control it comes 279 after the kill. **Executed** in the other
  order too (run `x`: `start` and the trigger before the first frame, so
  `shardCheckLoop` is ahead of `rallosHPcheck` in the queue; death and pickup in
  one step): `endDelay` already counts 1 in the grant frame, and `rallosruns`
  comes 276 frames after the grant (`outro_after_grant_same_step`). Both values
  are in `MILESTONES`.
- **The outro replaces `endmission`.** The grant posts `endmission`;
  `playRallosRuns` later posts `removeRallos`. One post-action slot exists, and
  a second call replaces the first (`docs/spec/script-builtins.md` lines
  248–266). **Executed:** if no post action runs in between, `removeRallos`
  replaces `endmission`, whose help notice and sound then never run. The grant
  itself has already happened. The second run (the shard count 2, with
  `endmission` run before the outro) shows the other order. Which callers run
  a post action between them in real play (`help_task`, dialog end, cutscene
  end) is **Unknown**.

**The portal (the good path's way out).** The Portal's `script` `if6896`
**Executed** returns 1 before the trigger, 0 after the trigger until the shard
is found, and 1 after. The second Trigger, `callScricb6b`, shows an info line
only while it is 0. A gate refuses its prompt while its `script` returns 0
(`t3/research-exits-walkin` `95760d9` `docs/exits-walkin.md` lines 113–126).
See section 8.

## 5. drunare (evil arena)

**Objects (Observed counts; Executed factory):** 39 records, 31 of which make
an object. They are four `UndeadKnight1`–`4` (0x478 / 0x271c70 Horsemen; each
named `knight`, `wait`, `deathscript`, `dropitem`), one `CazicAvatar`
(0x3e8 / 0x24a670; `avatar`, `wait`, `deathscript` `callScria381`), one
`RalosZek` (`rallos`, `wait`, no drop), four `arenadoor` (`exitdoor`, `safety`,
and two unnamed), 14 `uwflag` props, two Triggers, one PushTrigger and one
`Player1`. There is no save point, portal, torch or crate. This agrees with
`docs/issues/arena-desync.md` lines 122–150.

**How play reaches the avatar death (Observed links; Executed run, difftest
lines 589–633):**

1. **`start`** (ref 472–483) hides `Rallos`, `avatar` and every `knight`.
   Name lookup is case-insensitive (`docs/script.md` line 231), so `Rallos`
   finds `rallos`. It removes the quest that drundar's `arenaMessage` added (the
   same text key, compared by equality only), sets which 4 = 2000 on the avatar
   and the knights, and sets `safety` to state 1 once `killedAv` is set.
   **Executed** with `killedAv` 0 and 1.
2. **The arena Trigger** `callScri8654` runs `incoming`. The first time it
   requests cutscene `knights`, posts `nosave` and sets `sawknights`; `nosave`
   then calls `setSaveInhibit(1)` and `setCFlag('avatar', 0, 1)`. On re-entry
   it calls only `setFlag`. **Observed spawn:** the `knights` file binds the four
   placed knights (the box search finds exactly one candidate for each and the
   query has room for every counted object, section 6) and has one show key
   (type 8) per knight. A script-hidden creature is
   re-gridded for the actor search and hidden again by a second walk, and
   `cut_end` clears flags 0x88000 and inert bit 1 on bound actors
   (`docs/issues/arena-desync.md` lines 183–206). But `start`'s `hideMonster`
   also set object flag 0x8000 and creature bit 3 of +0x231
   (`docs/spec/script-builtins.md` line 669). A type-8 key only puts the object
   back on the grid (`docs/engine.md` line 520), and nothing cited here clears
   that flag or bit. **Unknown:** whether the knights are active after
   `knights`. **Inferred** only from the fight needing them: they are. This is
   the level's only knight wave.
3. **Knight deaths. Executed** `Creature_onDeath` on each knight's properties
   starts its `setvXXXX` entry, with the selected object set to that knight,
   then drops `rejuvpotion` (knights 1 and 3) or `healingpotion` (2 and 4);
   quiet 1 skips the drop. Each entry sets `knightN` and calls
   `knightDefeatedPause`. **Executed** in the order 3, 1, 4, 2: only the fourth
   death queues `knightDefeatedDelay`, and `cazic` is requested 303 frames after
   that death (302 counted calls; `> 300`). This agrees with `2ab82b2` lines
   352–367, which covers single-entry states.
4. **The avatar is shown by `cazic`. Observed (asserted, `SLOT3_KEYS`):**
   `cazic` binds `exitdoor` and gives it one type-3 key (virtual slot 3 with 1,
   key time 1.91) and then one type-4 key (slot 3 with 0, key time 10.01); the
   order and both times are asserted (`SLOT3_ORDER`, key times to 0.01). It binds
   the `avatar` with one show key and creates a `Player` stand-in. `arenadoor`
   is a `HackDoor`, an AutoProp, whose slot 3 moves to the next state when
   `triggerable` and `states` are set (`docs/monsters-2.md` lines 143, 7814–7819,
   8113); whether it reads the argument was not traced. **Unknown:** the door's
   state after `cazic`. The hide flag caveat of step 2 applies to the avatar
   too.
5. **Avatar death. Executed:** `Creature_onDeath` on the avatar's properties
   starts `callScria381` and drops nothing. From there, `bossDefeatedPause`, the
   doubled `bossDefeatedDelay`, `endmission` (`bossdefeated`, `reapEnemies`,
   `killedAv`) and the post action `levelChange` (grant, `hub2`) follow. They
   are **Executed** here 878 frames after the death script, as audited in
   `2ab82b2` lines 319–403. Frame numbers here count every `script_runDeferred`
   call after the step: frame 1 is the call that only promotes a name queued by
   a direct run, which `2ab82b2` counts as call 0. So frame 878 is its "call
   877", and `cazic`'s frame 303 is its 302 counted calls plus that call. **Observed:** `bossdefeated` binds an unnamed
   `arenadoor` and `rallos` and shows `rallos`. Rallos never fights here.
6. **Executed:** the PushTrigger key `return9d74` returns `killedAv`, 0 before
   and 1 after.

## 6. Cutscenes requested

**Observed** in each `<name>.cut` of the level lump. Header word +0 is flags,
+8 the key count, +0x10 the actor count. Actor records are 0x2c bytes: class
name at +8, position at +0x1c, a create byte at +0x2b (`docs/engine.md`
lines 444–450). Keys are 20 bytes. Object key types 3 and 4 call the object's
virtual slot 3 (trigger) with 1 and 0; type 8 puts it back on the grid (lines
511–525).

**Actor binding. Observed** in `cut_setup` 0x19a6cc (0x19b098–0x19b324): for a
bound actor, `world_collectObjectsInBox` 0x14a928 (call at 0x19b148) is called
with the actor position ±240 on x and y and ±100000 on z, capacity 0x40.
**Asserted from the ELF** (`bind_constants`, decoded from the instruction
fields, not copied): the `lui` at 0x19b098 (240.0, x and y), the `lui`/`ori` at
0x19b0a4/0x19b0a8 (100000.0, z), the capacity in a3 at 0x19b0f8 (0x40), the
`lui` at 0x19b0fc (600.0), the call target, and the type-name call: the
virtual table loaded from +0x48 at 0x19b1b8, the word at table + 4 loaded at
0x19b1bc and called at 0x19b1c0. A candidate's factory
class string (+0x34) or its C++ type name (leading digits skipped) must equal
the actor's class; objects already bound (flag 0x80000) are skipped; the
nearest in 2-D below 600 units is taken, and once a class-string match is held,
type-only matches are skipped. (`docs/engine.md` line 447 says "within 240
units"; it is this box.) **Executed/asserted** (`type_names`, `bind_actor`):
the type name of every constructor the four levels select was read by calling
the original type-info function at table + 4. The 26 names are asserted by
value (`TYPE_NAMES`) and printed in the log; among them, the NPC constructor
0x29df04 gives `NPC` and `Player1_ctor` 0x158928 gives `Player1` (the
executed `7Player1` of `docs/spec/object-system.md` line 769), and none is
`GameObject`. Asserted: the only type name that equals a cutscene actor class
is `NPC`, and every record of type `NPC` is of class `NPC`. For every bound
actor below exactly one matching record lies in the box, its 2-D distance is
below 600, and no other matching record lies in the box grown by 240 units on x
and y, so the result holds for any object radius below 240. **Capacity
(asserted):** the query keeps only the first 63 objects in walk order
(`docs/spec/object-system.md` lines 192–212). For each of the 25 bindings the
difftest counts every record that makes an object, of any class and bound or
not, whose centre cell lies in the cell range the query walks (an object
outside it is never returned, whatever its radius), plus four player slots
(`g_players[4]`, `docs/script.md` line 682) and the cutscene's created actors.
Every count is below 63 (the largest is 28), so the target is returned.
Records are taken at their placed positions; an object off the grid could only
remove a candidate. Not counted, and **Unknown**: objects spawned at run time
(drops, summoned creatures) and placed creatures that walked into the box; the
largest count leaves room for 35 of them. The
table is asserted against `CUTSCENES` (ref lines 142–164), the type-3/4 keys
against `SLOT3_KEYS` and, for `cazic` and `bossdefeated`, their order
against `SLOT3_ORDER` (in key order, times ascending).

| Level | Requested by (offset) | Cutscene | Flags | Keys | Actors: bound record (or created) | Shows |
|---|---|---|---:|---:|---|---|
| strife | `step1scene` 0xffc | `step1com` | 8 | 52 | NPC `we_scout`, NPC `we_scout_2` | `we_scout_2` |
| strife | `step2delay` 0x14b0 | `step2complete` | 0 | 37 | NPC `we_scout_2`, dbridge `bridge1`, NPC `we_scout_3` | `we_scout_3` |
| strife | `step3delay` 0x1900 | `step3complete` | 0 | 58 | NPC `we_scout_3`, NPC `we_scout_4`, dbridge `bridge2`, `bridge3` | `we_scout_4` |
| drundar | `doors` 0xacc | `doors` | 8 | 27 | 4 arenadoor `door`, UWStair `stairs` (one type-3 key each) | — |
| drunarm | `trippedTrigger` 0x31c | `rallosintro` | 8 | 31 | RalosZek `rallos`, created `Player`, unnamed Portal | — |
| drunarm | `playRallosRuns` 0x630 | `rallosruns` | 8 | 20 | RalosZek `rallos2` | — |
| drunare | `incoming` 0x244 | `knights` | 8 | 57 | UndeadKnight4..1 (`knight`) | all four |
| drunare | `knightDefeated` 0x660 | `cazic` | 8 | 43 | arenadoor `exitdoor` (type 3, then type 4), CazicAvatar `avatar`, created `Player` | `avatar` |
| drunare | `endmission` 0x9fc | `bossdefeated` | 8 | 64 | unnamed arenadoor (type 3, then type 4), RalosZek `rallos` | `rallos` |

Every cutscene name is requested from exactly one site. Besides the ten
`autosave*.cut` files (nine in drunare), only `drunarm`'s `rallosrun.cut`
(one actor, class `UndeadKnight`, asserted in `UNREQUESTED_ACTORS`) is in a
lump and requested by no script. drunarm has no `UndeadKnight` record. **Executed**
order: each request is made by the entry shown, at the frame given in
sections 2–5. Playback, keys and camera are **Unknown** here: `cutScene` is a
stub, and the post action runs when the test ends the synthetic pause.

## 7. Every exit and travel entry

**Executed** in the main runs. Each newWorld site writes the pending level
0x41b6d0 through the original `newWorld` (`NEWWORLD`, ref lines 227–237; all
nine sites in the four scripts are asserted at difftest lines 1103–1115).

| From | Object (link) | Gate | Entry → request |
|---|---|---|---|
| strife | PushTrigger (`action` `callScri5a82`) | none | `exitzone` → `drunarm` (`demoRunning` 0) |
| strife | PushTrigger and walk-in Trigger (`newWorld5d32`) | none | → `blood1` |
| strife | Portal (key `lump` only: no `script`, no destination) | gate prompt rules | travel menu |
| drundar | 4 PushTriggers (`key` `return56e0`, `action` `callScri5a82`) | key = all 8 switches | `exitzone` → `drunare` |
| drundar | 4 walk-in Triggers (`callScri5a82`) | none in script | `exitzone` → `drunare` |
| drundar | PushTrigger (`newWorld5d32`) | none | → `blood1` |
| drundar | Portal (key `lump` only) | gate prompt rules | travel menu |
| drunarm | PushTrigger (`newWorld1c57`) | none | → `strife` |
| drunarm | Portal (`script` `if6896`) | 0 from trigger to shard | travel menu |
| drunare | PushTrigger (`key` `return9d74`, `action` `newWorldbcf6`) | `killedAv` | → `drundar` |
| drunare | walk-in Trigger (`newWorldbcf6`) | none in script | → `drundar` |
| drunare | post action `levelChange` (after `bossdefeated`) | — | grant, → `hub2` |

The `demoRunning` branches of both `exitzone`s (count to 150, then
`grantMission(1)` and `hub`, still requeueing) are **Observed** and modelled
(ref lines 749–762) but not executed. The original `demoRunning` returns 0 in
this state. **Inferred:** the four drundar walk-in exits and the drunare
walk-in exit sit behind doors the scripts open. Their geometry is **Unknown**.

**Arrival markers. Executed** `Player1_ctor` 0x158928 over each level's markers
in record order (difftest lines 1129–1162; `MARKERS`, ref lines 1007–1014).
Coming from `drunarm`, strife's `from=drunarm` marker takes the spawn slots
(rank 2, eight spawn searches). Coming from `blood1`, the plain marker takes
them (rank 1). drundar, drunarm and drunare each have one plain marker, and it
takes the spawn whatever the previous level. The rank rules are
`docs/spec/object-system.md` lines 587–613.

## 8. The good path's return to a hub

Nothing in strife or drunarm requests a hub outside the demo branch
(**Executed**, section 7). The way back is a JumpGate travel menu:

1. **Executed:** `if6896` enables the drunarm Portal before the Rallos trigger
   and after the shard grant.
2. **Observed** (`t3/research-exits-walkin` `95760d9` `docs/exits-walkin.md`
   lines 113–140): the first valid prompt adds the current level with
   `jumpgate_addCurrentLevel` 0x27db60. A single destination shows the
   "virgin" prompt; with more, every other living player must be within 96
   units. `JumpGate_interact` opens the menu, and `jumpgate_menuRun` 0x27dd74
   refuses the current level, counts 180 travel ticks, then copies the chosen
   slot to 0x41b6d0 with orientation 0xff.
3. **Observed/Executed** (`t3/research-exits-r3` `e86f3de`
   `docs/exits-r3-gate-lifecycle.md` lines 15–49, `docs/exits-r4-travel.md`
   lines 66–73): an act change calls `jumpgate_resetDestinations` 0x27db00,
   which leaves one slot, the hub identity. A discovery that appends a level
   removes the first other hub-like entry whose name differs from the
   current hub.
4. **Executed here** (difftest lines 1254–1259): `game_getHubName` 0x1ec300 is
   `hub` for evil 0, decision 1, with mission 1 available or complete, and
   `hub2` for evil 1, decision 1, complete. `blood1` calls `setEvil(0)`,
   `setEvil(1)` and `setMadeDecision` (`2ab82b2` `docs/quests.md` line 112);
   `setEvil(0)` does nothing, because the built-in acts only when its argument
   is nonzero (`docs/spec/script-builtins.md` line 478). The four cases run
   here all have the decision bit set. The full rule (`hub2` only for evil,
   decision and complete together) is `2ab82b2` `docs/quests.md` lines
   279–283.

**Inferred:** the good path returns by the drunarm Portal (or strife's, after
the `newWorld1c57` walk back) to the `hub` slot of the travel menu. Strife,
drunarm and both hubs are act 0 (`t3/research-story-route-r3` `019a155`
`docs/story-route.md` lines 271–273), so arriving keeps bags and quest
variables. The pad
selection, the menu states 0–4 and the hub load are **Unknown**.

## 9. Client-implementable list

1. **Load order:** run `preStart`, then construct objects (each creature's
   `initscript` runs then), then `start`. Look entries up case-sensitively, so
   drunarm's `prestart` never runs, and reload the script image per level
   (its globals start at 0).
2. **Deferred queue:** two halves. A name queued from a direct run (trigger,
   death, dialog, load) first runs two frames later; one queued from a
   deferred run runs the next frame. Run every front name once per frame, then
   swap. `getScaledTime(n) = n − 1` for these counts, so `> 100` fires on the
   102nd call, `> 275` on the 277th and `> 300` on the 302nd.
3. **One post-action slot.** A second `postAction` replaces the first. Run it
   at cutscene end, dialog end, the help task and level-load end.
4. **strife:** implement the four scouts (one shown at a time from the stage
   flags, `exclamation` predicates), the three counters on globals 0x144,
   0x148 and 0x14c with init/death scripts, `sfe_step3counter` persistence,
   `trigger` on `bridge1`–`3`, the three cutscenes and post actions, the bomb
   droppers' `!step3complete` predicate and always-firing catapults, and the
   exits from section 7. Bind the dialog actions from the `.dbin` files.
5. **drundar:** `ogreminiboss` values, arena message and quest, eight
   switches (key `!pillarN`, action counts to 8, particle loop that stops on a
   paused frame), save inhibit, the `doors` cutscene 102 frames after the eighth
   switch, door/stair states on reload, the exit key `count == 8`, and the
   exits.
6. **drunarm:** 82 property-less gladiators (**Inferred** live from load) and
   inert catapults. Rallos is hidden
   until the walk-in trigger, then shown, with `rallosintro`, MiniBoss and boss
   music. Poll his hit points every frame; on death drop `shardofwar` and start
   the 277-count outro on global 0x10. Restart that count when the shard grant
   runs (276 or 277 frames after the grant, by queue order), then play `rallosruns` with `rallos2`. Let the outro's `removeRallos`
   replace a pending `endmission`. The portal gate is `if6896`; walking back
   goes to strife's `from=drunarm` marker.
7. **drunare:** hide the bosses at load. The arena trigger plays `knights`,
   which shows the knights (**Inferred**; whether the hide flag is cleared is
   Unknown), then `nosave`. Each knight death runs its entry and drops its
   potion. 302 counted calls after the fourth death, play `cazic`, which
   triggers `exitdoor` (slot 3 with 1, then with 0; the resulting door state is
   Unknown) and shows the avatar (same caveat). The avatar death leads to the
   doubled counter, `bossdefeated`, `reapEnemies`, and then `levelChange` →
   grant and `hub2` (as `2ab82b2` items 2 and 5). Lock the exit PushTrigger on
   `killedAv`.
8. **Good return:** a travel menu, with the hub slot from `game_getHubName`
   (`hub` on this path) and the current level refused.

## 10. Unknown

- Real cutscene playback, length and keys. Real combat: hit points, damage,
  and gladiator, goblin and ogre AI. Rallos's real hit-point float. Real
  `trigger`/`autoPropSetState` effects on bridges, doors and stairs.
- Which dialog node calls each strife dialog action. Dialog was not executed.
- The geometry: which Triggers and PushTriggers a player can reach before
  which door or bridge opens.
- When `help_task` or another caller runs `endmission` relative to the Rallos
  outro in real play.
- The demo branches (not executed), the travel-menu input and states 0–4, and
  the hub load after travel.
- Save/reload of creature state mid-stage. The reload runs here plant only
  quest variables.
- A second path to the `shardofwar` drop: a reload after the outro and before
  the pickup. `start` queues `removeRallos` once `war_killedRallos` is set, and
  `rallos` is then not hidden (`war_triggeredonce` 1, `war_foundShard` 0; ref
  lines 347–358). `removeRallos` calls `killMonster('rallos')`, which on a live
  creature calls slot 27 with 0x14 (`docs/spec/script-builtins.md` line 667),
  and `Zek_setState` 0x14 reaches slot 28 with quiet 0
  (`docs/spec/arena-monsters.md` lines 666–671, `tools/ref_arena_monsters.py`
  `Zek_setState`), the same drop. Not executed (`killMonster` is stubbed);
  whether the reloaded `rallos` is live and in the grid then is Unknown.
- How many spawned objects (drops, summoned creatures) and moved creatures are
  in a cutscene actor's search box when the cutscene starts. The counted
  records, players and created actors leave room for at least 35 (section 6).
- Whether the object flag 0x8000 and creature bit 3 that `hideMonster` sets are
  cleared for the knights after `knights` and for the avatar after `cazic`, and
  the door states after `doors`, `cazic` and `bossdefeated`.
- `rallosrun.cut`, which no script requests. Whether anything else plays it is
  unknown.

## 11. Verification

On the Mac mini, single process, with `PYTHONDONTWRITEBYTECODE=1`.
`local/disc` is the private level directory (ignored):

```sh
python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_levels.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","20973"]; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission1_levels.py", run_name="__main__")'
python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_levels.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","7"]; sys.path.insert(0,"tools"); runpy.run_path("tools/difftest_mission1_levels.py", run_name="__main__")'
python3 -c 'import dis,runpy,sys; sys.argv=["unittest","discover","-s","tools","-p","test_*.py"]; runpy.run_module("unittest", run_name="__main__")'
```

Each seed prints PASS with these counts: 261 arena objects made, 109 record
links, 9 cutscenes (25 actor bindings by the `cut_setup` box search, 26 type
names), 16 record facts, 9 travel sites, 2 loader names, 6 marker cases, 20
death cases, 4 hub cases, 5 controls rejected, and 3,575 compared steps (2,409
frames in the four main runs), plus the milestones in `MILESTONES`. Two more
lines print the 26 type names and the actor-search constants read from the
ELF, with the largest counted search (28 objects, below 63). The retained logs
are named in `work/cursor-report.md`. The existing
`tools/difftest_strife_drundar.py` was rerun unchanged on both seeds.
