# Hub mission menu art and layout

US `SLUS_209.73` v2.00, `t3/research-story-route`, 2026-10-23. This is a
function-level capture of the original `missionMenu_draw` 0x232300 and
`missionMenu_run` 0x2316fc with `tools/ee_emu.py`, seeds 20973 and 7. The
reference is `tools/ref_mission_menu_art.py`; the executable/disc comparison
is `tools/difftest_mission_menu_art.py`. The earlier route test's 26 state
snapshots per seed still establish the fresh selection's `blood1` request.

**Boundary:** UI resource lookup, localization, font rasterization and GPU
submission are stubbed. The calls and their arguments are **Executed**; the
addresses and table fields are **Observed** in the pinned executable. The
read-only ISO check reads texture header dimensions. Textures are named here by
the address of the name string the code passes (the names stay in the owner's
executable). There is no captured
retail screenshot, resolved localized prose, or native visual parity claim.

## Ownership and data

`missionMenu_open` 0x231520 registers a run task at priority 20 and a draw
task at the same priority (0x231650, 0x23166c). The draw task reads the menu
row `0x8e2f0c`, column `0x8e2f0d`, fade counter `0x8e2f04`, and scroll
vectors `0x8e2ec0`/`0x8e2ef0`. It calls the background tiler 0x2331e8 at
0x232504. `g_missionTable` 0x4fe540 has thirteen 0x34-byte records, of which
the first twelve have a mission image and position and row twelve is a
nameless terminator. Row `i` is mission `i+1`, as in `docs/data-tables.md`
§7.4. The twelve image identifiers and `(x,y)` pairs are asserted in the
reference: `(140,40)`, `(70,240)`, alternating by 70 horizontal units and
200 vertical units through `(70,2240)`. The image name pointers at +0x18 are
0x540da0 for row zero, 0x540df0 and 0x540e20 for rows one and two. Row eleven
has an alternative image pointer (0x5410d8) at +0x1c; `game_getEvil` 0x1bf8d8
chooses the alternative at 0x232858–0x232874 when present. The drawing loop
uses +0x2c/+0x30 as node position (0x2326c8–0x2326dc, 0x2328d4–0x232908).
The difftest forces each of the twelve rows as the centred scroll target,
sets the 0x1658f0 interpolation return to zero, and verifies that its node
appears at y=40, with the next two nodes at y=240/440 where present.
It checks both locked later rows and a synthetic all-available state.
This is a controlled endpoint, not evidence of the intervening scroll frames.
The table's `+0x20/+0x24/+0x28` entry flags and story/medal/bonus level
pointers remain the authority for row choices; the art is not a separate
mission list.

**Observed** row identifiers and level pointers (all asserted by the new
difftest; `—` means a null pointer):

| Mission | Display key | Story level | Medal / bonus | Map image (name at) |
|---:|---|---|---|---|
| 1 | `Plane_of_War` | `blood1` | `blomedal` / `boar1` | 0x540da0 |
| 2 | `Plane_of_Innovation` | `innovat1` | `innmedal` / `innpit` | 0x540df0 |
| 3 | `Norrath_Pit` | `islc1` | — | 0x540e20 |
| 4 | `Plane_of_Water` | `wat1` | `watmedal` / `watbonus` | 0x540e68 |
| 5 | `Plane_of_Torment` | `tormenta` | `tormedal` / `torbonus` | 0x540ec0 |
| 6 | `Plane_of_Disease` | `swamp1`, evil `swamp2` | `dismedal` / `disbonus` | 0x540f18 |
| 7 | `Plane_of_Valor` | `valor` | `valmedal` / `honor2` | 0x540f58 |
| 8 | `Plane_of_Fire` | `fire1` | `firmedal` / `firbonus` | 0x540fa0 |
| 9 | `Plane_of_Storms` | `storm1` | `stomedal` / `stobonus` | 0x540fe8 |
| 10 | `Norrath_Faydark` | `fay2`, evil `fay1` | — | 0x541018 |
| 11 | `Plane_of_Nightmares` | `nit1` | `nitmedal` / `nitbonus` | 0x541068 |
| 12 | `Plane_of_Fear`, evil `Plane_of_Tranquil` | `bossgood`, evil `bossevil` | — | 0x5410c8, evil 0x5410d8 |

Mission availability is a player-record flag, not implied by having a table
row. The fresh route has only mission 1 available; the remaining map nodes
draw dark until their corresponding mission byte is available.

## Original draw submissions

