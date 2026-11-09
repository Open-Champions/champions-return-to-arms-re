# Level-script commands that stop the client's story route

Research date: 2026-11-09. Executable: SLUS_209.73 US v2.00, SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
Branch `t3/research-level-commands`, from `t3/research-story-route` 76d4447.
Tools: `tools/difftest_level_commands.py`, `tools/ref_level_commands.py`,
`tools/test_ref_level_commands.py` (all new; no existing reference API, test vector or
difftest was changed).

The client's story-route probe stops a level entry at five built-ins because it has no
evidence for them: `autoPropSetState` (stops `tormenta` `start` before mission 5 becomes
available), `killMonster` (stops the `islgnome` entrances at their first kill),
`soundSequence` (stops after three completion grants), `preloadResource` (stops `tormenta`
`preStart`) and `activateStore` (stops the hub mission-4 entries). This document gives, for
each, the binding, the handler, the argument decoding, every store, the return value,
whether it can stop the script, and its recorded call list. The goal is that a client can
port each one, or treat it as a recorded no-op where the evidence shows no game-state
effect.

## Labels, evidence and what was stubbed

- **Observed (executed)**: the original instructions ran in `tools/ee_emu.py` and were
  compared, byte for byte and call for call, with the model. The property name of
  `difftest_level_commands.py` is given in brackets, e.g. [direct: killMonster].
- **Observed (static)**: read from the instructions at the given address, not run.
- **Inferred**: a consequence of observed facts; not run.
- **Unknown**: not established.

How the comparison works. It uses `difftest_natives.Rig` (handlers, interpreter, dispatcher
`scr_callNative` 0x141050, `script_runByName` 0x1ed694, quest variables, name lookup
`world_findObjectsByName` 0x14bf58, `obj_getPropStr` 0x14f4c0, the C library), plus the
bodies listed in `ref_level_commands.REAL_BODIES`, which earlier rounds kept as stubs. Every
run compares five things:
- the dispatcher result and error word;
- every call-out, with its decoded arguments;
- every byte stored outside the stack and the script image, and its final value;
- the shared seed 0x404464;
- the script machine.

A call to an address that is neither real nor a listed stub fails the case. Before every
call all argument and scratch registers are filled with junk.

**Stubs (recording, answers seeded and identical on both sides).** Each section repeats the
ones its claims depend on:

| stub | address | where it is reached |
|---|---|---|
| `world_movePiece` | 0x182c98 | AutoDoor `setPassable` |
| `res_find` | 0x17365c | `soundSequence` (it can itself call `lump_load`, see below) |
| `dialog_isOpen` | 0x22fbc0 | `activateStore`, `game_isFrozen` |
| `shop_openOrStock`, `net_isLocalSlot`, `net_closeLocalMenus` | 0x1c7af8, 0x13e150, 0x1eb000 | `activateStore` |
| `task_isRunning` | 0x19e5e8 | `game_isFrozen` |
| `lump_findLoaded`, `cd_findFile`, `lump_prepare`, `mem_allocTagged`, `cd_readBlocking`, `lump_pollAsync`, `dbg_printf` | 0x17306c, 0x1724fc, 0x1734c4, 0x14ff88, 0x172ad0, 0x172ca8, 0x355490 | `lump_load` |
| `creature_bossMusicName`, `stream_queueStop`, `obj_delete`, `arena_addKill`, `loot_spawnNamedItem` | 0x10dbe0, 0x211338, 0x14f200, 0x3056cc, 0x100ba0 | `Creature_onDeath` |
| virtual calls on objects with test tables | - | objects that are not AutoProp / AutoPropLP / Gnome |

**Fixtures.** Game state is seeded (`difftest_natives.Scene`). The objects a command targets
are built from the disc's own object records (`objects.ob` of TORMENTA, ISLGNOME), with the
real class table pointer at +0x48. The AutoProp fields a constructor would derive from the
record (`ref_level_commands.autoprop_kind`, after `docs/monsters-2.md` "AutoProp") were set by
hand; **the constructors were not run**. Animation clips, models and class definitions are
synthetic blocks. Track flag 0x800 is kept clear, so `animtrack_decode` 0x16e468 is never
reached.

