# Up to eight players, and enemies that scale with them (native build)

Started 2026-10-26. The owner: "Should be up to 8 players and enemies should scale with it." The decision that
frames everything here: **a room of five to eight is a room option of the Remastered / Hardcore kind only. A Classic
room, and every room of one to four, stays what it is today, tick for tick and byte for byte** (the rig comparison
of `native-app.md` 12 and 13 against `rta_app_orig`, and the room runs of `native-rendezvous.md` section 6).

Three parts:

- **A. The map**: everything in the game and in our own stack that is sized for four players, with the address, the
  size, how many functions touch it, and how it grows to eight. **Done (Read, and counted from the translation).**
- **B. Enemy scaling**: what the game does with the player count today, and a curve for one to eight players in
  Hardcore mode (hit points, damage, experience, poise, elites, more creatures). **Built and Ran** for parties of
  one to four, and with the party size forced to five to eight on the copies of a room of two (section B.5).
- **C. Five to eight in the lockstep core and net2**: designed in A.9; the first step (the tables move) built and
  Ran offline, the rest not this round (section C).

Every statement says **Read** (from the decompile, the translation or the docs it cites), **Counted** (a scan of the
local translation, numbers below) or **Ran**.

## STATE (rewritten at every step)

**2026-10-26.** A written (with a census of the translation: A.0). B built (`tools/recomp/app/partyscale.{h,cpp}`,
`partyscale_hle.cpp`, one line in `app/hle-app.txt`, small hunks in `soulscombat.cpp`, `app/build.py`,
`godot/build.py`) and **Ran**: offline (one and eight), and rooms of two and three copies in step - 4,836 ticks through
valor > drunare with the numbers for eight on two copies, 4,918 with three copies on the game's own count, 11,439
through 17 wipes and reloads with three copies on the numbers for eight (B.5). C not started: the order of work is
A.9: its first step (the tables sized for four moved at run time) is built and proven offline - the game plays tick
for tick the same with every table at its new place and the old places poisoned - while a room's launch with the
tables moved does not complete yet (C). Nothing committed (the orchestrator merges).

---

## A. Everything sized for four

### A.0 How the census was made

A scratch scan of the local translation of the unpatched game (`local/recomp-out/gen`, the C++ that
`tools/recomp/recomp.py` writes; nothing of it is tracked): per function, every constant address built from a `lui`
value and an offset, and every literal stride. It finds direct uses only - an address handed in a register from
elsewhere is not seen - so the counts are a floor for the tables and a ceiling for "a literal 4 in the same
function" (that test also matches unrelated fours). **Counted, 2026-10-26:**

| What | Functions |
|---|---|
| `g_numPlayers` 0x4d8ae0 read or written | 165 |
| `g_players` 0x4d8af0 .. 0x4ebbb0 by a constant address | 262 |
| the player-record stride 0x4c30 as a literal | 342 |
| ... of those with a literal 4 as well (candidates for a loop over four slots) | at most 114 |
| `g_peers` 0x5bf838 .. 0x5d0bb8 by a constant address / the stride 0x44e0 | 25 / 35 (11 with a literal 4) |
| `g_pads` 0x41bfd8 (4 x 0x58) / the stride 0x58 | 51 / 32 (14 with a literal 4) |
| the button tables 0x41b980 .. 0x41ba3f | 7 |
| `g_launchRecs` 0x402b90 (4 x 0x144) | 3 |
| the spawn copy 0x41b51c.. / `g_spawnPos` 0x4f70d0 | 18 / 1 |
| loops whose back-edge test is "below a literal 4" (`slti`/`sltiu` 4 followed by a backward branch) | 330 in 107 functions |
| ... in a function that also uses the player, peer or pad stride: **the review list for hard-coded fours** | 44 functions (below) |

The review list (address, name; a loop over a literal four in a function that indexes a slot table - not every one
of these loops is over players: item slots, elements and the four weapon-enchant spells loop over four things of
their own): 0x112948 `Creature_run`, 0x131b00 `net_sendMsgToPeers`, 0x132e90 `net_main`, 0x137a10 `net_loadModules`,
0x139e88 `net_frameLoop`, 0x13def8 `net_dropAllRemotes` (Read: the four peers, stride 0x44e0, at 0x13df74), 0x173ea8
`pad_init` (the four pads), 0x18cbfc `pauseMenu_isOpen`, 0x1a2f88 `eqcache_release`, 0x1a46c0 `Player_draw`, 0x1ac7a8
`classSkills_init`, 0x1b3900 `Player_regenMana`, 0x1b3b90 `Player_regenHealth`, 0x1b5790 `player_recalcArmor`,
0x1b6458 `player_recalcStats`, 0x1bc560 `Player_tickEnchantTimers`, 0x1bfbc8 `inventory_pollResources`, 0x1c8d38
`itemList_drawItemInfo`, 0x1ceea4, 0x1dc5f4 `hud_flushGold`, 0x1dc708 `hud_drawGold`, 0x1dcb80 `hud_tickGold`,
0x1e08d0 `hud_staticInit`, 0x1f4ad8 `Shooter_run`, 0x204fe0 `Camera_followCollide`, 0x207b5c `Vehicle_dtor`,
0x21f968, 0x221914 `save_build`, 0x221d60 `save_load`, 0x2223d4 `save_packLocalPlayer`, 0x225428
`playerSel_cacheTask`, 0x25f93c `RedDragon_draw`, 0x29b2c4 `MummyKing_draw`, 0x2c8f2c `SpellCharge_run`, the
weapon-enchant spells 0x2e24d8 .. 0x319068 (`SpellLightningWeapons_*`, `SpellFireWeapons_run`, `SpellColdWeapons_*`,
`SkillPoisonWeapons_manaCost`, 0x31646c, `SpellDiseaseBlade_*`). Also `pad_readAll` 0x174a10 (the four pads, stride
0x58, at 0x174cb8) - the raw controllers, which stay four.

