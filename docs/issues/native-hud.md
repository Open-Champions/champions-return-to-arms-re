# A new HUD drawn by Godot from the game's own state

Started 2026-10-13. The translated game runs as a library inside Godot
(`native-godot.md`). This work replaces the PS2 game's 640 x 448 HUD sprites with a clean
interface Godot draws itself, from numbers read out of the game's memory. Every statement
says **Ran** (with what was seen) or **Read**. Kept current as the work goes: a successor
needs only this file.

Nothing derived from the game is in the repository: names of characters, classes,
creatures, items, abilities and levels, the prompt's and the message's text are read from
the game's memory while it runs. No game art, no game font: every shape is drawn by code,
the font is the one inside Godot (Open Sans, SIL Open Font License). Pictures, memory
images, routes, logs and the test tones are under `local/godot-hud/`.

## STATE (2026-10-13, 15:50)

Nothing of this work is still running; test windows are closed (checked by process id at
the end, section "Processes").

| Part | State | How it is known |
|---|---|---|
| state reader `tools/recomp/app/gamestate.h`, `gamestate.cpp` (plain C struct, read only) | **done** | 48 comparisons of the game's own bars with the fields: 47 equal to the pixel, 1 explained (section 3) |
| extension class `RtaGameState` (`tools/godot/extension/src/rta_gamestate.*`) | **done, merged by the Godot agent** (registered behind `RTA_GODOT_HAVE_GAMESTATE`) | runs in every test here |
| the HUD `tools/godot/project/hud/` | **runs**: player frame, party frames, bars above heads, target and boss bar, floating numbers, quick slots, potions, weapon, gold, feed, prompt, radar / compass, attackers out of sight, the game's message, level title, level-up, online notices and chat, pause band, the portal's notice card | pictures in section 6 |
| three layouts (overhead, third person, first person), 4:3 / 16:9 / 21:9 | **Ran** | section 6 |
| the game's own HUD off (`set_option("game_hud", "off")`) | **Ran**; the boss meter, the one-line message and the prompt box are not hideable yet (asked for) | section 5 |
| custom music for boss fights from the player's own files | **Ran** with test tones; the game's music turned down by itself needs the two patch hunks of `tools/godot/hud-recomp.patch` (Ran here in a private library) | section 8 |
| look as a swappable theme | **Ran** with a small example skin | section 9 |
| cost | **0.33 ms a frame in play, 0.80 ms in the worst staged picture** (the reader 15 microseconds) | measured by the HUD itself in paced runs, section 10 |
| what the controls side offers (`fpcontrols::hud()`) | **consumer written, not run**: the library does not hand it out yet | section 7 |
| network: a second player | **not run**: the library has no network; party frames, a desync notice and chat were drawn from data made up by the test and marked "TEST DATA" on screen | section 6 |

## 1. What is where

```
tools/recomp/app/gamestate.h, gamestate.cpp     the reader: rta_gs_update(reader, ram) fills rta_gamestate; C, no dependencies,
                                                never writes to the game, calls none of its code
tools/godot/extension/src/rta_gamestate.h/.cpp  RtaGameState: the struct as Godot values (compiles gamestate.cpp into the extension)
tools/godot/project/hud/
    hud.tscn, hud.gd       the root: reads the state once per displayed frame, layout, settings, visibility, commands
    style.gd               the THEME: colours, font, panel / bar / text / glyph drawing; a skin can replace any of it
    world.gd               bars above heads, name tags of other players, floating numbers, the aim marks of the close views
    threat.gd              attackers out of sight, where a hit came from
    status.gd              the player's frame, the party's frames
    compass.gd             the radar (overhead) or the compass strip (close views)
    top.gd                 target bar, boss bar, the game's message, level title, level-up, network, chat
    bottom.gd              potions, quick slots, weapon, prompt, gold, the feed, the quick-cast ring
    pause.gd               the band while the pause menu is open
    notice.gd              the portal's invitation / request card
    music/music.gd         the music director (section 8)
    dev/skin_example.gd    a small skin (section 9);  dev/portal_stub.gd  a stand-in for the portal in tests
tools/godot/hud-recomp.patch                    what other agents' files need: two hunks (music volume) and four requests, with notes
local/godot-hud/                                snapshots, the private build, routes, tests, pictures (not in the repository)
```

