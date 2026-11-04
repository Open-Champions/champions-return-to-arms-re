# Save/load screen art and layout — SLUS-20973 v2.00

2026-10-23, with the play-flow section added 2026-11-03. This is research
for the shared native client, not a native change.
The original ELF is pinned by SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
`tools/difftest_save_screen.py` executes original functions in `tools/ee_emu.py`
against authored memory at seeds 20973 and 7; `tools/ref_save_screen.py` holds the
numeric reference. **Executed** below means that bounded synthetic test, not a
Play! or console capture. **Observed** means the code or named asset structure at
the stated address was read. Round 2 also read one completed slot file from the
existing Play! rig without modifying it. No live card-screen capture, localized
text, texture pixels, or retail screen was captured.

Prior evidence: `t3/research-menus` `docs/menus.md` and
`t3/research-menus-layout` `docs/frontend-layout.md` at `29c90a5`, plus
`t3/research-saves` `tools/difftest_save.py`. This document extends their
forced-state card captures with save/load specific row data, art selection,
preview fields, prompts, and input. The native menu art report is
`open-champions/worktrees/menus/work/loop-menus-art-r1-report.md`.

## Entry and screen phases

| Field or function | Evidence | Meaning |
|---|---|---|
| `g_memcardState` 0x88d3a0 | **Observed** dispatch 0x2189e0 | 3 saves, 4 loads. This is the outer screen selector. |
| `memcard_saveScreen` 0x218afc | **Executed** 0x218b44, 0x218bcc | Looks up `menu_savegame`, calls `memcard_browser` 0x219b90 while browser stage 0x88d3e4 is zero, then calls `memcard_slotList` 0x21c3a4 while slot stage 0x88d3d8 is zero. |
| `memcard_loadScreen` 0x219360 | **Executed** 0x2193ac, 0x2193f8 | Same two-stage route, with `menu_loadgame` and `MemcardLoad` keys. |
| Browser state 0x88d3e0 | **Observed** jump table 0x53f440; prior **Executed** 35 forced states | Card check, format and errors precede the slot list. `hud_drawMessageBox` 0x1df248 supplies shared prompts. |
| Slot state 0x88d3dc | **Observed** jump table 0x53f7f0; **Executed** selected states | 4 draws and accepts the list, 5 is overwrite confirmation, 9 is delete confirmation, 15 is an error prompt. The test forces states independently; it does not assert a full live sequence. |
| `g_cardXferLatch` 0x4f8f28 | **Observed** 0x218ba4, 0x218c18, 0x2195a8, 0x2190d0 | Set when a save/load slot is committed, cleared after clean completion as documented in `docs/issues/sync-breakers.md` B10. |

## The art actually selected

**Executed:** `memcard_slotList` submits two `ui_drawFrame` 0x17fbb8 calls,
at 0x21d814 and 0x21e548. In the settled fixture both pass
`(x=61, y=126, w=519, h=97, layer=6, tint=0x7f616369)`; their last flags are
1 and 0. The wrapper at 0x17fbb8 adjusts the rectangle to
`(60,122,521,105)` and **forces frame style 2** at 0x17fbd0. The frame
implementation 0x17c118 chooses the style-2 prefix `tile` at 0x17c1b4.
Its resource lump is `interfac.lmp` at 0x17c194. This corrects any reading of
the wrapper's final flag as the texture style.

**Observed:** format strings at 0x5340b8–0x534138 form nine `tile*.tex`
lookups: `tiletopleft`, `tiletopright`, `tilebotleft`, `tilebotright`,
`tileleft`, `tileright`, `tilebot`, `tiletop`, `tilecenter`. The read-only
`INTERFAC.LMP` directory/header check finds all nine: center 320×224, each
other piece 32×32. These are source texture dimensions, not the on-screen
piece rectangles. A second **Executed** fixture follows `ui_drawFrameImpl`
with authored texture descriptors matching those header dimensions. The first
wrapper call makes 40 tile submissions to 0x17b590/0x17b8b0: four corners at
`(60,194)`, `(549,194)`, `(60,121)`, `(549,121)`; top and bottom strips at
`x=92+32i`, `i=0..14`, `y=122/195`; left and right strips at `x=60/549`,
`y=154/186`; and two center submissions at `(67,128)` and `(387,128)`.
The second wrapper call, whose final stack flag is 1, makes no tile submission
in this fixture. All nine texture names reach the resource lookup. Exact
cropping, alpha blending and GPU pixels remain **Unknown** because resource
lookup and packet generation were replaced with authored descriptors/stubs.

