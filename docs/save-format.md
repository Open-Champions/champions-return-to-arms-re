# Memory-card saves (SLUS-20973 US v2.00)

This is the PlayStation 2 memory-card image. It is the raw `g_saveBuffer`, plus a separate
760-byte options file. It is not the native client's OCNSAVE schema.

`tools/difftest_save.py` ran the original functions in `tools/ee_emu.py` and compared them
with `tools/ref_save.py`. That is **Executed**. Nothing here was run on a console or in
Play!. A statement read from the executable and not run is **Observed**. A conclusion drawn
from those pieces is **Inferred**. A gap is **Unknown**.

The reader builds and parses synthetic images only. It does not contain a save from a disc
or a card.

## Files on the card

| File | What it is | Evidence |
|---|---|---|
| Directory `BASLUS-20973` | Product directory. `save_init` 0x216fcc writes the string at 0x88d418 with the format at 0x53ef28 and the product at 0x53ef30 | Observed |
| `BASLUS-20973_slotN` | One slot. `memcard_makeSlotName` 0x21effc takes the first unused `n` in 0..63 (`%s_slot%d`, scanning existing names with `slot%d`) | Observed |
| `BASLUS-20565_config` | Options. `save_init` writes this name at 0x88d438 (format 0x53ef40, product 0x53ef50). The browser also refers to `/BASLUS-20565` at 0x53f378 | Observed. Which name the 760-byte open actually uses is **Unknown** (below) |
| Either product in the import list | `memcard` import screen 0x21fa2c lists `BASLUS-20973` and `BASLUS-20565` (the first game). The screen was not followed through | Observed that both names are listed |

A slot file is `g_saveBuffer` at 0x895580, exactly 0x4bc78 bytes, written in one piece
(`docs/audio-save.md`). There is no magic and no file checksum. **Executed**: `save_build`
0x221914 produced that whole image, and `save_load` 0x221d60 restored a character from it
after the record-size field had been overwritten with 0x1111 (`load.ignores_record_size`).

## Slot layout

The camera and jump-gate writers always return 0xc4 and 0x1e4 in this build, so the offsets
below are fixed. `save_playerBlock` 0x2184a4 still recomputes them by calling the writers
into a scratch buffer. **Observed** for the return values; the fixed offsets are what the
executed images used.

| Offset | Size | Field |
|---|---|---|
| +0x00 | char[0x14] | Level name from `g_levelName` 0x41b721. When `g_gameCompleteFlag` 0x4f85c5 is set, the 13 bytes `gameComplete` and a NUL are stored and bytes 13..0x13 are left as they were |
| +0x14 | char[0x50] | Second name from `g_levelSubName` 0x41b771. The tail past the NUL is left as it was |
| +0x64 | u32 | Play time, `g_playTimeSeconds` 0x88d414 |
| +0x68 | u16 | Constant 0x4c30, the player-record size. Written here. A load with this half overwritten still restored the character |
| +0x6a | u16 | Listed player count. `save_build`'s second argument forces this to 1; otherwise it is the low half of `g_numPlayers` 0x4d8ae0 |
| +0x6c | u8 | Difficulty, `g_difficultyIdx` 0x4f719c |
| +0x6d | u8 | First argument of `save_build` / `save_game` |
| +0x6e | u16 | Act. The word at `g_currentAct` 0x88d3d4, stored as a half |
| +0x70 | 0xc4 | Camera. `Camera_saveState` 0x203918 |
| +0x134 | 0x1e4 | Jump gates. `jumpgate_saveDestinations` 0x27dcf4 |
| +0x318 | u32 | Minimap mode, `g_minimapMode` 0x4f8400 |
| +0x31c | u32 | `g_numPlayers`, copied as a word. The one-player argument does not change this word |
| +0x320 | 4 × 0x4c3e | Player blocks. A slot at or past `g_numPlayers` is left untouched |
| +0x13418 | quest records | Each record is 0x24 bytes, up to the level directory. The writer does not store a terminating empty name; the tail has to already be zero (`save_clearBuffer`) |
| +0x16010 | 10 × 0x18 | Level directory. Name in the first 0x14 bytes, u32 size at +0x14. Ten slots end at 0x16100 |
| +0x16100 | 0x18 | The stride the search looks at when all ten slots are full. Not one of the ten. **Observed** from the loop, **not executed** |
| +0x16118 | the rest | Level bodies, concatenated in directory order |