The hook into the host is one line in `tools/godot/project/main.gd` (`_ready`, after
`add_child(view)`): `add_child(load("res://hud/hud.tscn").instantiate())`. The HUD finds
the host (its parent), takes `machine` from it, and needs nothing else. With an extension
that has no `RtaGameState` it prints one line and stays off.

## 2. The state interface

`rta_gs_reader* r = rta_gs_create(); const rta_gamestate* s = rta_gs_update(r, ram);` once
per displayed frame, with the machine's 32 MB of main memory, while the game's thread
stands at a vertical blank. Every field of `gamestate.h` has its source beside it. The
reader keeps what the frame before looked like (to tell what happened in between and to
number creatures) and nothing else.

| What | Where it comes from | Evidence |
|---|---|---|
| player: name, class index, level, acknowledged level, experience, health, mana, gold, points | record +0x00, +0x50, +0x59, +0x58, +0x5c, +0xac/+0xb0, +0xc0/+0xc4, +0xe4, +0xe8/+0xec | `docs/player.md`; **Ran** (section 3) |
| class name | text table, key by class index (seven key addresses, `text_getClassName` 0x1eb0f8) | **Ran**: the seven names come out |
| experience bar | `(exp - T[L-1]) / (T[L] - T[L-1])`, `T` = s32 table 0x41b558, `L` = record +0x58 (`hud_drawPlayerStatus` 0x1d9cd4) | **Ran**: 0, 49, 89 of 99 pixels equal |
| healing / mana on its way | record +0xb4 / +0xc8, per tick +0xb8 / +0xbc | **Ran**: after a potion 5.04 -> 7.28 -> 12.38, the game draws the same overlay |
| gold still flying to the counter | `g_goldFloaters` 0x86a900 (8 x 0x24: +0x1c amount, +0x20 slot) + `g_goldPending` 0x86ace8 | Read (`hud_addGoldFloater` 0x1dc268, `hud_tickGold` 0x1dcb80); no gold was picked up in a run here |
| potions | bag 2 (+0x2540, count +0x3740) by the definition's name against the table 0x4ef4c8 (0..8 mana, 9..17 health) - the rule of `player_countPotions` 0x1ba5f8. The game's HUD shows 0x41b940 / 0x41b950, which are only refreshed when a potion is used | **Ran**: 2 / 2, after one health potion 1 / 2, the game's own icon says "x 1" |
| quick slots | record +0x4a84 / +0x4a85 -> ability record +0x4440 + n x 0x68 (+0x20 id, +0x25 kind); name = text table `<skill name>_name` (`g_skillTable` 0x41b170, skill +0 name, +0xc recast); cooldown = object +0x4ae; rank = record +0x4b08 | **Ran**: the name appears, the cooldown runs after a cast (the game dims its mana bar for the same frames) |
| mana cost of an ability | only the older inline abilities carry it as data (ability +0x2c); for `Skill` objects it is a function per class | **not given** (-1): the slots do not show a cost |
| weapon in hand | record +0x4434[+0x4a7c] -> item -> definition name -> text table `<name>_name`, with prefix (0x400e50 + p x 0x28) and suffix (0x4019e0 + s x 0x14) as the game builds it (0x101e48) | **Ran**: the starting weapon comes out with its prefix, as the game's inventory names it |
| status effects | object timers +0x340..+0x350 (burn, chill, shock, poison, second damage over time; seconds), +0x31c / +0x314 / +0x312 (stun, root, charm; frames), slow +0x2fc, spawn protection +0x4b4, hit immunity record +0x4c27, potions at work, timed item modifiers (item +0x24), the sixteen counters +0x36c | Read (`docs/creatures.md`); **Ran** only for "healing" (a potion); the others were not reached in a run |
| player object, alive, place, facing, action | record +0x43d8; flag 0x8; +0x10; +0x38; +0x58c | `docs/objects.md`, `docs/player.md`; Ran |
| local or not | offline all; online `slot >= g_numPeers ? 1 : u8 0x5c3d0c + slot x 0x44e0` (`net_isLocalSlot` 0x13e150) | Read; no net game ran |
| creatures | scan of the object pools (table 0x403a10: 512 x 0x500 at 0x6288c0, 32 x 3000 at 0x6c88c0): flag 0x20, a grid link whose node points back, not a destroyed husk (+0x48 != 0x5122a8), not hidden (0x8000), within 1150 units of a player | **Ran**: 104 creatures in `valor`, 7 in reach |
| creature id | a number given when first seen, kept while object address, type pointer (+0x34) and serial (+0x230) stay | Ran |
| creature name | ShowName (+0x368) through the text table for someone to talk to; the boss meter's own key (0x41ba40) for the creature the meter is about; else the kind's name in the level data (+0x34) - the game has no display name for ordinary monsters and never shows one; the HUD spaces it ("FooBarSmall" -> "Foo Bar Small") | **Ran**: the first level's character by her name; the boars of the second level by their kind |
| hostile | `Player_isEnemy` 0x1b5ea8 as data: creature, not dead, not friendly (flag 0x1000000, cflags 0x4000000 / 0x800), not charmed | Read; Ran on boars (hostile) and the hub's character (not) |
| who a creature is after; whom a player's attack is aimed at | target handle +0x234 (a cell with one node; node +0xc = object); for a player only while action state is 0 or 1 | **Ran**: the attacked boar is the player's target, boars after the player carry the flag |
| boss | rank 2 by the sixteen type names of `creature_bossRank` 0x10d940 (compared in memory), MiniBoss = cflags bit 0, "the game's meter is about it" = cflags bits 0 and 31 with `0x41b6a4` > 0 | **Ran** only by setting bit 0 on a boar from the test (the game then shows its own meter for it); no real boss level was reached |
| events | differences between two frames: health of creatures and players, experience, level, gold, the bags by definition | **Ran**: damage dealt and taken, a kill, +2,100 experience, level 2, a potion leaving the bag. A miss cannot be seen this way (needs a hook in the damage function) |
| prompt | `g_interactPromptAlpha` 0x4d8ac0[slot] > 0 and the tests `Player_draw` makes; text UTF-16 at 0x864f50 + slot x 0x200; what it is about: the nearest usable object (flag 0x100000) in the box round the player, as `Player_interact` 0x1b2640 asks; kind by vtable | **Ran**: the game's own "talk to" line with the character's name, kind shop (property `shop=`), button = the use button |
| the game's message | UTF-16 at 0x86ab78, frames 0x4f66e0 | **Ran**: the level-up line |
| compass target | counter 0x4f66d5, target 0x86a8f0 | Read; no script set it in a run |
| phase | pause menu 0x44f208 / task 0x18cc08, `g_paused`, menus 0x41b69d / 0x41b50c / 0x41b4f8 / tasks, cutscene 0x44fcd0, dialogue 0x8e2d60, help box 0x41b928, gate and mission menu by task, loading (pending level, 0x506094, 0x506048, 0x44f054), front end 0x41b510 / 0x4f85b0, camera mode | **Ran**: pause menu, inventory, a conversation, level change; Read: cutscene, gate menu |
| level name and title | 0x41b721; text table by the level's name | **Ran**: both levels' titles come out as the game's save screen names them |
| camera | `g_cameraPos` 0x44f038, `g_cameraMatrix` 0x44f110, `g_projScale` 0x44f108; or the frame's own view from the host | Ran (bars sit on the creatures) |
| online | stall 0x40279c, exit countdown 0x4f6948, checksum 0x4f7144, per-peer "out of sync" 0x5c3d0f + slot x 0x44e0, chat log 0x8e8ac8 (8 x 0x7e) | Read only |