**Executed:** no dedicated card icon sprite or `ui_drawSprite` submission
occurs in the followed slot-list body for the populated fixture. The browser
uses `hud_drawMessageBox`; the prior `MESSAGE_BOX_CALLS` capture on
`t3/research-menus-layout` puts its shared frame at `(60,186,520,68)` plus
the inner `(68,196,520,68)`, with small-font text. A card-specific picture
must not be chosen from an asset count alone. **Unknown:** what the full
front-end background shows behind these calls, and the finished retail pixels.

## Typography, rows and selection

**Executed:** `memcard_slotList` starts `text_begin` 0x1800b8 at 0x21c404
with the small-font pointer read from 0x4f7104, layer 6, base colour
`0x001e6464` with fade word 0x8e11f8 placed in the alpha byte. The settled
fixture has alpha 0x7f. The later batch at 0x21d830 uses the same small font,
layer 6, `0x801e6464`; colour calls include 0x21c6f8 (`0x7f3c4646` in the
fixture) and 0x21d850 (`0x7f323c3c`). These alpha values are fixture states,
not constants for all frames. The title is centered at `(320,110)` at
0x21d6e8. Text width and localized glyph rendering are stubbed.

**Executed:** five visible rows are considered, with `y=128+17r` for
`r=0..4`. The scroll base is 0x879e2c. Each visible numbered row submits
ASCII at `(77,y)` from 0x21d99c. A populated row additionally submits the
level line wide at `(100,y)` 0x21da8c, date ASCII at `(365,y)` 0x21db24,
and clock ASCII at `(487,y)` 0x21dbe8. With `g_memcardState=3` (save), the
first free row uses `MemcardNewSave` and wide text at `(100,y)` 0x21d9f4;
with `g_memcardState=4` (load), an empty list submits no rows. Rows beyond
the cache count retain only their numbered marker when count is nonzero.
The fixture covers counts 0, 1, 2, 5 and 6 in both modes, plus count 8 in the
indexed-row probe. The source does not establish that a real card holds eight
usable entries.

**Executed**, now with a settled nonzero scroll and distinct rows: the list
count is read from 0x4f9238. Visible row `r` uses index `0x879e2c + r` at
0x21d930–0x21d950. The metadata address is `0x88d300 + 16*index` at
0x21da10–0x21da24; the cached header address is
`0x8e1200 + 0x70*index` at 0x21da18–0x21da74. For scroll base 2 and count
8, `indexed_rows` passed headers 2–6 (0x8e12e0 through 0x8e14a0) and each
distinct date/clock on both seeds. The committed probe also checks five
`%d.` formatter calls with values 3–7 at 0x21d94c, paired with five numbered
ASCII draw submissions at 0x21d99c and y=128+17r. Text formatting and glyph
rendering remain stubbed. The target scroll word 0x879e30 must also be 2;
otherwise the list updates 0x879e2c back to zero at 0x21c9dc–0x21c9f8. Header +0x64, +0x6a,
and +0x6c feed play time, player count, and difficulty. These index and stride
calculations are **Observed** at the stated addresses and **Executed** in the
settled fixture. Actual card capacity and scroll reachability remain **Unknown**.

**Observed and Executed** in `date_boundary` and `clock_boundary`: the date
formatter call at 0x21db0c receives `%d/%d/%d` and single-digit BCD month/day
arguments `(1,9,2026)` from metadata bytes +6, +5 and +7 (year plus 2000).
That format requests no zero padding; the text formatter itself is stubbed.
The clock at
0x21da24–0x21da70 and 0x21db30–0x21dbec turns BCD +3 (hour) and +2
(minute) into `%d:%s%d%s`: 00:05 → `12:05am`, 11:10 → `11:10am`,
12:00 → `12:00pm`, 13:25 → `1:25pm`, and 23:59 → `11:59pm` on both seeds.
The minute below ten gets a leading zero; the suffix is lowercase and has no
space. Real card directory timestamps and locale-dependent display remain
**Unknown** because the completed slot file does not contain those directory
metadata bytes.

### Completed slot file check

