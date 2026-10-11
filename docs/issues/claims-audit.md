# Audit of "only writer / only reader" claims after the `gxref` fix

Scope: every statement in `FINDINGS.md`, `docs/*.md`, `docs/issues/*.md` and
`docs/spec/*.md` whose truth depends on a list of the readers or writers of a global being
complete, re-checked after `tools/gxref.py` was corrected. The two issue documents written
after the fix (`arena-entry.md`, `rescan.md`) were only searched, not audited.

Everything here was read from the executable (SLUS_209.73, v2.00) and its decompile;
**nothing was run.** (Still so for this audit. What the project has run on a live game
since is in `FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`.)
Statements are **Observed** unless marked otherwise. No symbol file was
added: nothing new needed a name. `FINDINGS.md`, the other documents, `names.tsv` and
`patches/` were not edited; the corrections are listed for whoever applies them.

## 1. Result in short

- **99 claims** were collected and re-checked. **76 stand as written. 21 stand with a
  changed list** (the reader or writer list in the document is incomplete, the conclusion
  drawn from it is not affected). **2 are wrong**: FINDINGS G5 as worded (conclusion
  intact), and the movement specification's list of writers of the record speed
  multiplier (a rebuild following it would be wrong in the arena game mode).
- **No ledger row is overturned and no patch loses its safety argument.** The rows the
  desync and lag work leans on (D6, D7, D13, D20, D24, D26, G5–G13, G19, L3, L9, L10,
  B4, B5, B10, K1, K2, MV2, E5, E10, the "Ruled out" list) and every "nothing else reads this" in
  the patch file hold with the corrected scan.
- **What the old scan actually got wrong was the kind of access, far more than the set of
  functions.** It usually listed a function with `&` (address taken) where the corrected
  scan shows a read or a write. Of the 99 claims, the set of *functions* touching the
  global is the same in both scans for all but a handful. Authors who read the `&`
  functions were not misled; lists copied from the `W` column alone are the ones that
  changed (G9, the movement specification).
- **The corrected scan is still not complete, and a hit without `?` is not always
  right** (section 6.1): it follows the listing, not the control flow. Two real examples
  are given. For every claim below the function list was therefore also compared with the
  Ghidra decompile, which resolves addresses by its own data flow.
- **Step 4 found no new desync candidate.** Every presentation-writer / simulation-reader
  pair that falls out of the delta file is either already in a document, offline only, or
  dead (section 5).

## 2. Method

1. **Collecting.** A search of the 38 documents that existed when the audit began, for
   about fifty phrasings ("only writer", "no reader", "never written", "nothing else",
   "private to", "initialised data", "N functions read", "cannot differ", "gxref", …),
   gave more than 400 lines; each was read and kept when it rests on the completeness of
   a list for a global or for a structure in static memory. Claims about fields of heap
   objects rest on `fieldxref` / `flagxref` instead; they are listed in section 6.4, not
   counted here, except where a top ledger row needed a spot check.
2. **Old evidence.** The pre-fix scan was re-implemented from its cached bytecode and
   checked to give the identical 1,546 hits on 18 globals, so "old evidence" below is
   what the old tool printed, not a guess.
