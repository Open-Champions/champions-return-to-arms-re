# Missions 9 to 12 and the ending

US `SLUS_209.73` v2.00, research worktree `t3/research-story-m9-12`, 2026-11-09.
This continues `docs/story-route.md`. Section 6 there lists the menu confirm
that writes each story level; that confirm is not re-run here:

| Mission | Row | Story level | Evil level | Act |
|---|---:|---|---|---:|
| 9 | 8 | `storm1` | none | 8 |
| 10 | 9 | `fay2` | `fay1` | 9 |
| 11 | 10 | `nit1` | none | 10 |
| 12 | 11 | `bossgood` | `bossevil` | 11 |

This is a function-level trace with constructed state. It is not a played
campaign and not a native-client result. `tools/difftest_story_mission912.py`
(called "the test" below, with line numbers) runs the original level and hub
script entries, and `frontend_start`, in `tools/ee_emu.py` at seeds 20973 and
7. Private archives, extracted scripts, script listings and the real text keys
stay in ignored `local/`.

## Evidence rules used here

- **Observed** means read from the executable or a shipped script image at the
  stated address or script offset. **Executed** means the original code ran
  in `ee_emu.py` and the test asserts the result. **Inferred** means a
  conclusion drawn from those, not run. **Unknown** means not established.
- Every entry runs through `scr_load` `0x13e8f8`, `scr_registerNatives`
  `0x141310` and `script_runByName` `0x1ed694` (the harness in
  `tools/difftest_natives.py`), as in sections 7 and 8 of `story-route.md`.
- Sentinels, set by `prepare` (test lines 224–231, and
  `difftest_story_mission45.prepare`): mission bytes 8..12 on all four player
  records start at `0xA0`; quest slots at `0x5A`; the other three records'
  quest counts at `0x5A5A5A5A`; pending level `PENDING-SENTINEL`; entrance
  `ENTRANCE-SENTINEL`; orientation `0x5A`. Player-flag words at record
  `+0x4c28` start at `0xA5A5A5A5` (bit 0 set, bit 4 clear). Where a test
  says a variable was stored, it planted `0x5A` (or the value is newly created)
  and checks the recorded write (`require_stored`). "Held" (test lines
  238–242) means every story byte 8..12 on every record is still `0xA0`.
- One player, difficulty 0, `g_paused` 0, unless stated.
- **Call lists** are the exact ordered list of stubbed callees an entry made.
  The stubs are the 96 entries of `ref_natives.EXT`. Unless stated, every stub
  returns 0. Exceptions: `inventory_countItemByName` returns the "count" named
  in each claim, `inventory_findItemBySubstring` returns not found, and
  `memcard_getState` returns the "card" value named. A claim that depends on
  a stub's return says so.
- **Text keys.** Quest and help keys are disc text, so this file names them by
  neutral ids. The test reads each one from the script image at a fixed call
  site (`TEXT_SITES`, test lines 65–90; `read_keys`, lines 139–159) and checks
  execution against it. `--keys-out local/m912-keys.tsv` writes the real map
  to an ignored path.

| Id | Where the key is | Use |
|---|---|---|
| `KV1` | `valor` `removeQuest` at `0x75c` | the quest removed when mission 9 is offered |
| `Q9` | `storm1` `addQuest` at `0x218` (title, body) | mission 9 quest |
| `Q10g` / `Q10e` | `fay2` `addQuest` `0x5b8` / `fay1` `addQuest` `0x5e0` | mission 10 good / evil quest |
| `Q11` | `nit1` `addQuest` at `0x190` | mission 11 quest |
| `H9s`, `B9`, `H9` | `storm4` `0x470`; `storm2` `showBust` `0xe64` arg 1; `storm2` `0xf10` | shard help, remaining-count bust text, completion help |
| `H10e`, `H10g` | `fay3` `0x12cc`; body at `0x13fc` (same title) | mission 10 completion help |
| `H11`, `H11m` | `nit2` `0x878`; `nitmar1` `0x19c` | mission 11 completion help |
| `H12` | `bossgood` and `bossevil` `0xadc` (same pair) | final-shard help |