**Read only:** the existing, previously run Play! rig's
`local/rig-out/run6-6/data-b/vfs/mc0/BASLUS-20973/BASLUS-20973_slot0`
under the original checkout is 310,392 bytes (0x4bc78), SHA-256
`c969195418643f79e31ddc493ad30c3cd5c24802be0aa34614fb584299027796`.
Its 0x70-byte header contains level identifier `strife` with an empty second
part, 59 play seconds, one player, and difficulty index 1. This is a finished
slot record, not a fabricated header. The committed optional `--completed-slot`
probe verifies size, SHA-256 and the three header fields before running
`memcard_slotList` on seeds 20973 and 7 with debug both off and on. The
original function passes that header to the level-label lookup at
0x21da74/0x22233c; the localized
level text is **Unknown** with lookup stubbed. With the record loaded into the
cache, the single-player branch at 0x21e194–0x21e208 and difficulty key
`memcardDifficulty1` at 0x21e258 execute on both seeds. The debug-only time
line at 0x21dd48–0x21e0f0 selects `MemcardBrowseMinutes` and passes numeric
1.0 for 59 seconds to the value submission at 0x21e088 (0x21dd94–0x21ddb8
clamps zero minutes to one). With debug
off, that line is absent. The character/class suffix uses separate cache state
at 0x88cf80/0x4f8e80; this record check does not establish its displayed
text. The real directory timestamp, localization, and rendered pixels were
not captured.

**Executed:** selection rectangle 0x21e508 follows displayed selection word
0x879e28: endpoints `(66,133+17r)` to `(574,152+17r)`, layer 6. The base
colour is `0x00366876` at 0x21e4c8, with an alpha computed from fade and
interpolation; the fixture submits `0x3f366876`. A second tile frame follows
at 0x21e548. There was no explicit text clip in this fixture. This rectangle
is **Inferred** to be the selected-row highlight from its motion with
0x879e28; forcing an out-of-count row also moves it, so the test alone does
not prove retail cursor bounds.

## Selected-slot summary and prompts

**Executed:** with a populated synthetic header selected, the summary draws
`MemcardSavePlayers` at `(220,247)` (0x21dce4/0x21dd00) and
`MemcardDifficulty` at `(220,264)` (0x21dd10/0x21dd28). Values appear at
`(320,247)` 0x21e208 and `(320,264)` 0x21e2c0. Header +0x6a drives the
player count and +0x6c selects one of the difficulty lookup keys at
0x21e230–0x21e2b4. When debug byte 0x4f8ee0 is nonzero,
`MemcardSaveTime` appears at `(100,281)` 0x21dd48/0x21dd60 and the value at
`(320,281)` 0x21e0f0 from header +0x64. With that byte zero the save-time
line is absent. **Unknown:** all localized strings, text widths, and some
single-character character/class description branches at 0x21e194–0x21e208;
the basic fixture's artificial header is not a validated save file. The
completed-record check above verifies the header-backed routes separately.

| Slot state | **Executed** lookup keys and draw anchors | Input result in the settled fixture |
|---|---|---|
| 4 list | title `(320,110)`; save mode adds `MemcardNewSave` at the first free row | confirm mask 0x40 on the first populated slot enters state 5; bit 0x80 enters state 9; repeat mask 0x204000 advances selection one row when another cached slot exists; cancel mask 0x20 starts the back fade (0x21ccc0) |
| 5 overwrite | `MemcardConfirmOverwrite` `(320,264)` 0x21cedc/0x21cf34; `MemcardContinueBack` `(320,320)` 0x21cf54/0x21cfa4 | bit 0x20 returns to 4; bit 0x80 enters 11 and marks write intent at 0x88d400. The file write is the screen machine in the play-flow section, after this list returns 1. |
| 9 delete | `MemcardConfirmDelete` `(320,247)`, `MemcardDeleteSlot` `(320,264)`, `MemcardYesBack` `(320,320)` at 0x21d234–0x21d328 | bit 0x20 returns to 4; confirm bit 0x40 starts a fade before the delete queue path (0x21d360–0x21d3c0). |
| 15 error | `MemcardError` `(320,196)`, `MemcardMissingError2` wrapped at `(320,230)`, `MemcardContinueBack` `(320,320)` at 0x21d4f0–0x21d6bc | Key and anchors verified; the text and card result type are **Unknown** for this artificial state. |

Button labels depend on the configured scheme word at 0x41b69c; these are
**button masks**, not an unconditional promise about face-button names. The
normal scheme's masks were executed on `t3/research-menus` at
0x1e6b68. `memcard_slotList` reads owner raw-pad words from 0x4028d0 at
stride 0x58, using slot byte 0x4f923c, edge +0x0c and repeat +0x10
(0x21c478–0x21c4ac). This is per-machine draw-task UI.

