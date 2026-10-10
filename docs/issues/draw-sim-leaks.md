# State written by one machine's screen code and read inside the lockstep tick

Two desyncs of one kind were found by hand in `docs/issues/kill-loot-xp.md`: K1 (a flag only
the HUD draw code writes gates `Player_interact`) and K2 (`Player_usePotion` branches on the
local-menu flag). FINDINGS D26 (the menu input lockout) is a third. This document is the
systematic search for the rest of that kind: state that only drawing, HUD, menu or raw
controller code writes, and that code inside the simulation tick reads.

Everything here was read from the executable (decompile, disassembly, the tool described
below); nothing was run on a console or emulator. That still holds for what this document
claims: the project's live game (the Play! emulator, not a PlayStation 2 and not PCSX2;
`FINDINGS.md`, "Run on the live game", rows V1–V8; `docs/issues/live-rig.md`) has run one
machine only, and none of the leaks below needs fewer than two. The input-delay rule has
been executed with two interpreter instances (`docs/spec/net-wire.md` section 14). Claims are **Observed** (read at the
address given), **Inferred** or **Unknown**. Patch proposals are **untested**; no test
patch has been run on a live game.

## Result in short

- `tools/drawsim.py` lists **271** globals written by presentation-only code and read by
  simulation code (813 with its loose tier), and 62 object-field store sites in draw
  functions. It rediscovers 0x41b818, 0x41b69d and 0x41b4fc.
- All 271 were triaged: 162 by group (the reader is rendering, audio, card or transport
  plumbing), 109 one by one (47 topics). All 62 field sites were read.
- **Real, already on the ledger:** K1, K2, D26, D12–D16 (status counters), D31 and the water
  spout (run-list membership decided by drawing), D34 (the pose cache filled by drawing —
  being traced elsewhere, only noted here), E9 (a notice box closed in a draw task runs the
  pending post-action script), the jump-gate drawn flag, card state read by the save point
  (B9–B11), scripts run from draw code, dialog state, the debug file.
- **Real, new:**
  - **U1** — leaving the pause menu's option list with any option changed rewrites the
    button maps of all four player slots from this machine's own saved configuration, with
    no network test. Needs a player with non-default controls.
  - **U2** — the lockstep mission menu skips the chooser's pad test on the chooser's machine
    while that machine's pause menu is open (the same pattern as the jump-gate menu).
  - **U3** — D26 has a second in-tick route (medal levels) and two routes that look like
    one but are not (respawn, message handlers).
- **None of them happens on every run.** What the list does show is a family — *press a
  button, then open a local screen before the press has been simulated* (K1, K2, U2, the
  jump-gate menu) — whose window is the input delay. At the minimum delay the two presses
  must fall in one sample; after any stall of half a second the delay is about 35 frames for
  15–30 s (FINDINGS L11), and "drink a potion, then open the inventory" or "pick something
  up, then hold the D-pad" within half a second is ordinary play. See "Ranking".

| # | State | Per-machine writer | Simulation reader | Kind | Rank in a DRUNARE boss fight |
|---|---|---|---|---|---|
| K2 | `g_localMenuOpen` 0x41b69d, `g_itemListCells` 0x4ebbb0 | `menu_openInventory` (from `hud_run`, raw pad), inventory resource poll (draw task) | `Player_usePotion` 0x1b9fcc, 0x1ba3ac | Observed; known | 1 |
| K1 | `g_spellSelectorHeld` 0x41b818 | `hud_spellSelect` (HUD draw, raw D-pad) | `Player_run` 0x1a5c08 | Observed; known | 2 |
| D26 / U3 | `g_menuInputLockout` 0x41b4fc | `inventory_close` 0x1c52dc, `shop_close` 0x1d0b48 when reached inside a tick on the one machine that has the menu open | `Player_takeDamage` 0x1b53d4, `Player_run` 0x1a5ba8 | Observed; known, routes extended | 3 |
| U1 | button-mask tables 0x41b980…0x41ba30 | `config_commitOptions` 0x1e6650 (pause menu, draw task) | `Player_run`, `Player_interact`, `Player_weaponSwapInput`, `Player_tryBlockMove`, `OniBall_run` | Observed code; consequence Inferred; **new** | 4 |
| D12–D16 | creature status counters +0x36c… | `Creature_draw` 0x10b8d4 | `Player_run`, `Creature_run`, `damage_apply` | Observed; known; reachability Unknown (D16) | 5 |
| U2 | `g_pauseMenuOpen` 0x44f208 | `pauseMenu_open` (run task on the raw pad) | `missionMenu_run` 0x231a5c, `jumpgate_menuRun` 0x27def0 | Observed; mission menu **new** | not in the fight |
| — | light and water-spout run-list membership (+0x88/+0x89 and the like) | their draw functions | their run functions | Observed; known (D31, gameplay §8) | none in DRUNARE |
| — | jump-gate drawn flag +0xd0 | `JumpGate_draw` | `JumpGate_run` | Observed; known, no shipped level triggers it | none in DRUNARE |

## The tool

`python3 -I -B tools/drawsim.py` (about four seconds). Its docstring is the reference; in
short:

1. **Call graph** over the 7,732 function bodies of `ghidra_funcs.tsv`: 22,607 direct call
   edges; 3,154 `jalr` sites resolved as virtual calls from the table offset and slot visible
   at the call site (slot *n* of every class that keeps its table pointer at that offset;
   game classes and library classes are kept apart); 114 edges for function addresses built
   in code; 229 indirect calls left unresolved. The 42 `task_add` call sites are evaluated
   for the function and the flag argument, the seven `net_registerMsgHandler` calls for the
   handler.