The data segments of the executable hold **no pointer into** `g_players`, `g_peers`, `g_pads`, `g_launchRecs`,
`g_savedPlayers`, the button tables, the address and port tables or the spawn table (a scan of every aligned word of
the two writable segments: 41 words fall in those ranges, none of them a pointer - round values such as 0x4e0000
and 0x5c0000 that are floats or halves of other numbers). So moving a table means changing **code** only, and the
pointers the game builds at run time.

### A.1 Players

| Table | Address, size | Indexed by | At eight |
|---|---|---|---|
| `g_numPlayers` | 0x4d8ae0, s32 | - | the count, 1..8 (it is already an int) |
| `g_players` (the player record) | 0x4d8af0, 4 x 0x4c30 | `base + slot x 0x4c30` (262 functions by constant, 342 with the stride) | relocated: 8 x 0x4c30 = 0x26180 bytes |
| `g_savedPlayers` (snapshot with item indices) | 0x879ec0, 4 x 0x4c30 | the same | relocated, 8 x 0x4c30 |
| the 0x2c-byte summary of a new character | 0x4fdb80 | local only | unchanged |
| `g_itemListCells` (inventory and shop copy, 0x23988 per slot) | pointer at 0x4ebbb0 | the local slot only (`net_isLocalSlot`) | unchanged: a heap block, only the local player's is loaded |
| `g_itemPanels` | 0x4f4040, 4 x 0x74 (+0x34 owner slot) | panel per slot | 8 x 0x74 relocated |
| `g_playerDrawPulse`, `g_playerAuraLevel`, `-Color` (int[4][4]), `-FadeRate`, `-Fade`, `-Dir` | 0x4d8a30 .. 0x4d8abf | slot | each to [8] (0x4d8a30 .. 0x4d8b80 at eight: relocated as one block) |
| `g_interactPromptAlpha`, `-Icon` | 0x4d8ac0, 0x4d8ad0, int[4] | slot | [8] |
| `g_playerAuraLightColor` | 0x8659a0, int[4][4] | slot | [8][4] |
| `g_playerDeadCountdown` | 0x4f84a8, s16[4] | slot | [8] |
| `g_spawnPos`, `g_spawnFacing` | 0x4f70d0 Vec3[4], 0x4f8410 s16[4] | slot | [8]; `Player1_ctor` 0x158928 fills **four** spawn points with `world_findFreeSpot` and four angles (a literal 4): a hook fills eight |
| the spawn copy (`level-flow.md` 17) | 0x41b51c flag, 0x41b520 [4] | slot below the count | [8] |
| `g_classStartStats` | 0x4ef400, s32[7][4] | class, statistic | unchanged (the 4 is four statistics, not players) |
| `g_argPlayerClass` | 0x506100, int[4] | offline start from arguments | unchanged (offline is never more than 4) |

**Read** from `symbols/*.tsv`, `docs/player.md`, `docs/level-flow.md`, `docs/hud-dynamic.md`.

### A.2 Input and controls

| Table | Address, size | At eight |
|---|---|---|
| `g_pads` (the lockstep pad per player) | 0x41bfd8, 4 x 0x58 | 8 x 0x58, relocated (51 functions by constant) |
| `g_padSlotMap` | 0x41c140, s8[4] | [8] |
| the button tables `g_btnAttack` .. `g_btnWeaponSwap` (12 tables of u32[4], stride 0x10) | 0x41b980 .. 0x41ba3f | each [8]: relocated as one block of 12 x 0x20; filled per player by the launch (0x137434 on) |
| `g_netCamYaw` | 0x5d0bc0, u16[4] | [8] |
| `g_netInputLock` | 0x5d0bc8, 4 x 12 | 8 x 12 |
| `g_rawPadPrev` | 0x5d0bf8, 4 x 8 | unchanged: the raw local pads (one controller online) |
| `g_spellSelectorHeld`, `-Dir`, `-Alpha` | 0x41b818, 0x4f66b8, 0x86a8d8, int[4] | [8] (written only for the local slot, read by `Player_run` for every slot) |
| `g_hudNoticeTimers`, `-Rows` | 0x41b828, 0x41b8a8, int[4][8] | [8][8] |
| `g_hudHitFlash` | 0x41b930, int[4] | [8] |
| `g_playerNoticeOpen`, `g_noticeButtonReleased` | 0x41b518, 0x86aa90, u8[4] | [8] |
| `g_goldPending`, the gold floaters' slot field | 0x86ace8 int[4]; 0x86a900 8 x 0x24 (+0x20 slot) | [8]; the floaters keep 8 entries (a slot number, not an index) |

### A.3 The lockstep core (`docs/netcode.md`)