**Neutral ids.** Script strings are referred to by call site, never by text:

| id | what | where |
|---|---|---|
| T1..T5 | name argument of the five `autoPropSetState` calls in `tormenta` `start` | code 0xc30, 0xc64, 0xc98, 0xccc, 0xd00 |
| G1..G8 | name argument of the eight `killMonster` calls | `islgnome` code 0x1f84 .. 0x20b8 (every 0x2c) |
| E-fail | the entry the three entrances `callScript` | `islgnome` 0x1cd4, 0x1df4, 0x1f14 |
| V-started, V-finished | quest variables the entrances read | `getv` at 0x1c50 and 0x1c80 (entrance1) |
| D, D2 | the `deathscript` value of the eight G records (a public entry), and the entry D calls | D2's `setv` at 0x238c |
| V-alive | the quest variable D2 stores | `setv` at 0x238c |
| C26c | script data cell 0x26c, the gnome counter D2 decrements | `islgnome` data |
| R1 | the `preloadResource` lump argument | `tormenta` 0xbe4 |
| S1, S2 | the `soundSequence` lump and entry arguments | `tormenta` 0x1df4; same pair in `wate2a/b/c`, `watg2a/b/c` |

## 1. Binding

**Observed (executed)** [binding: table 0x403370, binding: scr_registerNatives].
`scr_load` 0x13e8f8 and `scr_registerNatives` 0x141310 bound every import of these five
names in ten level scripts (15 imports) to the handler the table 0x403370 gives:

| command | handler | shipped calls checked |
|---|---|---|
| `autoPropSetState` | 0x142320 | tormenta 12 (5 in `start`), hub 2, hub2 2 |
| `killMonster` | 0x144a84 | islgnome 8, all in E-fail |
| `soundSequence` | 0x143684 | tormenta 1, wate2a/b/c 1 each, watg2a/b/c 1 each |
| `preloadResource` | 0x14222c | tormenta 1 (`preStart`) |
| `activateStore` | 0x144010 | hub 23 entries, hub2 19 entries (one call each) |

**Observed (static)**: elsewhere `autoPropSetState` is also called in BLOOD1, DIS2, DRUNARE,
DRUNDAR, FAY3, VALOR, BOSSEVIL/GOOD, DISEASE0 and TORMENTB, and `killMonster` in DRUNARM,
NIT2, TORMEDAL and VALMEDAL, and `activateStore` in ISLGNOME (2) and STOBONUS (1). Those
levels were not run here.

**All five, can they stop or suspend the script?** **Observed (static)**: every handler
ends `move $2, $zero` and returns (0x1423c8, 0x144b30, 0x143704, 0x142254, 0x1440e0), and the
dispatcher clears the machine error before the call and returns it afterwards
(`docs/spec/script-machine.md`, `scr_callNative`).
None reads or writes the interpreter's control state.
**Observed (executed)** [direct: *]: in 200 dispatcher calls per seed the error word was 0
and the result cell 0. In the shipped runs the entries went on past the call to their later
built-ins, and the machine error word (+0x5c) was 0. There are two ways a call can stop the
*game* (not the script); both are listed under their commands: `lump_load` of a missing file,
and an AutoProp state at or past the animation table.

## 2. autoPropSetState 0x142320 (s name, i state)

### Arguments and handler

**Observed (static and executed)** [direct: autoPropSetState]:
- The name is the cell at params+4, resolved by `scr_getAddr` 0x1414a8 and
  `scr_getString` 0x141650 into a 160-byte stack buffer. The pointer goes to stack slot
  0x1c0 (`ref_natives.STRING_SLOT`).
