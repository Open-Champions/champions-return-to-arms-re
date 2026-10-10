# Sync breakers that do not depend on a level

Scope: eight ways a network game was suspected of going out of sync, found by the first
round (docs/ui.md, audio-save.md, player.md, monsters.md, mainloop.md, startup.md,
objects.md, engine.md). Each is worked through to a static answer here: real or not, when
it bites, what players should avoid, what testers should try, and a one-word patch where
one exists.

Everything was read from the executable (SLUS_209.73, v2.00) and from the files on the
disc; **nothing was run, and every patch below is untested.** Each statement is
**Observed** (read at the address given), **Inferred** or **Unknown**. New names are in
`symbols/syncbreakers.tsv`. `FINDINGS.md` and `patches/` were not edited; proposed ledger
rows and corrections to earlier documents are at the end.

Two facts from the disc are used several times. They come from throw-away scripts that
read every level's `objects.ob` (120 files) and every animation header (4,510 `.anm`
entries in 560 lumps); only counts and property names are reported.

A warning about method. `tools/gxref.py` only sees an access when the `lui` that builds
the address is within 64 instructions. In long functions it misses accesses: it missed
three of the nine stores to 0x4f8f28 and one of the two to 0x44f054 inside
`mainloop_runSession`, and a first draft of this document drew a wrong conclusion from
that (it took the latch of section 4c for something every load leaves behind). Every "only writer" and "only reader"
statement below was therefore rechecked against the decompile and with a scan that has
no distance limit (any access with the right displacement whose base register is loaded
with the right upper half anywhere earlier in the same function).

## Result in short

| # | Candidate | Verdict |
|---|---|---|
| 1 | Character checksum exchange | Real mechanism, runs only when every player uses a lobby-stored character. Compares two numbers per player every 240 ticks and **drops** a player on a mismatch. No false mismatch found in normal play; the memory-card case in audio-save.md A1 cannot happen while the exchange is on |
| 2 | Shop stock from the cosmetic seed | Not real. The two seeds are equal when stock is generated |
| 3 | `getMedal` / `runMedalSuccess` read the local record | Not real. The value only decides what is drawn |
| 4 | Savepoint | Address in message 5: not real. Local memory-card state in the prompt: **real but narrow** (the script "active player" can differ for a while). A save that ends in a card error leaves the save buffer rewritten and a latch set that switches off the act-change clean-up on that machine: **real**, needs a card error |
| 5 | JumpGate drawn flag, travel effect | Not real with the levels on the disc: no gate uses the automatic mode the flag gates |
| 6 | `gameMiscSync` seed step; item loader's 223 draws | Not real. Every input of both conditions is the same on all machines |
| 7 | Local options | Options menu: not real. `debug.sht`: **real**, self-inflicted. The launch handshake copies no options |
| 8 | Random animation phase in constructors | Not real. Placed objects get the same phase everywhere; the animations carry no events and (one placed class aside) no root motion |

None of the eight is something an ordinary co-operative session is likely to run into.
The three that are real need, respectively, two players saving at the same save point at
once followed by an unusual script order; a memory-card error; and a cheat file.

## Background used below

- `g_cosmeticSeed` (0x404460) is set equal to `g_randSeed` inside `game_loadLevel`
  (0x1e59c4), before the level's objects are created (`level_loadScriptAndObjects`
  0x217978 is called later in the same function). **Observed.**
- "Lobby-stored character": the low five bits of record +0x4c1c are a character kind.
  `player_initNewCharacter` (0x1b1d70) writes 1 unless its ninth argument says otherwise;
  the one caller that passes 2 is the character-creation screen while a lobby session is
  open (0x2285cc, test of `lobby_stateIsMenu` at 0x228584; the other five callers pass
  −1); `player_importCharacter` writes 1 (0x1bdb14); the launch code gives 2 to quick characters in a lobby game
  (0x137400–0x137434). **Observed.** Kind 2 characters are handed to the lobby library by
  `lobby_sendCharacter` (0x3278f0) and are refused by the memory-card paths (below), so
  kind 2 = stored by the lobby service, kind 1 = memory card. **Inferred.**
- `net_allPlayersState2` (0x1ec5d8) is true when the game is a net game, `g_lobbyLaunch`
  (0x4f7134) is set, `g_gameCompleteFlag` (0x4f85c5) is clear and **every** player's kind
  is 2. **Observed.** `g_lobbyLaunch` is written by `frontend_startNetGame`: 1 when the
  lobby state word 0x506160 is non-zero (0x1e2258), 0 on the developer LAN path
  (0x1e2270). Below, "all-lobby-character game" means a game where this function is true.

---

## 1. Character checksum exchange

### Facts

| Fact | Kind | Where |
|---|---|---|
| Inside `gameMiscSync`, only when not in the front end and `net_allPlayersState2()` holds: on ticks where frame mod 240 is 60, the first active machine sends game message 9 | Observed | 0x1e3e58, 0x1e3e88–0x1e3eb4; `net_localIsFirstActive` 0x13d668 |
| Message 9 zeroes a counter and sets a pending flag on every machine; in the same tick `gameMiscSync` calls `net_sendChecksums` and clears the flag. So every machine computes on the same tick | Observed | handler 0x1d908c–0x1d90a0; 0x1e3e6c–0x1e3e80 |
| `net_sendChecksums` fills a table of two values for **each** player: `player_checksum` of the live record, and of that player's record inside this machine's save buffer (`save_playerBlock`). It sends only the pair of its own slot (message 10) | Observed | 0x1de4bc, 0x1de4d0–0x1de4e0, 0x1de570 |
| `player_checksum(slot, rec)` mixes: experience (+0x5c), gold (+0xe4), the four appearance bytes (+0x20), the two level bytes (+0x58, +0x59), the words at +0x94…+0xa7 (the word at +0x90 has weight 0), mana, maximum mana and pending potion mana (+0xc0, +0xc4, +0xc8), skill points (+0xe8), the 0xa88-byte block at +0x3748 and the 17 equipped-item words at +0x43f0. It also mixes in the **address** of the record shifted by the slot. Hit points, the bags, the ability records, quest text, medals and the menu bytes +0xed/+0xee/+0x4a58 are not covered | Observed | 0x1bdc98; address term 0x1bdcbc |
| Both addresses are fixed (the record table, and a fixed place in the save buffer), so the address term is the same on every machine | Observed for the table; Inferred for the buffer (its two leading sections have fixed sizes, docs/audio-save.md) | 0x2184a4 |
| Message 10 stores the sender's pair and counts. When the count equals `g_numPlayers`, every slot's received pair is compared with this machine's own pair for that slot | Observed | 0x1d90a4–0x1d9130 |
| On any difference for slot *j*: `g_checksumFailed` is set (the HUD then shows a checksum-failure line for the rest of the session: the flag is cleared only at session start); and if *j* is not this machine's slot, `net_disconnectPlayer(j, 1)` | Observed | 0x1d91c8–0x1d91d4; HUD 0x1dbcf8; clear 0x1e6f48 |
| `net_disconnectPlayer` marks peer *j* dropped on this machine only. If this machine is the first active one it also sends message 4, which kills *j*'s character on every machine | Observed | 0x13de68; `hud_onMsg` case 4 |
| `g_numPlayers` is not reduced when a player leaves. After any drop the count can no longer reach it, so no comparison is ever made again in that session | Inferred (the count needs one message per original player; the writers of 0x4d8ae0 are set-up code and `save_load`) | 0x1d90f4 |

