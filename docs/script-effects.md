# Script commands that touch combat, AI, audio and the HUD

Status 2026-10-20, SLUS-20973 v2.00. Branch `t3/research-script`. The handler for each command is still `tools/ref_natives.py`, and the 191-row composition table is still `docs/script-composition.md` (81 documented, 70 partly documented, 40 unknown). This document is the callee those handlers reach. `tools/ref_script_effects.py` is the same contract as code. `tools/difftest_script_effects.py` runs the original functions in `tools/ee_emu.py`.

Call counts are the shipped-script census in `docs/script.md` section 3. Counts only. Commands with zero disc calls are included when they reach a body a shipped command also reaches.

## Evidence

- **Executed.** The function ran under `tools/ee_emu.py` and the reference matched its stores, the arguments of the calls it makes, and `v0`. A callee that was stubbed is named here and was not entered.
- **Observed.** A direct run whose stores are listed, but which the script-wrapper difftest stubs so those stores are not part of that wrapper's byte compare.
- **Inferred.** A contract already executed on another research branch. The commit is named. This round did not re-enter that body.
- **Unknown.** No executed body for that call.

The handler's return is the script-visible result. Almost every handler below returns 0 and discards the callee's `v0`. The exceptions are `hudFadeScreen`, which returns `hud_stepFade`, and `runMedalSuccess` / `runMedalFail`, which return 0 while their gate is shut and otherwise the medal pad result.

None of the bodies executed in this file draw the shared seed at 0x404464 or the cosmetic seed at 0x404460. The cosmetic seed is inside `sound_playOnObject` (not entered). One shared draw is inside `creature_buildElementDamage` (not entered; `docs/spec/skills-01-34.md`).

## Spawn

### `generateMonster` — 136 calls — partial

Handler `0x1473d4` (`s generator, s className`). Interns the class name in the 24-byte table at 0x5d32c8 (count byte 0x4f8409), then calls `ScriptGenerator_spawn` 0x265fc4 for every object of that generator name whose class is ScriptGenerator. Handler returns 0.

**Executed** `ScriptGenerator_spawn` 0x265fc4 `(generator, className)`:

- Angle is the signed half at generator +0x38 minus 0x4000. Raw half 0x100 becomes angle 0xffffc100.
- Props are the word at +0x2c.
- The position passed to the factory is the three floats at +0x10, +0x14, +0x18 and a zero fourth word. A nonzero word at +0x1c is not copied.
- Calls `world_createObject` 0x14f6c8 `(className, position, angle, props)`. **Unknown** here: the factory is stubbed. It is not `combat_runtime::World::spawn_class` (`t3/research-combat` `2980af1`, `docs/combat-runtime.md`). Constructors reached from the factory may draw the shared seed. That draw was not executed on this path.
- No object: no stores. `v0` is 0x01000000 (the `lui` in the failure delay slot). That is not 0 and it is not the generator pointer.
- An object: creature cflags at +0xa8 get bit 24 (`| 0x1000000`, high bits kept). The class-name pointer is stored at +0x34. Virtual slot 0 is called with the vtable pointer at object +0x48, not with the object. Then `Skeleton_typeinfo` 0x3cc62c is called without a reloaded argument, so its entry `a0` is whatever slot 0 left. `rtti_typeInfoEquals` 0x3b1250 compares slot 0's return with the typeinfo return. If they are equal, slot 27 is called with state 23 (0x17). The base slot 27 does not write `v0`, so a Skeleton whose slot 27 is the base returns the function pointer 0x3c2688. If the type test fails, the flag and the name are still stored and `v0` is 0.

**Observed** on a direct call of `Skeleton_typeinfo`, three different entry arguments (0, a vtable pointer, an unrelated pointer): return 0x908e20, no seed movement, and the same eight stores, which initialise the Skeleton, Creature and GameObject type-info nodes.

| Address | Word stored |
|---|---|
| 0x564318 | 0x532210 |
| 0x56431c | 0x51df78 |
| 0x908138 | 0x564318 |
| 0x908130 | 0x530150 |
| 0x908134 | 0x51df48 |
| 0x908e28 | 0x908130 |
| 0x908e20 | 0x54c168 (type name Skeleton) |
| 0x908e24 | 0x51df48 |