2. **Categories.** S simulation (3,674 functions), P presentation during play (3,897),
   R prediction (2,493), L level entry and exit, N transport, B boot and front end.
   Presentation-only (P and not S): 860 functions.
3. **Globals.** The address tracking of `tools/gxref.py` (`scan`, `func_starts`) is run for
   every address in the data sections. A global is listed when a presentation-only function
   stores to it and a simulation function loads it.
4. **`--fields`**: fields a draw slot stores through `this` (including `this` plus a
   constant or an index, and through the functions it hands `this` to), matched against
   loads through `this` in the simulation slots of the same class.
5. **`--calls`**: simulation functions that change state and are called directly by
   presentation-only code (94). This is the complement of the global list: E9 and K3/K4
   are calls, not stores.

Other modes: `--check` (exit 1 unless the three known cases are listed), `--roots`,
`--why <function>`, `--global <address>`, `--vcalls`, `--stats`, `--loose`, `--prediction`.

### What had to be fixed before it found the three known cases

- **Run tasks that are not simulation.** `hud_run` is a run task, so it executes inside
  every tick, and it is the only caller of `menu_openInventory` — the only writer of
  0x41b69d outside the close functions. As a simulation root it made that writer
  "simulation" and the flag disappeared from the list. The seven per-machine run tasks of
  docs/mainloop.md section 9 (HUD, dialog, pause-menu opener, text chat, voice, save daemon,
  camera) are therefore presentation roots, and the front end and lobby tasks boot roots.
  Cost: lockstep helpers that only `hud_run` calls show up as presentation writers and are
  dismissed by reading (below).
- **Two worlds at one table offset.** Twenty library classes (lobby client) keep their
  table pointer at +0x48 like `GameObject`. Resolving by offset alone made a lobby
  destructor call every draw function, so every draw function was "simulation".
- **Run and draw called from the pause menu.** Two debug callbacks in the pause-menu code
  (0x18c660, 0x18c538) call the take-damage, run, touch and interact slots of every object.
  They sit behind `g_debugCheats`; they are why the presentation category reaches run
  functions at all.
- **`gxref` hits through a register a call does not preserve.** `gxref` keeps a `lui` value
  in a register across a call, so `lui $v0` … call … `lw x, 0($v0)` is reported as a certain
  access to the bare `lui` address (1,398 such hits). The tool confirms every hit with its
  own tracking, which forgets caller-saved registers at a call, and adds 3,404 indexed
  accesses (`base + index`) that `gxref` attributes to a stale address.

### Blind spots