The text table (`text_lookup` 0x173c84): 8192 key pointers at 0x7c2ea0, the text follows its
key as UTF-16; hash as in `gamestate.cpp`. **Ran** on class names, level titles, item
names, ability names, the hub character's name.

**The picture is one tick older than memory.** A frame's list holds what the game drew a
tick before the memory read at the same blank. **Ran**: in the frames of a hit or a cast
the game's own bar in the picture still had the old value while the field had the new one
(3 of the first 48 comparisons). So every `screen[]` the reader hands out is the place of
one update ago (`rta_gs_set_screen_delay`): with the camera read from memory, the
projection made then; with a camera handed in by the host (which is the shown frame's
own), the old place under that camera.

## 3. How the numbers were checked against the game's own HUD

`local/godot-hud/measure.py`: the game fills each bar to `(int)(start + value / maximum x
99)` pixels of its 640-wide screen (0x1d9cd4). The script finds where the filled colour
ends in the window picture and prints it beside what the HUD's state file of the same
displayed frame says ("hud shot" writes the picture and the state together).

| Run | Pictures | Result |
|---|---|---|
| first level: full; after two casts; experience set to 550 and 1000 by the test; health set to 8.2, 16.4, 24.6, 5.0; a health potion | 11 | health 99, 25, 49, 74, 15, 21, 36 of 99 = the field's; experience 0, 49, 89 = the field's; mana 57..62 = the field's. One mana bar reads "0": the game draws it faint during a cooldown - the same frames in which the HUD's slot shows the cooldown |
| a fight in `valor`, nothing set by the test: full, one hit (3.8 of 32.8), dead | 5 | all equal |

