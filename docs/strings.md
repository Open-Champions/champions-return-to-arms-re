# Strings: the text table, the wide-string formatter and the HUD text commands

SLUS-20973 v2.00, researched 2026-10-21 on `t3/research-strings`. This document is for the
native client, which refuses `setInfo`, `addHelpMessage`, `addHelpMessageF`, `showBust` and
`showCompass` because its host has no string table and no text formatter.

It covers:

- where the game's string tables come from and how a key becomes a text;
- `wstr_format` and every conversion it supports;
- what each of the five commands stores, and which timers and draw tasks read it;
- `sound_playOnObject`;
- `handle_clear` on a live target.

The drawing of the widgets is in `docs/hud-dynamic.md` on `t3/research-ui` (3e39392). The
dialog side is in `docs/dialog.md` on `t3/research-dialog` (334578d). This document does
not repeat them.

Evidence words follow CONTRIBUTING.md:

- **Observed**: read at the address given.
- **Executed**: the original function was run in `tools/ee_emu.py` by
  `tools/difftest_strings.py` and matched `tools/ref_strings.py`.
- **Inferred**: follows from the above.
- **Unknown**: not established.

Nothing here ran on a game. Keys, texts and other game data stay out of this file. The disc
figures in section 6 are counts printed by `tools/strings_census.py`.

| Part | Model | Synthetic tests | Difftest property |
|---|---|---|---|
| Text table | `ref_strings.TextTable`, `text_hash`, `uni_entries` | `HashAndTable` | `text.hash`, `text.register+lookup` |
| Wide strings, formatter | `wstr_format`, `wstr_format_ascii`, `widen` | `Formatter` | `wstr.helpers`, `wstr.format`, `wstr.formatAscii` |
| Five commands, setters, timers | `Hud`, `Commands` | `HudCommands` | `hud.commands` |
| `sound_playOnObject` | `SoundSeqs` | `SoundAndCharm` | `sound.playOnObject` |
| `handle_clear` on a live target | `set_charm` on `ref_core.HandlePool` | `SoundAndCharm` | `charm.liveTarget`, `sound.playOnObject` |

## 1. The string table

### 1.1 Files and loading

The table code was already outlined in `docs/data-tables.md` section 6 and `docs/engine.md`.
This section adds the execution results and corrects two points.

- **Loading (Observed).** `main` loads `gtext.lmp` with `lump_load` 0x173558 at 0x323fa0, at
  boot, next to the fonts.
- **Registration (Observed).** `lump_fixupEntry` 0x17153c sends every lump entry whose
  extension is `uni` to `text_registerTable` 0x173bac (call at 0x171684). When a lump is
  released, `lump_releaseEntry` sends the same entries to `text_unregisterTable` 0x173ac0
  (0x171b88). So a `.uni` inside any lump, including a level lump, is added to the one
  global table while that lump is loaded.
- **Correction: `.txt` files are not string tables (Observed).** An entry with extension
  `txt` is used only when its whole name is `credits.txt` (`strcasecmp` at 0x1716c4). It
  goes to `credits_splitLines` 0x223ba0. That function skips the 2-byte byte-order mark and
  cuts the UTF-16 text at CR/LF into the pointer array `g_creditsLines` 0x4fb5e8 (380
  lines at most). `docs/engine.md` said `.uni`/`.txt` went to `text_registerTable`.
- **Other credits files are never read (Inferred).** The disc's `credits_de.txt`,
  `credits_fr.txt` and `credits_sp.txt` do not match the name test.
- **Lifetime (Observed).** The table stores pointers into the loaded lumps and copies no
  text. A text pointer stays valid only while its lump stays loaded. For `gtext.lmp` that
  is the whole session.

### 1.2 Format of a `.uni` entry

Observed in `text_registerTable` 0x173bac. The walk was executed on synthetic streams.

```
repeat while the byte at the cursor is not 0 (lb: any non-zero byte, 0x80-0xff included):
    key   ASCII bytes, 0-terminated
    text  UTF-16LE units starting at (keyStart + strlen(key) + 2) & ~1, 0-terminated
    next key starts right after the text's terminator unit
```

- **No count and no index.** The stream ends at a key whose first byte is 0.
- **Encoding (Observed on the disc).** In the English table every text unit is below
  0x100. The English table uses 87 distinct units. The German, French and Spanish tables
  have 22, 127 and 43 texts with a unit of 0x100 or above (section 6).

### 1.3 Hash and registration

Executed: `text.hash` (keys of 0 to 60 bytes, a third of the bytes ≥ 0x80) and
`text.register+lookup`. All 8,192 slots are compared after every registration and every
unregistration.