### What a mismatch does

A machine that drops *j* stops counting *j* as active. Input packets are ignored when the
sender's active mask differs from the receiver's (docs/netcode.md, row 2), so a machine
that drops somebody the others did not drop is cut off from all of them: its simulation
stops when buffered input runs out, the others freeze until the 900-call silence timeout
removes it. If every other machine sees the same mismatch for *j*, they all drop *j* in the
same tick and carry on without him. **Inferred** from the Observed pieces.

The exchange is therefore a second out-of-sync detector with a harsher outcome than the
position hash: it covers gold, experience, mana, skills and equipment, which the hash does
not, and it removes a player instead of printing a line.

### When the two values can differ without cheating

*Live record.* Every covered field is changed only in lockstep code or restored after
prediction (hit points and mana: FINDINGS G3). A difference means the simulation has
already diverged in one of those fields. No per-machine writer of a covered field was
found; the three menu bytes that are per machine (docs/ui.md P4) are not covered.
**Observed** for the field list, **Inferred** for "no writer" (not an exhaustive search).

*Save-buffer copy.* The player blocks of the save buffer are written by `save_build`
(snapshot of every player) and zeroed by `save_clearBuffer`. In an all-lobby-character
game:

| Writer | Same tick on every machine? | Where |
|---|---|---|
| launch | yes, buffer zeroed | 0x1375cc |
| Savepoint auto-save, script `saveCheckPoint` | yes, lockstep | 0x28d65c, 0x142a5c |
| act change | yes, unless the save latch of section 4c is stuck on a machine; and the autosave on the first tick of the new level rebuilds the blocks | 0x320fcc |
| checkpoint autosave after a level load (`save_daemonRun`) | **gated by per-machine state**: card screen state idle, `g_menuOpenFlag` clear, local camera in follow mode | 0x2188a8 (gate 0x218924–0x218984, call 0x2189cc); armed by `game_loadLevel` 0x1e6174 |
| memory-card save (`save_packLocalPlayer`) | **cannot happen**: script `saveGame` returns when any player is kind 2 (0x146c04), and `Savepoint_interactPrompt` returns "nothing here" when `net_allPlayersState2()` holds (0x28da7c), so the save screen is never opened | 0x218d80 |

The autosave gate is the only per-machine input left. It is armed once per level load and
fires on the first tick on which the gate is open. For that tick to differ between
machines one of them must have a card screen open, a full-screen menu open or its camera
out of follow mode at that moment:

- Menus are closed on every level-change path that does not need a cheat file: the script
  `newWorld` family, the mission menu, the jump gate and recall all call
  `net_closeLocalMenus`, and `hud_run` refuses to open the inventory while those run
  (0x1dba44–0x1dba6c). The save daemon (priority 20) runs before `HUD Run` (50) in the
  tick, so nothing can be reopened first. **Observed** for the calls, **Inferred** complete.
- A level that starts with a cutscene holds the camera out of follow mode on every machine
  alike; `cut_runFrame` puts it back in the tick that ends the cutscene (0x199f5c).
- A config save (card state 5) holds the write flag `g_cardWriteBusy`, and the main loop
  waits for that flag before it loads the next level (0x322cf4). Only the single displayed
  frame between "state 5 requested" and "write started" is unprotected.

So: **no false mismatch in normal play.** The residual cases are that one-frame window, a
shop opened by a use-button press that lands on the very first tick of a level
(`runObjects`, priority 10, runs before the save daemon), and a machine whose save latch
is stuck (section 4c).

### Verdict

Real mechanism; active only in all-lobby-character games; not a source of desync by
itself. It turns a divergence in the covered fields into a dropped player within four
seconds, and it stops working after the first player leaves.

- **Players:** in a game where everyone uses a lobby-stored character, a player who
  vanishes a few seconds after something odd happened was removed by this check; nothing
  you do in the menus triggers it.
- **Testers:** all players on lobby characters; note the tick at which the checksum line
  appears and which slot each machine drops. To exercise the save-buffer half, change an
  option and accept the config save in the last frames before a level change.
- **Patches:** P3 (compare the live record only) or P4 (report but do not drop), below.
  Neither is needed unless a test shows a false failure.

---

## 2. Shops

### Facts

| Fact | Kind | Where |
|---|---|---|
| The buy message carries the address of a record in the static stock table; `shop_buy` reads price and item from the receiver's table | Observed | 0x1c5f78, 0x1c5d28, 0x1d1240 |
| Stock generation makes three draws from `g_cosmeticSeed`; each, below 0.1, adds a call to `item_generateFromSpecialTable`, which draws from `g_randSeed` and appends one item | Observed | 0x1c7ea0, 0x1c80c4, 0x1c8498 |
| It runs once per load of `hub`, `hub2`, `islgnome`, `stobonus`, after the warm-up loop and the net ready-wait, outside any tick | Observed | 0x3230c4, 0x3230f0 |
| The cosmetic seed is made equal to the shared seed during the same load | Observed | 0x1e59c4 |
| `game_clearLevel` (start of every load) stops every sound sequence (through `lump_unloadUpToLevel` → `sound_unloadAbove`), zeroes camera shake, and empties the scenery-animation table | Observed | 0x1713e8 → 0x215418; 0x1e4f80; 0x1e5078 |
| From the level change until after stock generation, world pieces are not drawn (`g_worldPiecesDrawn` 0x44f054 is 0), and scenery animations are only registered when a piece is drawn | Observed | cleared 0x322e2c, set again 0x323140; test 0x189cc8; registration 0x187fe0–0x188004, reached only from the piece-draw call 0x189d94 |