Struct fields reached through a pointer (only `this` in draw slots is covered); arrays
indexed with a constant folded into the index register (the element reported may be a
different one of the same array); 229 unresolved indirect calls; callbacks registered with
the kernel or the IOP; per-machine *conditions* inside simulation code (`net_isLocalSlot`
has 50 simulation callers — K2 is one of them); and, most important, **a writer that
simulation code can also reach is not "presentation only"**. `net_closeLocalMenus` is called
from 16 simulation functions and closes whatever this machine has open, so `inventory_close`,
`shop_close` and the resource poll count as simulation, and 0x4ebbb0 (K2's second global)
is not listed on its own. Those were followed by hand.

## Triage of the 271

### By group: the simulation reader is plumbing (162)

"Simulation reader" here means only that some simulation function can reach it. Simulation
code does draw (message boxes from script built-ins, HUD text), play sounds and wait for the
disc, so drawing state shows up.

| Group (reader lies in) | Count | Examples | Verdict |
|---|---|---|---|
| rendering: lights, model draw state, sorted packets, display list, glow / trail / decal counters, texture streaming | 88 | 0x5d3448… (level light), 0x41c149 `g_modelFade`, 0x44fe10 display-list cursor, 0x82cc94 glow count, 0x840314 decal count | output only; the pool counts (glow, line, decal, trail) are per machine. Whether a simulation caller branches on an adder's result was not checked one by one; the known case is the beam table of FINDINGS D28 |
| memory card and save screens | 31 | 0x895580 save buffer, 0x88d3bc `g_cardOpResult`, 0x4f8f28 `g_cardXferLatch` | per machine by nature; the routes into shared state are FINDINGS B9–B11 and docs/script.md P2, P4 |
| audio | 19 | 0x4f8954 `g_soundFrame`, 0x876c10 streams, 0x41bac8 group volumes | sound return values and stream status are per machine (docs/audio-save.md A3; FINDINGS D8, D18); no new reader |
| camera functions | 6 | 0x44f110 camera matrix, 0x4f8460 reverse-yaw option | the camera is per machine by design; its yaw travels in the input record |
| disc and lumps | 5 | 0x41bf90 read state | load timing. Simulation callers of the "disc busy" test: `cut_runFrame` 0x199a64 (dialog audio preload), `eqcache_lookupModel`, the inventory resource poll |
| transport | 5 | peer flag bytes 0x5c3d0d… written by `net_main` | the lockstep mechanism itself (docs/netcode.md) |
| library, pads, automap, front end | 8 | 0x41bfd0, 0x4044f1 | rumble, map reveal bits, lobby |

### One by one: a gameplay function reads it (109 addresses, 47 topics)

| Addresses | What | Presentation-only writer | Simulation reader | Verdict |
|---|---|---|---|---|
| 0x41b818 | selector held | `hud_spellSelect` | `Player_run` 0x1a5c08 | **real — K1** |
| 0x41b69d | local menu open | `menu_openInventory` | `Player_usePotion` | **real — K2** |
| same | | | `Player_takeDamage` 0x1b53f4 | screen tint only |
| same | | | `inventory_removeItem` 0x1c1f74, with `net_isLocalSlot` and 0x4ebbb0 | re-indexes this machine's item-list copy; the record is changed the same way before and after. Not real |
| same | | | `gameMiscSync` 0x1e3dc0 | medal levels: closes this machine's menus → U3 |
| same | | | `hud_showMessage`, `hud_setCompassTarget`, `hud_setBust`, `player_voice` | HUD and voice only (docs/script.md P10) |
| 0x41b4fc | input lockout | `pauseMenu_task`, `help_task`, card screens | `Player_run`, `Player_takeDamage`, vehicle input | these writers run between ticks and `tasks_run` zeroes the word at the start of every net tick (0x322710). **Real through the in-tick writers — D26, U3** |
| 0x41b980, 990, 9a0, 9c0, 9d0, a10, a20, a30 | button masks per slot | `config_commitOptions`, `net_restoreButtonConfig` (leaving a net game) | `Player_run`, `Player_interact`, `Player_weaponSwapInput`, `Player_tryBlockMove`, `OniBall_run`, `OniBall_onTouch`, recall poll | **real — U1** |
| 0x44f208, 0x44fa78 | pause menu open | `pauseMenu_open` | `pauseMenu_isOpen` ← `missionMenu_run`, `jumpgate_menuRun` | **real — U2**. Its other two simulation callers: `net_frameLoop` 0x13b234 (only delays the prediction rebase) and `gameMiscSync` (U3) |
| 0x41b4f4 | `g_paused` | `pauseMenu_open`, `menu_openInventory`, `help_task`, `memcard_popPause` | `script_gamePaused`, `Player_run`, `game_isFrozen`, `game_checkAllDead`, `arena_runTask` | docs/ui.md P3 holds: each store is offline-only or stores 0 over 0. Not real before `saveEndConfig` |
| 0x41b4f8, 0x4f66a8 | menu-open and HUD-suppressed flags | menu and front-end code | `hud_setCompassTarget`, `hud_setBust` | HUD state only |
| 0x41b928 | help box open | `help_task` | script built-in `helpMessageActive` | per machine, but no shipped script calls it (all 120 searched). Latent |
| 0x41b930 | hit flash per slot | `hud_drawPlayerStatus` (clears) | `Player_takeDamage` (ORs bit 0) | the tick only sets the bit. Not real |
| 0x41b828, 0x41b834 | HUD notice timers | `hud_drawPlayerStatus`, `menu_openInventory` | `hud_countActiveNotices` | the count only chooses a screen row. Not real |
| 0x41bfdc, 0x41bfe0, 0x41bfe8 | lockstep pad words | `net_main` copies the raw pad over the local slot after the tick (0x134454) | `Player_run` and others | rebuilt by `pad_apply` before every tick (FINDINGS G5). Words +0x00, +0x04, +0x24 are not rebuilt: +0x04 is a "controller answering" countdown and +0x00 a port label; `Player_run`, `Player_move` and `Player_weaponSwapInput` read only +0x08…+0x18. Other pad-pointer users not checked |
| 0x4028d8 | raw pad | `menu_cursorInput` | recall-button poll | raw poll → game message; by design |
| 0x4d8ae4 | script active player | `dialog_runTask` 0x2301b8 | 9 script built-ins | the store is in the offline branch (network test at the top). Not real |
| 0x4f694a | exit countdown | `hud_run` | `Player_takeDamage` 0x1b53e4 | set by game message 8, decremented unconditionally every tick. Lockstep. Answers the Unknown in docs/player.md item 8 |
| 0x4f66b0, 0x4f66b4, 0x4f6960 | pick-a-player list | `hud_runPlayerPick` | `missionMenu_run` | driven by the lockstep pad of the picking slot and the alive list. Lockstep |
| 0x4d8bd4 (record +0xe4) | gold | `hud_tickGold`; `hud_run` cheat; debug sweep | gold checks | the tick is lockstep (frame counter only); the cheat and the sweep need `g_debugCheats` (docs/ui.md P5) |
| 0x4f66e0 | HUD message frames | `hud_tickMessage` | boss-meter helper | docs/mainloop.md P5; no shared reader |
| 0x4f6708 | controller unplugged | `hud_drawControllerOut` | `game_isFrozen` 0x1ebe80 | `game_isFrozen` returns `g_paused` first thing in a net game. Offline only |
| 0x506048 | warm-up frames | session loop | `cut_runFrame`, `game_isFrozen`, `tasks_run` | each read is behind a network-mode test. Offline only |
| 0x44fcf4, 0x44fcf8, 0x44fdc0, 0x4f8f38 | options: subtitles, damage numbers, blood, saved block | options screens | `cut_setup` (letterbox height), `damage_apply`, gib code, `saveEndConfig` | sync-breakers §7 holds for these values |
| 0x4f8f29, 0x4f8f30 | card screen done, ticks since save | card screens, save daemon | `Savepoint_run`, `Savepoint_interactPrompt` | known: FINDINGS B9–B11 |
| 0x8e2ca8…0x8e2d54 (6) | dialog text state | `dialog_runTask` | `dialog_onMsg` | known: docs/audio-save.md A2 |
| 0x4f4074, 0x4f4078, 0x4f4240 | item panels | `menu_openInventory`, `itemList_draw` | equip, combine and join-panel handlers | equip and combine use the panel owner only for a notice flag; the join-panel message is never sent with one player per machine (kill-loot-xp.md) |
| 0x4dd6fd, 0x4f719c | medal byte, difficulty | `debug_missionEditor` | medal and item code | debug file only |
| 0x41b6d0, 0x404464, 0x44fdc8, 0x44fdcc, 0x4f7120, 0x4f85c4, 0x41b510, 0x402791 | pending level, seed, world, frame counter, PvP flag, creature serial, front-end flag, network flag | session function, `frontend_stop`, HUD exit path | most of the simulation | session start, level change and leaving the game. One live case: the pending-level cancel, docs/mainloop.md P1 |
| 0x4d8af0…0x4dd714 (44) | player-record fields | `player_importCharacter`, `memcard_importScreen` | everything | character import in the front end; records are sent whole at launch |
| 0x404460, 0x44fdd0, 0x44fe10, 0x41bac8, 0x403a54, 0x41c1b8, 0x425df8, 0x4ef3ec, 0x503968 | cosmetic seed, displayed-frame counter, display-list cursor, volumes, heap flag, texture cells, equipment cache, talk bits | draw and service code | `anim_advance`, `anim_buildPose`, `rigidbody_init`, … | cosmetic by design. `anim_advance` uses the displayed-frame counter only for its per-group sound limiter (0x16d9e4) |

### The loose tier (542 more)

"Address taken" on one side, or an access `gxref` reports that the tool cannot confirm.

| Evidence | Count | What they are |
|---|---|---|
| address taken on both sides | 263 | structures and strings passed by pointer |
| address taken by presentation code, loaded by simulation code | 108 | almost always a presentation *read* of simulation state (experience table, alive list, cutscene key index, grid). Read: `cut_drawFrame` (reads the key index and dialog lines), `missionMenu_draw` and `jumpgate_menuDraw` (pass state to drawing routines; `menuList_draw` 0x1a07c4 does not store through its table argument), `Skeleton_draw`, `Player_draw` |
| stored by presentation code, address taken by simulation code | 40 | read by name; nothing beyond the strict list |
| unconfirmed on one or both sides | 131 | mostly false: a `lui` constant followed by an unrelated use of the same register |

Not read one by one. A presentation function that stores through a pointer it received is
invisible here as everywhere else.

## Object and record fields, by hand

### Fields a draw function stores in its own object (`--fields`, 62 sites)

| Field | Stored by | Verdict |
|---|---|---|
| flag word +0xc | `Creature_draw` 0x10bacc, `AutoObject_draw`, the three `…LP_draw` functions | only bit 0x100 (flash), which only drawing reads |
| status counters +0x36c… | `Creature_draw` 0x10b8d4 | **real — FINDINGS D12–D16** |
| position +0x10…+0x18 | `Mosquito_draw`, `FireBeetle_draw`, `FireFly_draw`, `Critter_draw` | a wobble added for drawing; the saved values are put back before returning |
| facing +0x38 | `AntQueen_draw` | subtracted, drawn, added back |
| position and facing | `UndeadKnight_draw` 0x2b4258… | not restored, but only with a mount, and nothing links one (docs/monsters.md 7.8). The arena knights are class `Horsemen` |
| creature flag bit 0x200000 | `Creep_draw` | "do not draw the model"; read by `Creature_draw` only |
| colour quads +0x70, +0x80, +0x90, +0x98 | glow and tint helpers called from `Creature_draw` | colours |
| "was drawn" and "is linked" bytes (+0x88/+0x89 `Torch`, `Lamp`; +0x8d `Candle`; +0x4d `Candle2`; +0x94/+0x95 `Lantern`; +0x58/+0x59 `WaterSpout`) | their draw functions, which also link the object into the active run list | **real mechanism — FINDINGS D31, docs/gameplay.md §8**: the object runs only where it was drawn in the last 30 ticks. All six run functions use only the object's own generator, particles and (spout) a water ripple |
| +0xd0 | `JumpGate_draw` | **real mechanism**, no shipped trigger (sync-breakers §5) |
| +0x464 | `Player_draw` | gates weapon trails only (docs/player.md) |
| +0x220, +0xf8, +0x78, +0x84…, +0xb8…, +0x110…+0x13c | `Player_drawEquipped`, `NPC_draw`, projectile, text, gold, save-point and physics-prop draw functions | drawing caches; other readers found: the clone functions, and `Prop_saveState` for +0x134…+0x13c (a per-machine save record) |

The three `Spell` draw overrides (`SpellDrowsy` 0x30ed24, `SpellSummonBadger` 0x311034,
`SpellResurrect` 0x312f48) only draw. That closes docs/creatures.md C2.

### Draw code that writes other objects or records

| Writer | What | Verdict |
|---|---|---|
| `Player_draw` → `Player_interact` in display mode → the prompt slot (13) of the nearest usable object, on the owner's machine at display rate, from the *predicted* position | 22 prompt functions were listed. Stores: +0x104 of item props (a frame stamp only drawing reads), +0x168 `UserParamProp`, +0x190 `Vehicle`, +0x4d `JumpGate` (marks the gate found). Five run a level-script predicate (`PushTrigger`, `AutoChest`, `AutoProp`, `SpiritAnchor`, `JumpGate`) | known: docs/script.md P1, sync-breakers §5. In DRUNARE the one predicate (the exit trigger's) only reads a quest variable |
| `jumpgate_travelEffect` (draw task) | +0xf0 and status counter 10 of every living player | known (sync-breakers §5) |
| `stats_screen`, `skills_screen`, item list | `Player_recalcDamage`, `player_recalcStats` | known: K3, K4 |
| `hud_spellSelect` | record +0x4a74, +0x4a78 | no reader outside it (kill-loot-xp.md) |
| `menu_openInventory`, `stats_screen` | record +0xed, +0xee, +0x4a58 | menu code only (docs/ui.md P4) |
| pause-menu debug sweep 0x18c7bc | take-damage, run, touch and interact slots of every object; player 0's gold | debug file only |

