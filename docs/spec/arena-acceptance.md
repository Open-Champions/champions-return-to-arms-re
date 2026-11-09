# Arena acceptance boundary: what mode-B acceptance needs (round 12)

US `SLUS_209.73` v2.00. Research date 2026-11-09. Branch `t3/research-arena-match`,
starting at `d4f58da` (round 11). Cross-branch pins: `research-arena-live@9a0c26a`
(`docs/spec/arena-live-scheduler.md`), `research-inventory-reset@ce2e086`
(`docs/inventory-reset.md`), `research-spells-r3@6052213` (`docs/spec/combat-r6.md`),
`research-loot-drop@0643323` (`docs/loot-drop.md`).

Labels: **Executed** means the original function ran in `tools/ee_emu.py` and a check
compared it with an independent model. **Observed** means read at the address given,
not run. **Inferred** is a conclusion from those. **Unknown** is open. Nothing here
ran on a console, in Play!/PCSX2, or in the native client. No game text, table bytes,
disassembly or disc data is stored; the probes read them at run time and print
addresses, counts and hashes.

New tools (additive; no existing reference API, vector or difftest changed):

| File | What it runs |
|---|---|
| `tools/ref_arena_acceptance.py` | independent model of every rule below |
| `tools/test_ref_arena_acceptance.py` | pure model tests, no executable |
| `tools/difftest_arena_acceptance.py` | setup, init, results page, overflow, knock-back (sections 1-2, 5, 8, 10) |
| `tools/difftest_arena_round12.py` | controller-only three-wave run with the real task (section 9) |
| `tools/disc_dir.py` | lets the disc probes read an extracted disc directory |

## 0. Checklist: what the client needs to stop refusing mode-B acceptance

The native round-5 report refused live acceptance for seven reasons
(`native-arena` `work/loop-native-arena-r5-report.md`, "Refusals retained").
Each is answered here. A row is a contract the client can implement and test against;
it is not a claim that a full match ran on hardware.

| Refusal | Answer | Label | Where |
|---|---|---|---|
| Natural victory | Mode B has **no victory state**. A level ends after three cleared waves with a next-level request; the match ends only in defeat (all active slots out, no positive snapshot). Mode A's "win" is the kill limit, which opens the result page during an intermission and then rotates the map. The client must not add a win screen or a final wave. | Executed bodies + Observed store inventory; "no external writer" is Inferred | §4 |
| Normal-input kills | Creatures die from controller input through `Player_run` alone, with the original task running every frame: 8 kills over waves 0–2 on seed 20973, 3 kills over waves 0–1 on seed 7. Wave 0 is cleared on both seeds. | Executed (fixture bounds in §9); a whole three-wave level by controller is still partial | §9 |
| Later creature ticks | Wave-1 and wave-2 creatures, built by the original `arena_startWave` from the original empty-wave → intermission → next-wave path, are ticked by their class bodies every frame; Goblins, Mummies and a Scorpion fight and die. | Executed | §9 |
| Displayed results | The result page is `arena_drawPrompt` `0x3075dc`. Its header is one of three looked-up formats (mode-A winner name, mode-B defeat with wave+1, mode-B intermission with wave+1), followed by one row per active slot in rank order: place `N.`, name, signed kill count. | Executed (text services recorded, glyph drawing stubbed) | §5 |
| Fixed rewards / collection | There is **no fixed arena reward**. Entry clears each active record's gold; rewards are the ordinary kill experience and loot drops; gold buys extra lives; a restart restores the pre-arena record snapshot. | Executed except loot pickup inside the arena (Unknown here; the pickup body is executed on `research-loot-drop`) | §6 |
| Successful loading | The run ends at the original next-level request. On the following load `arena_init` takes its **continuing** branch (executed) and `arena_begin` adds three waves (executed on `research-arena-live`). The load body between them is the ordinary level loader. | Request and both ends Executed; the loader for a next arena map is Unknown | §7 |
| Signed-wave overflow | The wave halfword wraps from 32767 to −32768. Negative remainders spawn nothing; the remainder-0 wave takes one ring step with a negative count and spawns nothing; level requests still resolve inside the mode-B table for the sampled waves. Reaching it takes at least 32,768 waves of ≥ 608 frames each (over 90 hours at 60 Hz). | Executed | §10 |