16 pictures, 48 comparisons, 47 equal within one pixel of 99. An earlier run of the same
kind had 3 more differences, all in the frame of a hit or a cast itself (the tick of lag
above). Potion count: the game's own icon "x 1" beside the HUD's 1
(`pictures/v-hub-430.png`).

Not checked against the game's own display, because the game has none or the situation
was not reached: creature health (the game shows no bars; the values are the fields the
damage function writes), gold pickup, status timers other than a potion's, the compass.

## 4. Layouts, settings, commands

| Layout | When | What |
|---|---|---|
| overhead | view overhead / action | player frame lower left, party above it, slots lower middle, gold and feed lower right, radar upper right, target and boss bar upper middle, attackers beyond the picture as arrows at its edge |
| third person | chase / shoulder | the same frame a little smaller, slots lower right with gold above them, a compass strip instead of the radar, attackers out of sight on a ring round the middle |
| first person | first | two slim bars lower middle, slots lower right, compass strip, a dot where the view looks, corner marks on the enemy a swing would take, the prompt always drawn by the HUD (the game draws none when the player's model is left out) |

The layout follows the view of the frame (`RtaMachine.get_view().shown`); `view` forces
one. Scale: design pixels of a 1080-high picture, never below 0.74 (small print stays at
ten pixels); safe margin 2.5 % of the height; the corners never farther out than a 2:1
picture's.

Settings (`user://hud.cfg`, `[hud]`), command line after `--`, and script lines `app hud
...` (a script line can pass unseen in a run that is not paced: `--hud-at
"LEVEL@TICK:words;..."` runs words at a simulation tick, or `LEVEL@pause|menu|dialogue:`
once that screen has been up 45 blanks):

| Setting | Command line | Values |
|---|---|---|
| `mode` | `--hud` | `new` (asks the game's own HUD layer off), `original` (this HUD hidden), `both` |
| `view` | `--hud-view` | `auto`, `overhead`, `third`, `first` |
| `scale` | `--hud-scale` | 0.5 .. 2 |
| `numbers`, `radar` | | `on` / `off` |
| `music`, `music_volume` | | `on` / `off`, 0 .. 1 |
| `theme` | `--hud-theme` | a skin script, or `default` |
| test aids | `--hud-fake-party N`, `app hud say`, `shot FILE`, `cost`, `test ...`, `test-portal`, `test-sticks`, `delay 0|1`, `music say|tap|game V` | |

The HUD fades out (0.12 s) while a game screen is up - inventory, shop, character sheet,
a conversation, a help box, the gate or mission menu, a cutscene, loading - and when the
view falls back for anything but death. **Ran**: inventory, a conversation, the pause
menu (`pictures/s-inventory.png`, `s-talk-dialogue.png`, `s-pause.png`). Menus are not
rebuilt: they are the game's own.

## 5. The game's own HUD layer

`mode new` calls `machine.set_option("game_hud", "off")` (the Godot agent's switch:
player status, gold, compass, minimap, spell selector). **Ran**: the pictures `s-*` are
taken that way. Two functions of the game's HUD are not wrapped and still draw: the boss
meter with the one-line message (0x1d93b0) and the prompt box (0x1d99f0). Asked for as
`set_option("game_hud_text", "off")` (`hud-recomp.patch`, note 2). Until the library has
it the HUD does not draw its own message and prompt over the game's (except in first
person, where the game draws no prompt), and moves its slots above the game's meter while
a boss is up (`pictures/s-c43-2650.png`).

## 6. Pictures (all `local/godot-hud/pictures/`, Godot's own capture of the window)

| Picture | Shows |
|---|---|
| `s-w169-2600.png`, `s-w169-2760.png` | 16:9, overhead, game HUD off: frame, slots, radar, a boar's bar, attackers beyond the picture, a party frame from test data |
| `s-w219-2500.png` | 21:9: the corners stay inside a 2:1 area |
| `s-c43-2650.png` | 4:3 with everything at once: boss bar, three party frames (one down), chat, a desync notice - all three from test data and marked so - floating numbers; nothing overlaps |
| `s-chase169-2700.png` | third person: compass strip, a bar above the boar in 3-D, attackers on the ring |
| `s-first43-200.png`, `s-first169-200.png`, `s-firstv-2600.png` | first person: the minimal layout, the prompt, attackers behind |
| `f1-2700.png` | a kill: +2,100 experience, LEVEL 2, the game's message as a clean line (both HUDs on) |
| `v-fight-2500.png`, `v-hub-430.png` | beside the game's own HUD: 4 / 33 with the trail of what was lost; a potion at work |
| `s-pause.png`, `s-inventory.png`, `s-talk-dialogue.png` | the pause band; the HUD away under the game's own screens |
| `s-notice-key.png` | the portal's invitation card (stand-in portal, test data) |
| `s-skin-2600.png` | the example skin |
| `s-boss-2520.png` | the boss bar with the player's music playing (test tones) |

**Not shown**: a real boss (the "boss" is a boar whose MiniBoss bit the test set), a real
second player, a gold pickup, an item pickup, status effects other than a potion's, the
compass with an objective, a cutscene. First person at 16:9 has no prompt in its picture
(the scripted walk ends elsewhere at that shape).

## 7. Working with the others

- **Views** (`fpview.h`): the layout and the camera of the frame come from
  `RtaMachine.get_view()`. In the overhead view that Dictionary has no camera (all zero):
  the reader then takes the game's own from memory (asked to be filled, note 3 of the
  patch file).
