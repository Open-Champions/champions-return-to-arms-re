# Findings ledger — Champions: Return to Arms (SLUS-20973 v2.00)

Each row says what kind of claim it is. "Observed" = read directly from the bytes at the
address given. "Inferred" = follows from observations but not seen happening. "Unknown" =
not established; the note says what would settle it. Nothing here was observed on a
running game.

Paths under `scripts/`, `decomp/` and `extracted/` are files you generate locally from your
own disc with the tools in this repository; they are not part of it.

## Evil-path arena desync

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| D1 | "… IS OUT OF SYNC!" is raised when a peer's per-frame hash (shared seed 0x404464 + int player positions) differs from ours for the same frame | Observed | 0x13af44–0x13b118, HUD 0x1dbd5c |
| D2 | The arena level is DRUNARE; its script calls getv, cutScene, postAction, reapEnemies and never getEvil | Observed | script.scr decompiled with tools/scr.py |
| D3 | Objects UndeadKnight1–4 are class Horsemen (no mount) and cast player skills 4, 7, 87, 11 (DiseaseBolt, FireStorm, TagarsInsects, SummonSkeleton) | Observed | factory 0x15b804–0x15b900, 0x272a50–0x272c78, skill table 0x41b170 |
| D4 | Quest variables are not networked; a fresh net launch clears them and zeroes the save buffer on every machine | Observed | 0x1e0b40, 0x1375c4–0x1375cc, no setv in message handlers 0x1d8cf0–0x1d9250 |
| D5 | The pathfinder is budgeted by hardware timer T0, but net_frameLoop follows it with a blocking pass every frame, so results land on the same frame everywhere | Observed | 0x184de4–0x184df8, 0x184324, 0x13af3c |
| D6 | In a net game, while a cutscene is active, object activity is decided by distance to the camera focus instead of to the players | Observed | 0x1e4db4–0x1e4ddc, 0x14db28–0x14dba0 |
| D7 | During a cutscene the camera focus is the cutscene camera's, the same on every machine | Inferred | cut_runFrame 0x199d58–0x199d60 is the last camera writer each frame; not checked against every draw-phase camera writer |
| D8 | During a dialog line, the speaking creature's animation track times are nudged ±0.1 per frame toward the local audio stream position, with no network-mode check | Observed | 0x199444–0x1995c8, speaker chosen at 0x196a1c–0x196a68, audio position via IOP RPC 0x216480 |
| D9 | Only 7 of the 63 cutscenes on the disc have a speaking creature; the first one on the evil path is DRUNARE's bossdefeated (speaker "Rallos") | Observed | scan of every .cut/.dbin on the disc |
| D10 | D8 changes the sync hash and is the cause of the arena desync | Unknown | Needs two running copies: play the arena ending with and without patches/SLUS-20973_4028A55F.pnach |
| D11 | reapEnemies deletes objects directly and three of its type tests can never be true | Observed | 0x1453e4–0x145590, type names P6PhProp / P4Prop / P8ItemProp |
| D12 | The creature draw function decrements the first non-zero of 16 status counters at creature+0x36c (index 12 is never decremented) whenever the game is not frozen; in a net game "frozen" is only the pause flag Executing it also showed that while counter 12 is non-zero, counters 13–15 are not decremented either. | Observed | 0x10b898–0x10b8d4 inside Creature_draw 0x10b048; game_isFrozen 0x1ebdf8 |
| D13 | How often an object is drawn differs per machine: the draw pass walks only grid cells in the local camera frustum, stops when the render buffer has fewer than 3000 units free, and skips objects matching the exclude mask, which during drawing is 0x200000 — a flag each machine sets only on its own local player | Observed | world_drawObjects 0x14b168 (draw calls 0x14b4f8–0x14b8b0); mask writes 0x139f4c, 0x13b1f0, 0x131e38; flag set 0x13b578 |
| D14 | Simulation code reads those counters: counter 2 gives the player +0.25 melee swing rate (not movement speed — corrected by the movement specification), ×1.5 weapon damage and drains mana; counter 4 gives +0.1 swing rate and ×1.2 damage; counter 7 becomes a creature's slow amount (+0x2fc), which movement and animation read; the damage function reads counter 12 | Observed | 0x1a5ac0, 0x1aa0f0–0x1aa0f8, 0x1b7acc–0x1b7b1c, 0x113614–0x1137d8, 0x1e8c14 |
| D15 | The only code that sets counters 2, 7, 12 or 13 is four ability effect types (0x0e, 0x19, 0x1a, 0x1b) inside Player_run; their animation names ("*_warcry.anm", "spel_cas_repulsion.anm") look inherited from the engine's earlier game. Counters 8, 10 and 11, which Return to Arms code does set, are read only by drawing | Observed | 0x1a71c4; 0x1ac02c → 0x293704; 0x1ac164 → 0x29486c; 0x1abe90; setters 0x27eae8, 0x2940e8–0x2940f8, 0x1e8c9c |
| D16 | Whether any Return to Arms character can trigger those four effects. If one can, D12–D14 desync the game whenever it is used | Unknown | Read a character's ability records (player record +0x4440, 0x68 bytes each, effect type at +0x20) from a memory snapshot |
| D17 | The arena script's delays (300 frames after the fourth knight; after the avatar, a message at 250 and the ending at a count of 1500 — reached after about 875 frames, because the entry queues itself twice from the 250 mark on and so counts at double rate) count a script variable once per simulated frame; getScaledTime multiplies by 60 × 1/60; gamePaused is pause flag, jump-gate flag or cutscene flag. All of it is lockstep state | Observed | scripts/DRUNARE.txt; 0x14412c; 0x14699c; 0x27dd68 |
| D18 | bossdefeated.cut runs 53 s; dialog lines start at 13.4 s and three "everyone wait" keys (27.06, 35.18, 49.57 s) hold the cutscene until every machine's own audio stream has ended and its "done" game message has arrived. The speaker's animation is being nudged (D8) for about 36 s of that | Observed | key dump of extracted/DRUNARE/drunare.lmp/bossdefeated.cut; cut_advance: local audio status 0x199398, "done" message 0x1993b8, peer count 0x1993cc |
| D19 | The speaker's run function cannot reach the sync hash while he is a cutscene actor: in AI state 0 with inert bits set nothing consumes the animation's event bits, root motion or status word, and the level change is already pending in the frame the cutscene ends. So D8 has no route to the hash on the evil path. (Two earlier versions of this row were wrong: one argued from state 0x14, which is the death state.) | Inferred from Observed steps | Zek_run 0x2c2440; 0x10ded0; 0x10a9c0; 0x199f44–0x199f6c; docs/issues/arena-desync.md |
| D20 | newWorld in a net game is refused while the "active player" has a 600-frame cooldown running, and otherwise starts that cooldown. The active player is written by trigger volumes, interact, NPC talk, setBestActivePlayer and the dialog-tree reset (dialog_free 0x22f99c). The gate is skipped when the script runs as a post-cutscene action (flag 0x4f8698), which is how the arena's own level change runs, so it does not apply there (docs/script.md) The refusal also requires two or more players to be alive. | Observed | newWorld_netGate 0x143d04; writers 0x1ed15c, 0x1b2b70, 0x116d28, 0x1470fc, 0x22fa34 |
| D21 | How full the object pool is feeds back into the simulation, and it is not the same on every machine. The pool has three fixed size classes (512 × 0x180, 512 × 0x500, 32 × 3000 bytes); a request spills into the next larger class and returns nothing when all are full, in which case the caller silently skips creating the object. Below 300 free blocks a reaper also starts deleting expendable objects. Occupancy includes each machine's prediction copy (one block per machine; the old copy is freed before the new one is made, so they never overlap — 0x13b330, 0x13b540) and gib objects whose lifetime follows a local options setting (0x44fdc0) — from the menu that setting can only be 0 or 1 and the lifetime test is "below 2", so it gives the same lifetime on every machine (B8) | Observed (mechanism); in the arena fight it does not get near them: no arena class makes gib chunks in a net game, the player blood chunk ignores the option, and estimated peak use is an order of magnitude below both limits (Inferred) | pool_new 0x14fdb8; runObjects 0x14b9b0–0x14bb18; GutChunk constructors 0x2019e0, 0x201a80, 0x201b3c and run 0x1eddf4–0x1ede18; docs/objects.md O1–O2. Settle with a memory snapshot of the class table at 0x403a10 during the arena fight |
| D22 | One of the arena's four knights (variant 3) casts Summon Skeleton whenever the skill's "can use" test passes, ignoring the cooldown the other three variants obey. For a monster that test is "no object named skelightm exists in the world", so the knight re-summons on the first frame its previous skeleton's object is gone. Cazic's arena variant casts nothing. Each summon by a knight also leaks one pool block: the spell object the cast returns is never linked or freed (0x272c70, 0x2e221c) | Observed | Horsemen_run 0x2726a0–0x27271c; SkillSummonSkeleton can-use 0x2e2368 → world_findObjectByName 0x14f498; docs/monsters.md |
| D23 | The summoned skeleton has no corpse phase: its death state queues it for deletion and it is destroyed at the start of the next object pass, on the same frame everywhere. The name lookup the knight uses sees hidden, dead and delete-queued objects alike. Nothing on the path reads per-machine state, so D22 is an amplifier of other desyncs, not a cause | Observed | Skelight_setState 0x2a91b8 (call 0x2a9414); runObjects 0x14b910; name table 0x14bce0, 0x14be58, 0x14bf58 |
| D24 | Cutscenes whose header has flag 8 freeze every creature, players included, for their duration, and the camera-based activity flag (D6) comes from a camera-mode word that every local writer is locked out of during a cutscene. D6 therefore has no per-machine input left that has been found | Observed (freeze); Inferred (no writer) | 0x199024 → 0x19b3c0, 0x199074 → 0x19a554; gameSetObjectVis 0x1e4d48; callers of 0x2072e8 |
| D25 | **None of the candidates on this ledger explains an arena desync that happens on every run.** Each is closed or needs an uncommon event. The one with an observed route from per-machine to shared state inside the fight is G11–G13, and in this level it needs a player who was resurrected (re-made objects run before the monsters that hit them, so a blow can still be pending at the end of the frame), a re-clone on that frame and a party skill that reads the list. Floating-point special cases are not a cause either: a float cause needs machines that do not compute identically and would not be specific to the arena (F9) | Inferred | docs/issues/arena-desync.md, "Ranked list" and "What to record on two machines" |
| D26 | Player damage is dropped for every player while the menu input lockout (0x41b4fc) is non-zero. Closing the inventory or shop sets it to 60 only on the machine that had the menu open, and that can happen inside a frame when the local player dies with a menu open; for the rest of that frame that machine alone ignores damage to players The same word also gates the per-tick weapon recompute and interact in `Player_run` (0x1a5ba8) | Observed (each step); effect Inferred | Player_takeDamage 0x1b53d4; 0x1c52dc, 0x1d0b48; net_closeLocalMenus from 0x1b351c |
| D27 | Piston traps (props whose lump name starts `pipepistona`) switch their damage window on animation event bits of a loop whose starting phase comes from the per-machine cosmetic seed | Observed; which levels use them is Unknown | 0x23c95c; 0x23cc70–0x23ce10 |
| D28 | The CloudGiant king's AI decides whether to conjure a new bolt by testing a visual beam handle. The beam table is also filled by camera-gated effect code, so a beam that fails to be created on one machine changes that machine's choice | Observed (the read); divergence Inferred | 0x250930, 0x2519e8; beam_create 0x193088; docs/monsters-2.md |
| D29 | Four more pieces of code act only when something is "near the view", which in a net game means the camera during cutscenes (D6): FireBomb_run draws the shared seed and creates objects behind isNearView(960); Catapult_run, LightningRod_run and AutoProp_run gate scripts, object creation and damage on object activity | Observed | 0x261fd0; 0x24d9e4; 0x295954; 0x23cc0c |
| D30 | Animation phase taken from the per-machine cosmetic seed reaches game state in two cases: a Critter that follows a path (its position, and a squash test that runs its death script) and the piston trap of D27 (its damage frames) | Observed mechanism; whether a shipped level has either is Unknown | 0x2547fc and Critter run state 0x16; 0x23c44c |
| D31 | Every light that is drawn takes two nodes from the global handle-node pool from draw code, and the pool has no empty test. How many nodes are in use therefore differs per machine | Observed; matters only if the pool runs out | 0x2b2ba4, 0x2b30cc, 0x2b33d4, 0x2b36f8, 0x2b3adc; handle_link 0x1a1738 |
| D32 | The tools' own function boundaries cut a function at its first switch-case label, so the earlier automatic scans for per-machine reads (tools/localstate.py) saw only the part of each run function before its state switch. Findings that say "the scan found nothing" for a class need re-running with Ghidra's boundaries | Observed | docs/monsters-2.md section 9; tools/ps2elf.py func_of |