## Play flow: confirm, write, and which world a load restores

2026-11-03. `tools/difftest_save_screen_flow.py` walks the original screen
functions in `tools/ee_emu.py` at seeds 20973 and 7. Card queue, text, frame
and the diagnostic print are stubbed. Inside `save_build` and `save_load`, the
camera, jump-gate, player-fixup and quest callees return the sizes already
measured by `t3/research-saves` and `t3/research-death-reload`; this section
does not add object-record or camera evidence. The world body stays
`t3/research-save-world` `e7d8972` `docs/save-world.md` lines 68–102. Death
reload stays `t3/research-death-reload` `2c95314`
`docs/death-reload-sequence.md` lines 49–88 and 116–180.

The state-4 compare at 0x21caa4 is the cursor float at 0x879e34 against 0
(**Observed**). **Executed:** bit pattern 0x3f000000, with 0x879e24 equal to
0x879e28 and the confirm mask held, leaves slot state 4, 0x4f8ef4 at 0xa5 and
the fade step at 0x2a. Those three were planted for that call. Unequal row
words, with the float at 0, leave the same three. Bit pattern 0x3f800000 is
the snap at 0x21ca3c: the float is cleared and 0x879e28 is copied from
0x879e24, so the compare then sees 0 and a free row arms. Draw helpers return
0 and the card pump returns 0. Those stubs do not write the three words.

On a save screen whose card state is 3, the free row is 0x879e2c plus
0x879e28. **Executed** with both scroll words (0x879e2c and 0x879e30) at 1
and the cursor at 1, against cache count 2: the call leaves slot state 4,
stores 7 at 0x4f8ef4 and sets the fade step to −16 (0x21cb2c). A mismatch
copies 0x879e30 over 0x879e2c before that add (0x21c9f8). When the fade
reaches 0, the list queues card operation 8 and enters slot state 7
(0x21cce8). State 7 waits until the countdown at 0x88d3c4 has run down and
the fade step is positive, then compares 0x88d3ac with 0x88d3ec plus the low
bit of the cache count (**Observed** at 0x21cd68 and 0x21cd74). The pump stub
returns 0, so the compare runs. **Executed:** count 2, 100 against 100 sets
the fade step to −16 and stays in state 7; 99 looks up
`MemcardNeedFreeSpaceBrowser` and leaves the planted fade step at 8. Count 3
moves the threshold up by 1: 100 against 100 takes that short path, and 101
against 100 sets the fade step to −16. With the fade already 0, state 7
becomes 12. What those two words count is **Unknown**. Overwrite confirm
(state 5, mask bit 0x80) still enters state 11; state 11 queues operation
0x0a on `/BASLUS-20973` and enters 12 (0x21d3f4). State 12, with the pump
idle, 0x4f9540 non-negative and the fade at 0, returns 1 and clears the slot
state (0x21d474). That return is what the save and load screens treat as a
committed slot.

The save screen's own step is the word at 0x88d3a8, indexed through the table
at 0x53f170 (**Observed**). **Executed** in order:

| Step | What the original function did |
|---|---|
| 0 | If byte 0x8e1ad8 is nonzero, or the selected index equals the cache count, `memcard_makeSlotName` 0x21effc runs. **Executed:** a set byte with cache count 0 writes `BASLUS-20973_slot0` at 0x879d08. A clear byte with the index and the count both 0, and an empty directory, does the same and does call 0x21effc. A clear byte whose index equals a count of 1, 2 or 3 still calls 0x21effc, and that empty directory makes the name `BASLUS-20973_slot1`. The product prefix for the set-byte cases was supplied at 0x88d061; who fills that prefix in the browser was not run. Otherwise the name is copied from 0x88d060 + index×64. An occupied row copied `BASLUS-20973_slot1` and did not call 0x21effc. This step does not queue the image write. The writer of 0x8e1ad8 is **Unknown**. |
| 1 | Offline, `save_build` 0x221914 is called as `(slot byte 0x4f923c, 0)`. **Executed** with slot byte 3 and `g_numPlayers` 5: the recorded pair is (3, 0). The camera returns 0xc4, the jump-gate returns 0x1e4, and `save_storeLevelState` is the recording stub; none of those supply the pair. The image at 0x895580 then begins with the live level name, and that stub is called with the same name. Network byte 0x402791 calls `save_packLocalPlayer` 0x2223d4 instead, and does not call `save_build`. |
| 2 | Queues open mode 0x202 of the name at 0x879d08, write operation 5 of 0x4bc78 bytes from 0x895580, close, then file info. |
| 3 | Sets byte 0x4f8f29 and the fade step to −16. The next call, once the fade is 0, advances to step 4. |
| 4 | Looks up `MemcardContinue` and `MemcardSaveComplete`, plus `MemcardSaveGood2` for a new row or `OverwriteGood` for an occupied row. Confirm sets the fade step to −16. When the fade reaches 0 the latch at 0x4f8f28 is cleared and `memcard_setState` stores −1. |

