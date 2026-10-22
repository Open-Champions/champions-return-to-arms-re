# Arena match helper contracts

US `SLUS_209.73` v2.00. **Executed** in `tools/ee_emu.py` against
`tools/ref_arena_match_core.py` with `tools/difftest_arena_match_core.py`,
seeds 20973 and 7: 100 stat scales, 108 empty-wave visits, four next-wave
calls, 32 saved-pointer visits, four saved player records, 16 player respawns and four shutdowns
per seed; no mismatches. The tests construct state and
stub outside services. They do not establish a live match.

## `Creature_scaleStats` 0x1185d8

Arguments: creature in `a0`, five factors in `f12`–`f16`.
No calls and no seed draws. The five factors affect:

| Factor | Fields at creature offset | Operation |
|---|---|---|
| 0 | +0x228 current HP, +0x22c maximum HP | multiply, truncate to integer, convert back to float |
| 1 | +0xe4 armour | signed halfword × factor, truncate to signed halfword |
| 2 | +0xd0/+0xd2 damage range | signed halfwords × factor, truncate |
| 3 | +0xd4 attack rating | signed halfword × factor, truncate |
| 4 | +0xd8 experience award float | multiply, truncate to integer, convert back to float |

This matters for arena spawns: a factor of 1 still drops the fractional part of
the three float fields. The model and difftest cover positive fixture values
within the ordinary field ranges. Overflow and exceptional float inputs remain
unknown.

## Empty-wave visit callback 0x3069e8

The world walk calls this once per object. It increments the signed-halfword
live count at `0x8e733e` (with 16-bit wrap) exactly when object flags +0xc
masked by `0x68` equal `0x20`, and signed halfword +0x312 is nonnegative.
It makes no calls and no seed draws. The test checks ten flag combinations,
four states and three starting counts.

## `arena_nextWave` 0x305e9c and preparation 0x3063fc

The body calls screen effect `0x322954` with 15, then preparation `0x3063fc`,
then `arena_startWave` `0x305ed4` with its original argument. Preparation calls
`0x19f018`, clears the live count `0x8e733e`, walks objects through `0x14a610`
with callback `0x306a28`, then copies the resulting live count into the saved
count `0x8e7340`. The test injects nonzero counts after the walk and verifies
that copy.
The difftest executes preparation inside nextWave. The screen effect, its
`0x19f018` service, world walk and startWave are recording stubs; their own
bodies are outside this comparison. Neither function draws the shared seed.

### Saved monster pointer record

The pointer at `0x50388c` is an array of four-byte creature pointers. The
callback `0x306a28` uses signed halfword `0x8e733e` as the next index. A creature
with object flag `0x20`, without flag `0x40`, and with signed halfword +0x312
nonnegative is saved when flag `0x8` is clear **or** flag `0x2` is set. Thus
`0x612b` is saved despite its death bit. A saved creature gets byte +0x231 set
to `0xff`, moves off the grid through
`obj_moveOffGrid` `0x14ef48`, and its pointer is stored at array[count]. The
count increments with 16-bit wrap. An alive player is skipped. Other hidden or
dead creatures call virtual slot 1 instead; this call was stubbed in the
comparison. The callback's original body was compared for `0x2a`, `0x2b` and
the observed `0x612b` on both seeds, in addition to the earlier combinations.
Array bounds at a negative or excessive count
are not established. The saved count at `0x8e7340` then controls the next
`arena_startWave` reuse path.

### Saved player record at match end

The confirmed end-prompt branch asks `save_playerCopy` `0x21837c` once per active
slot and copies the entire `0x4c30`-byte saved player record to
`g_players[slot]` (`0x4d8af0 + slot × 0x4c30`). Four distinct generated
records matched byte for byte, including the final 0x10 bytes. The test runs
the original `arena_runTask` `0x306b78` while its UI, lookup, shutdown and
string-copy callees are stubs. The saved record is the ordinary player-record
layout in `docs/player.md` and `docs/audio-save.md`, not a small arena-specific
struct. No seed draw occurs in this copy branch.

## `player_respawn` 0x1bd040

**Executed**, 16 constructed cases per seed across local/other slot, offline/network,
mode A clear/set, and exact/free-spot placement. The old object is destroyed
through virtual slot 1; `pool_new(0x590)` supplies the new block; `Player_ctor`
`0x1a1d28` and `Player_startSpawnProtection` `0x1b8f28` are called, followed by
`game_rebuildAlivePlayers` `0x1e72f8`. In the difftest those callees were stubs;
the constructor stub updated the record's object pointer to the new block.

The direct stores are dead countdown `0x4f84a8 + slot × 2 = 240`, player-record
HP +0xac = half maximum HP +0xb0 (full maximum when mode A is set), and
`g_forceGhostRebase` byte `0x402797 = 1`. For arena arguments (2, 3),
`world_findFreeSpot` `0x14acf8` receives range 36 and radius 24, or in general
12 × argument five and 12 × argument four. The exact placement arguments
(-1, -1) skip that call. A local slot closes menus through `0x1eb000`.
Network mode checks the local slot again after rebuilding; the local branch
calls `0x207450`, `Camera_reset` `0x203210` and `0x207308` before `0x203400`,
then sends screen effect 4 through `0x322954`. The wrapper itself makes no
shared-seed draw on either tested seed. The world placement, Player constructor
and spawn-protection bodies were stubbed; their draws and side effects require
their own contracts. Allocation failure and nonzero slot addresses were not
compared here.

## `arena_shutdown` 0x304fb0

Calls `0x19e5e8` with identifier `0x551e48`. A zero answer returns without
changing anything. A nonzero answer frees the pointers at `0x503888` and
`0x50388c` through `0x150198` (even if null), clears those two words plus
`0x503890`, `0x41b500` and `0x41b4fc`, and removes run/draw tasks by passing
`0x306b78` and `0x307284` to `0x19e664`. It makes no seed draw. The lookup,
free and task services were recording stubs; the order and arguments of calls
and all five stores were compared.