3. **New evidence.** `python3 -I -B tools/gxref.py SLUS_209.73 <addr>`, and for arrays and
   static structures the whole byte range, with functions attributed by
   `ghidra_funcs.tsv` (the tool's own attribution uses the heuristic boundaries of D32).
4. **`?` hits.** Each one a verdict depends on was classified by walking back to the
   instruction that gave the base register its address and listing what wrote the
   register since: *indexed* (only an index was added: a real access into the array),
   *stale* (the register was replaced, with no branch target between the replacement and
   the access) or *read the code*. **On a per-slot array every real access is a `?`
   hit**, so "all `?` hits were stale" is true only for scalars.
5. **Cross-check.** For each address the functions whose decompile names it
   (`DAT_<addr>` or the symbol) were compared with the scan. For structure fields of the
   static player record table the slot-0 address was used the same way.
6. **Reading.** The decompile of every newly found writer or reader that a verdict depends
   on was read; the addresses are in the tables.

Columns: *old* = pre-fix scan; *new* = corrected scan plus what the code does.
W = store, R = load, & = address taken.

## 3. The claims

### 3.1 FINDINGS.md and the patch file

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 1 | D4: quest variables are not networked; only the script variable functions touch the table | `g_questVars` 0x86da80–0x86fa7f | & in `vars_clearAll`, `vars_get`, `vars_set`, `vars_getByIndex`; nothing else | the same four, now R (they walk the packed table through a pointer). Three more hits in the range are not accesses: stale registers in `hud_spellSelect` and 0x1de8c4, and 0x22231c, reported as a certain store to 0x86dbf8 but really a store to the text buffer 0x879ea8 (6.1) | stands | none |
| 2 | D6: `g_cullByCamera` is set by `gameSetObjectVis` and read by the activity test and `isNearView` | 0x4039c1 | W 0x1e4d48; R 0x14db08, 0x1e77c0 | identical | stands | none |
| 3 | D7: `cut_runFrame` is the last writer of the camera each tick; the engine camera is written through `camera_setView` | position 0x44f038, focus 0x44f048, matrix 0x44f110 | no W at all: position 30 functions (28 of them & only), focus 8 (all &), matrix 36 (all &) | position: W in `camera_setView` 0x18a2b0 (0x18a30c–0x18a314) and in `Camera_loadState` 0x203a20 (0x203a68–0x203a88; called only from `save_load` 0x221e74). Matrix: W in `camera_setView`; `Camera_loadState` also fills it, through a pointer (read in the decompile). Focus: W only in `camera_updateFocus` 0x18a520. Ten possible writes of the position in drawing code (0x1765e8, 0x17664c, 0x176654, 0x19b140, 0x1a4870, 0x1fc280, 0x204134, 0x24dd58, 0x24de04, 0x24de50) are stack stores | stands, list changed | `Camera_loadState` puts each machine's own saved camera back on a party-wipe reload. No cutscene is running then, and `cut_runFrame` overwrites the camera on every cutscene tick, so D7 is not affected. The open point in arena-desync.md ("address-taken references in drawing code were not read") is closed for position and focus |
| 4 | D13: the exclude mask is written at 0x139f4c, 0x13b1f0, 0x131e38 | 0x4039b8 | W in `net_frameLoop`, `net_predictLocalPlayer`, `Vehicle_collideObjects` (0x20e410, 0x20e690); & in `Creature_pickTarget` | adds W in `Creature_pickTarget` 0x10ded0: saves the mask, stores 8 (0x10e060) around one box query, restores it (0x10e044). `Vehicle_collideObjects` does the same with 1 | stands, list changed | none: both restore the saved value in the same call, and the box query has its own fixed test of 0x20000 (0x14a928), so it never returns the copy whatever the mask is. While the mask is 8 or 1 the query no longer skips the real local player during prediction; only the copy sees that |
| 5 | D20: the active player is written by trigger volumes, interact, NPC talk, `setBestActivePlayer` and `dialog_free` | `g_scriptActivePlayer` 0x4d8ae4 | W at 0x1ed15c, 0x1b2b70, 0x116d28, 0x1470fc–0x147120, 0x22fa34; & in `script_playGotItemSound`, `dialog_runTask` | adds two writers. `script_playGotItemSound` 0x1464e8 clamps the value to 0…1 (0x146508, 0x146518). `dialog_runTask` 0x22ff48 flips it between 0 and 1 (0x2301b8) only when the game is not a net game | stands, list changed | the script built-in runs in lockstep, so nothing diverges; but after a `playGotItemSound` the active player of a three- or four-player game is slot 0 or 1, which the D20 cool-down then applies to. No writer stores −1 (script.md P5 still holds) |
| 6 | D20: the gate is skipped when the script runs as a post-cutscene action | `g_scriptInPostAction` 0x4f8698 | & in `script_runPostAction`; R in the two `newWorld` handlers | W in `script_runPostAction` 0x1edb00, 0x1edb04 only | stands | none |
| 7 | D21 / B8: the blood option can only be 0 or 1 from the menu | 0x44fdc0 | W in `config_setDefaults` 0x1e62f8, 0x1e65e8 (config restore), `game_addCoreTasks` 0x1e6ea8, options screen raw copy 0x222d5c | identical. The menu's own store goes through a pointer held in the option table and is seen by neither scan (6.1, limit 6) | stands | none |
| 8 | D24: every local writer of the camera-mode word is locked out during a cutscene | camera object 0x86ad68 +0x34 (pointer 0x4f8450) | pointer: W only `game_initCamera` 0x1e6bb0 | pointer: same. The object is static but never addressed absolutely (no hit at 0x86ad9c). Stores at displacement 0x34 in camera code: `Camera_setMode` 0x207304 and `Camera_updateFree` 0x20440c | stands, list changed | `Camera_updateFree` is the fly camera of modes 3–5 and sets mode 1 on a button of pad 0; it cannot run while the mode is 0. arena-desync.md lists only `Camera_setMode` and its callers |
| 9 | D26: the input lockout is set to 60 by closing the inventory or shop; zeroed at the start of every net tick | `g_menuInputLockout` 0x41b4fc | W in 19 functions, R in 17 | adds W in the two modal loops `mainloop_runModalCallback` 0x323780 and `…WithDisplayReset` 0x3238b0 (count down outside any tick while two pads are idle) and R in `tasks_run` 0x322854 | stands, list changed | none in a net game: `tasks_run` stores 0 on entry (0x322710) before any tick |
| 10 | G1: the shared seed is saved and restored around the clone | `g_randSeed` 0x404464 | & in `net_frameLoop` | W in `net_frameLoop` | stands | none |
| 11 | G4: simulation and prediction each have their own codec state | 0x5bf798, 0x5bf7e8, 0x5bf6f8, 0x5bf748 | & only | W for all four in `net_gameInit`; prediction pair also W in `net_frameLoop` (reset at a rebase); simulation pair R in `net_frameLoop` | stands | none |
| 12 | G5: `pad_apply`'s two globals "are never written anywhere in the program"; 0x41bfc0 is decremented by `pad_apply` itself and nothing else writes it | 0x41bfc0, 0x41c138 | 0x41bfc0: R in `pad_apply`. 0x41c138: R in `pad_apply`, & in `pad_updateRumble` | 0x41bfc0: W only at 0x174464 in `pad_apply`. **0x41c138: W at 0x174790 in `pad_updateRumble`**, which runs at the end of every tick, subtracts one and stores the result clamped at 0 | **wrong as worded** | conclusion intact: both words are 0 in the file and no code stores a non-zero value, so they are 0 on every machine. The row, the note on the `pad_apply` symbol and dynamic-tests row b5 should say "never set to a non-zero value" (mainloop.md §11 and engine.md already say so). "Prediction leaving stale pad state" stays ruled out |
| 13 | G6: box queries never return the copy; run and draw loops skip what the mask names | 0x4039b8 | as row 4 | as row 4 | stands | none |
| 14 | G8: record +0x4a5c is written without a guard and nothing else reads it | slot 0: 0x4dd54c | no hit (accesses are indexed) | R and W only in `Player_run` (0x1a6200–0x1a629c, 0x1a8054–0x1a8084); W in `player_importCharacter` 0x1bd904 and a zero store in `player_initNewCharacter` 0x1b2218 made through a pointer to +0x4a50, which neither `gxref` nor `fieldxref` reports | stands | none |
| 15 | G9: the mode flags are "written only by game setup 0x1e15f8, 0x1e1888" | `g_pvpModeA` 0x4f711c, `g_pvpModeB` 0x4f7120 | A: W in `frontend_run`, boot code 0x323dcc. B: also `arena_runTask`, `mainloop_runSession`. & in `net_launchUpdate` | adds W in `net_launchUpdate` (0x1374a8–0x1374d8, from the host's mode byte). Full list: `frontend_run` (0x1e1664, 0x1e18dc, 0x1e1938; 0x1e1670, 0x1e18e4, 0x1e1984), `net_launchUpdate`, boot-argument code 0x323f34/0x323f38, and for B `arena_runTask` 0x307160 (0 when the first active slot's lockstep pad presses the cancel button on the end-of-match prompt; meaning Inferred) and session exit 0x3234f4 | stands, list changed | all writers are shared (launch data or lockstep) or outside play; the flags are not per machine |
| 16 | G11: the alive list is rebuilt only by `game_rebuildAlivePlayers` | count 0x4f8420, slots 0x4f8440–0x4f844f | W in 0x1e72f8 | W at 0x1e7358, 0x1e73bc; slots through a pointer formed at 0x1e7374. One possible W (0x27eccc) is a stack store | stands | none |
| 17 | G13: "about 50 functions read the list" | same | 51 functions reference count or slots | 51, the same functions (one is the builder). Only the kind changed, for eleven of them (& → R) | stands | none |
| 18 | G19: the readers inside the window that change shared state | same | — | no function added | stands | none |
| 19 | L3, L9 and patches LAG-3, LAG-4: the send-cycle table is read by `net_main` | 0x4027e8–0x4027f7 | R at 0x1337cc | the same indexed read; the other four hits are an unrelated 32-byte copy later in `net_main` | stands | the two data patches stay per machine |
| 20 | L10 and patches LAG-1, LAG-2: the pacing counters are private to `net_main` and the receiver | 0x4027a8, 0x4027b0, 0x4027b4, 0x4027d0, 0x4027dc, 0x4027e0, 0x4027e4 | 0x4027e0 and 0x4027e4: & only, in `net_main`. Others: R/W in `net_main`, W in `net_gameInit`, `net_startSync` | every R and W is in `net_main`, `net_gameInit` or `net_startSync`. Six possible reads in `net_sendInputPacket` (0x1392a4–0x139314) use a register recomputed from the peer index: stale. Decompile agrees: one user function for 0x4027b0, 0x4027b4, 0x4027dc, 0x4027e0, 0x4027e4 | stands | none |
| 21 | L10: the peer fields the counters read are written only by the receiver | peer +0x44c4, +0x44c8; table 0x5bf838–0x5d0bb7 | sweep listed 65 functions, many of them stale-register artefacts | sweep lists 32: all in 0x131b00–0x13e633 except a colour constant (0x1d9aa0, not an address) and a loop counter (0x1119d8). Stores at those displacements: 0x13b7ac and 0x13b790 only; in netcode the only pointers formed to them are at 0x13338c and 0x133390 in `net_main` step 3 (the few other instructions that add 0x44c4 or 0x44c8 build unrelated addresses) | stands | none |
| 22 | B4: `g_numPlayers` is written by set-up code and `save_load` | 0x4d8ae0 | W in `frontend_run`, `frontend_start`, 0x229d94, the offline set-up, the developer LAN lobby; & in `save_load` | adds W in `save_load` 0x221eb8. Two possible W in `mainloop_loadRequestedWorld` and one in `Camera_computeTarget` are stale | stands | none |
| 23 | B5: 51 functions touch the cosmetic seed (plus two the decompile lacks) | `g_cosmeticSeed` 0x404460 | 52 functions, W marked in 5 | 52 functions, all W: the 51 of the decompile plus orphan code at 0x217cc8 that no function contains or calls | stands | none; the reachability argument itself does not rest on `gxref` |
| 24 | B10: nine stores to the latch; three consumers | `g_cardXferLatch` 0x4f8f28 | — | W at exactly the nine addresses of the row. R at 0x320fb0, 0x27db08, 0x322dc4 and at 0x206778 in `Camera_computeTarget` (also in the old scan; not in the row) | stands, list changed | the fourth reader is camera code, per machine anyway |
| 25 | patch "net launch clears a stuck memory-card latch": the byte it used to clear "is never set by anything" | 0x4f8f2a | W 0x1375dc; R 0x21f14c | identical; one possible hit in `Savepoint_run` is a loop counter. Decompile: two users | stands | patch argument holds |
| 26 | patch "ignore the debug file": the patched store is the only one that sets the switch | `g_debugCheats` 0x4f8ee0 | & in `save_init` | W at 0x2173d4 (stores 0) and 0x217448 (the patched store), both in `save_init` | stands | patch argument holds |
| 27 | K1 and patch "use button works with the spell selector open": only `hud_spellSelect` writes the per-slot word | 0x41b818–0x41b827 | & in `hud_spellSelect`; R, W marked | W at 0x1dd4ec, 0x1dd504, 0x1dd5e4; R in `Player_draw` 0x1a47b0 and `Player_run` 0x1a5c08, 0x1a6e04 — all indexed. Between 0x41b7a0 and 0x41b827 the only other address formed is the previous-level name buffer at 0x41b7c2 (and one stale hit) | stands | patch argument holds |
| 28 | K2 and patch "potions always leave the bag directly": `g_localMenuOpen` is set at 0x1c15c8 | 0x41b69d | W in `menu_openInventory`, `shop_openOrStock`, `shop_close`; & in `inventory_close` | adds W in `inventory_close` 0x1c5318. In `Player_usePotion` the only reads are the two patched ones (0x1b9fcc, 0x1ba3ac) | stands, list changed | patch argument holds |
| 29 | MV2: the dialog-open word is written at four places | 0x8e2d60 | W 0x22f72c, 0x22f904, 0x22fa30, 0x230d50 | identical; the two address-taking sites (0x22f464, 0x230e8c) only read through the pointer. Decompile: nine users, the same nine | stands | none |
| 30 | D17: `gamePaused` reads the pause flag, the jump-gate flag and the cutscene flag | `g_paused` 0x41b4f4, 0x500ae8, `g_cutsceneActive` 0x44fcd0 | 23, 2 and 3 writer functions (two of the 23 as &) | the same functions | stands | none (ui.md P3's reservation about a paused net game is unchanged) |
| 31 | "Ruled out": Summon Skeleton's use of the unsynchronised seed is particles only | `g_cosmeticSeed`, 0x404468 | & in `SkillSummonSkeleton_cast` | R and W of the cosmetic seed there; 0x404468 is not touched by it | stands | none |
| 32 | D1 / netcode.md: the extra hash term's only writer stores 0 | `g_syncAcc` 0x4027c0 | W 0x139870; R 0x13af58 | identical | stands | none |
| 33 | D15 (spot check, structure field): only four ability effects set counters 2, 7, 12, 13 | creature +0x36c + 4n | `fieldxref` | `fieldxref` cannot see stores made through a pointer into the array. Pointers into it are formed in `Player_ctor` (0x1a228c: zero-fills all 16), in every clone function (copy of all 16; only `Player_clone` runs) and in `Player_draw` 0x1a4a88 (reads counter 0) | stands | none; "sets" should be read as "sets to a non-zero value" |
| 34 | E5: `cut_start` and the end of `cut_runFrame` restart the warm-up counter; no reader of the counter inside a net tick changes shared state; `cut_evalCamera` keeps one latch | `g_warmupFrames` 0x506048; latch 0x44fd00 | 0x506048: W in `mainloop_startWarmup` and the main loop, R in 8 functions. 0x44fd00: W in `cut_start`, & in `cut_evalCamera` | 0x506048: the same two writers (the restart routine 0x322934 is called from 0x19b514 and 0x199f3c, as the row says, and from six menu and card functions) and the same 8 readers; decompile agrees. 0x44fd00: W at 0x1973e8, 0x197b0c and R only in `cut_evalCamera`, reset at 0x19b570 | stands | one reader inside the tick, `hud_tickMessage`, feeds the HUD message timer that `Vehicle_run` asks about (row 72); what that gates is help text only |
| 35 | E10: the post-action name is not cleared by level teardown ("writers of 0x86fa80") | `g_scriptPostAction` 0x86fa80 | W in `script_resetState`; & in `script_setPostAction`, `script_runPostAction` | `script_setPostAction` 0x1eda9c copies the name in (called from the built-in at 0x143f04); `script_runPostAction` reads it and clears it at 0x1edae8; `script_resetState` clears it at 0x1eda90 and is called only from `game_resetState` (0x1e7028), i.e. at session start | stands | none |
| 36 | E11 (structure flag, spot check): bit 31 of the creature flag word is set from the local alive list and nothing else reads it | creature +0xa8, mask 0x80000000 | `flagxref 80000000 a8` prints nothing at all: the word is loaded as 8 bytes, which it does not look at | searched for the forms it cannot see: a sign test of the low word after a load at +0xa8 (one hit, 0x1c6214 in `shop_task`, another structure) and the mask constant near such a load (only 0x113bc8 in `Creature_run`). The sign tests at 0x112f80, 0x116324 and in `Critter_run` are of the 8-byte value, i.e. bit 63. Accessors that take the bit number as an argument (the script flag helper 0x1445fc) cannot be excluded this way | stands | none |

Rows added to the ledger while this audit ran (D33–D38, E1–E15, F1–F10, SA, SB, SC,
MV1–MV6): the ones that rest on a reader or writer list of a global are E5, E10 and MV2
(rows 34, 35, 29) and, for a structure flag, E11 (row 36). The others cite code paths,
structure fields or disc scans. For E15, which leaves open whether the pending-selection
flag 0x4fbbd8 can be set on one machine at a net launch: its only stores are in the
character-selection screen (0x2246f8, 0x2248c8, 0x22a408) and its only reader is
`playerSel_applyPending` 0x2247f8, in both scans and in the decompile.

### 3.2 docs/issues/lag.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 37 | §2.1: `eq`, `win`, `minReady`, `phase` are touched by `net_main` and nothing else | 0x4027dc, 0x4027e4, 0x4027e0, 0x4027b4 | see row 20 | R and W in `net_main` only | stands | their starting values do carry over between games |
| 38 | §7: `cycle`, `lastSent`, `stall` are referenced only by `net_main`, `net_gameInit`, `net_startSync` | 0x4027b0, 0x4027a8, 0x4027d0 | same | same | stands | none |
| 39 | §7: `g_netLongStallCalls` is also read by the HUD draw and the wait after a load | 0x40279c | & in the HUD function; R 0x323054 | R at 0x1dbf24–0x1dc05c and 0x323054; W in `net_main` 0x134438 and `net_gameInit` | stands | none |
| 40 | §7: the sweep of the peer table finds only netcode functions (others were artefacts) | 0x5bf838–0x5d0bb7 | 65 functions | 32, see row 21 | stands | the artefact caveat can go |
| 41 | §7: `lif` is read by prediction, `nf` is the lockstep frame | 0x4027a4, 0x4027ac | 4 and 7 functions | the same functions; W of `lif` in `net_main` 0x133670 and `net_startSync` 0x13dd14, W of `nf` in `net_frameLoop` 0x13af68 are newly marked | stands | none |

### 3.3 docs/issues/prediction-copy.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 42 | §3.1: record +0x4a5c has no reader | as row 14 | | | stands | none |
| 43 | §4.3: no creature targeting function references the list (nothing in 0x100000–0x131a40) | 0x4f8420–0x4f844f | — | lowest function with a reference is 0x142220 | stands | none |
| 44 | §2: `Player_dtor` is told when the copy is being torn down | `g_inGhostOp` 0x402795 | W in `net_predictLocalPlayer`, `net_frameLoop`; R 0x1a1be4 | identical | stands | none |
| 45 | §2: the force byte makes the copy re-clone | `g_forceGhostRebase` 0x402797 | R and & in `net_frameLoop`; 13 writer functions | adds W at 0x13b26c in `net_frameLoop`: one is subtracted at each rebase while the value is positive | stands, list changed | the byte is a count of forced rebases, see row 79 |

### 3.4 docs/issues/sync-breakers.md

This document already distrusted the old tool and re-checked its lists with a scan of its
own. All of them hold.

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 46 | §1: the writers of the player count are set-up code and `save_load` | 0x4d8ae0 | row 22 | row 22 | stands | none |
| 47 | Background: `g_lobbyLaunch` is written by `frontend_startNetGame` | 0x4f7134 | W 0x1e2258, 0x1e2270; also 0x1e2050 and 0x1e6bd8 | identical: the two extra stores (`frontend_start`, `game_initCamera`) write 0 | stands, list changed | none |
| 48 | §1: the checksum-failure flag is cleared only at session start | `g_checksumFailed` 0x4f7144 | W 0x1d91c8, 0x1e6f48; R 0x1dbcf8 | identical | stands | none |
| 49 | §6a: `g_gameCompleteFlag` is written by a lockstep script and `game_resetState` | 0x4f85c5 | W 0x146cb8, 0x1e6ff4 | identical | stands | none |
| 50 | §2: 51 functions touch the cosmetic seed; the unlimited scan adds two | 0x404460 | row 23 | row 23 | stands | none |
| 51 | §2: world pieces are not drawn between the level change and stock generation (cleared 0x322e2c, set 0x323140) | `g_worldPiecesDrawn` 0x44f054 | W there and in 0x1e3c84, 0x1e3cc4 | identical. The two small setters are called only from the lobby screens (0x33f924, 0x340274), not during a load | stands, list changed | none |
| 52 | §4c: "the store list above is complete" (nine stores to the latch) | 0x4f8f28 | row 24 | row 24 | stands | none |
| 53 | P1: 0x4f8f2a has one writer and one reader | 0x4f8f2a | row 25 | row 25 | stands | none |
| 54 | §7: the readers of each option variable, "from a search of every load of its address" (16 variables and the per-slot control tables) | 0x44fd80, 0x4f8944, 0x4f8940, 0x4f8948, 0x4f845c, 0x4f8460, 0x41bfb0, 0x44fdc0, 0x44fcf4, 0x44fcf8, 0x50391c, 0x4f8458, 0x505b00, 0x505afc, 0x505af4, 0x505af0 | — | every reader outside menu and config code is in the class the table names; the control tables 0x41b980–0x41ba3f are read by player input code, the HUD selector and one camera function, and written by the launch code and the config commit. Added by the corrected scan: R of both volumes in `pauseMenu_task` (a menu). The voice switch 0x505b00 is also written by 0x31f434, `mainloop_loadRequestedWorld` 0x3214f4 and `mainloop_runSession` 0x322cd0 (voice code) | stands | none |
| 55 | §7: `g_debugCheats` is set only by `save_init`; `g_debugInvulnerable` is read by `Player_run` and `Player_processDamage` | 0x4f8ee0, 0x44f20c | — | row 26; R at 0x1a5b64 and 0x1b31b0, W only 0x1e0b68 (the menu toggle goes through the option table) | stands | none |
| 56 | §7: the launch handshake's mode bytes | 0x402c30–0x402c32 | no hit | read in `net_launchUpdate` (0x137474–0x137484). They are the mode bytes of the first of the per-player launch records; `net_launchPrepare` 0x134c60 fills them for its own record through a computed record pointer, which only the decompile shows (6.1, limit 3) | stands | none |
| 57 | §7: the fourth generator has seven users | 0x404468 | 7 functions, no W marked | 7 functions, all W: 0x110d30, 0x1a5030, 0x24c994, 0x284b68, 0x2c7808, 0x2ee068, 0x308578 | stands | none |

### 3.5 docs/issues/kill-loot-xp.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 58 | K1 §3: 0x41b818 is initialised data, four zero words; `hud_spellSelect` is its only writer | row 27 | | | stands | none |
| 59 | "Is every piece the same": +0x4a74, +0x4a78 are stored by `hud_spellSelect`; "no reader found outside that function" | slot 0: 0x4dd564, 0x4dd568 | no hit | function 0x1de8c4 (HUD ability-bar code) reads and writes both (0x1dee1c–0x1def78); `player_initNewCharacter` and `player_importCharacter` store them. No call of or pointer to 0x1de8c4 was found (ui.md lists it as unreferenced) | stands, list changed | none: still no simulation reader |
| 60 | Gate table: the lockout is zeroed at each tick start | 0x41b4fc | row 9 | row 9 | stands | none |

### 3.6 docs/issues/arena-desync.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 61 | F4: the name table is written by the constructor and destructor; "nothing else writes the table" | keys 0x5f76f8, objects 0x5f7ef8, count 0x5f86f8 | & in the three name functions | stores: `objNames_add` 0x14be34, `objNames_remove` 0x14bf3c (both indexed). `world_init` 0x14c370 and `world_deleteAllObjects` 0x14c460 zero the count and every slot of both tables. Possible stores in `GameObject_ctor`, `obj_moveWithCollision`, `obj_moveOffGrid` are stale | stands, list changed | none: the clears are at level unload on every machine |
| 62 | The only writer of the kill plane is `game_loadLevel` | `g_killPlaneZ` 0x4f7188 | W 0x1e5de8; R 0x1a5b38 | identical (one stale hit in `Skelight_ctor`) | stands | none |
| 63 | "Readers of the list that run during this fight" (from `gxref 4f8420 4f8440`) | row 17 | | | stands | none |
| 64 | Writers of the camera-mode word: `Camera_setMode` and its ten callers | row 8 | | | stands, list changed | row 8 |
| 65 | The engine camera is written by `camera_setView` | row 3 | | | stands, list changed | row 3 |
| 66 | "Other things checked": the lockout is set by `cut_start` and every cutscene tick, zeroed at the start of every net tick | 0x41b4fc | W 0x19b5ac, 0x199998, 0x322710 | identical | stands | none |

### 3.7 docs/mainloop.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 67 | §4: no writer of the deferred variable pair was found | 0x8eda70, 0x8eda74 | & in `mainloop_runSession` | R at 0x322b24, 0x322b34 and one W, the clear at 0x322b38 | stands | the branch is dead as far as direct references go |
| 68 | §6: the display-rate mode words are written only by 0x19dd48 | 0x44fd44, 0x44fd40, 0x44fdb4 | W for two of them; & for 0x44fd44 | W at 0x19dd84, 0x19dd88, 0x19dd8c, nowhere else | stands | none |
| 69 | §6: the only store to byte 0x44fd7c writes 0 | 0x44fd7c | W 0x1c03f4 | identical | stands | none |
| 70 | §6: 0x44fd50 has "no writer anywhere" | 0x44fd50 | R 0x19e3fc | identical; decompile: one user | stands | none |
| 71 | §5, §9: `g_lastSimTimerDelta` is never read; 0x44fdb0, 0x44fdac, `g_terrainLateFrames` have no reader outside their writer | 0x44fd48, 0x44fdb0, 0x44fdac, 0x5060a8 | W only; & in the writer | R of the last three only inside `gfx_endFrame` / `mainloop_runSession`; 0x44fd48 has no reader | stands | none |
| 72 | P5: the readers of the HUD message timer are "the boss-meter draw and one camera function — both per machine" | `g_hudMessageFrames` 0x4f66e0 | R in `hud_drawBossMeter` 0x1d93b8 and in the one-line getter 0x1d933c | identical. The getter's only caller in game code, 0x207dc4, is inside `Vehicle_run` 0x207c3c (object run code), not a camera function | stands, list changed | the per-machine timer is read by simulation code. What it gates there is the one-time driver help text and its latch, vehicle +0x408, which nothing else reads (0x207dac–0x207dd4). Vehicles only; section 5 |
| 73 | §9 and script.md §2.1: the word stamped by `script_runByName` has no reader | 0x4f8694 | & only | R at 0x1ed6f4 and W at 0x1ed708, both in `script_runByName`: it compares the word with the display-frame counter before overwriting it | stands, list changed | none: the comparison only decides whether the stamp is renewed |
| 74 | §9: `g_fadeWaitFrames` is read only by the main loop | 0x50604c | R in `mainloop_runSession` | same; W also in `mainloop_startFadeWait` 0x322964 | stands | none |
| 75 | §9: `g_warmupFrames` is read inside the tick only at P5, P6 and (offline) three more places | 0x506048 | 8 reader functions | the same 8 | stands | none |
| 76 | §9: nothing reads the damage counters that the ambient-audio poll zeroes | 0x4f7158–0x4f7177, index 0x4f717a | & in three functions | & at 0x1e5e68, 0x1e8374, 0x32252c; the poll clears the block with a memory fill; the index is written only with 0 (0x1e5ecc). No load of any byte in the range | stands | same result as gameplay.md §8.1 |
| 77 | §10: `g_netLaunchLatch` has no other reference in the program | 0x5060a4 | & only | R 0x322d54, W 0x322d6c, both in `mainloop_runSession` | stands | none |

### 3.8 docs/skills.md, data-tables.md, runtime.md, doc-corrections.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 78 | runtime.md §5: the built-in table and the skill table are initialised data; no store | 0x403370; 0x41b170–0x41b307 | one & (0x147a98); R and & only | identical. Three possible stores in the skill-table range (0x152fd8, 0x2490f0, 0x29a384) are stack stores | stands | none |
| 79 | skills.md (c): the writers of the force byte; "the reader probably treats it as a frame count" | 0x402797 | the ten spell stores, plus `Player_processDamage` (0x1b2ef4, 0x1b352c, 0x1b3824), `Player_move` 0x1b5098, `player_respawn` 0x1bd1e8 | adds the store in `net_frameLoop` 0x13b26c (row 45). The table in skills.md lists the ten spell stores only | stands, list changed | the inference is confirmed: after the last store, 0x78 and 0x3c force a re-clone on each of the next 120 and 60 ticks on which a rebase is allowed. Useful for G12, which needs a re-clone on the tick a blow is pending |
| 80 | data-tables.md §5: other writers of the monster level are `arena_startWave` and two constructors that swap it | `g_levelMonsterLevel` 0x4f714c | W in `arena_startWave`, `Skelight_ctor`, `CastBadger_loadState`; & in three more | W also in `game_loadLevel` (the main one), `CastBadger_ctor` 0x244e4c and `Skelight_loadState` 0x2a90b0; both save, set and restore around one call, like the two already listed | stands, list changed | none |
| 81 | data-tables.md §7.1: the two floats copied from the level table have no other reader | 0x4f718c, 0x4f7190 | W only | identical | stands | none |
| 82 | doc-corrections.md §3: 0x404468 has seven users | row 57 | | | stands | none |
| 83 | doc-corrections.md §3: 0x44fdc0 is written by `config_setDefaults` and the options screen | row 7 | | four writers, not two (also 0x1e65e8 and 0x1e6ea8, both configuration code) | stands, list changed | none |
| 84 | doc-corrections.md §7: who installs which weapon table | 0x50cda0, 0x50cf40 | & in 14 and 36 constructors and clone functions | identical; four added possible hits (0x26a7b8…, 0x2a5c58, 0x125850, 0x29b0c0) are not accesses to the tables | stands | none |

### 3.9 docs/player.md, ui.md, script.md, engine.md, netcode.md, netlib.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 85 | player.md: about 50 functions read the alive list | row 17 | | | stands | none |
| 86 | player.md: the aura globals and HUD hint timers are advanced by the copy too; their only readers are `Player_draw`, `Player_run`'s light code and the HUD | 0x4d8a40–0x4d8ab3, 0x8659a0–, 0x41b828–0x41b8c7 | & only | readers as stated. Writers also `player_recallTick` 0x1b5fa0 (0x1b605c–0x1b607c and indexed stores), `Player_updateCast` 0x1a41f0, `player_resetAuraLights`; hint timers also `Player_usePotion`, `Player_weaponSwapInput` and the two axe skills (possible stores in two camera input functions were not classified) | stands, list changed | none: no simulation reader |
| 87 | player.md item 8: the exit countdown is set by message handlers; whether it can differ is Unknown | `g_exitCountdown` 0x4f694a | W in `hud_onMsg`; & in `hud_run` | W also at 0x1db8f0 in `hud_run`: one is subtracted on every tick with no per-machine condition | stands | answers the Unknown for this word: set and counted in lockstep |
| 88 | player.md: other users of 0x404468 | row 57 | | | stands | none |
| 89 | ui.md P3: the writers of the pause flag (table of 23) | `g_paused` 0x41b4f4 | 21 functions W, 2 as & | 23 functions W, the same 23. The two memory-card rows quote the address-taking instructions; the stores are 0x21e8a8 and 0x21e90c | stands | none |
| 90 | ui.md P4: everything else the item, stat and skill screens change goes through messages ("every assignment into 0x4d8af0–0x4ebbb0 in the range") | player record table | — | the corrected scan adds indexed stores in 13 functions of the range. Read: `stats_screen` 0x1d25c8 writes +0xee (already in P4); 0x1de8c4 (row 59) and 0x1c2120 are unreferenced; `player_addSkillAbility` and `player_rebuildAbilities` are called only from message handlers and character set-up; the rest are the message handlers themselves or stale | stands | none |
| 91 | script.md: `hidePlayers` stores a byte read only by `Player_draw` | 0x4f83f8 | R 0x1a4900; four writers | identical | stands | none |
| 92 | script.md: `activateStore` stores the store index and a pending flag | 0x4f7150, 0x4fdd30 | — | 0x4f7150: one store, no reader. 0x4fdd30: W 0x144054, 0x22f2b0; R 0x22f7fc | stands | none |
| 93 | script.md P5: no writer of the active player stores −1 | row 5 | | the two added writers store 0, 1 or the value with bit 0 flipped | stands | none |
| 94 | engine.md: `g_paused` is only touched offline by the pause menu | row 89 | | | stands | none |
| 95 | netcode.md: tick step 5, the hash term | row 32 | | | stands | none |
| 96 | netlib.md: the only writer of the UdpLibrary clock counter is `SRSClient_update` | 0x564208 | & only | R 0x32d390, W 0x32d39c there. Its reader `UdpDriverPS2_Clock` 0x395e3c loads it relative to the global pointer, which `gxref` does not follow (6.1, limit 4) | stands | none |

### 3.10 docs/monsters.md, monsters-2.md, gameplay.md, audio-save.md, online-setup.md, spec/movement-camera.md

| # | Claim | Global | Old evidence | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|---|
| 97 | monsters.md §7.1, monsters-2.md: the "not drawn" word is read only by the travel effect; the camera pointer's only writer is `game_initCamera`; 0x501b78 has no reader; the mission-menu draw's two globals are referenced by nothing else | 0x8e3c38; 0x4f8450; 0x501b78; 0x8e2e98, 0x4fe7e4 | — | 0x8e3c38: W 0x27da3c, R 0x27e928. 0x4f8450: W 0x1e6bb0 only (one possible store in `minimap_draw` is a stack store). 0x501b78: one store, no reader. 0x8e2e98 and 0x4fe7e4: R and W only in `missionMenu_draw` | stands | none |
| 98 | gameplay.md §8.1, audio-save.md A4, online-setup.md: the music counter is dead; the audio range does not reference the shared seed; 0x507268 is not read anywhere else by direct address | 0x4f7158, 0x4f717a; 0x404464; 0x507268 | — | row 76; no hit on the shared seed in 0x210000–0x217000 except a text-pointer increment in `ambient_parse` (0x215254, stale); 0x507268: one & (0x33f260) | stands | none |
| 99 | movement-camera.md §4.1: "the record multiplier is written only by `SpellGiantGrowth` (0x3093c4, 0x30965c) and `SpellResurrect` (0x312a28, 0x312adc) code"; and no code writes 0x4d8a28 | record +0x4c20 (slot 0: 0x4dd710); 0x4d8a28 | exactly those four hits (three W, one &) | 0x4d8a28: R only, holds. **+0x4c20 has three more writers**: arena set-up 0x307c80 (store 0x307d04; called from `arena_init` 0x304dd0 and `arena_startWave` 0x305f20) gives every player 1.25 in a net game and 1.75 offline; `player_importCharacter` 0x1bdb0c and `player_initNewCharacter` store 1.0. The corrected scan still misses 0x307d04: the low half of the table's address is folded into the index register (6.1, limit 3) | **wrong** | not a sync matter (set-up runs in lockstep). The specification and MV6 need "…and by arena set-up: 1.25 in a net game, 1.75 offline (capped by the 1.2 limit)". A rebuild that follows §4.1 moves arena players at the campaign speed |

## 4. Conclusions that change

1. **FINDINGS G5** — 0x41c138 *is* written: `pad_updateRumble` (0x174790) counts it down
   on every tick and clamps it at 0. Reword to "never set to a non-zero value". Same
   sentence in the note of the `pad_apply` symbol and in dynamic-tests.md row b5.
2. **movement-camera.md §4.1 / MV6** — add arena set-up (0x307c80) and character
   import / creation to the writers of the record speed multiplier (row 99).
3. **FINDINGS G9** — replace "written only by game setup 0x1e15f8, 0x1e1888" with the
   list of row 15.
4. **FINDINGS D20, script.md §6** — add `playGotItemSound` (clamps to slot 0 or 1) and,
   offline only, `dialog_runTask` to the writers of the active player.
5. **FINDINGS D13** — add the two save / set / restore brackets (`Creature_pickTarget`
   with 8, `Vehicle_collideObjects` with 1) to the mask writers.
6. **FINDINGS D7, D24; arena-desync.md** — the engine camera position is also written by
   `Camera_loadState` (from `save_load`); the mode word also by `Camera_updateFree`. The
   "not read to confirm they only read" remark can be closed for position and focus.
7. **FINDINGS B10** — fourth reader of the latch: `Camera_computeTarget` 0x206778.
8. **FINDINGS K4 table, kill-loot-xp.md** — +0x4a74 / +0x4a78 are also read and written
   by the unreferenced HUD function 0x1de8c4.
9. **mainloop.md P5** — the second reader of the HUD message timer is `Vehicle_run`, not
   a camera function. **mainloop.md §9, script.md §2.1** — 0x4f8694 is read by its own
   writer.
10. **skills.md (c)** — the force byte is counted down by `net_frameLoop` (0x13b26c);
    list the five non-spell writers too.
11. **data-tables.md §5** — four functions swap the monster level temporarily, not two.
12. **sync-breakers.md** — two more stores to `g_lobbyLaunch` and two more setters of
    `g_worldPiecesDrawn`, none of which changes an argument.
13. **player.md** — the exit countdown is decremented in `hud_run` every tick (answers an
    Unknown); more writers of the aura globals and hint timers.
14. **lag.md §7** — the remark about stale-register artefacts in the peer-table sweep no
    longer applies.
15. **FINDINGS "Tools added"** — the corrected `gxref` is not "any access is found": see
    6.1. In particular a hit without `?` can carry the wrong address.

## 5. New candidates from the delta file (step 4)

Method: for each of the 196 globals in `gxref_delta.tsv`, the newly found writers and all
readers were classed by name as presentation (draw, HUD, menu, audio, camera, pad, memory
card, main loop outside the tick) or simulation, and every pair "presentation writes,
simulation reads" was read, in both senses (a newly found presentation writer with any
simulation reader; a newly found simulation reader with any presentation writer). The
classification flagged 24 globals; the pairs that are not plainly shared set-up are below.
**None is a new candidate.**

| Global | Presentation writer (new) | Simulation reader | Finding | Where it is already covered |
|---|---|---|---|---|
| `g_cameraFocus` 0x44f048 | `camera_updateFocus` 0x18a5ac | `runObjects` 0x14ba98, `arena_pickSpawnPoint` 0x305328 | both reads are inside "not a net game" branches | — |
| same | same | `damage_apply` 0x1e8330 | counts into the dead block 0x4f7158 | gameplay.md §8.1 |
| same | same | `obj_updateActive` 0x14db50, `isNearView` 0x1e77d8 | the D6 route | FINDINGS D6, D29 |
| `g_cameraPos` 0x44f038 | `camera_setView`, `Camera_loadState` | `cut_setup` 0x19aa5c, 0x19ab58 | the blend-in and blend-out keys built from the local camera are made only when the game is not a net game | — |
| same | same | `cut_evalCamera` 0x197198 | the value read is replaced by key data before its only use | answers mainloop.md P9's question about this function for the position |
| same | same | `DragonGoldPile_run` 0x295da8 | own-generator draws that depend on the camera | monsters.md §7.3 |
| `g_hudMessageFrames` 0x4f66e0 | `hud_tickMessage` 0x1d938c (counts only while this machine is not warming up) | `Vehicle_run` 0x207dc4 through the getter 0x1d933c | gates the one-time driver help text and its latch +0x408 | row 72; low, vehicles only |
| `g_menuInputLockout` 0x41b4fc | the two modal loops | `Player_run`, `Player_takeDamage`, `Vehicle_run` | zeroed at the start of every net tick | FINDINGS D26 |
| `g_shopOpen` 0x41b50c, `g_helpMessageOpen` 0x41b928 | `shop_close` 0x1d0af4, `help_task` | script `storeRunning` 0x1440f8, `helpMessageActive` 0x1433bc | per machine; no shipped script calls either | script.md P6 |
| `g_localMenuOpen` 0x41b69d | `inventory_close` 0x1c5318 | `Player_usePotion`; `Player_takeDamage` 0x1b53f4; `inventory_removeItem` 0x1c1f74 | K2; screen tint only; refresh of the open item panel only | FINDINGS K2; kill-loot-xp.md |
| `g_networkMode` 0x402791 | `hud_netStatusDraw` 0x1dbe74 | about 40 simulation functions | this is the machine leaving the game at the end of its exit countdown | ui.md (HUD) |
| `g_exitCountdown` 0x4f694a | `hud_run` 0x1db8f0 | `Player_takeDamage` 0x1b53e4 | `hud_run` is a run task; the decrement is unconditional | row 87 |
| `g_drawFrame` 0x44fdd0 | `gfx_endFrame` 0x19db00 | `ShopDaemon_run` 0x1d1490 | restock timer of a class nothing constructs | ui.md P10 |
| same | same | `script_runByName` 0x1ed6f4 | row 73 | — |
| `g_cosmeticSeed` 0x404460 | about 30 drawing and audio functions | `damage_apply` 0x1e88b8, `SkillMultiFire_cast`, `SkillRiposte_counterAttack`, `SkillSummonSkeleton_cast`, `SkillStrongStance_trigger`, `world_runLightChunk` | particles, except the MultiFire damage figure for a non-player caster | rescan.md §4.3, skills.md (b) |
| `g_paused` 0x41b4f4 | `memcard_pushPause`, `memcard_popPause` | `script_gamePaused`, `Player_run`, `game_checkAllDead` | both return at once in a net game | ui.md P3 |
| `g_minimapMode` 0x4f8400 | `minimap_draw` | `save_build` 0x221914 | a per-machine display setting that `save_build` stores in the save buffer's header, before the player count and the player blocks, after the camera state (0x221a54) and the jump-gate list | audio-save.md |
| `g_cardScreenDone` 0x4f8f29 | the memory-card screens | `Savepoint_run` 0x28ce24 | per-machine card state in a run function | sync-breakers.md §4b |
| `g_lumpGeneration` 0x41bf78 | `lump_unloadUpToLevel` 0x1713c0 | `GameObject_ctor` and four constructors | changes only when lumps are unloaded, at level changes | — |
| `g_pendingLevel` 0x41b6d0 | front end, main loop | `net_frameLoop` 0x139fb4 | known gate of the tick | mainloop.md |

The reverse direction (a simulation writer newly found, a presentation reader) gives
nothing: such a pair cannot move shared state.

## 6. What the three scanners can miss

### 6.1 `tools/gxref.py` after the fix

Not asked for, but the audit depends on it. Measured against the decompile for all 513
globals that have a `g_` name: the corrected scan lacks a user *function* for one of them
(limit 3). At the level of single instructions it is weaker.

1. **It follows the listing, not the control flow.** Only the latest address given to a
   register is remembered. Where two paths join, the scan applies both paths' arithmetic
   in sequence. Two real cases:
   - 0x22231c (`memcard_portLabel`) is printed as a certain store to 0x86dbf8, inside the
     quest-variable table. The register was adjusted once on each of two exclusive paths;
     the real target is the text buffer 0x879ea8.
   - 0x1db688 (`hud_drawControllerOut`) stores to 0x4f6708. The base was set in the delay
     slot of a branch at 0x1db4a0 and re-used for another address further down the
     listing, so the scan prints the store as possible under 0x4df1f8 and does not list
     it under 0x4f6708 at all.

   So a hit without `?` is "certain in listing order", not certain.
2. **`?` means two different things.** An index added to the register (the normal way to
   reach element *n* of a static array) and a register that was simply reused both end in
   `?`. Per-slot arrays (0x41b818, the alive slots, the player record table, the send-cycle
   table) show *only* `?` hits, and they are real.
3. **A base folded into the index.** The compiler may add part of an array's address to
   the index register. `g_goldFloaters` 0x86a918 is reached from 0x86a900 with the other
   0x18 in the index: no hit at the array's address in either scan. The store to record
   +0x4c20 at 0x307d04 shows under 0x4e4c20, and the launch-record stores of
   `net_launchPrepare` (row 56) are not reported at all. A range scan needs slack below the array,
   and a field of a static structure array needs a displacement search or the decompile
   (`DAT_<slot-0 address>`) as well.
4. **Global-pointer-relative access.** Three instructions in the executable (0x395e64 and
   two more in the same driver, addresses 0x5641e8 and 0x564208).
5. **Constants that are not addresses.** 0x1d9aa0 builds a colour value that falls inside
   the peer table.
6. **Addresses that are not built in code at all**: pointers held in data (the two option
   tables, through which every options-menu store is made; the script built-in table),
   in memory, or returned by a call; and block fills and copies, which show only as `&` at
   the first byte.
7. Code between Ghidra's functions (0x217cc8) inherits the previous function's registers.

### 6.2 `tools/fieldxref.py`

It prints every load or store whose displacement equals the offset asked for and whose
base is not the stack pointer. No look-back window, because nothing is tracked. It misses:

| # | What | Size of the gap / example |
|---|---|---|
| 1 | **Unaligned accesses.** The left / right pairs used to copy 8 (and 4) bytes at once are not in its instruction lists | 4,963 unaligned 8-byte loads and 4,594 stores with a non-stack base, plus 77 and 59 4-byte ones. Copies of position pairs are mostly done this way |
| 2 | **A wider access at a lower displacement.** An 8-byte store at X also writes X+4; a word store writes the three bytes after it | 3,360 8-byte stores and 2,833 loads with a non-stack base. Asking for +0x44 does not show a store of 8 bytes at +0x40 |
| 3 | **A pointer formed first.** `base + K` put in a register and then used with a small displacement: loops over an array inside the object, zero fills, copies | `Player_ctor` 0x1a228c–0x1a22b0 clears the 16 status counters; every clone function copies them; `player_initNewCharacter` 0x1b21f0–0x1b2234 clears +0x4a58, +0x4a5c, +0x4a74, +0x4a78 this way |
| 4 | **Array elements.** An indexed access is printed at the displacement of element 0 only | asking for counter 7 (+0x388) does not show a loop over +0x36c |
| 5 | **Static instances.** A field of an object at a fixed address is usually addressed absolutely; the displacement is then the low half of the address | the player record table, the static camera object, the peer table |
| 6 | **A shifted `this`.** Virtual calls here pass the object plus a per-table adjustment; inside such a function every displacement is smaller by that amount | not measured |
| 7 | Whole-object copies and fills through a library routine | clone, save and load |
| 8 | It cannot tell classes apart (every structure with something at that displacement is printed), and it names functions by the heuristic boundaries that split a function at its first switch label (D32) | 0x1a60e0 and 0x1a6c30 in its output are parts of `Player_run` |

**Fix, in words.** Add the eight unaligned instructions, taking the displacement of the
"right" half as the field start. For an offset X also print accesses at X−k whose width
exceeds k, marked as covering. Track, per function and with Ghidra's boundaries, registers
that hold "object register + constant" (and their copies and self-increments) so that a
small displacement on such a register is printed as the sum, marked as derived, and a
self-increment as a range. Accept an optional static base and stride and print the
absolute form too. Take a function-range filter so one class's code can be isolated.

### 6.3 `tools/flagxref.py`

It looks for one instruction that carries the mask as an immediate and then requires a
word load or store at the flag-word displacement within **six instructions before or
after it**. It misses:

| # | What | Size of the gap / example |
|---|---|---|
| 1 | **The fixed window.** A flag word loaded once and tested later, or kept in a register across other work | of the plain immediate tests whose operand register was last loaded from displacement 0xc, 540 lie within six instructions and 55 do not |
| 2 | **Any mask that is not exactly the one bit.** A test, set or clear of several bits at once uses a different immediate | every combined test of the dead / inert / copy bits |
| 3 | **Tests by shifting.** A bit moved to the sign position and branched on, or shifted down and masked with 1 | 73 loads of displacement 0xc are followed within six instructions by a shift of the loaded register |
| 4 | **The mask in a register.** A low-half mask loaded into a register first, or a high-half mask built further away than four instructions from its use, or hoisted out of a loop | — |
| 5 | **Byte and halfword access.** A bit of the second byte tested through a byte load at displacement+1 with the mask shifted down; 64-bit flag words loaded as 8 bytes | 226 byte or halfword loads at 0xc–0xf with a non-stack base. The creature flag word at +0xa8 is 64 bits wide: `flagxref 80000000 a8` prints nothing, although `Creature_run` sets and clears that bit (row 36) |
| 6 | **Toggle and whole-word writes.** Exclusive-or with the mask; a store of a constant or of another object's flags | — |
| 7 | **Clearing bit 15.** The clear constant does not fit one instruction, so the pattern it looks for cannot occur | mask 0x8000 |
| 8 | A flag word reached through a formed pointer or at a fixed address (as 6.2, items 3 and 5) | — |
| 9 | **False hits.** Any unrelated instruction with that immediate near any access at that displacement; and its test for "the next instructions use this register" is a text search, so register 2 matches register 20 | — |

**Fix, in words.** Per function, follow the register that received the flag word from the
load until it is overwritten, instead of a window. Accept any immediate that *contains*
the bit and print the whole mask. Recognise the two shift forms, the sign-bit branch,
exclusive-or, masks loaded into a register (followed the same way), byte and halfword
loads with the mask shifted, 8-byte loads, and the two-instruction clear constant.
Compare operands as tokens. Report whole-word stores at the displacement separately.

### 6.4 Claims that rest on these two tools

Not re-checked here beyond rows 33 and 36. The ones the ledger leans on: D12–D15 (status
counters), the "Ruled out" entry for hit-flash flag 0x100 ("read only by drawing"), G2
(handle lists of the clone), G12 and patch "prediction copy starts without pending
damage" (+0xc8), D28 and its patch (+0x530, +0x508), creatures.md C2 (flag 0x80000000),
kill-loot-xp.md (prop +0x104, object +0xe4, tint +0xa0), and the object-flag table in
objects.md. Items 1–4 of 6.2 and 1–3 of 6.3 are the ways each could be incomplete.

`tools/ghostreach.py` has its own tracker with no window, but it does not count unaligned
or 16-byte stores as stores and it too follows the listing, so "563 globals written" in
the ledger's tool paragraph is a lower bound.

## 7. Not done

- The possible writes of the camera *matrix* in `line_draw`, `Camera_updateFree`,
  `Camera_updateFollow` and `DragonGoldPile_run` were not classified one by one.
- netcode.md row 1a (readers of two pad fields) is a field reached through a pad pointer;
  the document itself says the search was not exhaustive, and it was not redone.
- The claims of 6.4.
- `arena-entry.md` and `rescan.md`, written after the fix, and the specification files
  that appeared under `docs/spec/` while this audit was running.
- How often limit 1 of 6.1 occurs was not measured; only the two cases met during the
  audit are given.