### Why the seeds are still equal at stock generation

Between the copy and the stock call the main thread runs: the rest of `game_loadLevel`,
player construction, the deferred scripts, a per-machine number of passes of the warm-up
loop (`Camera_update`, `drawWorld`, `cut_runFrame(1)`), and a per-machine number of
`net_main(1, …)` calls. A direct-call search from each of these for the functions that
touch the cosmetic seed (51 in the decompile; the unlimited scan adds a HUD draw helper
and one routine nothing calls, neither on these paths) gives:

| Reached consumer | Count per machine |
|---|---|
| one draw for the level music timer, one per ambient entry (`game_loadLevel` 0x1e5a40, 0x2150c8) | fixed by level data |
| `anim_randomizeTopTime` and `rigidbody_init` in object constructors | one per object, fixed by the object list |
| `sound_update` ×2 at the end of `game_loadLevel` | no sequence is playing (all stopped above; no constructor reachable from the factory starts one); ambient timers are set in seconds and cannot expire in two calls |
| `Camera_apply` shake draws (warm-up loop and `net_predictLocalPlayer`) | none: shake is 0, and none of the four store levels' scripts shakes the camera |
| `world_draw` → scenery animations and piece drawing (the chain docs/ui.md P1 worried about) | none: table empty, pieces not drawn |
| `cut_runFrame(1)` | only overwrites the seed with shared values (0x19af20, 0x199f88) |