```
text_hash(key, len):                     # 0x173a74; bytes read with lb, so SIGNED
    h = 0
    for b in key: h += sx8(b); h += h << 10; h ^= h >> 6   (arithmetic shift, 32-bit)
    h += h << 3;  h ^= h >> 11;  return h & 0x1fff
```

The table is `g_textHash` 0x7c2ea0: 8,192 pointers to keys.

- **Registration.** The entry goes into the first empty slot at or after `hash(key)`,
  stepping +1 mod 8,192. Nothing checks for a repeated key or a full table. On a full
  table the probe never ends.
- **Repeated keys.** Both copies are stored. A lookup always meets the earlier copy first,
  so **the first copy of a key wins**. The English table repeats 1,189 keys (section 6). A
  host that loads the file into a map where later entries overwrite earlier ones shows the
  wrong text for every one of those keys.
- **Unregistration.** `text_unregisterTable` probes from the hash for the slot holding the
  same key address and stores 0 there. It leaves no tombstone. So any key registered
  later, whose probe passed that slot, can no longer be found. The difftest found such
  keys in 77 lookups (seed 20973) and 37 (seed 7), on purpose-built colliding tables.
- **The disc does not hit the unregistration problem (Inferred).** Two level lumps carry a
  `.uni` (section 6), and both are registered after `gtext.uni`. A slot taken later cannot
  lie inside the probe chain of an earlier key, so unregistering a level table cannot hide
  an English key.

### 1.4 Lookup

Executed: `text.register+lookup`. Each run makes 7,200 `text_find` and 7,200 `text_lookup`
calls, of which 2,183 to 2,365 are misses. On every miss the ring index and all 40 bytes
of the ring entry are compared, stale stack bytes included.

`text_lookup(key)` 0x173c84 works in five steps:

1. Copies the key into a 0x200-byte stack buffer and drops every `"` (0x22). A key longer
   than 511 bytes overruns the stack frame.
2. Hashes the copy with its `strlen`.
3. Probes from the hash slot. An empty slot means a miss. Otherwise `strcmp` against the
   stored key, and step +1 on a difference.
4. On a match, returns `(storedKey + strlen + 2) & ~1`: a pointer to the text in the
   lump, not a copy.
5. On a miss, advances `g_textMissIndex` 0x41bfa8 (`(i + 1) & 15`) and clears entry `i` of
   `g_textMissRing` 0x7caea0 (16 entries × 20 units). It writes `N`, `F`, `:`, then 16
   bytes of the stack copy, each sign-extended to 16 bits, and returns that entry.

What a miss shows, and how long it lasts:

- **The visible text** is `NF:` plus the first 16 bytes of the key, quotes removed.
- **Stale bytes.** Units past the key's terminator hold whatever the stack held. The last
  unit, 19, is always 0.
- **Lifetime.** A miss text is overwritten by the 16th miss after it.

`text_find` 0x173de0 is the same probe without the miss ring: it returns 0 for a missing
key. It had no name before.

Quotes are dropped from the request only, never from the stored key. A stored key that
contains a quote can never be found. No shipped table has one.

### 1.5 Language selection

- **The language byte (Observed).** `g_language` 0x44fddc starts at 0. 26 functions read
  it: item-name grammar, number separators, the boss meter's wide variant for 3 and 4,
  wrapping, stream-directory entries and save labels.
- **Its only writer is unreferenced (Observed).** The only store to the byte is
  `splash_languageMenu` 0x3235a8, which nothing references (`docs/mainloop.md`). Its five
  entries map, through the jump table at 0x554740, to the values 0, 3, 4, 1 and 2.
- **No code loads the other languages (Observed).** The executable names only `gtext.lmp`.
  No code loads `GTEXT_DE.LMP`, `GTEXT_FR.LMP` or `GTEXT_SP.LMP`, and all three name their
  entry `gtext.uni`.
- **Result (Inferred).** The US build always reads the English table with language 0.

**Unknown:**

- Which value 1 to 4 belongs to which lump. The grammar code treats 4 as German and 1
  and 3 as Romance (`docs/startup.md`).
- What value 2 is.
- Whether loading a second `gtext.uni` would work. Its 4,300 keys would be added after the
  English ones, and the first-copy rule would hide every translated text that has an
  English key.

## 2. `wstr_format` and the wide-string helpers

Executed: `wstr.format`, 4,000 random formats per seed with up to eight arguments. 865
(seed 20973) and 919 (seed 7) of them end in a conversion. Also `wstr.formatAscii` and
`wstr.helpers`.