- The state is the raw cell at params+8. There is no range check here, and it is passed on
  as a 32-bit value.
- `world_findObjectsByName(name, out, 100)` gives at most 99 objects. The name match is that
  of the name table (`ref_objects.NameTable`; case-insensitive).
- Each object whose flag word +0xc has 0x10000000 (the AutoProp bit) gets virtual slot 18
  (vtable +0x90; the s16 at +0x90 adjusts `this`, the word at +0x94 is the function) with
  the state. Objects without the bit are skipped silently.
- Returns 0. The handler itself stores nothing.

**Observed (executed)**: slot 18 is `AutoProp_setState` 0x23d680 in both AutoProp
(vtable 0x5133c0) and AutoPropLP (0x5130c0), and slot 19 is `AutoProp_setPassable` 0x23d7ac
in both. Both words were read from the ELF.

### What setState stores (exact)

**Observed (executed)** [direct: autoPropSetState; shipped: tormenta start expectations;
store regions], `ref_level_commands.Bodies.autoprop_set_state`. Let n = the state, as
signed. If n is not below the signed word +0x120 (States), **nothing is stored and nothing
is called.** Otherwise, in order:

| order | field | value |
|---|---|---|
| 1 | +0x178 state | n |
| 2 | +0x17c frames in state | 0 |
| 3 | +0x180 (u64) states reached | 0, then for n != 0 bits 0..n (each `1 << k` as a 32-bit shift, sign-extended) |
| 4 | +0xc8 (u64) mesh mask | `model_buildHideMask`(+0x90, low word of +0x180): ~(model+8); when model u16 +0x10 has 2 and the bits are not 0, each set bit k ORs record k's first u64 and clears its second (records at model + 16 x u8 model+0x21) |
| 5 | +0x9c track count | 0 |
| 6 | animation state +0x98 | if the state's clip (+0x128 + 8n) is not 0: `anim_push`(+0x98, clip, 3 if state flags (+0x12c + 8n) & 2 else 6), then `anim_jumpTopToEnd`(+0x98). The track at +0xa0 gets clip, time = clip length, weight 1.0, rate 0, target 1.0, life 0, flags; u16 +0x9e ORs in the flags; a cache pointer at +0x98 is zeroed with its +0x610 |
| 7 | +0x17c | 0 + clip length (word clip+4) + 1, only when the clip is not 0 |
| 8 | slot 19 `setPassable`(state flags & 1) | object flag +0xc bit 0x1 set (passable) or cleared. Only for an AutoDoor (+0x11c bit 1): the level piece +0x18c in world 0x44fdc8 also gets collision off/on (`world_setPieceCollision` 0x182b00: bit 0x2 of the chunk's u16 +0x10) and `world_movePiece` to (0,0,-256) / (0,0,0) |

The tormenta store-region census matches this list: of each target object, only +0xc,
+0x98–0x9c, +0x9e–0xbf, +0xc8–0xcf and +0x178–0x187 were written. +0x9d, the track capacity,
was not.

**Observed (static, 0x23d680–0x23d7a8)**: setState runs **no action script**, does not touch
the per-state "done" bit (state flags 0x10), does not change run lists, and draws from no
generator. **Observed (executed)**: the shared seed was unchanged in every run.

**Hazard. Observed (executed)**: setState indexes the clip and flag tables (+0x128 / +0x12c,
8-byte entries, 10 states before +0x178) with no bound but States. With States 12 and
state 11, the "clip" is the word at +0x180 that step 3 has just written. The original then
trapped on an unaligned load at 0x170c0c (counted as a stop on both sides in [direct:
autoPropSetState]). A negative state below States indexes below +0x128; that case was not
run. **Observed (static)**: no shipped record has States above 3 (tormenta 2, hub portal 3).

### Calls

AutoProp/AutoPropLP target: `model_buildHideMask` 0x179550, `anim_push` 0x170838,
`anim_jumpTopToEnd` 0x170bc8, virtual slot 19 0x23d7ac. AutoDoor only:
`world_setPieceCollision` 0x182b00 and the stub `world_movePiece` 0x182c98. All of them ran
for real except `world_movePiece`. Any other object carrying the bit: virtual slot 18 of its
own class (stubbed in this test).

### tormenta start

**Observed (static, disc)**: `start` passes state 0 to T1..T5 (0xc30–0xd00), then calls
`setMissionAvailable(5, 1)` at 0xd34. The disc's TORMENTA object records have no object
named T3 or T4. The T1, T2 and T5 records are AutoPropLP:
- they carry a particle emitter;
- +0x11c mask 0x10 (Pokeable);
- States 2;
- state flags state 0: 0, state 1: 4 (NoMessage);
- no Passable key, no AutoDoor;
- each has one `action1` script.

The other nine tormenta calls, in the timer and bridge entries, also pass 0. Hub and hub2
`start` pass 0 to the portal, and the portal-loop entry passes 2.

**Observed (executed)** [shipped: tormenta preStart/start, tormenta start expectations]:
13 runs of `start` per seed, against the model. In each:
- the five `autoPropSetState` calls ran, then `setMissionAvailable`;
- mission 5's byte got bit 0 (with g_numPlayers ≥ 1; `mission_setAvailable` writes the
  first g_numPlayers records);