A search of the decompile of all 860 presentation-only functions for assignments into the
four player records, or through a record's object pointer, finds only these, the character
import, and `hud_tickGold`. Stores through a pointer handed in as an argument are not
covered by that search.

### Presentation code that calls simulation code (`--calls`, 94 callees)

Most of the 94 are drawing, sound, disc and card helpers that simulation code also uses.
The ones that change shared state:

| Callee | Presentation-only caller | Verdict |
|---|---|---|
| `script_runPostAction` 0x1edac0 | `help_task` 0x1dcf60 (network-tested), 0x1dd1f0 (not) | **real — FINDINGS E9**. The lockout it stores there (0x1dd1ec) is erased before the next tick |
| `script_runByName` 0x1ed694 | map routine 0x1696c4, `inventory_runPanel` 0x1c0314, `hud_run` 0x1dbb30, `NPC_draw`, `Gnome_draw`, `GnomeNavigator_draw`, `Rondo_draw` | known: docs/script.md P1, docs/ui.md P6 (the two inventory hooks exist in no script) |
| `obj_runEveryFrame` 0x14f248 | `WaterSpout_draw`, `Torch_draw`, `Candle_draw`, `Candle2_draw`, `Lantern_draw`, `Lamp_draw` | real mechanism: D31, gameplay §8 |
| `player_recalcStats`, `Player_recalcDamage` | `stats_screen`, `skills_screen`, `itemList_input` | known: K3, K4 |
| `player_giveExp` 0x1d3150 | `stats_screen` 0x1d1e94 with amount 0, when the level-up page closes; `hud_run` cheat | amount 0 adds nothing and a level is raised at the award, so no change is expected (**Inferred**; the function was not re-read for a zero amount) |
| `GameObject_rand` 0x1509d0 | `Gold_draw` 0x157e10, `AntWave_draw` 0x238808 | the object's own generator is advanced by drawing. No simulation function of either class draws from it (the only other caller on a `Gold` is its constructor). Cosmetic |
| `Player_interact` 0x1b2640 | `Player_draw` | display mode; the prompts are in the table above |
| `anim_emitPose` 0x16f880 | draw functions | **FINDINGS D34** (pose cache); not traced here |
| mission, evil and decision setters; `inventory_removeItem`; `shop_openOrStock` | `debug_missionEditor`, the debug sweep, the debug pause menu | debug file only |
| `cut_end`, `net_closeLocalMenus`, `save_load`, `save_build` | HUD exit path, card screens | leaving the game; docs/audio-save.md A1 |

