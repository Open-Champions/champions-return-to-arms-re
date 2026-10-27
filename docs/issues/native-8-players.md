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
- **C. Five to eight in the lockstep core and net2**: **built and Ran** - rooms of five, six and eight copies in step
  through a level change and a Hardcore fight (section C).

Every statement says **Read** (from the decompile, the translation or the docs it cites), **Counted** (a scan of the
local translation, numbers below) or **Ran**.

## STATE (rewritten at every step)

**2026-10-26, third round (C.12).** The player-facing gaps are closed. **The portal has the switch**: a Remastered host
picks "Party size: up to 4 / up to 8" when hosting (and on the room screen while alone in it); the game copy is started
for the room's size (`party8=8`, 64 MB, or `party8=1`), a joiner's copy follows the room's size by itself, a copy of the
other size is told and offered a restart that comes back to the same room, and a copy that cannot play eight is told so.
Classic stays one to four. A Godot copy now says it can play eight (bit 0x1000 was missing from its own word: the room
service held a portal room of eight at four). **Limited to four no more** where a real room of five to eight meets it:
aiming by looking (second block at 0xE1A00, `guestmap.h`), the first-person and shoulder views and their controls for
players 5..8, the Elden Ring layer's figures (`rtag_skeletons` players 5..8, the skeleton export's record address), the
Godot extension's readers (the library's whole memory, and the moved tables for the HUD reader), the Hardcore HUD's
stamina / flasks / sheet for players 5..8, and the inventory's item lists of players 5..8. **Ran**: six Godot copies,
Remastered (Hardcore, aiming by looking, the Elden Ring layer, the shoulder view), a service on 127.0.0.1, valor >
drunare with fights: **4,455 - 4,470 ticks in step, all 15 pairs**; every copy's figures list players 1..6, player 5's
aim in the simulation on every copy alike. Rooms of one to four unchanged: the rig byte for byte (overhead and first
person), the offline route identical row for row (switch off; tables moved and poisoned: every value), a room of
**four** with the tables moved 3,455 ticks in step (all pairs), a room of two (switch off) 4,935. The 8-player native
launchers are on the Desktop. Open (C.11): the mixed Godot + window-program Hardcore room (the ChatGPT job), the inventory
change not yet run with an open inventory, the game's own launch screen and pause list of four.

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

## C. Five to eight (built; Ran in rooms of five, six and eight)

C.1 and C.2 are the first round (the tables move, offline); C.3 to C.11 the second; C.12 the third.

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

### C.3 The room launch with the tables moved (2026-10-26, second round: Ran)

Two faults, both in the translation, neither in a native reader (the coordinator's lead - `cinematic.cpp` reading
`g_pads` at its fixed address - was real and is fixed too, but it did not hold the launch):

1. **Tables reached from a pointer into another table.** `net_launchTransfer` reads the two address tables from a pointer
   into the port tables (0x135130: `lbu -0x2e(r17)`, r17 = the port table + 4k), and the end of the launch reads the
   records' neighbours the same way; with each table moved by its own amount those reads land in other memory: the
   game sent its launch packets to 0.0.0.0. `reloc.py` now follows a pointer into table k and reports every access
   from it that lands outside table k ("reached from a pointer into another table", `gen-app-p8/reloc-crosses.txt`);
   the launch's settings block, address and port tables, the launch buffer's words and the launch records are one
   range (0x402a30-0x4030a0); with that the list is empty apart from two known cases (the equipment cache, C.6, and a
   string index in `Player_interact`).
2. **`ori` relocated wrongly** (found by the ChatGPT review, item 5): a relocated `lui`/`ori` pair was emitted as
   `r | imm + delta`, which C++ reads as `r | (imm + delta)`. Now `SX32((u32)(r | imm) + delta)`.
   `tools/recomp/reloc_test.py` compiles and runs 308 synthetic cases (lui + addiu, lui + ori, lui + load / store;
   positive and negative deltas, carries and borrows across the 16-bit immediate and the 64 KB upper half): 308 right,
   and 54 of them wrong with the old `reloc.py`.