| Thing | Today | At eight |
|---|---|---|
| `g_peers` | 0x5bf838, 4 x 0x44e0 (input ring, sync ring, message ring, codec states, flags) | relocated, 8 x 0x44e0 = 0x22700 bytes; `g_localSyncRing` 0x5c10e4 is peer 0's ring + slot offset and moves with it |
| `g_numPeers` | 0x4027c4 | 1..8 |
| per-peer state at launch: +0x44c0 = 1 "for all four" | 0x13768c, a literal 4 | eight |
| `g_netSendCycleTable` | 0x4027e8, s32[4] = 6, 2, 4, 6 by remote count | s32[8]: 2 x remote count (one packet every second call, as now): 14, 2, 4, 6, 8, 10, 12, 14 |
| the input packet's byte 8: low nibble the slot, **high nibble the sender's active mask** (`net_frameLoop2` 0x13b5d0 compares it with its own, 0x13b6ec) | 4 bits of mask | **does not fit**: eight players need an 8-bit mask and 3 bits of slot. A packet of a game of five to eight carries its own type word (0xbd48, unused by the game) with a 16-bit field: slot in bits 0-3, mask in bits 8-15; built and read by native code (A.9), the game's 0xbd3f untouched for one to four |
| the kick request {requester, mask} (0xbd41) | mask in a byte | a byte holds eight: fits |
| `g_netKickAcks` | 0x5d1454, u8[4] | [8] |
| the raw relay (0xbd42) byte 9 = the relayer's slot | fits | fits |
| the sync record and hash: seed + x, y, height of every player object, the loop bounded by `g_numPlayers` (0x13afa0 .. 0x13b010, stride 0x4c30) | fine at any count | fine, with `g_players` relocated |
| a sync record rides in one packet per frame, so with three remote peers each record reaches one of them | | with seven remote peers a frame's record is compared by one machine in seven: still the game's rule; compare coverage falls, nothing breaks |
| send rotation: peer k of n served when phase = k x cycle / n (0x133850) | | the same arithmetic |
| input packet length: frames since the addressee's acknowledgement; the builder's 5008-byte stack buffer, the 1984-byte receive buffer | | per peer as now; nothing grows with the count except how often each peer is served (every 14 calls at eight: its packets carry 7 frames instead of 3; still far below 1984 bytes) |
| the input cap (38 frames), the trim and equalise rules | | unchanged; with seven peers the slowest report lags more (A.10) |
| game message slot bytes (3/0..3/13, 5/x, 7/x: "slot" in a byte; 1: slot in the low nibble, bit 7 on/off) | | all fit eight |
| talk bits 0x503968 (one bit per slot) | | eight bits: fits the word |
| `g_expectedChecksums`, `g_receivedChecksums` | 0x86ab38, 0x86ab58, int[4][2] | [8][2] (only in a lobby game with server characters: never in a net2 room) |

### A.4 The launch handshake (`net_launchTransfer` 0x134c60, `net_launchUpdate` 0x135638)

| Thing | Today | At eight |
|---|---|---|
| count, host, own number | 0x402a37, 0x402a38, 0x402a39 (bytes) | fit |
| the address tables (4 x 4 bytes each) and port tables (4 x u32) | 0x402b3b, 0x402b4b; 0x402b5c, 0x402b6c - **back to back**: an eighth entry of one is the first of the next | relocated together (8 x 4 x 2 + 8 x 4 x 2 = 0x80 bytes). In a net2 room every machine writes them itself (`launch.cpp`: player k is 10.77.0.(k+1):4000) |
| `g_launchRecs` | 0x402b90, 4 x 0x144 (state +0x5c, flags +0x5d, info block +0x68 ..) | relocated, 8 x 0x144 |
| `g_launchRpcBuf` | 0x402b7c, a pointer to a 0x8000-byte buffer | unchanged |
| KEEP ALIVE ACK (type 7) carries the number of others seen ready | | fits |
| HOST FORCE LAUNCH (type 8) carries the mask of players kept; `g_launchKeepMask` 0x5d0bbb is a u8 | | eight bits: fits |
| DATA: each machine sends its character (the 0x4c30-byte record, or the 0x2c summary) to every other in 1300-byte chunks | 3 x 15 chunks at four | 7 x 15 chunks at eight; the 2700-frame failure limit and the 0.75 s / 1.0 s retries stay |
| the end of the launch (0x136ffc on): compacts the player list to the kept mask, installs every player's button configuration (0x41b980 ..), writes address, port and the local flag of each peer, `g_numPeers` | loops over the count, some over a literal 4 (+0x44c0) | the relocated tables, and the literal 4 at 0x13768c |
| `net_launchDraw` 0x13ce68: the "Network Game Launch" screen, one row per player | rows for the count | eight rows do not fit the screen's layout: in a room of five to eight the portal draws the launch (it has every name from the room) and the game's screen is left as it is |

### A.5 Level, camera, picture

| Thing | Today | At eight |
|---|---|---|
| spawn points | `Player1_ctor` 0x158928: four spawn points from the marker with `world_findFreeSpot` (range 36), four angles from one shared draw; `mainloop_loadRequestedWorld` 0x32119c .. 0x3212ec adjusts them for the slots below the count (+8000 facing for slots 1-3); a marker that takes fills all four slots (`level-flow.md` "fills all four") | a native follow-up after `Player1_ctor` (it is a factory entry: the factory wrapper of B already sits in that call) fills slots 4..7 from the same marker with the game's own `world_findFreeSpot`; the +8000 rule extended to slots 1..7 |
| `g_activityCenters` | 0x4039c8, Vec3[4], count 0x403a08 (`gameSetObjectVis` 0x1e4d74 writes, `obj_updateActive` reads): objects run near a player | Vec3[8], relocated; the count byte holds eight |
| the camera's party framing | `Camera_computeTarget`: the **local** alive list (count 0x4f8424, slots 0x4f8430); online one local player, so the party is never framed online | nothing for the lockstep; the spectate cycle after death (`Camera_cycleSpectated`) goes over the slots below the count - eight with the count |
| the game's HUD party frames | `hud_drawPlayerStatus` 0x1d9cd4 per slot, origins x = 12, 478, 167, 323 and caps 180, 605, 333, 447 by slot (`docs/hud-layout.md`): four places across the bottom | the game's HUD draws slots 0..3 as now; slots 4..7 are not drawn by it (its tables have four). The Godot HUD (`tools/godot/project/hud/status.gd`) draws every party frame itself already (`--hud-fake-party N`): its party column takes seven others. The window program without Godot: a compact list of the others (name, health) drawn by the application |
| bars above heads, names, the minimap's blips (`minimap_draw` 0x1e42e0, a loop over the count) | | the relocated tables |
| the player-left text and the out-of-sync notice per peer (0x5c3d0f + slot x 0x44e0) | | moves with `g_peers` |