Minimum acceptance sequence for the client, every step either executed here or at
the cited pin:

1. Front end sets the mode words, player count and difficulty (§1).
2. `arena_init` fresh branch: snapshot records, clear gold, reset scores, register
   both tasks, allocate tables, scramble strip (§2).
3. `arena_begin`: preload, three waves, `arena_startWave(1)` (`research-arena-live`
   `docs/spec/arena-live-scheduler.md:10-15`).
4. 180-frame intro with state-change refusal, then play (`docs/spec/arena-match-probe.md`
   round 10; `docs/arena-modes.md:139-145`).
5. Controller kills → death → score → experience → loot; deleted corpses leave the
   grid before the next preparation walk; empty grid on the 128-frame scan →
   intermission (interval page) → after 480/960 visits the next wave (§9).
6. After the third wave: the next-level request; then step 2's continuing branch and
   step 3 again (§7).
7. All slots out with no positive snapshot → end flag → defeat page → full fade →
   confirm (restore records, restart at recipe 0) or cancel (exit to the front end)
   (§4, §7).

## 1. Match setup, teams and opponents

**Executed** (`difftest_arena_acceptance.py` `case_setup`, 71 checks per seed). The
probe enters `frontend_run` `0x1e08f0` at its state dispatch `0x1e15c0` with the
state word `0x4f6b78`, menu word `0x4f6b7c` and selected index in `$20`, and stops
at the handlers' merge `0x1e1cac`/`0x1e1cb0`. The dispatch table `0x53d050` sends
state 2 to `0x1e1888`, 4 to `0x1e18e8` and 5 to `0x1e19d8`; a hook confirms the
handler reached. `libc_strstr` `0x3b96a8` is followed;
`frontend_startPlayerSelect` `0x1e3ba0` is a recorded stub.

- **Player count (state 2, `0x1e1888`).** Index 0–3 stores `g_numPlayers = index+1`,
  state 4 and the mode menu: the two-entry menu `0x4f6c68` (missions, arena) for one
  player, the three-entry menu `0x4f6c28` (missions, arena co-op, arena versus)
  otherwise. Every visit clears mode A `0x4f711c`, mode B `0x4f7120` and the scramble
  word `0x4f7124` (`0x1e18d0-0x1e18e4`), including an index outside 0–3, which
  changes nothing else.
- **Game mode (state 4, `0x1e18e8`).** The chosen entry's identifier string is
  searched for three short substrings at `0x53d008`, `0x53d010`, `0x53d020`
  (read at run time; hashes only in the log). Mode A = first found; scramble =
  second found; mode B = third found **or** scramble. Scramble forces
  `g_numPlayers = 1`. Then: mode A → state 5, kill-limit menu `0x4f6c98`; else
  mode B → difficulty word `0x4f719c = 1` and the player-select call (no difficulty
  menu); else state 3, difficulty menu `0x4f6e38`. Executed results on the shipped
  menus: one-player arena → B only; co-op → B only; versus → **A and B**; missions
  → neither. No shipped offline identifier contains the scramble substring
  (Observed: both mode tables listed); a synthetic identifier built from the runtime
  substring executes the scramble branch (B=1, players=1).
- **Kill limit (state 5, offline, `0x1e1a58`).** Index 0, 1, other → 5, 10, 25 at
  `0x4f8408`, then player select (Executed, four indices).
- **Net launch** (`0x137464-0x137554`, Executed for mode bytes 0–4 and two argument
  values). From the launch block `0x402b90`: difficulty `+0xa0` (signed) →
  `0x4f719c`; kill limit `+0xa2` → `0x4f8408`; all three mode words cleared, then
  mode byte `+0xa1` 1–3 → mode B, 2–3 → mode A, 3 → scramble. With mode A it calls
  `game_set4f7110` `0x1ec830(+0xf4)`, which stores the argument, or
  `game_scanCm1Vars(1)` when it is −1. So the net modes are 0 missions, 1 co-op,
  2 versus, 3 versus with scramble.
