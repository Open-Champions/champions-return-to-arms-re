# Level-script commands: native composition

Status 2026-10-20, SLUS-20973 v2.00. Branch `t3/research-script`. A playable level runs when its `script.scr` runs. The native client already has the AMX machine (`Session::add_script` in `session.cpp`). The 191 engine commands are a separate binder, `Variables::natives()` in `script_builtins.cpp`. The playable session does not install that binder. This document names, for each command, the native function the binder's call-out should reach.

`tools/ref_script_compose.py` is the table as code. Call counts in the table are the shipped-script census in section 3 of `docs/script.md`. A walk of the disc's 120 `script.scr` files (`tools/script_usage.py`) reproduced that census: 5,660 `SYSREQ.C`, 0 `SYSREQ.pri`, 122 commands used, 69 never called, and the same count and level-count for every command. That walk is **Observed** (the loader in `tools/ref_amx.py` marks each instruction; the operand of opcode 0x7b is the script's own import index). No level name, entry-point name or string literal is recorded here.

## How a row was decided

Three evidence layers:

- **Executed.** `docs/spec/script-builtins.md` section 8 ran all 190 handlers in `tools/ee_emu.py`. This session ran the 14 commands with at least 100 disc calls again, and the entry points of the 95 scripts that import one of them. Results are in "What was run".
- **Observed.** The disc counts above. Addresses in the notes of `tools/ref_script_compose.py` are the handler addresses already listed in `docs/script.md`.
- **Inferred.** The native symbol is the playable-integration function whose header cites the same operation. `none` means no such function was found. The session does not call any of these from a level script.

Effect words:

- **documented** — the named function is the command's effect, and that effect has an executed contract (the binder's port of `tools/ref_natives.py`, or a callee this repository or the cited native header already executed).
- **partly documented** — the handler was executed; the named function is one part of the effect, or the callee is a different contract.
- **unknown** — no native function performs the effect. The seam column is still the call the handler makes, from `tools/ref_natives.py` `EXT` and `VIRTUAL`.

Counts: 81 documented (3,883 calls), 70 partly documented (1,184 calls), 40 unknown (593 calls).

## The seam

`Session::add_script` wraps the caller's `NativeMap` and runs it. `Variables::natives()` returns the 191 names. Installing that map is the composition root. The binder then needs four host callbacks the playable code already has pieces of:

| Callback | What fills it |
|---|---|
| `random_draw` / word 0x404464 | the session world's shared seed, the same LCG (`seed * 0x19660d + 0x3c6ef35f`, high 16 bits) |
| `local_player_slot` | the session's local player, for `getMedal` |
| `run_reward_script` | `Variables::run_script`, for `grantBronze` / `grantSilver` / `grantGold` |
| `scene_service` / `inventory_service` / `object_query` | the subsystem named on the row |

Object lookup stays `objects::NameTable`. Grid changes stay `objects::World::move_off_grid`, `update_grid_cell` and `run_every_frame`. `getRand` must advance the session seed. A private seed in the binder desynchronises combat and FX, which use the same multiplier.

## What to implement next

Order is call count among commands a shipped script actually uses, grouped so one wiring covers a whole set. The 69 commands with zero calls stay off this list.

