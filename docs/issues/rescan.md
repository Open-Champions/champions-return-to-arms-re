# Re-run of the per-machine-state scan with whole function bodies

`tools/localstate.py` follows direct calls from every virtual function of a class and
reports reads of state that is not part of the lockstep simulation. Until now it took
function boundaries from `tools/ps2elf.py`, which end a function at its first switch-case
label (FINDINGS D32). It now takes whole bodies from `ghidra_funcs.tsv`. This document is
the re-run over every class and the triage of what it reports.

Everything was read from the executable (SLUS_209.73, v2.00); **nothing was run, and the
patches at the end are untested.** (Still so. What the project has since run on a live
game, in the Play! emulator, is in `FINDINGS.md`, "Run on the live game" (rows V1–V8) and `docs/issues/live-rig.md`;
none of it re-checks a finding here, and no test patch has been run there.) Statements are **Observed** (read at the address given)
unless marked **Inferred** or **Unknown**. New names are in `symbols/rescan.tsv`.
`FINDINGS.md` and `patches/` were not edited.

## 1. Result in short

- The fixed scan was run over all 381 classes of `vtables.txt` that derive from GameObject
  (232), Skill (93) or Spell (56). It reports 108 distinct (address, kind) lines in 94
  functions; with every address kept (the tool prints one per function and kind) that is
  246 sites, 213 of them reached from a slot that runs inside the simulation.
- **The fix adds no function to the list.** Compared with the old boundaries it adds 70
  sites, all inside three shared presentation functions whose switch cases had been cut off
  (`player_voice` 40, `fx_spawn` 25, `stream_queueRandomByPrefix` 1) plus four false
  "hardware timer" lines, and it removes 15 sites that the old boundaries reported wrongly
  (they ran past the end of a short function into the next one). Per class the fixed scan
  reaches more of the *same* shared code (section 5). No first-round "nothing found for
  this class" turns into a finding because of the fix.