`save_build` writes the header, the four blocks and the quest records, then calls
`save_storeLevelState` 0x21777c. If the game is not complete and `save_findAct` 0x217d30
returns −1, `save_build` returns without writing. **Executed**: an unknown level name left
a buffer of 0x5a bytes unchanged. The game-complete path skips `save_findAct` and skips
the level store. **Executed**: the 13-byte name was written and the level directory was
left alone.

## Camera and jump gates

Camera, 0xc4 bytes, from the camera whose pointer is at `g_localCamera` 0x4f8450. A null
pointer faults. **Executed** as part of the full slot image:

1. 12 bytes, the three position floats at `g_cameraPos` 0x44f038.
2. Sixteen floats from `g_cameraMatrix` 0x44f110, a sliding window. Row start increases by
   2 and the column by 1, and each row copies four floats. The stored floats are source
   indices 0..3, then 3..6, then 6..9, then 9..12 (thirteen source floats).
3. u16 at camera +0x68, u16 at +0x6a, u32 at +0x54, u32 at +0x58.
4. Floats at +0x90, +0xd4 and +0x8c, in that order.
5. 0x60 bytes from camera +0x100.

Jump gates: the sign-extended count byte at `g_jumpGateDestCount` 0x8e3c30 stored as a
word, then 0x1e0 bytes from `g_jumpGateDests` 0x8e3a50. The function always returns 0x1e4.
Load copies the 0x1e0 bytes back and stores the low byte of the word as the count.
**Executed** inside the slot image; the load of the destinations was part of `save_load`
restoring that image.

## Player block

Each block is 0x4c3e bytes.

| Offset | Size | Field |
|---|---|---|
| +0x00 | u16 | Object bytes +0x38 and +0x39, the facing angle |
| +0x02 | 12 | Object +0x10, three position floats |
| +0x0e | 0x4c30 | The record from `g_savedPlayers` 0x879ec0 after `save_snapshotPlayer` |

`save_load` writes the facing to `g_spawnFacing` 0x4f8410 as a signed half per slot
(slot × 2) and the position to `g_spawnPos` 0x4f70d0 (slot × 0xc). **Executed** for slot 0:
facing 0x1234 and position (1, 2, 3).

If the record's object pointer at +0x43d8 is zero, the pose comes from another object and
the record copied is still this slot's. The stand-in is `g_localAliveFirst` 0x4f841c when
that index is ≥ 0 and that player has an object; otherwise the first slot below
`g_numPlayers` that has an object. **Executed**: a slot with no object took the other
player's facing and position.

`save_snapshotPlayer` 0x216c80 copies `g_players[slot]` (`g_players` 0x4d8af0, stride
0x4c30) into the saved copy. The call at 0x1bf328 is an empty return. It does not call
`player_checksum`. It then rewrites pointers in the saved copy:

- Each counted item's first word becomes a definition index (`item_encodeDefinitionIndex`
  0x107ea4): subtract 0x3f7650, arithmetic shift right 6. There is no null special case.
  Decode (0x107ec0) shifts left 6 and adds the table base. **Executed**: index 3 is the
  pointer 0x3f7710, and a zero word encodes as the shift of −0x3f7650.
- Seventeen words at +0x43f0, then +0x4434 and +0x4438, then +0x443c, become
  `bag * 1000 + slot`, or −1. `save_itemPtrToIndex` 0x216bf8 compares the address of the
  item record (bag start +0x130, stride 0x1208, item 0x48), not the definition pointer.
  A null pointer and a pointer that is not a counted slot return −1.
  `save_itemIndexToPtr` 0x216e10 returns 0 for −1 and for an index that is not a counted
  slot. **Executed**, including the null index.