### 2.1 Calling convention

`wstr_format(out, fmt)` 0x19ea78 takes `a0` = output and `a1` = a 16-bit format. **Every
argument is a float**, passed in `f12` to `f19` and stored to the stack in that order.
Each conversion takes the next one.

- **Integers and pointers arrive as floats.** Callers convert them with `cvt.s.w`, and
  the formatter truncates with `cvt.w.s`, which saturates at ±2³¹. A value is exact only
  below 2²⁴ in magnitude.
- **Pointers above 16 MB.** A `%s` or `%u` pointer above 16 MB comes back exact only if
  it is a multiple of the float spacing there (Inferred from the conversions).
- **A ninth conversion** reads the formatter's own scratch buffer (Observed: the argument
  pointer runs from sp+0 into the `%d` buffer at sp+0x20). The model refuses it.
- **The 8-bit variant.** `wstr_formatAscii` 0x19e9c4 widens an 8-bit format into a
  0x200-byte stack buffer with `wstr_fromAscii`, then calls `wstr_format` with the same
  float registers.

### 2.2 Conversions

The unit after `%` alone decides. Flags, widths and precisions are not parsed.

| Format | Output | How |
|---|---|---|
| `%%` | `%` | |
| `%d` | decimal | `sprintf("%d", trunc(arg))`, each byte widened |
| `%c` | one unit | `trunc(arg) & 0xffff` |
| `%s` | 8-bit string | `sprintf("%s", (char*)trunc(arg))`, each byte zero-extended |
| `%u` | 16-bit string | copied from `(u16*)trunc(arg)`. Not "unsigned" |
| `%f` | two decimals | `sprintf("%.2f", widen(arg))`. `%.2f` written in a format prints `2f` |
| `%` and anything else | nothing | takes no argument |

In every case the formatter then skips two units.

**`widen`.** This is the soft-float `soft_extendsfdf2` 0x3aef58. It reads the pattern the
R5900 way (Executed on edge patterns and inside `wstr.format`):

- exponent field 0 becomes a signed zero, so denormal patterns print `0.00` or `-0.00`;
- exponent field 255 is an ordinary number up to (2 − 2⁻²³)·2¹²⁸, never inf or NaN.

`newlib` then prints the exact value rounded to two places, as Python's `'%.2f'` does.
The `%f` path reaches `newlib` `malloc` through `_dtoa_r`, so the difftest answers four
system calls: GetThreadId, WaitSema, SignalSema and EndOfHeap.

### 2.3 The end test reads past the terminator (Executed)

```
loop:
    c = fmt[i]
    if c == '%':  convert(fmt[i+1]);  i += 2;  continue
    out += c;  i += 1
    if fmt[i] == 0:  out += 0;  return
```

The test for the end looks only at the unit after a copied unit. This has three
consequences:

- An empty format writes two zero units.
- A format that ends in a conversion, `%%` included, copies its own terminator. It then
  goes on copying whatever follows in memory, until a copied unit is followed by a 0. A
  `%` met there converts with the next argument.
- A format that ends in a lone `%` skips the terminator as its "conversion" and does the
  same.

The visible result always ends at the first 0, but memory after it is overwritten. For a
text from the table, what follows its terminator is the next key and the next text. The
English table has 55 texts that end in a conversion. Of the `addHelpMessageF` texts on
the disc, 2 do (section 6).

### 2.4 Helpers (Executed, `wstr.helpers`)

| Function | Behaviour |
|---|---|
| `wstr_copy` 0x19e854 | copies through the terminator, unbounded |
| `wstr_len` 0x19e994 | number of units |
| `wstr_fromAscii` 0x19e884 | each byte zero-extended (`lbu`) |
| `wstr_toAscii` 0x19e8b4 | the low byte of each unit (no name before) |

## 3. The five commands

The commands' bodies were executed by `t3/research-script` with the text calls stubbed
(`docs/script-effects.md`, 52984db). This section runs them **with** the real string
table and formatter.

Each command is executed by `hud.commands`, with:

- the real `scr_getAddr` and `scr_getString` on a fake script machine, with packed and
  unpacked strings;
- the real `text_lookup`, `wstr_format`, `wstr_copy` and `strcpy`.

After every step it compares six things:

- the HUD block 0x86aab0–0x86ac44, byte for byte;
- the help-F buffers 0x5d3048–0x5d3188;
- 11 state words;
- the miss ring;
- the outward calls and their arguments: the chime, `ui_startPulse` and net message 2.

Each run is 6,000 steps per seed: random sequences of the five handlers, the four setters
and the two run-side timers.