A nonzero card result at 0x88d3bc moves the save screen to step 9 and calls
`memcard_closeFile` 0x21e5c8. That path does not clear the latch, and it does
not write the card state: a prepared 3 is still 3, with no store to 0x88d3a0.
**Executed:** the cancel that follows calls `memcard_setState` 0x21f238, which
stores −1 at 0x21f254. While slot stage 0x88d3d8 is still 1,
`memcard_requestSave` 0x2175b4 returns without opening the screen. The
pending-level byte suppresses that call only when network byte 0x402791 is
set. **Executed** four ways, with `dialog_isOpen` and `memcard_popPause`
returning 0: offline with the pending name clear or set, and network with the
name clear, all call it at 0x2192f4; network with the name set does not. The
latch stays 1.

`memcard_requestSave` itself opens only from card state −1, with 0x88d3c8 and
0x88d3d8 both 0, and only when some player is counted living (**Executed** for
one player whose object is present, whose object flags at +0xc have bit 3
clear, and whose record float at +0xac is 1). No counted player leaves the
card state unchanged. A negative hit-point value and a set bit 3 were read at
0x2175fc–0x21761c and were not executed. `memcard_requestLoad` 0x2176e0 stores
its slot argument at 0x4f923c, copies byte 0x41b510 to 0x8e1ab8, stores its
flag argument at 0x8e1ab9, clears the latch, and sets card state 4. A nonzero
word at 0x88d3c8 makes the call return without opening (**Executed**). The
latch sentinel 0xa5 is still there on that return. The opening call stores 0
at 0x217760.

Load acceptance copies all 0x40 bytes from 0x88d040 + index×64 to 0x88d2c0,
including the bytes past the name (**Executed** at 0x2194a4), and sets the
load step to 0 (0x21948c). The slot list is stubbed to return 1 for that
call, so the list is not re-run. With the pump stub returning 0, the latch
is stored as 1 at 0x2195a8 over the sentinel 0xa5; the step word is still 0
and the fade step is still 16. **Executed:** step 2 queues open mode 1 of
the name at 0x88d2e0, read operation 3 of 0x4bc78 bytes, and close. Step 4
copies those bytes into `g_saveBuffer`. When 0x8e1ab9 is 0, `save_load` is
not called, a latch planted at 0xa5 is cleared, the card state becomes −1
and the step word is cleared. When the flag is 1, original `save_load`
0x221d60 runs and the latch is 1 afterward, over that same sentinel. For a
header name `strife` and an empty subname, pending level 0x41b6d0 and the
side name 0x8e1a98 are both `strife`. For `hub` plus subname `west`, both
are `hub_west`. The marker at 0x41b720 becomes 0xfd and the loaded flag
0x8e1ad6 becomes 1. The live level name at 0x41b721 is left as it was. The
0xf0 directory bytes at image +0x16010 and the word at +0x16118 are still
the planted sentinels after step 4, flag 0 and flag 1. The word at +0x16100
is the gap after those ten entries, not the directory. This call does not
consume the level directory. `save_load`'s camera, jump-gate, player-fixup
and quest callees are stubbed and return the sizes in `docs/audio-save.md`.
`world_loadRecords` 0x14e808, `level_loadScriptAndObjects` 0x217978 and
`save_reload` 0x22266c are not stubbed and are not called.

Step 5 builds the live qualified name with 0x1ec0f0 from 0x41b721 and 0x41b771
and compares it with 0x8e1a98 (**Observed** at 0x21984c, **Executed**). A
different live name leaves step 5, the latch at 1 and the card state at 4. The
same live name, including `hub` plus `west` against `hub_west`, sets the card
state to −1 and clears the latch. The screen is therefore waiting for the
level change it just requested. It is not applying the saved world.

