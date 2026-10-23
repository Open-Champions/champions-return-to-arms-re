# Player death and recovery (SLUS-20973 v2.00)

Research worktree `t3/research-death-flow`, based on main `034d0c0`.
**Observed** means the original instructions at the cited address were read;
**Executed** means a bounded function was run by `tools/ee_emu.py` and compared
with `tools/ref_death_flow.py`. Neither is a full game or console playthrough.

## 1. HP zero to the death clip

**Observed:** `Player_takeDamage` 0x1b5330 queues the hit. During `Player_run`
0x1a5030, `Player_processDamage` 0x1b2cc0 resolves it. When record HP
`R+0xac` is at most zero, the one-player `SpellResurrect` ward is checked
first (0x1b3370–0x1b33c8): if attached and `g_numPlayers == 1`, it calls
0x3130f4 and stores the returned HP. A successful roll restores half of max
HP, clears pending damage, and skips the death sequence; a failed roll
returns zero HP and continues into it. The spell's roll and return values
are separately documented and bounded-tested in `docs/spec/skills-35-68.md`
section 68 and `docs/spec/skills-35-68-executed.md`; this branch has **not**
executed the `Player_processDamage` caller or its ward hand-off. At
0x1b33d4–0x1b3408, the remaining lethal branch clamps HP to zero and sets
object flag `0x8`. The death branch selects an animation from the
player model definition: `def+0x14` for weapon animation class 2 except models
2, 3, 6, 7, otherwise `def+0x0c`. `anim_start` 0x16cfe0 gets a 0.5 start and
flags `0x206` at 0x1b34b0–0x1b34e4. `P+0x58c` becomes state 4 and
`P+0x448` receives the simulation frame at 0x1b34ec–0x1b3500. The alive
player list is rebuilt at 0x1b3504. The selected death animation is the
same hand-off described by `t3/research-player-anim` commit `4ad5721`,
`docs/spec/player-animation-selection.md` section 3; that branch's original
selector test established its bounded class/model cases, not loaded clip poses.

**Observed:** state 4 in `Player_run` 0x1ab2f0 stops cast sound/aura and steps
the death track while `g_playerDeadCountdown[slot]` at 0x4f84a8 is above 1.
It does not return to neutral; the object is replaced on revival. At 180
frames outside PvP mode A it also places a decal. The existing
`docs/spec/player-tick.md` section 6 and `docs/player.md` state table contain
the full state machine. There is no gold, XP, or inventory debit in this
death-state hand-off. This is a statement about the read branch, not a claim
about later checkpoint rollback.

## 2. One dead player versus a full wipe

**Observed:** `tasks_run` 0x3226e4 calls `game_rebuildAlivePlayers` 0x1e72f8,
then `game_checkAllDead` 0x1e7438 after the run tasks of each simulated tick
(`docs/spec/object-system.md` section 6.3). `game_checkAllDead` decrements
each dead slot's signed 16-bit countdown only when its record HP is at most
zero, the alive count differs from the player count, and the game is not
paused or in a cutscene (0x1e7524–0x1e75c0). It starts at 240 on level entry
or `player_respawn` (0x1ec2b8, 0x1bd0a4). A slot reaching zero calls
`arena_respawnPlayer` 0x305784 only in PvP mode B. The normal campaign path
does **not** automatically call `player_respawn` for that slot.

**Observed:** while anyone remains alive, the party-wipe branch is skipped
(`g_alivePlayerCount` 0x4f8420 at 0x1e7488–0x1e7490). In a net game the dead
local player's HUD can cycle among living players through
`hud_drawNetCamPrompt` 0x1e01b8 (`docs/spec/movement-camera.md` section 7.7).
The dead player can return by a living player's `SpellResurrect` at
0x312e40, or by `Savepoint_run` 0x28d528–0x28d618 when an active savepoint
finds a dead slot whose countdown is zero. The savepoint scan requires at
least two players, a live teammate, an active dead slot, and its own
activation conditions (0x28d534–0x28d5c4). The savepoint calls
`player_respawn(slot, position-near-savepoint, angle, 1, 12)` after a free
spot search; the spell uses the old body's position and facing with `-1,-1`.
`player_respawn` 0x1bd040 destroys the old object, sets record HP to half
max (full in PvP mode A), constructs a new Player, starts spawn protection,
rebuilds the alive list, and resets the local camera. The Resurrect spell
then overwrites HP with its rank-dependent percentage of max
(`docs/spec/skills-35-68.md` section 68). It does not reload a checkpoint.

**Observed, Executed:** when the alive count is zero in a loaded campaign
level, `game_checkAllDead` checks `game_isFrozen`; in a net game it also
requires at least two active peers (`net_fewerThanTwoActive` 0x13dd88).
It sets menu input lockout to 60, decrements the global signed 16-bit wipe
countdown at 0x4f7194, and when that reaches zero closes local menus and
calls `deathTask_schedule(0)` (0x1e74b4–0x1e751c). Cutscene, unloaded game,
PvP mode B, zero player count and frozen cases skip this scheduling path.
The global countdown is initialized to 240 by 0x1ec2b8. The original
function and the model matched 108 cases on each seed 20973 and 7; the
service answers were scripted, and no whole-game timing was measured.