## Local-player prediction (the "ghost")

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| G1 | Each machine keeps a second copy of its own player, made with Player_clone, and re-makes it when more than 30 frames are unconfirmed or a force flag is set. The copy gets flag 0x20000; the real local player gets 0x200000. The shared seed is saved and restored around the clone | Observed | 0x13b204–0x13b5b0; Player_clone 0x11e870 |
| G2 | The clone starts with every handle list empty (attached spells +0x364, +0x360, +0x234, +0x238, +0x2e4, +0x4b8, +0x588), so the copy cannot share or delete the real player's spells | Observed | handle_initEmpty 0x1a1860; Player_clone lines for those offsets |
| G3 | For every unconfirmed frame the prediction loop writes the local input into the lockstep pad slot, points the player table at the copy, runs Player_run on it, and then restores exactly four things: the shared seed, hp, mana and the table pointer | Observed | net_predictLocalPlayer 0x131d88 (loop tail 0x132bf4–0x132cf0) |
| G4 | The local player's own input is passed through the same lossy encode → decode as the wire before the simulation uses it; simulation and prediction each have their own copy of the codec state | Observed | net_frameLoop: encode calls 0x13a29c–0x13a328, decode calls 0x13a84c–0x13a99c, pad_apply 0x13ac84; prediction: 0x132134–0x13285c, 0x132b5c; state at 0x5bf798/0x5bf7e8 and 0x5bf6f8/0x5bf748 |
| G5 | pad_apply rebuilds every pad field from the input record. Its two globals that could differ between machines (0x41bfc0, 0x41c138) are never written anywhere in the program Executing the function showed two exceptions: it leaves pad words +0x00–0x07 and +0x24 alone, and it decrements 0x41bfc0 itself whenever that is non-zero (nothing else writes it). | Observed | 0x174410; brute-force displacement search |
| G6 | Box queries never return the copy; object run and draw loops skip whatever the exclude mask names (0x20000 while simulating, 0x200000 while predicting and drawing) | Observed | 0x14a928 lines for 0x20000 and the mask; iter_begin 0x1a1a48; runObjects 0x14b910 |
| G7 | Player_dtor skips its global side effects while the copy is being torn down | Observed | 0x1a1be4 |
| G8 | In Player_run, potion use and interact are guarded against the copy. The float at player record +0x4a5c is written without a guard, and nothing else reads it | Observed | 0x1b9cb8 first test; player_run.c line 689; 0x1a6200–0x1a629c, 0x1a8054–0x1a8084, 0x1bd904 |
| G9 | Player_processDamage runs for the copy too. In the two PvP modes its tail gives the killer a third of their mana, and may spawn an orb object with no test for the copy; neither is restored. (The score functions it calls, 0x305580 and 0x305650, test for the copy themselves — docs/skills.md) **Later finding (G20): this tail cannot run for the copy, because the clone's attacker handle is always empty.** | Observed | 0x1b2cc0 tail (after 0x1b3504); mode flags 0x4f711c, 0x4f7120 written only by game setup 0x1e15f8, 0x1e1888 |
| G10 | Withdrawn. It claimed PvP games go out of sync when the local copy dies in prediction, through G9; G20 shows that path is unreachable for the copy. What remains is G11, which is not specific to PvP | — | docs/issues/prediction-copy.md |
| G11 | The alive-player list (count 0x4f8420, slots 0x4f8440) is rebuilt at the end of every simulated frame and also on the spot when a player dies. The on-the-spot rebuild has no test for the prediction copy, and prediction does not restore the list afterwards The copy's destructor rebuilds the list again at every re-clone, so the wrong list never outlives one frame (G18). | Observed | tasks_run 0x3226e4 calls game_rebuildAlivePlayers after the run tasks, not before; Player_processDamage 0x1b3504; G3 |
| G12 | The copy can die before the real player does in exactly one way: Player_clone copies the pending-damage fields (+0xc8, +0x2dc, +0x2e0, +0x2e8), so a copy made while a killing blow is still waiting on the real player processes that blow itself during prediction. (An earlier version also named the kill plane under a level; that route does not exist — G15.) In practice the blow must come from something that runs after the victim in the same frame; monsters that woke after the player was linked run before it, so this mostly concerns a player object re-made in the level, for example by Resurrect | Observed (each step); not observed happening | Player_clone 0x11ea84–0x11ec14; Player_run calls Player_processDamage at 0x1a5b90 with no test |
| G13 | After the copy dies in prediction, the next simulated frame on that machine starts with its own player missing from the alive list, while every other machine still lists that player until the real death is processed later in that same frame (G18). About 50 functions read the list, among them Player_run for every player, party-size damage scaling, group spells and script commands. Co-op games would go out of sync around a player's death — which fits a boss arena better than any other finding so far | Inferred | `python3 tools/gxref.py SLUS_209.73 4f8420 4f8440`; found by the player-area pass (docs/player.md); test patch "alive list" in patches/ |
| G14 | Player_clone runs only for the prediction copy; it copies pending damage and leaves the attacker handle empty | Observed | table word 0x511384; the only slot-15 call is 0x13b534; 0x11ea84–0x11ec14, 0x11ebb0 |
| G15 | The kill plane is switched off in all 90 levels (−100000 in every row of the level table), so the copy cannot die from it | Observed | 0x4f7210 + n × 0x30 + 8; 0x1e5de8; 0x1a5b38 |
| G16 | Nothing can damage the copy during prediction: the damage function and the melee hit return for a copy attacker, and nothing calls the copy's take-damage slot. Cloned pending damage is the only way it loses hit points | Observed (each part), Inferred (completeness) | 0x1e828c–0x1e82a4; 0x1b6a98; docs/issues/prediction-copy.md 3.2 |
| G17 | The active run list is last-in-first-out, so a hit is still pending at the end of a frame only when the attacker was linked before the victim, or the hit comes from a script | Observed (list), Inferred (consequence) | 0x14f248, 0x1a1738, 0x1a2340 |
| G18 | After the copy dies, the list is wrong on that machine for the first part of exactly one simulated frame; every re-clone and every end of frame repairs it | Observed | 0x1b3504, 0x3227dc, 0x1a1c68, 0x13b330 |
| G19 | Code that reads the list inside that window and changes shared state: the swing-rate and damage scans for AncestralCall and BattleCry, group heal and buff spells, prop clean-up keyed on the first listed player's height, and the leave-request message handler | Observed (the readers), Inferred (the effect) | 0x1aa018, 0x1b7810, 0x2e9158, 0x154850, 0x156d24, 0x1d8f84 |
| G20 | The PvP tail of Player_processDamage (G9) cannot run for the copy: its attacker handle is always empty | Inferred | 0x11ebb0, 0x1b5728, 0x1166d4 |
| G21 | Simply removing the rebuild at 0x1b3504 (the first test patch tried for G11) would also delay it for real deaths: a party heal in the same frame could then give a corpse hit points, after which save-point revival skips that player. That patch is withdrawn | Inferred from Observed code | 0x2e9158 on; 0x28d564–0x28d590 |
| G22 | SpellCyclone_run starts its animation twice on the real player on every machine except the owner's | Observed; effect on the simulation Unknown | 0x2d1b04, 0x2d1d1c–0x2d1d38, 0x16ceb0 |
| G23 | All 17 call sites of the "real object or copy" helper are classified; apart from G22 and a contained BloodLust case none can change shared state | Observed | net_objOrGhost 0x13e180; docs/issues/prediction-copy.md 3.3 |
| G24 | Fix for G11–G13 without touching real deaths: make Player_clone store zero instead of the copied pending-damage amount, so the copy never loses hit points in prediction. One instruction, per machine, need not match between players | Proposed, untested | 0x11ea8c; test patch "prediction copy starts without pending damage" in patches/ |