### 3.1 Shared state (Observed; Executed by `hud.commands`)

| Address | Size | Written by | Meaning |
|---|---|---|---|
| 0x86ab78 `g_hudMessageText` | u16[100] | `hud_showMessage` (wstr_copy) | the one-line message; a longer text runs into `g_msgIdGame` 0x86ac40, the HUD game-message channel id |
| 0x4f66e0 `g_hudMessageFrames` | s16 | `hud_showMessage`, `hud_tickMessage` | run ticks left |
| 0x4f66e2 `g_hudMessageForce` | s8 | `hud_showMessage` | forced: ignores the local menu, draws on layer 7 |
| 0x41b928 `g_helpMessageOpen` | s8 | `hud_showHelpMessage` (1), `help_task`, `hud_resetNotices`, `game_clearLevel` (0) | the help box is up |
| 0x86aa64 / 0x86aa68 `g_helpTitle` / `g_helpBody` | pointers | `hud_showHelpMessage` | **pointers, not copies** |
| 0x4f66cc `g_helpCloseDelay` | s32 | 90 on open, 60 on close | `help_task` counts it down once per call and takes no confirm while it is above 0 |
| 0x5d3048 / 0x5d3088 | u16[32] / u16[128] | `addHelpMessageF` (wstr_copy) | formatted title and body; 0x5d3188 follows |
| 0x4f66d4 `g_hudBustShown` | s8 | `hud_setBust` (5), `hud_run` (−1 per tick) | the bust is drawn while it is non-zero |
| 0x4f6b48 `g_hudBustTexture` | char[40] | `hud_setBust` (strcpy) | portrait texture name; 0x4f6b70 follows |
| 0x86aab0 `g_hudBustText` | u16[32] | `hud_setBust` (wstr_copy) | caption; a longer one runs into the compass label |
| 0x86ab30 / 0x86ab34 | s32 / s32 | `hud_setBust` | value and maximum; maximum −1 shows the value as a number, otherwise as a meter fill |
| 0x4f66d5 `g_hudCompassShown` | s8 | `hud_setCompassTarget` (5), `hud_run` (−1 per tick) | the compass is drawn while it is non-zero |
| 0x86aaf0 `g_hudCompassLabel` | u16[32] | `hud_setCompassTarget` (wstr_copy) | label; a longer one runs into the bust value and maximum |
| 0x86a8f0 `g_hudCompassTarget` | Vec3 | `hud_setCompassTarget` | world point the needle turns to |
| 0x4f66a9 `g_hudBustHideLatch` | s8 | `hud_tickMessage`, `hud_spellSelect`; cleared by `hud_drawBust` | fades the bust out |

Every text buffer is filled by an unbounded copy. The longest text each command takes from
the shipped table fits its buffer (section 6). A bust caption of more than 31 units
overwrites the compass label. A compass label of more than 31 units overwrites the bust
value and maximum, then `g_expectedChecksums`. The difftest reaches all of these overruns
and matches them byte for byte.

### 3.2 `setInfo(textKey)`

- **Handler** 0x14318c: `text_lookup(key)`, then `hud_showMessage(text, 180, −1, 0)`.
- **Gate (Executed).** An explicit slot that is not local refuses. Slot −1 skips that
  test. Force 0 while `g_localMenuOpen` 0x41b69d is set refuses.
- **State.** The text is copied into 0x86ab78, the frames (180) into 0x4f66e0 and the
  force into 0x4f66e2.
- **Shared buffer.** `hud_showMessage` has 40 call sites, so any later game message replaces
  a script message.
- **Timer (Executed).** `hud_tickMessage` 0x1d934c is the first call of `hud_run` (the
  "HUD Run" run task, inside the lockstep tick). It steps nothing while `g_hudSuppressed`
  0x4f66a8 or this machine's `g_warmupFrames` 0x506048 is non-zero, or while the frame
  count is 0 or below. Otherwise it takes 1 from the count. In a 4-player offline game it
  also sets `g_hudBustHideLatch`. A `setInfo` text therefore lasts 180 run ticks on this
  machine (3 s at 60 Hz) plus any suppressed ticks.
- **Draw.** The draw (`hud_drawBossMeter` 0x1d93b0, step 4 of the HUD draw task) is
  `docs/hud-dynamic.md` section 4 on `t3/research-ui`: centred at (320, 78), with an alpha
  that fades over the last 32 ticks.
- **Per machine.** The timer is per machine, and one simulation read of it exists, in
  `Vehicle_run` 0x207dc4 (`docs/mainloop.md`, P5).