The loading-screen thread reaches no consumer. **Observed** for each row; **Inferred** that
the list is complete (virtual calls and script built-ins were not followed, apart from the
store levels' own scripts).

### Verdict

Not real: the stock tables are identical on all machines. If they ever were not, the
shared seed would differ too (the extra item costs shared draws), so the position hash
would report it on the first tick in the store level; a silent wrong purchase is not
possible.

- **Players:** nothing to avoid.
- **Testers:** compare the word at 0x404460 on two machines at 0x3230c4.

---

## 3. Medal levels

### Facts

| Fact | Kind | Where |
|---|---|---|
| `mission_getMedal(mission, min, flag)` reads the medal byte of the local slot unless `flag` is set in a net game | Observed | 0x1bf838 |
| Script `getMedal` passes flag 0. All nine `*MEDAL` scripts store the result in one variable and use that variable only as the second argument of `runMedalSuccess` | Observed | 0x142188; scripts BLOMEDAL, DISMEDAL, FIRMEDAL, INNMEDAL, NITMEDAL, STOMEDAL, TORMEDAL, VALMEDAL, WATMEDAL |
| In `runMedalSuccess` that argument and a second local read of the medal decide only which lines are laid out and how tall the box is. The return value comes from the lockstep pad of slot `g_medalPlayerSlot` (0x4f7148) | Observed | 0x1417a4 (local read 0x1418ac, layout loop after it, pad test from 0x141b5c) |
| The medal player's machine returns early while its own card is busy, and only then sends message 12; every machine waits for message 12 before it looks at the pad | Observed | 0x141810–0x141850 (busy test 0x14181c, send 0x14183c); `runMedalFail` 0x141c50–0x141c9c |
| The medal scripts call `setpv`, which starts a config save on each machine whose profile did not have that value yet, so card state does differ between machines here | Observed | 0x22274c → 0x217bdc |
| `mission_grantMedal` walks all records in lockstep; `playerAdjustStat` is always called with slot −1 (27 calls), which is the direct path, not the message path | Observed | 0x1bdb80; 0x146348 |

### Verdict

Not real. The per-machine medal value never reaches a branch or shared state, and the
per-machine card state is fenced by message 12. One narrow residue: after message 12 the
medal player's machine still returns before the pad test while its card is busy
(0x141824), and the others do not; that needs a card operation to start on that machine
during the dialog, and `gameMiscSync` closes that machine's menus while the dialog is up
(0x1e3d80–0x1e3dcc).

- **Players:** nothing to avoid.
- **Testers:** two characters with different medals for the same mission; compare the
  script variable and the sync hash through the result screen.

---

## 4. The Savepoint

### 4a. The object address in game message 5 — not real

| Fact | Kind | Where |
|---|---|---|
| Message 5 carries the Savepoint's address; the handler stores 1 at address + 0xcc with no check | Observed | 0x1de1a0, 0x1d8f00, 0x28cdc4 |
| A Savepoint is 0x118 bytes, so it comes from pool class 0 (0x180-byte blocks) | Observed | factory size; class table 0x403a10 |
| `pool_init` rebuilds all three free lists in address order at the end of `game_clearLevel`, i.e. on every level load; allocation pops the head | Observed | 0x1e5118, 0x14fcd8, 0x14fdb8 |
| Level objects are created in file order during the load, before the players and before any tick | Observed | 0x14e808 from 0x217978 |
| The per-machine object known so far, the prediction copy, is `Player`-sized (0x590 > 0x500) and so lives in class 2, and it is first made after ticks have started | Observed size and timing; that no other per-machine allocation precedes the level objects is Inferred | `net_clearGhost` at level entry, docs/mainloop.md |

So every machine gives the Savepoint the same block. **Inferred.** The address is wrong
only on a machine whose object list for the level already differs (for example after
section 4c); the store then lands in some other object. Any peer can also make every machine
write the value 1 anywhere, which is a robustness point, not a sync one.

### 4b. The prompt reads this machine's memory-card state — real, narrow

| Fact | Kind | Where |
|---|---|---|
| `Player_interact` calls slot 13 of the nearest usable object; only when that returns 1 or 2 with a text does a button press set `g_scriptActivePlayer` and call slot 14 | Observed | 0x1b2640; store 0x1b2b70 |
| `Savepoint_interactPrompt` returns 0 with no text when `memcard_isBusy()` is true | Observed | 0x28da6c–0x28da78 |
| `memcard_isBusy()` is true while this machine has any card screen open (state ≠ −1) or its card result word is non-zero | Observed | 0x217518 |
| The save screen stays open from the interact until its owner dismisses the "saved" box (or a level change is pending) | Observed | 0x218afc, sub-state 4 |
| `Savepoint_interact` makes the same test again before it sets +0x84, lights the point, sets +0xc4 and runs the `action` scripts | Observed | 0x28dc44–0x28dc80 |
| None of the 111 Savepoints on the disc has an `action` property | Observed (disc scan) | — |
| `Savepoint_run` leaves +0x84 set until the burst has played; its test of the card state clears it only for state value 0, which is a boot-time state, not "idle" | Observed | 0x28ce40–0x28ce4c |

What happens: player A opens the save dialog. While it is open, player B presses the use
button at a save point. Every machine except A's sets the active player to B and runs the
interact; A's machine does neither. Any other card screen on A's machine does the same
for as long as it is up: the config save after changing options (at least 180 displayed
frames, 0x21f390) and the reload of saved options from the options list (0x222b10). Differences on A's machine: `g_scriptActivePlayer`
(still A), and for a *different* save point its +0x84, +0xc4 and light, which are read
only by the point's own effect code and the level save record.

The active player is rewritten by the next trigger volume anyone enters and the next
object anyone uses, so the difference is short-lived. It matters only if a script that is
*not* started by a trigger or an interaction reads it first: the `newWorld` family (whose
cooldown is tested and set, FINDINGS D20), `startDialog` (which machine sends),
`putPlayersInVehicle`, `playGotItemSound` (list in docs/script.md, section 6). The worst
chain found: the level-end `newWorld` sets the 600-tick cooldown on different players on
different machines; a second `newWorld` by one of those two players within ten seconds is
then refused on some machines and not on others. **Inferred**; needs a running game.

This cannot happen in an all-lobby-character game (the prompt returns 0 for everybody,
0x28da7c).

### 4c. A failed card write — real, needs a card error

| Fact | Kind | Where |
|---|---|---|
| In a net game the save screen overwrites player block 0 of the save buffer with the local player and sets the player count to 1 before the write, and undoes it only in the sub-state reached after a clean write | Observed | 0x218d80, 0x218e88 |
| `g_cardXferLatch` (0x4f8f28) is a "card load or save in progress" latch. The save screen sets it when a slot is chosen and clears it when the "saved" box closes. The load screen sets it once a slot is chosen and clears it when the loaded level has been entered, when a load ends without a level change, or on its error exit. Boot and opening the load screen also clear it | Observed (all nine stores) | set 0x218ba4, 0x218c18, 0x2195a8; clear 0x2190d0, 0x219810, 0x219884, 0x219a18, 0x2170dc, 0x217760 |
| A card error sends the save screen to sub-state 9. Its exit restores neither the buffer nor the latch, and (unless a level change is pending) opens the save screen again from the start, where the player can retry or back out | Observed | 0x218ca0; sub-state 9 of 0x218afc |
| While the latch is 1, `mainloop_loadRequestedWorld` skips the whole act-change block: clearing the save buffer (all but the first level's state), resetting the jump-gate destination list to the start level, clearing the quest lists, removing flagged quest items from every record and clearing all quest variables | Observed | test 0x320fb0–0x320fb4, block to 0x321020 |
| `jumpgate_resetDestinations` has the same test of its own; the level change also skips `Camera_reset` | Observed | 0x27db08–0x27db10; 0x322dc4 |
| The levels are grouped in 13 acts, each beginning with `hub`. `save_actChanged` reports a change whenever the level being entered is not in the current act, so every trip to another plane is one. The current act is −1 at the start of every session | Observed | 0x217f70, table 0x4f8e48; 0x1e6f14 |
| Nothing at session start, in `game_resetState` or in the launch handshake touches the latch | Observed | the store list above is complete |
| A party-wipe reload (`save_load` from `deathTask`) reads the player count and block 0 from the buffer | Observed | 0x222674 |
| `JumpGate_interactPrompt` refuses a gate while the destination list has exactly one entry | Observed | 0x27d868 |

What follows when a save fails with a card error and the player then backs out instead of
retrying until it works (**Inferred**):

1. Until the next `save_build`, a party wipe reloads that machine with one player.
2. The latch stays 1 on that machine — through the rest of the game, back to the main
   menu, and into the next net game of the same boot. From then on, at every act change
   the other machines clear quest variables, stored level states, flagged quest items and
   the jump-gate list, and this machine does not. Going back to a plane visited earlier
   loads a fresh level on the others and the stored one here (different objects, different
   shared-seed use during the load: out of sync on the first tick); scripts that read a
   quest variable from the earlier visit diverge; and the jump-gate lists differ, so a
   gate can be usable on this machine and refused on the others.

A normal load or save does **not** leave the latch set.

### Verdict and advice

Address: not real. Prompt: real, low impact. Failed write: real, needs a card error.

- **Players:** in a game with memory-card characters, take turns at a save point — wait
  until the other player's "saved" box is gone before pressing the use button; and if a
  save ever fails with a card error, repeat it until it succeeds (or restart the game)
  before playing on or going online.
- **Testers:** (4b) two machines, memory-card characters. A opens the save dialog and
  leaves it open; B presses use at the same save point; read 0x4d8ae4 on both machines.
  (4c) make a save fail (pull the card on a console, or make the card image unwritable in
  an emulator), back out, and read 0x4f8f28; then change plane and compare the quest
  variables and the jump-gate count 0x8e3c30 with the other machine.
- **Patches:** P2 below removes the card test from the prompt, so the active player is
  written on every machine; the second test inside `Savepoint_interact` still keeps a
  busy machine from opening a second dialog. P1 clears a stuck latch at the next net
  launch; it does nothing for a save that fails during the net game itself.

---

## 5. JumpGate

### Facts

| Fact | Kind | Where |
|---|---|---|
| The constructor copies the integer property `hurt` to +0x4f. With +0x4f = 0 the gate is used through the interact prompt; with +0x4f ≠ 0 `JumpGate_run` opens the travel menu by itself when all living players are within 100 units | Observed | 0x27c848–0x27c860; 0x27d1d8 onward |
| `JumpGate_draw` sets +0xd0; `JumpGate_run` clears it on every exit. For a gate already marked found (+0x4d = 1), run returns early when +0xd0 is 0 — before the automatic open | Observed | 0x27d634; test 0x27d1e4–0x27d1e8; open 0x27d318–0x27d400 |
| For an interact gate (+0x4f = 0) the only things behind the +0xd0 test are draws from the gate's own generator, one particle and the idle animation step; the activation state +0x4e, which advances with that animation, is used for the glow and stored in the level save record | Observed | 0x27d1f0–0x27d30c; 0x27d974 |
| All 38 gates on the disc are class `Portal`; none has `hurt` or `destination`; eight have a `script` predicate. The two factory names share one constructor | Observed (disc scan); factory 0x15cea0–0x15cf08 |
| `jumpgate_travelEffect` (draw task) writes, when the travel count is 30, +0xf0 and +0x394 of every living player; +0x394 is status counter 10 and +0xf0 is read only in the counter-7 branch of `Creature_run`. Its cosmetic-seed tint writes are on the `destination` path, which no gate uses | Observed | 0x27e770; FINDINGS D12–D15 |
| In menu state 2 the chooser's machine skips the pad test for a tick while its pause menu is open and locks its input for four calls | Observed | 0x27dee0 |
| `JumpGate_interactPrompt` marks the gate found and adds the level to the destination list as a side effect, and is called from both `Player_run` and `Player_draw` (docs/script.md P1) | Observed | 0x27d81c–0x27d830 |

### Verdict

Not real with the shipped levels. The automatic open — the only shared decision behind the
drawn flag — needs a gate with `hurt`, and there is none. For the gates that exist the
flag reaches only the gate's own generator, its animation and a glow state that is saved
per machine. The travel effect's writes go to fields that nothing in the simulation reads
(with the same reservation as FINDINGS D16), and the players' objects are destroyed 150
ticks later.

Two small residues, both **Inferred** harmless: the draw-time call of the prompt can mark a
gate found one tick before the other machines do (same result after the next tick), and
the pause-menu early return needs a confirm or cancel press sampled within the frame or
two between pressing start and the first tick that sees the menu open.

What *would* break jump gates is a destination list that differs between machines; the
one way found for that to happen is the stuck latch of section 4c.

- **Players:** nothing to avoid here.
- **Testers:** nothing specific; a level built with a `hurt` gate would be the test case.

---

## 6. The seed step in `gameMiscSync` and the item loader's 223 draws

### 6a. `gameMiscSync`

| Fact | Kind | Where |
|---|---|---|
| The step is inside the same condition as the checksum exchange: not in the front end, `net_allPlayersState2()` true; then every 1800th tick `g_randSeed` is advanced once, and when bit 16 of the result is 0 the machine hands one player's record to the lobby (`game_sendCharacterToLobby(−1)`) | Observed | 0x1e3e58, 0x1e3ec0–0x1e3f0c |
| Inputs: the front-end flag (cleared by `frontend_stop` at launch on every machine, 0x1e21c8); `g_networkMode`; `g_lobbyLaunch` (set from the same test on every machine of a lobby game); `g_gameCompleteFlag` (written by a lockstep script and by `game_resetState`); the kind bits of the records, which are transferred at launch or assigned by the launch code from shared data | Observed | 0x1ec5d8; 0x1e2258; 0x146cb8; 0x137370–0x137434 |
| The record each machine hands over is chosen as (shared seed + own slot) mod active players — different per machine on purpose; the call changes only this machine's saved copy of that record, which is refreshed before every other use, and the call is off in medal missions | Observed | 0x1eb5c8; 0x3278f0 |

Verdict: not real. No input can differ between machines of one retail game.

### 6b. The item loader

| Fact | Kind | Where |
|---|---|---|
| `game_loadLevel`, for any level but `intro`, calls `item_loadResources` (223 shared draws, docs/startup.md) only when `hud.lmp` is not loaded; it then loads four lumps and raises every loaded lump to keep level 10 | Observed | 0x1e5690–0x1e5704 |
| Before that test it has already called `game_clearLevel(1)`, which unloads from the end of the lump list every lump with keep level 0 | Observed | 0x1e50b0 → 0x1713c0 |
| A lump loaded on demand (`res_find`) is registered with keep level 0 at the end of the list | Observed | 0x17365c → 0x173558; 0x172ca8 |
| Keep levels are raised only at boot, by `game_loadLevel` (10, in the branch above) and by `game_loadPlayerLumps` (5, called from the same branch) | Observed | callers of 0x17128c |
| Loading `intro` and leaving a session both unload everything up to keep level 10 | Observed | 0x1e5738, 0x32353c |

So `hud.lmp` survives to the test only if it was raised to 10 by an earlier game level of
the same visit to the game. Every machine enters a net game from the front end (`intro`),
where it was unloaded and nothing can raise it; on the first level every machine makes
the 223 draws, on every later level none does. **Inferred** from the rows above.

Verdict: not real.

- **Players:** nothing to avoid. **Testers:** nothing specific.

---

## 7. Local options, `debug.sht`, and what the launch handshake copies

### The options menu

Both option lists (pause menu 0x44f218, front end 0x4f6e88) hold the same entries. Readers
of each variable, from a search of every load of its address:

| Entry | Variable | Readers outside menus and config code | Reaches shared state in a net game? |
|---|---|---|---|
| brightness, music, sfx, stereo | 0x44fd80, 0x4f8944, 0x4f8940, 0x4f8948 | display and audio code | no |
| controls | per-slot tables 0x41b980…0x41ba30 | simulation | entry is disabled in a net game (0x18cc08, state 5); the tables are installed at launch from each owner's data. **Not the whole story** (`docs/issues/draw-sim-leaks.md`, U1): `config_commitOptions` 0x1e6650, run when the pause menu's option list is left with *any* option changed, copies this machine's four saved controller rows over all four per-slot tables with no network test (0x1e6a60–0x1e6b0c), so in a net game a machine that changes an option replaces the other players' button maps with its own |
| combat camera, reverse yaw | 0x4f845c, 0x4f8460 | `Camera_followRotateInput` | only through the camera yaw in the input record, which is by design |
| vibration | 0x41bfb0 | pad code | no |
| blood | 0x44fdc0 | see next table | no, for the values the menu can set |
| subtitles | 0x44fcf4 | `cut_setup` (letterbox height 0x44fd70), `cut_drawFrame` | no |
| damage display | 0x44fcf8 | `damage_apply`, `FlyingText_draw` | no: in a net game the number object is created whatever the option says (0x1ea998 tests the network flag first) |
| chat | 0x50391c | text-chat task | no |
| markers | 0x4f8458 | `Player_drawMarker` | no |
| voice options | 0x505b00, 0x505afc, 0x505af4, 0x505af0 | voice code | no |

The blood option, site by site:

| Site | What the option gates | Net game |
|---|---|---|
| `Creature_processDamage` 0x1113fc | gore effect, one own-generator draw, maybe a gib | executed regardless (the test also accepts the network flag) |
| same, 0x1116bc | a decal path | offline only |
| same, 0x1116f8 | two draws from the fourth generator 0x404468 and a floor decal | per machine; the generator's seven users (0x110d30, 0x1a5030, 0x24c994, 0x284b68, 0x2c7808, 0x2ee068, 0x308578) feed only particles, decals and sample points; decals are a separate pool with no simulation reader |
| `Player_processDamage` 0x1b31f4 | shared-seed draw and maybe a gib | executed regardless |
| the three `GutChunk` constructors 0x2019e0, 0x201a80, 0x201b3c | lifetime bit: set when the option is **below 2** | the menu entry is a toggle that stores 0 or 1 (list handler 0x1a01d0, type 3), so the bit is set on every machine |
| `GutChunk_run` 0x1edb6c | a particle after an own-generator draw that is made either way | cosmetic |
| `SpellBloodLust_run` 0x303e24 | draws from the spell's own generator; every draw of that generator in this function places a particle | cosmetic |
| `fx_spawn` 0x1efe9c, `fx_modelStatusEffects` 0x1f7718, `GutChunk_draw` | effects | cosmetic |

So objects.md O2 does not apply to a value set in the menu: the gib lifetime bit follows
"option < 2", and the menu cannot produce 2. A value of 2 or more could only come from a
config file read from the card (raw copy at 0x222d5c); whether such a file can exist
(for example one written by the engine's earlier game, whose config name the executable
also knows) is **Unknown**.

### `debug.sht`

| Fact | Kind | Where |
|---|---|---|
| `save_init` sets `g_debugCheats` when the card has a file of that name | Observed | 0x217420–0x217448 |
| `hud_run`: with the flag set, when slot 0's lockstep pad has pressed bit 0x4000 and held bit 0x8, slot 0 gets 1,500,000 gold and every player 20,000 experience — on this machine only | Observed | 0x1dbb64 |
| `pauseMenu_open`: with the flag set and slot 0's held-button word equal to 0x803, the menu is the debug table 0x44f458: level warp, a clean-up entry and a toggle of `g_debugInvulnerable` (0x44f20c), which `Player_run` and `Player_processDamage` read | Observed | 0x18e394–0x18e3b0; 0x1a5b64, 0x1b31b0 |
| The level-warp entry is the only sender of game messages 7 and 11 | Observed | 0x18dd5c, 0x18dd70 |

Verdict: real. A machine with the file differs from one without as soon as player 0
presses that button pair in normal play (gold is in the checksum; experience changes
levels and hit points). If every machine has the file the gold cheat stays in step, the
invulnerability toggle does not.

### What the launch handshake copies

`net_launchUpdate`'s finishing code (0x136ffc–0x137658) installs: each player's record
(packed record, or a summary for quick characters); from the host's block the difficulty,
game mode and kill limit (0x402c30–0x402c32) and the starting level; from **each** player's
block nine button-configuration words into the per-slot tables 0x41b980…0x41ba30; the lobby
identity strings; and the peer addresses. It zeroes the save buffer. **Observed.** No
options-menu value is in the block, and none is needed.

### Verdict and advice

- **Players:** do not keep a `debug.sht` file on the memory card you play online with.
  Which option settings a machine *has* does not matter; changing one during an online
  game does if anyone has remapped buttons (FINDINGS U1; the earlier version said
  "option settings do not matter"). Do not change options during an online game if anyone
  has remapped buttons.
- **Testers:** one machine with the file: have player 0 hold R1 and press down (pad bit
  names per docs/netcode.md, Inferred) and compare gold. Blood on against blood off through
  a long fight should stay in sync.
- **Patch:** P5 below makes the game ignore the file.

---

## 8. Animation phase randomised from the cosmetic seed

`anim_randomizeTopTime` (0x16d0b8) has 16 callers. Three facts settle all of them:

1. **Objects created during a level load get the same phase on every machine.** The
   cosmetic seed equals the shared seed when object creation starts, and creation consumes
   it a fixed number of times per object (section 2). **Inferred** from Observed pieces.
2. **No animation on the disc carries event bits.** The four event slots of an animation
   (times at +0x14/+0x1c/+0x24/+0x2c, bits at +0x18/+0x20/+0x28/+0x30, read by
   `anim_advance`) are zero in all 4,510 animation files. They are filled at run time by
   `creature_setDefEntryParams` (0x118378), whose callers are 59 monster constructors and
   nothing else. **Observed.**
3. **Root motion needs track flag 0x800.** Only one of the 16 call sites pushes such a
   track. **Observed.**

| Class | Call | Track pushed | Events on that entry | Root motion | Created in mid-play? |
|---|---|---|---|---|---|
| Critter | 0x254e34 | `movename` animation, flags 0x801 | none | **yes** | only when the object has a `path` property: 115 `Shark` and 4 `vulture` placements, all in level files. The critters spawned in play (corpse scavengers 0x1127b0, VampireLord's bats 0x2b8104, 0x2b9358) are built with `oneshot=1` and no path, and skip this branch |
| FireBeetle | 0x245a68 | entry 10 (`idle1a`), loop | constructor sets events on entries 3–6 only | no | yes: script `generateMonster` in FIRMEDAL (9 calls) |
| FireFly | 0x2473e4 | entry 8, loop | constructor sets none | no | only through the factory; which level class names map to it was not worked out |
| Ghoul | 0x26620c | entry 21 (`idle1a`), loop | sets 3, 4, 5, 0x11–0x14 | no | placed |
| SmallSpider | 0x2ab558 | entry 7 (`idle1`), loop | sets none | no | 12 placed; any other creation goes through the factory by name and was not traced |
| BlackWidow | 0x2abb68 | entry 16 (`idle1`), loop | sets 3–6, 8–11, 0x12, 0x14 | no | placed; the pit generator's widows take the other constructor branch (climb-up animation, no randomising) |
| SpiderQueen | 0x2ad374 | entry 11, loop | sets 4–6, 0xc–0x11, 0x15 | no | yes: `generateMonster` in NITBON2 (1 call) |
| Vampire | 0x2b6ae0 | entry 15 (`idle1`), loop | sets 3, 4, 5 | no | placed |
| VampireLord | 0x2b7874 | entry 5 (`idle1`), loop | sets 4, 8, 9, 0xc–0xf, 0x12, 0x14 | no | placed |
| NPC | 0x29de74, 0x29e194, 0x29e3a0 | idle animation named by a property, loop | none (no NPC function calls 0x118378) | no | placed, restored from level state, or cutscene actors (the cutscene code reseeds before each actor, 0x19af20) |
| AutoProp / AutoDoor | 0x23c95c | prop animation, loop | none — except a prop whose type starts with `pipepistona`: `AutoProp_ctor` 0x23c44c then writes four event slots into this same animation with inline stores (0.25 s and 1.85 s mask 1, 1.0 s and 2.6 s mask 2), and its run function switches the damage window on them (FINDINGS D27, D30; `docs/monsters-2.md` M5). Added in the second correction pass; the scan behind this table followed only callers of `creature_setDefEntryParams` | no | placed |
| UserParamProp | 0x157388 | prop animation, loop | none | no | placed |
| PoisonProjectile | 0x2b1620 | projectile animation, loop | none | no | yes, always; its run function discards the result of the animation step and asks for no root motion (0x2b176c) |
| world scenery | 0x188004 | scenery animation | — | — | draw code, per machine by nature |

For the instances that are created in mid-play the phase does differ per machine, and what
it reaches is the pose and the timing of sound cues. None of these classes' run or
set-state functions reads a track time, and only `VampireLord_run` asks the model for a
sample point (for an effect). The animation flag word they test (+0x11a) is the union of
track flags and does not depend on phase. **Observed** by a scan of the named functions of
each class; unnamed helpers in their ranges were not read.

A path critter's position does follow its root motion (state 0x16 adds the root velocity
to the position, 0x255008), but Critters are created with the dead flag 0x8, their
take-damage function is empty (0x255c54), and the only shared thing a Critter can do — run
its `deathScript` when a player steps on it — is used by `Bullfrog` and two clockwork
props, none of which has a path.

### Verdict

Not real.

- **Players:** nothing to avoid. **Testers:** nothing specific.

---

## Patch proposals

All **untested**. One word each. "Original" was read from the executable.

| ID | Address | Original | New | What it changes | What could go wrong | Who must apply it |
|---|---|---|---|---|---|---|
| P1 | 0x1375dc | a0408f2a | a0408f28 | The launch code's store of 0 goes to `g_cardXferLatch` (0x4f8f28) instead of 0x4f8f2a, so a latch left stuck by an earlier failed save (section 4c) is cleared when a net game is launched | 0x4f8f2a is no longer zeroed there. Its only writer in the program is this store and its only reader is `save_clearBuffer` (checked with the unlimited scan and the decompile), so it stays 0 from boot. Does nothing for a save that fails during the net game itself | Only useful on a machine that had a failed save; harmless everywhere, so everyone can apply it |
| P2 | 0x28da74 | 54400069 | 00000000 | `Savepoint_interactPrompt` no longer returns "nothing" while this machine's card is busy, so a use-button press at a save point sets the active player on every machine (section 4b). The branch was "likely", so its delay slot (clear the return register) now always runs, which is harmless before the call that follows | The prompt text can appear on a machine whose own card screen is open. `Savepoint_interact` keeps its own busy test, so no second dialog opens. Offline behaviour changes the same way | Each machine fixes its own simulation; needed on every machine to remove the difference, harmless when mixed |
| P3 | 0x1d91e0 | 2a620002 | 2a620001 | The checksum comparison looks at the live-record value only, not the save-buffer value | A tampered or stale save buffer is no longer noticed; nothing in the simulation reads that comparison | Every player: an unpatched machine still drops on the second value |
| P4 | 0x1d91d4 | 0c04f79a | 00000000 | A checksum mismatch still sets the on-screen flag but no longer drops the player (alternative to P3, not both needed) | A real divergence in gold, experience or equipment then continues until the position hash notices, and each machine keeps handing its own version of the characters to the lobby | Every player, for the same reason |
| P5 | 0x217448 | a2220000 | 00000000 | `g_debugCheats` is never set, whatever is on the card | Loses the debug menu and cheat for anyone who wants them offline | Only a machine that has the file |

No patch is proposed for candidates 2, 3, 5, 6 and 8 (nothing to fix) or for the message-5
address (a check would need more than one word).

## Ranking

How likely an ordinary co-operative session is to be hit, most likely first.

| Rank | Item | Needs | Likelihood |
|---|---|---|---|
| 1 | 4b Savepoint prompt | memory-card characters; one machine with a card screen open (usually its own save dialog) while another player uses a save point; then a script not started by a trigger or an interaction that reads the active player before anything rewrites it | the first two steps are everyday, the third is rare. Low |
| 2 | 4c failed card write | a memory-card error during a save (in this game or earlier in the same boot) that the player does not repeat until it works | very low to meet; once met, a break at the next return to an earlier plane or the next jump-gate use is close to certain |
| 3 | 7 `debug.sht` | the file on one player's card | none for normal players; certain within minutes for a machine that has it |
| 4 | 1 checksum exchange | all-lobby-character game and an existing divergence in a covered field | does not start a desync; turns one into a dropped player. False failures: not expected |
| 5 | 3 medal dialog residue | a card operation starting on the medal player's machine during the result dialog | very low |
| 6 | 5 JumpGate | a gate with `hurt` | none with the shipped levels |
| 7 | 2 shops, 6 seed step / item loader, 8 animation phase, 4a address, 7 options menu | — | none found |

## Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| B1 | The character checksum exchange runs only when the game was launched from the lobby and every player's character kind (record +0x4c1c, low 5 bits) is 2; kind 2 is given only by character creation inside the lobby and by the launch code | Observed | 0x1ec5d8, 0x1e2258, 0x2285cc, 0x137400 |
| B2 | Every 240 ticks each machine compares, per player, a checksum of the live record and of that player's block in its own save buffer with the pair the owner sent; a difference sets a flag and drops that player on this machine only | Observed | 0x1e3e88, 0x1de46c, 0x1d90a4–0x1d91d4, 0x13de68 |
| B3 | In such a game the memory-card save screen cannot be opened (script `saveGame` and the Savepoint prompt both refuse), so the save-buffer rewrite of audio-save.md A1 cannot coincide with a comparison | Observed | 0x146c04, 0x28da7c |
| B4 | The comparison needs one message per original player; after any player has left it is never made again | Inferred | 0x1d90f4; writers of 0x4d8ae0 (set-up code and `save_load`) |
| B5 | Shop stock is generated with the cosmetic seed equal to the shared seed: nothing that runs a per-machine number of times between 0x1e59c4 and 0x3230c4 draws from it | Inferred from Observed call paths | section 2 |
| B6 | Animation event bits are assigned only by 59 monster constructors (`creature_setDefEntryParams`); no animation file carries any. None of the constructors that randomise a start time puts events on the randomised entry. **Corrected in the second correction pass:** a few classes also write event slots with inline stores (`docs/formats/anim-audio.md` 2.7), and one of them, `AutoProp_ctor` for `pipepistona` props, does put events on the loop it randomises (0x23c44c; FINDINGS D27, D30) | Observed | 0x118378; disc scan |
| B7 | No jump gate on the disc has `hurt` or `destination`; no Savepoint has `action` | Observed | disc scan; 0x27c848, 0x14dcc8 |
| B8 | The blood option can only be 0 or 1 from the menu and the gib lifetime bit is set for any value below 2; damage numbers and gib creation ignore their options in a net game | Observed | 0x1a01d0, 0x2019e0, 0x1ea998, 0x1113fc, 0x1b31f4 |
| B9 | `Savepoint_interactPrompt` returns "nothing" while this machine's card is busy, so `Player_interact` neither sets the script active player nor calls the interact there | Observed | 0x28da6c, 0x1b2b70 |
| B10 | 0x4f8f28 is a "card load or save in progress" latch: set when a slot is chosen in the load or save screen, cleared when the loaded level has been entered or the "saved" box closes. While it is 1 the act-change clean-up, the jump-gate list reset and the camera reset are skipped on that machine. A save that ends in the card-error state does not clear it, and neither does a net launch | Observed | 0x2195a8, 0x218ba4, 0x218c18; 0x219810, 0x219884, 0x219a18, 0x2190d0; 0x320fb4, 0x27db10, 0x322dc4 |
| B11 | A machine whose latch is stuck (B10) goes out of sync at a later act change: it keeps quest variables, stored level states, flagged items and jump-gate destinations that the others clear | Inferred | section 4c; test given there |
| B12 | The launch handshake copies records, the host's difficulty, mode, kill limit and start level, and each player's button configuration; no options-menu value | Observed | 0x136ffc–0x137658 |

## Corrections to earlier documents (not edited — reported)

- **audio-save.md A1, ui.md P9.** The exchange is not always on (B1). Its first three
  bullets (card save, failed write, reload during the window) cannot occur while it is on
  (B3). The autosave bullet stands, with the gate analysed in section 1. The "type value
  of 2" is the lobby-stored character kind.
- **ui.md P1.** The Unknown is answered: `drawWorld` cannot reach its cosmetic-seed users
  during the load, because pieces are not drawn (0x44f054) and the scenery table is empty.
- **ui.md P4.** `player_checksum` does not cover +0xed, +0xee or +0x4a58.
- **ui.md, open question on `playerAdjustStat`.** All 27 script calls pass slot −1 (direct
  path); the message path is never used by a script.
- **ui.md, game-message table.** Messages 7 and 11 are sent only from the pause menu's
  level-warp list (0x18dd5c, 0x18dd70), whose menu entry is hidden unless `g_debugCheats`
  is set. The normal pause menu (table 0x44f3b8) has no save entry; the comparison with
  `menu_savegame` at 0x18d92c can never match.
- **mainloop.md P4.** The inputs cannot differ (section 6a).
- **mainloop.md, level change step 6.** The flag 0x4f8f28 that skips the act-change block
  is the card load/save latch of section 4c: transient in normal use, stuck after a save
  that ends in the card-error state.
- **Tool caveat for every area document.** `tools/gxref.py` misses accesses whose `lui` is
  more than 64 instructions back. "No writer", "only writer" and "only reader" statements
  that rest on it alone should be rechecked for globals used in long functions.
- **startup.md, per-machine item 1.** No flow leaves `hud.lmp` loaded on one peer only
  (section 6b).
- **objects.md O2 and FINDINGS D21.** Gib lifetime does not follow the menu option: the
  test is "below 2" and the menu stores 0 or 1.
- **engine.md P3, P4.** P3 applies only to placed path critters; P4's "harmless only if
  those animations carry no events" is answered: they carry none (B6).
- **monsters.md 7.1.** The consequence is unreachable with the shipped levels (B7).
  **7.6:** no Savepoint has an `action`; `Savepoint_run` clears +0x84 from the card state
  only when that state is 0, not when it is idle (−1).
- **script.md, "Active player".** Not every writer is unconditional simulation code: the
  `Player_interact` write depends on slot 13, and the Savepoint's slot 13 reads local card
  state (B9).
- **names.tsv `save_game`.** Its callers are script `saveCheckPoint` (0x142a5c), the save
  daemon and `Savepoint_run`; script `saveGame` calls `memcard_requestSave`.
- **symbols/gameplay.tsv `game_sendCharacterToLobby`.** 0x3278f0 packs a record and passes it to
  the lobby library (`lobby_sendCharacter`).
- **FORMATS.md, `objects.ob`.** Layout used for the scans here: `u32 count; u32
  stringTable`; then per object `u32 className; u16 size; u16 angle; float x, y, z;` and
  `(size − 20) / 4` property-string offsets, a zero word ending the list. Offsets are
  relative to the string table.

## Not done

- Nothing was run. 4b, 4c and the checksum outcomes are chains of Observed steps with an
  Inferred end.
- Whether card operations can still be pending at the moment a save slot is chosen. If
  they can, `memcard_abort` (called by `net_closeLocalMenus`) could close the save screen
  after the latch is set and before the write flag is, which would be a second way to
  leave the latch stuck.
- The reach searches follow direct calls only. Virtual calls and script built-ins run at
  level entry were not followed, except that the four store levels' scripts were searched
  for camera shake.
- How a lobby-stored character is fetched and written back (0x22d50c, the lobby library
  calls) was not read; "stored by the lobby service" is Inferred.
- The setter of `g_cardRequestsOff` (0x88d3c8) and the exact conditions under which the
  camera returns to follow mode after a dialog were not read.
- Whether a config file can carry a blood value of 2 or more.
- The option at 0x4fdcc8 (in the config file, in neither menu table, read by the dialog
  tasks) belongs to audio-save.md A2 and was not analysed.
- The resource tables of FireFly and SpiderQueen were not located; their rows in section 8
  rest on the constructor's event calls and the disc-wide scan.
- Unnamed helper functions inside the monster classes of section 8 were not read.
- The pending-level cancel that reads `memcard_isBusy` (mainloop.md P1) is another reader
  of local card state; it was not part of this work.