## Executed in isolation

Nothing here has run on a console or a full emulator. These rows record what has been
*executed* with `tools/ee_emu.py`, an interpreter that loads the executable and runs one
function at a time on state built by the test, with other calls stubbed. It shows what the
code does on that state, not that the state occurs in a real game.

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| X1 | The interpreter runs the executable's own C library correctly (string and memory functions, sprintf, qsort, the multiply-based generator), which is the basis for trusting it on game functions | Executed | `python3 tools/ee_tests.py SLUS_209.73`, checks x1–x5 |
| X2 | These ledger rows reproduce when the functions are executed: D1 (sync hash), D6, D8, D12, D18, D21 (pool spill and failure), D22, D28, D29, G8, G9, G11–G14 (clone carries pending damage; the copy's death rebuilds the alive list), L3–L5 (pacing rules), L6 (stick: 4 dead frames after a full push) | Executed in isolation | 128 checks, all passing; docs/issues/dynamic-tests.md |
| X3 | Every section in `patches/SLUS-20973_4028A55F.pnach` changes exactly what its description says when the patched function is executed, as do the withdrawn patches and several proposals not yet in the file | Executed in isolation | docs/issues/dynamic-tests.md |
| X4 | The network sign-in step returns "wait" as shipped and "network ready" through the developer shortcut (debug flag plus held button) | Executed in isolation | state 5 of 0x33ed70; docs/online-setup.md |

## Ruled out for the desync

getEvil (D2); differing quest variables on a fresh launch (D4); uninitialised object memory
(pool_new 0x14fdb8 zero-fills); Summon Skeleton's use of the unsynchronised seed (particles
only, 0x2e194c–0x2e1e40); pathfinder timing (D5); party-wipe reload and save points (run in
lockstep, 0x1e7438, 0x28d65c); the arena script's timed delays (D17); the copy sharing or
deleting the real player's spells (G2); the copy being hit by boss projectiles, picked by
Tagar's Insects, burned by FireStorm or tripping the arena's trigger volumes (G6; 0x1509f8,
0x30d998, 0x2d470c, 0x1ecf3c); prediction leaving stale pad state (G5); the hit-flash flag
0x100, which is moved to the copy after every tick but is read only by drawing (0x13af14,
0x10b150); the "*inventoryOnNotify" script hook run when a menu opens (no level defines it); the knights'
own AI function reading camera, local-player or unsynchronised-seed state directly
(Horsemen_run 0x27236c reads none; it uses the per-object generator and the frame counter.
An earlier version of this ledger said the same of Cazic, citing 0x248598 — that function is
Bubo's. Cazic's run is 0x24aaf0; see docs/monsters.md once that area is written up); Summon Skeleton treating a monster caster as a player slot (guarded by the
is-player flag at 0x2e18a4, decompile lines for caster+0x3c8).