## 3. Wipe fade, reload, location and possessions

**Observed:** `deathTask_schedule` 0x1ebd48 clears the fade and registers
`deathTask` 0x1e75e8 at priority 20. The death-flow difftest stubs this
scheduler call; its setup has not been executed here.

**Observed, Executed:** `deathTask` phase 0 repeatedly asks
`hud_stepFade(4)` until it returns `0x80`; then phase 1 begins
(0x1e7648–0x1e7680). A script-set `setAlternateDeath` flag at 0x4f712c
instead moves to phase 10, which waits for an alive player and removes
the task (0x1e7648–0x1e7658, 0x1e7788–0x1e77a0). The alternate script's
own revival behavior is outside this task.

**Observed, Executed:** normal phase 1 checks `save_findAct(current level)`
0x217d30 at 0x1e76b0. It searches the current act's level table, then the
other act tables. If it returns `-1`, `deathTask` requests the current
level in `g_pendingLevel` 0x41b6d0, writes the `0xfd` level-change marker,
copies each player's max HP `R+0xb0` to current HP `R+0xac`, and removes
itself (0x1e76c4–0x1e777c). Gold `R+0xe4`, XP `R+0x5c`, item bags and
equipment are not written by this branch, so their current record values
carry into the requested level. The fate of world pickups and altered
level objects on this special restart requires the level loader; the branch
alone does not establish a reset of world state.

If `save_findAct` finds the level, phase 1 calls `save_reload` 0x22266c,
which calls `save_load` 0x221d60 (0x1e7720). `save_load` restores the
saved level name and player position/facing and copies each entire saved
`0x4c30` player record from `g_saveBuffer` 0x895580, then requests the
saved level (`docs/audio-save.md` section "Reading back"). The player
appears at that snapshot's location when the loader constructs objects,
whether the saved level is the hub or another checkpoint. Gold, XP, items,
equipment and other record fields become their **saved values**; changes
made after that in-memory checkpoint are rolled back. There is no separate
fixed death tax established by these branches. The buffer is made by
`save_game` 0x218128 on savepoints or script `saveCheckPoint`; this is an
in-memory checkpoint and the death path does not read a card slot. Phase 2
waits for the pending-level request to clear and the qualified level name
to match, then removes the task (0x1e7740–0x1e7780).
Behavior when `save_findAct` finds a level but the in-memory save buffer has
no valid snapshot is **Unknown** here; the test stubs `save_reload` and does
not exercise that failure state.

**Observed:** no game-over or continue-choice menu is called or branched
to in `game_checkAllDead`, `deathTask_schedule`, or `deathTask`.
This normal campaign path fades and automatically requests a level or
reload. The `MemcardContinue` identifiers in the executable belong to the
memory-card UI; this research does not infer a death-screen option from
their names. An actual rendered fade/overlay was not inspected in a live
session, so its pixels and any external platform prompt remain **Unknown**.
The script-set alternate death mode and PvP arena are distinct flows.

**Executed scope:** `tools/difftest_death_flow.py` runs the original
`game_checkAllDead` and `deathTask` instructions in `tools/ee_emu.py` on
scripted globals, compares call order and fields with
`tools/ref_death_flow.py`, and covers 108 all-dead cases and 56 task cases
per seed. It stubs freeze/network, fade, save lookup/reload and task services.
It requires the pinned US v2.00 executable SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
It does not run `Player_processDamage`, animation, save parsing, level
loading, savepoint revival, or a full party wipe as one continuous game.

## 4. Ordered native port list

1. Keep the actual record/object link and HP/pending-damage fields, and
   process the one-player `SpellResurrect` ward before the lethal clamp and
   death clip. A successful ward roll restores half max HP and skips death;
   a failed roll enters the ordinary death branch. Keep this separate from
   a living teammate's post-death Resurrect spell. Use the model/weapon-class
   selector and animation flags from `4ad5721`; refuse missing clip/model
   inputs. Execute the ward hand-off in `Player_processDamage` before
   claiming this ordering as bounded-tested.
2. Rebuild the alive list after player damage and at the end of the tick;
   decrement slot and global wipe timers with the original cutscene, pause,
   network and PvP gates. Preserve spectator selection while teammates live.
3. Implement `player_respawn` object replacement and local spawn protection
   for spell and savepoint revival. Keep savepoint free-spot placement separate
   from exact-body Resurrect placement.
4. Schedule the fade/death task and its normal/alternate branches. Execute
   `deathTask_schedule` setup before claiming its fade clear and priority as
   bounded-tested. Port checkpoint buffer creation and restore before claiming
   party-wipe parity; the saved record and level choose location and retained
   values. Keep the direct same-level/max-HP branch when `save_findAct`
   returns `-1`.
5. Validate a real death through fade and level load in the native client,
   checking before/after HP, Gold, XP, items, equipment, position and world
   objects against the original on the same saved state. `328b072` supplies
   the assisted Valor combat/boar-death and separate Gold-credit evidence, but
   it did not kill a player or run this wipe route. No fixture actor or
   guessed service should stand in for that integration test.