### A.6 Inside objects (arrays of four in a creature)

The count is also used to index arrays **inside** objects. Found so far (**Read**, `docs/monsters-2.md`):
`MummyKing` keeps a `SpawnMummy` handle per player slot at +0x464 (handle[4]) and a `MummySnake` handle per slot at
+0x480 (handle[4]), and summons "one per player slot below `g_numPlayers`" (states 8 and 9, 0x29c9f8, 0x29ca5c). At
eight it would walk past both arrays into the object's next fields. The rule for a room of five to eight: **such a
creature acts for at most four players** - its functions are run with the count it reads held at 4 (the same
technique as B's `Creature_setStats`, an HLE wrapper), and the party scaling makes up the difference (more hit
points). The 165 functions that read `g_numPlayers` (A.0) are the list to go through for others; the ones in the
creature range (0x100000 .. 0x130000 and the monster classes 0x230000 .. 0x310000) first.

### A.7 Saves

| Thing | Today | At eight |
|---|---|---|
| a save file holds `g_numPlayers` and 4 player blocks of 0x4c3e at +0x320 (`docs/audio-save.md`) | offline party saves | unchanged: offline is never more than four. In a room every machine saves its own character only (`save_packLocalPlayer`): player count 1 |
| `save_load` writes `g_spawnPos` / `g_spawnFacing` per slot | | the relocated tables |

### A.8 Our own stack

| Thing | Where | At eight |
|---|---|---|
| `NET2_PLAYERS 4` | `tools/recomp/net2/session.h` 50 (room members, start description, `net2_direct` players) | 8; every loop in `launch.cpp`, `carrier.cpp`, `session_net.cpp`, `session_mock.cpp` is already bounded by `NET2_PLAYERS` or the count (**Read**: the 17 places found by a search). The Godot extension reads the same header: one rebuild |
| the room limit of the service | `tools/rendezvous/rendezvous.py` 949 (joinable while fewer than 4) and 1322 (refuse the fifth) | the room's own capacity: 8 when the host's room has the eight-player option (and every member's copy has it, fix_words bit below), else 4. The public service keeps 4 until the owner redeploys it |
| the carrier: one route per member, `10.77.0.(k+1):4000` per player | `carrier.cpp`, `launch.cpp` | fits 8 (`Peer peers_[NET2_PLAYERS]`) |
| the relay's datagram header: one byte of the sender's member index (`rendezvous.py` 1569) | | fits |
| the room options and the copy's description (`fix_words`: 0x8000 Hardcore, 0x4000 aiming, 0x2000 Remastered) | | a new bit, **0x1000 "eight-player capable"**; the room refuses a fifth member unless every member has it and the host asked for a room of up to eight |
| the souls block (`soulscombat.h`, 0xE0800): per player at +0x40 + slot x 0x40, +0x200 + slot x 0x40, +0x400 + slot x 0x60, +0x600 + slot x 0x80; header words at +0x300 ..; aiming's block (`fpaim.h` 0xE0E00), the cut-scene block (`cinematic.h` 0xE1C00, +0x20 + slot x 4) | sized for four, laid out back to back | the per-player parts of all three move into one new block of eight (next to B's at 0xE2000), the four-player layouts left as they are for rooms of up to four. Note: today the souls block's attributes part (+0x600 .. +0x7ff, version 4) **overlaps aiming's block at 0xE0E00**; see "Found on the way" |
| the HUDs | `hud/souls.gd`, `sheet.gd` read the souls block by slot | follow the block |
| tick logs and `tools/rig/compare.py` | columns per player for 4 | eight |

### A.9 How it grows: one translation, one switch, Classic untouched

**The rule.** Everything above that moves is moved **at run time**, by one switch set at the launch of a room of
five to eight (`g_party8`), and is exactly the game when the switch is off. So `rta_app` stays one program, and a
Classic or one-to-four room runs the same instructions on the same addresses as today.