- **Every "hardware timer" line is a false positive** (44 sites at the tool's depth).
- For the Drundar arena classes the scan reports nothing outside shared base code. The two
  pieces the arena document left unread — the weapon holder's per-frame update and
  `fx_modelStatusEffects` — were read here: presentation only (section 6).
- Reading the sites no document covers gave four results worth a ledger row. They come
  from sites that both versions of the tool report and nobody had read, not from the fix:

| # | What | Verdict |
|---|---|---|
| R1 | The skeleton pose the simulation reads (`anim_getJointMatrix`) is cached, and the cache is filled by drawing and emptied by a least-recently-drawn rule keyed on the render frame counter. Several animation calls change the tracks without emptying it | mechanism Observed; a route to shared state **not found**, not excluded |
| R2 | `SmokeGen_run` deals damage (with shared-seed draws) only when `isNearView(1000)` holds | shared-state effect; same family as D6 / D29 |
| R3 | `WaveMaker_run` knocks creatures back, and draws its own generator, only when `isNearView(503)` holds | shared-state effect; same family |
| R4 | A metal crate (`PushPhysicsProp`) keeps a starting rotation taken from the cosmetic seed, and its physics moves it according to that rotation | equal on every machine only because crates are created during level load, when the two seeds are equal (Inferred) |

## 2. How the scan was run

1. **Class list.** The base of each class was taken from the type-info getters (the table a
   previous pass left in its scratch directory, 406 rows; three pointer-type rows ignored)
   and checked against the table lengths in `vtables.txt`: every GameObject-rooted table
   has 16, 17, 19, 29 or 39 entries, every Skill table 15, every Spell table 4. All 381
   class names were found by the tool; none has two tables.
2. **The tool**, three runs (the tool takes many names at once):

   ```
   python3 -I -B tools/localstate.py SLUS_209.73 <232 GameObject classes>
   python3 -I -B tools/localstate.py SLUS_209.73 <93 Skill classes>
   python3 -I -B tools/localstate.py SLUS_209.73 <56 Spell classes>
   ```

   4,501 report lines. Raw output was kept outside the workspace.
3. **Collapsing.** The tool prints, per class, the first slot that reaches a function and
   the first address of each kind inside it. To get "every site, every class, every slot"
   a scratch copy of the same walk (same kind tables, same stop list, same Ghidra bodies)
   kept every address and every (class, slot) pair. At the tool's depth of 4 calls it gives
   246 sites in 94 functions; with no depth limit 252 sites in 97 functions (the three
   extra functions are Sony library code, section 3). Tables below use the unlimited walk,
   which visits 3,110 functions.
4. **Checking each data line.** For every site flagged through an address constant the
   last writer of the base register was looked up; 45 sites turned out to be stale register
   tracking (section 3).
5. **Old against new.** The same walk was repeated with the old boundaries to see exactly
   what the fix changed (section 5).
6. **Supplementary walks**, to measure what the tool leaves out (section 9): the four
   weapon-holder classes, the 191 script built-ins, code no Ghidra body covers, and a list
   of further per-machine globals and calls.

Slot notation below: `G4×72` = slot 4 of 72 GameObject-rooted classes, `K` = Skill slot,
`P` = Spell slot. Slots that run in the simulation: G 1–4, 6–12, 14, 17, 18, 27, 28, 32;
K 1, 2; P 1, 2. Draw side: G 5, P 3 (G 13, the interact prompt, runs from both).

## 3. Lines that are not what they say

| Label printed | What it is | Sites |
|---|---|---|
| hardware timer | The tool treats any use of a register that once held 0x10000000 as a read of timer T0. In all 44 sites at depth 4 the register had been overwritten before the flagged instruction. The constant itself is a flag bit (`damage_apply`: "fire damage without burn"; `Player_run` and `fx_modelStatusEffects`: bit 0x10000000 of the word 0x44fe08) or part of a display-list tag or mask in drawing and lighting code | 0x148f48, 0x149528, 0x17580c, 0x17582c, 15 in `model_drawShadow`, 10 in `model_draw`, 0x178854, 0x1789a8, 0x17b710, 0x17ba78, 0x17bc68, 0x17bc90, 0x1ab1b0, 0x1ea098–0x1ea274 (6), 0x1f70c8, 0x1f7390 |
| hardware timer (unlimited depth only) | Real hardware registers, flagged by accident: DMA status words 0x1000e010 / 0x1000c000 in 0x355608, timer 2 count and mode 0x10001000 / 0x10001010 in 0x35cc48 and 0x35d140. All three sit under `res_find` → `lump_load` → `lump_pollAsync` → `DelayThread`: the wait for a lump that is loaded on demand. They time a blocking disc read; nothing is returned to the caller. Reached from almost every class (first at 7 calls deep, e.g. `Creature_processDamage` → `res_find`) | 0x35574c, 0x35576c, 0x35cc7c, 0x35cd50, 0x35d14c, 0x35d164 |
| render frame counter at 0x24122c | stale register in `AutoEmitter_draw`; the real read is 0x241204 | 1 |
| audio busy | the function is `cd_isBusy` (0x172be8): disc, not audio | 0x1a2e68, 0x1bfc3c |
| particle seed | `g_cosmeticSeed` 0x404460 | — |

The true T0 reads of the pathfinder (0x184324, 0x184df0, FINDINGS D5) are not reached from
any class slot: `path_service` is called only by `net_frameLoop`, `cut_advance` and
`task_plotroute`. The old boundaries reported them for `Savepoint` and `SpellResurrect` by mistake (section 5).

## 4. Every simulation-side site

Verdicts: **shared** = what is read can change shared state; **presentation** = particles,
sound, light, camera, menus, HUD only; **offline** = the read is not executed in a net
game; **dead** = no reader. "D6 family" means the test is `isNearView` or
`obj_updateActive`: in a net game both use the players' positions, except while a cutscene
is active, when they use the camera focus (FINDINGS D6, D7, D24). One addition to that
rule, so far only in a symbol note (`symbols/arena.tsv`): while a dialog is open `gameSetObjectVis` installs a single
activity centre, the object the dialog is with (0x1e4d48 → `dialog_objIfOpen` 0x231050;
`g_dialogFocusObj` 0x4fdcc0). Dialog open and close are game messages 0 and 3, and the
object is set in the message-0 handler (0x22f1b0), so this is lockstep; it applies to
`obj_updateActive` only, `isNearView` keeps using the players.

### 4.1 Activity and view tests (D6 family)

| Function | Site | Reached by | What the test guards | Verdict | Covered by |
|---|---|---|---|---|---|
| `Creature_updateActive` 0x10c0f0 | 0x10c168 | G4×72 | whether the creature's AI runs; the scavenger's shared draw on a corpse turning active | shared | creatures C5, objects O4, D6 |
| `Creature_run` 0x112948 | 0x112c3c | G4×72 | teleport of a stuck path follower when not near view | shared | creatures C4 |
| `AutoProp_run` 0x23cb54 | 0x23cc0c | G4×12 | animation, end scripts, piston damage | shared | D29, monsters-2 M3 |
| `Catapult_run` 0x24d9c0 | 0x24d9e4 | G4 Catapult | script call, bomb creation | shared | D29, M3 |
| `LightningRod_run` 0x295954 | 0x29597c | G4 LightningRod | timer, own draws, bolt creation | shared | D29, M3 |
| `FireBomb_run` 0x261f48 | 0x261fd0 | G4 FireBomb | shared draws, bomblet creation | shared | D29, M2 |
| `StaticFire_run` 0x2c595c | 0x2c5b3c | G4 StaticFire | own draws, 12-frame damage tick with a shared draw per hit | shared | skills (b) 7 |
| **`SmokeGen_run` 0x31c898** | 0x31c8c0 | G4 SmokeGen | particle step and the damage tick | **shared — R2** | skills (b) 8 said Unknown |
| **`WaveMaker_run` 0x15f2b4** | 0x15f818, 0x15f914 | G4 WaveMaker | first: two own draws and a particle; second: knockback of creatures, more own draws | **shared — R3** | none |
| `MissileWeapon_run` 0x15153c | 0x1515a4 | G4 MissileWeapon | only for a missile stuck in a target (+0x128 set): which run list it is on, i.e. how often it re-reads the target's sample point for its own position. The delete test that follows does not depend on the result | presentation (plus the shared 60-frame list cursor, as for every row here) | arena-desync names the call only |
| `UserParamProp_run` 0x15741c | 0x157448 | G4 UserParamProp | run-list membership; the function only steps the prop's animation and ignores the result | presentation | none |
| `CosmeticPropAnim_run` 0x15831c | 0x158330 | G4 CosmeticPropAnim | same | presentation | none |
| `JumpGate_run` 0x27cb58 | 0x27cb88 | G4 JumpGate | run list; clears the drawn flag when inactive | presentation with the shipped gates | monsters 7.1, sync-breakers 5 |
| `Savepoint_run` 0x28cdd0 | 0x28ce08 | G4 Savepoint | run list only | presentation | monsters 7.6 |
| `HateBridge_run` 0x243414 | 0x243438 | G4 HateBridge | always-draw list membership | presentation | monsters-2 §6 |
| `TormentBridge_run` 0x243ea0 | 0x243ec8 | G4 TormentBridge | always-draw list membership | presentation | monsters-2 §6 |
| `FireBomblet_run` 0x262588 | 0x2625e8 | G4 FireBomblet | nothing: the result is discarded | presentation | monsters-2 §6 |
| `AutoEmitter_run` 0x241310, `SpiritAnchor_run` 0x2964a8, `PointSourceSound_run` 0x28f4ac | 0x241328, 0x2964f0, 0x28f4c8 | G4, one class each | particles, light, sound; the anchor's own generator | presentation | monsters-2 7.3 |

### 4.2 The always-camera test `isNearCameraFocus480` (0x1ebd90)

| Function | Site | Reached by | Callees behind the test | Verdict | Covered by |
|---|---|---|---|---|---|
| `fx_spawn` 0x1ef270 | 0x1ef2e0 | G4×132, G6×24, G27×4, K2 SkillSummonSkeleton, P2×16, others | particles and sounds; id 5, the only id that draws the shared seed and creates objects, is exempt from the test | presentation | gameplay §4, §8.3 |
| `fx_modelParticlesNearCamera_1f5210` | 0x1f5290 | G4×72 | sample points, sine table, `particle_spawn` | presentation | gameplay §8.14 (by text scan); callee list read here |
| `fx_modelParticlesNearCamera_1f61c0` | 0x1f6244 | G4×73, P2×3 | the same plus `beam_create` / `beam_update` | presentation; the beam table is what D28 is about | gameplay §8.14, D28 |
| `fx_impactPuffNearCamera` 0x1fc150 | 0x1fc194 (and camera position 0x1fc1bc) | G4×7: FireArrowProjectile, FireBomblet, FireBombletJr, GutChunk, LooseIceChunk, PhIce, PhProp | `particle_spawn` only | presentation | gameplay §8.14 |

All four are `void`; none allocates an object, touches `g_randSeed` or calls a virtual.

### 4.3 Cosmetic seed

| Function | Sites | Reached by | Where the value goes | Verdict | Covered by |
|---|---|---|---|---|---|
| `rigidbody_init` 0x1682f0 | 0x168350 | G4×78, G27×52, G28×76, G17×13, G2, G6, G8, G14 | rotation of a new rigid body, **stored in the object** | PhProp: overwritten (arena-desync); PushPhysicsProp: **R4** | engine P5 (open) |
| `anim_randomizeTopTime` 0x16d0b8 | 0x16d0d8 | G4×72 (through `Creature_spawnScavenger` → `Critter_ctor`), G8 NPC | track time, stored in the object | shared in the two cases of D30, otherwise presentation | sync-breakers 8, D27, D30 |
| `SkillMultiFire_cast` 0x2d9a90 | 0x2d9e08 | K2 SkillMultiFire | second damage figure of each projectile, **stored in the object**, only when the caster is not a player | shared if a non-player ever casts it; reachability Unknown | skills (b) 1 |
| `shop_openOrStock` 0x1c7af8 | 0x1c7ea0, 0x1c80c4, 0x1c8498 | G14×76 (`Creature_interact`) | chance of an extra stock item; the stock branch runs at level load only, the interact path opens the menu | covered: seeds equal at that point | sync-breakers 2 |
| `player_voice` 0x1b7ba8 | 40 sites 0x1b7d00–0x1b8ea4 | G4×119, G6×24, G11×4, G14×7, G27, K2×3, P2×16 | which voice sample; returns at once unless the slot is local | presentation | player.md |
| `stream_queueRandomByPrefix` 0x211190 | 0x211238 | as `player_voice` | which stream entry | presentation | audio-save A4 |
| `fx_spawn` | 25 sites 0x1f0158–0x1f2b88 | as above | particle placement | presentation | gameplay §4 |
| `fx_modelStatusEffects` 0x1f6ac8 | 14 sites | G4 Cyclops, Innoruuk, Player, VampireLord (and the weapon holders, section 6) | particle placement | presentation | read here |
| `fx_ringBurst` 0x1f3d00, `fx_disintegrateModel` 0x1f4340, `fx_emitFromModelVerts` 0x1eb1e8, `fx_iceShatterParticles` 0x1fb510, `fx_burst_1fbdf0`, the two `NearCamera` emitters, `fx_impactPuffNearCamera` | 3, 1, 3, 1, 2, 2 + 3, 5 | G4×14; G4×67; P2 Resurrect, Retribution; G3 MummyKing; G4 Player, P2×3; as above | particle placement; callee lists hold only `particle_spawn`, model sample points, matrix helpers, one sound | presentation | none individually |
| beam segment builder 0x192a40 | 0x192a4c | G4×78, P2×4 | beam jitter (also `libc_rand`) | presentation | engine "clean" list |
| `AddParticle` emitter 0x195400 | 3 | G18 AddParticle | particle placement | presentation | monsters-2 M9 |
| `damage_apply` 0x1e8230 | 0x1e88b8 | G4×119, G6×24, G11×4, G27, P2×16 | sparks of a blocked hit | presentation | gameplay §2.5 step 11 |
| `SkillRiposte_counterAttack` 0x2ddccc, `SkillSummonSkeleton_cast` 0x2e18a4, `SkillStrongStance_trigger` 0x308578 | 2, 5, 1 | as `damage_apply`; K2; G4 Player | particle placement | presentation | skills (b) 5, FINDINGS "ruled out" |
| `hud_addGoldFloater` 0x1dc268 | 0x1dc478 | G6 Gold, G14 chests | drift of a HUD gold floater (`g_goldFloaters`) | presentation | ui.md |
| `Camera_apply` 0x2035c8 | 0x203834 | G14×77, G4×3, P2 Resurrect | camera shake | presentation | gameplay §8.10 |

### 4.4 Camera position and focus

| Function | Site | Reached by | Use | Verdict | Covered by |
|---|---|---|---|---|---|
| `damage_apply` | 0x1e8324 | as above | dead music counter | dead | gameplay §8.1 |
| `Weather_run` 0x1d80b0 | 0x1d8124 | G4 Weather | rain and snow are placed around the camera. The number of own-generator draws per frame is fixed by two object fields (+0x184, +0x23c); the gust timer (+0x268), the wind globals 0x4f66a0 / 0x4f66a4 and bit 0x100 of 0x44fe08 follow the frame counter and the own generator, not the camera | presentation | none (ui.md: only skimmed) |
| `game_buildScreenEdgePlanes` 0x1e71b0 | 0x1e71d8 | G4 Player, P2 Bash, Cyclone, ShadowStep, ShieldBash | view planes for `Player_clampToScreen`; both callers skip it when `g_networkMode` is set (0x1b4f80–0x1b4f84, 0x311e84 / 0x311ea8) | offline | player.md, skills (b) 11 |
| `DragonGoldPile_run` 0x295d58 | 0x295da0 | G4 DragonGoldPile | sparkles, own generator | presentation | monsters 7.3 |
| `sound_panAtten` 0x213c50 | 0x213c70 | G4×8 (projectiles, PointSourceSound) through `sound_setVolume` | volume and pan | presentation | audio-save A3 |
| `camera_setView` 0x18a2b0, `Camera_updateFollow` 0x204938, `Camera_followCollide` 0x204fe0, `Camera_computeTarget` 0x206538, `Camera_updateOrbit` 0x206fd8, `Camera_pushState` 0x207210 | 0x18a2fc, 0x204ea0, 0x20519c, 0x206ae0, 0x207058, 0x207234 | G14×76–77 (shop branch of `Creature_interact`); G4 Savepoint and P2 SpellResurrect (through `player_respawn`) | the camera object itself | presentation | gameplay §5, §8.10 |
| `Camera_saveState` 0x203918 | 0x203920 | G4 Savepoint (`save_game` → `save_build`) | camera written into the save | presentation; save content differs per machine by design | audio-save A5 |

### 4.5 Render counters

| Function | Site | Reached by | Use | Verdict | Covered by |
|---|---|---|---|---|---|
| `game_isFrozen` 0x1ebdf8 | 0x1ebe34, 0x1ebe70 | G4×159 and nearly every other slot | both reads are behind the network-mode test at 0x1ebe00–0x1ebe1c; a net game returns `g_paused` | offline | D12, mainloop, dynamic-tests i3 |
| `script_runByName` 0x1ed694 | 0x1ed6f0 | G3×69, G4×98, G14×90, G28×76, G32×76, K2×4, others | when the named entry does **not** exist, `g_drawFrame + 20` is stored at 0x4f8694. No instruction anywhere reads that word (search with no distance limit; no data word holds the address) | dead | none — `g_scriptMissingStamp` |
| `anim_advance` 0x16d748 | 0x16d9d8 | G4×70, P2×8 | sound limiter | presentation | engine P10 |
| **`anim_buildPose` 0x16ed40** | 0x16ed9c | G4×127, G27×13, G6×24, G17×5, G11×4, G2×3, K2×6, P2×33 | chooses a pose buffer; see R1 for what else depends on it | **could not tell — R1** | engine P11 (values only) |
| `eqcache_lookupModel` 0x1a2d48 | 0x1a2dfc (and `cd_isBusy` 0x1a2e68) | G4 Player (`Player_weaponTrails`) | whether the weapon's model is loaded yet; the result only picks the model handed to `fx_modelStatusEffects` | presentation | none |
| `gfx_addSortedPacket` 0x16b7f0, `anim_emitPose` 0x16f880 | 0x16b870, 0x16b8b4, 0x16f8dc | G4 Cazic and Marr (`ui_drawRect` in the death effects), G4 IceChunk (its run function draws its own model), G4 Player (prompt box) | draw calls issued from run code | presentation | monsters-2 7.3 for the two bosses |
| `ShopDaemon_run` 0x1d1490 | 0x1d149c | G4 ShopDaemon | restock timer; the class is never constructed | dead | ui.md P10 |
| `shop_openOrStock` | 0x1c879c | G14×76 | menu timing | presentation | ui.md |
| `Camera_update` 0x203400, `mainloop_startWarmup` 0x322934, `mainloop_startFadeWait` 0x322954 | 0x203448, 0x32293c, 0x322948, 0x32295c | G4 JumpGate, Player, Savepoint; G14 JumpGate; P2 SpellResurrect | camera, fade and warm-up counters | presentation | gameplay §5, mainloop |

### 4.6 Local player slot, audio and disc status

| Function | Site | Reached by | Use | Verdict | Covered by |
|---|---|---|---|---|---|
| `net_sendGameMsg` 0x13db38 | 0x13db88 | G14×83, G4×3, K2×2, P2 | selects this machine's outgoing message ring | by design | netcode.md |
| `net_closeLocalMenus` 0x1eb000, `pauseMenu_close` 0x18df90, `inventory_close` 0x1c5100, `inventory_pollResources` 0x1bfbc8 (`cd_isBusy`) | 0x1eb02c, 0x18dfd8, 0x1c51f8, 0x1c5314, 0x1bfc3c | G4 JumpGate, Player, Savepoint; G14 JumpGate; P2 SpellResurrect | closes this machine's menus. The side effect that matters, the input lockout set to 60 on the machine that had a menu open, is D26 | presentation, except D26 | D26, script.md, ui.md |
| `game_sendCharacterToLobby` 0x1eb5c8 | 0x1eb668, 0x1eb6b8 | same slots (through `save_game`) | which record this machine hands to the lobby | presentation | sync-breakers 6a |
| `shop_openOrStock` | 0x1c8770 | G14×76 | opens the shop only for a local slot | presentation | creatures C10, ui P1 |
| `Savepoint_run` | 0x28d68c | G4 Savepoint | who sees a HUD line | presentation | monsters 7.6 |
| `Camera_followRotateInput` 0x205db0 | 0x205f68 | G4 Savepoint, P2 SpellResurrect | camera | presentation | gameplay §5 |
| `stream_activeFlags` 0x216388 | 0x21639c | everything that reaches `player_voice` (its only caller) | a voice cue is skipped while stream 1 is busy; the test sits after the local-slot return | presentation | player.md |

No other audio status or handle is used in a condition by code these walks reach: of the
406 call sites of `sound_playSample`, `sound_playOnObject` and `sound_playAtPos` in the
program, none branches on the returned handle within the next eight instructions (a
heuristic; a handle stored first and tested later would not show, and monsters-2 7.3 lists
the stored ones as only ever passed back to `sound_stop`).

### 4.7 Draw-only sites (not triaged)

Reached from draw slots only: `light_pickShadowLights`, `model_drawShadow`, 0x1786c8,
`Player_draw` (0x1a4820, 0x1a4c3c), `fx_drawModelGlowNearCamera`, 0x2248f4,
`AutoEmitter_draw`, the three LP draws (monsters-2 7.2: dead stores), `Catapult_draw`,
`NPC_draw`, `StaticFire_draw`, `SmokeGen_draw`.

## 5. What the fix changed, class by class

The same walk with the old boundaries gives 191 sites in the same 94 functions.

- **Added (70 sites):** 40 in `player_voice`, 25 in `fx_spawn`, 1 in
  `stream_queueRandomByPrefix` — cosmetic-seed draws inside switch cases — and 4 false timer
  lines (0x17ba78, 0x17bc68, 0x17bc90, 0x1ab1b0).
- **Removed (15 sites):** reports that existed only because the old boundaries ran on past a
  short function into its neighbour: the pathfinder's T0 reads (through
  `mainloop_startFadeWait`, which is followed in memory by `task_plotroute`), a water
  routine at 0x186e38 (after `water_disturb`), `decal_drawTask` (after `decal_add`), and the
  unattributed code after `pauseMenu_close`. So the old tool both under- and over-reported.
