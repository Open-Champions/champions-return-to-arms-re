# Level-script built-in commands: specification

What a rebuild has to do when a compiled level script calls one of the 191 native functions
of the table at 0x403370, and what the game does around those calls: how a built-in gets
its arguments, how names become objects, the "active player", quest variables, deferred
calls, the post action, and who starts scripts. The bytecode machine itself is
`docs/spec/script-machine.md`; the area survey is `docs/script.md` (section 9 below lists
where executing the code corrected it).

`tools/ref_natives.py` is this document as code. `tools/difftest_natives.py` runs the
original handlers in `tools/ee_emu.py` (an instruction interpreter, not a console) through
the real dispatcher and compares them with the model. Evidence words used here:

- **Executed** — the original code was run for seeded random states and arguments and the
  model, which is the statement in this document, agreed on the result, on every call made
  to code outside the model with its arguments, on every byte written, and on the shared
  seed. Section 8 gives the numbers.
- **Observed** — read in the instructions at the address given; not run.
- **Inferred** — follows from the above; the reasoning is given.

Nothing here was run on a console or on the live game. Floats were compared as 32-bit
patterns under the interpreter's 'ps2' floating-point model (`docs/issues/dynamic-tests.md`).
Everything in sections 1 and 3–5 is Executed unless marked otherwise.

## 1. Shared machinery

### 1.1 How a built-in is called and what it returns

The script pushes its arguments right to left, then their size in bytes, and executes
SYSREQ.C *n*. The interpreter saves CIP, FRM, HEA and STK into the machine structure and
calls the dispatcher `scr_callNative` 0x141050:

```
scr_callNative(machine, n, &PRI, params):
    machine.error = 0                               // +0x5c
    PRI = handler_n(machine, params)                // the low 32 bits of the handler's result
    return machine.error                            // always 0: no handler sets it
```

`params[0]` is the byte count and `params[1 + k]` argument *k*. Three rules follow from the
handlers (all 190; `newWorld` and `newWorldAlways` share one):

1. **No handler reads the byte count.** A handler takes as many cells as it wants. A call
   that pushed too few reads the caller's stack above its arguments (`activateStore` and
   `givePlayerItem` are called that way by shipped scripts, `docs/spec/script-machine.md`
   section 9); a call that pushed too many (one shipped `getv`) is not noticed.