Bags, counts and the rest of the record are `docs/player.md`. Counts are the signed words
at +0x1330, +0x2538 and +0x3740. A count ≤ 0 skips that bag. The object pointer is copied
raw; the snapshot does not clear it. `save_fixupPlayer` 0x216ea8 zeroes it, decodes the
definition indices, turns the equipment indices back into pointers, and calls the same
empty function. `save_load` zeroes +0x43d8 again after the fixup. **Executed**: the file
still held the object pointer, and the live record after load had zero there and the
definition pointer 0x3f7710 restored.

The one-player argument sets only the u16 at +0x6a. The block loop and the u32 at +0x31c
still use `g_numPlayers`. `save_load` uses the u32, and the loop stops at 4. A negative
count (the high bit set, signed compare) loads no players and leaves `g_numPlayers` as
stored. **Observed** from the compare; a negative count was not passed to the original.
`save_setPlayerCount` 0x218520 writes both fields. **Executed**: passing 1 made the u16
and the u32 both 1. It calls the camera-size helper, so it needs a valid `g_localCamera`.

`save_packLocalPlayer` 0x2223d4 copies the local player's block to slot 0 before a net-game
write (`docs/audio-save.md`). That function was not run here.

### Fields a client imports

`import_character` returns one record. The meanings are `docs/player.md`; the offsets
below are where they sit in the saved record. The whole 0x4c30 bytes are `Character.raw`.
An importer ignores `object_pointer`: load clears it.

| Field | Offset | Notes |
|---|---|---|
| Name | char[0x20] at +0 | |
| Appearance | s8[4] at +0x20 | |
| Class, model | s32 at +0x50, +0x54 | |
| Acknowledged level, level | s8 at +0x58, +0x59 | |
| Experience | s32 at +0x5c | |
| Base stats | s32[4] at +0x78 | Strength, intelligence, dexterity, stamina. Order **Ran** in `docs/player.md` |
| Gold | s32 at +0xe4 | |
| Skill points, stat points | s32 at +0xe8, s8 at +0xec | |
| Passives | s8[48] at +0xef | |
| Three bags | +0x130, +0x1338, +0x2540 | 64 items of 0x48. The saved first word is a definition index. Count is the s16 at item +4 (`docs/startup.md`) |
| Equipment | s32[17] at +0x43f0 | `bag * 1000 + slot`, or −1 |
| Weapon-set words, offhand | +0x4434, +0x4438, +0x443c | Same index form |
| Skill ranks | {s16 id, s16 rank}[48] at +0x4b08 | Stop at id −1 |
| Mission flags | +0x4bbf .. +0x4c0c | Difficulty `d` 1..5, mission `m` 0..12, at +0x4bbf + d×13 + m (`docs/player.md`) |
| Medals | s8[13] at +0x4c0d | |
| Evil, decisions, kind | +0x4c1a, +0x4c1b, low 5 bits of +0x4c1c | |
| Quest-list text, abilities, hit points, mana | +0x41d0, +0x4440, and the floats in `docs/player.md` | Present in `raw`. The named fields above are the ones the reader lifts out |

## Checksum

`player_checksum` 0x1bdc98 is the netplay mix (`docs/issues/sync-breakers.md` §1). It is
not a checksum of the file. `save_build` and `save_load` do not call it. **Executed**: the
function matched the model on a zero record, on 48 random records in slots 0..3, and on
the live record and the saved record of one built character (live 0x407d263f, saved
0x41331236). The same bytes at two addresses differ, because the address is mixed in.

32-bit wrap. Each byte is sign-extended. The first byte of a mix is subtracted and later
bytes are added (`mix_bytes`).

1. Start from `(address << slot) XOR 0xc18da3b1`. The shift and the later arithmetic
   shift use the low 5 bits of the slot.