### 3.3 `addHelpMessage(titleKey, bodyKey)` and `addHelpMessageF(key1, v1, key2, v2)`

- **Handlers.**
  - 0x1431d8: two lookups, then `hud_showHelpMessage(−1, title, body)`.
  - 0x143270: lookup `key1`, then `wstr_format` into a stack buffer of 0x200 bytes, with
    `f12 = cvt.s.w(v1)` and `f13`–`f19` = 0.0. The same for `key2`/`v2`. Then
    `wstr_copy` of the two results into 0x5d3048 and 0x5d3088 (in that order) and
    `hud_showHelpMessage(−1, 0x5d3048, 0x5d3088)`.
- **Which conversions work in `addHelpMessageF` (Executed).** The looked-up text is the
  format, and the one integer is the only argument.
  - `%d`, `%c`, `%%` and `%f` work. `%f` prints the integer with two decimals.
  - `%s` and `%u` dereference the address 0, which faults in the interpreter; the model
    refuses them.
  - The disc's `addHelpMessageF` texts use `%d` or nothing (section 6).
- **Title overflow (Executed).** A formatted title of more than 31 units runs into the body
  buffer, and the body copy then overwrites it. The box shows 32 title units followed by
  the body. `hud.commands` reaches this case.
- **Setter** `hud_showHelpMessage` 0x1d9830 (Executed).
  - An explicit slot that is not local refuses.
  - Offline, the box opens at once.
  - In a net game the alive list 0x4f8440 is walked. The first local slot gets
    `hudmsg_sendMenuState(slot, 1, 0)` (game message 2) and the box opens. With no living
    local player nothing opens.
  - On opening it calls `res_find("fx.lmp", "butn_message.anm")`, then
    `sound_playOnObject(resource, 0, 1.0)` (section 4), then
    `sound_setPlaysWhileFrozen(handle)` and `ui_startPulse(0)`.
  - It stores open = 1, the two **pointers**, and close delay 90.
- **There is no queue.** A second call while a box is open replaces both pointers. It plays
  the chime again and re-arms the 90-frame delay. The help-message "queue" the native
  client expected is one slot, and the last call wins.
- **Pointer lifetime (Inferred from 1.4 and the setter).**
  - A title or body whose key missed points into the miss ring. Sixteen further misses
    while the box is open change what it shows.
  - An `addHelpMessageF` box points at the static buffers. The next `addHelpMessageF`
    rewrites them in place.
- **Draw and dismissal.** `help_task` 0x1dcc78 is a draw task, priority 50. Its draw is
  `docs/hud-dynamic.md` section 9. Read again here (Observed, 0x1dcc78–0x1dcff0):
  1. Each call takes 1 from the close delay while it is above 0.
  2. While the box is open in an offline game, it sets `g_paused` 0x41b4f4 to 1 and the byte 0x44fa80 to 1.
  3. With the delay at 0, a confirm on any of the `g_numPlayers` raw pads closes the box.
     Closing clears the open flag, stores 60 into the delay and into `g_menuInputLockout`
     0x41b4fc, and, offline,
     runs `script_runPostAction`. It then clears 0x44fa80, and clears `g_paused` unless a
     local menu is open. Every living local slot then gets `hudmsg_sendMenuState(slot, 0,
     0)`.

  So, offline, an open help box pauses the game until it is confirmed, and the post action
  runs only after it. `helpMessageActive` (0 disc calls) reads the open flag.

### 3.4 `showBust(texture, textKey, value, max)`

- **Handler** 0x142864: lookup, then `hud_setBust(texture, text, value, max)`.
- **Gate** (shared with the compass, Executed). The first failing test refuses:
  1. `g_hudSuppressed`;
  2. `g_localMenuOpen`;
  3. local camera mode (`g_localCamera` +0x34) not 1 (a null camera faults);
  4. `g_loadscreenActive` 0x506094;
  5. `g_menuOpenFlag` 0x41b4f8.

  A dialog sets `g_hudSuppressed`, so a bust asked for by a dialog choice is dropped
  (`docs/dialog.md` 6.1 on `t3/research-dialog`).
- **State.** `strcpy` of the texture name to 0x4f6b48, `wstr_copy` of the text to 0x86aab0,
  value to 0x86ab30, maximum to 0x86ab34, and **5** to `g_hudBustShown`.
- **Timer: the bust is a 5-tick lease (Executed).** `hud_run` 0x1dbbec–0x1dbc24 takes 1
  from `g_hudBustShown` and from `g_hudCompassShown` every run tick, unconditionally. So a
  bust disappears 5 ticks after the last `showBust`. A script keeps it up by calling
  `showBust` at least every 5 ticks.