1. **Relocatable constants (the translator).** `recomp.py` gets a list of ranges (`app/party8-ranges.txt`: start,
   end, the slot that holds its new base): `g_players`, `g_savedPlayers`, `g_peers`, `g_pads` + `g_padSlotMap`, the
   button tables, the address and port tables, `g_launchRecs`, `g_netCamYaw` .. `g_netInputLock`, `g_netKickAcks`,
   `g_activityCenters`, `g_spawnPos`, `g_spawnFacing`, the spawn copy, `g_itemPanels`, the per-slot HUD and aura
   arrays of A.1/A.2, `g_playerDeadCountdown`, `g_goldPending`. For each `lui`/`addiu` pair whose address falls in a
   range, the fix-set translation emits `addr + g_reloc[k]` instead of `addr`; `g_reloc[k]` is 0 unless the switch
   is on. (The pair is resolved per function as A.0's scan does; a `lui` whose register reaches addresses inside
   **and** outside a range is reported and handled by hand - the end-of-table constants of a loop are the expected
   case: such a loop is bounded by the count, not by an end address, in every function read so far.) The unpatched
   translation (`rta_app_orig`, the rig's) is not touched. Cost with the switch off: one add of a zero per relocated
   access.
2. **Hard-coded fours (the translator).** A list of instruction addresses (`app/party8-sites.txt`) whose immediate 4
   is the slot count (+0x44c0 = 1 for all four at 0x13768c, `Player1_ctor`'s four spawn points, the button-table
   installs, `net_dropAllRemotes`' loop at 0x13df74, and whatever else the review list of A.0 - 44 functions -
   holds) is emitted as `g_slots` (4, or 8 with the switch). Reviewing that list is the larger part of the work;
   each site found is one line in the file.
3. **The switch.** At the end of a launch with more than four players `launch.cpp` (on the game's thread, before
   the first level is loaded, while no object exists that could hold a pointer into the old tables): copies every
   relocated table to its new place (guest memory the game leaves alone: `guestmap.h`; about 0x6f000 bytes at
   eight), sets `g_reloc[k]` and `g_slots`. (Built: C. The move is made at boot instead, C.2.) When the game is over (back at the title screen) it
   copies slots 0..3 back and clears them. A room of up to four never sets it.
4. **The wire for five to eight (native code, HLE wrappers).** `net_sendInputPacket` 0x137d60 and the receiver
   `net_frameLoop2` 0x13b5d0 go on `app/hle-app.txt`: with the switch off they are the originals; with it on, the
   wrapper builds / reads packet type 0xbd48 with a 16-bit slot-and-mask field (A.3) and otherwise the game's own
   codec (the codec functions are called as they are). `g_netSendCycleTable` read through a wrapper of the one
   function that reads it (0x1337cc is in `net_main`: the table itself is relocated with eight entries instead).
5. **Creatures with arrays of four** (A.6): HLE wrappers that hold `g_numPlayers` at 4 while they run.
6. **The HUD and the launch screen** (A.4, A.5): the portal and the Godot HUD draw five to eight; the game's own
   screens draw the first four.
7. **net2**: `NET2_PLAYERS` 8, the room's capacity, the fix_words bit 0x1000, the service's limit by room (A.8).
8. **Hardcore's numbers for eight**: part B is already there (its tables run to eight); the souls, aiming and
   cut-scene blocks get their eight-player layout (A.8).

**Proof of each step, in this order:** (i) with the switch off: the rig comparison three ways and the room runs of
`native-rendezvous.md` 6 unchanged, byte for byte; (ii) the switch on with **four** players: the same room runs in
step (the tables moved, nothing else); (iii) five and six headless copies in one room through a level change, every
pair in step (`n2party.py --players 5|6`); (iv) eight. Six processes at most on this machine for (iii).

### A.10 What eight costs at run time (Inferred, from `docs/netcode.md`)

- Packets: one every second call whatever the count; each peer is served every 14 calls instead of every 6, so a
  lost packet costs up to 233 ms instead of 100 ms before the frames arrive again (netcode "When a packet is lost").
- The input cap: 38 frames minus how far the slowest report lags; with seven peers the slowest report lags about two
  send intervals more. In practice the lead settles higher by a few frames: a little more input delay at eight.
- The sync check sees a frame's record on one machine in seven.
- Every machine still waits for the slowest machine's input every tick: eight players are as fast as the slowest
  connection of the eight.

---

## B. Enemy scaling by party size (built)

### B.1 What the game does (Read: `Creature_setStats` 0x10a620, `docs/data-tables.md` 3.2; Ran: B.5)

With n = `g_numPlayers` at 2 or more and the word 0x4f713c clear:

- hit-point multiplier x (1 + 0.6 (n - 1)) - **before** the hit-point formula `(15.5 + r) x pow(hp x L, 0.85)`, so the
  hit points grow by (1 + 0.6 (n - 1))^0.85: x 1.49, 1.95, 2.40 at two, three, four;
- damage x (1 + 0.15 (n - 1)), not for a boss (rank 2), a creature whose type name is "droid", or one without a type
  name at that moment. **Ran:** creatures whose constructor has not stored a type name before it calls
  `Creature_setStats` (in valor: the butterflies `bflya`/`bflyb` among others) never get the damage step - the game's
  own rule, kept;
- experience x n.

Nothing else depends on the count in the creatures' numbers: no extra creatures, no tougher kinds. (Elsewhere the
count shapes behaviour: `MummyKing` summons one per player, goblins call for help only when alone - A.6 and
`docs/monsters-2.md`.)

### B.2 The curve (`partyscale.h` `Tuning`; every number in percent; index = party size)

| Party | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| hit-point multiplier (`hp`) | 100 | 160 | 220 | 280 | 340 | 400 | 460 | 530 |
| = hit points (^0.85) | x1.00 | x1.49 | x1.95 | x2.40 | x2.83 | x3.25 | x3.66 | x4.12 |
| boss multiplier (`boss_hp`) | 100 | 160 | 220 | 280 | 450 | 600 | 790 | 990 |
| = boss hit points | x1.00 | x1.49 | x1.95 | x2.40 | x3.59 | x4.58 | x5.82 | x7.03 |
| damage (`damage`) | 100 | 115 | 130 | 145 | 155 | 165 | 175 | 185 |
| experience (`exp`) | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 |
| Hardcore poise limit (`poise`) | 100 | 110 | 120 | 135 | 150 | 170 | 190 | 210 |
| elite chance (`elite`) | 2 | 4 | 7 | 10 | 13 | 16 | 20 | 24 |
| one more creature (`extra`) | 0 | 0 | 0 | 10 | 35 | 60 | 80 | 100 |