2. Add the appearance term and subtract the level term. Appearance is the signed 32-bit
   product of `((s8+0x20 + s8+0x23) + (s8+0x22 + s8+0x21))` and 0x35. Levels are
   `(s8+0x58 + s8+0x59) XOR 0x023d5097`.
3. XOR the mix of the experience word at +0x5c.
4. XOR the mix of the gold word at +0xe4, multiplied by 35 with shifts
   `(((v << 3) + v) << 2) - v`.
5. Add, for each of the six words at +0x90, that word's mix times its index. Index 0 has
   weight 0, so +0x90 does not change the result. +0x94..+0xa4 have weights 1..5.
6. Subtract the mix of mana +0xc0, plus the mix of maximum mana +0xc4, minus the mix of
   pending potion mana +0xc8.
7. Subtract three times the mix of the skill-point word at +0xe8.
8. Arithmetic-shift the accumulator right by the slot.
9. Add one running mix of the 0xa88 bytes at +0x3748 (through +0x41cf, the start of the
   quest text) and one running mix of the 0x44 bytes at +0x43f0 (the 17 equipment words,
   through +0x4433).

A zero record at address 0, slot 0, is 0xbf50531a. That constant is the formula at
address 0; the executed zero record was at another address and matched the same formula.
Hit points, the bags, abilities, quest text, medals, the weapon-set words at +0x4434,
+0x4438 and +0x443c, and the bytes at +0xed, +0xee and +0x4a58 are outside the mix.

## Quest variables, act and campaign

Quest variables are the packed table `g_questVars` 0x86da80: a name, a NUL, a signed byte
(`docs/script.md`). `save_build` copies the name to the cursor and stores the value as a
word at +0x20. A value 0xfe is stored as 0xfffffffe. The record stride is 0x24. An empty
name ends the table. A name of 0x20 bytes or more overflows the field; the writer does
not check. **Executed**: names `opened` / 7 and `door` / −2 round-tripped, and load
clamped them back to signed bytes.

`save_load` calls `script_clearDeferred` 0x1eda08 and `vars_clearAll` 0x1ed728 (values
zeroed, names kept), then `vars_set` 0x1ed854, which clamps to −128..127. It stops on a
zero first byte. It does not stop at the directory. The reader's strict mode does: a
quest record that would cross +0x16010 is refused, and a name with no NUL inside 0x20
bytes is refused. Those two refusals are reader rules. The 313th record would land on
the directory. **Observed** from the sizes; a table that long was not built.

The act is the half at +0x6e. Load sign-extends it and `save_setAct` stores that word at
`g_currentAct`. **Executed** for act 0.

Campaign progress that belongs to the character (mission flags, medals, evil bits,
decision bits, kind) is in the record, above. It is not a separate section of the file.

## Level directory and level state