- the error word stayed 0.

Each of T1, T2 and T5 ended with:
- state 0, reached bits 0, mask ~(model+8), flag 0x1 clear (state 0 is not passable);
- one track holding clip 0 at its end, frame counter = clip-0 length + 1.

T3 and T4 found nothing, and objects with other names (the switches) were untouched.

**What a client must do (Inferred from the above)**: for each object of the name that has
the AutoProp bit, "enter state n silently": state = n; reached bits as above; state-n mesh
mask; animation n jumped to its end; passable from the Passable string's character n;
no action script. Ignore n >= States. For `tormenta` `start` that means T1, T2 and T5 to
state 0 (unlit, the prompt of state 0, solid as before for these records), and nothing for
T3 and T4. It is **not** a no-op: it resets a saved state.

### What reads the state later

- **Observed (static)**, loads of +0x178 in the AutoProp functions: run 0x23cb54
  (0x23cb8c, 0x23cbbc, 0x23cc28: ActionAtEnd actions once the animation ends), save
  0x23cea0 (the 4-byte saved state), prompt 0x23d014 (0x23d044, 0x23d0fc: message /
  NoMessage of the state), trigger 0x23d1fc (0x23d244), nextState 0x23d2ec (0x23d318–0x23d5a4;
  it also reads +0x180 at 0x23d324–0x23d3d4), runStateActions 0x23d890 (0x23d8b4, 0x23d8d4).
- AutoPropLP's own run 0x2421e0 and draw 0x241ee4 (slots 4 and 5) read +0x178 and +0x17c
  (0x241f3c–0x2422ec).
- `autoPropGetState` 0x1423e0 returns +0x178; no shipped script calls it.
- **Inferred** from the record keys (`particle<k>state<n>on/off`, `light0`) and those reads:
  the LP run/draw switch the T records' particles and light by state and frames in state.
  That is cosmetic.
- **Inferred** from `docs/monsters-2.md` (interact 0x23d1b0, nextState): with the state at
  0, the next player use of a Pokeable T record advances it to state 1 and runs that
  record's `action1` entry. That is where the level's own logic continues. Neither was run
  here.
- **Unknown**: whether, on a revisit, the saved-state load (slot 18 from 0x23ceb8) runs
  before or after `start`, and so whether `start` overrides a saved lit state. The order of
  level load was not run in this round.

## 3. killMonster 0x144a84 (s name)

### Arguments and handler