- **Teams / opponents.** There is no team-selection screen. The record team byte
  `+0x4c24` is the slot number in mode A and 0 otherwise when a character is imported
  (`0x220644-0x22067c`, Executed for slots 0–3 in both modes; neighbouring records
  untouched, no calls), and the slot number for every player of a net game
  (`0x1373d8`, Observed, `docs/spec/skills-35-68.md:2222-2226`). `Player_isEnemy`
  `0x1b5ea8` treats other players as enemies only in mode A on a different team
  (`symbols/player.tsv`). **Inferred:** versus is free-for-all; co-op puts every
  player against the monster waves.

## 2. Arena entry: `arena_init` `0x304c4c`

**Executed** (`case_init`, 14 configurations, 221 checks per seed). Called from
`game_loadLevel` at `0x1e5cdc` (Observed). Followed: the whole body,
`arena_isArenaLevel` `0x307d48`, `strcmp`, `save_playerCopy` `0x21837c`,
`arena_resetScores`, `arena_registerSpawn`, `player_removeAllItems` `0x1bf600`
and the real `inventory_removeItem` `0x1c1cb0`. Recorded stubs: `game_scanCm1Vars`
(returns 3), task add `0x19e4a0`, allocator `0x14ff88` (returns a test block),
`lump_load` `0x173558`, `res_find` `0x17365c`, and the three callees
`research-inventory-reset` also stubs (`player_recalcStats`, `player_resetIdleAnim`,
`net_isLocalSlot`).

**Branch.** `0x307d48` compares the previous level name `0x41b7c2` with the mode's
table (mode A: 13 names at `0x5037b8`; otherwise 7 at `0x503798`). If it is an arena
level **and** the end flag `0x503894` is clear, the body skips to `0x304ed0`
(continuing branch). Otherwise it runs the fresh branch. Every mode-B table name is
also in table A (Executed).

**Fresh branch** (first entry, or the level after a defeat restart):
- For each slot below `g_numPlayers`: the whole `0x4c30`-byte record is copied to
  `save_playerCopy(slot)` = `0x879ec0 + slot × 0x4c30`, then the **live** record's
  gold `+0xe4` is set to 0. Experience, level and bags stay (Executed; other slots and
  their copies untouched).
- wave `0x8e7338 = −1`, mode-A index `0x8e7343 = game_scanCm1Vars(0)`, end flag 0,
  `arena_resetScores` (lives 2, timer 2.0 for active slots).
- Tasks `arena` `0x306b78` and `arenaDraw` `0x307284`, both priority 100, the draw one
  flagged 1. Spawn table `0x320` bytes → `0x503888`, monster table `0x4b0` →
  `0x50388c`. Life budget `0x8e7358 = 100`, `0x8e7354 = 0x80000000`, and a one-byte
  list at `0x8e7238`.
- **Scramble word set:** `player_removeAllItems(slot)` for every active slot, then
  minimap mode `0x4f8400 = 1`; otherwise minimap mode 2. The real removal follows
  `research-inventory-reset` `docs/inventory-reset.md:113-134`: a bag-0 count of 2 or
  more keeps the cell that started at index 1; bags 1 and 2 are emptied. Executed
  with 3/2/1, 1/0/2, 2/1/0 and 0/0/1 cells: the `inventory_removeItem (slot, index,
  bag)` call list and the bags afterwards match the model, slots at or above
  `g_numPlayers` keep their cells, and the saved copy still holds every cell.
  **Inferred:** scramble starts a versus match with near-empty bags and restores them
  only through the snapshot. Co-op and plain versus keep the bags.

**Continuing branch** (next arena level of the same match): records, saved copies,
wave, mode-A index, budget, minimap, scores and the table pointers are all left as
they were; no task is added, nothing is allocated, nothing is removed, even with the
scramble word set (Executed).

**Both branches** load the arena lump and two resources (`0x8e734c`, `0x8e7350`, the
fonts the result page uses), store spawn count 1 and register entry 0 at the origin
with angle 0. The shared seed does not move.