`save_findAct` walks the act tables. Each row is a name pointer and a u16 size, stride 8.
`g_actLevelCounts` 0x4f8e10, `g_actLevelTables` 0x4f8e48, `g_actCount` 0x4f8e7c. It tries
the current act first (skipped when the act word is −1 or that act's count is ≤ 0), then
every act. A table name matches when it is a prefix of the qualified level name
(`strncmp` of `strlen(table name)`). An empty table name matches everything. The result
is the act index, or −1.

The qualified name is `level_getQualifiedName` 0x1ec0f0: `name_subname` when
`g_levelSubName` is not empty (format `%s_%s` at 0x53e000), otherwise the level name.
The file header stores the two parts separately. The directory stores the qualified
string.

`save_storeLevelState` returns 0. It writes nothing when `g_memcardState` 0x88d3a0 is 4,
or when the word at 0x44fe08 has bit 0x800 set. **Executed** for both: the header was
written and the directory was not. The game-complete branch inside the store uses the
constant size 0x88b8 and skips the lookup, but `save_build` does not call the store when
the game is complete, so that branch runs only on a direct call. It was not executed.

Otherwise the reserved size is a u16 from the current act's table. A qualified name whose
first three bytes are `hub` (the string at 0x53ea80, length 3) forces row 0 and does not
search. `hu` does not match, and the compare is case-sensitive. Any other name uses
`save_levelIndexInAct` 0x2187a0, which searches the current act only and returns −1 when
`g_currentAct` is −1; a miss writes nothing. **Executed**: `hub_west` with row 0 named
`town` at size 0x1800 and row 1 named `hub` at size 0x1000 stored the directory name
`hub_west` and the size 0x1800, the whole 0x4bc78 image matching.

The directory is `g_saveLevelDir` 0x8ab590, which is the buffer at +0x16010. The search
walks ten slots. An empty first byte is a free slot. An exact name updates that slot and
does not rewrite the name or the size; the body offset is the sum of the sizes before
it. A new slot copies the qualified name and the reserved size before the fit check.
The fit check is an unsigned compare of `0x16118 + prior + size` with 0x4bc78. If the
file is smaller, `save_writeLevelState` is not called and the new name is left in the
directory. **Executed**: a prior size of 0x40000 left the new name `crypt` in slot 1 and
left the body bytes alone. A single u16 size always fits. What the eleventh name does
with the 0x18 bytes at +0x16100 was not executed. The model stops after ten slots.

`save_writeLevelState` 0x218600 calls `level_getQualifiedName` and does not use the
result for the bytes. The budget passed to the world writer is the reserved size minus
the word at 0x4044d0 minus 0x18. That word is 0x16c8 in this executable (the difftest
stops if it is not). The body, on a buffer `save_clearBuffer` has zeroed:

| Offset in the body | What |
|---|---|
| +0 | u32, the world writer's return |
| +4 | Four bytes the writer does not store. They stay zero on a cleared buffer |
| +8 | World body, that many bytes. `world_saveState` 0x14e5c8 |
| then | u32, the decal writer's return, four bytes not stored, then the decal body |
| then | Automap, 0x16c8 bytes, no length. `automap_packExplored` 0x16865c |

**Executed** on the executable's empty grid (`g_grid` 0x5db4f0 is zero, the decal table
at 0x846458 is zero, the automap span is zero): the world return is 8 and the body is
u16 0, u16 1, u32 8. The decal return is 8 and the body is eight zero bytes. The automap
starts 32 bytes into the blob. A reserved size of 0x2000 left the rest of that slot
untouched. The same automap function matched all 0x16c8 bytes of a patterned grid.
`world_writeRecords` 0x14e140 was not stubbed; its non-empty object records are
**Unknown**. A negative world return is stored and the cursor moves backward.
**Observed** from the stores, not executed.

`decal_serialize` 0x19ee10 writes a zero word and returns 8 when the budget is below
0x15. Otherwise it walks a 15×30×30 pointer table. The empty table was executed (count
0, return 8). A live decal's 12-byte fields were not executed. When records fit, the
return is 8 + 12 × count. **Observed** from the function, not executed with a decal.

The automap has no returned size. It writes 108 × 54 = 0x16c8 bytes from `g_automapGrid`
0x4044f0. Outer rows step by 2 while the row index is below 0xd8; the row base starts at
0 and adds 0x1b0. Each row emits 54 bytes. The address starts at `grid + (row_base << 1)`
and adds 8 per byte. The byte is `(grid[off + 1] & 0xf0) + (grid[off + 5] >> 4)`. The
highest byte read is at grid offset 0x16acd. A short grid reads as zero past its end.

`save_init` rewrites every act-table u16 in place to
`(original + the half at 0x4044d0 + 0x3e8) & 0xff80`. The half is 0x16c8, so a zero
original becomes 0x1a80. **Observed** in `save_init`; the function was not executed
because it talks to the card. The arithmetic is `round_reserved`. **Inferred**: a booted
game's directory sizes are these rounded values, because the store copies whatever u16
is in the row at the time.

`save_clearBuffer` 0x21f144. **Executed**:

- If `g_saveClearBlock` 0x4f8f2a is nonzero, only the word at 0x4f9234 is cleared. The
  buffer stays.