`read_keys` also asserts that hub `setMissi22ce`/`setMissi8ea7` add the
same `Q10g` pair, hub2 `setMissiec81` the `Q10e` pair, hub/hub2
`setMissi3604`/`setMissi2732` the `Q11` pair (executed, test lines 842–868),
that `fay3` removes `Q10e`/`Q10g` and `nit2` removes `Q11` (lines 151–158).

## 1. Who writes missions 9 to 12 at all

**Observed, asserted over the whole disc** (`CENSUS` and `check_census`,
test lines 874–951): the test parses every `.GOB` script on the owner's disc
(more than 100 files) and reads the raw first immediate of each
`setMissionAvailable` and `grantMission` call. No call has a computed first
argument. For missions 9 to 12 the complete site list is:

| Mission | `setMissionAvailable(n, 1)` | `grantMission(n)` |
|---|---|---|
| 9 | `valor` `0x730` (`setMissie47a`), `storm1` `0x24c` (`start`) | `storm2` `0xf70` (`checkEveryFrame`) |
| 10 | `fay1` `0x648`, `fay2` `0x620` (`start`); hub `0x1764`, `0x17b0`, `0x25d8`, `0x2658`; hub2 `0x3b20`, `0x3b6c`, `0x46e4` | `fay3` `0xe8c` (`anchorscript`) |
| 11 | `nit1` `0xbc`, `nitmar1` `0x78` (`start`); hub `0x19d0`, `0x1a1c`, `0x2730`; hub2 `0x3d8c`, `0x3dd8`, `0x4764`, `0x47e4` | `nit2` `0x8d8` (`shardCheck`), `nitmar1` `0x1c8` |
| 12 | `bossgood` `0x34`, `bossevil` `0x34`, `fearboss` `0x78`; hub `0x1c3c`, `0x1c88`, `0x27b0`; hub2 `0x3ff8`, `0x4044`, `0x48bc` | `bossgood` `0xb3c`, `bossevil` `0xb3c`, `endgood` `0xdc`, `endbad` `0xdc`, `fearboss` `0xf0` |