- **Per (class, slot), functions newly reached:** `rigidbody_init` from slot 27 of 52
  creature classes (a part or weapon dropped in a state change); `player_voice`,
  `stream_queueRandomByPrefix`, `stream_activeFlags`, `SkillRiposte_counterAttack` and
  `damage_apply` itself for classes whose hit call sits inside a switch case (DiseaseTrail,
  HammerOfWrath, MissileWeapon, PoisonBolt, RainOfFireSpell, Sparks, SpellWaveOfFlame,
  SpellWizardBeam and others); `fx_spawn` (+15), `fx_ringBurst` (+7), `anim_buildPose`
  (+11), `game_isFrozen` (+34), `script_runByName` (+3). All are rows of section 4.
- **No function is reported now that was not reported for some class before.**

## 6. The Drundar arena classes

| Class | Newly reached with the fix (slot) | No longer reported |
|---|---|---|
| Horsemen | `rigidbody_init` (27), `player_voice` (4) | `gfx_addSortedPacket` (4), 0x186e38, `decal_drawTask` |
| Cazic | `rigidbody_init` (27), `player_voice` (4, 11), `stream_queueRandomByPrefix` (11) | 0x186e38, `decal_drawTask` |
| Skelight | `anim_buildPose`, `fx_spawn`, `game_isFrozen` (27), `player_voice` (4) | the same three as Horsemen |
| UndeadKnight | `rigidbody_init`, `damage_apply` and what it reaches, `fx_spawn`, `game_isFrozen` (27), `player_voice` (4) | the same three |
| Zek | `rigidbody_init` (27), `player_voice`, `fx_ringBurst` (4) | the same three |
| FireStorm | `player_voice`, `stream_queueRandomByPrefix` (4) | — |
| FireStormFlare | — | `gfx_addSortedPacket`, `decal_drawTask` |
| DiseaseBolt | `player_voice`, `stream_queueRandomByPrefix` (6) | 0x186e38 |
| SpellTagarsInsects | `player_voice` (2) | — |
| SkillSummonSkeleton | `fx_spawn` (2) | — |