- If the argument is nonzero, the whole 0x4bc78 is cleared and that word is cleared.
- If the argument is zero, the first directory name is kept, and as many level-data
  bytes as the u16 of act 0's first row are copied back to +0x16118. The size stored at
  the first directory entry is that row's u16, not the size the entry had. The word at
  0x4f9234 is cleared.

When the game is not complete, `save_build` calls the level store and then sets the word
at 0x4f9234 to 1 (0x221d1c–0x221d38). The call returning without a new body still leaves
that word set. The game-complete path skips both. **Observed.** The word is outside the
slot image, and the executed runs did not read it back.

## Options

The options file is 0x2f8 (760) bytes, a raw image of `g_savedConfig` 0x4f8f38. No
checksum. `memcard_saveConfigScreen` 0x21f4a4 queues a write of that length from
`g_savedConfig` (op 5) and queues the open from the string pointer at 0x88d418.
**Observed.** `save_init` puts the product directory at 0x88d418 and
`BASLUS-20565_config` at 0x88d438. Whether the browser copies the config name over
0x88d418 before that open is **Unknown**.

`config_setDefaults` 0x1e6238 writes the image. `music_applyVolume` 0x215e78 has to be
stubbed to run it here. **Executed**, the whole 760 bytes, for scheme byte 0x41b69c
equal to 1, equal to 0, and equal to 2, and for a single button row (`which` = 1) on a
dirty image.

`which` = −1 writes the scalars and all four button rows. A slot index writes only that
row. Scheme 1's row is 0x40, 0x20, 0x10, 0x80, 0x08, 0x02, 1, 0x400, 0x04. Scheme 0
swaps the first three masks and keeps the rest. Any other scheme leaves the button row
as it was. The scheme byte in this executable is 1.

Scalars, and the global that held the same value after `which` = −1. **Executed** by
reading both.

| Image | Default | Global | Name (`docs/issues/sync-breakers.md` §7, except the unnamed word) |
|---|---|---|---|
| +0x00 | 0 | | |
| +0x04 | 0.5 | 0x44fd80 | Brightness |
| +0x08 | 0.5 | 0x4f8944 | Music |
| +0x0c | 0.5 | 0x4f8940 | Effects |
| +0x10 | 1 | 0x4f8948 | Stereo |
| +0x14 | 1 | 0x41bfb0 | Vibration |
| +0x18 | 1 | 0x4fdcc8 | Unnamed |
| +0x1c | 1 | 0x44fcf4 | Subtitles |
| +0x20 | 1 | 0x44fcf8 | Damage numbers |
| +0x24 | 0 | 0x44fdc0 | Blood / decal detail |
| +0x28 | 1 | 0x4f8458 | Markers |
| +0x2c | 1 | 0x4f845c | Combat camera |
| +0x30 | 0 | 0x4f8460 | Reverse yaw |
| +0x34 | 4 × 9 words, stride 0x24 | | Button masks, four slots. Ends at +0xc4 |

The five words at +0xc4 are the word 1, the bits 0x3e199999, the float 0.5, the word 1,
and the word 0. After the same call the four voice globals were 0x505af0 = 0x3e199999,
0x505af4 = 0.5, 0x505afc = 0 and 0x505b00 = 1 (`docs/issues/sync-breakers.md` §7). Which
image word pairs with which global was not traced: +0xc4 and +0xd0 are both 1.
**Unknown** pairing. The 0x20 bytes at +0xd8..+0xf7 are unnamed. `config_setDefaults`
does not clear them.

`g_profileVars` 0x4f9030 is this image at +0xf8 (0x4f9030 − 0x4f8f38). It is the packed
profile table, a name, a NUL, a signed byte, the same form as the quest variables
(`docs/script.md`, `setpv` / `getpv`). The reader lists those entries and stops at a zero
byte. `config_setDefaults` does not clear this tail.

## Load path