- **Draw (`docs/hud-dynamic.md` section 7).** The bust is drawn only while the countdown
  is non-zero. The fade 0x4f66d0 moves ±0.08445 per drawn frame toward 0 while the latch
  is set, and toward 1 otherwise. `hud_drawBust` clears the latch every frame it runs, and
  clamps a negative value to 0 (stores 0 at 0x86ab30).
- **Native client.** The native client must model the lease, not a show/hide pair.

### 3.5 `showCompass(objectName, textKey)`

- **Handler** 0x1427b4: `world_findObjectByName(name)`, then the lookup, then a copy of
  the object's +0x10..+0x1b. There is **no null check**: a name that finds nothing reads
  address 0x10 after the lookup has already run. The difftest's 45 such cases (seed 20973)
  fault on the original and are refused by the model.
- **Setter** `hud_setCompassTarget` 0x1df668: same gate as the bust. It stores 5 to
  `g_hudCompassShown`, copies the label to 0x86aaf0, then the three position words to
  0x86a8f0.
- **Timer.** The same 5-tick lease, from the same two lines of `hud_run`.
- **Draw.** `hud_drawCompass` 0x1df720 (`docs/hud-dynamic.md` section 7) needs, besides
  the countdown, the local alive list, a compass player and no dialog. The mesh footprint
  is Unknown there.

### 3.6 Which machine shows what

All five commands write per-machine presentation state (`docs/script.md` P10):

- a menu, a dialog or the load screen on one machine refuses there only;
- the message timer pauses on a machine that is still warming up.

The net effects are the help box's game message 2 and the offline pause in 3.3.

## 4. `sound_playOnObject(seq, obj, f12 volume)` 0x214230

This is the call behind the help chime, `soundSequence` and `healPlayer`.
`docs/script-effects.md` left it Unknown. It is executed now by `sound.playOnObject`:
12,000 calls per seed. `anim_push` 0x170838, `handle_clear` and `handle_link` run for real,
and `game_isFrozen` is stubbed. After each call the return value, 17 fields of all 32
slots, the serial, every handle list and the free list are compared.

```
if seq == 0: return -1
g = seq->category (+0x3c);  chosen = -1;  n = 0
for i in 0..31:                                 # g_soundSeqs 0x871a68, 0x4c bytes each
    if slot[i].tracks (+0x04) == 0: chosen = i;  continue     # keeps the LAST free slot
    if slot[i].seq->category != g: continue
    n += 1
    if g != 0 and not n < s8(g_soundGroupLimit[g]): return -1  # 0x4f8a28
if chosen < 0: return -1
s = slot[chosen];  s.flags (+6) = 0
anim_push(s, seq, 4)        # +4 += 1, +6 |= 4, track at +8: seq, time 0, weights 1/0/1/0, flags 4;
                            # an old track link at +0xc gets 0 at its +0x14 and is cut
if obj: handle_clear(s+0x28); handle_link(s+0x28, obj+0, obj); s.pos = obj[+0x10..+0x1b]; s.noPos = 0
else:   s.noPos (+0x3a) = 1
s.frozen (+0x3b) = game_isFrozen()
s.serial (+0x38) = serial;  serial = (serial + 1) & 0x7f      # 0x4f8950
s.released (+0x3c) = 0;  s.volume (+0x40) = f12;  +0x44 = 360.0;  +0x48 = 840.0
return chosen | serial_before << 8 | 0x8000
```

What the execution established:

- **The scan keeps the highest-numbered free slot**, and the category cap fails the call
  as soon as the count reaches it, even with free slots left. Category 0 has no cap.
- **No seed is touched (Executed).** Neither `g_randSeed` 0x404464 nor `g_cosmeticSeed`
  0x404460 is read during the call (the difftest records every read). The cosmetic seed
  of sound playback is drawn later, by the per-frame update (`docs/audio-playback.md` on
  `t3/research-audio`), not here.
- **The return depends on this machine's sound state**: free slots, caps and the serial
  (`docs/audio-save.md` A3). Callers such as `soundSequence` only pass it to
  `sound_setPlaysWhileFrozen`, which takes no further action for −1.
- **A slot that finished keeps its object handle (Executed, 2,890 to 4,532 reuses per
  seed).** Reusing the slot clears that handle, which unlinks the partner node from the
  old object's back list. The old object and its other handles are untouched (section 5).

## 5. `handle_clear` on a live target

The general contract of `handle_clear` 0x1a1698 is `docs/spec/core.md` section 12 (random
difftest `handles.sequence`). What the script side lacked is the case where the handle
being cleared points at an object that is still alive. That case is executed now.