2. **The result is whatever is in the return register.** Handlers that return a value say
   so in section 3. Handlers written as "no result" return 0, except those that end in a
   call and pass its result on unchanged: `callScript` (the run's result), `getv` and
   `getpv` (a sign-extended byte), `getEvil` and `getMadeDecision` (the masked flag byte, so
   1 << difficulty and not 1), `getMissionComplete`, `getMissionAvailable`, `getMedal`,
   `dialogRunning`, `playerSelRunning`, `hudFadeScreen`, `countQuestItems`,
   `onePlayerHasItem` (each the callee's result).
3. **No handler can fail.** There is no error return; a handler that is handed nonsense
   reads and writes wherever the nonsense points.

### 1.2 String arguments

A string argument is a data-relative address. Every handler turns it into a C string the
same way:

```
scr_getAddr(machine, address, &pointer)     // 0x1414a8; result ignored by every handler
scr_getString(buffer, pointer)              // 0x141650; packed or unpacked, no length limit
```

`buffer` is a local array, 160 bytes in most handlers (128 for each of the four texts of
`runMedalSuccess`). A longer string overruns the handler's frame; the model refuses such a
call instead of guessing (Observed for the frame layout; not executed).

**A refused address.** `scr_getAddr` accepts an address below HEA, or from STK up to STP
(the registers as saved at the SYSREQ); for any other it returns 5 and does **not** store a
pointer. Because the handlers ignore the result, they then convert whatever their stack
slot already holds. That slot is at a fixed distance below the stack pointer the handler is
entered with, and handlers called from the same interpreter run are entered with the same
stack pointer, so the slot holds the pointer of the last successful conversion made through
a slot at the same distance — usually the previous string argument of the previous
built-in call. The distances (bytes below the entry stack pointer), measured in 5,981
executed calls:

| Slot | Handlers |
|---|---|
| 0x20 | callScript, print, simpleNewWorld, newWorld, newWorldAlways, newWorldPost, stopPropAnim, propAnimAtEnd, NPCAnimAtEnd, onePlayerHasItem, setInfo, removeQuest, startMusic, startAudio, getv, setv, addv, setpv, getpv, setNoCollide, addDeferedCall, postAction, controlVehicle, holdVehicle, getVPosition, setEntrance, closestPlayerDist, setHitPoints, preloadResource, countQuestItems |
| 0x30 | sound, soundSequence, playerHasItem, removePlayerItem, addHelpMessage, addQuest, putNPCInVehicle, findDistance |
| 0x40 | lightEffect, startPropAnim, addExpandingPool, putPlayersInVehicle, showBust, selectDropItem |
| 0x50 | addParticleOnObject, showCompass |
| 0x60 | hitPlayers, dropItem |
| 0x70 | entityRideVehicle, runMedalSuccess |
| 0x80 | startDialog |
| 0xa0 | deleteObjects |
| 0xb0 | giveOnePlayerItem |
| 0xc0 | runMedalFail |
| 0xd0 | givePlayerItem, cutScene |
| 0x110 | objInPlayerTrig |
| 0x1c0 | autoPropSetState, autoPropGetState, showOnMap |
| 0x1d0 | trigger |
| 0x220 | countLiveObjects |
| 0x440 | addHelpMessageF |
| 0x820 | increaseEnemyRank, unRootMonster, stopFollowingPlayer, friendly, unFriendly, getHitPoints |
| 0x830 | charmMonster, rootMonster, setMonsterVal, setCFlag, killMonster, deleteMonster, hideMonster, showMonster, followPlayer, followPath, stopFollowingPath, setCreatureParams |
| 0x840 | setOFlag, setWeaponType, setMonsterRange, moveMonster, monstersInTrigger, setContainerProps, particleMorph (second argument) |
| 0x850 | startNPCAnim, generateMonster |
| 0x10f0 | particleMorph (first argument) |

This is not an academic case. The `start` entry point of the shipped script TORMEDAL walks
an array of 20 object names with an index that runs to 20 and calls `rootMonster(name)` and
`setCFlag(name, 26, 1)` for each. For index 20 the "address" is the first cell of the first
name and is refused; both handlers share slot 0x830, so both act once more on the
twentieth name. Executed: with that rule the model and the original agree on the whole
entry point (the creatures of that name get virtual slot 27 a second time). It is the only
refused address in the 1,828 shipped entry points as far as the test's runs reached them.

The model keeps a slot's content only where it is certain: a later handler with a
different frame layout may overwrite the word with something else (a string buffer, a
saved register), so a slot survives a built-in call only if that built-in has a slot at the
same distance. In any other case the model raises `StackGarbage` (the original goes on
with a word the model cannot know). A nested run (1.8) is entered with a lower stack
pointer and starts with nothing known.

### 1.3 Which object a name means

Objects are found through the name table (`ref_objects.NameTable`; 512 slots, keys at
0x5f76f8, objects at 0x5f7ef8), by `world_findObjectsByName(name, out, limit)` 0x14bf58 or
its first-match wrapper `world_findObjectByName` 0x14f498 (which asks for limit 2).
Executed against `ref_objects.NameTable` on 400 random tables (several objects per name,
removed entries, mixed case): the same objects in the same order.

- The slot is a hash of the name with upper case folded to lower; the walk goes slot by
  slot from there and ends at the first slot that never had a key. A slot counts when its
  key equals the name ignoring case and its object is still there.
- The result is in **slot order**. An object entered later normally lands in a later slot,
  so the order is the order in which the objects were entered (the order of the level's
  object records); the exception is an object that takes over the slot of a destroyed
  object of the same name, which then comes first.
- At most limit − 1 objects are returned, zero-terminated. The limits the built-ins use:
  0x200 (511 objects) for the creature built-ins, 100 (99) for `trigger`,
  `autoPropSetState`, `autoPropGetState` and `showOnMap`, 0x80 (127) for
  `countLiveObjects`, 0x19 (24) for `deleteObjects`.
- "The first creature named X" (`getHitPoints`) is the first entry with object flag 0x20
  among up to 511; "the first object named X" (the first-match wrapper) is the first entry
  whatever it is. Built-ins that take the first object and then test its kind
  (`setHitPoints`, `autoPropGetState`, `particleMorph`) do nothing when a different kind of
  object with the same name comes first.

Most built-ins that take one object do **not** test for "not found"; section 3 says for
each what happens. Where it says "no null check" the original reads and writes through
address 0 plus a field offset (the interpreter stops there, as the model does; what a
console does with those addresses was not established).

### 1.4 The two implicit arguments

Entry points take no arguments; two globals carry the context.

**Selected object** `g_scriptSelectedObj` 0x4039f8 — set around a script run by whoever
starts it for an object (1.9) and 0 otherwise. Read by `selectSetMonsterVal`,
`selectSetCFlag`, `selectSetOFlag`, `selectFollowPath`, `selectStopPath`,
`selectDropItem`, `initScriptSetParams`, `newWorldParameter`, and by
`script_setNextWorld` (so by `newWorld`). No built-in writes it.

**Active player** `g_scriptActivePlayer` 0x4d8ae4 — a player index. Its writers (Observed
unless marked; the list is that of `docs/script.md` 2.3 and FINDINGS D20):

| Writer | Where | Value |
|---|---|---|
| `Trigger_run` | 0x1ed15c | the lowest-numbered player inside, when the trigger's change counts as an entry (1.9); not written on an exit |
| `Player_interact` | 0x1b2b70 | the player who used something, when the object's prompt allows it |
| `Creature_interact` | 0x116d28 | the player who talks to the NPC, before its `dialogScript` |
| `dialog_free` | 0x22fa34 | 0, at level teardown |
| `dialog_runTask` | 0x2301b8 | flips 0/1, offline only |
| `setBestActivePlayer` | 0x1470e0 | Executed: 1 when player 0 has no object or is dead and there are exactly two players, else 0 |
| `playGotItemSound` | 0x1464e8 | Executed: clamped to 0..1 and stored (a 2 or 3 becomes 1 for every later reader) |

Nothing resets it between scripts: a deferred call, a post action or a death script sees
the value the last writer left. Readers among the built-ins: the newWorld gate (1.10),
`startDialog` (which machine sends, and the value in the message), `activateMissionMenu`
and `activateStore` (offline only), `playGotItemSound`, `activePlayerIsDwarf`,
`putPlayersInVehicle`. None of them checks its range; `activePlayerIsDwarf` and the gate
index the player array with whatever is there.

### 1.5 Quest variables

One packed table at `g_questVars` 0x86da80 (0x2000 bytes to the next global, no bounds
check): entries of *name*, a zero byte, one signed value byte; an empty name ends the
table. Functions (all Executed, 300 random sequences):

| Function | Behaviour |
|---|---|
| `vars_get(name)` 0x1ed778 | The name is copied and lower-cased (ASCII upper case + 0x20). Entries are compared with `strcmp` from the start of the table. Found: the value byte, sign-extended. **Not found: the name is appended with value 0** and 0 is returned — a read changes the table. |
| `vars_set(name, value)` 0x1ed854 | The value is clamped to −128..127 first. Same search; a new name is appended. The value byte is stored. |
| `vars_clearAll()` 0x1ed728 | Every value byte becomes 0. **The names stay**, in the same order. |
| `vars_getByIndex(i, &value)` 0x1ed974 | The *i*-th entry in table order (name pointer and value), or null; the save builder's reader. |

Appending writes the name, its terminator and the value byte and nothing else: the table's
end marker is whatever follows, so the area must be zero beyond the last entry (it is in
the executable's zeroed data, and nothing shortens the table).

Built-ins: `getv`, `setv`, `addv` (get, add as 32-bit, set, and the unclamped sum is the
result). Names are case-insensitive for scripts because of the lower-casing; a name with a
character of 0x80 or above indexes the C library's character table with a negative number
(the model refuses).

Who clears (Observed, not executed):

- **An act change** — `mainloop_loadRequestedWorld` 0x320f8c–0x321020: outside the front
  end, when `save_actChanged(pending level)` 0x217f70 is non-zero, the card latch 0x4f8f28
  is clear and no death task runs: `save_clearBuffer(0)`, `jumpgate_resetDestinations` for
  the new act, `quest_clearAll` (the players' quest lists), `player_removeFlag39Items` for
  every player, 0x4f7118 = 1, and `vars_clearAll`. So every quest variable reads 0 after an
  act change but keeps its place in the table. (A machine whose card latch is stuck skips
  all of it: FINDINGS B10, B11.)
- `game_resetState` 0x1e6f58 (a fresh net launch): `quest_clearAll`, `script_resetState`,
  `vars_clearAll`, then `vars_set("needPlayers", 1)`.
- `save_load` 0x221d60: `script_clearDeferred`, `vars_clearAll`, then `vars_set` for every
  variable in the save.

**Profile variables** (`getpv`, `setpv`) use the same format in a second table at
0x4f9030, this machine's profile. `profile_getVar` 0x22289c appends an unknown name with 0
like `vars_get`. `profile_setVar(name, value, save)` 0x22274c clamps, and when the name is
new or the stored value differs it stores and, with `save` set (as `setpv` passes), calls
`memcard_requestConfigSave`; an equal value does nothing at all.

### 1.6 Deferred calls and the per-tick script task

State: `g_scriptDeferNames` 0x86b278 (two halves of 64 names × 0x50 bytes),
`g_scriptDeferCount` 0x86da78 (names in the half being run), `g_scriptDeferQueued`
0x86da7c, `g_scriptDeferFlip` 0x4f8690 (its low bit selects the half being run).

```
script_queueDeferred(name)                  // 0x1ed52c, script addDeferedCall
    if queued < 64:
        strcpy(names[(flip & 1) ^ 1][queued], name);  queued += 1
    // a 65th name in one tick is dropped without notice

script_runDeferred()                        // 0x1ed5a0, run task "Script", priority 125
    for i = 0; i < count; i++:              // count is read again after every run
        script_runByName(names[flip & 1][i])
    count = queued;  queued = 0;  flip += 1
```

A name queued while the task runs goes to the other half and runs on the next tick, never
in the same one. A name of 0x50 bytes or more runs into the next name. The task is
registered by `script_init` 0x1eda40 and also called once from `mainloop_runSession` right
after a level load (Observed). `script_clearDeferred` 0x1eda08 zeroes the three counters
(level teardown, save load); `script_resetState` 0x1eda78 does that and empties the post
action. The task runs while the game is paused, which is why scripts test `gamePaused()`
themselves (`docs/script.md` 2.6).

### 1.7 The post action

One name at `g_scriptPostAction` 0x86fa80. `script_setPostAction` 0x1eda9c (`postAction`)
copies it; a second call replaces the first. `script_runPostAction` 0x1edac0:

```
if name is not empty:
    copy the name;  name = "";  g_scriptInPostAction (0x4f8698) = 1
    script_runByName(copy)
    g_scriptInPostAction = 0
```

The buffer is emptied before the run, so the script may set a new post action for the next
time. The flag is what lets `newWorld` skip its net gate (1.10). Callers of
`script_runPostAction` (Observed): `cut_runFrame` when a cutscene ends (0x199f6c), the
dialog-end handler (0x22f7f0), `game_loadLevel` at the end of a load (0x1e60b8 — a name
left over from the previous level runs in the new one, FINDINGS E10), and `help_task`
(0x1dcf60 offline only; 0x1dd1f0 with no network test, from a draw task, FINDINGS E9).

### 1.8 Running an entry point

```
script_runByName(name)                      // 0x1ed694
    if name == null or g_scriptMachine == 0: return -1
    if scr_findEntry(machine, name, &index) fails:
        if g_scriptMissingStamp (0x4f8694) < g_drawFrame (0x44fdd0):     // signed
            g_scriptMissingStamp = g_drawFrame + 20
        return -1
    result = 0
    scr_interpret(machine, &result, index, 0, null)     // its error code is dropped
    return result
```

The entry lookup is case-sensitive. A run may start from inside a built-in — `callScript`,
or a built-in whose effect runs a script (`grantBronze` / `grantSilver` / `grantGold`) —
and then uses the script stack below the caller's, as `docs/spec/script-machine.md`
describes. Executed: 200 direct runs, 250 runs of the deferred task (1 to 3 ticks), 200 of
the post action, all with nested built-ins.

### 1.9 Who starts scripts for an object

Observed (read, not executed; the full list of about 50 call sites is `docs/script.md`
2.2). The three that set the implicit arguments:

**`Trigger_run` 0x1ecf3c** (a Trigger's turn in `runObjects`):

1. Once: a box query over the trigger's rectangle looks for an object of one class
   (type-info 0x3c3788, the trigger's parameter object) and links the two (+0x6c here,
   +0x4c there).
2. A delay at +0x64 counts down first; while it is non-zero nothing else happens.
3. +0x68 = −1. For each player slot from 0 with an object, the trigger's virtual slot 17
   ("contains") is asked; the **first** player inside wins: if the recall countdown
   0x41b51d is running the function returns; otherwise "inside" is true, +0x68 = that slot.
4. If "inside" equals the stored state +0x60, return. So a script runs on a change only.
5. A linked parameter object can override the direction: a non-zero `onOnly` property
   makes the change count as an entry whichever way it went, a non-zero `offOnly` as an
   exit (it wins when both are set). The parameter object's `action` scripts are then run
   by `obj_runActionScripts(parameters, raw = entry)`.
6. `g_scriptSelectedObj` = the trigger. Entry: `g_scriptActivePlayer` = the slot from
   step 3 — 0 when nobody is inside, which `onOnly` makes possible — then
   `script_runByName(name at +0x5c)`. Exit: `script_runByName("not" + name)`; the active
   player is not written. Then the selected object = 0 and +0x60 = "inside".
7. Only with `onOnly` / `offOnly`: the state +0x60 is forced back to "outside", and the
   delay word +0x64 becomes the `timeout` property × 4 when that is non-zero (unless the
   word already is −1); without a timeout it becomes −1, which never counts down to 0 —
   except that with `needScriptHit` and a script result of 0 it is left alone, so the
   trigger fires again at the next change.

**`MonsterTrigger_scan(trigger, script)` 0x1ed388**: +0x50 = 0; a box of ± the radius
(+0x4c) around the trigger; for each of up to 127 objects that is a living creature and
not a player (flags 0x20 set, 0x8 and 0x40 clear) and, if the trigger has a `monstername`
property, whose `name` property equals it ignoring case: +0x50 += 1, and when a script
name was given: selected object = that creature, run the script, selected object = 0.
`MonsterTrigger_count` 0x1ed4e4 (`monstersInTrigger`) rescans without a script when the
trigger has no `script` property and returns +0x50.

**`obj_runActionScripts(obj, raw)` 0x14dcc8**: selected object = obj; for n = 0, 1, …: the
n-th `action=` property; `raw` runs its value as an entry point, otherwise "not" + value;
the selected object = 0 when the properties run out. The list is read again for each n, so
a script that changes the object's properties changes what runs.

Creature events (`initScript`, `deathScript`, `resurrectScript`, `dialogScript`,
`followLostScript`, `followFoundScript`) set the selected object to the creature in the
same way. Deferred calls and post actions run with the selected object 0.

### 1.10 Changing level

A level change is a name in `g_pendingLevel` 0x41b6d0 (0x50 bytes) and an entrance
orientation byte at 0x41b720; the main loop acts on a non-empty name between ticks
(FINDINGS E1).

```
newWorld_netGate()                          // 0x143d04 -> 1 to refuse
    if g_networkMode and g_scriptActivePlayer != -1:
        cooldown = players[active].+0x4bca                  // 16 bits
        if cooldown != 0 and g_alivePlayerCount >= 2:
            if net_isLocalSlot(active):                     // HUD only
                hud_showMessage(text_lookup(<refusal key at 0x531280>), 180,
                                net_getLocalPlayerSlot(0), 0)
            return 1
        cooldown = 600
    return 0

script_setNextWorld(name)                   // 0x1472c4
    strcpy(g_pendingLevel, name)
    found = false
    if g_scriptSelectedObj != 0:
        for each property of it:                            // no null check on the list
            if strncmp(property, "orientation=", 12) == 0:  // case-sensitive
                found = true;  orientation byte = atoi(property + 12)   // last one wins
    if not found: orientation byte = 0xff
```

`newWorld(level)` and `newWorldAlways(level)` (the same handler, 0x143dd0): convert the
string; then, **unless `g_scriptInPostAction` is set**, ask the gate; if not refused:
`net_closeLocalMenus(0)`, `script_setNextWorld(level)`. `simpleNewWorld` is the same with
"orientation byte = 0xff; strcpy(g_pendingLevel, level)" in place of the last call.
`newWorldParameter` has no gate and takes the name from the selected object's first
`level=` property. `newWorldPost` only copies the name to 0x4fdcf0; the dialog-end handler
moves it (Observed, 0x22f7c8).

Net-game consequences, all Executed in the handler and gate: the cooldown belongs to the
active player (1.4), not to the player who caused the script; the refusal needs two living
players; a level change made from a post action (after a cutscene or dialog) is never
gated; the refusal text appears only on the active player's machine, the refusal itself is
the same everywhere as long as the active player is. A level name of 0x50 bytes or more
overwrites the orientation byte and the current level name behind the buffer (plain
memory, as the model does it). `script_setNextWorld` also copies the name into a 112-byte
local buffer and, when no orientation was found, appends 17 characters of debug text
there: a name of 95 characters or more (112 with an orientation) overruns that buffer and
the saved registers behind it (Observed; the model refuses).

### 1.11 Campaign state the built-ins wrap

All in the player records (`g_players` 0x4d8af0, 0x4c30 bytes each); Executed, 300 direct
sequences besides the built-in cases.

| Function | Behaviour |
|---|---|
| `mission_isAvailable(d, m)` 0x1bf698 | bit 0 of record 0 +0x4bbf + 13 d + m; 0 when m ≥ 13 (signed test, so a negative m reads in front of the row) |
| `mission_setAvailable(d, m, on)` 0x1bf6d0 | that bit in the first `g_numPlayers` records |
| `mission_isComplete(d, m)` 0x1bf730 | bit 1 of record 0's byte |
| `mission_setComplete(d, m, v)` 0x1bf770 | bit 1 in **all four** records whatever the player count; v = −1 sets it, any other v stores v's bit 0 |
| `mission_grantMedal(m, level)` 0x1bdb80 | m < 13 only. For each of the first `g_numPlayers` players whose medal byte (+0x4c0d + m) is below level: 0x4f7149 (reward player) = that slot; then for each level gained, in order, `script_runByName` of `firstBronze` (from 0), `firstSilver` (from 1), `firstGold` (from 2 or more); then the byte = level |
| `mission_getMedal(m, level, flag)` 0x1bf838 | the medal byte of `net_getLocalPlayerSlot(0)` — of slot 0 when flag is set in a net game. level −1 returns the byte, else whether it has reached level. `getMedal` and `runMedalSuccess` pass (m, −1, 0): **this machine's first local player** |
| `game_getEvil()` 0x1bf8d8, `game_getMadeDecision()` 0x1bf960 | record 0 +0x4c1a / +0x4c1b masked with 1 << `g_difficultyIdx` (the masked value) |
| `game_setEvil(on)` 0x1bf8f8, `game_setMadeDecision(on)` 0x1bf980 | set or clear that bit in the first `g_numPlayers` records |
| `player_setFlag(slot, bit, on)` 0x1be398 | bit (number mod 32, in a byte, so 8 and above do nothing) of record +0x4c28; slot −1 = the first `g_numPlayers` records |
| `player_getFlag(slot, bit)` 0x1bfb80 | the masked byte |
| `quest_add(title, text)` 0x1d386c | Players in order; **the whole call ends at the first player whose list is full (8) or already has the title**; until then each player gets title (+0x41d0 + 0x40 n) and text (+0x20 behind it) appended and the count (+0x43d0) raised. Both are plain string copies into 0x20-byte fields |
| `quest_remove(title)` 0x1d3968 | Per player: every entry with that title has both strings overwritten with a nine-byte placeholder; then the entries behind the **last** match move up one place and the count drops by one — only one, however many matched |
| `game_countPlayersWithHp()` 0x1ebec8 | players among the first `g_numPlayers` with hit points (+0xac) above 0 |
| `game_savePlayerRecord()` 0x1ec720 | the medal player's (0x4f7148) whole record → `save_playerCopy(slot)`; 0x4f85c0 = 1 |
| `game_restorePlayerRecord()` 0x1eb6f8 | the copy comes back except five fields that keep their live values: +0x4c0d (8 bytes, medals), +0x4c15 (4 bytes), +0x4c19, +0x78 (24 bytes), +0x43d8 (object). Then 0x4f7194 (16 bits) = 240, the four 16-bit death countdowns at 0x4f84a8 = 240, `game_rebuildAlivePlayers`, 0x4f85c0 = 0 |
| `dialog_start(name, a, b)` 0x22fa50 | section 4, `startDialog` |

### 1.12 Call-outs

Everything else a built-in calls is outside this model: it is recorded with its arguments
and answered by the caller of the model. `ref_natives.EXT` has the complete list (96
functions with address and argument registers) and `ref_natives.VIRTUAL` the ten virtual
slots used. The object-system call-outs (`obj_moveOffGrid`, `obj_updateGridCell`,
`obj_runEveryFrame`, the box query, the grid walk, the class query, and the destructor
slot) are modelled by `tools/ref_objects.py` and wired to it by default; inventory, items,
spells, sound, HUD, camera, cutscene, save and net messages are plain call-outs.

Virtual calls go through the table at object +0x48: function pointer at table + 8 × slot
+ 4, a 16-bit this-adjustment at table + 8 × slot. Slots used: 1 destroy (argument 3 =
destroy now and free), 2 take damage (amount in a float register, two zero arguments),
3 trigger, 14 interact, 17 contains, 18 set auto-prop state, 19 seat position, 27 set AI
state, 34 set home range; and slot 8 of the object at creature +0x50 (set weapon type),
whose table is at its +0. Class tests (`generateMonster`, `monstersInTrigger`,
`setContainerProps`, `objInPlayerTrig`, `reapEnemies`) call slot 0 for the type-info
object and compare names.

## 2. How often the shipped scripts call each built-in

Counted from the SYSREQ.C instructions of the 120 shipped scripts (5,660 calls, 122 of the
191 built-ins; "levels" is the number of scripts with at least one call).

| Calls | Built-ins (calls / levels) |
|---|---|
| 300 and more | getv 790/64, setv 571/73, hideMonster 373/48, callScript 357/63 |
| 100–299 | addDeferedCall 278/61, newWorld 163/71, removePlayerItem 147/34, generateMonster 136/11, getRand 130/27, getMissionAvailable 129/3, getMissionComplete 115/13, setMonsterVal 114/16, gamePaused 108/40, postAction 105/45 |
| 40–99 | setInfo 95/25, setMissionAvailable 88/23, setEntrance 76/30, addHelpMessage 65/47, getEvil 63/19, autoPropSetState 62/13, playerHasItem 61/20, countQuestItems 61/13, cutScene 58/43, setCreatureParams 56/13, addParticleOnObject 54/13, showMonster 52/23, startDialog 45/24, activateStore 45/4, stopFollowingPath 45/1, setSaveInhibit 44/33, addQuest 43/20, changeSwoop 43/3 |
| 20–39 | onePlayerHasItem 36/32, savePlayer 36/9, restorePlayer 36/9, sin1000 35/6, cos1000 35/6, grantMission 33/32, deleteMonster 33/8, getNumPlayers 33/15, print 31/3, printVal 31/3, showBust 31/17, removeQuest 30/19, runMedalSuccess 30/9, trigger 29/17, followPath 28/8, soundSequence 27/26, setpv 27/9, playerAdjustStat 27/9, getScaledTime 26/16, getHitPoints 25/2, showOnMap 24/4, charmMonster 20/4 |
| 10–19 | setCFlag 18/14, saveCheckPoint 16/15, rootMonster 16/7, increaseEnemyRank 15/3, killMonster 15/5, setParticle 14/13, friendly 13/4, preloadResource 13/13, initScriptSetParams 13/6, setPlayerFlag 12/8, hitPlayers 11/3, selectStopPath 11/4, countPlayersAlive 11/10, setWeaponType 10/5, givePlayerItem 10/6, monstersInTrigger 10/3, runMedalFail 10/9 |
| 1–9 | grantGold, grantSilver, grantBronze, getMedal, setAlternateDeath, selectDropItem (9 each, 9 levels); selectSetMonsterVal 9/3; unRootMonster 8/3; getPlayerFlag 7/4; addHelpMessageF 7/3; demoRunning 7/5; saveDone 6/3; unFriendly 6/1; dropItem 6/6; setContainerProps 6/3; newWorldPost 5/3; leaveGame 5/3; simpleNewWorld 4/1; activateMissionMenu 4/2; givePlayerGold 4/2; checkPlayerGold 4/1; shakeCamera 4/2; getMadeDecision 4/3; findDistance 4/4; startWithSwoopDone 3/2; moveMonster 3/2; selectFollowPath 3/3; playGotItemSound 3/3; saveGame 3/3; saveEndConfig 3/3; showCompass 3/3; networkMode 3/2; revealMap 3/3; giveOnePlayerItem 2/1; closestPlayerDist 2/1; zeroPlayerMana 2/2; getMaxPlayerHP 2/2; setEvil 2/1; setMadeDecision 2/1; clearAllSkills 2/2; refillPlayerMana 2/2; takePlayerGold, reapEnemies, getHealthUsed, explodePotionsOnly, setWaveDetail, removeAllItems, piercePlayerEar, giveFullHealth, isClericOrWizard, removeAllWeapons (1 each) |
| never | the other 69: newWorldAlways, newWorldParameter, addv, getpv, sound, startMusic, startAudio, endMusic, lightEffect, all vehicle built-ins, givePlayerRandom, givePlayerExp, hornOmen, planarSteel, particleMorph, healPlayer, the prop and NPC animation built-ins, and the rest marked 0 in section 3 |

## 3. The built-ins

Conventions. **#** is the index in the table 0x403370 (entry at 0x403370 + 8 #). Arguments:
`s` a string (1.2), `i` an integer cell, `ref` the address of script cells. "→" gives the
result; no arrow means 0. "rec" is a player record (`g_players[n]`, 0x4d8af0 + 0x4c30 n),
"all players" the first `g_numPlayers` records, "creatures named X" the objects of
`world_findObjectsByName(X, 0x200)` that have object flag 0x20 — in table order (1.3).
Calls to code outside the model are written `name(arguments)` and are made in the order
given; "float" arguments are the integer cell converted with the CPU's int-to-float.
The last column is calls / levels in the shipped scripts. Everything in these tables is
Executed (section 8) unless a row says otherwise.

### 3.1 Script control and pure helpers

| # | Built-in (handler) | Arguments → result | What it does | Calls |
|---|---|---|---|---|
| 0 | `callScript` 0x143158 | s entry → the run's result | `script_runByName(entry)` (1.8): −1 for an unknown name, 0 for a run that ended in an error. Nested on the same machine. | 357/63 |
| 104 | `addDeferedCall` 0x144160 | s entry | `script_queueDeferred(entry)` (1.6). | 278/61 |
| 106 | `postAction` 0x143ee4 | s entry | `script_setPostAction(entry)` (1.7). | 105/45 |
| 1 | `print` 0x143120 | s text | Converts the string, nothing else. | 31/3 |
| 2 | `printVal` 0x143150 | i | Nothing. | 31/3 |
| 87 | `getRand` 0x146570 | → 0..65535 | **One shared-seed draw**: seed = seed × 0x19660d + 0x3c6ef35f; result = seed >> 16. | 130/27 |
| 13 | `getScaledTime` 0x14412c | i n → i | (int)((float)n × 60.0 × 0x3c888888). The constant is 1/60 rounded down, so the result is n − 1 for most n (FINDINGS R17). | 26/16 |
| 161, 162 | `sin1000` 0x141fb0, `cos1000` 0x141fe0 | i angle (16 bits = a turn) → i | (int)(`math_sin16` / `math_cos16`(angle) × 1000.0); the angle functions are those of `ref_core`. | 35/6 each |
| 90 | `gamePaused` 0x14699c | → 0/1 | 1 if `g_paused` 0x41b4f4, or the jump-gate travel word 0x500ae8, or `g_cutsceneActive` 0x44fcd0 is non-zero. | 108/40 |
| 178 | `demoRunning` 0x141764 | → 0 | Constant. | 7/5 |
| 143 | `networkMode` 0x142214 | → flag | `g_networkMode` 0x402791 (a signed byte). | 3/2 |
| 92 | `levelLoading` 0x146aa4 | → i | The word at 0x4f7198. | 0 |
| 146 | `getLevelTimer` 0x1421a8 | → i | (int)((float)(unsigned)counter 0x4f85cc × 0x3c888888). | 0 |

### 3.2 Quest variables, profile variables, campaign progress

| # | Built-in (handler) | Arguments → result | What it does | Calls |
|---|---|---|---|---|
| 81 | `getv` 0x143500 | s name → −128..127 | `vars_get` (1.5). Appends an unknown name. | 790/64 |
| 83 | `setv` 0x143540 | s name, i value | `vars_set`: clamped. | 571/73 |
| 84 | `addv` 0x143588 | s name, i delta → sum | `vars_get`, 32-bit add, `vars_set`; the result is the sum before clamping. | 0 |
| 86 | `getpv` 0x143480 | s name → −128..127 | `profile_getVar` (1.5): this machine's profile table. | 0 |
| 85 | `setpv` 0x1434b4 | s name, i value | `profile_setVar(name, value, 1)`: `memcard_requestConfigSave()` when the name is new or the stored value differs. | 27/9 |
| 147 | `getEvil` 0x142044 | → masked byte | `game_getEvil` (1.11): 0 or 1 << difficulty. | 63/19 |
| 148 | `setEvil` 0x142058 | i on | Only when on ≠ 0: `game_setEvil(on)`. There is no way to clear the flag from a script. | 2/1 |
| 149 | `getMadeDecision` 0x142010 | → masked byte | `game_getMadeDecision`. | 4/3 |
| 150 | `setMadeDecision` 0x142024 | – | `game_setMadeDecision(1)`. | 2/1 |
| 151 | `grantMission` 0x1420a4 | i mission | `mission_setComplete(difficulty, mission, −1)`: all four records. | 33/32 |
| 152 | `getMissionComplete` 0x142084 | i mission → 0/1 | `mission_isComplete(difficulty, mission)`. | 115/13 |
| 153 | `setMissionAvailable` 0x1420d0 | i mission, i on | `mission_setAvailable(difficulty, mission, on)`: bit 0 of on. | 88/23 |
| 154 | `getMissionAvailable` 0x1420fc | i mission → 0/1 | `mission_isAvailable(difficulty, mission)`. | 129/3 |
| 155–157 | `grantGold` 0x14211c, `grantSilver` 0x142140, `grantBronze` 0x142164 | i mission | `mission_grantMedal(mission, 3 / 2 / 1)` (1.11): sets the reward player and runs `firstBronze` / `firstSilver` / `firstGold` for every level each player gains. | 9/9 each |
| 158 | `getMedal` 0x142188 | i mission → 0..3 | `mission_getMedal(mission, −1, 0)`: the medal of **this machine's first local player** (`net_getLocalPlayerSlot(0)`). | 9/9 |
| 64 | `addQuest` 0x1433c8 | s title, s text | `quest_add` (1.11). | 43/20 |
| 65 | `removeQuest` 0x143448 | s title | `quest_remove` (1.11). | 30/19 |

A mission number of 13 or more does nothing in all of these; the test is signed, so a
negative number addresses bytes in front of the mission row.

### 3.3 Level flow, cutscenes, dialog, saving

| # | Built-in (handler) | Arguments → result | What it does | Net game | Calls |
|---|---|---|---|---|---|
| 7, 8 | `newWorld`, `newWorldAlways` 0x143dd0 | s level | 1.10: gate unless in a post action; then `net_closeLocalMenus(0)`, `script_setNextWorld(level)`. | gate; `net_closeLocalMenus` acts only in net games | 163/71, 0 |
| 6 | `simpleNewWorld` 0x143e70 | s level | Same gate; then `net_closeLocalMenus(0)`, orientation byte = 0xff, `strcpy(g_pendingLevel, level)`. | as above | 4/1 |
| 9 | `newWorldPost` 0x143cc4 | s level | `strcpy(0x4fdcf0, level)`. | – | 5/3 |
| 107 | `newWorldParameter` 0x1471fc | – | The selected object's first property that starts with `level=` (6 characters, case-sensitive): `net_closeLocalMenus(0)`, `script_setNextWorld(rest of it)`. No property: nothing. No gate. No null check on the selected object or its property list. | – | 0 |
| 121 | `setEntrance` 0x142a94 | s name | `strcpy(0x4f8468, name)`. | – | 76/30 |
| 105 | `cutScene` 0x143f1c | s name | `cut_start(res_find("<level>.lmp", "<name>.cut"), "<name>.cut")`, level = the current level name 0x41b721. A resource that is not found is passed on as 0. | – | 58/43 |
| 15 | `startDialog` 0x143824 | s name, i a, i b | `lump_load("<level>.lmp")`, then `dialog_start(name, a, b)`: `Camera_update(local camera 0x4f8450)`; 0x4fdce8 = 0; then, **only if `net_isLocalSlot(active player)` and no dialog is open (0x8e2d60 = 0)**: `net_sendGameMsg(id at 0x8e2e94, message, length)` with message = 0, strlen(name), name, 0xff bytes up to a multiple of 4, active player, a, b, 0 (one byte each), this machine's camera position 0x44f038 (12 bytes), `Camera_getYaw`, `Camera_getPitch` (16 bits each). The dialog itself opens when the message is processed. | one machine sends, with its own camera | 45/24 |
| 18 | `dialogRunning` 0x143cb0 | → i | `dialog_isOpen()`'s result. | – | 0 |
| 103 | `forceMutexRelease` 0x1471dc | – | `menuMutex_release()`. | – | 0 |
| 16 | `changeSwoop` 0x1438b0 | i mode | 0x4fdce4 = mode. | – | 43/3 |
| 17 | `startWithSwoopDone` 0x1438c4 | – | 0x4fdce8 = 1. | – | 3/2 |
| 70 | `leaveGame` 0x146ab0 | i how | Session exit code 0x41b508 = 1 when how = 0, else 0x65. | – | 5/3 |
| 79 | `exitToMainMenu` 0x146d80 | – | 0x41b508 = 1. | – | 0 |
| 71 | `endGame` 0x146ad4 | – | `memcard_requestEndGameSave(0, 1)`. | – | 0 |
| 76 | `saveGame` 0x146c04 | – | If any player's status word (rec +0x4c1c) has 2 in its low five bits: nothing. Else `memcard_requestSave(net_getLocalPlayerSlot(0))`. | this machine's first local player | 3/3 |
| 77 | `saveEndConfig` 0x146c78 | – | `game_sendCharacterToLobby(−1)`; bytes 0x4d8a08 and 0x4039c0 = 0; 0x41b4f8 = 1; byte 0x4f85c5 = 1; `g_paused` = 1; in a net game `net_dropAllRemotes()`; 0x4f8f38 \|= 8, 0x10, 0x20, 0x40 for difficulty 1, 2, 3, 4 (nothing for 0); `memcard_requestConfigSave()`. | drops every remote peer | 3/3 |
| 78 | `saveDone` 0x146d5c | → 0/1 | 1 when `memcard_getState()` is −1. | this machine's card | 6/3 |
| 132 | `saveCheckPoint` 0x142a40 | – | `dbg_printf(0x531250)`, `save_game(0, 0, 1)`. | – | 16/15 |
| 133 | `loadCheckPoint` 0x142a74 | – | `deathTask_schedule(0)`. | – | 0 |
| 138, 139 | `setSaveInhibit` 0x1473b4, `getSaveInhibit` 0x1473c8 | i on / → i | The word 0x50605c. | – | 44/33, 0 |
| 172 | `setAlternateDeath` 0x141790 | – | 0x4f712c = 1. | – | 9/9 |
| 137 | `preloadResource` 0x14222c | s lump | `lump_load(lump)`. | – | 13/13 |
| 72 | `clearRecall` 0x146af8 | – | The five bytes of the word "None" and its terminator over rec +0x24 of all players. | – | 0 |
| 112 | `playersLoaded` 0x147278 | → 0/1 | 1 if any of the players has an object pointer (rec +0x43d8). | – | 0 |
| 91 | `pauseGameControl` 0x1469f0 | i frames | 0x41b4fc = frames, 0x41b500 = 1. | (`tasks_run` zeroes the first in a net game: Observed, `docs/script.md`) | 0 |

### 3.4 Menus, HUD, medal results

| # | Built-in (handler) | Arguments → result | What it does | Net game | Calls |
|---|---|---|---|---|---|
| 10 | `activateMissionMenu` 0x143fa8 | – | Nothing if `dialog_isOpen()` or the recall countdown 0x41b51d is non-zero. Else `missionMenu_open(slot)`, slot = the active player offline, `net_firstActiveSlot()` in a net game. | slot from peer state | 4/2 |
| 11 | `activateStore` 0x144010 | i store | If store < 21 (unsigned): 16-bit 0x4f7150 = store. If `dialog_isOpen()`: byte 0x4fdd30 = 1 and nothing else. Offline: `shop_openOrStock(active player, 0, 1)`. Net: for each entry of the alive list, in order: if `net_isLocalSlot(slot)`: `net_closeLocalMenus(0)`, `shop_openOrStock(slot, 0, 1)`. | only machines with a living local player call `net_closeLocalMenus(0)`, which also empties vehicles | 45/4 |
| 12 | `storeRunning` 0x1440f8 | → i | `g_shopOpen` 0x41b50c. | per machine | 0 |
| 62 | `setInfo` 0x14318c | s key | `hud_showMessage(text_lookup(key), 180, −1, 0)`. | – | 95/25 |
| 63 | `addHelpMessage` 0x1431d8 | s titleKey, s bodyKey | Both strings are converted, then `text_lookup(title)`, `text_lookup(body)`, `hud_showHelpMessage(−1, title, body)`. | inside the call-out | 65/47 |
| 164 | `addHelpMessageF` 0x143270 | s key1, i v1, s key2, i v2 | `wstr_format(buffer1, text_lookup(key1), (float)v1, 0.0 × 7)`; the same for key2 / v2 into buffer2; `wstr_copy(0x5d3048, buffer1)`, `wstr_copy(0x5d3088, buffer2)`; `hud_showHelpMessage(−1, 0x5d3048, 0x5d3088)`. | – | 7/3 |
| 163 | `helpMessageActive` 0x1433bc | → i | The signed byte 0x41b928. | per machine | 0 |
| 127 | `showCompass` 0x1427b4 | s object, s key | `hud_setCompassTarget(position of the first object named so, text_lookup(key))`. **No null check.** | – | 3/3 |
| 128 | `showBust` 0x142864 | s texture, s key, i a, i b | `hud_setBust(texture, text_lookup(key), a, b)`. | – | 31/17 |
| 122 | `hudResetFadeScreen` 0x14277c | i on | `hud_setFade(on)`. | – | 0 |
| 123 | `hudFadeScreen` 0x14279c | i delta → i | `hud_stepFade(delta)`'s result. | – | 0 |
| 165 | `revealMap` 0x141e78 | – | `automap_revealAll()`. | – | 3/3 |
| 166 | `showOnMap` 0x141e98 | s name, i on | For the creatures among the first 99 objects of the name: bit 43 of the creature flag word (+0xa8) set (on ≠ 0) or cleared. | – | 24/4 |
| 170 | `runMedalSuccess` 0x1417a4 | i mission, i old, s title, s line1, s line2, s line3 → 0/1 | See below. | see below | 30/9 |
| 171 | `runMedalFail` 0x141c00 | s key → 0/1 | See below. | see below | 10/9 |
| 117, 118 | `setupPlayerSel` 0x142bb8, `startPlayerSel` 0x142bc0 | – | Nothing. | – | 0 |
| 119 | `playerSelRunning` 0x142bc8 | → i | `playerSel_isRunning()`'s result. | – | 0 |

**The medal screens** are meant to be called every tick until they return 1. Both:

```
0x4f7114 = 2                                            // every call
offline:   g_paused = 1;  if memcard_isBusy(): return 0;  show = true
net, medal player (byte 0x4f7148) == net_getLocalPlayerSlot(0):
           if memcard_isBusy(): return 0
           if ack word 0x4f7140 == 0: hudmsg_sendMedalAck(); return 0     // game message 12
           show = true
net, other machines:
           if ack == 0: return 0
           show = not memcard_isBusy()
if show: <draw, below>
pressed = g_pads[medal player].+0xc                     // lockstep pad word
if pressed & mask at 0x41bfbc:  strcpy(g_pendingLevel, current level name);
                                orientation byte = 0xff;  return 1      // restart the level
if pressed & mask at 0x41bfb8:  game_openMissionMenu();  return 1
return 0
```

The drawing of `runMedalFail`: convert the key; the prompt (below); `text_lookup` of the
title key at 0x531240, `text_lookup(key)`; `hud_drawMessageBox(title, body, prompt, 0x80,
0, 0, 0, −1, 0, 0)`.

The drawing of `runMedalSuccess`: `text_begin(font 0x4f7104, 6, 0x80323c3c, −1)`; medal =
`mission_getMedal(mission, −1, 0)` (this machine's player); the four texts are converted
in order, and text 0 (the title) and each text k = 1..3 with old < k ≤ medal (and old <
medal) is looked up and measured — `text_drawWrappedCentered(0x140, 0xdc, text, 0x15e, 100,
100, 0x11)` — giving a height of result + 0x22 for the title and result + 0x11 for a line,
and a total of the heights + 0x11 each. Then the title is drawn at y = 0xd8 − total / 2
(`text_drawWrappedCentered(0x140, y, text, 0x15e, −100, 0x244, 0x11)`, after a second
`text_lookup`) and below it the measured lines **in the order 3, 2, 1**, each advancing y
by its height; `text_end()`; the prompt; `text_lookup` of the title key at 0x531220;
`hud_drawMessageBox(title, 0, prompt, 0x80, 400, total, 0, −1, 0, 0)`.

The prompt exists only offline or where `net_getLocalPlayerSlot(0)` is the medal player:
`text_lookup` of the key at 0x531230, `wstr_format(0x4f6848, text, (float)word 0x41b978,
(float)word 0x41b97c, 0.0 × 6)`, and 0x4f6848 is passed to the box; elsewhere 0 is passed.

What matters for lockstep: the result and the two shared writes (pending level, mission
menu) are decided after a per-machine early return. On the medal player's machine the
function returns 0 without looking at the pad whenever its memory card is busy, while the
other machines test the pad once the acknowledge has arrived (`docs/script.md` P2).
Offline `g_paused` is set on every call, also on the calls that return early.

### 3.5 Players

| # | Built-in (handler) | Arguments → result | What it does | Calls |
|---|---|---|---|---|
| 82 | `getNumPlayers` 0x143534 | → i | `g_numPlayers` 0x4d8ae0. | 33/15 |
| 141 | `countPlayersAlive` 0x142220 | → i | `g_alivePlayerCount` 0x4f8420. | 11/10 |
| 99 | `checkPlayerAlive` 0x1470ac | i which → i | which ≠ 0: whether the 16-bit countdown 0x4f7194 is above 0. which = 0: `game_countPlayersWithHp()`. | 0 |
| 100 | `setBestActivePlayer` 0x1470e0 | → 0/1 | Active player = 1 when player 0 has no object or its object is dead and `g_numPlayers` is exactly 2, else 0; returns it. | 0 |
| 88 | `activePlayerIsDwarf` 0x1465a0 | → 0/1 | rec[active player] +0x54 (model index) is 0. No range check. | 0 |
| 89 | `activePlayerIsElf` 0x1465c4 | → 0 | Constant. | 0 |
| 188 | `isClericOrWizard` 0x1465cc | i player → 0/1 | For player < 4 (unsigned) and ≤ `g_numPlayers`: rec +0x50 (class) is 1 or 4. Player = `g_numPlayers` is accepted. | 1/1 |
| 129 | `getMaxPlayerHP` 0x1428fc | i player (from 1) → i | (int) of rec[player − 1] +0xb0, −1 when out of 1..`g_numPlayers`. | 2/2 |
| 69 | `healPlayer` 0x1468ac | – | `sound_playOnObject(1.0, res_find(lump name 0x531398, entry name 0x5313a0), player 0's object pointer)`; then hit points (+0xac) = maximum (+0xb0) for all players whose hit points are above 0. | 0 |
| 184 | `giveFullHealth` 0x146950 | – | Hit points = maximum for all players, dead or not. | 1/1 |
| 126, 189 | `zeroPlayerMana` 0x142450, `refillPlayerMana` 0x142494 | – | Mana (+0xc0) = 0 / = maximum (+0xc4) for all players. | 2/2 each |
| 125 | `hitPlayers` 0x1424dc | s object, i radius, i damage, i push | For each entry of the alive list, in order (the count is read again each time): the player object p; if sqrt((dx² + dy²) + dz²) < (float)radius (d = p − object): virtual slot 2 of p with (0, 0; amount (float)damage); then p (read again from the record) +0x2e8 = (float)push and 16-bit +0x2e0 = `math_atan2_16(dy, dx)`. **No null check** on the object (when the alive list is not empty) or on a listed player's object. | 11/3 |
| 124 | `closestPlayerDist` 0x14268c | s object → i | (int) of the smallest 3-D distance from the object to a listed player that has an object; 100000 when there is none. No null check on the object when such a player exists. | 2/1 |
| 56 | `givePlayerExp` 0x146278 | i amount | `player_giveExp(slot, amount)` for all players in order. | 0 |
| 57 | `givePlayerGold` 0x1462dc | i amount | Gold (+0xe4) += amount / `g_numPlayers` (C division) for all players, then capped at 99,999,999. | 4/2 |
| 58 | `takePlayerGold` 0x1463ec | i amount | Gold −= amount / `g_numPlayers`, not below 0. | 1/1 |
| 59 | `checkPlayerGold` 0x14644c | → i | The sum over all players. | 4/1 |
| 60 | `checkPlayerMinGold` 0x146494 | → i | The smallest; player 0's with one player or none. | 0 |
| 183 | `playerAdjustStat` 0x146348 | i player, i stat, i count | Only for stat 4..8, count times: player = −1: `inventory_onStatPoint(reward player 0x4f7149, stat)`; any other player: `invmsg_sendStatPoint(player, stat)` — a **message is sent** instead of the change being made. | 27/9 |
| 185 | `setPlayerFlag` 0x1416d4 | i player, i bit, i on | `player_setFlag` (1.11). | 12/8 |
| 186 | `getPlayerFlag` 0x1416fc | i player, i bit → 0/1 | Whether `player_getFlag` is non-zero. | 7/4 |
| 182 | `piercePlayerEar` 0x145610 | i player | Byte rec +0x4c26 = 1 for player 0..3, or for all players with −1; other values nothing. | 1/1 |
| 187 | `clearAllSkills` 0x1458e0 | – | In the **medal player's** record (0x4f7148): 8 bytes at +0x128 = 0; 48 bytes from +0xef = 0; 48 pairs of 16-bit words from +0x4b08 = −1; +0xe8 = 0; byte +0x4a85 = 1; +0x4a80 = 0; byte +0x4a84 = 0; and for the 15 ability records (+0x4460 + 0x68 k): 16-bit = −1, byte at +4 = 0. | 2/2 |
| 180 | `savePlayer` 0x141724 | – | `game_savePlayerRecord` (1.11). | 36/9 |
| 181 | `restorePlayer` 0x141744 | – | `game_restorePlayerRecord` (1.11). | 36/9 |
| 98 | `hidePlayers` 0x147098 | i on | Byte 0x4f83f8 = the low byte. | 0 |
| 101 | `decayPlayerLights` 0x147130 | i t1, i t2, i step → 0/1 | target = (t2 if exactly two players are alive, else t1) × 0.01; s = step × 0.01; float 0x4f83f4 += s (stored); if (s > 0 and target ≤ value) or (s < 0 and value ≤ target): the float = target, result 1. | 0 |
| 66 | `hornOmen` 0x146628 | – | For all players with an object: block = `pool_new(0x20)`; if block: `SpellHornOmenEffect_ctor(block, 1, object, pointer at 0x41b1e4)`; then `creature_addSpell(object, block)` — **also when the allocation failed, with 0**. | 0 |
| 67 | `planarSteel` 0x1466d4 | – | The same with `pool_new(0x6c)` and `SpellPlanarSteelEffect_ctor`; before it, per player, hit points = maximum when above 0. | 0 |
| 144, 145 | `getManaUsed` 0x1421fc, `getHealthUsed` 0x142208 | → i | The 16-bit counters 0x4f85c8 / 0x4f85ca, **sign-extended**. | 0, 1/1 |
| 61 | `playGotItemSound` 0x1464e8 | – | v = active player. Stored back clamped: 0 when negative, 1 when above 1. If `g_numPlayers` ≥ 2 and rec[v] hit points ≤ 0 (v unclamped): v = 1 if the clamped value is 0, else 0. `player_voice(v, 9)`. | 3/3 |
| 169 | `explodePotionsOnly` 0x1433a8 | – | 0x4f7128 = 1. | 1/1 |

### 3.6 Items

The inventory itself belongs to other models; the built-ins contribute the loops and
tests. The "blank item" is a 0x48-byte record on the handler's stack with bytes
+0x10..+0x1f zero, +0x20 and +0x21 0xff, and the 16-bit words at +0x24, +0x2c, +0x34,
+0x3c −1.

| # | Built-in (handler) | Arguments → result | What it does | Calls |
|---|---|---|---|---|
| 50 | `playerHasItem` 0x145590 | s item → i | Sum of `inventory_countItemByName(item, slot)` over all players. | 61/20 |
| 51 | `onePlayerHasItem` 0x145690 | i player, s item → i | 0 unless player < `g_numPlayers` and its object exists and is not dead; then `inventory_countItemByName(item, player)`. The string is converted only then. A negative player passes the test. | 36/32 |
| 140 | `countQuestItems` 0x145720 | s item → i | `inventory_countItemByName(item, 0)`: player 0 only. | 61/13 |
| 52 | `removePlayerItem` 0x14598c | i player, s text | For the player — or with −1 for all players in order —: `inventory_findItemBySubstring(slot, text, &index, &bag)`; if index ≠ −1: `inventory_removeItem(slot, index, bag, 0)`. A player ≥ `g_numPlayers` does nothing; a negative one other than −1 is used as given. | 147/34 |
| 179 | `removeAllItems` 0x145758 | – | **Medal player** (0x4f7148): for bag 0, 1, 2: n = the bag's count (rec +0x130 + 0x1208 b + 0x1200), read once; n times: if the bag's first entry is non-zero, `inventory_removeItem(slot, 0, bag, 0)`. | 1/1 |
| 190 | `removeAllWeapons` 0x145828 | – | The same for bag 0 only; then the three words at rec +0x4434 = 0. | 1/1 |
| 53 | `givePlayerItem` 0x145a88 | s descriptor, i equip, i variant | For each player in order — only the medal player while medal mode 0x4f713c is non-zero —: blank item; `item_parseDescriptor(descriptor, item, −1, variant)`; w = `player_itemWeight(slot, item)`; if carried (+0x120) + w < capacity (+0x124), **or w = 0**: i = `inventory_giveItem(slot, item, 1)`, `player_recalcLoad(slot)`, and if equip ≠ 0: `inventory_equipItem(slot, rec + 0x130 + 0x1208 × (signed byte at definition +0x1d) + 0x48 i, 0)`, `player_resetIdleAnim(slot)`. Otherwise a ground item: `pool_new(400)`, and if it gave a block `ItemProp_ctor2(block, position, item, 0)` at the player's object, or at the object of the first entry of the alive list when the player has none (no null check there). | 10/6 |
| 54 | `giveOnePlayerItem` 0x145d20 | i player, s descriptor, i equip, i variant | Only for player < `g_numPlayers` with a living object. As above without the "w = 0" exception and without `player_resetIdleAnim`; the ground item is at the player. | 2/1 |
| 55 | `givePlayerRandom` 0x145f18 | – | Per player in order: blank item; **one seed draw** d; s = `level_monsterLevelTimesDifficulty()`; budget = (int)((float)d × s × 0x3c75c28f). If the level name contains the fragment at 0x5312a8: for difficulty 1, 2, 3 `item_parseDescriptor(fixed text, item, 0, 0)` and two item bytes are overwritten (other difficulties keep the blank item); then give (`inventory_giveItem`, `player_recalcLoad`) if carried + weight < capacity, else a ground item at the player (no null check). Then up to ten times: **one seed draw** r; `item_generateWithAffixes(item, budget, r & 1, −1, (int)float 0x4f714c)`, stop when it returns non-zero. Then give or drop as before. 2 to 11 draws per player. | 0 |
| 173 | `dropItem` 0x1477ac | s object, s descriptor | `loot_spawnNamedItem(position of the first object named so, descriptor)`; nothing when there is none. | 6/6 |
| 174 | `selectDropItem` 0x147860 | s descriptor | The same at the selected object; nothing when there is none. | 9/9 |

### 3.7 Creatures

"Root" below means: 16-bit +0x314 = −1. AI state is the 16-bit word +0x232; 0x14 is the
death state. The creature flag word is the 64-bit word at +0xa8.

| # | Built-in (handler) | Arguments | What it does to each creature named so (or as stated) | Calls |
|---|---|---|---|---|
| 19 | `increaseEnemyRank` 0x144200 | s name | Flag bit 44 set. | 15/3 |
| 20 | `charmMonster` 0x14429c | s name | `Creature_setCharm(creature, −1, 0)`. | 20/4 |
| 21 | `rootMonster` 0x14433c | s name | Unless AI state is 0x14: root, then virtual slot 27 with 0. | 16/7 |
| 22 | `unRootMonster` 0x144408 | s name | +0x314 = 0. | 8/3 |
| 24 | `setMonsterVal` 0x144550 | s name, i which, i value | `script_applyMonsterVal` 0x144494: which 1, 2, 3, 5 store the low 16 bits at +0x3ac, +0x3ae, +0x3b0, +0x3c4; 4 calls virtual slot 34 with them; any other which does nothing. | 114/16 |
| 23 | `selectSetMonsterVal` 0x144514 | i which, i value | The same on the selected object if it is a creature. **No null check.** | 9/3 |
| 26 | `setCFlag` 0x144714 | s name, i bit, i on | `script_applyCFlag` 0x1445fc: only bits 0 and 26 exist for it. Bit 0: when clearing and flag bit 31 is set, the words 0x41b6a0 and 0x41b6a4 = 0 and bit 31 is cleared; then, set or cleared, `creature_startBossMusic(creature)`; then the bit. Bit 26: the bit. Other bits: nothing. | 18/14 |
| 25 | `selectSetCFlag` 0x1446d0 | i bit, i on | The same on the selected object if there is one and it is a creature. | 0 |
| 28 | `setOFlag` 0x144834 | s name, i which, i on | **Every** object of the name: `script_applyOFlag` 0x1447c4: only which = 14: object flag 0x4000 set or cleared. | 0 |
| 27 | `selectSetOFlag` 0x1447fc | i which, i on | The same on the selected object if there is one. | 0 |
| 29 | `setWeaponType` 0x1448e4 | s name, i type | If the pointer at +0x50 is not 0: virtual slot 8 of that object with (0, type as a byte). | 10/5 |
| 30 | `setMonsterRange` 0x1449b4 | s name, i range | If range > 0: virtual slot 34 with its low 16 bits. | 0 |
| 31 | `killMonster` 0x144a84 | s name | Creatures not already dead (flag 0x8 clear): object flags \|= 0x2009; hit points (+0x228) = 0; virtual slot 27 with 0x14. | 15/5 |
| 32 | `deleteMonster` 0x144b44 | s name | Virtual slot 1 with 3 (destroyed at once). | 33/8 |
| 33 | `hideMonster` 0x144c00 | s name | **Every** object of the name: `obj_moveOffGrid(object)`; object flag 0x8000 set; and for a creature bit 3 of byte +0x231 set. | 373/48 |
| 34 | `showMonster` 0x144db8 | s name | Every object: `obj_updateGridCell(object)`; flag 0x8000 cleared; for a creature that bit cleared. | 52/23 |
| 35 | `moveMonster` 0x144cb8 | s name, s target | If the target (first object of that name) exists: every object of name gets its position (12 bytes) and facing (+0x38, 16 bits), then `obj_updateGridCell(object)`. | 3/2 |
| 36 | `followPlayer` 0x144e78 | s name | Flag bit 23 set, then `Creature_setCharm(creature, −1, 0)`. | 0 |
| 37 | `stopFollowingPlayer` 0x144f2c | s name | Bit 23 cleared. | 0 |
| 38 | `followPath` 0x144fc8 | s name | If bit 27 is clear: bit 27 set; +0x3c4 = 44000; `obj_runEveryFrame(creature)`. | 28/8 |
| 39 | `selectFollowPath` 0x145090 | – | The same on the selected object if there is one and it is a creature. | 3/3 |
| 40 | `stopFollowingPath` 0x1450ec | s name | If bit 27 is set: +0x3c4 = 1150; bit 27 cleared; the position is copied to +0x3b4; unless AI state is 0x14: virtual slot 27 with 0. | 45/1 |
| 41 | `selectStopPath` 0x1451f0 | – | The same on the selected object. | 11/4 |
| 42 | `friendly` 0x145294 | s name | Object flag 0x1000000 and flag bit 26 set. | 13/4 |
| 43 | `unFriendly` 0x145338 | s name | Both cleared. | 6/1 |
| 80 | `reapEnemies` 0x1453e4 | – | `world_collectObjectsInBox(−60000 ×3, +60000 ×3, out, 0x200)`; each object that is a dead creature (flags 0x28 both set) and not a player (0x40 clear) gets virtual slot 1 with 3. For every other object its class is compared with three pointer types, which no object has (FINDINGS D11). | 1/1 |
| 102 | `checkMonstersLeft` 0x1441c0 | → 0/1 | Byte 0x5d32c4 = 1; `world_forEachGridObject(callback 0x144198)`, the callback clearing the byte for an object with flag 0x20 set and 0x8 and 0x40 clear; result 1 when the byte is 0. | 0 |
| 130 | `getHitPoints` 0x142944 | s name → i | (int) of +0x228 of the first creature of the name; 0 when there is none. | 25/2 |
| 131 | `setHitPoints` 0x1429e0 | s name, i value | The first object of the name, if it is a creature: +0x228 = (float)value. **No null check.** | 0 |
| 159 | `generateMonster` 0x1473d4 | s generator, s className | Both strings are converted. The class name is looked up (case-sensitive) in the table of 24-byte names at 0x5d32c8 (count: signed byte 0x4f8409) and appended when new (count first, then the copy; no limit on count or length). Then for every object of the generator name whose class is `ScriptGenerator`: `ScriptGenerator_spawn(object, pointer to the table entry)`. | 136/11 |
| 160 | `monstersInTrigger` 0x147570 | s name → i | The sum of `MonsterTrigger_count(object)` over the objects of the name whose class is `MonsterTrigger`. | 10/3 |
| 167 | `initScriptSetParams` 0x147640 | i ×5 | If the selected object exists and is a creature: `Creature_scaleStats(object; five floats = each argument × 0.01)`. | 13/6 |
| 168 | `setCreatureParams` 0x1476c0 | s name, i ×5 | The same for every creature of the name. | 56/13 |
| 47 | `startNPCAnim` 0x1438d8 | s name, s lump, s anim, i mode | Three strings converted; per creature, with state = creature + 0x114: mode −1: `anim_clear(state)`, `anim_push(state, res_find(lump, anim), 6)`, `anim_jumpTopToEnd(state)`, `anim_releaseCaches(state)`; other modes: `anim_start(0x3e999999; state, res_find(lump, anim), mode)`. The resource is looked up once per creature. | 0 |
| 48 | `NPCAnimAtEnd` 0x143a4c | s name → 0/1 | Bit 7 of the 16-bit word +0x11a of the first object. **No null check.** | 0 |
| 142 | `countLiveObjects` 0x146a10 | s name → i | Among the first 127 objects of the name: those that are not dead creatures. | 0 |

### 3.8 Other objects, effects, camera

| # | Built-in (handler) | Arguments → result | What it does | Calls |
|---|---|---|---|---|
| 134 | `trigger` 0x142264 | s name, i arg | Virtual slot 3 with arg on each of the first 99 objects of the name, whatever they are. | 29/17 |
| 135 | `autoPropSetState` 0x142320 | s name, i state | Virtual slot 18 with state on those of the first 99 that have object flag 0x10000000. | 62/13 |
| 136 | `autoPropGetState` 0x1423e0 | s name → i | The word +0x178 of the first object if it has that flag, else 0. **No null check.** | 0 |
| 44 | `startPropAnim` 0x143a8c | s name, s anim, i mode | The first object, state = object + 0x54; like `startNPCAnim` with the lump name taken from the object's `lump` property (`obj_getPropStr`, which lower-cases its key in place). **No null check**; a missing property passes a null name on. | 0 |
| 45 | `stopPropAnim` 0x143bb8 | s name | Byte +0x58 of the first object = 0. **No null check.** | 0 |
| 46 | `propAnimAtEnd` 0x143bf4 | s name → 0/1 | Bit 7 of the 16-bit word +0x5a. **No null check.** | 0 |
| 97 | `deleteObjects` 0x146ff4 | s name | Virtual slot 1 with 3 on the first 24 objects of the name. | 0 |
| 95 | `setNoCollide` 0x146f58 | s name, i on | Object flag bit 0 of the first object set or cleared. **No null check.** | 0 |
| 120 | `objInPlayerTrig` 0x142ad4 | s name → 0/1 | If the object exists: `world_findObjectsByClass("7Trigger" type name, out, 0x32)`; 1 at the first trigger whose +0x68 is not −1 and whose virtual slot 17 answers non-zero for the object. | 0 |
| 175 | `findDistance` 0x1478c8 | s a, s b → i | (int)sqrt(dx² + dy²) between the first objects of the two names; 0 when either is missing. | 4/4 |
| 176 | `setContainerProps` 0x14799c | s name, i which, i value | Objects of class `AutoContainer`, only for which = 1: bit 3 of the word +0x124 set when value is 0, cleared otherwise. | 6/3 |
| 5 | `lightEffect` 0x143720 | ref pos[3], i scale, i ×10 | The three cells at pos converted to floats; block = `pool_new(0xbc)`; if block: `LightEffect_ctor(block, &position, 0, 0;` values 2..9 as eight floats; on the stack values 10 and 11 as floats, 1.0, and scale × 0.01`)`. | 0 |
| 49 | `addExpandingPool` 0x143c34 | s object, i unused, i size | `decal_add((float)size; position, 0, 10, 2)`. **No null check.** | 0 |
| 68 | `particleMorph` 0x1467ac | s from, s to | Both lists are fetched (up to 511 each); if the **first** object of each is a creature: block = `pool_new(0x5c)`; if block: `ParticleMorphEffect_ctor(block, from, to)`. | 0 |
| 93 | `setParticle` 0x146d94 | i slot, i ×14 | `0x18f118(definition of the slot; values 1..7 as integers; values 9, 10, 11 as floats; on the stack values 8, 12, 13, 14 and a 0)`. The definitions are the three pointers at 0x403360 (0x5d3188, 0x5d31d8, 0x5d3228); the slot is not checked. | 14/13 |
| 94 | `addParticleOnObject` 0x146e20 | i slot, s object, i dx, dy, dz, i vx, vy, vz | `particle_spawn(0.0; definition, &(object position + (float)d), &((float)v × 0x3a83126e))`; slot −1 means slot 0. **No null check.** | 54/13 |
| 96 | `shakeCamera` 0x146fc0 | i amount | If the medal countdown 0x4f7114 is 0: `camera_shake((float)amount; 0)`. | 4/2 |
| 14 | `setFarClip` 0x144104 | i distance | `camera_setFarClip((float)distance)`. | 0 |
| 177 | `setWaveDetail` 0x14176c | i on | 0x4f7130 = 1 or 0. | 1/1 |

### 3.9 Audio

| # | Built-in (handler) | Arguments | What it does | Calls |
|---|---|---|---|---|
| 3 | `sound` 0x1435e0 | s lump, s name | r = `res_find(lump, name)`; if r: `sound_playSample(1.0, 1.0, 0.0; r, 0)`. | 0 |
| 4 | `soundSequence` 0x143684 | s lump, s name | `sound_setPlaysWhileFrozen(sound_playOnObject(1.0; res_find(lump, name), 0))` — also for a resource that was not found. | 27/26 |
| 73 | `startMusic` 0x146b68 | s name | `music_playLevel(name, 3)`. | 0 |
| 74 | `startAudio` 0x146ba4 | s name | `stream_playLevel(1, name, 2)`. | 0 |
| 75 | `endMusic` 0x146be4 | – | `stream_queueStop(2)`. | 0 |

### 3.10 Vehicles (no shipped script calls these)

| # | Built-in (handler) | Arguments → result | What it does |
|---|---|---|---|
| 108 | `putNPCInVehicle` 0x142bdc | s vehicle, s npc | If the vehicle exists: `Vehicle_attachNpcDriver(vehicle, first object named npc or 0)`. |
| 109 | `putPlayersInVehicle` 0x142df4 | s vehicle | If it exists: virtual slot 14 with the active player (unless that is −1); then for every other player in order whose object is not dead (no null check): slot 14 with that player. |
| 110 | `entityRideVehicle` 0x142c78 | s entity, s vehicle, i x, y, z, i angle | The vehicle's virtual slot 19 with (&(float x, y, z), &position, &facing); the entity gets that position and facing + angle (16 bits); `obj_updateGridCell(entity)`. **No null checks.** |
| 111 | `controlVehicle` 0x142d94 | s vehicle, i a, i b | If it exists: +0x410 = a, +0x2f0 = (float)b. |
| 113 | `holdVehicle` 0x142eec | s vehicle, i on | If it exists: `Vehicle_setHold(vehicle, on)`. |
| 114 | `getPlayerVPosition` 0x142f40 | → i | best = 0.0; for all players with a living object whose +0x540 (vehicle) is not 0: if best < vehicle +0x90c then best = vehicle **+0x34c**; result (int)(best × 128.0). |
| 115 | `getVPosition` 0x1430cc | s vehicle → i | (int)(+0x90c × 128.0); 0 when not found. |
| 116 | `getPlayerVDir` 0x142fc8 | → 1 / −1 / 0 | For each entry of the alive list with a living object in a vehicle whose +0x348 is above 2.0: dot = (−(+0x468) × p[+0xc]) + (−(+0x46c) × p[+0x10]) + (−(+0x470) × p[+0x14]), p = the pointer at vehicle +0x910; 1 if dot > 0, otherwise −1 (the second test, dot < 0x3f34fdf3 — about 0.707 — cannot fail once the first has). 0 when no entry qualifies. |

## 4. Shared-seed draws

Only two built-ins draw from the shared seed 0x404464 themselves (Executed: the seed after
every compared call is the seed before advanced by exactly the model's count):

| Built-in | Draws |
|---|---|
| `getRand` | one |
| `givePlayerRandom` | per player, in player order: one, then one before each of the 1 to 10 calls of `item_generateWithAffixes` |

Every other draw a built-in causes happens inside a call-out, so the order of draws is the
order of the call-outs given in section 3. Call-outs that draw, according to the documents
of their own areas (Observed there, not here): every object constructor draws once in
`GameObject_ctor` for the object's own seed (`docs/spec/object-system.md`), so
`ItemProp_ctor2` (the ground item of the give-item built-ins), `LightEffect_ctor`,
`ParticleMorphEffect_ctor`, the object `ScriptGenerator_spawn` creates (one spawn per
matching generator, in name-table order) and the item of `loot_spawnNamedItem`;
`item_parseDescriptor` with variant −1 randomises the item's look; the two spell-effect
constructors of `hornOmen` / `planarSteel`; and `item_generateWithAffixes`. A failed
`pool_new` skips the constructor and with it the draw — the dependence on the pool that
FINDINGS D21 describes reaches scripts through `givePlayerItem`, `giveOnePlayerItem`,
`givePlayerRandom`, `lightEffect`, `particleMorph`, `hornOmen` and `planarSteel`.

Scripts that run from draw code (`docs/script.md` P1) would move the seed on one machine
only if they reached `getRand`; that is a property of who starts the script, not of the
built-in.

## 5. What differs in a net game, and what is per machine

Executed in the handlers; the consequences are Inferred unless a ledger row is cited.

| Built-in | Reads | Effect |
|---|---|---|
| `newWorld`, `newWorldAlways`, `simpleNewWorld` | `g_networkMode`, active player, its cooldown (rec +0x4bca), `g_alivePlayerCount`; `net_isLocalSlot(active)` | Refusal and cooldown are shared state (D20). The local-slot test only chooses whether the HUD line is shown. Skipped in a post action. |
| the same, `newWorldParameter`, `activateStore` | – | `net_closeLocalMenus(0)` is called on every machine by the level-change built-ins, but by `activateStore` only on machines that own a living player (`docs/script.md` P6). |
| `startDialog` | `net_isLocalSlot(active)`, the dialog word 0x8e2d60, **this machine's camera position and angles** | Exactly one machine sends game message 0, with its own camera values in it (`docs/script.md` P5). If the active player differed between machines, none or several would send. |
| `activateMissionMenu` | `dialog_isOpen()`, recall countdown; `net_firstActiveSlot()` in a net game | Which slot gets the menu comes from peer state, not from the active player. |
| `activateStore` | `dialog_isOpen()`; the alive list; `net_isLocalSlot` per living player | The pending flag 0x4fdd30 and the store index 0x4f7150 are written on every machine; the shop opens per machine. |
| `saveGame` | every player's status word; `net_getLocalPlayerSlot(0)` | Opens the save flow for this machine's player (FINDINGS B3). |
| `saveEndConfig` | `g_networkMode`, difficulty | Drops all remote peers; everything after it is a private game. |
| `saveDone` → script | `memcard_getState()` | A per-machine value becomes the script's result (`docs/script.md` P4). |
| `setpv` | this machine's profile table | A config save is requested only where the stored value differed. |
| `getpv` → script | this machine's profile table | Per-machine result. No shipped script calls it. |
| `getMedal` → script | `net_getLocalPlayerSlot(0)`, that player's medal byte | Per-machine result whenever the players' medals differ (`docs/script.md` P3). |
| `runMedalSuccess`, `runMedalFail` → script | `g_networkMode`; `net_getLocalPlayerSlot(0)` against the medal player; `memcard_isBusy()`; the acknowledge word 0x4f7140; the medal player's pad word | Section 3.4: the early returns are per machine and come before the two shared writes (pending level, mission menu) and the result. Offline it sets `g_paused`. |
| `playGotItemSound` | active player, `g_numPlayers`, a hit-point value | Writes the active player (same on all machines); the voice is local presentation. |
| `playerAdjustStat` with a player other than −1 | – | Every machine that runs the script sends inventory message 6 (`docs/script.md` P8). |
| `storeRunning`, `helpMessageActive`, `dialogRunning`, `playerSelRunning`, `hudFadeScreen` → script | menu and HUD state | Per-machine or presentation state as a script result. No shipped script calls any of them (`helpMessageActive`: FINDINGS U6). |
| `networkMode` → script | `g_networkMode` | The same on all machines of one game. |

Of these, FINDINGS has rows for the newWorld gate (D20), `saveGame` (B3) and
`helpMessageActive` (U6). The reads of `startDialog`, `getMedal`, `saveDone`, `setpv` /
`getpv`, the two medal screens, `activateStore`, `activateMissionMenu`, `playerAdjustStat`,
`storeRunning`, `dialogRunning`, `playerSelRunning` and `hudFadeScreen` are described in
`docs/script.md` section 5 (P2–P8, P10) but have no ledger row; section 10 proposes rows
for the ones that reach a script result or shared state. Executing the handlers found no
per-machine read beyond those: every other value a handler reads is a player record, an
object field, a quest variable, a lockstep global or a script cell.

## 6. Missing objects and bad arguments: summary

| Case | Built-ins | What happens |
|---|---|---|
| Name has no object, handler loops over a list | all creature built-ins, `trigger`, `autoPropSetState`, `showOnMap`, `hideMonster`, `showMonster`, `moveMonster`, `deleteObjects`, `setOFlag`, `generateMonster`, `monstersInTrigger`, `setContainerProps`, `countLiveObjects`, `particleMorph`, `getHitPoints` | Nothing (result 0). |
| Name has no object, handler tests for it | `dropItem`, `findDistance`, `objInPlayerTrig`, `getVPosition`, `controlVehicle`, `holdVehicle`, `putNPCInVehicle`, `putPlayersInVehicle`, `moveMonster` (target) | Nothing (result 0). |
| Name has no object, **no test** | `showCompass`, `addParticleOnObject`, `addExpandingPool`, `setHitPoints`, `setNoCollide`, `autoPropGetState`, `NPCAnimAtEnd`, `startPropAnim`, `stopPropAnim`, `propAnimAtEnd`, `entityRideVehicle`; `hitPlayers` when the alive list is not empty; `closestPlayerDist` when a listed player has an object | Reads (and for some writes) at address 0 + field offset. |
| No selected object, no test | `selectSetMonsterVal`, `newWorldParameter`; and `newWorld` / `newWorldParameter` with a selected object whose property list pointer is 0 | The same. |
| A listed or numbered player has no object, no test | `hitPlayers`, `putPlayersInVehicle`, the ground-item paths of `givePlayerItem` (first entry of the alive list) and `givePlayerRandom` | The same. |
| Player number out of range | `getMaxPlayerHP` (→ −1), `isClericOrWizard`, `piercePlayerEar`, `onePlayerHasItem`, `giveOnePlayerItem`, `removePlayerItem` test an upper bound; a negative number passes the signed tests of the last three. `setPlayerFlag`, `getPlayerFlag`, `activePlayerIsDwarf`, `playGotItemSound` do not test at all | An unchecked number indexes the player array as given. |
| Mission number ≥ 13 | all mission and medal built-ins | Nothing / 0. Negative: not refused. |
| Particle slot outside 0..2 | `setParticle`, `addParticleOnObject` | Reads the word behind the three-pointer table (0 at 0x40336c, then the built-in table itself). Observed; the model refuses. |
| String address refused | every built-in with a string | 1.2. |
| String longer than the buffer | every built-in with a string | Overruns the handler's stack frame (Observed). |

In every "no test" case the model raises `HostFault`; the differential test checks that
these are exactly the cases in which the interpreter leaves mapped memory (533 such cases
agreed among the per-built-in runs, see 8).

## 7. The model

`tools/ref_natives.py` (standard library only, no game data):

- `Game()` holds the state: `mem` (every scalar at its real address — globals, the four
  player records, the quest-variable table, the queue buffers, object fields), `world` (a
  `ref_objects.World`: name table, grids, run lists), `host` (call-outs) and `machine` (the
  level's `ref_amx.Machine`). Named properties exist for the globals a user is likely to
  set (`active_player`, `num_players`, `network_mode`, `selected_obj`, `seed`, …).
- `Game.natives()` is the table for `ref_amx`: name → callable(machine, argument cells).
  `Game.set_script(machine)` binds it; `run_script`, `run_deferred`, `run_post_action`
  are the three ways the game enters a script.
- The host functions of section 1 are methods of the same names (`var_get`, `var_set`,
  `vars_clear_all`, `queue_deferred`, `net_gate`, `set_next_world`, `mission_grant_medal`,
  `quest_add`, …).
- `EXT` lists the 96 call-outs with address and argument registers, `VIRTUAL` the virtual
  slots. `Host.log` records every call-out; `Host.handlers[name]` supplies an answer.
  Without a handler the object-system call-outs act on the model's `ref_objects.World`
  and everything else answers 0.
- `new_object(...)` puts an object into the model's world for a user or a test; it is
  state set-up, not the game's constructor, and draws nothing.

`python3 tools/ref_natives.py list` prints the table with one line per built-in.
`tools/test_ref_natives.py` has 26 checks of the model's own logic that need no game files.

## 8. What the differential test covers

`python3 tools/difftest_natives.py` (needs the executable; the script properties also need
`scripts_raw/*.scr`). One PASS/FAIL line per property. The full run:

| Group | Property | Cases | What agreed |
|---|---|---|---|
| machinery | `script_queueDeferred` | 150 | 1 to 4 names queued on random queue states (the 65th dropped) |
| | `script_runDeferred` | 250 | 1 to 3 ticks of the Script task with nested built-ins |
| | post action | 200 | set, run, run again |
| | `script_runByName` | 200 | existing, missing and near-miss names; the missing-entry stamp |
| | quest variables | 300 | random sequences of get / set / clear-all / get-by-index |
| | queue reset | 40 | `script_clearDeferred`, `script_resetState` |
| | refused string address | 116 | six directed entry points (1.2); 124 further runs were not compared because the model declines (`StackGarbage`) |
| | campaign state functions | 300 | the functions of 1.11 called directly, with arguments the built-ins never pass |
| | `script_newWorldNoGate` | 60 | the unreferenced copy at 0x143e30 |
| | name lookup | 400 | 1.3 |
| builtins | load | 1 | the real `scr_load` and `scr_registerNatives` bind all 191 names from the table |
| | one property per table name (191) | 60 each, 11,460 in all | result, error word, call-outs with arguments, bytes written, seed, script memory; 533 of the cases are ones where both sides stop at a null object |
| | string pointer slots | 5,981 | the slot table of 1.2 |
| scripts | shipped entry points | 3,663 runs | every one of the 1,828 entry points of the 120 shipped scripts run whole on at least two random states, with objects and variables under the names the entry point uses: 6,774 call-outs; 69 runs in which both sides stop at a null object; **all 1,828 entry points ran to their end on both sides at least once** |
| | shipped scripts over time | 15,604 steps | each script twice: `preStart`, `start`, then 60 ticks of the Script task with the post action every tenth tick, nothing reset in between, compared after every step; 5,613 call-outs; 11 of the 240 sequences ended early where both sides stop at a null object |

205 properties, all PASS; no mismatch is left open. The run takes about four minutes
(`--quick`: under one).

Coverage, counted in basic blocks of the original code that the interpreter entered:

- built-in handlers entered: **190 of 190** distinct handlers (191 table names);
- 1,090 of 1,093 basic blocks in 230 functions — the 190 handlers, their 7 helpers in the
  script range and the 33 host functions of section 1 — with 229 functions covered
  completely. The three blocks never entered are the "bad typeid" calls of `reapEnemies`
  (0x145488, 0x1454cc, 0x145510), which need a null entry inside a zero-terminated list.
  Each built-in's own line of the test output gives its blocks.
- from the shipped scripts alone (entry points and over time, without the per-built-in
  cases): 114 handlers entered, 677 blocks. Of the 122 built-ins the scripts call, eight
  were not reached by any script run under the random states used and are covered by the
  per-built-in cases only: `getMaxPlayerHP`, `giveFullHealth`, `grantBronze`,
  `grantSilver`, `refillPlayerMana`, `runMedalSuccess`, `shakeCamera`, `takePlayerGold`
  (all sit behind conditions on script variables that count kills or time).

How a case is built. The original code runs on a state constructed in the interpreter's
memory: four random player records (hit points, mana, gold, quest lists, bags, medals,
mission bytes, cooldowns), 3 to 14 objects of random kinds (creatures, players, generators,
monster triggers, containers, triggers, auto props, vehicles) with random flags, creature
flag words, positions and property lists, entered in the real name table under names from
a small pool (several objects per name, mixed case, some entries removed again), random
globals (net mode, player count, active and selected object, difficulty, pause states,
queue contents, post action, pad words, medal state), a random quest-variable table. The
model works on a copy-on-write view of that memory and on the same script image. Callees
outside the model are recording stubs whose answers (local-slot tests, dialog and card
state, resource pointers, pool blocks or 0, item weights, lists of objects for the box and
class queries, …) come from a seeded script that is the same on both sides.

What the comparison does not show:

- **The call-outs are not executed.** That `Creature_setCharm`, `inventory_giveItem`,
  `ScriptGenerator_spawn`, `cut_start`, `save_game` and the rest do what their own
  documents say is outside this test. For the object-system call-outs
  `tools/difftest_objects.py` is the test.
- **Argument registers of a call-out that the list in `EXT` does not name are not
  compared.** The lists were taken from the handlers and the callees' documented
  signatures; a register the model leaves out would go unnoticed. A register the model
  names but the handler does not set is noticed: the test fills every argument and scratch
  register, integer and float, with junk before each call into the original.
- **States are random, not played.** The object fields the handlers read are random bits,
  not what the game's constructors produce. Combinations the game never reaches are
  therefore included, and combinations that need a played game (a real dialog in
  progress) are represented only by the stub's answer.
- **Console behaviour at address 0** was not established; the test only shows that model
  and interpreter stop in the same cases.
- **The uninitialised stack word of 1.2** is modelled for the case that occurs in shipped
  data and in the directed entry points of the test; the model declines the rest.
- Not compared at all: a string longer than the handler's buffer, a particle slot outside
  0..2, a non-ASCII variable or object name.

## 9. Where executing the code corrected `docs/script.md`

| `docs/script.md` | It says | Executed |
|---|---|---|
| 1.7, string arguments | `scr_getAddr` is a bounds check whose result callers ignore | On a refusal the pointer is **not written**, so the handler converts the string its stack slot still points at (1.2). A shipped script, TORMEDAL `start`, relies on it. |
| `addQuest` / `quest_add` | "appends the pair to every player's quest list unless already present (max 8)" | The loop over the players **ends** at the first player whose list is full or has the title; later players get nothing. |
| `removeQuest` / `quest_remove` | (wraps `quest_remove`) | All matching entries are overwritten with a placeholder, but only the entries behind the last match move up and the count drops by one. |
| `playGotItemSound` | after the clamp, "switches to the other of 0/1 if that player has no hit points, and calls `player_voice(slot, 9)`" | The slot passed to `player_voice` is the **unclamped** value (2 or 3 stays), and the hit-point test indexes the records with the unclamped value; only when that test fires is the other of 0/1 used. The stored active player is clamped as described. |
| `runMedalSuccess` | reward lines chosen from the local player's medal | Also: the lines are drawn in the order 3, 2, 1 under the title; every shown text is drawn twice (a measuring pass with a clip window of 100..100); offline the function returns 0 while `memcard_isBusy()` as well. |
| `lightEffect` | "ref pos[3], i unused, i x8" | The second argument is used (× 0.01, on the stack), and ten values follow, not eight (the last two on the stack, with a constant 1.0). |
| `sound` | `sound_playSample(1.0, 1.0, 0, res, 0)` | Three float arguments (1.0, 1.0, 0.0) and two integers (the resource, 0). |
| `clearAllSkills` | "three fields at +0x4a80.." cleared | +0x4a80 (word) and +0x4a84 (byte) are cleared; the byte +0x4a85 is set to **1**. |
| `getManaUsed`, `getHealthUsed`, `helpMessageActive` | return the counter / the flag | Sign-extended (16-bit and 8-bit loads): a counter of 0x8000 or more reads negative. |
| `checkPlayerAlive`, `restorePlayer` | the countdown 0x4f7194 | A 16-bit value (read and written as such). |
| `getPlayerVPosition` | "returns a vehicle float × 128" | Compares vehicle +0x90c with the value kept so far but keeps vehicle **+0x34c**. |
| `getPlayerVDir` | "1, −1 or 0 from a dot product" | For the first qualifying vehicle the result is 1 or −1; the 0.707 test can never send it on to the next player. |
| `hornOmen`, `planarSteel` | allocate and link | `creature_addSpell` is also called when the allocation failed, with a null spell. |
| `startDialog` | "preloads the level lump, clears 0x4fdce8, then calls `dialog_start`" | The clear is inside `dialog_start`, after `Camera_update` on the local camera, which was not mentioned. The handler also formats "<name>.dbin" into a buffer nothing reads. |
| `setPlayerFlag` | "bit of record +0x4c28" | The bit number is taken mod 32 and the flag is one byte: bits 8..31 change nothing. |
| `saveEndConfig` | sets the completion bit for the difficulty | For difficulty 1..4 (0x08, 0x10, 0x20, 0x40); difficulty 0 sets none. |
| `removeAllItems`, `removeAllWeapons` | "empties" the bags | As many `inventory_removeItem(slot, 0, bag, 0)` calls as the bag's count at the start, each only if the bag's first entry is then non-zero. |
| `generateMonster` | interns the class name | The call-out gets a pointer into the name table, and the count byte is raised before the copy; neither has a limit. |
| section 2.2, 2.3 | (consistent) | Not executed here; restated in 1.4 and 1.9 as Observed. |

Nothing in `docs/script.md`'s account of which built-in calls which function was wrong
beyond these rows; its per-machine list (section 5 there) stands as written.

## 10. Proposed ledger rows (untested on a game; no patch is proposed)

| Row | Statement | Kind | Evidence |
|---|---|---|---|
| N1 | A built-in whose string address `scr_getAddr` refuses goes on with the pointer left in its stack slot — the string of the last built-in call that used a slot at the same frame distance. The shipped TORMEDAL `start` does this once (an array of 20 names indexed to 20): `rootMonster` and `setCFlag` act a second time on the twentieth name. Deterministic, so not a desync, but a rebuild that validates addresses differs | Executed in the interpreter | 1.2; 0x1414a8; `difftest_natives.py` "refused string address" and the TORMEDAL entry point |
| N2 | `quest_add` stops at the first player whose quest list is full or already holds the title, so in a game where an earlier slot has the quest and a later one does not, the later one never gets it from `addQuest` | Executed | 0x1d386c |
| N3 | `quest_remove` lowers the count by one however many entries matched; duplicate titles leave a placeholder entry behind | Executed | 0x1d3968 |
| N4 | `getMedal` hands a script the medal of this machine's first local player; `saveDone` this machine's card state; `getpv` this machine's profile value. In the nine medal scripts the `getMedal` value only selects text (`docs/script.md` P3) | Executed (the read), Observed (the use) | 0x142188 → 0x1bf838; 0x146d5c; 0x143480 |
| N5 | `runMedalSuccess` / `runMedalFail` return 0 before looking at the pad on the medal player's machine while its card is busy, and on the other machines until the acknowledge arrives; the level restart and the mission menu are written after those returns | Executed (the paths), reachability unknown | 0x1417a4, 0x141c00; `docs/script.md` P2 |
| N6 | `startDialog` sends its game message only where the active player is local and no dialog is open, and puts that machine's camera position and angles into it | Executed | 0x22fa50 |
| N7 | `activateStore` in a net game calls `net_closeLocalMenus(0)` — which also empties vehicles — only on machines that own a living player | Executed (the calls), Inferred (the vehicle consequence) | 0x144010; `docs/script.md` P6 |
| N8 | `playGotItemSound` stores the active player clamped to 0..1 but plays the voice for the unclamped slot | Executed | 0x1464e8 |

## 11. Not done

- The call-outs are documented by name and arguments only; nothing about their effects was
  established here.
- `Trigger_run`, `MonsterTrigger_scan`, `obj_runActionScripts` and the other script
  starters (1.9) were read, not executed, and are not in the model.
- The act-change clean-up, `game_resetState` and `save_load` (1.5) were read, not executed.
- The writers of the active player other than the two built-ins were not executed.
- What the console does when a handler follows a null pointer, and what TORMEDAL's stale
  pointer is when the script is entered at a different stack depth than in the test (the
  rule of 1.2 does not depend on the depth, but only the depths of a direct run and of a
  `callScript` were executed).
- Whether a string longer than 159 bytes or a class name longer than 23 bytes occurs in
  shipped data was not checked.

Proposed names for addresses that had none: `particle_define` 0x18f118 (the callee of
`setParticle`), `profile_append` 0x222a44 (appends a name and value to a packed variable
table), `script_newWorldNoGate` 0x143e30 (already in `symbols/script.tsv`).