**Observed (static and executed)** [direct: killMonster]:
- The name is decoded as in section 2 (stack slot 0x830).
- `world_findObjectsByName(name, out, 0x200)` gives at most 511 objects.
- For each object whose flags & 0x28 is 0x20 (a creature, not dead): flags |= 0x2009,
  i.e. 0x1 not solid, 0x8 dead, 0x2000 killed (`docs/objects.md` flag table); the word +0x228
  (hit points, a float) = 0; then virtual slot 27 (vtable +0xd8) with 0x14.
- Dead creatures and non-creatures are skipped.
- Returns 0. The flag and hit-point stores are made before the virtual call, whatever the
  class does.

### What the Gnome class does with slot 27 (the islgnome targets)

**Observed (static, disc)**: G1..G8 are eight `islgnome` records of the `Gnome` family:
- five peasant, three soldier;
- vtable 0x5103a8, slot 27 = `Gnome_setState` 0x269bb4, slot 28 = 0x10beb8 (read from the
  ELF);
- each has `deathscript` = D (a public entry of the level) and an initscript;
- none has `dropitem`.

**Observed (executed)** [direct: killMonster; shipped: islgnome entrances, islgnome
expectations; store regions], `Bodies.gnome_set_state`:

1. State gate 0x10a9c0 (state 0x14). It **refuses**, and nothing below happens (only the
   handler's flags and hit points remain), when the arena flag 0x4f7120 is set, 0x4f711c is
   0, 0x503890 is set and 0x503894 is 0. It refused 15 deaths in 20 islgnome runs (seed
   20973). Otherwise it zeroes the s16 timers +0x31c, +0x318, +0x314, +0x31a. The attack
   test 0x1195f0 stores 0 into +0x318 again when +0x234 is 0. The gate then passes.
2. One draw of the object's **own** generator `GameObject_rand` 0x1509d0 (+0x44 =
   +0x44 x 0x19660d + 0x3c6ef35f). It is not the shared seed, which was unchanged in every run.
3. `anim_start`(blend 0.1 s, +0x114, clip = word at class definition (+0x24) + 0xa4 +
   8 x (draw & 3), flags 6): a death animation pushed with fade-in rate 1/(0.1 x 60).
4. Slot 28, `Creature_onDeath` 0x10beb8, with 0:
   - creature flags +0xa8 &= 0xfffffffff73fffff (clears 0x8c00000);
   - `obj_getPropStr(obj, "deathScript", 0)`, which **lower-cases its key string in place**
     (the bytes at 0x52fbf8 are stored, region "obj_getPropStr keys"). If found,
     g_scriptSelectedObj 0x4039f8 = the gnome, `script_runByName(D)` (a nested run), then
     **g_scriptSelectedObj = 0**, not the value it had;
   - argument 0: `obj_getPropStr("dropitem")`; a value would call `loot_spawnNamedItem`
     (stub; the G records have none);
   - object flag 0x2: flag 0x4000, the animation to its end, `obj_delete` (stub; set in 10%
     of the generated gnomes, not taken from a record);
   - arena flag: `arena_addKill` (stub);
   - `creature_stopBossMusic` 0x1192f8: `creature_bossMusicName` (stub), and when it
     answers non-zero, `stream_queueStop(2)` (stub).
5. +0x232 (s16 AI state) = 0x14.

The islgnome store census matches this list: of each G object, only +0xc, +0x44, +0xa8,
+0x114–0x118, +0x11a–0x17b (the animation state), +0x228, +0x232, +0x314 and +0x318–0x31d
were written.

**D, the deathscript (Observed, executed in the nested run)**: D calls D2. D2 decrements
C26c and stores it with `setv` into V-alive. With C26c planted, V-alive became
C26c − (number of G objects that died past the gate) in every run.

### islgnome entrances

**Observed (static, disc)**: entrance1, 2 and 3 each:
1. call `setEntrance`;
2. read V-started and V-finished;
3. only when V-started is 1 and V-finished is 0, `callScript(E-fail)`;
4. **in every state**, `newWorld` of the same level (islc2).