Coordinates below are UI API arguments in a 640×448 design space. The plain
sprite primitive adds one to `y` in its packet (`t3/research-ui`
`docs/formats/ui-fonts.md` and `tools/ref_ui_layout.py`); no GPU packet was
compared here. The fixture holds fade counter 127 and initial scroll.

| Element | **Executed** original call (texture name at) | Disc texture header and limit |
|---|---|---|
| Side frame | the frame strip (0x541198) at 0x232420/0x232480; eight 0x17fb88 submissions at x 0 and 608, y 0/128/256/384, layer 3, tint `0x7f808080` | 32×128; strip composition is submitted, rendered edge pixels unknown. |
| Moving backdrop | 0x2331e8: four cosmic-line (0x541300), four starfield (0x541310) and one sparkle (0x541320) lookups at 0x233280–0x23372c, layer 3 | Each 640×448. Cosmic tint `0x14808080`, starfield `0x7f808080` in the controlled run; the modulo-scroll math uses stubbed external float callees, so exact moving rectangles and speed remain unknown. |
| Map nodes | 0x2328cc lookup and 0x232908 sprite: initial viewport rows 0, 1, 2 at `(140,40)`, `(70,240)`, `(140,440)`, layer 4. The centred endpoint is checked for all twelve rows using table positions. | Each tested image is 411×156. Fresh mission 1 is `0x7f808080`; locked later rows are `0x7f3c3c3c`. Marking mission 2 available changes its node to `0x7f808080`; the synthetic all-available state brightens all twelve. |
| Links | 0x232b30/0x232bc0: pipe 1 (0x541228) `(186,181)`, pipe 2 (0x541238) `(186,381)`, pipe 1 `(186,581)`, layer 4 | Pipes 1 and 2 are 249×74. The first pipe brightens from `0x7f3c3c3c` to `0x7f808080` when mission 2 becomes available. Other pipe variants and scroll states remain to capture. |
| Row zero marks | the shard (0x5411a8) `(283,101)` at 0x232630 when complete; amulet 1/2/3 (0x5411d8/0x5411c8/0x5411b8) `(215,91)` selected by medal at 0x2326a0/0x232734; the bonus mark (0x5411e8) `(167,99)` at 0x2327ec/0x232828 for top medal. The complete-state amulet 2 overlay is a separate 0x232754/0x2327a4 call. | 35×34 shard, 53×52 amulets, 33×34 bonus. The latter overlay is dark in the controlled state. Texture lookup must succeed for the medal icon draw branch; the difftest supplies a nonzero synthetic handle. |
| Selection glow | Selected, available row zero: column 0 glow (0x5411f8) `(300,44)`, column 1 glow (0x541208) `(198,73)`, column 2 glow (0x541218) `(152,85)`, 0x232920–0x232a9c | 256×146, 88×88, 64×62 respectively. Column 1/2 are forced after giving completion/top medal; 0x232a14 calls sine 0x1666e0 and 0x232a3c–0x232a68 combines pulse/fade into tint. Full pulse and displayed blending remain unknown. |

Row eleven's evil control instead looks up its alternative image (0x5410d8) at 0x23286c,
submits it at `(70,40)` at 0x2328a8, and switches the detail key from
`Plane_of_Fear` to `Plane_of_Tranquil`; this was **Executed** in a forced
state, not confirmed in a retail playthrough.

The mission-map lump has 32 textures in the read-only disc check. The test
reads each name the code uses from the executable (31 of them, including pipes
3–6, which this fixture does not submit) and asserts its header dimension; it
neither copies textures nor stores their names. The prior
`t3/research-menus-layout` result for general interface list frames concerns
other menus. This mission map has its
own frame strips and node sprites. The `t3/research-menus` flow contract
still applies to task ownership and lockstep input.

## Text and prompts

The detail batch begins at 0x232f2c with the small-font word `0x4f7104`
(sentinel planted in the test), layer 5 and controlled colour `0x0049616a`.
The title uses 0x181530 at 0x233044 with arguments
`(320,267,0,550,262,365,21)`; description text uses 0x181ca0 at
0x233074, anchored `(320,235)`. The local prompt is anchored `(320,410)`
at 0x2330f8; 0x233094 sets its controlled colour `0x64464646`.
0x2331a8 also submits a framed rectangle `(25,230,590,215)`, with alpha
from `0x8e2f08`. These are call arguments, not resolved glyph positions.