Also: a moved table keeps its old address modulo 16 (the address tables at 0x402b3b are read with `lwl`/`lwr`), and
jump tables are followed to their own targets (`reloc.py jump_table`: the `sltiu` bound, the `lui`/`lw` table) instead
of "every label of the unit", which lost registers that stay the same across one dispatch (`net_launchUpdate`'s r18).

**Ran** (`rta_app_p8`, `--opt party8=poison`, valor 1,500 frames > drunare 2,400, drawn input): a room of **two**, 4,932
ticks in step; a room of **three**, 4,914 / 4,915 / 4,914 ticks in step, all three pairs (`local/party8/m2b`, `m3b`).

### C.4 The hard-coded fours (A.9 step 2)

The review of A.0's 44 functions and the launch code (`party8-sites.txt`, each line with its reason) found seven
immediates that are the slot count and nothing else, and more that need other treatment. The translator emits a listed
site with `g_party8_slots` (4, or 8 in a game of five to eight; `recomp.py --reloc-sites`), by kind:

| Kind | What | Sites |
|---|---|---|
| (slots) | an immediate 4: `slti`, `sltiu`, `addiu`, `ori` | 0x134d58 (launch: the peers), 0x13df74 (`net_dropAllRemotes`), 0x158b78 (`Player1_ctor`: spawn points), 0x18ce68 (pause menu: active players), 0x1a02b8 (a menu nobody owns: the pads), 0x1dc6c0, 0x1dc6d8, 0x1dcc64 (gold), 0x1a3044 (`eqcache_release`) |
| `last` | `addiu r, $zero, 3`, a count-down over the four | 0x1a2820, 0x1bf790 (`mission_setComplete`), 0x1ec2d4, 0x1eb900 (dead countdowns), 0x1e4ff4 (notice boxes) |
| `lastoff:N` | from element 0 of an array to its last | 0x1ec2d0, 0x1eb8c4, 0x1e4fe0 |
| `rows:0x160` | a step or offset in rows of one record per slot | the equipment cache, C.6 |
| `shl+1` | a row offset made as (row x 11) << 5 | 0x1a2ab4 |
| `rxmask` | the input packet's active mask | 0x13b694, C.5 |
| `memtop` | the top of memory the heap is sized by | 0x19d59c, C.7 |

Kept at four (Read): the raw controllers (`pad_readAll`, `pad_updateRumble`, `pad_resetSlotMap`), the save format's
four blocks, the game's own HUD places (`hud_drawGold`'s positions), `net_restoreButtonConfig` and the two other
installs of the offline button configuration (they read a table of four), `pad_init` (its loop also clears the raw
buffers; slots 4..7 of the moved pads start empty), the developer LAN lobby, `net_frameLoop`'s save / clear / restore
of four raw pads' edges (its stack arrays hold four: a local player 5..8 keeps its edges through the ticks of one call -
local menus only).

**Per-slot tables added** (`party8-ranges.txt`, now 65 tables in 96 slots of `g_reloc`): `g_netSendCycleTable` (and
`party8.cpp` fills its entries for four to seven remote peers), the HUD's gold arrays and `g_goldPending`, the per-slot
copies the launch's end makes (0x4f84b0 + slot x 0x40, 0x4f85d0 + slot x 4: slot 4's would have overwritten
`g_gameLevelLoaded`), the notice and recall arrays, the aura and prompt arrays, the spell selector's, the HUD notices,
the hit flash, `g_playerAuraLightColor`, `g_itemPanels`, the twelve button tables each on its own line, the launch's
character summaries (0x4030a0), the interact prompt's text, the equipment cache's ten rows, and the **raw pads by
player slot**: `net_main` samples the local player's pad into `g_rawPads[own slot]` and `g_rawPadPrev[own slot]`
(0x1334b4, 0x1334d4) - for player 5 that wrote into the launch's settings block.

### C.5 The wire, the launch, the room (A.3, A.4, A.8)