Every entry is shared base code with a verdict in section 4: the weapon dropped on a state
change goes through `PhProp_initPhysics`, which overwrites the cosmetic rotation
(arena-desync, corrections); `player_voice` returns unless the slot is local;
`fx_spawn` and `fx_ringBurst` are particles. No class-specific function of the arena set
contains a site except `SkillSummonSkeleton_cast` (particles, already ruled out).

**The two pieces arena-desync.md called its weakest link**, read here:

- *Weapon holder update.* `Weapon1_slot21` 0x11b2a8, `Weapon1_slot22` 0x11b3e8 and
  `Weapon2_update` 0x118058 (slots 21 / 22 of the tables 0x50cf40, 0x50ce70, 0x50cda0) do
  one thing: if the hand is in use, the owner is not hidden and `isNearView(480, owner
  position)` holds (0x11b328, 0x11b458, 0x1180dc), call `fx_modelStatusEffects`. The other
  22 slots were skimmed: on/off bits, the element damage descriptor at +0x50
  (`creature_buildElementDamage`), drop-as-prop (slot 11), draw (18–20), three-byte
  save and load (23, 24). None reads what slots 21 / 22 write.
- *`fx_modelStatusEffects`* 0x1f6ac8 (17 KB, `void`, 16 call sites in 11 functions). Its
  callees are `dialog_isOpen`, model attachment and sample-point helpers, matrix helpers,
  `fx_spawn` with id 0x11 (0x1f71c8), `particle_spawn` (14 sites), `glow_add`,
  `trail_create`, `beam_create`, `beam_update` and two trail/beam helpers. No allocation, no
  `g_randSeed`, no damage call, no virtual call. It reads the damage descriptor (to pick the
  element visuals), `g_simFrame`, the local option 0x44fdc0 and bit 0x100 of 0x44fe08 (set
  by `Weather_run`). It writes only the effect block the caller passes, about 0x40 bytes:
  the previous attachment matrix, a frame stamp, a beam handle and a trail handle (holder
  +0xc / +0x9c; for players the two blocks at record +0x4a88 and +0x4ac8, the first of
  which `Player_ctor` clears at 0x1a2464). No other reader was found among the holder's
  slots or by address for the record blocks. **Presentation only.** Its
  `beam_create` call is one of the two camera- or view-gated users of the beam table that
  D28 depends on.