So no hub or hub2 entry makes mission 9 available. Its only offer is in
`valor` (mission 7's level). `fearboss` and `nitmar1` are standalone
`start`-plus-trigger levels like `water1` in section 8; `fearboss` is not run
here.

## 2. Mission 9: `storm1`

### How mission 9 becomes available

**Observed** (`check_links`, test lines 199–201): `valor`'s `mattmar.dbin`
node 0 has condition `if2a2e` and action `setMissi1bb4` (target node 1).
Node 2 has condition `ifa054` and action `setMissie47a` (target node 3).

**Executed** (test lines 291–323): `setMissie47a` sets mission 9's
available bit on record 0 only (`0xA1`). Records 1–3, and missions 8, 10, 11
and 12 on all records, stay `0xA0`. With `KV1` planted as the only quest, the
count becomes 0 and the slot becomes the `NoQuests` placeholder. With a
different title planted, that quest stays. Call list: empty.
`setMissi1bb4` sets mission 8 the same way and edits no quest.
`ifa054` returns 1 exactly when mission 9's available bit is clear
(`0xA0`, `0xA2` → 1; `0xA1`, `0xA3` → 0), whatever mission 8's byte is.
`if2a2e` is the same test on mission 8. Neither checks mission 7's
completion.

**Inferred:** under the first-true node rule, node 2 opens only when nodes 0
and 1 are false. Node 1's condition `if84f0` was not run, and
`dialog_onMsg` was not run. Mission 8's completion (`fire5` `0x58c`) belongs
to the mission 6–8 work and is not run here.

### How mission 9 starts after the menu request

**Executed** (test lines 326–347): `storm1` `start` from `0xA0`:
- `getMissionComplete(9)` at `0x1d8` returns 0.
- Adds quest `Q9` (count 1).
- `setMissionAvailable(9, 1)` makes record 0 `0xA1`; the rest stay held.
- Stores `startedMission9` 1 and `currentMission` 9 over a planted `0x5A`.
- Posts `absorb`.
- Pending level stays the sentinel, the seed is unchanged, and the call list
  is empty.

With mission 9 already complete (`0xA2`) it does the same, except no quest is
added and the byte becomes `0xA3`.

**Executed** (lines 348–361): `absorb` calls `cut_start` for `storm` when
`sawstorm` is absent or 0. Call list: `res_find(".lmp", "storm.cut")` →
0, `cut_start(0, "storm.cut")`. It stores `sawstorm` 1. With `sawstorm`
planted at `0x5A` or 1 it makes no call and no store. The gate is
`== 0`, unlike `wat1`.

### The storm levels

**Executed** (`TRAVEL` and `check_travel`, test lines 365–408). Each entry
requests the level, stores orientation `0xff` over `0x5A`, leaves mission
bytes and quests held, and calls only `net_closeLocalMenus(0)`, which
returns 0. "—" means the entrance sentinel is left in place.

| Level | Entry | Pending | Entrance |
|---|---|---|---|
| `storm1` | `setEntrac6fa` | `storm1c` | `entrance` |
| `storm1` | `setEntra6fc5` | `storm1c` | `exit` |
| `storm1` | `newWorld68d7` | `storm1a` | — |
| `storm1` | `newWorld92e0` | `storm1b` | — |
| `storm1` | `newWorldebc5` | `storm2` | — |
| `storm1a` | `setEntra52d2` | `storm1` | `1a` |
| `storm1b` | `setEntra31d` | `storm1` | `1b` |
| `storm1c` | `setEntra2ec7` | `storm1` | `entrance` |
| `storm1c` | `setEntraf253` | `storm1` | `exit` |
| `storm2` | `newWorld1940` | `storm1` | `grenidor` |
| `storm2` | `newWorld43c8` | `storm5` | — |
| `storm5` | `newWorldebc5` | `storm2` | — |
| `storm5` | `newWorld1dd1` | `storm3` | — |
| `storm3` | `newWorld43c8` | `storm5` | — |
| `storm3` | `newWorlda363` | `storm4` | — |
| `storm4` | `newWorld1dd1` | `storm3` | — |

**Observed** (`check_links`, lines 173–198): each entry is named by a
`PushTrigger` `action=` (and `storm3`/`storm4` also by a `Trigger` `t=`)
property in that level's `objects.ob`. Which use reaches them was not run.

### The shard: `storm4`

**Executed** (test lines 411–428): `storm4` `start` stores `currentMission`
9. It does not set availability. Call list:
`inventory_countItemByName("shardofstorms", 0)`, and that count (0 here) is
saved in script local `0xc`. It queues `shardCheck` and posts `absorb`.
`absorb` cuts `boss` (`res_find(".lmp", "boss.cut")` → 0,
`cut_start(0, "boss.cut")`), stores `sawBoss` 1 and posts `cutsave`.

**Executed** (lines 429–452): after that `start`, 24 unpaused `shardCheck`
calls make no call and leave the flag words, `stm_gotShard` (planted `0x5A`)
and the mission bytes alone. The 25th unpaused call compares the item count
with local `0xc`:
- **Count stub 1 or 2:** sets bit 4 of the flag word on all four records
  (`0xA5A5A5A5` → `0xA5A5A5B5`) and stores `stm_gotShard` 1. Call list:
  - `inventory_countItemByName("shardofstorms", 0)`
  - `text_lookup(H9s title)`, `text_lookup(H9s body)`
  - `hud_showHelpMessage(-1, 0, 0)`
  - `player_voice(0, 9)`, from `playGotItemSound`

  It posts `secondMsgDelay` and does not requeue `shardCheck`.
- **Count stub 0:** the only call is the count. No flag or variable store.
- A `g_paused` call does not count, so the grant comes one unpaused call later.

`storm4` never grants mission 9. All story bytes stay held. With no player
object planted, `onePlayerHasItem` returns 0, so `removePlayerItem` is not
reached. The shard is not removed in this harness. This depends on there
being no player object, not on a stub.

### How mission 9 is marked complete: `storm2`

**Executed** (test lines 456–468): `storm2` `start` stores `currentMission`
9. If `getPlayerFlag(0, 4)` is set (record 0 flag word `0xA5A5A5B5`), it
clears bit 4 on all four records, stores `stm_gotShard` 1 and queues
`checkEveryFrame`. Without the flag it creates `stm_gotShard` at 0 and
queues nothing. Call list in both cases: `automap_revealAll()`.

**Observed** (`storm2` script `0xd98`–`0x1028`, local listing): each call
copies the live-monster count (script local `0xb0`, raised by the
three init scripts and `rezzone`, lowered by `invdeathscript`) into a local. While that count
is below 21 and `storm2cleared` is 0, it shows the remaining-count bust. When
the count is 0 and the frame counter (local `0xac`, cleared by `start`)
equals 100, it stores `storm2cleared` 1 and shows the help. Then, if
`stm_gotShard` is set, it grants mission 9 and plays the completion sound.
The counter only advances when `gamePaused` is 0. The entry always requeues
itself.

**Executed** (lines 469–498), with the monster count at its image value 0
(no monsters were spawned, and this is a precondition of the claim):
- **Calls 1–100:** each call list is `text_lookup(B9)`, then
  `hud_setBust("bust_bubonian.tex", 0, 0, -1)`. No store; the story bytes are
  held.
- **Call 101 with `stm_gotShard` 1:** stores `storm2cleared` 1 and makes
  mission 9 `0xA2` on all four records. Call list: the two bust calls,
  `text_lookup(H9 title)`, `text_lookup(H9 body)`,
  `hud_showHelpMessage(-1, 0, 0)`, `res_find("fx.lmp",
  "quest_complete.anm")` → 0, `sound_playOnObject(0, 0, 1.0)` and
  `sound_setPlaysWhileFrozen(0)`.
- **Call 101 with `stm_gotShard` 0:** stores `storm2cleared` 1 and shows the
  help, but grants nothing. Every later call returns with no call. So a
  shardless clear forfeits this grant path.
- **Paused calls:** 50 unpaused, 10 paused, then 50 unpaused calls do not
  grant; the next call does.

**Observed, not executed** (hub script `0x3150`–`0x3244`): hub `start` clears
flag bit 4 on all players unless `currentMission` is 7 or 9. The shard flag
therefore survives a hub visit during mission 9.

### Which entries make mission 10 available

See section 6. Mission 9's grant does not set mission 10's bit: after the
101st call, mission 10 is still `0xA0` (held check, line 482).

## 3. Mission 10: `fay2` (good) or `fay1` (evil)

### How mission 10 starts

**Executed** (test lines 507–522): `preStart` decides only while
`playerisevil` and `playerisgood` are both absent or 0. The `madeDecision`
byte is record `+0x4c1b`, and the evil byte `+0x4c1a`.
- No decision: `fay2` stores good (`playerisevil` 0, `playerisgood` 1), and
  `fay1` stores evil.
- Decision made: both levels store evil when the evil byte is set, otherwise
  good.

Call list: `lump_load("bust.lmp")`, which returns 0, so nothing is loaded.
With `playerisgood` already 1 there is no store.

**Executed** (lines 523–542): `start` on either level makes mission 10
available on record 0 (`0xA1` from `0xA0`, `0xA3` from `0xA2`). It stores
`startedMission10` 1 and `currentMission` 10 and queues `checkEachFrame`.
- `fay2` adds `Q10g` only when the evil byte is clear and mission 10 is not
  complete.
- `fay1` adds `Q10e` only when the evil byte is set and mission 10 is not
  complete.
- Otherwise no quest is added.

Call list: empty. The seed is unchanged because both side variables were
absent, so the axe-box `getRand` branch is not reached.

**Executed** (`TRAVEL`): `fay2` `setEntrad0dc` → `fay3` entrance
`kelethin`; `fay1` `newWorldf59a` → `fay3`; `fay3` `newWorld5640` →
`fay1`, `newWorldbff` → `fay2`, `newWorld6f17` → `faybonus`. Each sets
orientation `0xff` and calls only `net_closeLocalMenus(0)`.

**Not run:** the `checkEachFrame` kill counters on `fay1`/`fay2`, the orc
cut, and the `we_king` dialog.

### How mission 10 is marked complete: `fay3` anchors

**Observed:** `SpiritAnchorAct` `action=anchorscript` in `fay3`
(`check_links`).

**Executed** (lines 544–567): each `anchorscript` call adds 1 to
`anchCompleted`. Calls 1–7 change no story byte and no quest, and make no
call. On call 8 it:
- makes mission 10 `0xA2` on all four records (others held);
- stores `fay3done` 1 over `0x5A`;
- removes `Q10e` if `playerisevil` is 1 and `Q10g` if `playerisgood` is 1
  (planted as the only quest, which leaves `NoQuests`). On the good side a
  planted `Q10e` stays.

Call list: empty.

**Executed** (lines 568–578): `missionDone`, which `fay3` `checkEachFrame`
queues when `anchCompleted` is 8, removes the side's quest. Call list:
- `res_find("fx.lmp", "quest_complete.anm")`, `sound_playOnObject(0, 0, 1.0)`,
  `sound_setPlaysWhileFrozen(0)`
- `text_lookup(H10e title)`
- `text_lookup` of the `H10e` body on the evil side or the `H10g` body on the
  good side
- `hud_showHelpMessage(-1, 0, 0)`

`g_networkMode` is 0, so `setInfo` is not called. `checkEachFrame` itself
was not run; the countdown local it reads comes from `getScaledTime`.

## 4. Mission 11: `nit1`

### How mission 11 starts

**Executed** (test lines 586–603): `nit1` `start` makes mission 11
available on record 0 and stores `startedMission11` 1 and `currentMission`
11. It adds `Q11` when mission 11 is not complete. Call list: empty.
`faywords` is set from `getRand() % 4 + 1`. It ends between 1 and 4 and **the
seed changes**: this entry consumes a shared random draw.

**Executed** (`TRAVEL`): `nit1` `newWorld980` → `nitdung1`, `newWorld3ab3` →
`nitdung4`; `nitdung1` `newWorld9ad` → `nit1` (`n1nd1`), `newWorldb992`
→ `nitdung2` (`nd1nd2`); `nitdung2` `newWorld22cd` → `nitdung1`
(`nd1nd2`), `newWorld3da6` → `nit2` (`nd2n2`); `nit2` `newWorld6e37` →
`nitdung2` (`nd2n2`); `nitdung4` `newWorldbafc` → `nit1` (`n1nd4`).

### How mission 11 is marked complete: `nit2`

**Executed** (lines 604–631): `nit2` `start` saves the shard count
(`inventory_countItemByName("shardofnightmare", 0)`; the call list is just
that) and queues `shardCheck`. With `Q11` planted afterwards:
- **Calls 1–24:** no call and no change.
- **Call 25, count stub 1:** makes mission 11 `0xA2` on all four records,
  stores `nit_gotShard` 1, removes `Q11` (`NoQuests`) and does not requeue.
  Call list: the count, `text_lookup(H11 title)`, `text_lookup(H11 body)`,
  `hud_showHelpMessage(-1, 0, 0)`, then the three sound calls above.
- **Call 25, count stub 0:** no grant and no store.
- **`nit2` `shardCheck` has no `gamePaused` test:** 25 calls with `g_paused`
  1 still grant.

**Executed** (lines 632–640): the second writer. `nitmar1` `start` makes
mission 11 available with no quest. Its trigger `callScri7351` grants mission
11 on all four records with no quest edit. Call list: `text_lookup(H11m
title)`, `text_lookup(H11m body)`, `hud_showHelpMessage(-1, 0, 0)`.

## 5. Mission 12: `bossgood` or `bossevil`, and the ending

### How mission 12 starts

**Executed** (test lines 650–664), on both levels:
- `start` makes mission 12 available on record 0 and stores
  `startedMission12` 1 and `currentMission` 12.
- It posts `absorb`, creates `killedThule` (good) or `killedMar` (evil) at 0,
  and stores `g_saveInhibit` `0x50605c` = 1 over `0x5A5A5A5A`.
- It saves the count of `shardoffear` (good) or `shardoftranquility` (evil)
  and queues `shardCheck`.
- No quest. Call list: that one count.

`absorb` cuts `boss`, stores `sawThule`/`sawMar` 1 and posts
`cutsave`. `killedboss` stores `killedThules` (good; note the extra `s`,
so `start`'s test of `killedThule` never sees it) or `killedMar` (evil) 1,
with no call (lines 718–729).

### How mission 12 is first marked complete

**Executed** (lines 665–682): after `start`, 24 unpaused `shardCheck`
calls do nothing.
- **Call 25, count stub 1:** stores `finalShard` 1. Mission 12 becomes
  `0xA3` on record 0 (it was `0xA1`) and `0xA2` on records 1–3. Call list:
  the count, `text_lookup(H12 title)`, `text_lookup(H12 body)`,
  `hud_showHelpMessage(-1, 0, 0)`. There is no completion sound.
- **Count stub 0:** no grant and no store.

The removal loop again needs a player object, so no item is removed.

### The exit to the ending

**Observed:** both boss levels carry `PushTrigger` `key=returnc798` with
`action=callScri53d3`, and `Trigger` `t=callScri1ef1` (`check_links`).

**Executed** (lines 683–704):
- `returnc798` returns `finalShard`: 0 when absent or 0, 1 when set.
- `gatewaytrigger` (through `callScri1ef1`) stores `firedgate` 1 only when
  `finalShard` is set and `firedgate` is 0. Its `trigger("portal", 0)` found
  no object named `portal` in this harness, so the call list is empty. That
  is a harness limit; section 2 of `story-route.md` ran the same request with
  a synthetic portal.

**Executed** (lines 705–717): `callScri53d3` → `end`:
- Stores `g_saveInhibit` 0 over `0x5A5A5A5A`.
- `setPlayerFlag(-1, 0, 0)` clears bit 0 of record 0's flag word only, because
  there is one player. Records 1–3 stay `0xA5A5A5A5`.
- Tries to remove 25 named story items for player 0: the call list is 25
  `inventory_findItemBySubstring(0, item)` calls, each "not found", so
  nothing is removed. That outcome depends on the stub.
- Requests `endgood` (from `bossgood`) or `endbad` (from `bossevil`), stores
  orientation `0xff`, leaves the entrance alone, and calls
  `net_closeLocalMenus(0)` last.

The story bytes are unchanged by `end`. The pairing of key and action is
**Inferred** from the properties; `PushTrigger_interact` was not run.

### The ending levels: what completion triggers

**Executed** (test lines 733–747): `endgood` and `endbad` `start` posts
`absorbExtra`, with no call. `absorbExtra`:
- calls `res_find(".lmp", "endgood.cut")` / `"endbad.cut"` → 0, then
  `cut_start(0, …)`;
- posts `bailFromGameWin`;
- grants mission 12 again: `0xA2` on all four records from `0xA0`. This is a
  second completion writer after the shard grant.

**Executed** (lines 748–788), difficulty 1 and 0, card idle
(`memcard_getState` → −1) and busy (→ 0). Destinations were pre-filled:
`g_sessionExitCode` `0x41b508` = `0x5A5A5A5A`, `g_gameCompleteFlag`
`0x4f85c5` = `0x5A`, config byte `0x4f8f38` = `0x41`, and `0x41b4f8` =
`0x5A5A5A5A`. Each call is one deferred tick of `bailFromGameWin`, which
always requeues itself.

1. **Tick 1** runs `saveEndConfig`. Call list:
   `game_sendCharacterToLobby(-1)`, `memcard_requestConfigSave()`. It stores:
   - `g_gameCompleteFlag` 1 (recorded write);
   - `g_paused` 1 and `0x41b4f8` 1;
   - config byte `0x4f8f38` |= `0x08` at difficulty 1 (`0x41` → `0x49`),
     unchanged at difficulty 0.

   The exit code stays the sentinel. `g_networkMode` is 0, so
   `net_dropAllRemotes` is not called.
2. **Tick 2, card idle:** runs `saveGame`. Call list: `memcard_getState()`,
   `net_getLocalPlayerSlot(0)` (stub → slot 0), `memcard_requestSave(0)`.
   **Card busy:** the call list is `memcard_getState()` only, and the
   machine stays at this step.
3. **Tick 3, card idle:** the call list is `memcard_getState()`, then
   `leaveGame(1)` stores `g_sessionExitCode` = `0x65` (recorded write).
   **Card busy:** the exit code stays the sentinel.

Mission bytes, quests and the seed are unchanged by these ticks. Whether the
save starts at all depends on the `memcard_getState` stub.

**Observed, not executed** (`main` `0x324234`–`0x324264`): after
`mainloop_runSession` returns, exit code 1 restarts the front end with
`frontend_start(0)`, `0x65` with `frontend_start(1)`, and `0xc9` with
`frontend_start(2)`.

**Executed** (`check_frontend`, test lines 792–828; every callee of
`frontend_start` `0x1e1f34` stubbed to return 0):
- `frontend_start(1)` stores 1 at `0x4f701a` (pre-filled `0x5A`) and writes
  `intro` to `g_pendingLevel`. It adds the `frontend_run` task
  (`task_add(0x1e08f0, 25, …)`). Its last three calls are:
  - `stream_clearQueue(2)`
  - `music_playGlobal("mx_endcredits_ext_l.vag", 3)`
  - `credits_load(1)`

  It sets `g_frontendState` `0x4f6b78` = 15 and `g_frontendMenu` = `0x4f6fb8`.
- `frontend_start(0)` and `(2)` store 0 at `0x4f701a` and never call
  `credits_load` or the music. The state is 0 there because the stubbed
  `0x3283b0` returned 0. With a nonzero return the code would store state 10
  instead (observed at `0x1e205c`–`0x1e2078`), not run.

So the ending request is the exit code `0x65` from `leaveGame(1)`. The
front end then plays the end-credits stream and opens credits state 15.
`credits_run` `0x223d3c` itself was not run.

**State the ending writes** (executed unless marked):
- mission 12 complete on all records for the current difficulty;
- `g_gameCompleteFlag` 1;
- `g_paused` 1 and `0x41b4f8` 1;
- the difficulty completion bit in `0x4f8f38` (`0x08` for difficulty 1
  executed here; `0x10`/`0x20`/`0x40` for 2–4 per `docs/spec/script-builtins.md`
  line 512, not re-run);
- the config-save and save requests (stubs);
- exit code `0x65`.

Per earlier work, not re-run: `saveEndConfig` also clears bytes `0x4d8a08`
and `0x4039c0` (`docs/spec/script-builtins.md` line 512), and the save
header level name becomes `gameComplete` while the flag is set
(`docs/audio-save.md` line 61).

## 6. Which entries make the next mission available

**Observed** (`check_links`, test lines 202–220) and **Executed** (lines
830–869):
- The hub conditions `if3a40`, `if2302` and `ifb354` return 1 exactly when
  mission 10, 11 or 12 respectively is not available (bit 0 clear), on both
  hub and hub2. Call list: empty.
- Each action below sets that mission's available bit on record 0 only
  (`0xA1`), leaves the other story bytes held, and does not change the
  pending level.
- "shop" means the call list is `dialog_isOpen()` → 0, then
  `shop_openOrStock(0, 0, 1)` → 0. No shop opens because both are stubbed.

| Dialog file, node: condition | Actions | Mission | Quest | Shop |
|---|---|---:|---|---|
| hub `firiona` 24: `if3a40` | `setMissi22ce`, `setMissi8ea7` | 10 | `Q10g` | second only |
| hub `firiona_bak` 22: `if3a40` | `setMissi4db8`, `setMissi9964` | 10 | none | second only |
| hub2 `natasla` 19: `if3a40` | `setMissiec81` | 10 | `Q10e` | no |
| hub2 `natasla_bak` 20: `if3a40` | `setMissi4db8`, `setMissi9964` | 10 | none | second only |
| hub `firiona` 26: `if2302` | `setMissi3604` | 11 | `Q11` | no |
| hub `firiona_bak` 24, hub2 `natasla_bak` 22: `if2302` | `setMissi6baa`, `setMissi8b33` | 11 | none | second only |
| hub2 `natasla` 21: `if2302` | `setMissi3604`, `setMissi2732` | 11 | `Q11` | second only |
| hub `firiona` 29, hub2 `natasla` 24: `ifb354` | `setMissia052`, `setMissib397` | 12 | none | second only |
| hub `firiona_bak` 27, hub2 `natasla_bak` 25: `ifb354` | `setMissia052`, `setMissi350c` | 12 | none | second only |

The level `start` entries in sections 3–5 also make their own mission
available when entered from the menu. Mission 9's next-mission source is the
table above (mission 10). Mission 12's "next" is the ending in section 5. No
grant (`storm2`, `fay3`, `nit2`, the boss shard, `absorbExtra`) sets the next
mission's bit; each of those runs leaves the other story bytes held.

**Inferred:** the hub dialog shows the first node whose condition is true.
The earlier nodes' conditions (for missions 1–9) and `dialog_onMsg` were not
run, so this file does not show which node a given campaign state opens.
Which of `firiona` or `firiona_bak` the hub NPC uses is the link in section 1
of `story-route.md` (`startDia3314`), not re-checked here.

## 7. What the client can implement from this

1. **Mission 9 offer.** `valor` dialog node 2's action makes mission 9
   available on record 0 and removes quest `KV1`. No hub entry offers
   mission 9.
2. **`storm1` `start`** makes mission 9 available. It adds `Q9` unless
   mission 9 is complete, stores `startedMission9` and `currentMission` 9,
   and posts `absorb`. `absorb` plays cut `storm` once, gated on
   `sawstorm == 0`.
3. **Storm travel.** The sixteen storm entries in the section 2 table request
   their levels and entrances with orientation `0xff`.
4. **`storm4` shard.** Count `shardofstorms` at `start`. On every 25th
   unpaused `shardCheck` where the count has risen, set player flag 4 on every
   record, store `stm_gotShard`, show `H9s` and play the got-item voice.
   Do not grant there.
5. **`storm2` `start`** turns flag 4 into `stm_gotShard` 1, clears flag 4,
   and only then queues `checkEveryFrame`. Hub `start` must keep flag 4
   while `currentMission` is 7 or 9 (observed, not run).
6. **Grant mission 9 in `storm2` `checkEveryFrame`.** It needs no monsters
   left and 100 unpaused frames counted. It stores `storm2cleared` and shows
   `H9`, then grants (all records) and plays the sound only if
   `stm_gotShard` is set. If the shard is missing at that moment, the clear is
   spent and that path never grants. Showing the bust while fewer than 21
   remain is cosmetic.
7. **Mission 10 `preStart`.** Pick the side as in section 3. `start` (either
   level) makes mission 10 available, stores the two variables and adds
   `Q10g` (fay2, good) or `Q10e` (fay1, evil) unless already complete.
   Travel goes to `fay3` (`kelethin` from fay2).
8. **Grant mission 10 on the 8th `fay3` `anchorscript`.** Store `fay3done`
   and remove the side's quest. `missionDone` repeats the removal, plays the
   sound and shows `H10e` or `H10g`.
9. **`nit1` `start`** makes mission 11 available, adds `Q11` unless complete,
   and consumes one `getRand` draw. Travel follows the nit table.
10. **Grant mission 11 on the 25th `nit2` `shardCheck`** once the
    `shardofnightmare` count has risen. This check counts paused frames too.
    Store `nit_gotShard`, remove `Q11`, show `H11` and play the sound.
    `nitmar1`'s trigger is a second writer.
11. **Boss `start`** makes mission 12 available and sets save-inhibit. Count
    `shardoffear` (good) or `shardoftranquility` (evil). The 25th unpaused
    `shardCheck` with a raised count grants mission 12 and stores
    `finalShard`. Shows `H12`, no sound.
12. **Boss exit.** The portal request fires once `finalShard` is set; the
    exit key is `finalShard`. Its action clears save-inhibit, clears player
    flag 0, removes the story items and requests `endgood` or `endbad`.
13. **Ending level.** `start` posts `absorbExtra`, which plays the ending cut,
    grants mission 12 again and posts the bail loop. The loop runs
    `saveEndConfig` once, then `saveGame` when the card is idle, then
    `leaveGame(1)` when idle again. Keep it requeued every tick.
14. **Front end after the ending.** Exit code `0x65` restarts the front end in
    mode 1. That mode starts the end-credits stream and credits state 15
    instead of the main menu.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_story_mission912.py","--elf","local/SLUS_209.73","--data","/path/to/BG/DATA","--keys-out","local/m912-keys.tsv"]; runpy.run_path("tools/difftest_story_mission912.py", run_name="__main__")'
```

Result on the owner's disc: `PASS seed 20973: 244` and `PASS seed 7: 244`
mission-9..12 and ending checks. The log is in ignored `local/story-m912.log`.

## 8. Unknown

- The menu-to-level load and arrival for each of the six story levels.
- Which object use reaches the travel entries, the anchors, the boss key and
  action, and the dialogs. `PushTrigger_interact` and `dialog_onMsg` were not
  run.
- Live monster counts for `storm2`, and the `fay1`/`fay2` kill counters.
- Real inventory counts, and item removal with a player object present.
- `fay3` `checkEachFrame`'s countdown.
- The Portal virtual call on the boss levels.
- `fearboss`.
- `credits_run`, and the medal and bonus levels (`nitmedal`, `faybonus`,
  `nitbonus`, `nitbon2`).
- A continuous session from the menu through the credits.