## 3. Round start

Unchanged from earlier rounds: `arena_begin` (`research-arena-live`
`docs/spec/arena-live-scheduler.md:10-34`), `arena_startWave` and its recipe split
(`docs/arena-modes.md:94-145`), the intro lock and its refusal of creature state
changes (`docs/spec/arena-match-probe.md` round 10, "Observed at
`Creature_filterState`"). Round 12 runs these bodies in sequence (§9).

## 4. Win and lose conditions

Mode B (co-op and one-player arena):
- **Wave clear.** On frames where `g_simFrame & 0x7f == 0` and the end flag is clear,
  the task walks the grid with `0x3069e8`; a living count of 0 sets intermission 1
  and calls `arena_openEndPrompt` (`docs/arena-modes.md:199-201`; executed naturally
  in §9). It does not set the end flag.
- **Next wave / next level.** Intermission expiry at 480 (offline) or 960 (online)
  calls `arena_nextWave(1)` while waves remain, otherwise requests the next level
  (`docs/arena-modes.md:76-92`; §9).
- **Defeat.** All active slots out (signed lives < 0, HP ≤ 0, dead countdown 0) with
  no positive snapshot → end flag, prompt (`0x306f94`); with a positive snapshot →
  `arena_nextWave(0)` retry (`docs/arena-modes.md:202-208`;
  `tools/difftest_arena_modes.py:642-649`). The intermission-time wipe at `0x306dd4`
  does the same without the retry (`docs/arena-modes.md:194-197`).

Mode A (versus): the kill limit opens the prompt with intermission 1 and no end flag
(`0x306de8-0x306e3c`, `docs/arena-modes.md:239-246`); the intermission then always
changes map (`docs/arena-modes.md:250-253`). The page shows the winner (§5).

**Observed (store inventory):** direct stores to the end flag `0x503894` exist only at
`0x304dcc` (init clear), `0x306dd4` (intermission wipe) and `0x306f94` (live wipe);
the intermission halfword is stored only at `0x3060d8`, `0x306ddc`, `0x306e34` and
`0x306e90`. This is a text search for `lui`-based stores, not an alias proof; it
matches `research-arena-live` round 2 (`arena-live-scheduler.md:127-132`).
**Inferred:** there is no victory writer. The result page has no victory header (§5).

## 5. The result page: `arena_drawPrompt` `0x3075dc`

**Executed** (`case_results`, seven configurations per seed, 58 checks). The draw
task `0x307284` calls it while the intermission halfword is nonzero or the end flag
is set, after the intro, unless a local menu is open (Observed `0x307290-0x3072f8`).
Followed: the body, `math_hermite` `0x1658f0`, and newlib `sprintf`. Recorded stubs:
`text_lookup` `0x173c84` (returns a token per call; the key **address** is checked),
`wstr_format` `0x19ea78` (its first float argument is checked), text batch
begin/end/colour, both draw calls (the ASCII text is read at call time),
`ui_fitText` `0x1bdf60` (copies the record name into `0x4f3ec8 + 32 × slot`) and
`player_slotColor` `0x1bf2a0`.

- Fade: one `0x3c61029b` step capped at 1.0, the only store the body makes
  (`docs/arena-modes.md:221-228`).
- Header, one lookup and one format call: mode A → key `0x551f60` with the fitted
  name of rank 0 (`0x8e7348[0]`); mode B with the end flag → key `0x551f70` with
  `float(signed wave + 1)`; mode B without it (the between-waves page) → key
  `0x551f80` with the same figure. At wave `0x8000` the figure is −32767.
- Column label key `0x551f90`, drawn twice (shadow, then front).
- One row per slot below `g_numPlayers`, in rank-byte order: place `"%d."`, the
  fitted name, and the signed kill halfword in decimal, drawn at x 0x7b/0xa0/0x205
  (shadow) and 0x77/0x9c/0x201 (front). `player_slotColor(slot, 0x80)` colours the
  front name only when there are two or more players. Lives are **not** shown.

**Observed:** with the end flag set the draw task also draws the confirm/cancel line
(key `0x551f08`), on a net game only on the lowest active machine
(`0x307300-0x3073d0`). **Unknown:** glyph rendering itself (stubbed).

## 6. Rewards

- **Gold is cleared on entry** (§2), so every arena run starts at 0 and the
  pre-arena balance lives only in the snapshot.
- **Experience** comes from the ordinary kill award. `Creature_processDamage`
  `0x110d30` has no mode-word load (Observed, whole body); the award rules are
  `research-spells-r3` `docs/spec/combat-r6.md:172-222`. §9 records the
  `player_giveExp` `0x1d3150` calls made by the arena kills.
- **Loot** is the ordinary death drop (`Creature_dropLoot` → `loot_generateDrops`,
  once per death, §9). Gold reaches the record only through a Gold object's touch and
  the HUD floater credit (`research-loot-drop` `docs/loot-drop.md:241-294`). No Gold
  object is collected inside the arena here (Unknown here).
- **Spending:** gold buys extra lives at a budget of 100 that doubles per purchase
  (`docs/arena-modes.md:172-177`).
- **Restart:** confirm restores the saved records, so gold, experience and items won
  in the arena are discarded (`docs/arena-modes.md:230-232`; §2 snapshot). **Unknown:**
  whether cancel's return to the front end saves the live record anywhere; no arena
  code path writes a save.

The client must not grant a fixed reward at a wave, a level or the defeat page.

## 7. Return to the menu, restart and the next level

- **Cancel** (full fade, end flag): mode B 0, `g_sessionExitCode` `0x41b508 = 1`
  (`docs/arena-modes.md:233-235`). The main loop then leaves the session at
  `0x3234d4`: mode B cleared again, `arena_shutdown` `0x304fb0`, `game_clearLevel(1)`
  and the front end restarts (Observed; `docs/mainloop.md:217-243,473-475,608`).
- **Confirm:** restore records, `arena_shutdown`, request recipe 0's level, keep mode B
  (`docs/arena-modes.md:230-232`). The next `arena_init` sees the end flag still set
  and takes the fresh branch (§2: "restart, end=1" configurations).
- **Next level** after three waves: the request of §9, then `arena_init`'s continuing
  branch and `arena_begin`. **Unknown:** the original load of a second arena map; the
  probe has only the first map's terrain.

## 8. PvP damage and knock-back

- `damage_apply` mode-A steps (armour for every victim, ×0.5 for a player victim, no
  stun) and the mode-B absence of both: `docs/arena-modes.md:337-364`.
- Knock reaction in `Player_processDamage`: mode A lowers the knock level by one and
  halves the speed (`research-spells-r3` `docs/spec/combat-r6.md:136-168`).
- **New, Executed** (`case_knockback`, 24 configurations, 72 checks per seed):
  `Creature_applyKnockback` `0x115eb8` zeroes `+0x2e8` and returns without moving
  when the object has flag `0x40` (a player) and either the network byte `0x402791`
  or mode B is set (`0x115ef0-0x115f24`). Otherwise it moves the object through
  `Creature_moveBy` `0x113c48` and lowers the speed by 2. Mode A has no effect on
  this gate. Creatures (`0x20` only) are pushed in every mode. `Player_run` calls it
  at `0x1a5254` (Observed). Followed: the body and the two trig functions; recorded
  stub: `Creature_moveBy` (returns 1, which skips the dust tail at `0x116034`).
  **Inferred:** in co-op and in offline versus (A and B) a player's knock reaction
  still plays but the positional push is never applied.

## 9. Controller-only run of a whole arena level

**Executed** (`tools/difftest_arena_round12.py`, seeds 20973 and 7). Continues the
round-10/11 fixture (`difftest_arena_engagement.prepare`): disc terrain and clips,
original Goblin and creature bodies, the original class-0 unarmed record.

Changes from round 11 (`arena-match-probe.md` round 11), each disclosed in the tool's
docstring:
- **No scheduled `Player_meleeHit`.** Every hit comes from `Player_run` on a
  controller stick and attack button the driver chooses from positions, as a player
  would: walk to 58 units of the nearest living creature, face it, press attack every
  36 frames; after three swings on a target reach no `Player_meleeHit`, walk to 26
  units instead. The driver never calls a damage or melee body.
- **Round 11's swing stall, explained.** `Player_animStep` `0x1b9520` was not
  followed, so the first player reaction (state `+0x58c` = 3, case `0x1ab1f0`)
  waited forever on `+0x11a` bit 8. Round 12 follows it; the player's tracks come
  from the followed `anim_start` and the disc Ragnar clips.
- **Animation decoder.** `animtrack_decode` `0x16e468` and `animcache_alloc`
  `0x16e388` are followed. Round 10's follow set took only `anim_*`/`anm_*` names;
  the arena spawn-effect clip (FX lump, read at run time) is the first compressed
  (`+0x1c & 0x800`) track this fixture synchronises.
- **Deferred deletion.** `obj_delete` `0x14f200` and its handle calls are followed;
  at the start of each frame the original `world_flushDeleteList` `0x14f3a8` runs
  with every callee followed, as `runObjects` `0x14b910` does inline. Without it a
  deletion-requested corpse (flags `0x612b`) stays on the grid, the preparation
  walk saves it, and the next `arena_startWave` re-places it instead of building the
  recipe wave (seen in a development pass of this driver before the flush was added;
  that log is not retained). With HP ≤ 0 such a corpse is not counted, so the wave
  "cleared" on its first scan. **Inferred:** a client must
  remove deleted creatures before the preparation walk.
- **Saved-creature table.** `0x50388c` gets a `0x4b0`-byte block, the allocation
  `arena_init` makes (§2); this fixture never ran `arena_init`.
- **HP.** 10,000, as in round 11. A level-up (`player_giveExp`) recomputes maximum
  HP from the real class-0 statistics (33.5 at level 2) and refills HP to it; the
  driver then writes 10,000 to both again and reports the frame. Without that, the
  unarmed level-2 character died to wave 1 (development pass, state 4 at frame ~2850;
  not retained).
- A Scorpion sting makes `damage_apply` attach a `SpellDiseaseEffect`
  (`pool_new(0x1b0)` at `0x1e9de8`, `docs/spec/skills-01-34.md:2433-2436`); the probe
  allocates that one block and follows its constructor `0x2d5594`. The effect's own
  tick is an auto-stub, so disease damage is not applied.
- The model joint service `0x1799c8` returns 1 so `SpellArena_run` on new creatures
  can divide (`docs/arena-modes.md:330-331`). The end prompt, `strcpy` (it receives
  the next level's name pointer) and `net_closeLocalMenus` are recorded stubs; any
  other unfollowed callee is an auto-stub returning 0.

**Results** (retained `work/arena-round12-r12-20973.log` and `-7.log`):

| | seed 20973 | seed 7 |
|---|---|---|
| Waves built (all recipe 0, matching `ref_arena_modes`) | 0, 1, 2: classes 3 3 / 3 3 1 / 3 3 1 0 | 0, 1: 3 3 / 3 3 1 |
| Controller kills per wave | 2/2, 3/3, 3/4 | 2/2, 1/3 |
| Death frames (class) | 1130, 1881 (3); 3565 (1), 4601, 5216 (3); 7123 (1), 8972, 10390 (3) | 2748, 2957 (3); 5065 (1) |
| Intermission start → next wave | 1920 → 2400, 5248 → 5728 | 3072 → 3552 |
| `player_giveExp(0, n)` per kill | 270, 270, 339 ×3, 414 ×3 | 270, 270, 339 |
| Left alive at frame 16,000 | the Scorpion (class 0), HP 88 | two Goblins, HP 5.6 and 59.9 |

Every death ran `Creature_processDamage`, `Creature_onDeath`, `arena_addKill`,
`Creature_dropLoot` and `loot_generateDrops` exactly once; the arena kill count equals
the deaths; every intermission began on a frame that is a multiple of 128 and the
next wave was built 480 visits later; the player never died; mode B stayed set and
the end flag clear. Each Mummy corpse requested `obj_delete` about one frame after
its death and was destroyed by the flush; the requesting call site is not identified
here (**Unknown**). This qualifies `docs/creatures.md:423` (C5, "arena corpses stay
for the rest of the level") for the Mummy; the Goblin corpses did stay. Seed 20973 also attached one `SpellDiseaseEffect`
from a Scorpion sting. 12 checks per seed, PASS.

**Partial.** The driver's simple controller (walk to the nearest creature, swing)
did not finish wave 2 on seed 20973 (the Scorpion keeps about 200 units away in its
chase state) or wave 1 on seed 7, so this run does **not** reach the third-wave
next-level request. That request, and the waves-left-0 branch that issues it, are
executed separately (`docs/arena-modes.md:76-88`, `difftest_arena_modes.py`
`test_task`, §10 here). A better controller, not a game rule, is what is missing.

## 10. Signed-wave overflow

**Executed** (`case_overflow`, 120 checks per seed). `arena_startWave` with the
halfword at `0x7ffd`…`0x8004` before the call, one and four active slots: the halfword
becomes the next value modulo 2^16; the monster level is `float(s16) × 0x3f2bc579 + 5`
(negative after the wrap); the record index is the signed remainder, so −32768 and
−32767 read record −2 and remainder −2/−1 (before the table), which spawn nothing and
take no ring step; −32766 (remainder 0) takes one ring step with a negative count and
spawns nothing; −32765/−32764 read record −1, again with no spawns. Spawn requests,
ring-step counts, seed, level and intro match the model on both seeds. The level
request at waves `0x7ffe`…`0x8003`, `0xfffe`, `0xffff` (waves-left 0, intermission
expiring offline) copies exactly the pointer the model predicts; for these samples it
lies inside the mode-B table. **Inferred:** a client may implement the raw 16-bit
wrap from these vectors or stop at 32767 waves; acceptance does not depend on it.

## 11. Still unknown

- The original load of a second arena map and anything on that map.
- Gold object pickup inside the arena, and whether arena gains reach a save.
- Glyph rendering of the result page; the confirm line's input image.
- Destructor flags for preload/saved objects (`arena-live-scheduler.md:30-34`).
- Anything between two machines, and a console run.

## Reproduction

On the mini, from the worktree, with the executable in ignored `local/`:

```sh
export PYTHONDONTWRITEBYTECODE=1
DISC=~/malik-champions/open-champions/private-validation/rta-disc
python3 -c 'import dis,unittest,runpy,sys; sys.argv=["tools/difftest_arena_acceptance.py","local/SLUS_209.73","--seed","20973"]; runpy.run_path(sys.argv[0], run_name="__main__")'
python3 -c 'import dis,unittest,runpy,sys; sys.argv=["tools/difftest_arena_acceptance.py","local/SLUS_209.73","--seed","7"]; runpy.run_path(sys.argv[0], run_name="__main__")'
python3 -c "import dis,unittest,runpy,sys; sys.argv=['tools/difftest_arena_round12.py','local/SLUS_209.73','$DISC','--seed','20973']; runpy.run_path(sys.argv[0], run_name='__main__')"
python3 -c "import dis,unittest,runpy,sys; sys.argv=['tools/difftest_arena_round12.py','local/SLUS_209.73','$DISC','--seed','7']; runpy.run_path(sys.argv[0], run_name='__main__')"
python3 -c 'import dis,unittest,sys; sys.path.insert(0,"tools"); r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName("test_ref_arena_acceptance")); sys.exit(0 if r.wasSuccessful() else 1)'
```

Retained PASS logs (ignored `work/`, produced after the final edit of every tool):
`arena-round12-acceptance-{20973,7}.log` (542 checks each, PASS),
`arena-round12-r12-{20973,7}.log` (12 checks each, PASS),
`arena-round12-unittest.log` (13 tests, OK) and
`arena-round12-modes-regression.log` (unchanged `difftest_arena_modes.py`, 302 passed).
On the mini the disc argument is the extracted disc directory; an image path works too.