So for the arena the re-run changes nothing in the ranking of arena-desync.md.

## 7. New findings

### R1. The pose the simulation reads can be one that drawing computed

`anim_buildPose` reads the render frame counter (0x16ed9c). `docs/engine.md` P11 says the
pose values do not depend on which buffer is used. That is true of one build. What P11 does
not say is that **whether a build happens at all** depends on drawing.

Facts (all Observed):

| Fact | Where |
|---|---|
| An animation state's first word is a pointer to its pose buffer, or 0 | every row below |
| `anim_getJointMatrix` — the function the skeleton queries go through (`model_getAttachPoint` 117 call sites, `model_getSamplePoint` 88, `model_getAttachMatrix` 9, `model_getAttachWorldMatrix` 5, `model_getAttachLocal` 3, `PhProp_ctor2` 14) — builds a pose **only when that pointer is 0** | 0x16f738–0x16f744 |
| `anim_advance` clears the pointer on every step | 0x16d7bc–0x16d7c8 |
| The draw path (`anim_emitPose`) builds a pose when the pointer is 0, leaves it attached, stamps the buffer with `g_drawFrame` and moves it to the recent end of a list | 0x16f8b4–0x16f8c4, 0x16f8e4 |
| `anim_buildPose` takes the first buffer, from the old end of the list, whose stamp is older than `g_drawFrame − 3`, and zeroes the pointer of the state that owned it. There are 100 buffers. If none qualifies, a draw caller gives up and a simulation caller uses one static buffer shared by everybody | 0x16ed8c–0x16ede4, 0x16ee88–0x16ee94; `anim_init` 0x16f9a8 |
| These calls change the tracks **without** clearing the pointer: `anim_push` (new track at full weight, time 0), `anim_pushWithWeights`, `anim_pushChained`, `anim_clear` (track count 0; 88 callers), `anim_syncToSimFrame` (every track time; 61 callers), `anim_randomizeTopTime`, `anim_dropNonPersistent`, `anim_stop` with a blend time, and `anim_start` / `anim_startBlendInOut` (those two add a track at weight 0, which changes nothing until the next step) | 0x170838, 0x1708c0, 0x170938, 0x1707b0, 0x1709f8, 0x16d0b8, 0x16cb50, 0x16d1a0, 0x16cfe0, 0x16ceb0 |
| Only seven functions touch the owner field of a pose buffer: `anim_advance`, `anim_buildPose`, `anim_emitPose`, `anim_jumpTopToEnd`, `anim_snapTopToEnd`, `anim_releaseCaches`, `AnimState_dtor` | search for the offset 0x610 in the animation range |

Consequence (**Inferred**). Simulation code that asks for a joint position gets either a
pose built now from the current tracks, or the pose left by the last build — which may be
the last *draw* of that object. The two differ exactly when the tracks were changed by one
of the calls in the sixth row since that build. Whether a pose is attached differs between
machines: an object in one player's view and not in another's; a machine that runs two
ticks between two pictures; the real local player, which its owner's machine never draws
(it draws the prediction copy) while every other machine does; and, once about 25 animated
objects are in view (a drawn object needs a new buffer after every step and each buffer
stays reserved for four pictures, against 100 buffers), which buffers the
least-recently-drawn rule hands out.