**`charmMonster` and `followPlayer`** go through `Creature_setCharm(c, frames, team)`
0x1189f0. Executed by `charm.liveTarget`: 9,600 steps per seed with:

- 16 creatures that take targets and lose them;
- several creatures holding the same target;
- a creature whose +0x234 list holds two links;
- extra lists;
- objects destroyed under them.

```
if s16(c+0x312) == -1:    return            # already charmed for ever: nothing stored
if not c.flags & 0x20:    return            # not a creature
if c.flags & 0x40:        return            # a player
c+0x310 = team;  c+0x312 = frames
handle_clear(c+0x234)                       # the target handle
c+0x234 = 0                                 # already 0 after the clear
```

With a live target the clear does exactly four things:

- it unlinks this creature's node(s) from +0x234;
- it unlinks each partner node from the target's back list (target +0);
- it returns both nodes to the free list, partner first, so the creature's own node is
  reused first;
- it leaves the target, its other back-links and every other creature's handle to it
  unchanged.

Of the stored calls, 540 and 559 (two seeds) had the target still held by other
creatures. Every list and the free-list order matched after every step. The same holds for
a sound slot's handle (section 4).

So the native refusal of `charmMonster`/`followPlayer` for a live +0x234 (SC-15 in the
native report) can be lifted on this evidence. The effect is "forget my target", local to
the charmed creature.

## 6. On the disc (counts only)

`python3 tools/strings_census.py --disc ~/Projects/open-champions/private-validation/rta-disc`.
The disc folder was only read.

**String files: 10.** Six are `.uni` and four are `.txt`.

| File | Entries | Distinct keys | Repeated | Longest key | Longest text | Texts > 31 / > 99 / > 255 units | Texts with `%` | Ending in a conversion |
|---|---|---|---|---|---|---|---|---|
| `GTEXT.LMP` (English) | 5,498 | 4,309 | 1,189 | 33 | 543 | 1,086 / 290 / 40 | 421 | 55 |
| `GTEXT_DE.LMP` | 4,304 | 4,300 | 4 | 33 | 540 | 1,142 / 318 / 45 | 420 | 57 |
| `GTEXT_FR.LMP` | 4,304 | 4,300 | 4 | 33 | 548 | 1,187 / 327 / 47 | 419 | 63 |
| `GTEXT_SP.LMP` | 4,304 | 4,300 | 4 | 33 | 475 | 1,113 / 271 / 41 | 414 | 57 |
| `STRIFE.GOB` level lump | 1 | 1 | 0 | 17 | 36 | 1 / 0 / 0 | 0 | 0 |
| `BOSSEVIL.GOB` level lump | 0 (4 bytes) | – | – | – | – | – | – | – |

- **The four `.txt`** are the credits in `CREDITS.LMP`: `credits.txt` plus `_de`, `_fr`
  and `_sp`. Only `credits.txt` is read (1.1).
- **Conversions in the English table:** `%d` 485, `%c` 386, `%%` 92, `%s` 34, `%u` 5,
  `%f` 1, other units after `%` 20. No key holds a quote or a byte ≥ 0x80. No key is
  longer than the 159-byte script copies.
- **Keys present in one language only.** 19 English keys are missing from each
  translation, and 10 keys of each translation are not in English.
- **Hash load.** English fills 5,498 of 8,192 slots. Its 1,189 repeats cluster, so the
  longest probe from a key's hash slot is 261 slots. Each translation's longest probe is
  19.

**Level scripts: 121.** Calls, and the texts the five commands look up:

| Command | Calls | Distinct literal keys | Keys missing (show `NF:`) | Longest text | Over its buffer |
|---|---|---|---|---|---|
| `setInfo` | 95 | 71 | 1 | 47 | 0 (limit 99) |
| `addHelpMessage` | 65 | 88 | 7 | 169 | – (pointers, no copy) |
| `addHelpMessageF` | 7 | 11 | 0 | 71 | 0 (limits 31 / 127) |
| `showBust` | 31 | 29 | 0 | 30 | 0 (limit 31) |
| `showCompass` | 3 | 3 | **3** | – | – |

- **`addHelpMessageF`.**
  - Of its 14 key arguments, 6 texts use `%d` and 8 have no conversion.
  - 6 of the integer arguments are not literals, so only the literal ones were formatted.
  - 2 texts end in `%d`, so the formatter reads past them (2.3). With literal values their
    visible output stays inside the buffers.