The quest test jumps to 0x1ce4, past only the `callScript`. E-fail is the eight
`killMonster` calls G1..G8 and `return 0`.

**Observed (executed)** [islgnome expectations], 20 runs per seed:
- **Quest started, not finished**: 8 `killMonster` calls, then `newWorld`. Every living G
  object: flags 0x2009, hit points 0. Past the gate: state 0x14, one own draw, the
  deathscript run.
- **Quest finished, or not started**: no kill, the same travel.
- **Travel**: the pending level is islc2 every time. The orientation byte 0x41b720 is
  **0xff whenever at least one gnome died past the gate** (8 runs): the deathscript left
  g_scriptSelectedObj at 0, and `script_setNextWorld` 0x1472c4 uses 0xff without a selected
  object. When no gnome died (12 runs), the orientation is the triggering object's
  `orientation=` value, and the selected object is kept.

Error word 0 in every run.

**What a client must do (Inferred from the above)**: for each living creature of the name
(first 511):
- set flags 0x2009 and hit points 0, then the class's "set state 0x14";
- for Gnome: the arena gate; clear the four timers; one own-generator draw choosing death
  animation 0–3; clear creature flags 0x8c00000;
- run the record's `deathscript` with the selected object = the gnome, then clear the
  selected object;
- drop / delete / arena / boss-music only as listed;
- AI state 0x14.

The game-state effects that matter for the route are V-alive, the dead and killed flags, and
the entrance orientation 0xff that the cleared selected object causes. **Unknown**: slot 27
of the classes the other four killMonster levels name (not run). **Inferred** from
`docs/monsters-2.md` (Gnome run, state 0x14 → `Creature_deadUpdate`) and `docs/objects.md`
(0x2000 thinned from saves, 0x1 not solid): what reads the result later. Not run here.

## 4. soundSequence 0x143684 (s lump, s name)

**Observed (static and executed)** [direct: soundSequence; shipped: soundSequence entries,
soundSequence returns]:
- Both strings are decoded as in section 2 into two 160-byte stack buffers (slot 0x30).
- `res_find(lump, name)` (stub). Then `sound_playOnObject(1.0, resource, 0)` 0x214230 is
  called **also for resource 0**, which returns -1 at once.
- Then `sound_setPlaysWhileFrozen(handle)` 0x216ad0.
- Returns 0.

What `sound_playOnObject` with object 0 stores (`Bodies.sound_play_on_object`, executed):
- All 32 players at 0x871a68 (0x4c bytes each) are scanned. The **last** free one (s8 +4 == 0)
  is taken; every busy player of the same group (sequence u8 +0x3c) counts. For a non-zero
  group, reaching the cap s8 0x4f8a28[group] gives -1, and so does no free player.
- The player: u16 +6 = 0; the sequence pushed on its animation state (flags 4); +0x3a = 1;
  +0x38 = serial 0x4f8950, which becomes (serial + 1) & 0x7f; +0x3b = `game_isFrozen()`
  0x1ebdf8; +0x3c = 0; +0x40 = volume 1.0; +0x44 = 360.0; +0x48 = 840.0.
- Handle = player | serial << 8 | 0x8000.
- `sound_setPlaysWhileFrozen` then sets the player's +0x3b = 1 (any handle other than -1 with
  0x8000).
- `game_isFrozen` reads the net flag, g_paused, the cutscene flag, 0x506048, 0x4f6708,
  frame 0x44fdcc, `task_isRunning("playerSelection")` (stub) and `dialog_isOpen` (stub).
  It stores nothing.

**Stores**: only the sound-player table and the serial (compared byte for byte); the
shared seed was unchanged. **Observed (static, gxref)**: every function addressing
0x871a68 or 0x4f8950 by lui+displacement is in the audio area (0x213438–0x216b10:
`sound_release`, `sound_playSample`, `sound_stop`, `soundSeq_updateAll` 0x2147c0, ...).
**Inferred**: no gameplay state reads what this command writes. **Unknown**: what
`res_find` (stub) and the per-frame `soundSeq_updateAll` do. Neither was run; `res_find`
may call `lump_load` (0x173558 is called from 0x17365c, static), which touches only the
resource cache (section 5).