That split is the one the other two notes already measured. `save_load` only
requests the header's level; `level_loadScriptAndObjects` is what later copies
a matching directory body in and constructs its records
(`docs/save-world.md` lines 81–91 on `t3/research-save-world`). Death reload
never opens this screen. `deathTask` calls `save_reload`, which calls the same
`save_load` on the checkpoint already in the buffer, and the following loader
still stops at syscall 124 before world reconstruction
(`docs/death-reload-sequence.md` lines 71–88). Lines 144–176 of that note
are later stops, a store through a null particle slot and `TerminateThread`
syscall 37, and both still precede world reconstruction. A dismissed save
box is not a death reload, and a finished card read is not a restored level.

## What the client can implement

1. The five-row list, dates, clock and preview already in this note, and a
   confirm that is ignored while 0x879e34 is neither 0 nor the 1.0 snap, or
   while 0x879e24 and 0x879e28 differ. The 1.0 snap copies the settled row.
2. The free-row save start, including a nonzero scroll whose sum is the cache
   count, the free-space compare with the cache count's low bit, the overwrite
   confirm, and the list's return of 1 once its card step is idle.
3. The save machine: fresh name versus the existing directory name, offline
   `save_build(slot byte, 0)` or the net pack, one 0x4bc78-byte write, the
   new-slot or overwrite saved box, and a dismiss that clears the latch. An
   error keeps the latch and leaves card state 3; cancel stores −1. A pending
   level name suppresses the save request only together with the network byte.
   Treat a same-call reopen as absent while 0x88d3d8 is still 1.
4. The load machine: copy the whole 0x40-byte directory record, read 0x4bc78,
   call `save_load` only when 0x8e1ab9 is set, and take the pending world from
   the header (`name` or `name_sub`). Hold the screen until the live level
   name matches. Leave the 0xf0 directory bytes and the word at +0x16118 for
   the level loader in the save-world order. Do not route this screen through
   `save_reload`, and do not drop the death-reload refusal.

Localized strings, pixels, real directory timestamps, the units of the
free-space words, the writer of 0x8e1ad8, and a retail card capture stay
**Unknown**. Object-record load effects stay the save-world unknowns. Death
reload stays blocked at syscall 124 (lines 71–88), and at the later stops
in lines 144–176, all before world reconstruction.

## Ordered native port list

1. Reuse the disc-selected **small font** and localization lookup for title,
   rows, preview and prompts. Do not render card names from a host font.
2. Load the nine named `tile*.tex` pieces from `INTERFAC.LMP` at runtime and
   implement the 0x17fbb8 wrapper plus 0x17c118 nine-piece frame. Verify the
   resulting rectangles and alpha in a graphical capture before calling it
   visually equivalent.
3. Build the card-browser stage and shared message boxes, preserving save/load
   titles, pending/error prompts and the two-stage routing at 0x218afc/0x219360.
4. Populate the five-row list from real card directory entries and cached
   save headers, using the strides and the completed-record preview above.
   Drive confirm, the free row, overwrite, the 0x4bc78 write and the load's
   pending world from the play-flow section. Leave the world body and death
   reload on their own notes.
5. Compare native captures with a permitted real-card capture for text width,
   card icons, language, frame tiling and fades. Those remain **Unknown**.

## Reproduction and limits

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_screen.py
local/SLUS_209.73 local/disc.iso --completed-slot local/BASLUS-20973_slot0`
passed **189 checks** across seeds 20973 and 7, including indexed numbered
rows, the single-digit date format, clock boundaries, read-only tile header
dimensions, and completed-record preview branches with debug on and off.
The companion `difftest_frontend_screens.py`, `difftest_frontend_art.py`, `difftest_menus.py`
and `difftest_save.py` on their existing research worktrees also passed.
The full Python unit suite passed 652 tests. The art difftest follows
the original UI control functions, frame wrapper and frame implementation
with authored texture descriptors; resource lookup, text shaping, card I/O
and GPU presentation are stubbed. It proves call
submissions and selected state changes under authored inputs, not pixel or
memory-card parity.

On 2026-11-03 the same ELF-only art command, without the disc or the
completed-slot argument, passed 176 checks. `python3
tools/difftest_save_screen_flow.py local/SLUS_209.73` passed 120 checks at
seeds 20973 and 7, and the unit suite again passed 652 tests. The flow run
stubs the card queue and the world-body callees. No game bytes or raw
disassembly are tracked.

The same day's audit fix reran the flow command and passed 170 checks at
seeds 20973 and 7. The art command above, with `local/disc.iso` and
`local/BASLUS-20973_slot0`, passed 189 checks. The unit suite passed 652
tests in 5.636s.