No presentation-only function calls `pool_new`, an object constructor, `obj_delete`,
`handle_link`, `damage_apply`, `world_findFreeSpot`, `player_respawn` or
`inventory_giveItem` directly. So no object is created or deleted from draw code by a
direct call; the unresolved indirect calls are the reservation.

Virtual calls from presentation-only code into simulation-side slots (`--vcalls -v`): the
debug sweep (take-damage, run, touch, interact); and slot 17 of objects held in a child
array, called by `AutoEmitter_draw` (0x241138…0x2411f8), `AutoChestLP_draw` 0x2415ac,
`AutoPropLP_draw` 0x242084 / 0x242100 and `AutoContainerLP_draw` 0x2426d0 with a position.
The children are `AddParticle` helpers, whose slot 17 (0x240800) recomputes the helper's
light and halo (docs/monsters-2.md, slot table and the LP section); for the `AutoProp`
classes themselves slot 17 is "next state", but the draw functions do not call it on
`this`. Drawing only; the body of 0x240800 was taken from that document, not re-read.

## The real ones

Input delay: a pad sample taken in `net_main` call *c* is simulated in call *c + L − 1*,
where *L* is the lead (minimum 2; about 5 for two players at 30 ms; about 35 for 15–30 s
after any half-second stall — FINDINGS L11). Local screens change at once. So a local change
made in calls *c … c + L − 2* is in place when the sample of call *c* is simulated: the
window is *L − 1* calls, 0.57 s at a lead of 35. **Inferred** from kill-loot-xp.md F2.
Confirmed since by execution (`docs/spec/net-wire.md` section 14, property "input delay
rule": every frame of a two-machine interpreter session obeyed it), with two things made
exact: *L* is `g_localInputFrame − g_netFrame` taken after the sample is stored and before
the tick, and *c + L − 1* assumes one tick per call — every call without a tick in between
adds one. *L* was 1 only in each machine's very first call and at least 2 afterwards. On
the live game one machine alone read `g_localInputFrame` = `g_netFrame` + 1 between frames
(`docs/issues/live-rig.md` 4d); that is consistent with *L* = 2 by the definition above if
the reading was taken after the call's tick, which the rig's log does not say.

### K1, K2 (known) — only what this pass adds

Both are confirmed as listed by the tool. For K2 the list of readers of 0x41b69d is now
complete (table above): `Player_usePotion` is the only one that changes shared state on the
flag. For K1 the only readers of 0x41b818 are `Player_run` (0x1a5c08; and 0x1a6e04 behind an
offline test) and `Player_draw`.

- **Trigger:** K1 — use, then a D-pad direction; K2 — a potion button, then the inventory
  button. **Window:** *L − 1* calls.
- **Then:** K1 — the item stays on the ground on the owner's machine (a chest would fail
  the hash at once; DRUNARE has only dropped items). K2 — one potion more on the owner's
  machine for good. Both **silent**; the hash fails later, when a potion exists on one
  machine and not the other.