**Shipped (Observed, executed)**: the soundSequence entries of tormenta and the six water
levels were run whole, 70 runs per seed. In the 9–10 runs whose seeded state reached the
call, each went on to its later built-ins with error word 0.

**Client (Inferred)**: gameplay state is unaffected. Treat it as a recorded no-op that
plays the sequence S1/S2, or port the player selection above for audio.

## 5. preloadResource 0x14222c (s lump)

**Observed (static and executed)** [direct: preloadResource; shipped: tormenta preStart
expectations]:
- The lump name is decoded as in section 2 (slot 0x20).
- `lump_load(name)` 0x173558; the result is ignored. Returns 0.

`lump_load` (`Bodies.lump_load`, executed):
- **Loaded already** (`lump_findLoaded` answers non-zero): returns it, and **nothing is
  stored**.
- **Not loaded**: `cd_findFile` (stub), `lump_prepare` 0x1734c4 (stub), a block of
  ((size + 0x7ff) & ~0x7ff) + 0x100 bytes from `mem_allocTagged` tagged
  0x7b9480 + 40 x word 0x41bf7c, then the **blocking** read `cd_readBlocking` (stub; it
  waits on vsync, `symbols/engine.tsv`). Then:
  - pending data 0x41bfa0 = block, size 0x41bfa4, flag 0x41bf9d = 1;
  - the name is copied to 0x7c25c8;
  - `lump_pollAsync` (stub) runs, 0x41bf80 = 0;
  - `lump_findLoaded` is called again.
- **Missing file**: `dbg_printf` of the not-found format 0x533f80, then a store to address 0
  (0x17363c). In the emulator both sides stop (fault). **Observed (static, disc)**: R1 and S1 both
exist as files in BG/DATA, so the shipped calls do not take this path.

**Can it suspend the script?** No. The blocking read stalls the whole thread inside the
call; the script machine sees an ordinary return (error word 0, `preStart` finished with
`preloadResource` its last built-in).

**What reads it later (Observed, static)**: `res_find` 0x17365c loads a lump that is not
loaded (it calls 0x173558). **Inferred**: a later use of R1 (`showBust` in tormenta) loads
it on demand, so the preload changes only when the disc read happens and what sits in the
resource heap, not game state. **Client (Inferred)**: a recorded no-op (or a cache warm-up)
is safe. **Unknown**: anything in the stubbed `cd_*` / `lump_pollAsync` bodies.

## 6. activateStore 0x144010 (i store)

**Observed (static and executed)** [direct: activateStore; shipped: hub/hub2 activateStore
entries, activateStore expectations]:
- The argument is the raw cell at params+4. When it is below 0x15 (unsigned), its low 16
  bits are stored to the store index 0x4f7150 (0x144038).
- Then `dialog_isOpen` (stub):
  - **open**: the pending flag 0x4fdd30 = 1, and nothing else;
  - **closed, offline**: `shop_openOrStock(g_scriptActivePlayer 0x4d8ae4, 0, 1)`
    (0x144074);
  - **closed, net** (0x402791 set): for each of the alive list 0x4f8440 (count 0x4f8420)
    that `net_isLocalSlot`: `net_closeLocalMenus(0)` then `shop_openOrStock(slot, 0, 1)`.
- Returns 0.

**Shipped argument (Observed, executed)**: all 42 hub/hub2 entries that call it, 84 runs:
- Many call sites push no argument cell (`PUSH.C 4; SYSREQ.C`, e.g. hub 0xfc4). The handler
  then reads the next stack word, the entry's saved frame word (docs/script.md row 11).
  That word was **0** in every top-level run through `script_runByName`.