## Tools added for this

Ghidra 12.1.4 with ghidra-emotionengine-reloaded 2.1.38 (project in ghidra/proj, decompiles in
decomp/). ghidra_funcs.tsv is Ghidra's function table (7,732 indexed functions; 7,731 successful local decompilations, with `001a3580` still failing). tools/fieldxref.py
lists loads and stores at a struct offset; tools/flagxref.py finds tests of a flag bit;
tools/gxref.py lists reads and writes of a global (until the sync-breakers pass it only looked 64 instructions back from an access for the instruction that built the address and did not follow an address kept in a register, so it under-reported: across the 392 named globals the corrected scan adds a writer function to 151 and a reader function to 146; "only writer" and "no writer" statements made before that are being rechecked); tools/ghostreach.py walks direct calls
from a function and lists the globals each reachable function writes, marking the ones that
never test for the prediction copy. From Player_run it reaches 812 functions (206 virtual
call sites are not followed) writing 563 globals; the player-record writers in that set have
been read, the rest have not.

## Lag

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| L1 | Gameplay traffic is peer to peer, and the game's own netcode sends it as plain UDP datagrams through the PS2 network library. SOE UdpLibrary is used only by the lobby client's player-to-player handshake before play and is torn down when play starts. (Earlier versions of this ledger said gameplay ran over UdpLibrary; that was wrong.) | Observed | sceInetSendTo 0x365830 is called from 0x131b00, net_main 0x132e90, 0x1354f8, 0x135638, 0x135d48, 0x13c078; UdpConnection_Send 0x391430 is called only from 0x32b480–0x32bce8; manager deleted at 0x328770; docs/netlib.md |
| L2 | UdpLibrary's reliable resend (300 ms + 1.25 × ping, capped at 8 s) therefore affects only that pre-game handshake, not play | Observed | constants 0x32a6ac (300), 0x32a6b0 (125), 0x32a6b4 (8000); docs/netlib.md |
| L3 | Nothing is retransmitted on a timer. Every input packet repeats all frames the peer has not acknowledged, and one packet leaves every second call, so a lost packet is repaired by the next one: 2, 4 or 6 calls later for 1, 2 or 3 remote peers | Observed (mechanism); timings Inferred at 60 calls per second | send cycle table 0x4027e8, sender 0x1393b8, docs/netcode.md |
| L4 | A stall is never caught up: each call runs at most as many simulation frames as it samples. Three rules skip a sample: the cap (own input 39 or more ahead of the slowest *reported* simulation frame), equalise (own lead 5 or more above the smallest reported lead for 31 calls in a row), trim (every 62nd call, if all 62 had 3 or more frames ready). Reported values are as old as the last packet | Observed | 0x133548–0x133608, 0x13b790, 0x13b7ac; docs/issues/lag.md section 2 |
| L5 | At full display rate a call stands for one step however long the picture took, so every field a machine misses costs every other machine one frame of lead. After 32 late pictures in a row the display goes to half rate and a call stands for two steps; only below 30 pictures per second does the shortfall continue | Observed (rules), Inferred (consequence) | 0x19e3a8, 0x19da78, 0x19dd48; docs/mainloop.md section 6 |
| L6 | The stick codec is used for the local player too. From rest its predictor moves 4, 8, 16, 32, 64 counts in successive frames and a radial dead zone of 0.32 follows, so a full push gives no movement for at least 3 frames; with the decoder's spring the model gives 4 dead frames, 0.8 on the 7th, at most 0.94, and nothing at all for a flick under 4 frames | Observed (code), Inferred (model numbers) | 0x13c450, 0x13c970, 0x174ce0; `tools/pacing_sim.py stick` |
| L7 | When the sync check fails, the other player's packets are ignored from then on; the simulation stops when their buffered input runs out, and 900 calls later they are dropped. In a two-player game each side ends alone | Inferred from the flag's uses | 0x13bec0–0x13bf30, 0x13b048, 0x133060 |
| L8 | A packet that brings no new frame is used only for the sender's reported lead and simulation frame and to reset the silence counter. Its acknowledgement, sync record and message blocks are not read | Observed | 0x13b7a4–0x13b7a8, 0x13b7f4–0x13b804 |
| L9 | Game messages are attached to an input frame only in a call where two sampled frames are still unsent. At one step per call that needs a call without a send before it, which the cycles 2, 4, 6 provide. A send cycle with a packet in every call would stop all game messages | Observed (rules), Inferred (consequence) | 0x1336c4–0x1336d4, 0x1341c0, table 0x4027e8 |
| L10 | The pacing counters and the peer fields they read are private to `net_main` and the packet receiver. The pacing constants can differ between machines without affecting the simulation. The cap must not be raised (raw relay depth 41, 8-bit header fields) | Observed | gxref on 0x4027a8–0x4027e8; writes 0x13b790, 0x13b7ac; 0x13c370 |
| L11 | Predicted input delay with the original constants: about 5 frames each for two players at 30 ms one way, 9 for three, 13 for four (send cycle 2, 4, 6 calls); 35 frames after any stall of half a second, lasting about 15 s after a one-sided event and 30 s after an outage; 36 frames for as long as a peer runs 10 % slow | Inferred (unvalidated model) | `tools/pacing_sim.py cases --brief`; docs/issues/lag.md section 5 |
| L12 | Predicted effect of the test patches: trim window 12 multiplies steady stalls by 3–6; cap 14 slows three- and four-player games and two-player games beyond about 60 ms; equalise duration 1 bounds the delay after every kind of stall at about 12 frames without slowing any modelled case | Inferred (unvalidated model) | docs/issues/lag.md section 6 |
| L13 | The stick decoder uses floating-point arithmetic, and two plausible models of the console's adder disagree by one count on about 5% of decoded stick bytes. Machines whose floating-point units differ in the last bit — a console against an emulator, or emulators set up differently — could decode different stick values from the same packet, which is an input desync with nothing wrong in the game logic | Inferred | decoder 0x13c970 (float path 0x13cdb0); docs/issues/dynamic-tests.md |