The shortest sequence that gives different results on two machines:

```
tick N     object's animation step            (pointer cleared)
           [machine B draws the object: pose attached; machine A does not]
tick N+1   before the object's next step:
             a full-weight change of its tracks (push, clear+push, sync)
             a skeleton query                  B: pose from before the change
                                               A: pose after the change
```

What was checked:

- Monster run functions step the animation before their state switch, so queries made in
  the switch follow a clear in the same tick and are the same everywhere. This rests on the
  common shape in `docs/monsters.md` 1.3 (observed there in the 14 run functions read by
  hand, found by script in 68–72 of the 73) and on the order arena-desync.md gives for
  Skelight and Zek; the run functions were not re-read for it here.
- The code that runs before the step is `Creature_processDamage` (hit effects, parts and
  weapons dropped at death), status-effect particles and the weapon holder update.
- A search for functions in which a full-weight change is followed, with no step between,
  by a skeleton query (directly or one call down) finds ten: `Clockwork_setState`,
  `Mummy_setState`, `Orc_setState`, `Skeleton_setState`, `Skelight_setState`,
  `Soul_setState`, `WoodElfSoldier_setState`, `Skelight_ctor`, `Soul_ctor`, `Savepoint_run`.
  In each the query feeds particles or the start position of a debris prop (shed parts,
  shattered bones, a severed limb, dropped weapons). Debris props are non-solid and live in
  the grid that box queries do not see (`docs/objects.md`), so that is presentation, apart
  from pool occupancy (D21). **That sentence is wrong** (`docs/issues/pose-cache.md`
  section 5, FINDINGS D39): the start position of a debris prop is shared state. A `PhProp`
  that comes to rest builds a resting `Prop`, whose constructor draws `g_randSeed`
  (`PhProp_run` 0x155fcc, `Prop_ctorRes` 0x153c88, `Prop_ctorNamed` 0x153ac0), so the tick
  on which the piece settles moves the shared seed, and where it starts decides when it
  settles. What saves these ten functions is the order, not the kind of object: in the
  death cases that create debris the query comes before the track call, or after an
  `anim_start` only, which changes nothing until the next step (`pose-cache.md` section 6).
  The search goes by address order inside a function, so it
  over-reports: in `Skeleton_setState`, for one, the death case (weapon drop, shatter at
  0x2a7cd8, loot, delete) changes no track at all; the push at 0x2a7828 belongs to the
  rise state.
- The usual shape of a monster run function ends with one call to slot 27
  (`docs/monsters.md` 1.3). A query in the state switch followed by a state change in the
  same tick therefore does leave a pose from before the change attached into the next
  tick. What reads it there before the next step is the list two items up: effects, and
  debris dropped at death.
- `Player_run` uses only `anim_start` / `anim_startBlendInOut`. The cast position that
  `Player_castSkill` takes from attachment points 0 and 1 (0x1a43ac, 0x1a43ec) is read in
  the neutral state before that tick's step (the call at 0x1a7048), so it does come from a
  possibly draw-built pose, but no full-weight change was found between the draw and it.
  Two corrections from `docs/issues/pose-cache.md` (sections 2 and 4.1). First,
  `Player_move`, which `Player_run` calls, does change tracks another way: after stepping
  the animation it writes the weight and life of track 1 directly (0x1b498c, 0x1b499c) and
  a second block zeroes tracks 1–3 (0x1b4bb8–0x1b4bc4); those stores change the pose and
  do not detach it. Second, the cast position is read before the step, yes, but the pose
  attached at that moment is not a draw-built one: `Player_updateCast` queries the
  skeleton at the tail of `Player_run` on every tick of a living player, after the step
  and after every track change of the tick, so the pose the next tick's cast reads was
  built by the simulation at the end of the previous tick, on every machine.

So: **mechanism Observed; no sequence found in which a position that matters reads a stale
pose; not excluded.** Not done: sequences that cross functions (a state change in one
function, a query in its caller) other than the ones above; spell run functions, which run
from `Creature_run` before the owner's step and several of which query the owner's skeleton
(`SpellWizardBeam_run` 0x2f24ec among them); buffer exhaustion, where the least-recently-
drawn rule also decides staleness for poses built by the simulation itself.

- **Affects:** every animated object in every level; the more animated objects on screen,
  the more the cache state differs.
- **What would settle it:** on two machines, log each `anim_getJointMatrix` call made inside
  a tick with a non-zero pointer (the branch at 0x16f73c taken) and compare the buffer with
  a fresh build.
- **Patch:** none of one word was found. Making `anim_getJointMatrix` always rebuild (the
  branch at 0x16f73c, word 0x14400004) would leave buffers whose owner field still points at
  a state that no longer uses them; when such a buffer is reused the old owner's first word
  is zeroed, and if that object has been destroyed in the meantime the zero lands in
  whatever now occupies its pool block. A safe fix clears the state pointer and the buffer's
  owner at the end of `anim_emitPose` (the buffer stays protected by its stamp), which takes
  two stores in a code cave.

### R2. `SmokeGen_run` damages only "near view"

`SmokeGen_run` 0x31c898 (class `SmokeGen`, 0x490 bytes, created only by the object factory,
0x15d998):

1. `isNearView(1000, position)`; if false, return (0x31c8c0–0x31c8c8).
2. `SmokeGen_stepParticles` (own generator).
3. If the damage field +0x48c is above 0 and `g_simFrame & 7` is 0: box query of three
   times +0x478 around the object, and for every solid creature in it
   `damage_apply(dmg, dmg, creature, this, 100000, …, flags 0x100c040, a descriptor with a
   disease slot)` (0x31ca8c).

Each `damage_apply` call draws `g_randSeed` several times whether or not the damage lands
(`docs/gameplay.md` 2.5), so the test gates shared-seed use as well as hit points and the
disease effect. In a net game the test uses the players, except during a cutscene, when it
uses the camera focus: the same dependence as `StaticFire_run` (skills (b) 7) and the four
sites of D29. A frozen creature ignores the damage but the draws are still made
(**Inferred** from `docs/gameplay.md` 2.5 and the inert test in `Creature_takeDamage`).
`docs/skills.md` (b) 8 had this function as "not read further".

- **Affects:** levels that place a `SmokeGen` with damage. Which do is **Unknown** (the
  level files are not in this workspace; the object-list scan of sync-breakers.md would
  answer it).