- **Controls** (`fpcontrols::hud()`): the HUD looks for `RtaMachine.get_controls_hud()`
  and uses `locked` / `shot` / `melee` for the aim marks, `reticle` for the dot, `threats`
  for the attackers out of sight. **Not run**: no library hands it out yet (note 4).
  Without it the HUD derives the marks itself: the creature the player's attack is aimed
  at, else the nearest enemy near the middle of a first-person view; attackers from the
  creatures' own targets; where a hit came from, from the player's last attacker (object
  +0x2e4).
- **Portal**: the HUD finds the node in group `portal`, sets `draw_notices_in_game =
  false`, draws `notice(d)` as one card in the upper right corner (over the game's own
  screens too) and drops it at `notice_gone(id)`. **Answering in the game**: F2 (the
  portal's key) and, on a controller, **both sticks pressed together and held half a
  second**. Every button of the pad is the game's; this chord takes none away - the game
  still gets its two buttons (left stick: its camera swings behind the character; right
  stick: its map changes size), no action of the character is on either, and it is not
  pressed by accident. Not answering lets the card run out. **Ran** with a stand-in
  portal (`dev/portal_stub.gd`): the card, the chord made by the test, `notice_answer(id,
  true)` arriving. **Not run** with the real portal.

## 8. Custom music

The player's own files, nothing shipped, nothing fetched: `<data folder>/music/boss/`
(`.ogg`, `.mp3`, `.wav`); `music/level/<level>/` and `music/menu/` are reserved and not
played yet. `music/music.gd`: when a boss is engaged (the game's boss meter is up, or a
boss is after a player or hurt) and the folder has files, a track is loaded on a thread,
fades in over 1.6 s and loops; shuffled, none again before all were played. Four seconds
after the boss is dead, every local player is, or the boss is left behind, it crosses
back over 3 s. An empty or missing folder changes nothing. The folder is read when a
level starts.

The game's music by itself: the stream driver's stream 2 is the music, apart from speech
and effects. The two hunks of `tools/godot/hud-recomp.patch` add a host gain for that
stream and `rtag_set_option("music_volume", "0..1")`. **Ran** in a private library with
only stream 2 rendered: 1.0 -> mean -24.5 dB, 0 -> silence, 0.25 -> -32.9 dB; with the
whole mix the three settings differ by 3 dB (the narrator and the effects stay). A library
without the option answers "no": the director then ducks the whole game mix by 14 dB.

**Ran** with two test tones made here (`local/godot-hud/tones/`, 2 s sines): boss engaged
at tick 2422 -> loaded -> level 0.98 with the game's music at 0.00 -> held through the
fight -> back after the boss died; with an empty folder no line but "0 track(s)". Nobody
listened: test runs are muted; the levels are the mixer's own figures.

## 9. Theme

All drawing of panels, bars, text, key caps and glyphs is in `style.gd`; the pieces draw
no such shape themselves. A skin is a script with any of `setup`, `panel`, `bar`, `text`,
`status_icon`, `glyph`, `flask`, `coin`, `skull`, `keycap` (signatures at the head of
`style.gd`); what it returns false for is drawn as before. `--hud-theme
res://hud/dev/skin_example.gd` (**Ran**, `pictures/s-skin-2600.png`) changes the palette,
panels and bars and nothing else. A later skin with the game's own art loaded at run time
is that swap; nothing of it is started here.

## 10. Cost

The HUD measures itself (`app hud cost`): the time of `hud.gd`'s `_process` with all
pieces' `tick`, of it the reader, and the pieces' `_draw` calls. Wall time on a machine
that was loaded the whole day (load average 95 to 240), so these are upper figures.

| Run | Scripts per frame | of it the reader | Drawing per frame |
|---|---|---|---|
| a fight, 16:9, overhead, game HUD off, paced (60.0 pictures a second, 5,475 frames) | 239 us | 15.5 us | 91 us |
| the same in the chase view (5,473 frames) | 230 us | 15.3 us | 82 us |
| everything at once at 4:3: boss bar, three party frames from test data (redrawn every frame), chat, a desync notice (pulsing), the portal's card; paced (59.7 a second, 5,876 frames) | 289 us | 15.5 us | 507 us |
| not paced, 16:9 fight / boss with music (1,245 / 1,332 frames) | 244 / 230 us | 15 us | 265 / 137 us |

So a frame of play costs about **0.33 ms** (scripts and drawing calls together), and the
worst picture that could be staged **0.80 ms**; the reader itself is 15 microseconds. All
under the millisecond asked for, the worst case not by much. Where the time goes (Read,
from the structure, not profiled): the scripts' share is mostly turning the state into
Godot values every frame (one Dictionary per player, the frame's Dictionary, the creature
array) and the pieces' checks whether anything changed; the drawing share is text - every
string is drawn twice, outline and fill. Each piece is drawn again only when what it shows
changed or moves (the compass and, while anything is there, the world piece every frame).
What Godot's renderer then spends on the HUD's canvas items is not in these figures.

## 11. What has to be merged where

1. `tools/godot/project/main.gd`: the one line (section 1).
2. `tools/godot/extension`: nothing more (the class is registered; the reader's directory
   is named in its CMake).
3. `tools/godot/hud-recomp.patch`: the two hunks (music volume) into
   `tools/recomp/sound/drivers.cpp` and `tools/godot/lib/rtag.cpp`; and its notes 2 to 4
   as requests: the second HUD group hideable (two addresses in `hle.txt`), the camera in
   the overhead view's `rtag_view`, `get_controls_hud()`.
4. The native application (`rta_app`) can use the same reader: `rta_gs_update(reader,
   rta::memory())` from its frame hook; nothing of that is written.

## 12. Left

- A real boss level, a real second player, gold and item pickups, the other status
  effects, the compass with an objective, a cutscene: reach them and look.
- Misses, and whose hit a number belongs to when two players strike the same creature in
  one frame: need a hook in the damage function (0x1e8230).
- Mana cost of `Skill` abilities; the eight abilities of the quick-cast ring by name (the
  ring shows the chosen direction only).
- A map: the game's automap grid (0x4044f0, 216 x 216 cells of 120 units, reveal level in
  bits 12-15) is cheap to read; the radar shows creatures, players and the objective, not
  the ground.
