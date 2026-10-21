#!/usr/bin/env python3
"""Which native subsystem already implements each level-script command.

The 191 names are the table at 0x403370, in tools/ref_natives.py order. The
playable client (open-champions-godot, worktree playable-integration) runs an
AMX machine whose callbacks are supplied by the caller. Session::add_script
does not install Variables::natives(). Those bindings are the script binder:
they perform the in-model writes and they call out through scene_service,
inventory_service, player_service, object_query and Host::call. This module
names, for each command, the playable function that call-out should reach.

Status is the retail effect, not the handler listing:

  documented          the named native function is that effect, and the effect
                      was executed against the original (the handler in
                      tools/difftest_natives.py, and the callee where named)
  partly documented   the handler was executed; the named function is only
                      part of the effect, or the callee body is a different
                      contract
  unknown             no native function performs the effect

Nothing here is wired. A row's native symbol is the function to call, not a
claim that Session already calls it. Call counts are parsed from the tables in
docs/script.md (the shipped-script census). tools/script_usage.py recounts
them from a disc and prints counts only.
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_natives as N                         # noqa: E402

ROOT = os.path.dirname(_HERE)
SCRIPT_MD = os.path.join(ROOT, 'docs', 'script.md')

SUBSYSTEMS = (
    'script-binder', 'level-flow', 'objects', 'combat-runtime', 'creature-ai',
    'fx', 'audio', 'hud', 'items', 'save', 'session', 'none',
)
STATUSES = ('documented', 'partly documented', 'unknown')

# name, subsystem, native symbol, status, seam, note
# The symbol is a function in the playable-integration headers cited in the note's
# subsystem, or a Variables method in native/src/script_builtins.cpp.
_ROWS = (
    ('callScript', 'script-binder', 'Variables::run_script', 'documented', 'in-model',
     'Nested script_runByName on the one machine. 0x143158.'),
    ('print', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'Converts the string and drops it. 0x143120.'),
    ('printVal', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'Returns 0. 0x143150.'),
    ('sound', 'audio', 'audio::Playback::play_sample', 'partly documented', 'sound_playSample',
     'Handler calls sound_playSample 0x2134e8 with three floats and a resource. Playback plays a named sample.'),
    ('soundSequence', 'audio', 'audio::Playback::play_sample', 'partly documented', 'sound_playOnObject',
     'sound_playOnObject 0x214230 then sound_setPlaysWhileFrozen 0x216ad0. Playback has no object attachment.'),
    ('lightEffect', 'fx', 'lighting::LightEffect', 'partly documented', 'LightEffect_ctor',
     'Handler passes twelve values to LightEffect_ctor 0x201bd8. EffectWorld stores a lighting::LightEffect for that constructor.'),
    ('simpleNewWorld', 'level-flow', 'level_flow::Pending::request', 'partly documented', 'net_closeLocalMenus',
     'new_world_gate then the name with orientation 0xff. Menu close has no native function. 0x143e70.'),
    ('newWorld', 'level-flow', 'level_flow::new_world_gate', 'partly documented', 'net_closeLocalMenus',
     'Gate matches level_flow::new_world_gate; the name and orientation go to Pending::request. 0x143dd0.'),
    ('newWorldAlways', 'level-flow', 'level_flow::new_world_gate', 'partly documented', 'net_closeLocalMenus',
     'Same handler as newWorld, 0x143dd0. The ungated copy at 0x143e30 has no table entry.'),
    ('newWorldPost', 'script-binder', 'Variables::scene_dispatch', 'partly documented', 'in-model',
     'Stores the name at 0x4fdcf0. level_flow::State has no post-dialog level field.'),
    ('activateMissionMenu', 'none', 'none', 'unknown', 'missionMenu_open',
     'missionMenu_open 0x231520. No native mission menu.'),
    ('activateStore', 'none', 'none', 'unknown', 'shop_openOrStock',
     'shop_openOrStock 0x1c7af8, store index 0x4f7150. No native shop.'),
    ('storeRunning', 'script-binder', 'Variables::menu_dispatch', 'partly documented', 'in-model',
     'Returns the shop-open word 0x41b50c. Nothing in the playable client writes it.'),
    ('getScaledTime', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'int(n * 60 * (1/60 truncated)). 0x14412c.'),
    ('setFarClip', 'none', 'none', 'unknown', 'camera_setFarClip',
     'camera_setFarClip 0x18617c, cap 1800. No native far-clip.'),
    ('startDialog', 'none', 'none', 'unknown', 'dialog_start',
     'dialog_start 0x22fa50 sends game message 0 with the local camera. No native dialog opener.'),
    ('changeSwoop', 'script-binder', 'Variables::scene_dispatch', 'documented', 'in-model',
     'Stores the mode at 0x4fdce4. 0x1438b0.'),
    ('startWithSwoopDone', 'script-binder', 'Variables::scene_dispatch', 'documented', 'in-model',
     'Sets 0x4fdce8. 0x1438c4.'),
    ('dialogRunning', 'script-binder', 'Variables::scene_dispatch', 'partly documented', 'dialog_isOpen',
     'Returns 0x8e2d60 != 0. Whether that byte flips on the same frame on every machine is not established.'),
    ('increaseEnemyRank', 'script-binder', 'Variables::creature_dispatch', 'documented', 'in-model',
     'Sets creature flag bit 44. 0x144200.'),
    ('charmMonster', 'creature-ai', 'none', 'partly documented', 'Creature_setCharm',
     'Creature_setCharm 0x1189f0, permanent, team 0. No native charm.'),
    ('rootMonster', 'creature-ai', 'none', 'partly documented', 'virtual:27',
     'Sets +0x314 to -1 and virtual slot 27 with 0, unless AI state is 0x14. Slot 27 refuses a bare boolean.'),
    ('unRootMonster', 'script-binder', 'Variables::creature_dispatch', 'documented', 'in-model',
     'Sets +0x314 to 0. 0x144408.'),
    ('selectSetMonsterVal', 'creature-ai', 'none', 'partly documented', 'virtual:34',
     'Same stores as setMonsterVal on the selected object. which 4 is virtual slot 34.'),
    ('setMonsterVal', 'creature-ai', 'none', 'partly documented', 'virtual:34',
     'which 1, 2, 3, 5 store creature fields in the binder. which 4 is virtual slot 34. 0x144550.'),
    ('selectSetCFlag', 'audio', 'audio::Playback::boss_music_name', 'partly documented', 'creature_startBossMusic',
     'Same as setCFlag on the selected object. Bit 0 starts boss music.'),
    ('setCFlag', 'audio', 'audio::Playback::boss_music_name', 'partly documented', 'creature_startBossMusic',
     'Only bits 0 and 26. Bit 0 calls creature_startBossMusic 0x1192b0. Clearing bit 0 with bit 31 set clears the boss meters.'),
    ('selectSetOFlag', 'script-binder', 'Variables::apply_oflag', 'documented', 'in-model',
     'which 14 sets or clears object flag 0x4000. Other values do nothing.'),
    ('setOFlag', 'script-binder', 'Variables::apply_oflag', 'documented', 'in-model',
     'Same as selectSetOFlag, by name. 0x144834.'),
    ('setWeaponType', 'creature-ai', 'none', 'unknown', 'virtual:8',
     'Virtual slot 8 of the object at creature +0x50. No native weapon-visual slot.'),
    ('setMonsterRange', 'creature-ai', 'none', 'partly documented', 'virtual:34',
     'range > 0 calls virtual slot 34. No native home-range slot.'),
    ('killMonster', 'combat-runtime', 'combat_runtime::World::take_damage', 'partly documented', 'virtual:27',
     'Flags 0x2009, hit points 0, virtual slot 27 with 0x14. take_damage exists; goblin_set_state covers one death branch.'),
    ('deleteMonster', 'combat-runtime', 'combat_runtime::World::destroy', 'partly documented', 'virtual:1',
     'Virtual slot 1 with 3. destroy is that slot for a combat actor, not for every named object.'),
    ('hideMonster', 'objects', 'objects::World::move_off_grid', 'documented', 'obj_moveOffGrid',
     'Flag 0x8000, off the grid, creature bit +0x231 bit 3. move_off_grid is the executed grid half. 0x144c00.'),
    ('showMonster', 'objects', 'objects::World::update_grid_cell', 'documented', 'obj_updateGridCell',
     'Clears 0x8000 and the +0x231 bit, then relinks. 0x144db8.'),
    ('moveMonster', 'objects', 'objects::World::update_grid_cell', 'documented', 'obj_updateGridCell',
     'Copies position and facing from the target and relinks. 0x144cb8.'),
    ('followPlayer', 'creature-ai', 'none', 'partly documented', 'Creature_setCharm',
     'Flag bit 23 and the same charm call as charmMonster. No native follow.'),
    ('stopFollowingPlayer', 'script-binder', 'Variables::creature_dispatch', 'documented', 'in-model',
     'Clears flag bit 23. 0x144f2c.'),
    ('followPath', 'objects', 'objects::World::run_every_frame', 'partly documented', 'obj_runEveryFrame',
     'Sets flag bit 27, stores 44000 at +0x3c4, moves to the every-frame list. The path walker is not that list operation.'),
    ('selectFollowPath', 'objects', 'objects::World::run_every_frame', 'partly documented', 'obj_runEveryFrame',
     'followPath on the selected object.'),
    ('stopFollowingPath', 'creature-ai', 'none', 'partly documented', 'virtual:27',
     'Stores 1150, clears bit 27, copies position to +0x3b4, slot 27 with 0 unless state is 0x14.'),
    ('selectStopPath', 'creature-ai', 'none', 'partly documented', 'virtual:27',
     'stopFollowingPath on the selected object.'),
    ('friendly', 'script-binder', 'Variables::creature_dispatch', 'documented', 'in-model',
     'Object flag 0x1000000 and creature flag bit 26. 0x145294.'),
    ('unFriendly', 'script-binder', 'Variables::creature_dispatch', 'documented', 'in-model',
     'Clears both flags. 0x145338.'),
    ('startPropAnim', 'none', 'none', 'unknown', 'anim_start',
     'anim_start 0x16cfe0 on the prop block at +0x54. Native animation does not drive that block.'),
    ('stopPropAnim', 'script-binder', 'Variables::effects_dispatch', 'partly documented', 'in-model',
     'Clears the playing byte at +0x58. No native prop player reads it.'),
    ('propAnimAtEnd', 'script-binder', 'Variables::effects_dispatch', 'partly documented', 'in-model',
     'Bit 7 of +0x5a. No native prop player writes it.'),
    ('startNPCAnim', 'none', 'none', 'unknown', 'anim_start',
     'anim_clear / anim_push or anim_start on creature +0x114. No native NPC anim block.'),
    ('NPCAnimAtEnd', 'script-binder', 'Variables::effects_dispatch', 'partly documented', 'in-model',
     'Bit 7 of +0x11a on the first object of that name.'),
    ('addExpandingPool', 'fx', 'fx::EffectWorld::decal_add', 'partly documented', 'decal_add',
     'decal_add 0x19f110. The native decal exists. The retail call also reads a detail option and the camera.'),
    ('playerHasItem', 'items', 'items::parse_descriptor', 'unknown', 'inventory_countItemByName',
     'inventory_countItemByName 0x1c5880 sums bags. items parses a descriptor and does not walk bags.'),
    ('onePlayerHasItem', 'items', 'items::parse_descriptor', 'unknown', 'inventory_countItemByName',
     'Count for one living player. Same missing bag walk.'),
    ('removePlayerItem', 'items', 'items::parse_descriptor', 'unknown', 'inventory_removeItem',
     'inventory_findItemBySubstring 0x1c5a70 then inventory_removeItem 0x1c1cb0. No native bag removal.'),
    ('givePlayerItem', 'items', 'items::parse_descriptor', 'partly documented', 'inventory_giveItem',
     'item_parseDescriptor 0x1069b8 is items::parse_descriptor. The bag insert and the ground drop are not.'),
    ('giveOnePlayerItem', 'items', 'items::parse_descriptor', 'partly documented', 'inventory_giveItem',
     'Same give path for one living player.'),
    ('givePlayerRandom', 'items', 'items::parse_descriptor', 'partly documented', 'item_generateWithAffixes',
     'item_generateWithAffixes 0x104ca4 has a native generator. The bag insert does not. No shipped call.'),
    ('givePlayerExp', 'none', 'none', 'unknown', 'player_giveExp',
     'player_giveExp 0x1d3150. No native experience grant.'),
    ('givePlayerGold', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Adds amount / player count to each record +0xe4, cap 99999999. 0x1462dc.'),
    ('takePlayerGold', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Subtracts the share, floored at 0. 0x1463ec.'),
    ('checkPlayerGold', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Sum of the gold words. 0x14644c.'),
    ('checkPlayerMinGold', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Minimum gold word. 0x146494.'),
    ('playGotItemSound', 'audio', 'none', 'partly documented', 'player_voice',
     'Clamps the stored active player to 0..1 and calls player_voice 0x1b7ba8 with the unclamped slot. No native voice.'),
    ('setInfo', 'hud', 'hud_dynamic::helpBox', 'partly documented', 'hud_showMessage',
     'hud_showMessage 0x1d92a0 for 180 frames. hud_dynamic has the help-box geometry, not this message queue.'),
    ('addHelpMessage', 'hud', 'hud_dynamic::helpBox', 'partly documented', 'hud_showHelpMessage',
     'hud_showHelpMessage 0x1d9830. The box layout is native. The open/send path is not.'),
    ('addQuest', 'script-binder', 'Variables::quest_add', 'documented', 'in-model',
     'Stops at the first player whose list is full or already has the title. 0x1433c8.'),
    ('removeQuest', 'script-binder', 'Variables::quest_remove', 'documented', 'in-model',
     'Placeholder overwrite; the count drops by one. 0x143448.'),
    ('hornOmen', 'fx', 'none', 'partly documented', 'SpellHornOmenEffect_ctor',
     'SpellHornOmenEffect_ctor 0x2fc574 and creature_addSpell. Skill recipes draw the effect; they are not this allocator.'),
    ('planarSteel', 'fx', 'none', 'partly documented', 'SpellPlanarSteelEffect_ctor',
     'Refills living hit points, then SpellPlanarSteelEffect_ctor 0x2fb728. A failed allocation still links a null spell.'),
    ('particleMorph', 'none', 'none', 'unknown', 'ParticleMorphEffect_ctor',
     'ParticleMorphEffect_ctor 0x160a88. No native morph effect.'),
    ('healPlayer', 'audio', 'none', 'partly documented', 'sound_playOnObject',
     'Cast sound on player 0, then hit points to maximum for living players. The refill is in-model; the sound is not native.'),
    ('leaveGame', 'session', 'Variables::scene_dispatch', 'partly documented', 'in-model',
     'Sets 0x41b508 to 1 or 0x65. The playable session has no reader of that word.'),
    ('endGame', 'save', 'none', 'unknown', 'memcard_requestEndGameSave',
     'memcard_requestEndGameSave 0x217c38. Native save is a replay checkpoint, not the memory card.'),
    ('clearRecall', 'level-flow', 'level_flow::apply_act_entry', 'partly documented', 'in-model',
     'Writes the five-byte None over every record +0x24. apply_act_entry does that on an act change, not on this command.'),
    ('startMusic', 'audio', 'audio::Playback::music_play_level', 'partly documented', 'music_playLevel',
     'music_playLevel 0x215f48 with flag 3. music_play_level exists; this flag argument was not the audio-2 gate set.'),
    ('startAudio', 'audio', 'audio::Playback::music_play_level', 'partly documented', 'stream_playLevel',
     'stream_playLevel 0x215fc8 with arguments (1, name, 2). No separate native stream-id 1 entry.'),
    ('endMusic', 'audio', 'audio::Playback::queue_stop', 'partly documented', 'stream_queueStop',
     'stream_queueStop 0x211338 with stream 2. queue_stop(2) is stop_boss_music, which is this call.'),
    ('saveGame', 'save', 'none', 'unknown', 'memcard_requestSave',
     'memcard_requestSave 0x2175b4 for the local slot, refused while a status byte is 2. No native card.'),
    ('saveEndConfig', 'save', 'none', 'unknown', 'memcard_requestConfigSave',
     'Lobby send, pause, drop remotes, completion bits, config save. No native card or lobby send.'),
    ('saveDone', 'save', 'none', 'unknown', 'memcard_getState',
     '1 when memcard_getState 0x217550 is -1. Local card state. No native card.'),
    ('exitToMainMenu', 'session', 'Variables::scene_dispatch', 'partly documented', 'in-model',
     'Sets 0x41b508 to 1. Same unread exit word as leaveGame.'),
    ('reapEnemies', 'combat-runtime', 'combat_runtime::World::destroy', 'partly documented', 'virtual:1',
     'Destroys dead non-player creatures in a whole-map box. destroy is slot 1 for a combat actor.'),
    ('getv', 'script-binder', 'Variables::quest_get', 'documented', 'in-model',
     'Signed byte of a quest variable; an unknown name is appended as 0. 0x143500.'),
    ('getNumPlayers', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Returns g_numPlayers 0x4d8ae0. 0x143534.'),
    ('setv', 'script-binder', 'Variables::quest_set', 'documented', 'in-model',
     'Clamped store, creating the name. 0x143540.'),
    ('addv', 'script-binder', 'Variables::quest_get', 'documented', 'in-model',
     'Get, 32-bit add, clamped store; returns the sum before the clamp. No shipped call.'),
    ('setpv', 'save', 'none', 'partly documented', 'memcard_requestConfigSave',
     'Profile store at 0x4f9030, then memcard_requestConfigSave when the value changes. The store is in-model.'),
    ('getpv', 'script-binder', 'Variables::profile_get', 'documented', 'in-model',
     'Signed byte from the profile table. The table is per machine. No shipped call.'),
    ('getRand', 'session', 'Variables::random_draw', 'documented', 'in-model',
     'seed = seed * 0x19660d + 0x3c6ef35f at 0x404464; result is the high 16 bits. The session seed is world->shared.state.'),
    ('activePlayerIsDwarf', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Active record +0x54 == 0. 0x1465a0.'),
    ('activePlayerIsElf', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Constant 0. 0x1465c4.'),
    ('gamePaused', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     '1 if 0x41b4f4, 0x500ae8 or 0x44fcd0 is set. The binder reads those three words. 0x14699c.'),
    ('pauseGameControl', 'script-binder', 'Variables::scene_dispatch', 'partly documented', 'in-model',
     'Stores the frame count at 0x41b4fc and 1 at 0x41b500. A net game clearing 0x41b4fc each tick is inferred, not executed.'),
    ('levelLoading', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'Returns 0x4f7198. No shipped call.'),
    ('setParticle', 'fx', 'fx::EffectWorld::add_definition', 'partly documented', 'particle_define',
     'particle_define 0x18f118 writes one of three script definitions. add_definition installs a definition; it is not that writer.'),
    ('addParticleOnObject', 'fx', 'fx::EffectWorld::particle_spawn', 'documented', 'particle_spawn',
     'Slot definition, object position plus the offset, velocity / 1000, then particle_spawn 0x18f3f8. 0x146e20.'),
    ('setNoCollide', 'script-binder', 'Variables::effects_dispatch', 'documented', 'in-model',
     'Sets or clears object flag bit 0. 0x146f58.'),
    ('shakeCamera', 'none', 'none', 'unknown', 'camera_shake',
     'camera_shake 0x1ebae0 when 0x4f7114 is 0. No native shake.'),
    ('deleteObjects', 'combat-runtime', 'combat_runtime::World::destroy', 'partly documented', 'virtual:1',
     'Virtual slot 1 with 3, at most 24 objects. destroy covers a combat actor.'),
    ('hidePlayers', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Stores the byte at 0x4f83f8. Player_draw is the only reader found.'),
    ('checkPlayerAlive', 'script-binder', 'Variables::count_players_with_hp', 'documented', 'in-model',
     'which != 0 reads the signed16 at 0x4f7194. which == 0 counts players with hit points. No shipped call.'),
    ('setBestActivePlayer', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Active player 0, or 1 when player 0 is missing or dead and there are two players. No shipped call.'),
    ('decayPlayerLights', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Steps the float at 0x4f83f4. No shipped call.'),
    ('checkMonstersLeft', 'objects', 'objects::World::for_each_grid_object', 'partly documented', 'world_forEachGridObject',
     '1 if any living non-player creature is on the grid. The walk exists; the script predicate is the binder.'),
    ('forceMutexRelease', 'none', 'none', 'unknown', 'menuMutex_release',
     'Clears 0x4fe53c. No native menu mutex.'),
    ('addDeferedCall', 'script-binder', 'Variables::queue_deferred', 'documented', 'in-model',
     'Appends a name; the 65th is dropped. 0x144160.'),
    ('cutScene', 'none', 'none', 'unknown', 'cut_start',
     'res_find of the level lump and cut_start 0x19b4dc. No native cutscene player.'),
    ('postAction', 'script-binder', 'Variables::set_post_action', 'documented', 'in-model',
     'Copies the name to 0x86fa80. level_flow::State.post_action is the level-change copy, not this buffer. 0x143ee4.'),
    ('newWorldParameter', 'level-flow', 'level_flow::Pending::request', 'partly documented', 'net_closeLocalMenus',
     'First level= property, then the same next-world write, with no gate. orientation_from_props reads orientation=, not level=.'),
    ('putNPCInVehicle', 'none', 'none', 'unknown', 'Vehicle_attachNpcDriver',
     'Vehicle_attachNpcDriver 0x208af0. No native vehicle. No shipped call.'),
    ('putPlayersInVehicle', 'none', 'none', 'unknown', 'virtual:14',
     'Virtual slot 14 for the active player, then every other living player. No shipped call.'),
    ('entityRideVehicle', 'none', 'none', 'unknown', 'virtual:19',
     'Virtual slot 19 for a seat, then moves the entity. No shipped call.'),
    ('controlVehicle', 'none', 'none', 'unknown', 'in-model',
     'Stores a at +0x410 and b as a float at +0x2f0. No native vehicle. No shipped call.'),
    ('playersLoaded', 'script-binder', 'Variables::scene_dispatch', 'documented', 'in-model',
     '1 if any of the first g_numPlayers records has an object pointer. No shipped call.'),
    ('holdVehicle', 'none', 'none', 'unknown', 'Vehicle_setHold',
     'Vehicle_setHold 0x208b94. No shipped call.'),
    ('getPlayerVPosition', 'none', 'none', 'unknown', 'in-model',
     'Compares vehicle +0x90c and keeps +0x34c, times 128. No shipped call.'),
    ('getVPosition', 'none', 'none', 'unknown', 'in-model',
     'Vehicle +0x90c * 128. No shipped call.'),
    ('getPlayerVDir', 'none', 'none', 'unknown', 'in-model',
     '1 or -1 from the first qualifying vehicle. The 0 result is not reached. No shipped call.'),
    ('setupPlayerSel', 'none', 'none', 'unknown', 'in-model',
     'Empty, returns 0. No shipped call.'),
    ('startPlayerSel', 'none', 'none', 'unknown', 'in-model',
     'Empty, returns 0. No shipped call.'),
    ('playerSelRunning', 'none', 'none', 'unknown', 'playerSel_isRunning',
     'Returns 0x4fbbdc. No shipped call.'),
    ('objInPlayerTrig', 'none', 'none', 'unknown', 'virtual:17',
     '1 if the object is inside a Trigger that holds a player. No shipped call.'),
    ('setEntrance', 'level-flow', 'level_flow::State::entrance', 'documented', 'in-model',
     'Copies the name to 0x4f8468. State.entrance is that name. 0x142a94.'),
    ('hudResetFadeScreen', 'hud', 'none', 'partly documented', 'hud_setFade',
     'hud_setFade 0x1df5d0 stores 0 or 0x80. No native fade word.'),
    ('hudFadeScreen', 'hud', 'none', 'partly documented', 'hud_stepFade',
     'hud_stepFade 0x1df5ec. No native fade word. No shipped call.'),
    ('closestPlayerDist', 'script-binder', 'Variables::distance3', 'documented', 'in-model',
     'Horizontal distance to the nearest living player, 100000 if none. 0x14268c.'),
    ('hitPlayers', 'combat-runtime', 'combat_runtime::World::take_damage', 'partly documented', 'virtual:2',
     'Virtual slot 2 with the damage, then push speed +0x2e8 and direction +0x2e0. take_damage is the damage half.'),
    ('zeroPlayerMana', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Mana word +0xc0 = 0 for every player. 0x142450.'),
    ('showCompass', 'hud', 'hud_dynamic::compassLabel', 'partly documented', 'hud_setCompassTarget',
     'hud_setCompassTarget 0x1df668. compassLabel draws a label; it does not take an object position.'),
    ('showBust', 'hud', 'hud_dynamic::bustFadeStep', 'partly documented', 'hud_setBust',
     'hud_setBust 0x1dfaa0. bustFadeStep is the fade arithmetic, not the texture and text pair.'),
    ('getMaxPlayerHP', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     '1-based player, maximum hit points or -1. 0x1428fc.'),
    ('getHitPoints', 'script-binder', 'Variables::creature_dispatch', 'documented', 'in-model',
     'Integer hit points of the first creature of that name, else 0. 0x142944.'),
    ('setHitPoints', 'script-binder', 'Variables::creature_dispatch', 'documented', 'in-model',
     'Sets +0x228 on the first object if it is a creature. No shipped call.'),
    ('saveCheckPoint', 'level-flow', 'level_flow::checkpoint', 'partly documented', 'save_game',
     'save_game 0x218128 with (0, 0, 1). level_flow::checkpoint is the research snapshot, not that card write.'),
    ('loadCheckPoint', 'level-flow', 'level_flow::party_wipe', 'partly documented', 'deathTask_schedule',
     'deathTask_schedule 0x1ebd48. party_wipe is the in-act restore, not that schedule. No shipped call.'),
    ('trigger', 'level-flow', 'level_flow::Trigger::interact', 'partly documented', 'virtual:3',
     'Virtual slot 3 on up to 99 objects. Trigger::interact runs a level-flow trigger, not an arbitrary object slot.'),
    ('autoPropSetState', 'none', 'none', 'unknown', 'virtual:18',
     'Virtual slot 18 on objects with flag 0x10000000. Pieces::move is a world piece, not this slot.'),
    ('autoPropGetState', 'none', 'none', 'unknown', 'in-model',
     'State word +0x178 of the first auto prop of that name. No shipped call.'),
    ('preloadResource', 'level-flow', 'level_flow::Loader::load', 'partly documented', 'lump_load',
     'lump_load 0x173558. Loader::load reads one level, not an arbitrary named lump.'),
    ('setSaveInhibit', 'script-binder', 'Variables::scene_dispatch', 'documented', 'in-model',
     'Stores the value at 0x50605c. 0x1473b4.'),
    ('getSaveInhibit', 'script-binder', 'Variables::scene_dispatch', 'documented', 'in-model',
     'Returns 0x50605c. No shipped call.'),
    ('countQuestItems', 'items', 'items::parse_descriptor', 'unknown', 'inventory_countItemByName',
     'Count in player 0 bags only. No native bag walk.'),
    ('countPlayersAlive', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Returns 0x4f8420. 0x142220.'),
    ('countLiveObjects', 'objects', 'objects::NameTable', 'documented', 'in-model',
     'Objects of that name, at most 127, that are not dead creatures. No shipped call.'),
    ('networkMode', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'Returns the signed byte at 0x402791. 0x142214.'),
    ('getManaUsed', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Sign-extended halfword 0x4f85c8. No shipped call.'),
    ('getHealthUsed', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Sign-extended halfword 0x4f85ca. 0x142208.'),
    ('getLevelTimer', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'int(unsigned(0x4f85cc) * (1/60 truncated)). No shipped call.'),
    ('getEvil', 'script-binder', 'Variables::choice_get', 'documented', 'in-model',
     'Record 0 byte +0x4c1a, masked by the difficulty bit. 0x142044.'),
    ('setEvil', 'script-binder', 'Variables::choice_set', 'documented', 'in-model',
     'Non-zero sets that bit on the first player-count records. Zero does nothing. 0x142058.'),
    ('getMadeDecision', 'script-binder', 'Variables::choice_get', 'documented', 'in-model',
     'Decision byte +0x4c1b, same mask. 0x142010.'),
    ('setMadeDecision', 'script-binder', 'Variables::choice_set', 'documented', 'in-model',
     'Sets the bit. The argument is ignored. 0x142024.'),
    ('grantMission', 'script-binder', 'Variables::mission_set_complete', 'documented', 'in-model',
     'Completion bit at the current difficulty, all four records. 0x1420a4.'),
    ('getMissionComplete', 'script-binder', 'Variables::mission_complete', 'documented', 'in-model',
     'Completion bit of record 0. 0x142084.'),
    ('setMissionAvailable', 'script-binder', 'Variables::mission_set_available', 'documented', 'in-model',
     'Copies bit 0 of the argument onto the first player-count records. 0x1420d0.'),
    ('getMissionAvailable', 'script-binder', 'Variables::mission_available', 'documented', 'in-model',
     'Availability bit of record 0. 0x1420fc.'),
    ('grantGold', 'script-binder', 'Variables::mission_grant_medal', 'documented', 'run_reward_script',
     'Medal level 3. Raises the medal and runs firstBronze, firstSilver, firstGold. 0x14211c.'),
    ('grantSilver', 'script-binder', 'Variables::mission_grant_medal', 'documented', 'run_reward_script',
     'Medal level 2. 0x142140.'),
    ('grantBronze', 'script-binder', 'Variables::mission_grant_medal', 'documented', 'run_reward_script',
     'Medal level 1. 0x142164.'),
    ('getMedal', 'script-binder', 'Variables::mission_get_medal', 'documented', 'local_player_slot',
     'Medal byte of this machine\'s first local player. 0x142188.'),
    ('generateMonster', 'combat-runtime', 'combat_runtime::World::spawn_class', 'partly documented', 'ScriptGenerator_spawn',
     'Interns the class name, then ScriptGenerator_spawn 0x265fc4. spawn_class builds the own-machine classes, not that generator.'),
    ('monstersInTrigger', 'none', 'none', 'unknown', 'MonsterTrigger_count',
     'MonsterTrigger_count 0x1ed4e4 summed over that name. No native trigger census.'),
    ('sin1000', 'script-binder', 'core_math::sin16', 'documented', 'in-model',
     'int(sin16(angle) * 1000). sin16 is core_math.cpp. 0x141fb0.'),
    ('cos1000', 'script-binder', 'core_math::cos16', 'documented', 'in-model',
     'int(cos16(angle) * 1000). 0x141fe0.'),
    ('helpMessageActive', 'script-binder', 'Variables::menu_dispatch', 'partly documented', 'in-model',
     'Sign-extended byte 0x41b928. No shipped call, and no native writer of that byte.'),
    ('addHelpMessageF', 'hud', 'hud_dynamic::helpBox', 'partly documented', 'hud_showHelpMessage',
     'Formats two texts with wstr_format and shows them. The box geometry is native; the format and the open are not.'),
    ('revealMap', 'none', 'none', 'unknown', 'automap_revealAll',
     'automap_revealAll 0x16a760. Level textures decode automap tiles; they do not mark cells seen.'),
    ('showOnMap', 'script-binder', 'Variables::menu_dispatch', 'documented', 'in-model',
     'Sets or clears creature flag bit 43, up to 99 creatures. 0x141e98.'),
    ('initScriptSetParams', 'creature-ai', 'none', 'partly documented', 'Creature_scaleStats',
     'Creature_scaleStats 0x1185d8 on the selected object, each argument / 100. No native scale.'),
    ('setCreatureParams', 'creature-ai', 'none', 'partly documented', 'Creature_scaleStats',
     'Same scale for every creature of that name. 0x1476c0.'),
    ('explodePotionsOnly', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Sets 0x4f7128. 0x1433a8.'),
    ('runMedalSuccess', 'hud', 'hud_dynamic::medalPrompt', 'partly documented', 'hud_drawMessageBox',
     'Draws the result and reads the medal player pad. medalPrompt is the prompt record, not this draw or the pad test.'),
    ('runMedalFail', 'hud', 'hud_dynamic::medalPrompt', 'partly documented', 'hud_drawMessageBox',
     'Same flow as runMedalSuccess with the failure box. 0x141c00.'),
    ('setAlternateDeath', 'level-flow', 'level_flow::party_wipe', 'partly documented', 'in-model',
     'Sets 0x4f712c. party_wipe returns Wait for alternate death when the owner says so; it does not set this byte.'),
    ('dropItem', 'items', 'items::parse_descriptor', 'partly documented', 'loot_spawnNamedItem',
     'loot_spawnNamedItem 0x100ba0 at the object. Native loot callbacks record a spawn; they are not this call.'),
    ('selectDropItem', 'items', 'items::parse_descriptor', 'partly documented', 'loot_spawnNamedItem',
     'Same spawn at the selected object. 0x147860.'),
    ('findDistance', 'script-binder', 'Variables::distance3', 'documented', 'in-model',
     'Horizontal distance, 0 if either name is missing. 0x1478c8.'),
    ('setContainerProps', 'none', 'none', 'unknown', 'in-model',
     'AutoContainer, which 1, bit 3 of +0x124. No native container.'),
    ('setWaveDetail', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'Stores 0 or 1 at 0x4f7130. 0x14176c.'),
    ('demoRunning', 'script-binder', 'Variables::utility_dispatch', 'documented', 'in-model',
     'Constant 0. 0x141764.'),
    ('removeAllItems', 'items', 'items::parse_descriptor', 'unknown', 'inventory_removeItem',
     'Empties the medal player\'s three bags by repeated inventory_removeItem. No native bag.'),
    ('savePlayer', 'level-flow', 'level_flow::PlayerRecord', 'partly documented', 'save_playerCopy',
     'Copies the medal player\'s record and sets 0x4f85c0. PlayerRecord::persistent is an owner blob, not that copy.'),
    ('restorePlayer', 'level-flow', 'level_flow::PlayerRecord', 'partly documented', 'save_playerCopy',
     'Copies the saved record back, sets the signed16 at 0x4f7194 to 240, rebuilds the alive list.'),
    ('piercePlayerEar', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Sets record +0x4c26 for one player or for all. 0x145610.'),
    ('playerAdjustStat', 'items', 'none', 'unknown', 'inventory_onStatPoint',
     'stat 4..8. player -1 calls inventory_onStatPoint; any other player sends inventory message 6. No native stat spend.'),
    ('giveFullHealth', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Hit points to maximum for every player. 0x146950.'),
    ('setPlayerFlag', 'script-binder', 'Variables::player_set_flag', 'documented', 'in-model',
     'Bit of record +0x4c28, modulo 32, one byte so bits 8..31 change nothing. 0x1416d4.'),
    ('getPlayerFlag', 'script-binder', 'Variables::player_get_flag', 'documented', 'in-model',
     'Reads that byte. 0x1416fc.'),
    ('clearAllSkills', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Clears the medal player\'s skill slots. +0x4a85 is set to 1. 0x1458e0.'),
    ('isClericOrWizard', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Class byte +0x50 is 1 or 4, for a player index in range. 0x1465cc.'),
    ('refillPlayerMana', 'script-binder', 'Variables::interaction_dispatch', 'documented', 'in-model',
     'Mana = maximum for every player. 0x142494.'),
    ('removeAllWeapons', 'items', 'items::parse_descriptor', 'unknown', 'inventory_removeItem',
     'Empties bag 0 of the medal player and clears three equipped pointers. No native bag.'),
)


def commands():
    """Every table name, in table order, as a dict."""
    by_name = {row[0]: row for row in _ROWS}
    missing = [name for name in N.NATIVE_NAMES if name not in by_name]
    extra = [row[0] for row in _ROWS if row[0] not in N.NATIVE_NAMES]
    if missing or extra or len(_ROWS) != len(N.NATIVE_NAMES):
        raise RuntimeError('composition rows missing %s extra %s' % (missing, extra))
    out = []
    for index, name in enumerate(N.NATIVE_NAMES):
        _name, subsystem, native, status, seam, note = by_name[name]
        if subsystem not in SUBSYSTEMS or status not in STATUSES:
            raise RuntimeError('%s has subsystem %s status %s' % (name, subsystem, status))
        out.append({
            'index': index, 'name': name, 'subsystem': subsystem, 'native': native,
            'status': status, 'seam': seam, 'note': note,
        })
    return out


def published_counts(path=SCRIPT_MD):
    """Call counts from the tables in docs/script.md section 3. Counts only."""
    with open(path, 'r', encoding='utf-8') as source:
        text = source.read()
    start = text.index('## 3. The built-ins')
    end = text.index('### Fields the built-ins touch')
    body = text[start:end]
    found = {}
    for line in body.splitlines():
        match = re.match(r'\| \d+ \| `([A-Za-z0-9]+)` \|.*\| (\d+) / (\d+) \|$', line)
        if not match:
            continue
        name, calls, levels = match.group(1), int(match.group(2)), int(match.group(3))
        if name in found:
            raise RuntimeError('duplicate published row %s' % name)
        found[name] = (calls, levels)
    missing = [name for name in N.NATIVE_NAMES if name not in found]
    if missing:
        raise RuntimeError('docs/script.md has no call count for %s' % ', '.join(missing))
    return found


def ranked(counts=None):
    """Commands a playable level should wire next.

    A shipped call of a documented effect outranks a partial one, which outranks
    an unknown one. Commands no shipped script calls stay at the bottom.
    """
    weight = {'documented': 3, 'partly documented': 2, 'unknown': 1}
    counts = counts if counts is not None else {name: pair[0] for name, pair in published_counts().items()}
    rows = []
    for command in commands():
        calls = int(counts.get(command['name'], 0))
        score = calls * weight[command['status']] if calls else 0
        rows.append((score, calls, command))
    rows.sort(key=lambda item: (-item[0], -item[1], item[2]['index']))
    return rows


def markdown_table(counts=None):
    counts = counts if counts is not None else {name: pair[0] for name, pair in published_counts().items()}
    lines = [
        '| # | Command | Calls | Effect | Native function | Seam |',
        '|---:|---|---:|---|---|---|',
    ]
    for command in commands():
        lines.append('| %d | `%s` | %d | %s | `%s` | `%s` |' % (
            command['index'], command['name'], int(counts.get(command['name'], 0)),
            command['status'], command['native'], command['seam']))
    return '\n'.join(lines)


def main(argv):
    rows = commands()
    counts = published_counts()
    if argv[:1] == ['--md']:
        print(markdown_table({name: pair[0] for name, pair in counts.items()}))
        return 0
    by_status = {}
    for row in rows:
        by_status[row['status']] = by_status.get(row['status'], 0) + 1
    calls = sum(pair[0] for pair in counts.values())
    used = sum(1 for pair in counts.values() if pair[0])
    print('commands %d' % len(rows))
    for status in STATUSES:
        print('%s %d' % (status, by_status.get(status, 0)))
    print('published calls %d' % calls)
    print('published commands used %d' % used)
    print('published commands never called %d' % (len(rows) - used))
    print('rank')
    for score, call_count, command in ranked({name: pair[0] for name, pair in counts.items()})[:15]:
        print('%4d  %s  %s  %s' % (call_count, command['name'], command['status'], command['subsystem']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