- The other sites push 0 explicitly.
- Either way the store index **becomes 0**.
- **Inferred**: a run nested in another script run would read a non-zero frame word instead
  (a data offset, above 0x14), and then the index is not written. Not run.

Results:
- Dialog open: 0x4fdd30 = 1 and no shop call (42 runs).
- Dialog closed: `shop_openOrStock(active, 0, 1)` and the flag untouched (42 runs).
- Error word 0 in every run.

**The deferred open (Observed, static)**: `dialog_onMsg`'s end-of-dialog path reads
0x4fdd30 at 0x22f7fc (after the post action 0x1edac0):
- offline: `shop_openOrStock(active player, 0, 1)` at 0x22f86c;
- net: `net_closeLocalMenus(0)` and the first local slot under g_numPlayers, at 0x22f850.

The flag is cleared only where a dialog opens, at 0x22f2b0, not at the deferred open. Not
run here.

**Who reads the store index (Observed, static, gxref)**: the only lui+displacement access
to 0x4f7150 is this store (0x144038). **Unknown**: a reader through a computed base.

**Link to the vendor-stock research** (t3/research-vendor-stock 4c73914,
`docs/spec/vendor-stock.md`):
- mode 0, which is what this command passes, "takes the menu branch and preserves all three
  stock buffers";
- stock is generated by the session loop when a store level loads, not by this command
  ("The command at 0x144010 selects/defer-opens a store, not new stock");
- the opened shop is that document's state machine: panel 0 state 3, panel 1 state 2,
  `g_shopOpen` 0x41b50c = 1, offline pause 1; executed there with `shop_task` 0x1c6068.

In this round `shop_openOrStock` was a stub.

**Client (Inferred)**:
- index = argument when it is below 0x15 (0 at every shipped hub/hub2 site);
- if a dialog is open, set the pending flag and open the vendor-stock shop (mode 0) for the
  active player when that dialog ends;
- otherwise open it now;
- never regenerate stock here.

## 7. Mutation controls

**Observed (executed)**: each control is the model with one deliberate change, run on the
first 12 direct cases of its command. Each must be rejected by the comparison:

| control | change | rejected (seed 20973 / 7) |
|---|---|---|
| autoprop_bits_for_zero | state 0 also sets reached bit 0 | 3/12, 2/12 |
| autoprop_mode_swapped | looping state pushed with mode 6, others 3 | 5/12, 5/12 |
| passable_inverted | setPassable argument inverted | 6/12, 6/12 |
| kill_no_deathscript | the deathscript is not run | 5/12, see log |
| kill_keeps_selected | g_scriptSelectedObj not cleared | 5/12, see log |
| gnome_anim_first | death animation 0 always | 4/12, see log |
| sound_first_free | the first free player instead of the last | 10/12, see log |
| lump_skip_loaded_check | a loaded lump is read again | 5/12, see log |
| store_any_index | the < 0x15 test removed | 9/12, see log |

(The full per-seed figures are in the PASS log; see the report.)

## 8. How to run

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); \
  sys.argv=["difftest_level_commands.py","--elf","local/SLUS_209.73","--data","/path/BG/DATA","--seed","20973"]; \
  runpy.run_path("tools/difftest_level_commands.py", run_name="__main__")'
```

Run the same command with `--seed 7` for the second seed. The defaults are 40 direct cases
per command, 12 controls, 20 tormenta and 20 islgnome runs, every hub/hub2 store entry twice
and every soundSequence entry ten times. Unit tests:
`python3 -m unittest discover -s tools -p 'test_ref_level_commands.py'`.

## 9. Not established here

- The object constructors: the AutoProp fields were set from the records by hand.
- Level load order against `start`.
- The other classes' slot 27.
- `res_find`, the `cd_*` bodies, `shop_openOrStock` and the per-frame sound updater.
- Nested-run `activateStore` arguments.
- Net play beyond the recorded calls.
- Anything on a live game.