Two of its callees, 0x3c2608 and 0x3c7e10, are passed that entry argument. The eight stores do not depend on it. The spawn difftest stubs 0x3cc62c, so those stores are not in the wrapper compare. The wrapper's decision uses only the return.

## Creature values and stats

### `setMonsterVal` — 114 — executed

Handler `0x144550` `(s name, i which, i value)`, and `selectSetMonsterVal` `0x144514` `(i which, i value)` on the selected object (9 calls). `script_applyMonsterVal` 0x144494. A creature only.

- which 1, 2, 3, 5: low 16 bits stored at +0x3ac, +0x3ae, +0x3b0, +0x3c4.
- which 4: virtual slot 34. **Executed** base 0x3c2708: the low 16 bits become a float at +0x3c0 (`from_int`). 0x1abcd becomes the pattern 0x472bcd00. `v0` is unchanged.
- Any other which stores nothing.

`setMonsterRange` `0x1449b4` `(s name, i range)` is the same slot 34 when `range > 0`. Zero disc calls. Handler returns 0. No seed.

### `setCreatureParams` — 56 — executed

Handler `0x1476c0` `(s name, i x5)`. `initScriptSetParams` `0x147640` `(i x5)` is the same call on the selected creature (13 calls). Each of the five integers is divided by 100 (`0x3c23d70a`) and passed in `f12`..`f16` to `Creature_scaleStats` 0x1185d8.

**Executed.** No calls. Returns 0. Store order is armour, hit points, maximum hit points, damage low, damage high, attack rating, experience:

| Field | Address | Rule |
|---|---|---|
| armour | +0xe4 s16 | truncated product; 0, a negative, or a low half with the sign bit becomes 1 |
| hit points | +0x228 float | `cvt.s.w(cvt.w.s(product))`, toward zero |
| maximum hit points | +0x22c float | same |
| damage low, high | +0xd0, +0xd2 s16 | same floor as armour |
| attack rating | +0xd4 s16 | truncated low 16, no floor (a negative stays) |
| experience | +0xd8 float | same truncation as hit points |

100 scaled by 0.5 stays the pattern 0x42480000. 100.5 scaled by 0.5 is stored as 50 (0x42480000), not 50.25. No seed. The handler returns 0.

## AI state

Base slot 27 is 0x3c2688. **Executed:** it stores the low 16 bits at +0x232 and does not write `v0`. It does not run the filter and it does not clear timers.

A derived set-state calls `Creature_filterState` 0x10a9c0 first. That filter is **Executed** in this repository (`tools/ref_creature.py`, the creature difftest). `t3/research-anim` `5694ae3`, `docs/spec/creature-animation-dispatch.md` section 5.4, stubbed the filter and then recorded the clip the class starts. Six classes keep the base slot 27. The class bodies were not re-entered here. **Inferred** for the clip; **Unknown** for any class whose slot 27 is not the base, beyond the filter result below.

Filter results the script commands rely on, from `ref_creature.filter_state`:

- State 0 while the root timer is -1 stays 0. The root timer is not cleared. The target handle at +0x234 is cleared because the result is 0.
- State 4 with a root timer and a target becomes 5. The same request with no target becomes 0.
- State 0x14 clears the halfwords at +0x31c, +0x318, +0x314 and +0x31a, then stays 0x14.

No seed in the base store or in these filter results.

### `stopFollowingPath` — 45 — partial

Handler `0x1450ec`. `selectStopPath` `0x1451f0` is the same on the selected object (11 calls). A creature that has cflags bit 27: activity radius +0x3c4 becomes 0x47e (1150), bit 27 is cleared, the three position words are copied to +0x3b4, and, unless the AI state is already 0x14, slot 27 is called with 0. Handler returns 0. The base store is executed. The derived set-state is the animation table.

### `rootMonster` — 16 — partial

Handler `0x14433c`. A creature whose AI state is not 0x14 gets root timer +0x314 = -1 and slot 27 with 0. State 0 is not redirected to 5, and the filter does not clear the root timer. Handler returns 0. `unRootMonster` only clears the timer; it does not call slot 27.

### `killMonster` — 15 — partial

Handler `0x144a84`. A creature that is not already dead (flag 0x8): flags become `flags | 0x2009` (0x2000, dead, no-collide), hit points +0x228 become 0, slot 27 is called with 0x14. On a derived set-state the filter clears the four timers before the class death clip. The base store does not. Handler returns 0. No seed in the handler.