`memcard_requestLoad` 0x2176e0 stores `g_inFrontend` into byte 0x8e1ab8 and its flag
argument into byte 0x8e1ab9, then `memcard_setState(4)`. **Observed.** The screen itself
was not executed.

`memcard_loadScreen` is a 10-step table at 0x53f1d0 (the index must be below 10). Step 4,
at 0x2196c0, reads 0x4bc78 bytes and copies them into `g_saveBuffer`. If byte 0x8e1ab9
is zero, `save_load` is not called and the screen ends. If it is nonzero, `save_load`
runs and the step advances. Step 5, at 0x21984c, builds the live qualified name and
compares it with the string at 0x8e1a98. Equal ends the screen (pause popped, card state
−1). Unequal leaves the step at 5, so the compare runs again. **Observed** from the
table and the branches. The screen's compare was not executed.

`save_load` 0x221d60, **Executed** on the crypt image and on a `hub_west` image:

1. Copies the 0x70-byte header to `g_saveHeaderCopy` 0x879e38.
2. Restores the camera and the jump gates. Their return sizes advance the cursor.
3. Restores the minimap mode and `g_numPlayers` from the u32 at +0x31c.
4. For each slot below that count, and at most four: pose into the spawn fields, record
   into `g_players`, `save_fixupPlayer`, then zero the object pointer.
5. Clears deferred scripts and quest values, then `vars_set` for each quest record.
6. Sets `g_loadedFromSave` 0x8e1ad6 to 1, the act, the difficulty (the byte is
   sign-extended; the executed value was 2), and the play time.
7. Builds the pending level at `g_pendingLevel` 0x41b6d0. A non-empty subname uses
   `%s_%s` at 0x53fb70. Otherwise the level name is copied. Byte 0x41b720 becomes 0xfd.
8. Copies the level name to 0x8e1a98. A non-empty subname appends the underscore at
   0x53fb78 and then the subname. **Executed**: both the pending name and 0x8e1a98 were
   `hub_west`. The live qualified name uses the same `%s_%s` (0x53e000), so a subname
   does not by itself make step 5 disagree. **Inferred** from the two formats and the
   executed strings; the screen compare was not run.
9. If the word at 0x4f85b4 is 1, calls `inventory_shareQuestItems(0)` and clears the
   word. **Observed.** The executed loads set the word to 0, so the call did not run.
10. Sets `g_autosaveCountdown` 0x88d40c to 99.

The level bodies are not parsed here. The level loader consumes them (`docs/audio-save.md`).

`save_load` checks no magic, no checksum and no record-size field, and the only clamp on
the player count is that the loop stops at 4. **Executed** for a rewritten record-size
field; the other absences are the function having no such compare (**Observed**) together
with a load that completed.

The reader's strict mode is tighter, and these refusals are reader rules, not original
behaviour:

- The file is exactly 0x4bc78 bytes, and the options file exactly 760.
- The record-size field is 0x4c30.
- The u32 player count is in 0..4. The u16 is reported separately as `listed_count`,
  because the one-player argument can make it differ.
- A quest name has a NUL inside 0x20 bytes, and the record does not cross +0x16010.
- A directory name has a NUL inside 0x14 bytes, and the sum of the directory sizes fits
  in the file.
- A bag count is in 0..64.

A level body whose framing does not fit inside its directory size is reported on that
level and does not refuse the character, as long as the directory sizes themselves fit.

## Reader

`tools/ref_save.py`

| Call | Result |
|---|---|
| `parse_slot(data, strict=True)` | One slot image |
| `import_character(data, index=0, strict=True)` | One character |
| `parse_config(data, strict=True)` | The 760-byte options image |
| `player_checksum(slot, address, record)` | The netplay mix |
| `build_slot`, `config_set_defaults` | Synthetic images for tests |

`tools/test_ref_save.py` uses synthetic images only. `tools/difftest_save.py` compares
the builders and the checksum, the automap, the item indices, the options image, the
slot image and `save_load` with the original functions. It skips, exit 0, when the
executable is absent.