1. **Install the binder.** One `Variables` on the session, the shared seed, `local_player_slot` and `run_reward_script`. That covers the documented script-binder rows, including `getv` (790), `setv` (571), `callScript` (357), `addDeferedCall` (278), `getRand` (130), `getMissionAvailable` (129), `getMissionComplete` (115), `gamePaused` (108), `postAction` (105), `setMissionAvailable` (88), `getEvil` (63) and the smaller documented stores (gold, flags, quests, entrance-independent helpers). Documented call mass is 3,883, most of it in this step.
2. **Hide, show and move.** `hideMonster` (373), `showMonster` (52), `moveMonster` (3) go to `objects::World` grid functions. The flag writes stay in the binder. Both halves are executed.
3. **Level change.** `newWorld` (163) and `simpleNewWorld` (4) call `level_flow::new_world_gate` and then `Pending::request`. `setEntrance` (76) is `level_flow::State::entrance`. `net_closeLocalMenus` has no native function; the gate and the pending name do.
4. **Particles.** `addParticleOnObject` (54) scales velocity by 1/1000 in the binder and calls `fx::EffectWorld::particle_spawn` (header cites 0x18f3f8).
5. **Creature stats, home range and AI state.** `setMonsterVal` (114), `selectSetMonsterVal` (9) and `setMonsterRange` store the four field halves in the binder; `which == 4` and a positive range are base slot 34 `0x3c2708`, executed. `setCreatureParams` (56) and `initScriptSetParams` (13) call `Creature_scaleStats` 0x1185d8, executed. `stopFollowingPath` (45), `selectStopPath` (11), `rootMonster` (16) and `killMonster` (15) call slot 27. The base store `0x3c2688` is executed. A derived set-state is the animation table; the filter in front of it is already `ref_creature.filter_state`. A request of 0 does not clear a root timer. The contract is `docs/script-effects.md`.
6. **Spawn.** `generateMonster` (136 calls, 11 scripts) interns a class name and calls `ScriptGenerator_spawn` 0x265fc4. The wrapper's flag, name, slot 0, Skeleton test and state 23 are executed (`docs/script-effects.md`). `world_createObject` 0x14f6c8 is still the factory and is not entered. `combat_runtime::World::spawn_class` builds the own-machine classes and is a different constructor.
7. **HUD text, compass and bust.** `setInfo` (95), `addHelpMessage` (65), `addHelpMessageF` (7), `showBust` (31) and `showCompass` (3) have executed setters in `docs/script-effects.md`. Drawing those widgets stays `docs/hud-dynamic.md` on `t3/research-ui`. `runMedalSuccess` (30) and `runMedalFail` (10) still enter `hud_drawMessageBox` as a different body.
8. **Bags.** `removePlayerItem` (147), `playerHasItem` (61), `countQuestItems` (61) and `onePlayerHasItem` (36) walk bags. `items::parse_descriptor` parses a descriptor and does not walk a bag. Item-gated scripts wait on this.
9. **Still no native function, and scripts do call them.** `autoPropSetState` (62, virtual slot 18), `cutScene` (58, `cut_start` 0x19b4dc), `startDialog` (45, `dialog_start` 0x22fa50), `activateStore` (45, `shop_openOrStock` 0x1c7af8), `savePlayer` / `restorePlayer` (36 each, the medal-player record copy), `playerAdjustStat` (27), `soundSequence` (27, object-attached playback). `audio::Playback` can play a named sample and a level track; attaching a voice to an object is a further seam.
10. **Leave the zero-call commands.** Vehicles, prop and NPC animation, `givePlayerRandom`, the unused music commands, and the empty player-select commands are in the table so a later script can find them. No shipped script calls them.

`tools/ref_script_compose.py` with no arguments prints this rank from the published counts. A documented command with more calls sorts ahead of a partly documented one, which sorts ahead of an unknown one.

## What was run

**Executed** in `tools/ee_emu.py` through `tools/difftest_natives.py`, seed 20973, the US v2.00 executable. The 14 commands at or above 100 calls, 12 random states each, entered by `scr_callNative` 0x141050 and compared with `tools/ref_natives.py` on the result, the error word, the call-outs, the bytes written and the shared seed:

`getv`, `setv`, `hideMonster`, `callScript`, `addDeferedCall`, `newWorld`, `removePlayerItem`, `generateMonster`, `getRand`, `getMissionAvailable`, `getMissionComplete`, `setMonsterVal`, `gamePaused`, `postAction`.

All 14 matched. `removePlayerItem` entered 6 of 12 basic blocks in that 12-state sample. A 60-state run of the same command entered 12 of 12, 63 call-outs, 0 mismatches. The other thirteen of the sample entered every block of that handler.

The 95 scripts that contain one of those 14 commands were then run on the same interpreter: every entry point once (1,847 runs, 1,796 of 1,798 ran to the end, 3,713 call-outs, 51 runs where both sides stop on a null object) and, for each script, `preStart`, `start` and 10 ticks of the deferred task with the post action on every tenth tick (2,381 steps, 2,687 call-outs, 9 sequences ended where both sides stop on a null object). 17 properties, 0 mismatches. `tools/vu1_emu.py` is not on this path. Nothing was run on a console or in the Play! emulator.