- **Shared only as long as D7 holds.**

### R3. `WaveMaker_run` knocks creatures back only "near view"

`WaveMaker_run` 0x15f2b4 (class `WaveMaker`, created by the factory for a `Line` named
`wave`, 0x15d430) walks the wave front in steps. Per step:

1. With probability 1/9 or 1/4 from its own generator: `isNearView(503, point)`
   (0x15f818); if true, two more own draws and a particle.
2. If `g_waveDetail` (0x4f7130; 1 after every level clear, changed by the script command
   `setWaveDetail`) is non-zero and `isNearView(503, point)` (0x15f914):
   `WaveMaker_splashParticles`, `WaveMaker_foamParticle` and
   `WaveMaker_knockbackAndFoam` 0x15fef4. The last one, every 16th frame, takes the solid
   creatures in a 24-unit box that stand more than 12 below the crest and stores knockback
   speed 82 at +0x2e8 (0x1600d0) and a knockback angle at +0x2e0 built from the wave
   direction and two own-generator draws. All three helpers draw the own generator.
3. A field (+0x758) is cleared when no step passed test 2 and a step count is below +0x75c.

So a view test decides (a) knockback of monsters — players get none in a net game
(creatures C9), but the fields are among those `Player_clone` copies — and (b) how far the
wave's own generator has advanced, which in turn sets the next knockback angles. Same
family as R2. No earlier document reads this class (`docs/objects.md`, open questions).

- **Affects:** levels with a `wave` line; **Unknown** which. `ISLSM1` is the one script
  that calls `setWaveDetail` (with 0, which switches part 2 off there).

### R4. Metal crates start with a rotation from the cosmetic seed

`rigidbody_init` 0x1682f0 sets the body's rotation to a turn about the vertical axis by an
angle drawn from `g_cosmeticSeed` (0x168350). Its three callers:

| Caller | What happens to the rotation |
|---|---|
| `PhProp_initPhysics` 0x155110 | overwritten from the prop's matrix (arena-desync, corrections) |
| `PushPhysicsProp_loadState` 0x15dbd4 (slot 8) | overwritten: the thirteen body words at +0x60…+0x90, which include the rotation (+0x6c…+0x78), are copied from the level record after the call, then 0x167a58 is called on the body (**Inferred**: it rebuilds the derived matrix) |
| `PushPhysicsProp_ctorCrate` 0x15dddc (factory names `MetalCrateLrg`, `MetalCrateSml`) | **kept**: only the body position (+0x60…+0x68) is written afterwards |

`PushPhysicsProp_run` 0x15e244 rotates the eight box corners by that matrix (+0x94) to find
which ones touch the ground and applies impulses accordingly; the result is the object's
position. Movers collide with the crate and can stand on it (flag 0x10,
`docs/objects.md`), so its position is shared state.

It is the same on every machine because crates come only from the object factory, at level
load or from a level record, and `game_loadLevel` copies the shared seed into the cosmetic
seed before the objects are created (0x1e59c4; sync-breakers.md section 2 shows nothing
per-machine draws from it in between). No script creates one (`scripts/*.txt`). **Inferred**
safe; this answers `docs/engine.md` P5 for all three callers.

### Smaller results

- `script_runByName` stamps 0x4f8694 from the render counter when a script name is missing;
  nothing reads it (section 4.5).
- `Player_run` calls `memcard_isBusy` (0x1a54fc), which the tool has no entry for. It gates
  only the low-health rumble (`pad_rumble`, 0x1a5570, 0x1a5598).
- While a dialog is open, object activity is measured from the object the dialog is with
  and from nothing else (section 4, first paragraph).

## 8. Patches

All **untested**. Original words were read from the executable.

| ID | Address | Original | New | What it changes | What could go wrong | Who must apply it |
|---|---|---|---|---|---|---|
| T5 (from arena-desync.md, repeated because it is the one-word answer to R2 and R3 as well as D29) | 0x001e4dd4 | 8043fcd0 | 00001821 | `gameSetObjectVis` reads the cutscene flag as 0: in a net game `isNearView` and `obj_updateActive` always use player positions, never the camera | props near a cutscene camera but far from the players stop animating during cutscenes; smoke, waves, fires and bombs near the camera but far from the players stop acting during cutscenes | every player |
| RS1 (alternative to T5 for R2 only) | 0x0031c8c8 | 50400078 | 54000078 | the branch-likely after `isNearView` in `SmokeGen_run` becomes one that is never taken, so neither it nor its delay slot runs: the smoke's particles and damage tick run wherever the players are | smoke far from all players now damages monsters standing in it and draws the shared seed for them: a change of behaviour, equal on all machines only if all are patched. More particle work per frame. Also changes offline play | every player |

No patch is proposed for R1 (see there), R3 (two tests and the wave's generator; T5 covers
it) or R4 (nothing to fix).

## 9. Limits of the fixed tool