- The controls data and the real portal, once the library and the portal run with it.
- Paced at a steady 60 on a free machine with a person looking at motion; nobody has
  looked at the HUD moving, only at pictures at fixed ticks.

## How it is built and run here

The Godot agent owns `tools/godot/` and changes it while this is written, so everything
runs from a snapshot (three were taken as its tree moved):

- `local/godot-hud/root/` - a private root: `tools/godot` copied 15:25, its own
  `build.py snapshot --refresh --from <workspace>` and `build.py lib` run there, so the
  library is built from the shared tree as it stood then (views, `game_hud`), plus the two
  music hunks. (`local/godot-hud/snap`, `snap2`: the earlier ones.)
- `python3 local/godot-hud/hud.py ext` compiles that snapshot's extension sources and the
  HUD's `rta_gamestate.*` with clang against the godot-cpp library the Godot agent built
  (by reference; `RtaNet2` left out); `hud.py stage` makes `local/godot-hud/project/` (the
  snapshot's project, `tools/godot/project/hud/`, the hook line); `hud.py run NAME --
  ...` starts Godot (the one under `local/godot-spike/deps`, home redirected to
  `local/godot-hud/godot-home`) at nice 10 in a small window titled "AGENT TEST - HUD
  NAME", without focus, sound muted; log and data under `local/godot-hud/test/NAME/`.
- Routes: `mkroute.py` (power-on to the first level by the Godot agent's tick-keyed route,
  then a body from `routes/`), `mkfight.py` (its fight in `valor` with commands at chosen
  ticks). `shots.sh` makes the picture set; `measure.py` is section 3; `crop.py` enlarges
  a piece of a picture.

## Processes

Every Godot started here was started by `hud.py run`, which records the process id in
`local/godot-hud/test/NAME/pid`, waits for it and kills it on a time-out. **Checked at
the end (15:50): 33 process-id files, none of the processes exists any more; no process
on the machine has `godot-hud` in its command line; no Godot process is running at all.**
The two research helpers started at the beginning (they only read the decompile) have
ended; one of them wrote helper scripts into the session's shared scratch directory and
said it overwrote a file `rd.py` there once (it was replaced again by its owner's version
afterwards) - told to the coordinator.