- **One to four is the game's own** for hit points, damage and experience: a Hardcore room of up to four has the
  game's numbers for every creature that is not an elite (the call is handed to the original unchanged - B.5 counts
  95 of 98 in valor alone). What Hardcore adds there is the elites, the poise and, at four, a few extra creatures.
- **Eight feels like a raid** by three things together: about twice as many ordinary creatures (an extra one beside
  each), each with x4.1 hit points and x1.85 damage, a quarter of them elites (x2.2 hit-point multiplier = x1.95 hit
  points on top, x1.25 damage, the mini-boss poise limit, x3 experience); and bosses with x7 hit points against eight
  players' x8 damage, so a boss takes all eight about as long as it takes one player alone, with eight times the
  things going on around it. Bosses get no damage step (the game's rule).
- **Elites** (`elite_hp` 220, `elite_damage` 125, `elite_exp` 300): an ordinary creature (rank 0) is an elite when a
  figure of the level's name, its place and its kind falls under the row's chance: the same creature is an elite on
  every machine, and a creature of a level file is the same elite at every visit; one made during play (a spawner's)
  also mixes in the tick. An elite's poise limit is the mini-boss one (`poise_miniboss`), then the row's percent.
- **More creatures** (`extra`; above 100 a second one): only for creatures of a level file (`world_loadRecords`
  loading the level, not a saved level state), only ordinary ones (rank 0) that are not someone - no `action`,
  `hide`, `dead`, `miniboss`, `boss`, `dialog...`, `shop`, `showname`, `script...` property. A creature of a named
  group (`name=first`, `name=second`: the groups the level scripts wake and count) is copied **with** its name, so
  the group's scripts count and wake the extra one too; while the game's name table (512 objects, 0x5f7ef8) has
  more than 384 entries, named ones are not copied. The place is the game's own `world_findFreeSpot` (range 48, the
  creature's radius; it draws on the shared generator as every machine does); no free spot, or fewer than 96 free
  creature blocks in the object pool, and none is made. Extra creatures are marked transient (object flag 0x4000:
  never written into a saved level state), so a level visited again from its saved state has its own creatures only.

### B.3 How it is reached

- `Creature_setStats` 0x10a620 is called directly by `Creature_ctor` (and the two `CastBadger` functions):
  `rt_replace_function` does not reach direct calls, so it is on `app/hle-app.txt` and `partyscale_hle.cpp` supplies
  it in the fix-set translation (as the cut-scene work did for `cut_runFrame`). With Hardcore off it is the original
  and nothing else; `rta_app_orig` (the rig's translation) does not have it at all.
- With Hardcore on: the party size n (the game's count, or `combat.party.players`); the creature's rank
  (`creature_bossRank` 0x10d940, the game's own, as the original calls it); elite or not. When the row is the game's
  own for this n and the count the game reads is n and it is not an elite: the original as it is. Otherwise the
  multipliers (f12 hit points, f14 damage, f16 experience) are multiplied by the row (and the elite's), the count
  the original reads is held at 1 while it runs, and put back.
- `world_objectFactory` 0x159c94 is called through `g_objectFactory`: `rt_replace_function`, installed with
  Hardcore's wrappers. The original runs first; when the call came from `world_loadRecords` loading a level file
  (return address 0x14e9a8 and the blob's saved-state bit, held in r30 by that function, clear) and the object is
  an ordinary creature, the extra ones are made by the original factory with the same class, angle and properties.
- `soulscombat.cpp` (four one-line hunks): the poise limit goes through `partyscale_hook::poise_limit`; the tuning
  figure folds in the party tuning (a room whose copies differ refuses to start, as for every Hardcore number);
  `combat.party.*` settings; the figures line. Through hook pointers: a build without `partyscale.cpp` (the Windows
  and Linux programs today) links and has no party scaling.
- The block at 0xE2000 (partyscale.h) counts creatures scaled, elites, extras, bosses and the sum of the maximum hit
  points given: written in the simulation, so its words are tick-log columns that every copy must agree on.

Settings (`settings.txt`, `--settings`, `app souls set party.NAME VALUE` offline): `combat.party.on`,
`combat.party.players` (0 = the game's count), `combat.party.hp.1` .. `.8`, `boss_hp.N`, `damage.N`, `exp.N`,
`poise.N`, `elite.N`, `extra.N`, `elite_hp`, `elite_damage`, `elite_exp`, `extra_range`, `pool_keep`.
`PARTY_LOG=1`: a line for every creature scaled and every extra one made.

### B.4 What it does not do (yet)

- Elites are not marked on screen (no tint, no name); the Godot HUD's target bar could say "Elite" from `elite()`.
- No scaling of loot (more creatures already drop more; the game's drop tables are per creature).
- Parties of five to eight exist only as the forced count until part C: the curve for them is tuned on paper and
  run with two copies standing in for eight (B.5).

### B.5 Ran

Program `rta_app_next` (`python3 tools/recomp/app/build.py --as rta_app_next`, 2026-10-26), Hardcore on.

**Offline, valor, the route of `local/souls-combat/t3`** (`local/party8/v1.rig`, `v8.rig`; `PARTY_LOG=1`):

| Party | Creatures scaled | Handed to the game unchanged | Elites | Extra creatures (not made) | e.g. WarBoar |
|---|---|---|---|---|---|
| 1 (the game's count) | 98 | 95 | 3 | 0 | 545.6 - 686.5 hit points, damage 37-74, experience 1190 (the game's own) |
| 8 (forced) | 173 | 0 | 48 | 75 (19) | 2252 - 2833 hit points, damage 68-137, experience 18604; an elite 4970, 86-172, 79501 |

The run with eight went through the level's load and 1,600 ticks of play with 75 more creatures standing in it.

**Rooms** (`local/party8/room.sh OUT PLAYERS PORT PARTY`: `local/souls-combat/net/as-app.py` copies of
`rta_app_next`, offscreen; a rendezvous service of the run's own on 127.0.0.1; the host given `--combat hardcore`,
the joiners following; `--level-option valor`, 1,500 frames, then drunare for 2,400; drawn input; every pair of tick
logs compared, with the party block's words and Hardcore's poise and blocks as columns; `compare.py ticks` as in
`native-rendezvous.md` 6):

| Run | Copies | Party size | Ticks in step (every pair) | Levels | Scaled / unchanged / elites / extra (not made) / bosses | Notes |
|---|---|---|---|---|---|---|
| `r2p8` | 2 | 8 (forced) | 4,905: **every game column equal**; the party block's extras counter differed from tick 1 (86 against 73) | valor > drunare | - | the counters were not reset when the room's game began: the host (Hardcore on before the room) had counted the title screen's creatures. Fixed: the block is reset where Hardcore resets its own (`partyscale_hook::reset`) |
| `r2p8b` | 2 | 8 (forced) | **4,836**, no column differs | valor > drunare | 183 / 0 / 45 / 77 (16) / 3 | |
| `r3p0` | 3 | 3 (the game's count) | **4,918** in all three pairs | valor > drunare | 107 / 100 / 7 / 0 / 3 | the game's own numbers for 100 of 107: only the elites changed |
| `r3p8` | 3 | 8 (forced) | **11,439** in all three pairs (11,441 j1/j2) | valor, 51 deaths, 17 reloads after the whole party died | 1,786 / 0 / 452 / 73 (16) / 18 | every player put beside a creature by Hardcore's test aid eight times (`poke32 0xe0d80 slot+1` in one lockstep tick on every copy): a party of three against the numbers for eight is wiped again and again, and stays in step through every reload; the level change was never reached (the scripts ran out of time), `r2p8b` has it |

Offline with Hardcore **off** (the same valor route, `c1`): every `Creature_setStats` call went straight to the
original (the party code took none: "creatures scaled 0 (0 calls here)"), and the factory wrapper was never
installed: a Classic game runs the original translation of both.

Seen in `r3p8`: a reload after a wipe loads the level's saved state, so the extra creatures do not come back
(73 extras over 17 reloads: all from the first load). As designed (B.2); a party that wipes meets the level's own
creatures, scaled and with elites, on the next try.

## C. Five to eight: the first step built (the tables move), the rest not this round

A.9 steps 1 and 3 are built and **Ran offline**; the room launch with the tables moved does not complete yet; steps 2
and 4 to 8 are not started.

### C.1 What was built

| Piece | Where | State |
|---|---|---|
| relocatable addresses in the translator | `tools/recomp/reloc.py`, `recomp.py --reloc FILE` | a forward data flow per unit (per register "holds the upper half H" / "H plus an index"; a jump table reaches every label; an entry only the data words point at is an ordinary label); every load, store, `addiu`, `ori` that forms an address in a listed range gets `+ g_reloc[k]`. On today's executable: **1,043 instructions in 442 units** (g_players 644, g_pads 120, the button tables 89, g_peers 71, the launch records 32, ...), none it could not rewrite. Without `--reloc` the translator's output is unchanged |
| the ranges | `tools/recomp/app/party8-ranges.txt` | 16 tables (A.1-A.4). Still to split: the 12 button tables and the four address and port tables are back to back - each needs its own line before it can grow |
| the build | `tools/recomp/app/build.py --party8 [--party8-check] --as NAME` | a translation of its own (`gen-app-p8`; the shared `gen-app` is untouched), compiled with `RECOMP_RELOC_DYN`: every translated load and store that still reaches an old place goes to the new one (a 8 KB page map, then the ranges: one byte load per access when nothing is moved). `--party8-check` instead reports every such access with the function it is in (`RECOMP_RELOC_CHECK`, `rt/recomp.h`) |
| the move | `tools/recomp/app/party8.{h,cpp}`, `app party8 on [poison|trap] / off / info`, `--opt party8=1|poison` | copies the 16 tables to 0x88000-0xDFFFF (and g_savedPlayers to 0x30000-0x73FFF), each with room for eight; checks both areas are empty (the game writes 0x74000-0x77FFF and 0x82000-0x83FFF early on: left out); `poison` fills the old places with 0xA5; `trap` also makes their whole pages unreadable (a call stack on the first access; it trips the renderer's texture scan, so the check build is the tool) |
| the native modules | `rt/moved.h` `party8_at()`; used by `rt/rt.h` `guest_addr` (so every runtime and network reader of a guest pointer: DMA, the network library, the script's `show`/`poke`), `rt/script.cpp`, `net/netshim.cpp`, `net2/launch.cpp`, and the readers of `soulscombat.cpp`, `partyscale.cpp`, `fpaim.cpp`, `fpcontrols.cpp`, `fpview.cpp`, `gamestate.cpp`, `testerkit.cpp` | the same address while nothing is moved; not done: `cinematic.cpp` (the cut-scene work's file: it reads `g_pads` at its fixed address) and the Godot library's `skeleton_export.cpp` |
| the memory map | `tools/recomp/app/guestmap.h` | every native block in the first megabyte in one list with a compile-time overlap check; `partyscale.cpp` checks `soulscombat.h`, `fpaim.h`, `cinematic.h` and `partyscale.h` against it, `party8.cpp` its two areas |

### C.2 Ran

The valor route offline (`local/party8/cs.rig`, Classic, a `show` of the seed, the player's hit points, gold, place,
facing and the three free-list heads of the object pool every 20 ticks, 74 rows):

| Program | Tables | Rows equal to `rta_app_next`'s |
|---|---|---|
| `rta_app_p8` (relocatable translation, dynamic map) | not moved | **74 of 74** (the relocations are a no-op) |
| `rta_app_p8` | moved at the first blank, old places poisoned (`cmb.rig`) | **74 of 74** |
| `rta_app_p8` | moved at the title screen, poisoned (`cms.rig`) | **74 of 74** |
| `rta_app_next` after every hunk of this part (moved.h in the readers, `guest_addr`, `recomp.h`) | - | **74 of 74**; a Classic room of two (`cl2`) 4,933 ticks in step through valor > drunare |
| `rta_app_p8`, a room of two, not moved (`u2`) | - | 4,934 ticks in step through valor > drunare |
| `rta_app_p8`, a room of two (and three), moved at boot, poisoned (`m2`, `m3`) | moved | **the launch never completes**: both copies send the room's start, the game's handshake sends no datagram, the level is never loaded. The check build (`c2`) sees no translated access to an old place in that run (one, from an out-of-line `LD32`, to `g_pads`), so what is still at the old place is read by native code: the next thing to look at |

What the runs taught, for the next round:

1. **Static relocation alone is not enough.** With it only, a move at the title screen hangs the front end: the
   translated code of `player_initNewCharacter` and the inventory checks reached the old places (found with
   `--party8-check`). Two causes: (a) loop heads that the translator makes entries only because a data word holds
   their address reset the analysis (fixed: such entries are ordinary labels now); (b) a register that holds a
   record's address across a vertical blank - a guest thread suspended in a system call while the move happens.
   The dynamic map (`RECOMP_RELOC_DYN`) makes both harmless for slots 0 to 3; for slots 4 to 7 the static relocation
   has to be complete, because an address past the old end is another global of the game.
2. **Move at boot** (`--opt party8=1`): before the game has made any pointer into a table. A copy that can host or
   join a room of five to eight is started that way (the portal knows the room's size before it starts the game).
3. **Every native reader goes through `party8_at`**: the runtime's `guest_addr` covers most at once.

### C.3 Next, in order

1. The room launch with moved tables (C.2, last row).
2. Split the back-to-back tables into their own ranges; the review list of A.0 (44 functions) into
   `party8-sites.txt` (the literal fours, A.9 step 2).
3. The wire (A.3, packet type 0xbd48), the launch (A.4), `NET2_PLAYERS` 8 and the room's capacity (A.8).
4. Five and six headless copies in one room through a level change.

## Found on the way

- **The Hardcore block and the aiming block overlapped** (the Hardcore block grew to 0xE147F with its attributes
  part; aiming sat at 0xE0E00). Fixed by the orchestrator: aiming moved to 0xE1800 (`fpaim.h`). To keep it from
  happening again: `tools/recomp/app/guestmap.h` lists every block and checks at compile time that none overlap,
  and `partyscale.cpp` checks the modules' own constants against it.

## Files

| File | What |
|---|---|
| `tools/recomp/app/partyscale.h`, `partyscale.cpp` | B: the curve, the block, the setStats logic, the factory wrapper, settings |
| `tools/recomp/app/partyscale_hle.cpp` | B: `fn_0010a620`, the fix-set translation's entry |
| `tools/recomp/app/hle-app.txt` | one line: 10a620 |
| `tools/recomp/app/soulscombat.cpp` | four hunks: include, install, poise limit, figure, settings, figures line |
| `tools/recomp/app/build.py`, `tools/godot/build.py` | the two files compiled (the HLE one only when the translation leaves 0x10a620 open) |
| `tools/recomp/app/guestmap.h` | every guest-memory block of the native modules, checked not to overlap |
| `tools/recomp/reloc.py`, `tools/recomp/recomp.py` (`--reloc`), `tools/recomp/app/party8-ranges.txt` | C: relocatable addresses |
| `tools/recomp/app/party8.{h,cpp}`, `tools/recomp/rt/moved.h`, `rt/recomp.h` (`RECOMP_RELOC_DYN`, `RECOMP_RELOC_CHECK`), `rt/rt.h` (`guest_addr`), `rt/script.cpp`, `app/build.py` (`--party8`, `--party8-check`), `app/app_main.cpp` (`party8::blank`, `app party8`) | C: the move and its checks |
| the readers through `party8_at` | `net/netshim.cpp`, `net2/launch.cpp`, `app/fpaim.cpp`, `fpcontrols.cpp`, `fpview.cpp`, `gamestate.cpp`, `testerkit.cpp`, `soulscombat.cpp` (its eight memory helpers), `partyscale.cpp` |
| `local/party8/` (not tracked) | `v1.rig`, `v8.rig`, `run.sh` (offline), `room.sh`, `n2p8.py` (rooms), `cs.rig`, `cms.rig`, `cmb.rig`, `runt.sh`, `room8.sh` (C), the runs |
| the census (not tracked) | a scratch script over `local/recomp-out/gen`; its output is A.0's table |