## Sync breakers that do not depend on a level

From `docs/issues/sync-breakers.md`: eight things that could break sync in any level were
checked. Five are not real (shop stock, medal levels, jump gates, the seed step in
`gameMiscSync` and the item loader, animation start phase). Three are real but narrow: the
save-point prompt, a save that ends in a card error, and a `debug.sht` file on one card.

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| B1 | The character checksum exchange runs only when the game was launched from the lobby and every player's character kind (record +0x4c1c, low 5 bits) is 2; kind 2 is given only by character creation inside the lobby and by the launch code | Observed | 0x1ec5d8, 0x1e2258, 0x2285cc, 0x137400 |
| B2 | Every 240 ticks each machine compares, per player, a checksum of the live record and of that player's block in its own save buffer with the pair the owner sent; a difference sets a flag and drops that player on this machine only | Observed | 0x1e3e88, 0x1de46c, 0x1d90a4–0x1d91d4, 0x13de68 |
| B3 | In such a game the memory-card save screen cannot be opened (script `saveGame` and the Savepoint prompt both refuse), so the save-buffer rewrite of audio-save.md A1 cannot coincide with a comparison | Observed | 0x146c04, 0x28da7c |
| B4 | The comparison needs one message per original player; after any player has left it is never made again | Inferred | 0x1d90f4; writers of 0x4d8ae0 (set-up code and `save_load`) |
| B5 | Shop stock is generated with the cosmetic seed equal to the shared seed: nothing that runs a per-machine number of times between 0x1e59c4 and 0x3230c4 draws from it | Inferred from Observed call paths | section 2 |
| B6 | Animation event bits are assigned only by 59 monster constructors (`creature_setDefEntryParams`); no animation file carries any. None of the constructors that randomise a start time puts events on the randomised entry | Observed | 0x118378; disc scan |
| B7 | No jump gate on the disc has `hurt` or `destination`; no Savepoint has `action` | Observed | disc scan; 0x27c848, 0x14dcc8 |
| B8 | The blood option can only be 0 or 1 from the menu and the gib lifetime bit is set for any value below 2; damage numbers and gib creation ignore their options in a net game | Observed | 0x1a01d0, 0x2019e0, 0x1ea998, 0x1113fc, 0x1b31f4 |
| B9 | `Savepoint_interactPrompt` returns "nothing" while this machine's card is busy, so `Player_interact` neither sets the script active player nor calls the interact there | Observed | 0x28da6c, 0x1b2b70 |
| B10 | 0x4f8f28 is a "card load or save in progress" latch: set when a slot is chosen in the load or save screen, cleared when the loaded level has been entered or the "saved" box closes. While it is 1 the act-change clean-up, the jump-gate list reset and the camera reset are skipped on that machine. A save that ends in the card-error state does not clear it, and neither does a net launch | Observed | 0x2195a8, 0x218ba4, 0x218c18; 0x219810, 0x219884, 0x219a18, 0x2190d0; 0x320fb4, 0x27db10, 0x322dc4 |
| B11 | A machine whose latch is stuck (B10) goes out of sync at a later act change: it keeps quest variables, stored level states, flagged items and jump-gate destinations that the others clear | Inferred | section 4c; test given there |
| B12 | The launch handshake copies records, the host's difficulty, mode, kill limit and start level, and each player's button configuration; no options-menu value | Observed | 0x136ffc–0x137658 |
| B13 | The checksum exchange does not start a desync; it turns an existing difference in a covered field into a dropped player. Two one-word changes that would switch it off (0x1d91e0, 0x1d91d4) are described in the document and are deliberately not in the patch file: no false mismatch was found, so removing the check would only hide real divergence | Inferred | docs/issues/sync-breakers.md sections 1 and "Patch proposals" |