### `followPath` — 28 — partial

Handler `0x144fc8`. `selectFollowPath` `0x145090` is the same on the selected object (3 calls). A creature that does not already have cflags bit 27: bit 27 is set, activity radius becomes 44000, and `obj_runEveryFrame` is called with the object. Handler returns 0. The flag and the radius are the handler, executed in the round-1 handler difftest. **Unknown:** `obj_runEveryFrame` was not entered.

### `followPlayer` — 0 — executed

Handler `0x144e78`. Sets cflags bit 23, then the same `Creature_setCharm(creature, -1, 0)` as `charmMonster`. No disc calls.

## Charm, weapon, damage, destruction

### `charmMonster` — 20 — executed

Handler `0x14429c` `(s name)`. `Creature_setCharm` 0x1189f0 `(creature, frames, team)` with frames -1 and team 0.

**Executed.** No seed.

- Charm timer +0x312 already -1: return -1, no stores.
- Object flag 0x20 clear: return 0, no stores.
- Object flag 0x40 set (a player): return `flags & 0x20`, no stores.
- Otherwise: team byte at +0x310, frame half at +0x312, `handle_clear` 0x1a1698 of the target at +0x234 with -1, then the word at +0x234 is stored as 0. The return is `handle_clear`'s `v0`. The handler discards it and returns 0.

**Unknown:** `handle_clear` of a live handle. The script difftest follows it on a null handle, which stores nothing.

### `setWeaponType` — 10 — partial

Handler `0x1448e4` `(s name, i type)`. For each creature whose weapon object at +0x50 is nonzero, virtual slot 8 of that weapon object is called with `(0, type as a byte)`. Handler returns 0.

**Executed** chain, with `creature_buildElementDamage` 0x1176e0 stubbed:

- `WeaponObject_slot8` 0x3c17e8 reads the object at holder +4 and calls slot 8 of that object's vtable (function pointer at table +68), type masked to a byte.
- `Weapon2_setElement` 0x3c2238. which 0 (the script's value) calls the element function twice, destinations `this+0x50` and `this+0xe0`, source `this+4`. which 1 calls only the first and leaves `v0` as 2, the compare immediate. which 2 calls only the second. which 0 and which 2 return the element function's `v0`.
- `WeaponShield_slot8` 0x3c2500 makes one element call when which < 2, destination `this+0x50`. which 2 makes no call and returns 0.

**Inferred** for the element body: `docs/spec/skills-01-34.md` records one shared draw and the entry formula. That body was not entered here, so the draw was not taken on this path. No seed in the slot-8 chain itself.

### `hitPlayers` — 11 — partial

Handler `0x1424dc` `(s object, i radius, i damage, i push)`. Every living player nearer than `radius` takes virtual slot 2 with no attacker and the damage in `f12`, then push speed at +0x2e8 and an `atan2_16` angle at +0x2e0. Handler returns 0. The distance and the push stores are the handler.

**Inferred:** slot 2 on a player is `Player_takeDamage` 0x1b5330, and on a creature `Creature_takeDamage` 0x116638, both executed on `t3/research-combat` `2980af1` (`docs/combat-runtime.md`, the slot-2 row). Not re-entered here. No seed in the handler's own push stores. Whether `Player_takeDamage` draws is that combat contract.

### `deleteMonster` — 33 — partial

Handler `0x144b44`. Virtual slot 1 with argument 3. Handler returns 0.

`reapEnemies` `0x1453e4` (1 call) uses the same slot and the same argument for a dead non-player creature inside a box of ±60000. The three pointer-type names it also tests match nothing (`docs/script.md`).

**Executed** `Creature_dtor` 0x117128 `(creature, flags)` on an empty spell list, return 0. Sets the vtable at +0x48 to 0x50cc58. `iter_begin` 0x1a1a48 of the list at +0x364, then `iter_end` 0x1a1ae8. Five `handle_clear` 0x1a1698 calls, of +0x364, +0x360, +0x2e4, +0x238 and +0x234, each with second argument 0 when those functions actually run. Effect-attachment destructor 0x202500 `(creature+0x320, 2)` (`docs/creatures.md`). `AnimState_dtor` 0x171098 `(creature+0x114, 0)` and `GameObject_dtor` 0x14cf90 `(creature, 0)` are stubbed. Flag bit 0 calls `pool_free` 0x150470. `deleteMonster` passes 3, so a class that chains to this destructor does free. The free is this destructor's own `pool_free`; `GameObject_dtor` is called with flags 0.

On a zeroed creature the only store is the vtable word. **Unknown:** a populated spell list (each node would take slot 1 with 3), `handle_clear` of a live handle, the two stubbed destructors, and a class destructor that does not chain to 0x117128.

## HUD

### `setInfo` — 95 — executed

Handler `0x14318c` `(s textKey)`. `text_lookup`, then `hud_showMessage` 0x1d92a0 `(text, 180, -1, 0)`. Handler returns 0.

**Executed** setter. Slot -1 skips `net_isLocalSlot` 0x13e150. Any other slot returns 0 when that test is 0, with no stores. Force 0 while `g_localMenuOpen` 0x41b69d is nonzero returns that menu byte and stores nothing. Otherwise `wstr_copy` 0x19e854 into 0x86ab78, the frame half at 0x4f66e0, and the force byte at 0x4f66e2. Success `v0` is 0x4f0000, the `lui` of the buffer. The handler returns 0. No seed. The copy function is stubbed; the destination, the frame count and the force byte are the stores.

The draw is **Inferred** from `t3/research-ui` `3e39392`, `docs/hud-dynamic.md` (message draw). The setter described there is this function.

### `addHelpMessage` — 65 — executed

Handler `0x1431d8` `(s titleKey, s bodyKey)`. Two lookups, then `hud_showHelpMessage` 0x1d9830 `(slot -1, title, body)`. Handler returns 0.

`addHelpMessageF` `0x143270` (7 calls) formats each looked-up text with its number into a stack buffer, copies those to the static buffers 0x5d3048 and 0x5d3088, and calls the same setter with those two pointers. Handler returns 0.

**Executed** setter. An explicit slot other than -1 that fails `net_isLocalSlot` returns 0. Offline (`g_networkMode` 0x402791 is 0) opens without a scan. Online, the alive list at 0x4f8440 (count 0x4f8420) is walked; the first local slot gets `hudmsg_sendMenuState` 0x1de0dc `(slot byte, 1, 0)` and the box opens. If none is local, nothing opens and `v0` is 4 times the alive count. Opening calls `res_find` 0x17365c `(0x53c3b8, 0x53c3c0)`, `sound_playOnObject` 0x214230 `(resource, 0, f12 = 1.0)`, `sound_setPlaysWhileFrozen` on that handle, and `ui_startPulse` 0x320ea4 `(0)`, then stores 1 at 0x41b928, the title pointer at 0x86aa64, the body pointer at 0x86aa68, and 90 at 0x4f66cc. Return is 90, which the handler discards.

The frozen-flag body is executed (below). **Unknown** here: `sound_playOnObject`. The help-box draw is **Inferred** from `help_task` 0x1dcc78 in `docs/hud-dynamic.md`. No seed in the setter. The playback call is where the cosmetic seed would be drawn, and it was stubbed.

### `showBust` — 31 — executed

Handler `0x142864` `(s texture, s textKey, i a, i b)`. Lookup, then `hud_setBust` 0x1dfaa0. Handler returns 0.

### `showCompass` — 3 — executed

Handler `0x1427b4` `(s object, s textKey)`. No null check. The object's three position words and the looked-up text go to `hud_setCompassTarget` 0x1df668. Handler returns 0.

Both setters share one gate. The first failing value is the return, and nothing is stored. Order: `g_hudSuppressed` 0x4f66a8, `g_localMenuOpen` 0x41b69d, camera mode at `g_localCamera` 0x4f8450 +0x34 compared with 1 (a null camera faults), `g_loadscreenActive` 0x506094, `g_menuOpenFlag` 0x41b4f8. Success `v0` is 0x870000.

**Executed** compass: three position words at 0x86a8f0. The fourth word is not written. `wstr_copy` to 0x86aaf0. Byte 5 at 0x4f66d5.

**Executed** bust: `strcpy` 0x3b868c of the texture name to 0x4f6b48, `wstr_copy` to 0x86aab0, byte 5 at 0x4f66d4, the two integers at 0x86ab30 and 0x86ab34. The draw reads 0x86ab34 as the maximum (**Inferred**, `docs/hud-dynamic.md` section 7). No seed.

### `hudResetFadeScreen` — 0 — executed

Handler `0x14277c` `(i on)`. `hud_setFade` 0x1df5d0 stores 128 or 0 at `g_hudFade` 0x4f66ac. Turning it on returns 128. Turning it off leaves `v0` unchanged. The handler returns 0 either way. No disc calls. No seed.

### `hudFadeScreen` — 0 — executed

Handler `0x14279c` `(i delta)`. This handler returns `hud_stepFade` 0x1df5ec. The delta is added to 0x4f66ac and clamped to 0..128. The clamped word is what the byte compare uses. A nonzero result calls `ui_drawRect` 0x17bd30 `(0, 0, 640, 448, layer 6, colour = fade << 24)`. 40 + 100 clamps to 128. 128 - 16 is 112. 5 - 10 is 0 and draws nothing. No disc calls. No seed.

### `runMedalSuccess` — 30 — partial

Handler `0x1417a4`. `runMedalFail` `0x141c00` (10 calls) is the same gate and the same pad tail with the failure box. Both were re-run in this round's handler difftest (24 of 34 blocks, and 14 of 21). Return 0 while the gate is shut; otherwise the medal player's confirm restarts the level and cancel opens the mission menu, and either returns 1.

**Unknown:** `hud_drawMessageBox` was not entered. The prompt measured by the handler is a different function from the medal prompt 0x1e0698 named in `docs/hud-dynamic.md`.

## Audio

### `soundSequence` — 27 — partial

Handler `0x143684` `(s lump, s name)`. `res_find`, then `sound_playOnObject` 0x214230 `(resource, 0, f12 = 1.0)` even when the resource is 0, then `sound_setPlaysWhileFrozen` 0x216ad0 on the handle. Handler returns 0.

**Executed** frozen flag. A handle of -1, or one whose bit 15 is clear, stores nothing and returns -1. Otherwise slot `handle & 0xff` gets byte 1 at `g_soundSeqs` 0x871a68 + slot * 0x4c + 0x3b. Handle 0x8003 stores at 0x871b87 and returns the byte offset 0xe4. No seed.

**Unknown** here: `sound_playOnObject`. **Inferred** playback, including the cosmetic seed, is `t3/research-audio` `6b08886`, `docs/audio-playback.md`. Not re-entered.

`sound` `0x1435e0` (0 calls) is `sound_playSample` 0x214230's neighbour: `res_find`, and when the resource is nonzero `sound_playSample(resource, 0)` with volumes 1, 1, 0. **Unknown** here. The named-sample contract is the same audio document.

### `setCFlag` — 18 — partial

Handler `0x144714` `(s name, i bit, i on)`. `selectSetCFlag` `0x1446d0` is the same on the selected creature (0 calls). `script_applyCFlag` 0x1445fc changes only bit 0 and bit 26.

Bit 0, on or off, calls `creature_startBossMusic` 0x1192b0. Clearing bit 0 while bit 31 is set also clears bit 31 and the boss meter words 0x41b6a0 and 0x41b6a4. Bit 26 is the friendly bit, with no music call. Any other bit returns without a store. Handler returns 0.

**Executed** `creature_bossMusicName` 0x10dbe0. A null creature or a null type name at +0x34 returns 0. Otherwise the first of the eleven rows whose type text matches, and whose property text matches when the row has one. The property is `obj_getPropStr` 0x14f4c0 `(creature, 0x52fab0, 0)`. The compare is `libc_strcasecmp` 0x3b81a0, followed and not recorded as a script call. No match returns 0. The return is the track pointer, not a copy of the text. The type, property and track addresses are the rows in `tools/ref_script_effects.py`. The names at those addresses are in `docs/audio-playback.md` on `t3/research-audio` and are not copied here. No seed.

**Executed** `creature_startBossMusic` 0x1192b0. No name: no further call, stream 2 untouched, return 0. A name: `audio_streamStop` 0x211ce8 `(2)`, then `music_playGlobal` 0x2110e0 `(name, 0x103)`, and that call's `v0` is returned. The handler discards it.

**Inferred:** the boss override and `music_playGlobal` were executed on `t3/research-audio` `6b08886`. Not re-entered here.

### `startMusic` — 0 — executed

Handler `0x146b68` `(s name)`. `music_playLevel` 0x215f48 `(name, flags 3)`. No disc calls.

**Executed.** Volume at 0x4f8944 compared with 0x3d4ccccc (`c.olt`; equal is open). Below the gate: no calls, `v0` stays 0x500000. Otherwise `f12 = scalar(0x4f894c) * volume * 0x3f480000`, `audio_setChannelVolume` 0x216690 `(channel 2, f12)`, then `stream_playLevel` 0x215fc8 `(2, name, flags | 0x22)`. Flags 3 become 0x23. No seed in this function. The two callees are stubbed. **Inferred** for their bodies: `docs/audio-playback.md`. The channel argument is first and the volume is `f12`, which matches that document.

### `endMusic` — 0 — executed

Handler `0x146be4`. `stream_queueStop` 0x211338 `(2)`. No disc calls.

**Executed.** Stream 2's count word is 0x877158. Fewer than 8 markers: one stop is appended and the new count is returned. The marker stores, relative to `g_streams` 0x876c10 plus the stream stride plus `count * 48`, are byte 0 at +64, word 2 at +0x6c, and zeros at +80, +88, +92 and +84, then the incremented count. A full queue stores nothing and returns `count * 3` (8 returns 24). Count 0 returns 1. No seed.

### `startAudio` — 0 — partial

Handler `0x146ba4` `(s name)`. `stream_playLevel` 0x215fc8 `(1, name, flags 2)`. No disc calls. Handler returns 0. **Unknown** here; the level-stream body is the audio document.

### `healPlayer` — 0 — partial

Handler `0x1468ac`. `res_find` of the heal sample, `sound_playOnObject` on player 0's object at volume 1, then hit points copied from maximum for every player whose hit points are above 0. Handler returns 0. The refill is the handler. **Unknown** here: the playback call. No disc calls. No seed in the refill.

### `playGotItemSound` — 3 — partial

Handler `0x1464e8`. Clamps `g_scriptActivePlayer` to 0..1 and stores that clamp. The slot passed to `player_voice` 0x1b7ba8 is the value from before the clamp, except when there are two or more players and that player's hit points are not above 0: then the other of 0 and 1. The voice kind is 9. Handler returns 0. **Unknown:** the voice body was not entered. `docs/script.md` P7 is the handler rule, already executed in the handler difftest.

## What remains, by disc calls

A command marked executed above can be wired from this contract. These calls are still another body:

| Calls | What is still unentered |
|---:|---|
| 147, 61, 61, 36, 10 | Bag walks: `removePlayerItem`, `playerHasItem`, `countQuestItems`, `onePlayerHasItem`, `givePlayerItem`. `givePlayerItem` also reaches item construction, which draws the shared seed (`docs/spec/skills-01-34.md`). Not entered this round. |
| 136 | `world_createObject` 0x14f6c8, the factory `generateMonster` calls. Class constructors behind it. |
| 45, 16, 15, 11 | Derived slot 27 (stop path, root, kill, select-stop). The filter result is executed here. The clip is `t3/research-anim` `5694ae3`. |
| 33, 1 | Class destructors that do not chain to `Creature_dtor`, a non-empty spell list, `handle_clear` of a live handle, `AnimState_dtor`, `GameObject_dtor`. |
| 30, 10 | `hud_drawMessageBox` inside `runMedalSuccess` and `runMedalFail`. |
| 28, 3 | `obj_runEveryFrame` inside `followPath` and `selectFollowPath`. |
| 27, 3, 0 | `sound_playOnObject` (`soundSequence`, the help chime, `healPlayer`) and `player_voice` (`playGotItemSound`). Cosmetic seed stays inside playback. |
| 18, 0 | `music_playGlobal` and `audio_streamStop` bodies. The script's arguments are executed. The bodies are `t3/research-audio` `6b08886`. |
| 11 | `Player_takeDamage` / `Creature_takeDamage` for `hitPlayers`. Executed on `t3/research-combat` `2980af1`, not re-entered. |
| 10 | `creature_buildElementDamage` for `setWeaponType`, including its one shared draw. |
| 0 | `sound_playSample` (`sound`) and `stream_playLevel` (`startAudio`, and the call `startMusic` makes after the gate). |

`tools/vu1_emu.py` is not on this path. Nothing was run on a console or in the Play! emulator.