- **The input packet's active mask** (`rt/moved.h`, `net/netdrv.cpp`): in a game of five to eight the network layer
  appends a trailer word 0xB8000000 | mask (eight bits, computed as `net_sendInputPacket` computes it) to every input
  packet (0xbd3f) and raw relay (0xbd42) it sends, and takes it off every one it receives, leaving the mask in
  `g_party8_rx_mask`; the site 0x13b694 (`net_receivePackets`' `sra $10, $10, 4`) reads that instead of the nibble.
  Sync-word alignment is unchanged (the trailer is after the message blocks; the receiver walks blocks to the end of
  the datagram, which no longer includes it). Only in rooms of five to eight; every other packet as before.
- **The launch for five to eight** (`net2/launch.cpp`): `party8_game(count)` (net2 hook) turns the fours into eights
  before `net_launchTransfer`; the second address table is left empty in such a room (a player 4..7 looks for its own
  outside address at `addr1[own]`, which is entry own-4 of the second table: empty, no packet matches it, so the "two
  consoles behind one router" re-addressing never fires); after `net_launchTransfer` the launch records 4..7 get their
  addresses and ports written field for field as the game's loop writes 0..3 (`party8_records`); when the launch
  completes, peers 4..7 get +0x44c0 = 1 and their two **input-codec states** (+0x10, +0x60: `net_shutdown`'s loop
  ends at four peers; with zero states a sender's encoder and the receivers' decoder disagreed from the first tick,
  Ran) - `party8_peers`.
- **Room capacity** (`NET2_PLAYERS` 8, `net2_options.max_players`, `--opt net2-size=N`; `rendezvous.py`
  `Room.capacity`): a host asks for a room of 5..8 (option `size`); the room takes a fifth player only while every copy
  in it says it can play one (bit 0x1000 of the copy's word count, set by `launch.cpp` when the copy was started with
  `--opt party8=1` and its translation has the relocations); the room line says `size=` (asked) and `cap=` (holds now).
  `check.py` 262 of 262 (eight checks new); `check_client.py` 136 of 136. **The public service is not changed**:
  `tools/rendezvous/deploy/STEPS.txt` 14-17 (prepared, not run); until then rooms there hold four.
- `session.cpp clean_options` passes `max_players` (it dropped it: the first five-copy run was refused at the fifth).

### C.6 The equipment cache

`eqcache_*` (0x1a2680-0x1a3080) keeps ten rows (equipment kinds) of one 0x58-byte record per slot, rows 0x160 apart
(0x8659e8). Players 5..8 indexed past their row into the next row's slot 0..3: a weapon read into a 0x140-byte
'armor(righthand)' buffer overran the heap block after it (Ran: `party8: HEAP` - a heap walk every 30 blanks in a
game of five to eight, `PARTY8_HEAPCHECK`, found the list broken after 'armor(helmet)', 'armor(lefthand)',
'armor(righthand)' blocks; the record dump showed rows 5-9 with size 0). Each row is its own table, moved 0x2c0 apart in
order (`party8.cpp` checks it), and the code that steps or offsets by rows (0x160 multiples, and 0x1a2ab4's
(row x 11) << 5) is listed in `party8-sites.txt` (`rows:0x160`, `shl+1`). After that: no heap break in any run.

### C.7 Memory for eight

The game sizes its heap from the top of memory (0x19d59c: 32 MB; 23 MB of heap). Every player costs about 0.85 MB of
it (the equipment cache's buffers - body 80 KB, boots, gloves, helmet, leggings, the hands, shield 150 KB - and the
character's model lump, 290 KB for an iksar). **Ran**: five players fit; the sixth ran the heap out loading valor
(`memAlloc failed`, 24 KB free). A program built for rooms of up to eight (`app/build.py --party8`) now has 64 MB of
guest memory (`rt/ramsize.h` `RAM_SIZE`, every file of the program compiled with it), and a copy started with
`--opt party8=1` is told of all of it (`g_party8_memtop`: `GetMemorySize`, the main thread's stack, the heap's size at
0x19d59c); every other copy of the same program is told of 32 MB, as before. Native readers that masked guest
addresses with a 32 MB constant now use `RAM_SIZE - 1` (the runtime's system calls, the IOP's reads, the render
pipeline's memory copy, `fpworld`, `fpview`, `gfx_rt`, `testerkit`, `fpcontrols`, `gamestate`, `control.h`,
`skeleton_export`, `worldfill`). The Godot extension's own readers (`rta_machine.cpp`) still read the first 32 MB only.

### C.8 The native modules for slots 4..7

`party8_at(address)` maps an address inside an old place; a slot past the old end is reached as
`party8_at(table) + slot x size` (the table's base mapped, then the slot): `gamestate.cpp`, `fpcontrols.cpp`, `fpview.cpp`,
`cinematic.cpp`, `testerkit.cpp`, `soulscombat.cpp`, `launch.cpp`, `skeleton_export.cpp`, and the script's symbols
(`rt/script.cpp`: a moved table's name is its new place, so `g_players+4*0x4c30` is slot 4 in `show`, the tick logs and
`n2party.py`'s columns). Hardcore's per-player parts for players 5..8 are a second block with the same layout at
0xE2100 (`soulscombat.cpp high()`, `guestmap.h`); its guards and loops go to eight. Aiming by looking (`fpaim`) stayed at
players 1..4 in this round (5..8 aimed the game's way); C.12 gives it 5..8.

### C.9 What the players see

- `gamestate.h` `RTA_GS_PLAYERS` 8 (version 2): the HUD state has eight players; the Godot HUD reads eight
  (`hud.gd MAX_PLAYERS`), and `status.gd` draws the others' frames compact (name, level, health) when there are more
  than three; `--hud-fake-party` takes up to 7.
- The window program without Godot: the game's own HUD draws players 1..4; `party8::overlay` draws players 5..8 as a
  list on the right (name, health bar, "(LEFT)").
- The portal's room screen (`room.gd`): eight seats in two rows in a room of up to eight; a "Players: up to 4 / up to 8"
  choice for a host whose copy can play one; Invite follows the room's capacity. A Remastered copy is started with
  `--opt party8=1` (`handover.gd`); the Godot library is built from the relocatable translation with
  `RTA_GODOT_PARTY8=1 python3 tools/godot/build.py` (`party8.cpp` and its blank in `rtag.cpp`, 64 MB).
- The game's own launch screen (`net_launchDraw`) is left as it is (rows for four).

### C.10 Ran: five, six and eight in one room

Program `rta_app_next` = `app/build.py --party8 --as rta_app_next` (the relocatable translation, 64 MB, the switch off
unless asked). Copies started with `--opt party8=poison8` (tables moved at boot, old places filled with 0xA5, 64 MB for
the heap); the window program offscreen (`local/souls-combat/net/as-app.py`); a service of the run's own on 127.0.0.1;
`local/party8/room8h.sh`: a **Hardcore** room (the host chooses, the joiners follow; party scaling at the game's own
count), valor 1,500 frames > drunare 2,400, drawn input; Hardcore's test aid puts players 1 and 2 beside the nearest
creature at tick 1500 and everybody at ticks 3000 and 3400 (fights); every pair of tick logs compared (`compare.py
ticks`: seed, level, count, the twelve button tables, every player's position, state, hit points, gold, experience, the
out-of-step flags, the sync hash, the party block and Hardcore's figures).

| Run | Copies | Ticks in step, every pair | Levels | Fight (Hardcore's figures) | Party scaling |
|---|---|---|---|---|---|
| `n5` | 5 | **8,165 - 8,168** (10 pairs) | valor > drunare | 12 creature hits by players, 2 player hits, 2 deaths | party of 5: 135 scaled, 16 elites, 29 extra creatures (5 not made), 3 bosses |
| `n6` | 6 | **4,821 - 4,828** (15 pairs) | valor > drunare | 11 creature hits, 11 player hits, 5 deaths | party of 6: 155 scaled, 20 elites, 48 extra (10 not made) |
| `n8` | **8** | **4,738 - 4,752** (all 28 pairs) | valor > drunare | 23 creature hits, 22 player hits, 4 deaths | party of 8: 180 scaled, 40 elites, 73 extra (20 not made) |
| `gm8` | **4 Godot + 4 window programs** (Classic combat) | **3,564 - 3,582** (all 28 pairs) | valor > drunare | - | - |
| `gm5` | 1 Godot + 4 | 1,857 - 1,863 (10 pairs), valor | | | |
| `g8` | 4 Godot + 4, Hardcore | each group of four in step with itself; **the two groups differ** from tick 219 (a player's state, then the seed at 386) | valor > drunare | | party of 8 |

The Godot copies: `RTA_GODOT_PARTY8=1 RTA_GODOT_OUT=local/godot-p8 python3 tools/godot/build.py all` (the library from
`obj-rta_native_p8`, 64 MB), started by `local/party8/as-godot8.py` (scene mode, 640 x 360, offscreen; `GODOT_ROLES`
picks which copies). `g8`: the library's snapshot was older than one change - it read `party8=poison8` as "no
poison", so its copies kept stale copies at the old places where the window programs had 0xA5: the two groups differ
exactly as a read of an old place in Hardcore's path would make them. That read is the open item (C.11).

Rooms of one to four, the same program: a Classic room of two (`fc2`, switch off) 4,933 ticks in step through valor >
drunare; tables moved (`party8=poison`) rooms of two (`fm2`, 3,445 ticks) and three (`fm3`, 3,451-3,452, all pairs).
(Room runs are not repeatable tick for tick between two runs - the drawn input is keyed to frames: two runs of the same
plain program part at tick 1,176 - so the program-against-program identity is shown offline and by the rig:)

| Check | Result |
|---|---|
| the rig comparison, the unpatched translation with all of this work linked in (`app/build.py --original --as rta_app_orig_p8`; `local/souls-combat/rig/check.py`) | **overhead and first person both byte for byte the reference** (`reference-compare.txt`, `s13-first-compare.txt`) |
| offline valor route (`cs.rig`, 74 rows of seed, hit points, gold, place, facing, pool heads, with their addresses) `rta_app_next` (switch off) against `rta_app_next_plain` (`app/build.py` without `--party8`) | **74 of 74 identical**, addresses included |
| the same with `--opt party8=poison` (tables moved and poisoned, 32 MB) | **74 of 74 values identical** |
| the same with `party8=8` (64 MB) | differs from the first row: a bigger heap is other addresses, other choices - why only a copy for rooms of five to eight is started that way (C.7) |

### C.11 Open

- **Hardcore across the Godot library and the window program in a room of five to eight** (`g8`, above): a read of an
  old place in Hardcore's path (native or translated); a check-build Hardcore room (`--party8-check`) lists translated
  ones. All-window-program and all-Godot Hardcore rooms are in step (both read the same thing), so a room of eight in
  one program plays; a mixed one does not yet.
- ~~The public service holds four~~ (deployed 2026-10-26).
- Players 5..8: ~~aiming by looking, the Elden Ring layer's figures, the Godot extension's readers, the inventory's
  item lists~~ (C.12). Still four: the game's own launch screen draws four rows, `pauseMenu_task`'s player list holds
  four (0x18db2c); the eqcache release at the end of a game of eight frees eight. The inventory change (C.12) is built
  but no run has opened an inventory yet (a scripted `tap select` opened none, for player 2 either).
- ~~No room of four copies was run~~ (C.12: `xm4`).

### C.12 Third round: the switch in the portal, and the last fours (2026-10-26: Ran)

**The portal** (`portal.gd host_party`, `restart_for_party`; `handover.gd party_size`; `screens/room.gd`):

- *Host a game* (Remastered, a game library that can play eight: `rtag_has("party8")`) first asks **Party size: up to 4 /
  up to 8** (the last choice remembered, profile `eight`). The room is opened with `max_players` 8 (the service holds
  eight once every copy says it can: `rendezvous.py Room.capacity`). Classic never asks: up to four.
- The game copy is started for **the room's size** (`handover.gd party_size`: `party8=8`, 64 MB, in a room that asks for
  more than four, else `party8=1`): the two are different games (C.7), so a joiner's copy follows the room it is in.
  The size of a copy is fixed for the run of the program (one machine per run); another size restarts the program
  (`OS.set_restart_on_exit`), which then hosts again (`--portal-host-party N`) or joins the same room again
  (`--portal-join-code CODE`).
- The room screen: a **Party size** choice for the host (locked once somebody else is in the room: changing it restarts
  the host's game and opens a new room); eight seats in a room of up to eight.
- **Joiners are told**: a copy whose size is not the room's sees "This room is for up to 8 players and your game was
  started for up to 4 - restart it to play here" and the button *Restart your game for up to 8* (back in the same room);
  a copy whose library cannot play eight: "This room is for up to 8 players - your copy of the game can play up to 4
  only. The host can switch to up to 4"; the others see who must restart. The start waits.
- Found: a Godot copy's own word for itself (`rtag.cpp`, the `copy=` of `rtag_info`, which the portal says to the room)
  had no bit 0x1000, so the service held a portal room of eight at four; it has it now.

**Ran** (the portal on a service of its own on 127.0.0.1, `local/party8/pt`): a host started with `--portal-host-party 8`
opened a room asking for eight, its game started with `party8=8` and said `words=61629` (0x1000 set); a second portal
joined by the code with `eight=false` in its profile: "the game is started for a room of up to 8", the same word, eight
seats, no warning (`join3.png`). Before the `copy=` fix the same host showed the warning and the restart button
(`room.png`). The restart itself (the program starting again) was not run.

**The last fours** (each only in a game of five to eight; every game of one to four does what it did):

| What | Where | Change |
|---|---|---|
| aiming by looking, players 5..8 | `fpaim.{h,cpp}`, `guestmap.h`, `partyscale.cpp` | the per-player parts of players 5..8 in a second block `AIM_HIGH` 0xE1A00-0xE1A7F (listed in `guestmap.h`, checked by `static_assert`); the message handler, `Player_run`'s wrapper and the sender take slots up to 7 |
| the look views' controls and camera for players 5..8 | `fpcontrols.cpp find_body`, `fpview.cpp fallback_reason`, the pad slot | slots up to 7 (players 5..8 had no first-person or shoulder view at all, so no look to aim with); the interact prompt's arrays read as moved table + slot |
| the Elden Ring layer's figures | `lib/skeleton_export.cpp`, `lib/rtag.h` (`rtag_skeletons.players_more[4]`, filled when the host's structure has it), `extension rta_machine.cpp get_skeletons`, `er_layer.gd _player_slot_of` | eight players; the record address of slots 4..7 is the moved table + slot (it was `party8_at(table + slot)`: past the old end, no player found); `er_layer.gd` takes owners up to 64 MB and masks with 0x3FFFFFF |
| the Godot extension's readers | `rta_machine.cpp` (`peek_*`, the lights), `rta_gamestate.cpp`, `rtag_memory_size`, `rtag_moved_get` | the library's whole memory (64 MB) instead of the first 32 MB; the HUD reader (`gamestate.cpp` compiled into the extension) takes the library's memory size and its moved tables (it had its own empty map: in a copy with the tables moved it read the old places) |
| the Hardcore HUD for players 5..8 | `hud/souls.gd`, `hud/sheet.gd` | stamina, flasks, the weapon and the sheet from the second block (`SOULS_HIGH`) |
| the inventory's item lists | `party8.cpp` (a wrapper of `inventory_pollResources` 0x1bfbc8) | the four blocks of 0x23988 bytes from the pointer at 0x4ebbb0 are indexed by the local player's slot; a machine whose player is 5..8 gets the pointer four blocks lower, so its block is the cleared one of the player slot - 4, which is not local there (player 8 overran 0x1cc40 bytes into the inventory's textures) |

**Ran**: programs `rta_app_p8x` (`app/build.py --party8`), `rta_app_orig_p8x` (`--original`), Godot `local/godot-p8x`
(`RTA_GODOT_PARTY8=1`).

| Run | Copies | Result |
|---|---|---|
| `x6b` (`local/party8/room8gx.sh`, `as-godot8x.py`) | **6 Godot copies, Remastered** (`--edition remastered`: Hardcore, aiming by looking, the Elden Ring layer; shoulder view), `party8=poison8`, service on 127.0.0.1 | **4,455 - 4,470 ticks in step, all 15 pairs**, valor > drunare, 3 deaths; party of 6 (155 scaled, 20 elites, 48 extra); every copy's figures (`app er dump`) list players 1..6; aiming: player 5 on with pitch -10923 after 112 messages, player 6 95 messages - the same on every copy (the simulation's block) |
| `x6` (the same, before the skeleton fix) | 6 Godot | 3,890 - 3,905 ticks, all 15 pairs; the figures listed four players (the record address fault above) |
| `y5` | 1 Godot (player 5, Elden Ring layer) + 4 window programs, Classic combat | 3,593 - 3,601 ticks, all 10 pairs (figures: the fault above, found here) |
| `xm4` | **4** window programs, tables moved and poisoned (32 MB) | 3,455 - 3,456 ticks, all 6 pairs |
| `xc2` | 2 window programs, switch off | 4,935 ticks |
| `xi5c`, `xi5d` | 5 window programs, a copy taps select | in step (4,845 - 4,852); no inventory opened (player 5 or 2): the inventory change is not exercised |
| the rig (`check.py`, `rta_app_orig_p8x`) | - | **overhead and first person byte for byte the reference** |
| the offline route (`cs.rig`) `rta_app_p8x` against `rta_app_next_plain` | - | switch off: **identical** (198 lines, addresses included); `party8=poison`: every value identical (only the moved tables' addresses differ) |

**The launchers** (on the Desktop, not tracked): *Play Champions - REMASTERED (new)* starts `local/godot-p8x` (the build
for rooms of up to eight; the portal asks the party size); new *Play Champions - native, host online (8 players)* and
*... join online (8 players)*: `rta_app8` (`--party8`) with `--opt party8=8` (the host also `--opt net2-size=8`, Hardcore,
aiming by looking, the shoulder view). A game started for four and one started for eight do not play together, so the
four-player launchers stay as they are.

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
| second round | `reloc.py` (crosses, jump tables, `ori`, sites: `slots`, `last`, `lastoff`, `rows`, `shl+1`, `rxmask`, `memtop`), `reloc_test.py`, `recomp.py --reloc-sites`, `app/party8-sites.txt`, `app/party8-ranges.txt` (65 tables), `rt/ramsize.h`, `rt/moved.h` (wide game, trailer, memory top), `rt/recomp.h`, `rt/runtime.cpp`, `rt/iop.cpp`, `rt/script.cpp`, `render/worldfill.cpp`, `net/netdrv.cpp`, `net/netshim.cpp`, `net/lobbyparty.py`, `net2/{hooks.h,launch.cpp,session.h,session.cpp,session_net.cpp,session_mock.cpp,n2party.py}`, `app/{party8.*,build.py,appmodules.py,app_main.cpp,gamestate.*,soulscombat.cpp,partyscale.cpp,fpcontrols.cpp,fpview.cpp,cinematic.cpp,testerkit.cpp,fpworld.cpp,gfx_rt.cpp,pipeline.h,control.h,guestmap.h}`, `tools/rendezvous/{rendezvous.py,check.py,deploy/STEPS.txt}`, `tools/godot/{build.py,lib/rtag.cpp,lib/skeleton_export.cpp,extension/src/rta_net2.cpp,project/hud/{hud,status}.gd,project/portal/{handover,profile}.gd,project/portal/screens/room.gd}` |
| third round | `app/{fpaim.h,fpaim.cpp,fpcontrols.cpp,fpview.cpp,guestmap.h,party8.cpp,partyscale.cpp}`, `tools/godot/{build.py,lib/rtag.{h,cpp},lib/skeleton_export.cpp,extension/src/{rta_machine.cpp,rta_gamestate.cpp,rta_library.h},project/er_layer.gd,project/hud/{souls,sheet}.gd,project/portal/{portal,handover,profile}.gd,project/portal/screens/room.gd}` |
| `local/party8/` (not tracked) | `v1.rig`, `v8.rig`, `run.sh` (offline), `room.sh`, `n2p8.py` (rooms), `cs.rig`, `cms.rig`, `cmb.rig`, `runt.sh`, `room8.sh` (C), `room8h.sh` (Hardcore rooms of up to eight), `room8g.sh`, `as-godot8.py` (Godot copies), `room8gx.sh`, `as-godot8x.py`, `n2p8x.py` (Remastered Godot rooms with figures probes), `room-inv.sh`, `as-app-inv.py`, `pt/` (the portal runs), the runs |
| the census (not tracked) | a scratch script over `local/recomp-out/gen`; its output is A.0's table |