## Kill, experience, loot and pick-up

From `docs/issues/kill-loot-xp.md`. The chain itself is lockstep; two places in it branch on
what one machine's own screen is showing. Neither happens on every run, but both get easier
to hit the larger the input delay is (see Lag: 35 frames after any half-second stall).

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| K1 | `Player_run` skips `Player_interact` while a per-slot word at 0x41b818 is non-zero, with no network test. Only `hud_spellSelect` writes it — HUD draw code that returns for remote slots — while the D-pad is held (quick-spell selector open). A use press already in the input stream when the D-pad goes down therefore interacts on every other machine and not on the owner's. A chest opened that way builds its loot from the shared seed on the other machines only (immediate mismatch); a dropped item is picked up on the other machines only (bags differ silently — the arena case) | Observed (gate, writer); Inferred (window, consequence) | 0x1a5c08–0x1a5c1c; 0x1dd2bc, 0x1dd4b8, 0x1dd4ec, 0x1dd504, 0x1dd5e4; contrast 0x1a6de8, which does test the network mode; chest 0x292a2c; test patch "use button works with the spell selector open" |
| K2 | `Player_usePotion` leaves the bag untouched on the owner's machine when that machine's inventory screen is open and sends a drop message instead; every other machine takes the potion out directly and then also runs the message, which removes one of whatever is in the first cell of the owner's potion list. After a potion press followed by the inventory button within the input delay the machines disagree by one potion for good | Observed (branch); Inferred (window) | 0x1b9fcc–0x1ba050, 0x1ba3ac–0x1ba430; `inventory_dropItem` 0x1c4310; `g_localMenuOpen` set at 0x1c15c8; test patch "potions always leave the bag directly" |
| K3 | The stats page (draw code on the owner's machine) calls `Player_recalcDamage`, which writes the record's attack rating and weapon damage (+0xcc, +0xd0, +0xd4); for a dual wielder the last call is for the off-hand weapon, so the record holds off-hand values until the next per-tick recompute | Observed; effect Inferred small | 0x1d2c38, 0x1d2d30; `Player_recalcDamage` 0x1b7158 |
| K4 | The stats and skill pages and the item list call `player_recalcStats`, which recomputes derived fields of every player's record and object on that machine; `hud_spellSelect` writes record +0x4a74 and +0x4a78. The recompute was found idempotent | Observed; "idempotent" Inferred | 0x1d2e7c, 0x1d5950, 0x1ce530, 0x1dd4f8 |
| K5 | A flying item's landing conversion deletes the flying object even when the allocation of the resting prop failed, so a full pool on one machine loses the item there (adds to D21); flying loot is deleted 120 units below the first alive player (G19) | Observed | `PhProp_run` 0x156c18, 0x156c4c, 0x156d00 |
| K6 | Nothing else in the chain depends on the machine: experience uses only the player count, record levels, record hit points and the last-attacker handle; every loot roll draws the shared seed; gold is taken by touch and items by the use button inside the taker's own `Player_run`, with no message | Observed | 0x111e40–0x1121e8; 0x100d54; 0x157a9c; 0x1b2640, 0x154dbc |
| K7 | A level-up changes the level byte +0x59, both point pools, the maxima and the refill at once on every machine; the attack-rating level +0x58 follows by inventory message 9, sent when the owner opens the level-up screen | Observed | 0x1d3150; 0x1db870; 0x1c1814; 0x1b7158 |
| K8 | When knight variant 3 dies, its set-state sends the summoned skeleton to the death state in the same tick and drops both held weapon parts | Observed | `Horsemen_setState` case 0x14: 0x273278, 0x2732ac |

## Movement

From `docs/spec/movement-camera.md`, which writes player and monster movement, collision and
the camera out for a rebuild.

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| MV1 | `Creature_turnToward` takes the square root of 0.2 at run time on every call, and the truncated and the nearest result differ in the last bit (0x3ee4f92d / 0x3ee4f92e). Two machines whose floating-point square root rounds differently diverge on the first monster turn | Observed (instruction, both values); divergence Inferred; which value a console gives is Unknown | 0x10bbc8 |
| MV2 | `Player_move` zeroes the stick while a dialog is open, and `Player_run` swaps in a zero pad on the same test, with no net-game test. The dialog-open word 0x8e2d60 is written only by the dialog message handler (open on message 0, close on message 3), by task set-up at boot and by `dialog_free` from the level reset, all of which run in lockstep, so the state was not found able to differ | Observed (reads, writer list); "cannot differ" Inferred | 0x1b40c0, 0x1a565c; writers 0x22f72c, 0x22f904, 0x22fa30, 0x230d50 (`python3 tools/gxref.py SLUS_209.73 8e2d60`) |
| MV3 | The contact normal of the terrain sweep is taken from a point one quarter of the travelled distance along the step. The same on every machine; a rebuild must copy it | Observed | 0x186088–0x1860c4 |
| MV4 | A player's facing in a net game uses the 16-bit camera-yaw word of the input record including its bit 0, which is the "camera not following" flag. The camera itself is per machine; only the yaw each machine sends steers its character | Observed | 0x133464–0x133498, 0x13e0f8 |
| MV5 | In a net game a player in action state 3, 4, 10 or 0xc is not passed to any move routine: no gravity, no push-out, no knock-back | Observed | `Player_run` switch 0x1a5e80; knock-back zeroed at 0x115ef4 |
| MV6 | Player run speed is 180 × min(S·stick, S) along the facing with no acceleration, S = 0.861945 offline and 0.75 in a net game, times a record multiplier and the level's `runSpeed`, capped at 1.2; statistics and encumbrance do not change it | Observed | `Player_move` 0x1b4020 |

## Floating point

From `docs/issues/float-divergence.md` and `tools/fp_hazards.py`. Lockstep here depends on
every machine producing the same float bits. Between machines that compute identically no
diverging site was found; between machines that do not, input decoding itself diverges.

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| F1 | No float status flag can influence the game: the control register is written once and never read, and there is no double-precision or multiply-add instruction | Observed | 0x14fb98; raw scan of `.text` |
| F2 | The executable has 368 `div.s` (302 not shown safe by the scan), 128 `rsqrt.s`, 172 `sqrt.s` (9 not plainly non-negative) and 1,462 `cvt.w.s` | Observed | `python3 -I -B tools/fp_hazards.py` |
| F3 | In the arena fight three computations divide by zero: the FireStorm light (constructor, and the first 30 frames of each storm) and the insects' speed on the arrival frame. The first two feed a light record only, the third is overwritten before use | Observed; "light record only" Inferred | 0x2d429c, 0x2d4854, 0x2d48a8; 0x30cee8, 0x30cf40, 0x30d050 |
| F4 | A player with slow byte 60 divides by zero in the cast and melee states; 60 is reachable only through status counter 7 (D16). The outcome is the same on console and emulator as far as known | Observed; reachability is D16 | 0x1a81a0–0x1a81f8, 0x1aa178–0x1aa1b4; 0x113738–0x1137d8 |
| F5 | Every machine decodes stick input through a ten-step single-precision spring and truncates the result, so player input itself depends on bit-identical float arithmetic: in a model, rounding to nearest instead of chopping changes about 12% of decoded stick bytes (extends L13) | Observed (code); model figure Inferred | 0x13cdb0–0x13cddc |
| F6 | Skeleton poses are computed by a VU0 microprogram, and `Player_castSkill` places a cast at a point taken from the pose, so the vector unit's rounding and clamping settings reach the simulation too | Observed | 0x16f594, 0x16f5f4, 0x3e5c40; 0x1a42b8 |
| F7 | `sqrt.s` of the constant 0x3e4ccccc is evaluated at run time in four functions; the result is 0x3ee4f92d or 0x3ee4f92e depending on the rounding rule (same fact as MV1) | Observed (sites), computed (values) | 0x10bbc8, 0x10bcc4, 0x10bdcc, 0x13cd24 |
| F8 | The sync hash converts player coordinates with `cvt.w.s`, which truncates and has no mode | Observed | 0x13afe0, 0x13afec, 0x13aff8 |
| F9 | Two PCSX2 installations of the same version with the same EE and VU rounding, division rounding, clamping and FPU/VU fixes agree at every site read. A console against an emulator, different rounding or "full" clamping against the defaults, or an ARM-native build against an x86 one, should be expected to drift in any level, not just the arena | Inferred (emulator behaviour from general knowledge, nothing run) | docs/issues/float-divergence.md, "What an emulator does with this" |
| F10 | Three one-word hardening changes that remove divides by zero (0x14d56c, 0x1a81b4, 0x1aa190) are described in the document and deliberately not in the patch file: they address no known cause and two of them change cast and swing timing for every slowed player, so a mix of patched and unpatched machines would itself desync | Inferred | docs/issues/float-divergence.md, "Patch proposals" |

## Entering the arena

From `docs/issues/arena-entry.md`: the level change into `drunare`, the load, the first
frames and the opening cutscene `knights`, traced tick by tick. No per-machine route to
shared state was found in an ordinary entry, so this phase does not explain the every-run
desync either. The document gives the marks to record on two machines (first tick, cutscene
start, cutscene end, first mismatch) and two bisecting patches that decide which phase the
divergence is in.

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| E1 | A script level change stops every machine after the same frame: the name is written inside a tick, later steps test it first, and the first frame of the new level is the next frame number. No message is involved | Observed | 0x143dd0, 0x1472c4, 0x139fb4 |
| E2 | Between that frame and the next, every shared-seed draw is made by object constructors, `Player1_ctor` and two free-spot loops; no input of those is per machine on a first visit | Inferred from Observed steps | 0x14cd54, 0x158928, 0x3212e0; section 1.4 |
| E3 | `Player1_ctor` fills four spawn slots with a free spot within 36 units of the best start marker and a facing within ± 2000; the session code moves slots 1–3 again by up to 36 and creates the players in slot order | Observed | 0x158928; 0x321294–0x321414 |
| E4 | In `drunare` no start can lie inside either trigger rectangle; the opening cutscene starts on a frame with remainder 2 modulo 15, after a player has walked at least 77 units | Observed (data), Inferred (remainder) | `objects.ob`; 0x1ecdf4, 0x14f330 |
| E5 | `cut_start` restarts the per-machine frame warm-up counter inside a tick, and `cut_runFrame` does so again at the end; no reader of the counter inside a net tick changes shared state. `cut_evalCamera` keeps one latch and is otherwise a function of the clock | Observed | 0x19b514, 0x199f44; `gxref` 0x506048; 0x44fd00 |
| E6 | After a level load the first prediction copy is made 1–31 ticks in, on a per-machine tick. The copy is on no run list, so a flag-8 cutscene neither freezes nor unfreezes it; clones made during the cutscene inherit the freeze and keep it up to 30 ticks after the end | Observed | 0x13dcd0, 0x13b1e8; 0x14a7c8; 0x1a55a0 |
| E7 | In a net game players ignore damage for 30 of their own run ticks after every level load and 60 after every cutscene | Observed | 0x1e61c0, 0x1bfaf8, 0x1a5330, 0x1b5438 |
| E8 | In this level a machine whose autosave gate is shut from the first tick to the cutscene start never takes the entry snapshot (the cutscene holds the camera mode and its post action sets the save inhibit) | Inferred from Observed pieces | 0x2188a8; scripts/DRUNARE.txt |
| E9 | Closing a per-player notice box calls `script_runPostAction` from a draw task with no network test; the full-screen help box's path has the test | Observed | 0x1dd1f0; 0x1dcf58 |
| E10 | The post-action name is not cleared by level teardown; `game_loadLevel` runs a left-over one in the new level's script | Observed | 0x1e60b8; writers of 0x86fa80 |
| E11 | Bit 31 of the creature flag word and the boss-meter globals are set from the local alive list; nothing else reads the bit | Observed | 0x113960–0x113ad8 |
| E12 | The main loop resets the local camera at every level change unless the card latch is set; in a net game the transition flag is cleared by the first camera update of the load warm-up loop | Observed | 0x322dfc; 0x204fb0; 0x2065e8–0x2065f4 |
| E13 | In `knights` the sync hash cannot change between the tick after it starts and the tick it ends, apart from a stuck actor's teleport and the 1800-frame seed step of lobby games | Inferred | section 3.5 |
| E14 | After a load a machine waits for one packet from every peer for at most about 900 calls; a peer's silence counter keeps running meanwhile and starts a kick above 900. A much slower loader is dropped, not desynchronised | Observed (constants), Inferred (outcome) | 0x323014–0x32305c; 0x134408–0x134448; 0x133060 |
| E15 | Every level entry applies a pending character selection (flag 0x4fbbd8) by re-creating that slot's character; whether a net launch can start with the flag set on one machine is not established | Observed (code), Unknown (reachability) | 0x321024; 0x2247ec |

## Skills

From the skill specifications `docs/spec/skills-01-34.md` (rows SA) and
`docs/spec/skills-69-101.md` (rows SC), which write each skill out for a rebuild. No patch is
proposed for any of these: SA1–SA3 need the stale-pointer condition reproduced first, and the
rule quirks should be copied by a rebuild, not repaired.

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| SA1 | `SpellBlindingLight` keeps its caster as a plain pointer and passes it to `damage_apply` as the attacker every 30 frames for up to s2 seconds. If the caster's object is destroyed meanwhile (a player object is rebuilt on respawn and on a level change) the pointer is stale; what `damage_apply` then reads depends on what the pool put there, and pool contents are not identical between machines (the prediction copy and gore-dependent objects are per-machine allocations) | Observed pointer; consequence Inferred | store 0x2f4474 (+0x1c), use 0x2f4538 |
| SA2 | `HolyBolt` (Dismiss Undead) keeps its homing target as a plain pointer and reads its position and flags every frame; it is cleared only when the target is flagged dead, not when the object is deleted | Observed; consequence Inferred | constructor 0x2f5248 (+0x64), run 0x2f57b0 |
| SA3 | `SpellShieldBash` keeps the creature it turns the player toward as a plain pointer for the length of the bash (about a second) | Observed; consequence Inferred | constructor 0x2face4 (+0x24), run 0x2fae80 |
| SA4 | The elemental entries of `damage_apply` take `draw rem (v2 − v1 + 1)` with a signed machine divide and no zero test. Cone of Fire passes v2 < v1 always, and v2 = v1 − 1 (divisor 0) when its statistic 0 is 4–7, which a monster caster gets at levels 2 and 3. The result of a divide by zero is processor-defined; a rebuild or another emulator that differs from the console here computes a different damage | Observed arithmetic; console result Inferred | 0x1e990c (`div`), caller 0x2f02fc |
| SA5 | The Critical Hit aura walks the all-players alive list, so it inherits G11/G13: on a frame where one machine's list lacks its own player, the aura owner is skipped there, the chance differs, and the shared critical-hit draw is made on one machine and not the other | Inferred from G11 | `SkillCriticalHit_critBonusFor` 0x2e76c4 |
| SC1 | Tagar's Insects, the skill the arena's third knight casts, reads nothing per-machine. Its outcome depends on the shared generator, on the spell's own generator (including the particle loops between two wander draws) and on a single-precision clock | Observed | 0x30c708–0x30dc30, section 87 |
| SC2 | Five skills in ids 69–101 take a gameplay decision from the spell's own generator, in a stream shared with particle draws (ids 70, 77, 87, 88, 101); two more let an object's own generator decide how many shared draws follow (80, 100) | Observed | 0x2fddf0, 0x302adc (in 0x301a34), 0x30d0ac, 0x30e6f0, 0x31bcd0; 0x30b428, 0x31b25c |
| SC3 | The decoration interval of Lightning Strike and Pus Storm is `20 − level / 2` and is used as a divisor with no zero test; it is 0 at skill level 40–41 and negative above. A monster's skill level is trunc(monster level × 0.3), which reaches 40 at monster level 134 | Observed (code); reachability Inferred from the monster-level range in `docs/data-tables.md` §5 | 0x31a920, 0x31b5ac, 0x30aaa8 |
| SC4 | Frost Armor strikes back with `trunc(damage − factor)` cold damage, the factor being a number between 0 and 1: nearly the whole incoming hit, not the absorbed part | Observed | 0x318364 |
| SC5 | Pus Storm takes its damage from the player table for every caster; the dark elf's storm hits with 85 + 5 per level | Observed | 0x30ab54–0x30ab74 (slot 8, called with no test of the caster) |
| SC6 | `Player_recalcDamage` raises a thrown weapon's maximum by fraction × the already-raised minimum; Battle Mage replaces the weapon range by a fraction that is 0 at rank 0 | Observed | 0x1b7478–0x1b7488; 0x314a78 with slot 10's level-0 rule |
| SC7 | Disease Blade's two "is the old enchantment weaker" tests compare the old disease *value* with a frame count; with the aura's limit of 31 the ally buff is on for 31 frames in every 60 from rank 17 | Observed (code); effect Inferred | 0x318ca8, 0x318d4c; run 0x319068 |
| SC8 | `SpellRaiseArmy`'s raise step reads `caster + 0x3c8` without an is-player test | Observed | 0x313d74 |

## What "source" the disc contains

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| S1 | No C/C++ source or headers are on the disc; 16,370 packed files are audio, animation, textures, models, worlds and data | Observed | inventory of all 940 lumps by extension |
| S2 | The 120 level scripts are compiled bytecode that keeps entry-point names, imported built-in names and 8,829 source line markers; all 51 opcodes they use are decoded | Observed | scripts/*.txt (27,752 lines, no undecoded opcode), interpreter 0x13ecf8 |
| S3 | The engine survives only as traces in the ELF: 8 engine file names (lump.cc, sound.cc, particle.cc, object.cc, mem.cc, game.cc, engine.cc, core.cc), 403 class names, 191 built-in names | Observed | strings_all.txt, rtti_classes.txt, table 0x403370 |
| S4 | Two third-party components are identifiable by file name and assertion text: SOE UdpLibrary (5 .cpp, 2 .h) and LibTomCrypt AES (aes.c, aes_tab.c) | Observed | strings_all.txt |
| S5 | STRIFE.GOB carries a stray build file reading "include /usr/local/bin/makeworld.mak" | Observed | STRIFE.GOB/makefile.uni |