### D26 and U3 — the lockout inside a tick

**Observed.** `net_closeLocalMenus` (0x1eb000) does, in a net game: send menu-state 0 for
the local slot, close the pause menu, `inventory_close`, reset notices, `shop_close`, and
(argument 0) take every living player out of a vehicle. Only `inventory_close` and
`shop_close` store the lockout, and only where that menu is open.

| Caller inside the tick | When in the tick | Can one machine have a menu open? | Effect |
|---|---|---|---|
| `Player_processDamage` 0x1b351c — the local player dies | during `runObjects` | yes: the inventory does not pause a net game | **D26**: for the rest of that tick that machine drops all player damage and skips weapon swap and interact for players that run after the dead one |
| `gameMiscSync` 0x1e3dcc — medal player's machine, while the medal countdown 0x4f7114 runs | run task priority 1, **before** `runObjects` | yes | **U3**: a whole tick of the above on that machine. Medal levels only |
| `JumpGate_openMenu` 0x27da8c from `JumpGate_run` | during `runObjects` | yes | needs an automatic gate; none shipped |
| `cut_start` 0x19b520 | during `runObjects` or the script task | yes, but `cut_start` then stores 60 on every machine (0x19b5ac) | same everywhere |
| `player_respawn` 0x1bd0b8 | during `runObjects` | no: only for the local slot, whose menus were closed at death and cannot reopen while dead (`hud_run` requires hit points) | none |
| `hud_onMsg`, `dialog_onMsg` | message handlers, before `tasks_run` | — | erased: `tasks_run` zeroes the word first |
| mission menu, arena, `game_checkAllDead`, script built-ins | after `runObjects`, or with a level change | — | nothing left in the tick to read it |

- **Trigger in DRUNARE:** a player dies with the inventory open while another player, who
  runs later in that tick, has a use or weapon-swap press in that tick's input, or is hit
  later in that tick. Monsters run before players there (arena-desync.md F1), so in
  practice it is the press. **Window:** one tick. **Then:** silent (a pick-up or a weapon
  swap missing on one machine).

### U1 — the option commit rewrites every slot's button map

**Observed:**

1. The per-slot button-mask tables 0x41b980…0x41ba30 (attack, ability A/B, use, block,
   potion A/B, weapon swap, one camera button) are what `Player_run` and its helpers use to
   read the lockstep pad. At launch each slot's row is installed from that player's data
   (0x13776c–0x1377a4; FINDINGS B12).
2. `config_commitOptions(force, queryOnly, noCardSave)` 0x1e6650 counts the options that
   differ between the live globals and the saved block `g_savedConfig` 0x4f8f38. The
   button maps are part of the count only offline (network test at 0x1e6824).
3. If it is not a query and the count is non-zero, it copies the live options into the block
   and then copies **all four rows** of `g_savedButtonMaps` 0x4f8f6c — this machine's own
   controller configuration per local port — into the per-slot tables (loop
   0x1e6a60–0x1e6b0c). No network test. It is the same copy `net_restoreButtonConfig`
   0x1378e0 makes when a net game is left.
4. Callers during play: `pauseMenu_task` when the option list is left with cancel (state
   0x33: query at 0x18d180, then commit at 0x18d2c8 or 0x18d2e0) and the `warpMenu` task when
   the pause menu is closed (0x18e2f8).
5. The pause menu disables only the *controls* entry in a net game (0x18cc08, the string
   test for that entry). Brightness, volumes, vibration, blood, subtitles, damage display,
   chat, markers and the voice options stay available.

**Inferred:** after any option is changed in the pause menu during a net game, that machine
reads slot *s*'s pad with its own row *s* instead of the map player *s* sent. Nothing
changes if every player uses the default controls. If any player has remapped a button,
the machine that changed an option now takes that player's presses for different actions
(and, when it is not slot 0, its own presses too: its own configuration sits in row 0).
Which row a machine sends at launch was not read; "row 0" is Inferred.

- **Trigger:** a non-default controller configuration on any machine, and any option
  changed through pause → options on any machine. No timing window.
- **Then:** the first press of a button whose mask differs gives a different action on
  that machine: a swing, a cast or a potion on one side only. Hash mismatch within a few
  frames.
- **Test:** player B remaps attack and ability A before launch; player A changes the
  music volume in the pause menu and leaves the option list; B attacks.

### U2 — the mission menu and the chooser's pause menu

**Observed.** `missionMenu_run` 0x2316fc is a run task driven by the chooser's lockstep pad.
At 0x231a4c–0x231a74: if the chooser's slot is local and this machine's pause menu is open,
it locks local input for four calls and returns before the pad test. `jumpgate_menuRun` has
the same lines at 0x27dee0–0x27df0c (noted in sync-breakers §5).