The selected row name key at table +0x00 (or +0x04 under the evil branch)
is combined at 0x232fc8–0x233024 with `_mis`, `_med`, or `_bon` according to
column 0/1/2, then `_title` for the title lookup. The executed row-zero keys
are `Plane_of_War_mis`, `_med`, `_bon` and their `_title` variants; only
identifiers, no localized text, are stored in the test. Offline/local-first
draws look up `AcceptBack` (0x2330a0). In a network game where this machine
is not first active, `clientMissionSelect` is looked up at 0x233140 unless
the local pause menu is open (0x233108–0x233158). The prompt branches are
executed separately; they do not establish a network session.

## Availability and input/transition gates

**Observed** helper 0x2310d4 treats row zero as present, while later rows
query `mission_isAvailable` 0x1bf698 with mission `row+1`. The original
draw uses this to choose bright/dark node and pipe tint. Helper 0x231310
checks table flag +0x20 and `mission_isComplete` 0x1bf730; helpers
0x2311d4/0x231180/0x23112c check medal thresholds 3/2/1; 0x231228
checks completion plus medal-level pointer; 0x231360 checks top medal.
These calls gate the shard/amulet/bonus art and the selectable columns.
The probes execute mission-1 flags 1 and 3 and medal 0–3; they do not claim
every campaign state is reachable.

**Executed** `missionMenu_run` input probes after its 16-tick fade: opening
selection is the highest currently available row, so fresh state selects
row zero and a fixture with mission 2 available selects row one.
The lockstep pad word is `0x41bfe4`. A confirm bit `0x40` on fresh row-zero
story column enters state 5, then 6/7/8 and writes `blood1` as proved by
`difftest_story_route.py`. Cancel bit `0x20` (also `0x100` in the read)
enters state 4 and the fade counter falls from 127 to zero in eight further
ticks; task removal at 0x2320ec–0x2320fc is **Observed**, but the synthetic
test does not run the task scheduler. Down `0x4000` (also `0x200000`)
moves row zero to available row one and resets the column. Right `0x8000`
(also `0x400000`) needs mission completion to reach medal column 1; from
column 1, medal 3 is needed to reach bonus column 2. The tested calls request
the accept sound (name at 0x541128) on confirm **and cancel**, and
the toggle sound (0x541140) on successful movement. The owner's pause-menu gate
at 0x231a4c–0x231a78 remains the known lockstep caveat from
`docs/issues/draw-sim-leaks.md` U2.

## Ordered native port

1. Load the mission-map lump from the owned disc and validate its 32
   textures and each header dimension. Bind the UI coordinate/layer/tint
   semantics from `t3/research-ui` before presenting them. Match the
   executed frame, cosmic/starfield and dark medal-overlay tint arguments,
   title's seventh argument, and prompt colour in the controlled state.
2. Port the 13-row `g_missionTable` and row/column helper gates. Keep the
   row-zero special case, story/evil/medal/bonus destination pointers and
   the nameless terminator. Derive locked art from actual player mission and
   medal records, not a hard-coded route state.
3. Render the eight frame strips, the 0x2331e8 background layers, visible
   image nodes, icon overlays and connecting pipes at their table-driven
   positions. Match scroll, clipping, frame alpha and sine glow against
   original frames before declaring visual parity.
4. Use the small-font/localization lookup path for detail keys, title,
   description and local/network prompt, including the evil alternative.
   Compare actual glyph layout and alpha across fade, scroll and locale.
5. Connect lockstep input, availability gates, sounds, fade/close and direct
   pending-level write to the existing route contract. Compare the
   mission-2 opening row, nine cancel snapshots through zero, and primary
   and alternate down/right bits before integrated hub validation. Then
   validate confirm/cancel in a native hub session and test the `blood1` load.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission_menu_art.py --elf /path/to/SLUS_209.73 --iso '/path/to/Champions - Return to Arms (v2.00).iso'
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_story_route.py --elf /path/to/SLUS_209.73 --hub-gob /path/to/hub-archive --blood-gob /path/to/first-level-archive
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

The art comparison pins the ELF SHA-256, compares the 13 table records,
checks the count of the lump's textures and the dimensions of the 31 the code
names, reading the names from the executable,
and checks 39 draw fixtures and twenty input fixtures per seed. The draw
fixtures also check controlled tints, full title arguments and prompt colour;
the input fixtures check the opening row, cancel fade and alternate bits.
The reference contains only string addresses, display and level keys,
dimensions, coordinates and bounded state rules. Full rendered art, scroll
animation, localization, a real controller and native parity remain open.