| # | Limit | Measured effect |
|---|---|---|
| 1 | Prints one address per function and kind, and only the first slot of a class that reaches a function | 108 printed lines stand for 246 sites; the slot shown for shared code is often 3 or 14 although slot 4 reaches it too |
| 2 | Depth 4 | unlimited depth adds only the six library sites of section 3 and 1.5 % more (class, slot) pairs (22,120 → 22,453) |
| 3 | The address tracker still comes from `ps2elf.py`: it is reset at every switch-case label and never forgets a register that is overwritten | the second half makes all 45 false positives of section 3. The first half could hide a read whose `lui` sits before a case label; a tracker with no distance limit and no reset, run over the 3,110 functions reachable from the class slots, finds no read of the tool's globals that the tool misses |
| 4 | Only exact addresses in its table match | reads of the camera's y and z words, the camera matrix and the focus z are missed unless the same function also touches the x word. A scratch walk with 21 more globals and 7 more calls (`net_isLocalSlot`, `net_objOrGhost`, `memcard_isBusy`, `memcard_getState`, `pauseMenu_isOpen`, `libc_rand`, `engine_frameStep`; the third seed 0x404468, the local alive list, the menu flags and lockout, the two options, the camera matrix and object pointer, the raw pads, the ghost pointer, three memory-card and drawing flags) finds 209 more sites in 98 functions; 85 of those functions are reached from simulation slots. Most are in documents already (creatures C3, C6, C7; player.md; skills (b); gameplay §8; engine P15; sync-breakers 4 and 7). Not triaged here: `Player_pickAttackAnim` 0x1bba88, `inventory_removeItem`, `inventory_equipItem`, `player_giveExp`, `PushTrigger_interact`, `light_recalcSun`, `model_evalFacingPoints` |
| 5 | Virtual calls are not followed | the weapon holder classes are not GameObjects and are reached only through the pointer at creature +0x50; run on `Weapon1`, `Weapon2`, `WeaponShield` the tool reports the view test and `fx_modelStatusEffects` (section 6). Spell and Skill code is covered because those classes are scanned as roots |
| 6 | Only class slots are roots | run tasks, game-message handlers and script built-ins are not scanned. The same walk from the 191 built-ins reaches 33 functions with sites, 8 of them not reached from any class: `script_runMedalSuccess`, `script_runMedalFail`, `mission_getMedal` (sync-breakers 3), `newWorld_netGate` (D20), `script_saveGame`, `memcard_requestConfigSave`, `memcard_requestEndGameSave`, `dialog_start` (audio-save) — all documented. Tasks and handlers were not walked |
| 7 | `ghidra_funcs.tsv` does not cover all code | 86 stretches of game code (4,706 non-zero words) belong to no body, among them the opcode handlers of `scr_interpret` (0x13eea8–0x140edc), part of `Critter_setState` (0x255d3c–0x255f5c), part of `MaleDarkElf_ctor`, most of `Player_drawEquipped`, and unattributed functions after `pauseMenu_close` (0x18e00c–0x18e330) and at 0x217cc8. Attaching each stretch to the function before it adds six sites: five inside the stretch after `pauseMenu_close` and one in `memcard_requestConfigSave`, which is called from that stretch. None belongs to a class function |
| 8 | A use of a returned sound handle, a pose, pool occupancy, or anything else that is per-machine without being a named global is invisible | R1 is of this kind; so are D21, D28 and audio-save A3 |
| 9 | Labels | "audio busy" is `cd_isBusy`; "particle seed" is `g_cosmeticSeed`; the docstring's "under-reports" should also say it over-reports through limit 3 |

## 10. Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| D32 (answer) | Re-run with whole bodies over all 381 GameObject, Skill and Spell classes: 246 sites in 94 functions; the fix adds no function, only 66 cosmetic-seed sites inside the switch cases of `player_voice`, `fx_spawn` and `stream_queueRandomByPrefix`, and removes 15 sites the old boundaries reported by running past the end of a short function. For the arena classes nothing outside shared base code is reported | Observed | docs/issues/rescan.md sections 1, 5, 6 |
| D33 | Every "hardware timer" line of `tools/localstate.py` is a false positive (the constant 0x10000000 used as a flag bit or display-list tag); the pathfinder's real T0 reads are not reachable from any class slot | Observed | section 3 |
| D34 | The skeleton pose that simulation code reads is cached per animation state. `anim_getJointMatrix` rebuilds only when no pose is attached; drawing attaches one; a least-recently-drawn rule keyed on the render frame counter detaches them; `anim_push`, `anim_clear`, `anim_syncToSimFrame` and others change the tracks without detaching. A query made after such a change and before the next animation step therefore returns different positions on machines that did and did not draw the object | Observed (mechanism); Inferred (consequence); no route to shared state found, none excluded | 0x16f73c, 0x16d7bc, 0x16f8c0, 0x16f8e4, 0x16edb8–0x16ede4, 0x16ee94; 0x170838, 0x1707b0, 0x1709f8 |
| D35 | `SmokeGen_run` makes its damage calls (shared-seed draws, hit points, disease) only when `isNearView(1000)` holds, and `WaveMaker_run` knocks creatures back and advances its own generator only when `isNearView(503)` holds: two more members of the D6 / D29 family | Observed; which levels place them is Unknown | 0x31c8c0, 0x31ca8c; 0x15f914, 0x15fef4, 0x1600d0 |
| D36 | A metal crate keeps a starting rotation drawn from the cosmetic seed and its physics depends on it. Crates are created only at level load, when the cosmetic seed equals the shared one. `PhProp` and a crate restored from a level record overwrite the rotation | Observed; equality Inferred | 0x168350, 0x15dddc, 0x15dbd4, 0x15e244, 0x1e59c4 |
| D37 | The weapon holder's per-frame update and `fx_modelStatusEffects` write nothing but a per-weapon effect block that only they read | Observed | 0x11b2a8, 0x11b3e8, 0x118058, 0x1f6ac8 |
| D38 | While a dialog is open the only activity centre is the object the dialog is with; the switch is driven by game messages 0 and 3 | Observed | 0x1e4d48, 0x231050, 0x22f1b0, 0x22fa24 |

## 11. Corrections to earlier documents (reported, not edited)

- **engine.md P11.** "Values do not depend on the buffer" is right for one build; whether a
  build happens depends on drawing (R1).
- **engine.md P5.** `PushPhysicsProp` slot 8 overwrites the rotation; the crate constructor
  0x15dddc does not; no crate is created outside level load (R4).
- **skills.md (b) 8.** `SmokeGen_run` read: R2.
- **objects.md, open questions.** `MissileWeapon_run`, `UserParamProp_run`,
  `CosmeticPropAnim_run`, `PushPhysicsProp` (constructor, load, run in outline) and
  `WaveMaker_run` now read as far as section 4 and R3, R4 say.
- **arena-desync.md, "Not done" and both "weakest link" notes.** `fx_modelStatusEffects`
  and the weapon holder update: presentation only (section 6).
- **gameplay.md §8.14.** The camera-gated emitters are now checked by callee list, not only
  by text scan.
- **Old scan output.** A line that showed the pathfinder timer under `Savepoint` or
  `SpellResurrect` (through `mainloop_startFadeWait`) was a boundary artefact; D5 itself
  stands.
- **tools/localstate.py.** Label and docstring points of section 9, row 9.

## 12. Not done

- R1 beyond the checks listed there.
- Which levels contain `SmokeGen`, `wave` lines or metal crates.
- The 85 simulation-side functions of limit 4 were not triaged. Most are named in the
  per-machine sections of the area documents; the seven listed in that row were not read.
- Run tasks and game-message handlers as scan roots.
- `Weather_run`'s lightning branch (0x1484c8 and the light fields at +0xac…+0xe8) was read
  only far enough to see that it is driven by the frame counter and the own generator.
- `res_find` loading a lump on demand from simulation code: only the timing side was
  looked at. Whether the order of the lump list, which on-demand loads from drawing and
  menus also change, can alter what a later `res_find` returns was not examined.
- Draw-only sites (4.7).