## The 191 commands

The note for each row, including the handler address, is the last field of `tools/ref_script_compose.py`.

| # | Command | Calls | Effect | Native function | Seam |
|---:|---|---:|---|---|---|
| 0 | `callScript` | 357 | documented | `Variables::run_script` | `in-model` |
| 1 | `print` | 31 | documented | `Variables::utility_dispatch` | `in-model` |
| 2 | `printVal` | 31 | documented | `Variables::utility_dispatch` | `in-model` |
| 3 | `sound` | 0 | partly documented | `audio::Playback::play_sample` | `sound_playSample` |
| 4 | `soundSequence` | 27 | partly documented | `audio::Playback::play_sample` | `sound_playOnObject` |
| 5 | `lightEffect` | 0 | partly documented | `lighting::LightEffect` | `LightEffect_ctor` |
| 6 | `simpleNewWorld` | 4 | partly documented | `level_flow::Pending::request` | `net_closeLocalMenus` |
| 7 | `newWorld` | 163 | partly documented | `level_flow::new_world_gate` | `net_closeLocalMenus` |
| 8 | `newWorldAlways` | 0 | partly documented | `level_flow::new_world_gate` | `net_closeLocalMenus` |
| 9 | `newWorldPost` | 5 | partly documented | `Variables::scene_dispatch` | `in-model` |
| 10 | `activateMissionMenu` | 4 | unknown | `none` | `missionMenu_open` |
| 11 | `activateStore` | 45 | unknown | `none` | `shop_openOrStock` |
| 12 | `storeRunning` | 0 | partly documented | `Variables::menu_dispatch` | `in-model` |
| 13 | `getScaledTime` | 26 | documented | `Variables::utility_dispatch` | `in-model` |
| 14 | `setFarClip` | 0 | unknown | `none` | `camera_setFarClip` |
| 15 | `startDialog` | 45 | unknown | `none` | `dialog_start` |
| 16 | `changeSwoop` | 43 | documented | `Variables::scene_dispatch` | `in-model` |
| 17 | `startWithSwoopDone` | 3 | documented | `Variables::scene_dispatch` | `in-model` |
| 18 | `dialogRunning` | 0 | partly documented | `Variables::scene_dispatch` | `dialog_isOpen` |
| 19 | `increaseEnemyRank` | 15 | documented | `Variables::creature_dispatch` | `in-model` |
| 20 | `charmMonster` | 20 | partly documented | `none` | `Creature_setCharm` |
| 21 | `rootMonster` | 16 | partly documented | `none` | `virtual:27` |
| 22 | `unRootMonster` | 8 | documented | `Variables::creature_dispatch` | `in-model` |
| 23 | `selectSetMonsterVal` | 9 | partly documented | `none` | `virtual:34` |
| 24 | `setMonsterVal` | 114 | partly documented | `none` | `virtual:34` |
| 25 | `selectSetCFlag` | 0 | partly documented | `audio::Playback::boss_music_name` | `creature_startBossMusic` |
| 26 | `setCFlag` | 18 | partly documented | `audio::Playback::boss_music_name` | `creature_startBossMusic` |
| 27 | `selectSetOFlag` | 0 | documented | `Variables::apply_oflag` | `in-model` |
| 28 | `setOFlag` | 0 | documented | `Variables::apply_oflag` | `in-model` |
| 29 | `setWeaponType` | 10 | unknown | `none` | `virtual:8` |
| 30 | `setMonsterRange` | 0 | partly documented | `none` | `virtual:34` |
| 31 | `killMonster` | 15 | partly documented | `combat_runtime::World::take_damage` | `virtual:27` |
| 32 | `deleteMonster` | 33 | partly documented | `combat_runtime::World::destroy` | `virtual:1` |
| 33 | `hideMonster` | 373 | documented | `objects::World::move_off_grid` | `obj_moveOffGrid` |
| 34 | `showMonster` | 52 | documented | `objects::World::update_grid_cell` | `obj_updateGridCell` |
| 35 | `moveMonster` | 3 | documented | `objects::World::update_grid_cell` | `obj_updateGridCell` |
| 36 | `followPlayer` | 0 | partly documented | `none` | `Creature_setCharm` |
| 37 | `stopFollowingPlayer` | 0 | documented | `Variables::creature_dispatch` | `in-model` |
| 38 | `followPath` | 28 | partly documented | `objects::World::run_every_frame` | `obj_runEveryFrame` |
| 39 | `selectFollowPath` | 3 | partly documented | `objects::World::run_every_frame` | `obj_runEveryFrame` |
| 40 | `stopFollowingPath` | 45 | partly documented | `none` | `virtual:27` |
| 41 | `selectStopPath` | 11 | partly documented | `none` | `virtual:27` |
| 42 | `friendly` | 13 | documented | `Variables::creature_dispatch` | `in-model` |
| 43 | `unFriendly` | 6 | documented | `Variables::creature_dispatch` | `in-model` |
| 44 | `startPropAnim` | 0 | unknown | `none` | `anim_start` |
| 45 | `stopPropAnim` | 0 | partly documented | `Variables::effects_dispatch` | `in-model` |
| 46 | `propAnimAtEnd` | 0 | partly documented | `Variables::effects_dispatch` | `in-model` |
| 47 | `startNPCAnim` | 0 | unknown | `none` | `anim_start` |
| 48 | `NPCAnimAtEnd` | 0 | partly documented | `Variables::effects_dispatch` | `in-model` |
| 49 | `addExpandingPool` | 0 | partly documented | `fx::EffectWorld::decal_add` | `decal_add` |
| 50 | `playerHasItem` | 61 | unknown | `items::parse_descriptor` | `inventory_countItemByName` |
| 51 | `onePlayerHasItem` | 36 | unknown | `items::parse_descriptor` | `inventory_countItemByName` |
| 52 | `removePlayerItem` | 147 | unknown | `items::parse_descriptor` | `inventory_removeItem` |
| 53 | `givePlayerItem` | 10 | partly documented | `items::parse_descriptor` | `inventory_giveItem` |
| 54 | `giveOnePlayerItem` | 2 | partly documented | `items::parse_descriptor` | `inventory_giveItem` |
| 55 | `givePlayerRandom` | 0 | partly documented | `items::parse_descriptor` | `item_generateWithAffixes` |
| 56 | `givePlayerExp` | 0 | unknown | `none` | `player_giveExp` |
| 57 | `givePlayerGold` | 4 | documented | `Variables::interaction_dispatch` | `in-model` |
| 58 | `takePlayerGold` | 1 | documented | `Variables::interaction_dispatch` | `in-model` |
| 59 | `checkPlayerGold` | 4 | documented | `Variables::interaction_dispatch` | `in-model` |
| 60 | `checkPlayerMinGold` | 0 | documented | `Variables::interaction_dispatch` | `in-model` |
| 61 | `playGotItemSound` | 3 | partly documented | `none` | `player_voice` |
| 62 | `setInfo` | 95 | partly documented | `hud_dynamic::helpBox` | `hud_showMessage` |
| 63 | `addHelpMessage` | 65 | partly documented | `hud_dynamic::helpBox` | `hud_showHelpMessage` |
| 64 | `addQuest` | 43 | documented | `Variables::quest_add` | `in-model` |
| 65 | `removeQuest` | 30 | documented | `Variables::quest_remove` | `in-model` |
| 66 | `hornOmen` | 0 | partly documented | `none` | `SpellHornOmenEffect_ctor` |
| 67 | `planarSteel` | 0 | partly documented | `none` | `SpellPlanarSteelEffect_ctor` |
| 68 | `particleMorph` | 0 | unknown | `none` | `ParticleMorphEffect_ctor` |
| 69 | `healPlayer` | 0 | partly documented | `none` | `sound_playOnObject` |
| 70 | `leaveGame` | 5 | partly documented | `Variables::scene_dispatch` | `in-model` |
| 71 | `endGame` | 0 | unknown | `none` | `memcard_requestEndGameSave` |
| 72 | `clearRecall` | 0 | partly documented | `level_flow::apply_act_entry` | `in-model` |
| 73 | `startMusic` | 0 | partly documented | `audio::Playback::music_play_level` | `music_playLevel` |
| 74 | `startAudio` | 0 | partly documented | `audio::Playback::music_play_level` | `stream_playLevel` |
| 75 | `endMusic` | 0 | partly documented | `audio::Playback::queue_stop` | `stream_queueStop` |
| 76 | `saveGame` | 3 | unknown | `none` | `memcard_requestSave` |
| 77 | `saveEndConfig` | 3 | unknown | `none` | `memcard_requestConfigSave` |
| 78 | `saveDone` | 6 | unknown | `none` | `memcard_getState` |
| 79 | `exitToMainMenu` | 0 | partly documented | `Variables::scene_dispatch` | `in-model` |
| 80 | `reapEnemies` | 1 | partly documented | `combat_runtime::World::destroy` | `virtual:1` |
| 81 | `getv` | 790 | documented | `Variables::quest_get` | `in-model` |
| 82 | `getNumPlayers` | 33 | documented | `Variables::interaction_dispatch` | `in-model` |
| 83 | `setv` | 571 | documented | `Variables::quest_set` | `in-model` |
| 84 | `addv` | 0 | documented | `Variables::quest_get` | `in-model` |
| 85 | `setpv` | 27 | partly documented | `none` | `memcard_requestConfigSave` |
| 86 | `getpv` | 0 | documented | `Variables::profile_get` | `in-model` |
| 87 | `getRand` | 130 | documented | `Variables::random_draw` | `in-model` |
| 88 | `activePlayerIsDwarf` | 0 | documented | `Variables::interaction_dispatch` | `in-model` |
| 89 | `activePlayerIsElf` | 0 | documented | `Variables::interaction_dispatch` | `in-model` |
| 90 | `gamePaused` | 108 | documented | `Variables::utility_dispatch` | `in-model` |
| 91 | `pauseGameControl` | 0 | partly documented | `Variables::scene_dispatch` | `in-model` |
| 92 | `levelLoading` | 0 | documented | `Variables::utility_dispatch` | `in-model` |
| 93 | `setParticle` | 14 | partly documented | `fx::EffectWorld::add_definition` | `particle_define` |
| 94 | `addParticleOnObject` | 54 | documented | `fx::EffectWorld::particle_spawn` | `particle_spawn` |
| 95 | `setNoCollide` | 0 | documented | `Variables::effects_dispatch` | `in-model` |
| 96 | `shakeCamera` | 4 | unknown | `none` | `camera_shake` |
| 97 | `deleteObjects` | 0 | partly documented | `combat_runtime::World::destroy` | `virtual:1` |
| 98 | `hidePlayers` | 0 | documented | `Variables::interaction_dispatch` | `in-model` |
| 99 | `checkPlayerAlive` | 0 | documented | `Variables::count_players_with_hp` | `in-model` |
| 100 | `setBestActivePlayer` | 0 | documented | `Variables::interaction_dispatch` | `in-model` |
| 101 | `decayPlayerLights` | 0 | documented | `Variables::interaction_dispatch` | `in-model` |
| 102 | `checkMonstersLeft` | 0 | partly documented | `objects::World::for_each_grid_object` | `world_forEachGridObject` |
| 103 | `forceMutexRelease` | 0 | unknown | `none` | `menuMutex_release` |
| 104 | `addDeferedCall` | 278 | documented | `Variables::queue_deferred` | `in-model` |
| 105 | `cutScene` | 58 | unknown | `none` | `cut_start` |
| 106 | `postAction` | 105 | documented | `Variables::set_post_action` | `in-model` |
| 107 | `newWorldParameter` | 0 | partly documented | `level_flow::Pending::request` | `net_closeLocalMenus` |
| 108 | `putNPCInVehicle` | 0 | unknown | `none` | `Vehicle_attachNpcDriver` |
| 109 | `putPlayersInVehicle` | 0 | unknown | `none` | `virtual:14` |
| 110 | `entityRideVehicle` | 0 | unknown | `none` | `virtual:19` |
| 111 | `controlVehicle` | 0 | unknown | `none` | `in-model` |
| 112 | `playersLoaded` | 0 | documented | `Variables::scene_dispatch` | `in-model` |
| 113 | `holdVehicle` | 0 | unknown | `none` | `Vehicle_setHold` |
| 114 | `getPlayerVPosition` | 0 | unknown | `none` | `in-model` |
| 115 | `getVPosition` | 0 | unknown | `none` | `in-model` |
| 116 | `getPlayerVDir` | 0 | unknown | `none` | `in-model` |
| 117 | `setupPlayerSel` | 0 | unknown | `none` | `in-model` |
| 118 | `startPlayerSel` | 0 | unknown | `none` | `in-model` |
| 119 | `playerSelRunning` | 0 | unknown | `none` | `playerSel_isRunning` |
| 120 | `objInPlayerTrig` | 0 | unknown | `none` | `virtual:17` |
| 121 | `setEntrance` | 76 | documented | `level_flow::State::entrance` | `in-model` |
| 122 | `hudResetFadeScreen` | 0 | partly documented | `none` | `hud_setFade` |
| 123 | `hudFadeScreen` | 0 | partly documented | `none` | `hud_stepFade` |
| 124 | `closestPlayerDist` | 2 | documented | `Variables::distance3` | `in-model` |
| 125 | `hitPlayers` | 11 | partly documented | `combat_runtime::World::take_damage` | `virtual:2` |
| 126 | `zeroPlayerMana` | 2 | documented | `Variables::interaction_dispatch` | `in-model` |
| 127 | `showCompass` | 3 | partly documented | `hud_dynamic::compassLabel` | `hud_setCompassTarget` |
| 128 | `showBust` | 31 | partly documented | `hud_dynamic::bustFadeStep` | `hud_setBust` |
| 129 | `getMaxPlayerHP` | 2 | documented | `Variables::interaction_dispatch` | `in-model` |
| 130 | `getHitPoints` | 25 | documented | `Variables::creature_dispatch` | `in-model` |
| 131 | `setHitPoints` | 0 | documented | `Variables::creature_dispatch` | `in-model` |
| 132 | `saveCheckPoint` | 16 | partly documented | `level_flow::checkpoint` | `save_game` |
| 133 | `loadCheckPoint` | 0 | partly documented | `level_flow::party_wipe` | `deathTask_schedule` |
| 134 | `trigger` | 29 | partly documented | `level_flow::Trigger::interact` | `virtual:3` |
| 135 | `autoPropSetState` | 62 | unknown | `none` | `virtual:18` |
| 136 | `autoPropGetState` | 0 | unknown | `none` | `in-model` |
| 137 | `preloadResource` | 13 | partly documented | `level_flow::Loader::load` | `lump_load` |
| 138 | `setSaveInhibit` | 44 | documented | `Variables::scene_dispatch` | `in-model` |
| 139 | `getSaveInhibit` | 0 | documented | `Variables::scene_dispatch` | `in-model` |
| 140 | `countQuestItems` | 61 | unknown | `items::parse_descriptor` | `inventory_countItemByName` |
| 141 | `countPlayersAlive` | 11 | documented | `Variables::interaction_dispatch` | `in-model` |
| 142 | `countLiveObjects` | 0 | documented | `objects::NameTable` | `in-model` |
| 143 | `networkMode` | 3 | documented | `Variables::utility_dispatch` | `in-model` |
| 144 | `getManaUsed` | 0 | documented | `Variables::interaction_dispatch` | `in-model` |
| 145 | `getHealthUsed` | 1 | documented | `Variables::interaction_dispatch` | `in-model` |
| 146 | `getLevelTimer` | 0 | documented | `Variables::utility_dispatch` | `in-model` |
| 147 | `getEvil` | 63 | documented | `Variables::choice_get` | `in-model` |
| 148 | `setEvil` | 2 | documented | `Variables::choice_set` | `in-model` |
| 149 | `getMadeDecision` | 4 | documented | `Variables::choice_get` | `in-model` |
| 150 | `setMadeDecision` | 2 | documented | `Variables::choice_set` | `in-model` |
| 151 | `grantMission` | 33 | documented | `Variables::mission_set_complete` | `in-model` |
| 152 | `getMissionComplete` | 115 | documented | `Variables::mission_complete` | `in-model` |
| 153 | `setMissionAvailable` | 88 | documented | `Variables::mission_set_available` | `in-model` |
| 154 | `getMissionAvailable` | 129 | documented | `Variables::mission_available` | `in-model` |
| 155 | `grantGold` | 9 | documented | `Variables::mission_grant_medal` | `run_reward_script` |
| 156 | `grantSilver` | 9 | documented | `Variables::mission_grant_medal` | `run_reward_script` |
| 157 | `grantBronze` | 9 | documented | `Variables::mission_grant_medal` | `run_reward_script` |
| 158 | `getMedal` | 9 | documented | `Variables::mission_get_medal` | `local_player_slot` |
| 159 | `generateMonster` | 136 | partly documented | `combat_runtime::World::spawn_class` | `ScriptGenerator_spawn` |
| 160 | `monstersInTrigger` | 10 | unknown | `none` | `MonsterTrigger_count` |
| 161 | `sin1000` | 35 | documented | `core_math::sin16` | `in-model` |
| 162 | `cos1000` | 35 | documented | `core_math::cos16` | `in-model` |
| 163 | `helpMessageActive` | 0 | partly documented | `Variables::menu_dispatch` | `in-model` |
| 164 | `addHelpMessageF` | 7 | partly documented | `hud_dynamic::helpBox` | `hud_showHelpMessage` |
| 165 | `revealMap` | 3 | unknown | `none` | `automap_revealAll` |
| 166 | `showOnMap` | 24 | documented | `Variables::menu_dispatch` | `in-model` |
| 167 | `initScriptSetParams` | 13 | partly documented | `none` | `Creature_scaleStats` |
| 168 | `setCreatureParams` | 56 | partly documented | `none` | `Creature_scaleStats` |
| 169 | `explodePotionsOnly` | 1 | documented | `Variables::interaction_dispatch` | `in-model` |
| 170 | `runMedalSuccess` | 30 | partly documented | `hud_dynamic::medalPrompt` | `hud_drawMessageBox` |
| 171 | `runMedalFail` | 10 | partly documented | `hud_dynamic::medalPrompt` | `hud_drawMessageBox` |
| 172 | `setAlternateDeath` | 9 | partly documented | `level_flow::party_wipe` | `in-model` |
| 173 | `dropItem` | 6 | partly documented | `items::parse_descriptor` | `loot_spawnNamedItem` |
| 174 | `selectDropItem` | 9 | partly documented | `items::parse_descriptor` | `loot_spawnNamedItem` |
| 175 | `findDistance` | 4 | documented | `Variables::distance3` | `in-model` |
| 176 | `setContainerProps` | 6 | unknown | `none` | `in-model` |
| 177 | `setWaveDetail` | 1 | documented | `Variables::utility_dispatch` | `in-model` |
| 178 | `demoRunning` | 7 | documented | `Variables::utility_dispatch` | `in-model` |
| 179 | `removeAllItems` | 1 | unknown | `items::parse_descriptor` | `inventory_removeItem` |
| 180 | `savePlayer` | 36 | partly documented | `level_flow::PlayerRecord` | `save_playerCopy` |
| 181 | `restorePlayer` | 36 | partly documented | `level_flow::PlayerRecord` | `save_playerCopy` |
| 182 | `piercePlayerEar` | 1 | documented | `Variables::interaction_dispatch` | `in-model` |
| 183 | `playerAdjustStat` | 27 | unknown | `none` | `inventory_onStatPoint` |
| 184 | `giveFullHealth` | 1 | documented | `Variables::interaction_dispatch` | `in-model` |
| 185 | `setPlayerFlag` | 12 | documented | `Variables::player_set_flag` | `in-model` |
| 186 | `getPlayerFlag` | 7 | documented | `Variables::player_get_flag` | `in-model` |
| 187 | `clearAllSkills` | 2 | documented | `Variables::interaction_dispatch` | `in-model` |
| 188 | `isClericOrWizard` | 1 | documented | `Variables::interaction_dispatch` | `in-model` |
| 189 | `refillPlayerMana` | 2 | documented | `Variables::interaction_dispatch` | `in-model` |
| 190 | `removeAllWeapons` | 1 | unknown | `items::parse_descriptor` | `inventory_removeItem` |