- **`showBust`.** 11 calls pass maximum −1 (the value shown as a number). 20 pass a maximum
  that is not a literal. No texture name exceeds 39 bytes.
- **Missing keys.** All 11 missing key references sit in five level files: three `E3*`
  demonstration levels and two others. None of the five is a name in the level table
  0x4f7210. Every `showCompass` on the disc is among them. Whether a player can reach those
  levels is Unknown: two of them are named by a `newWorld` call somewhere.

## 7. What the native client should implement first

Ranked by disc use per unit of work. Section numbers are this document's.

1. **The string table (1.2–1.4).** Load `gtext.uni` from `GTEXT.LMP`, walk it as in 1.2,
   and keep the **first** copy of a repeated key: 1,189 English keys depend on it. Drop
   `"` from requests. On a miss return `NF:` and the first 16 key bytes. A hash map is
   enough. The 13-bit probe order matters only for unregistration, which the disc does not
   need (1.3). This unblocks every command below and the dialog and item names, which use
   the same lookup.
2. **`setInfo` (3.2).** 95 calls in 25 levels.
   - Copy the text, set 180 run ticks, step in the run task with the two gates, apply the
     local-menu refusal.
   - It draws through research-ui's message contract.
   - It needs no formatter.
3. **`addHelpMessage` and `addHelpMessageF` (3.3).** 72 calls.
   - One slot: last call wins, 90-frame close delay.
   - The offline pause until confirm, and the post action after it.
   - Net game message 2 on open and close.
   - A `wstr_format` subset: `%d`, `%%` and `%c` cover every shipped text that
     `addHelpMessageF` uses. Then the read-past-terminator rule for texts ending in `%d`:
     reproduce the visible result; the overrun can be bounded.
   - The chime goes through section 4, owned by the audio job.

   Ranked above the bust because it changes simulation state offline (`g_paused`) and
   sends a game message online.
4. **`showBust` (3.4).** 31 calls in 17 levels. The 5-tick lease, the value/maximum meter
   or number, the texture from `bust.lmp`, the shared gate, and the latch and fade.
5. **`showCompass` (3.5).** 3 calls. All are in levels outside the level table, and all
   look up missing keys. It needs an object position, the null-object case refused, the
   lease, and the compass mesh, whose footprint is Unknown. Implement it last.

Alongside:

- **`charmMonster` and `followPlayer`** can drop their live-target refusal (section 5).
- **`sound_playOnObject`** has an executed contract (section 4) for the audio job.

## 8. Validation

| Run | Command | Result |
|---|---|---|
| Model tests | `python3 -m unittest tools/test_ref_strings.py tools/test_strings_census.py` | 31 tests OK |
| Difftest, seed 20973 | `python3 tools/difftest_strings.py --seed 20973` | 8 properties, 8 PASS, 47 s |
| Difftest, seed 7 | `python3 tools/difftest_strings.py --seed 7` | 8 properties, 8 PASS, 51 s |
| Mutations | the model changed in seven ways, then the matching properties run (`--quick`) | all 7 caught |
| Census | `python3 tools/strings_census.py --disc …` | section 6 |

The seven mutations:

1. hash over unsigned bytes;
2. `setInfo` lasting 181 ticks;
3. a 4-tick lease;
4. a close delay of 60 on open;
5. `%f` of exponent 255 printed as inf;
6. `setCharm` without its `handle_clear`;
7. the first free sound slot instead of the last.

Cases per property and seed are printed by the difftest. Every property passed on both
seeds.

| Property | Cases per seed | What is compared |
|---|---|---|
| `text.hash` | 20,000 | the hash of each random key |
| `text.register+lookup` | about 7,230 | all slots after each registration or unregistration, then every lookup and find |
| `wstr.helpers` | 3,000 | each helper's output and the unit after it |
| `wstr.format` | 4,000 | output and the unit after it |
| `wstr.formatAscii` | 1,500 | output and the unit after it |
| `hud.commands` | 6,000 | the six comparisons listed in section 3 |
| `sound.playOnObject` | 12,000 | the comparisons listed in section 4 |
| `charm.liveTarget` | 9,600 | creature fields and every list |

## 9. Unknown

- Language values 1 to 4 and their lumps (1.5). Whether any build loads a second
  `gtext.uni`.
- Whether the levels whose keys are missing (section 6) are reachable in normal play.
- The compass mesh footprint and the minimap projector (research-ui's open items).
- `help_task`'s draw was not executed here. Its state handling above is Observed.
- Exact console behaviour. All execution is the interpreter's (`tools/ee_emu.py`). The
  formatter's float handling depends only on integer and soft-float code, so the model
  question there is small.