**Inferred.** A confirm or cancel already in the input stream when the chooser opens the
pause menu is acted on by every machine except the chooser's: the others leave the menu or
request the level. **Window:** *L − 1* calls. **Then:** the menu and the pending level
differ — not silent. Not reachable inside the arena fight.

### The rest of the known ones, for completeness

| Ledger | State | Why it is in this class |
|---|---|---|
| D12–D16 | status counters | decremented by `Creature_draw`, read by the tick. Whether any character can set counters 2, 7, 12, 13 is still Unknown |
| D31, gameplay §8 | lights, water spouts | linked into the run list by their draw functions |
| sync-breakers §5 | jump gate +0xd0, +0x4d | drawn flag gates the automatic open; the prompt marks the gate found from draw code |
| B9–B11 | card state | `Savepoint_interactPrompt` and `Savepoint_run` read this machine's card state |
| script.md P1, P2 | scripts from draw code; medal result | predicates run at display rate on one machine; the medal box waits on the local card |
| audio-save.md A2 | dialog progress | the dialog task writes text state from local audio and layout; the handler reads it |
| mainloop.md P1 | pending level | cancelled once per displayed frame on a card-state test |
| ui.md P5, sync-breakers §7 | `debug.sht` | gold and experience cheat, debug pause menu, object sweep |

## Ranking for an ordinary two-player boss fight in DRUNARE

The level has no light objects, water spouts, jump gates or save points; one usable trigger
whose predicate only reads; three cutscenes that freeze every player. What the players do:
hold the D-pad, drink potions, open the inventory, pick up the potions the knights drop,
die, get revived.

1. **K2.** Potion, then inventory, inside the delay. Every level-up invites the inventory
   press. Silent; shows as a hash mismatch only when the missing or extra potion is used.
2. **K1.** Use (the dropped potions), then the D-pad, inside the delay. Silent, usually
   repaired by picking the item up again.
3. **D26.** A death with the inventory open and another player's use or swap press in that
   tick. One tick wide.
4. **U1.** Only with remapped controls and an option changed during the fight.
5. **D12–D16, G11–G13** as ranked in the earlier documents.

**Inferred, and the main thing this pass adds to the arena question:** K1 and K2 are one
sample wide at the minimum lead and half a second wide at a lead of 35. A boss fight is where
a stall is most likely, and a stall leaves the lead high for 15–30 s. A run that goes out of
sync "every time" in the arena and rarely elsewhere fits *a large lead plus K2* better than
any single cause on the ledger — but nothing here proves it. The observation that would:
potion counts of one player (record +0x2540, 0x48 per item, count at +4) differing between
machines before the message appears, and `g_localInputFrame − g_netFrame` (0x4027a4, 0x4027ac)
well above 5 during the fight.

## Patch proposals (all untested)

One change each. PCSX2 form: `patch=1,EE,<address>,word,<new>`. Original words were read from
the executable. The first three are the proposals of kill-loot-xp.md, repeated because they
are the top of the ranking; they are not in `patches/` yet.

| # | Address | Original | New | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| P1 | 0x001a5c0c | 54600006 | 00000000 | K1: `Player_interact` is called whatever 0x41b818 says | offline, use also acts with the selector open | each machine protects its own player; a mix is safe |
| P2a | 0x001b9fcc | 8043b69d | 00001821 | K2: the health-potion branch reads the local-menu flag as 0, so the potion always leaves the bag directly | the open inventory may show the old count until reopened | same |
| P2b | 0x001ba3ac | 8043b69d | 00001821 | K2: the same for the mana-potion branch | same | same |
| P4 | 0x001b53d4 | 8c43b4fc | 00001821 | D26/U3: `Player_takeDamage` reads the lockout as 0, so damage is never dropped because a local menu closed | offline, players can be hurt in the 60 calls after a menu closes and during cutscenes that do not freeze them | each machine for itself; a mix is safe (a patched machine does what the machines without the menu already do) |
| P5 | 0x001a5ba8 | 8e02b4fc | 00001021 | D26/U3: the gate in front of weapon swap and interact reads the lockout as 0 | offline, the press that closed a menu can also swap weapons or interact | same |
| P6 | 0x001e6a60 | 3c060042 | 08079ac4 | U1: a jump over the copy loop to 0x1e6b10 (the instruction after it, a shift into a scratch register, runs in the delay slot and is harmless). `config_commitOptions` no longer rewrites the button tables | in **every** mode a change made in the controls screen stops taking effect when the options are left, until the tables are rebuilt some other way (leaving a net game does it). Use only for an online test session | each machine for itself; a mix is safe |
| P7 | 0x00231a64 | 10400006 | 10000006 | U2: the branch that skips the lock-and-return is always taken; the mission menu reads the chooser's pad on the chooser's machine as everywhere else | presses made in the chooser's pause menu also reach the mission menu underneath, on every machine alike | the chooser's machine; a mix is safe |
| P8 | 0x0027def8 | 50400006 | 10000006 | the same for the jump-gate menu | same | same |

P4 and P5 change the readers rather than the two stores (0x1c52dc, 0x1d0b48), because in a
net game the word is already zero in every tick except the D26 windows, while offline the
stores are what keeps a closing press from acting.

## Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| U1 | `config_commitOptions` 0x1e6650, run when the pause menu's option list is left with any option changed (and when the pause menu closes), copies this machine's four saved controller rows into the per-slot button-mask tables with no network test; in a net game those tables hold each player's own map from the launch handshake. Any remapped button then reads differently on that machine | Observed (code); Inferred (consequence) | 0x1e6824 (offline-only compare), 0x1e6a60–0x1e6b0c (copy), callers 0x18d2c8, 0x18d2e0, 0x18e2f8; 0x13776c; `Player_run` readers |
| U2 | `missionMenu_run` returns before its pad test on the chooser's machine while that machine's pause menu is open; the other machines act on the press | Observed; Inferred (window) | 0x231a4c–0x231a74; same lines in `jumpgate_menuRun` 0x27dee0–0x27df0c |
| U3 | Routes by which the lockout is set inside a tick on one machine: local death (D26), the medal countdown in `gameMiscSync` (before objects run), an automatic jump gate. Not routes: `player_respawn` (no menu can be open), message handlers (the word is zeroed before the tasks), `cut_start` (stores 60 everywhere) | Observed | 0x1b351c, 0x1e3dcc, 0x27da8c; 0x1bd0a8–0x1bd0b8; 0x322710; 0x19b5ac |
| U4 | The windows of K1, K2, U2 and the jump-gate menu are the lead minus one call: one sample at the minimum lead, about 0.57 s at a lead of 35 | Inferred | kill-loot-xp.md F2; FINDINGS L11 |
| U5 | `g_exitCountdown` 0x4f694a is lockstep: set by game message 8 and decremented unconditionally in `hud_run` | Observed | 0x1d907c, 0x1db8f0 |
| U6 | The three `Spell` draw overrides only draw; `dialog_runTask`'s store to the script active player is offline-only; `g_helpMessageOpen` reaches scripts only through a built-in no script calls | Observed | 0x30ed24, 0x311034, 0x312f48; 0x2301b8; 0x1433bc |
| U7 | A mechanical search (`tools/drawsim.py`) for globals stored by presentation-only code and loaded by simulation code gives 271; apart from K1, K2, D26, U1, U2 and rows already on the ledger, none reaches shared state in a net game. Its blind spots are pointer-reached fields and per-machine conditions inside simulation code | Observed list; Inferred completeness within the blind spots | this document |

## Corrections to earlier documents

- **sync-breakers.md §7** says option settings do not matter online and that the button
  tables "are installed at launch from each owner's data". True at launch; U1 rewrites them
  whenever the option list is left with a change. The advice "option settings do not
  matter" should read "do not change options during an online game if anyone has remapped
  buttons".
- **docs/mainloop.md**, run-task table: the `net_isLocalSlot` at 0x231a4c in
  `missionmenurun` is the pause-menu early return of U2, a per-machine branch in a lockstep
  menu, not a harmless local test.
- **FINDINGS D26** names one route ("the local player dies with a menu open"). There is a
  second (U3). Closes reached from message handlers do not count: the word is zeroed
  afterwards.
- **docs/player.md**, item 8: 0x4f694a cannot differ between machines (U5); 0x41b4fc can,
  inside a tick (D26).
- **docs/creatures.md C2** ("spell draw bodies not checked"): checked, drawing only.
- **docs/creatures.md C10** asks whether local UI code touches the menu latch 0x4fe53c. Not
  in a net game: `menu_openInventory` skips the acquire when the network flag is set
  (test in front of the call at 0x1c1608) and `inventory_close` releases only offline
  (0x1c52b0). Its other writers are `Creature_interact`, `Creature_trigger`, `dialog_onMsg`,
  `dialog_free` and one script built-in.
- **docs/netcode.md**, per-machine item 4 ("no handler was identified that reads a pad"):
  `inventory_unequipItem` (inventory message 2) passes the message slot's lockstep pad to
  `Player_weaponSwapInput` (0x1c2ffc). It is the sender's own slot, whose pad has been
  applied for the frame, so it is consistent; it is the one handler that does read a pad.
- **`tools/gxref.py` output:** hits are labelled with the heuristic function table, so the
  read of 0x4039c0 at 0x14b170 (the first instructions of `world_drawObjects`) is printed
  under `world_findFreeSpot`; and a `lui` kept in a caller-saved register across a call
  gives certain-looking hits at round addresses (0x450000, 0x420000). "Only reader" and
  "only writer" statements that rest on such lines should be re-checked with
  `drawsim.py --global`.

## Not done, not known

- The `--prediction` list (353 globals written by code the prediction copy reaches and
  read by the tick) was not triaged; it is over-approximate and overlaps
  `tools/ghostreach.py`.
- The loose tier was classified by evidence and read only in part.
- The 50 simulation callers of `net_isLocalSlot`, the 20 of `net_getLocalPlayerSlot`, and
  the audio, card and "near view" callers were listed (`drawsim.py` call graph) but not
  re-read; the earlier area documents cover many, not all.
- Stores through a pointer argument in menu code; the 229 unresolved indirect calls.
- Pad words +0x00, +0x04 and +0x24 keep per-machine values in the lockstep pad; only three
  pad-pointer users were checked for reads of them.
- Which controller row a machine sends in the launch handshake (U1), and whether a card
  config load during play can also call `config_commitOptions`.
- The weapon-holder draw slots (table pointer at +0 of the holder; slots 18 and 19 are
  called only from draw functions) were not covered by `--fields`.
- `AddParticle_updateLightAndHalo` 0x240800 (called from the four `Auto…LP` draw functions)
  was not re-read; if it links a light it is one more D31 case.
- Who calls `arena_init` 0x304df0 (no direct call or built address was found), and so
  whether the `arena` run task exists in DRUNARE.
- Whether K2 at a large lead is the arena's "every time": needs two running copies.
